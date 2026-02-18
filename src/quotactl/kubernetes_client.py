"""Kubernetes API client for namespace operations via Rancher kubeconfig.

Retrieves namespace details from the Kubernetes API; Rancher stores project
association and other metadata in namespace annotations (e.g., field.cattle.io/projectId).
"""

import os
from typing import Any, Dict, List, Optional

import requests
import urllib3
import yaml

from quotactl.logging import ContextLogger
from quotactl.models import Namespace, QuotaSpec

# Rancher annotation for project association: cluster-id:project-id
PROJECT_ID_ANNOTATION = "field.cattle.io/projectId"


class KubernetesAPIError(Exception):
    """Base exception for Kubernetes API errors."""

    pass


def _parse_kubeconfig(kubeconfig_str: str) -> tuple[str, str, bool]:
    """Parse kubeconfig YAML and extract server URL and token.

    Returns:
        Tuple of (server_url, token, verify_ssl).
        token may be empty if using client-cert auth.
    """
    config = yaml.safe_load(kubeconfig_str)
    if not config or not isinstance(config, dict):
        raise KubernetesAPIError("Invalid kubeconfig format")

    clusters = config.get("clusters", [])
    users = config.get("users", [])
    contexts_list = config.get("contexts", [])
    current_context = config.get("current-context")

    if not clusters or not users or not current_context:
        raise KubernetesAPIError("Kubeconfig missing clusters, users, or current-context")

    # Find current context
    context_map = {c["name"]: c.get("context", {}) for c in contexts_list if "name" in c}
    ctx = context_map.get(current_context, {})
    cluster_name = ctx.get("cluster")
    user_name = ctx.get("user")

    if not cluster_name or not user_name:
        raise KubernetesAPIError("Could not resolve current context")

    # Find cluster and user
    cluster_data = next((c.get("cluster", {}) for c in clusters if c.get("name") == cluster_name), {})
    user_data = next((u.get("user", {}) for u in users if u.get("name") == user_name), {})

    server = cluster_data.get("server", "")
    if not server:
        raise KubernetesAPIError("Kubeconfig cluster has no server URL")

    # Verify SSL - False if insecure-skip-tls-verify
    verify = not cluster_data.get("insecure-skip-tls-verify", False)
    if cluster_data.get("certificate-authority-data"):
        verify = True  # CA data implies verification

    # Token auth (common from Rancher generateKubeconfig)
    token = user_data.get("token", "")
    if not token:
        # Client-cert auth - not supported directly; would need cert files
        raise KubernetesAPIError(
            "Kubeconfig uses client-cert auth; token auth required from Rancher"
        )

    return (server, token, verify)


class KubernetesClient:
    """Client for Kubernetes API operations, using credentials from Rancher."""

    def __init__(
        self,
        base_url: str,
        token: str,
        logger: ContextLogger,
        verify: Optional[bool] = None,
    ):
        """Initialize Kubernetes client."""
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.logger = logger
        if verify is None:
            verify = os.getenv("RANCHER_INSECURE_SKIP_VERIFY", "").lower() not in (
                "1",
                "true",
                "yes",
            )
        self.verify = verify
        if not self.verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

    def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request to Kubernetes API."""
        url = f"{self.base_url}{path}"

        if method.upper() == "GET":
            response = self.session.get(url, timeout=30, verify=self.verify)
        elif method.upper() == "PATCH":
            response = self.session.patch(
                url,
                json=data,
                headers={"Content-Type": "application/strategic-merge-patch+json"},
                timeout=30,
                verify=self.verify,
            )
        elif method.upper() == "PUT":
            response = self.session.put(url, json=data, timeout=30, verify=self.verify)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        response.raise_for_status()
        return response.json()

    def list_namespaces(self) -> List[Dict[str, Any]]:
        """List all namespaces with metadata and annotations."""
        data = self._request("GET", "/api/v1/namespaces")
        return data.get("items", [])

    def list_namespaces_in_project(self, project_id: str) -> List[Namespace]:
        """List namespaces in a Rancher project via field.cattle.io/projectId annotation."""
        items = self.list_namespaces()
        result: List[Namespace] = []
        for item in items:
            metadata = item.get("metadata", {})
            annotations = metadata.get("annotations", {}) or {}
            ns_project_id = annotations.get(PROJECT_ID_ANNOTATION)
            if ns_project_id == project_id:
                ns = self._namespace_from_k8s_item(item, project_id)
                result.append(ns)
        return result

    def get_namespace(self, name: str) -> Optional[Dict[str, Any]]:
        """Get namespace by name with full metadata and annotations."""
        try:
            return self._request("GET", f"/api/v1/namespaces/{name}")
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 404:
                return None
            raise KubernetesAPIError(f"Failed to get namespace {name}: {e}") from e

    def patch_namespace(self, name: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Patch namespace (e.g., to update annotations)."""
        return self._request("PATCH", f"/api/v1/namespaces/{name}", data=patch)

    @staticmethod
    def _namespace_from_k8s_item(item: Dict[str, Any], project_id: str) -> Namespace:
        """Build Namespace from Kubernetes namespace item."""
        metadata = item.get("metadata", {})
        name = metadata.get("name", "")
        uid = metadata.get("uid", "")
        annotations = metadata.get("annotations", {}) or {}

        # Rancher namespace ID format: cluster:namespace-name (uid-based in Rancher)
        # Use cluster:name as identifier for k8s namespaces
        ns_id = f"{project_id.split(':')[0]}:{name}" if ":" in project_id else name

        # Extract quota from annotations if Rancher stores them there
        # Supports both limit.cpu / reservation.cpu and limit.limitsCpu / limit.requestsCpu
        quota = QuotaSpec()
        quota_anno = annotations.get("field.cattle.io/resourceQuota")
        if quota_anno and isinstance(quota_anno, str):
            try:
                import json
                q = json.loads(quota_anno)
                limit = q.get("limit", {})
                reservation = q.get("reservation", {})
                cpu_limit = limit.get("cpu") or limit.get("limitsCpu")
                memory_limit = limit.get("memory") or limit.get("limitsMemory")
                cpu_reservation = (
                    reservation.get("cpu") or limit.get("requestsCpu")
                )
                memory_reservation = (
                    reservation.get("memory") or limit.get("requestsMemory")
                )
                quota = QuotaSpec(
                    cpu_limit=cpu_limit,
                    memory_limit=memory_limit,
                    cpu_reservation=cpu_reservation,
                    memory_reservation=memory_reservation,
                )
            except (json.JSONDecodeError, TypeError):
                pass

        return Namespace(
            id=ns_id,
            name=name,
            project_id=project_id,
            quota=quota,
        )

    @classmethod
    def from_kubeconfig(
        cls,
        kubeconfig_str: str,
        logger: ContextLogger,
        verify_override: Optional[bool] = None,
    ) -> "KubernetesClient":
        """Create client from kubeconfig YAML (e.g., from Rancher generateKubeconfig).

        If verify_override is not None (e.g. from RancherClient.verify), it takes
        precedence over kubeconfig and env so --insecure applies to K8s API calls too.
        """
        server, token, verify = _parse_kubeconfig(kubeconfig_str)
        if verify_override is not None:
            verify = verify_override
        elif os.getenv("RANCHER_INSECURE_SKIP_VERIFY", "").lower() in ("1", "true", "yes"):
            verify = False
        return cls(base_url=server, token=token, logger=logger, verify=verify)
