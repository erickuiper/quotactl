"""Configuration loading and validation."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import yaml

from quotactl.models import QuotaSpec

# Environment variables for config and credentials
ENV_QUOTACTL_CONFIG = "QUOTACTL_CONFIG"
ENV_RANCHER_URL = "RANCHER_URL"
ENV_RANCHER_TOKEN = "RANCHER_TOKEN"


def default_config_path() -> Path:
    """Return default config file path: QUOTACTL_CONFIG or ~/.quotactl/config."""
    if os.environ.get(ENV_QUOTACTL_CONFIG):
        return Path(os.environ[ENV_QUOTACTL_CONFIG])
    return Path.home() / ".quotactl" / "config"


@dataclass
class ProjectQuotaConfig:
    """Project quota configuration."""

    project_quota: QuotaSpec
    namespace_quotas: Dict[str, QuotaSpec] = field(default_factory=dict)


@dataclass
class ClusterConfig:
    """Cluster configuration."""

    cluster_id: str
    projects: Dict[str, ProjectQuotaConfig] = field(default_factory=dict)


@dataclass
class RancherInstanceConfig:
    """Rancher instance configuration."""

    url: str
    token: str
    clusters: Dict[str, ClusterConfig] = field(default_factory=dict)
    verify_ssl: bool = True

    @classmethod
    def from_file(cls, config_path: Path, token_env_var: Optional[str] = None) -> "RancherInstanceConfig":
        """Load configuration from YAML file."""
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("Config file must contain a YAML dictionary")

        # URL: config file > RANCHER_URL env
        url = data.get("url") or os.getenv(ENV_RANCHER_URL)
        if not url:
            raise ValueError(
                "Config must contain 'url' or set RANCHER_URL environment variable"
            )

        # Token: CLI override > token_ref env var > literal token in config > RANCHER_TOKEN env
        token = None
        if token_env_var:
            token = os.getenv(token_env_var)
        elif "token_ref" in data:
            token = os.getenv(data["token_ref"])
        elif "token" in data:
            token = data["token"]
        if not token:
            token = os.getenv(ENV_RANCHER_TOKEN)

        if not token:
            raise ValueError(
                "Token must be provided via 'token' in config, 'token_ref' in config, "
                "--token-env-var, or RANCHER_TOKEN environment variable"
            )

        # SSL verification: config insecure_skip_tls_verify (env is handled by RancherClient when verify=None)
        verify_ssl = not data.get("insecure_skip_tls_verify", False)

        # Parse clusters
        clusters: Dict[str, ClusterConfig] = {}
        clusters_data = data.get("clusters", {})

        for cluster_name, cluster_data in clusters_data.items():
            if not isinstance(cluster_data, dict):
                raise ValueError(f"Cluster '{cluster_name}' must be a dictionary")

            cluster_id = cluster_data.get("cluster_id")
            if not cluster_id:
                raise ValueError(f"Cluster '{cluster_name}' must have 'cluster_id'")

            # Parse projects
            projects: Dict[str, ProjectQuotaConfig] = {}
            projects_data = cluster_data.get("projects", {})

            for project_name, project_data in projects_data.items():
                if not isinstance(project_data, dict):
                    raise ValueError(
                        f"Project '{project_name}' in cluster '{cluster_name}' must be a dictionary"
                    )

                # Parse project quota
                project_quota_data = project_data.get("project_quota", {})
                project_quota = QuotaSpec(
                    cpu_limit=project_quota_data.get("cpu_limit"),
                    memory_limit=project_quota_data.get("memory_limit"),
                    cpu_reservation=project_quota_data.get("cpu_reservation"),
                    memory_reservation=project_quota_data.get("memory_reservation"),
                )

                # Parse namespace quotas
                namespace_quotas: Dict[str, QuotaSpec] = {}
                namespace_quotas_data = project_data.get("namespace_quotas", {})

                for ns_name, ns_quota_data in namespace_quotas_data.items():
                    if not isinstance(ns_quota_data, dict):
                        raise ValueError(
                            f"Namespace quota '{ns_name}' in project '{project_name}' "
                            f"must be a dictionary"
                        )

                    namespace_quotas[ns_name] = QuotaSpec(
                        cpu_limit=ns_quota_data.get("cpu_limit"),
                        memory_limit=ns_quota_data.get("memory_limit"),
                        cpu_reservation=ns_quota_data.get("cpu_reservation"),
                        memory_reservation=ns_quota_data.get("memory_reservation"),
                    )

                projects[project_name] = ProjectQuotaConfig(
                    project_quota=project_quota,
                    namespace_quotas=namespace_quotas,
                )

            clusters[cluster_name] = ClusterConfig(
                cluster_id=cluster_id,
                projects=projects,
            )

        return cls(url=url, token=token, clusters=clusters, verify_ssl=verify_ssl)


def write_default_config(
    path: Path,
    url: str,
    token_ref: str = "RANCHER_TOKEN",
    token_literal: Optional[str] = None,
) -> None:
    """Write a minimal config file. Creates parent directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data: Dict = {
        "url": url,
        "token_ref": token_ref,
    }
    if token_literal is not None:
        data["token"] = token_literal
        data.pop("token_ref", None)
    data["clusters"] = {}
    with open(path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

