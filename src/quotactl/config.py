"""Configuration loading and validation."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import yaml

from quotactl.models import QuotaSpec


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

    @classmethod
    def from_file(cls, config_path: Path, token_env_var: Optional[str] = None) -> "RancherInstanceConfig":
        """Load configuration from YAML file."""
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("Config file must contain a YAML dictionary")

        url = data.get("url")
        if not url:
            raise ValueError("Config must contain 'url' field")

        # Resolve token (priority: CLI override > token_ref env var > literal token)
        token = None
        if token_env_var:
            token = os.getenv(token_env_var)
        elif "token_ref" in data:
            token = os.getenv(data["token_ref"])
        elif "token" in data:
            token = data["token"]

        if not token:
            raise ValueError(
                "Token must be provided via 'token' in config, 'token_ref' in config, "
                "or environment variable"
            )

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

        return cls(url=url, token=token, clusters=clusters)

