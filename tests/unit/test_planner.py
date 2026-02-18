"""Unit tests for planner."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from quotactl.config import ClusterConfig, ProjectQuotaConfig, RancherInstanceConfig
from quotactl.logging import setup_logging
from quotactl.models import Namespace, Project, QuotaSpec
from quotactl.planner import Planner
from quotactl.rancher_client import RancherClient, RancherAPIError


class TestPlanner:
    """Tests for Planner."""

    @pytest.fixture
    def logger(self):
        """Create logger for tests."""
        return setup_logging("DEBUG")

    @pytest.fixture
    def mock_client(self, logger):
        """Create mock Rancher client."""
        client = MagicMock(spec=RancherClient)
        client.logger = logger
        return client

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return RancherInstanceConfig(
            url="https://rancher.example.com",
            token="test-token",
            clusters={
                "cluster1": ClusterConfig(
                    cluster_id="c-123",
                    projects={
                        "project1": ProjectQuotaConfig(
                            project_quota=QuotaSpec(cpu_limit="2000m", memory_limit="4Gi"),
                            namespace_quotas={
                                "ns1": QuotaSpec(cpu_limit="1000m"),
                            },
                        )
                    },
                )
            },
        )

    @pytest.fixture
    def planner(self, mock_client, config, logger):
        """Create planner for tests."""
        return Planner(mock_client, config, logger)

    def test_create_plan_project_quota_change(self, planner, mock_client):
        """Test creating plan with project quota change."""
        # Mock cluster validation
        mock_client.get_cluster.return_value = {"id": "c-123"}

        # Mock project lookup
        current_project = Project(
            id="p-123",
            name="project1",
            cluster_id="c-123",
            quota=QuotaSpec(cpu_limit="1000m"),  # Different from desired
        )
        mock_client.find_project_by_name.return_value = current_project

        plan_items = planner.create_plan(cluster_ids=["c-123"], project_names=["project1"])

        assert len(plan_items) == 1
        assert plan_items[0].resource_type == "project"
        assert plan_items[0].resource_name == "project1"
        assert plan_items[0].diff.has_changes()

    def test_create_plan_no_changes(self, planner, mock_client):
        """Test creating plan with no changes needed."""
        # Mock cluster validation
        mock_client.get_cluster.return_value = {"id": "c-123"}

        # Mock project with matching quota
        current_project = Project(
            id="p-123",
            name="project1",
            cluster_id="c-123",
            quota=QuotaSpec(cpu_limit="2000m", memory_limit="4Gi"),  # Matches desired
        )
        mock_client.find_project_by_name.return_value = current_project

        plan_items = planner.create_plan(cluster_ids=["c-123"], project_names=["project1"])

        # Should have no items with changes
        items_with_changes = [item for item in plan_items if item.diff.has_changes()]
        assert len(items_with_changes) == 0

    def test_create_plan_namespace_quota_change(self, planner, mock_client):
        """Test creating plan with namespace quota change."""
        # Mock cluster validation
        mock_client.get_cluster.return_value = {"id": "c-123"}

        # Mock project
        project = Project(
            id="p-123",
            name="project1",
            cluster_id="c-123",
            quota=QuotaSpec(cpu_limit="2000m"),
        )
        mock_client.find_project_by_name.return_value = project

        # Mock namespace list
        current_namespace = Namespace(
            id="ns-123",
            name="ns1",
            project_id="p-123",
            quota=QuotaSpec(cpu_limit="500m"),  # Different from desired
        )
        mock_client.list_namespaces.return_value = [current_namespace]

        plan_items = planner.create_plan(cluster_ids=["c-123"], project_names=["project1"])

        # Should have namespace quota change
        namespace_items = [
            item for item in plan_items if item.resource_type == "namespace"
        ]
        assert len(namespace_items) == 1
        assert namespace_items[0].resource_name == "ns1"
        assert namespace_items[0].diff.has_changes()

    def test_create_plan_project_not_found(self, planner, mock_client):
        """Test creating plan when project not found."""
        # Mock cluster validation
        mock_client.get_cluster.return_value = {"id": "c-123"}

        # Mock project not found
        mock_client.find_project_by_name.return_value = None

        plan_items = planner.create_plan(cluster_ids=["c-123"], project_names=["project1"])

        # Should have no items (project not found is logged but doesn't create plan item)
        assert len(plan_items) == 0

    def test_create_plan_all_projects(self, planner, mock_client):
        """Test creating plan for all projects."""
        # Mock cluster validation
        mock_client.get_cluster.return_value = {"id": "c-123"}

        # Mock project
        project = Project(
            id="p-123",
            name="project1",
            cluster_id="c-123",
            quota=QuotaSpec(cpu_limit="1000m"),  # Different from desired
        )
        mock_client.find_project_by_name.return_value = project

        plan_items = planner.create_plan(cluster_ids=["c-123"], all_projects=True)

        assert len(plan_items) > 0

    def test_create_plan_cluster_error(self, planner, mock_client):
        """Test creating plan when cluster access fails."""
        mock_client.get_cluster.side_effect = RancherAPIError("Cluster not found")

        with pytest.raises(RancherAPIError):
            planner.create_plan(cluster_ids=["c-123"])

