"""Execution plan generation."""

from typing import List, Optional, Set

from quotactl.config import ClusterConfig, ProjectQuotaConfig, RancherInstanceConfig
from quotactl.logging import ContextLogger
from quotactl.models import Namespace, PlanItem, Project, QuotaDiff, QuotaSpec
from quotactl.rancher_client import RancherAPIError, RancherClient


class Planner:
    """Generates execution plan from current and desired state."""

    def __init__(
        self,
        client: RancherClient,
        config: RancherInstanceConfig,
        logger: ContextLogger,
    ):
        """Initialize planner."""
        self.client = client
        self.config = config
        self.logger = logger

    def create_plan(
        self,
        cluster_ids: Optional[List[str]] = None,
        project_names: Optional[List[str]] = None,
        all_projects: bool = False,
    ) -> List[PlanItem]:
        """Create execution plan."""
        plan_items: List[PlanItem] = []

        # Determine which clusters to process
        clusters_to_process = self._get_clusters_to_process(cluster_ids)

        for cluster_name, cluster_config in clusters_to_process.items():
            self.logger.set_context(cluster=cluster_config.cluster_id)
            self.logger.info(f"Processing cluster: {cluster_name} ({cluster_config.cluster_id})")

            try:
                # Validate cluster exists
                self.client.get_cluster(cluster_config.cluster_id)
            except RancherAPIError as e:
                self.logger.error(f"Failed to access cluster: {e}")
                raise

            # Determine which projects to process
            projects_to_process = self._get_projects_to_process(
                cluster_config, project_names, all_projects
            )

            for project_name, project_config in projects_to_process.items():
                self.logger.set_context(project=project_name)
                self.logger.info(f"Processing project: {project_name}")

                try:
                    # Find project in Rancher
                    project = self.client.find_project_by_name(
                        cluster_config.cluster_id, project_name
                    )

                    if not project:
                        self.logger.warning(f"Project '{project_name}' not found in cluster")
                        continue

                    # Plan project quota
                    if not project_config.project_quota.is_empty():
                        plan_item = self._plan_project_quota(
                            project, project_config.project_quota, cluster_config.cluster_id
                        )
                        if plan_item:
                            plan_items.append(plan_item)

                    # Plan namespace quotas
                    if project_config.namespace_quotas:
                        namespace_plan_items = self._plan_namespace_quotas(
                            project,
                            project_config.namespace_quotas,
                            cluster_config.cluster_id,
                        )
                        plan_items.extend(namespace_plan_items)

                except RancherAPIError as e:
                    self.logger.error(f"Failed to process project '{project_name}': {e}")
                    raise

        return plan_items

    def _get_clusters_to_process(
        self, cluster_ids: Optional[List[str]]
    ) -> dict:
        """Get clusters to process based on selection criteria."""
        if cluster_ids:
            # Filter by cluster IDs
            result = {}
            for cluster_name, cluster_config in self.config.clusters.items():
                if cluster_config.cluster_id in cluster_ids:
                    result[cluster_name] = cluster_config
            return result

        # Process all clusters
        return self.config.clusters

    def _get_projects_to_process(
        self,
        cluster_config: ClusterConfig,
        project_names: Optional[List[str]],
        all_projects: bool,
    ) -> dict:
        """Get projects to process based on selection criteria."""
        if all_projects:
            return cluster_config.projects

        if project_names:
            # Filter by project names
            result = {}
            project_names_set = set(project_names)
            for project_name, project_config in cluster_config.projects.items():
                if project_name in project_names_set:
                    result[project_name] = project_config
            return result

        # Default: process all projects in cluster
        return cluster_config.projects

    def _plan_project_quota(
        self, project: Project, desired: QuotaSpec, cluster_id: str
    ) -> Optional[PlanItem]:
        """Plan project quota enforcement."""
        diff = QuotaDiff.compute(project.quota, desired)

        if not diff.has_changes():
            self.logger.debug(f"Project '{project.name}' quota already matches desired state")
            return None

        return PlanItem(
            resource_type="project",
            resource_id=project.id,
            resource_name=project.name,
            cluster_id=cluster_id,
            current=project.quota,
            desired=desired,
            diff=diff,
        )

    def _plan_namespace_quotas(
        self,
        project: Project,
        namespace_quotas: dict,
        cluster_id: str,
    ) -> List[PlanItem]:
        """Plan namespace quota enforcement."""
        plan_items: List[PlanItem] = []

        try:
            namespaces = self.client.list_namespaces(project.id)
        except RancherAPIError as e:
            self.logger.warning(f"Failed to list namespaces for project '{project.name}': {e}")
            return plan_items

        # Create lookup by name
        namespace_by_name = {ns.name: ns for ns in namespaces}

        for ns_name, desired_quota in namespace_quotas.items():
            self.logger.set_context(namespace=ns_name)

            if desired_quota.is_empty():
                self.logger.debug(f"Skipping empty quota for namespace '{ns_name}'")
                continue

            namespace = namespace_by_name.get(ns_name)
            if not namespace:
                self.logger.warning(
                    f"Namespace '{ns_name}' not found in project '{project.name}'"
                )
                continue

            diff = QuotaDiff.compute(namespace.quota, desired_quota)

            if not diff.has_changes():
                self.logger.debug(
                    f"Namespace '{ns_name}' quota already matches desired state"
                )
                continue

            plan_items.append(
                PlanItem(
                    resource_type="namespace",
                    resource_id=namespace.id,
                    resource_name=ns_name,
                    cluster_id=cluster_id,
                    project_id=project.id,
                    current=namespace.quota,
                    desired=desired_quota,
                    diff=diff,
                )
            )

        return plan_items

