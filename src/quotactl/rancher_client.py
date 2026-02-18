"""Rancher API client."""

import json
import os
import time
from typing import Dict, List, Optional

import requests

from quotactl.kubernetes_client import KubernetesClient
from quotactl.logging import ContextLogger
from quotactl.models import Namespace, Project


class RancherAPIError(Exception):
    """Base exception for Rancher API errors."""

    pass


class RancherClient:
    """Client for Rancher API operations."""

    def __init__(
        self,
        base_url: str,
        token: str,
        logger: ContextLogger,
        verify: Optional[bool] = None,
    ):
        """Initialize Rancher client."""
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
        endpoint: str,
        data: Optional[Dict] = None,
        max_retries: int = 3,
    ) -> Dict:
        """Make HTTP request with retry logic."""
        url = f"{self.base_url}{endpoint}"

        for attempt in range(max_retries):
            try:
                if method.upper() == "GET":
                    response = self.session.get(url, timeout=30, verify=self.verify)
                elif method.upper() == "PUT":
                    response = self.session.put(
                        url, json=data, timeout=30, verify=self.verify
                    )
                elif method.upper() == "POST":
                    response = self.session.post(
                        url, json=data, timeout=30, verify=self.verify
                    )
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else None

                # Don't retry on client errors (4xx) except 409
                if status_code and 400 <= status_code < 500 and status_code != 409:
                    if status_code == 401:
                        raise RancherAPIError("Authentication failed") from e
                    elif status_code == 403:
                        raise RancherAPIError("Authorization failed - insufficient permissions") from e
                    elif status_code == 404:
                        raise RancherAPIError(f"Resource not found: {endpoint}") from e
                    else:
                        raise RancherAPIError(
                            f"Client error {status_code}: {e.response.text if e.response else str(e)}"
                        ) from e

                # Retry on 409 (conflict) or 5xx errors
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    self.logger.warning(
                        f"Request failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    time.sleep(wait_time)
                    continue

                raise RancherAPIError(
                    f"Request failed after {max_retries} attempts: {e}"
                ) from e

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    self.logger.warning(
                        f"Request error (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    time.sleep(wait_time)
                    continue

                raise RancherAPIError(f"Request failed: {e}") from e

        raise RancherAPIError(f"Request failed after {max_retries} attempts")

    def get_cluster(self, cluster_id: str) -> Dict:
        """Get cluster information."""
        return self._request("GET", f"/v3/clusters/{cluster_id}")

    def list_projects(self, cluster_id: str) -> List[Project]:
        """List all projects in a cluster."""
        response = self._request("GET", f"/v3/projects?clusterId={cluster_id}")
        data = response.get("data", [])
        return [Project.from_rancher_dict(item) for item in data]

    def get_project(self, project_id: str) -> Project:
        """Get project by ID."""
        data = self._request("GET", f"/v3/projects/{project_id}")
        return Project.from_rancher_dict(data)

    def update_project(self, project_id: str, quota_data: Dict) -> Project:
        """Update project quota."""
        # First get current project data
        current = self._request("GET", f"/v3/projects/{project_id}")

        # Merge quota data
        current.update(quota_data)

        # Update project
        updated = self._request("PUT", f"/v3/projects/{project_id}", data=current)
        return Project.from_rancher_dict(updated)

    def list_namespaces(self, project_id: str) -> List[Namespace]:
        """List namespaces in a project via Kubernetes API (field.cattle.io/projectId annotation)."""
        cluster_id = project_id.split(":")[0] if ":" in project_id else ""
        if not cluster_id:
            return []
        kubeconfig = self.generate_kubeconfig(cluster_id)
        k8s_client = KubernetesClient.from_kubeconfig(kubeconfig, self.logger)
        return k8s_client.list_namespaces_in_project(project_id)

    def get_namespace(self, namespace_id: str) -> Namespace:
        """Get namespace by ID (cluster:name format) via Kubernetes API."""
        parts = namespace_id.split(":", 1) if ":" in namespace_id else ("", namespace_id)
        cluster_id, ns_name = parts[0], parts[1] if len(parts) > 1 else parts[0]
        if not cluster_id or not ns_name:
            raise RancherAPIError(f"Invalid namespace ID format: {namespace_id}")
        kubeconfig = self.generate_kubeconfig(cluster_id)
        k8s_client = KubernetesClient.from_kubeconfig(kubeconfig, self.logger)
        item = k8s_client.get_namespace(ns_name)
        if not item:
            raise RancherAPIError(f"Namespace not found: {namespace_id}")
        project_id = item.get("metadata", {}).get("annotations", {}).get(
            "field.cattle.io/projectId", f"{cluster_id}:"
        )
        return KubernetesClient._namespace_from_k8s_item(item, project_id)

    def update_namespace(self, namespace_id: str, quota_data: Dict) -> Namespace:
        """Update namespace quota via Kubernetes API (field.cattle.io/resourceQuota annotation)."""
        parts = namespace_id.split(":", 1) if ":" in namespace_id else ("", namespace_id)
        cluster_id, ns_name = parts[0], parts[1] if len(parts) > 1 else parts[0]
        if not cluster_id or not ns_name:
            raise RancherAPIError(f"Invalid namespace ID format: {namespace_id}")
        kubeconfig = self.generate_kubeconfig(cluster_id)
        k8s_client = KubernetesClient.from_kubeconfig(kubeconfig, self.logger)
        resource_quota = quota_data.get("resourceQuota", {})
        patch = {
            "metadata": {
                "annotations": {
                    "field.cattle.io/resourceQuota": json.dumps(resource_quota)
                }
            }
        }
        updated = k8s_client.patch_namespace(ns_name, patch)
        project_id = updated.get("metadata", {}).get("annotations", {}).get(
            "field.cattle.io/projectId", f"{cluster_id}:"
        )
        return KubernetesClient._namespace_from_k8s_item(updated, project_id)

    def generate_kubeconfig(self, cluster_id: str) -> str:
        """Generate kubeconfig for cluster. Returns kubeconfig YAML string."""
        response = self._request(
            "POST", f"/v3/clusters/{cluster_id}?action=generateKubeconfig", data={}
        )
        config = response.get("config")
        if not config:
            raise RancherAPIError("Kubeconfig not returned from generateKubeconfig")
        return config

    def find_project_by_name(self, cluster_id: str, project_name: str) -> Optional[Project]:
        """Find project by name in a cluster."""
        projects = self.list_projects(cluster_id)
        for project in projects:
            if project.name == project_name:
                return project
        return None

