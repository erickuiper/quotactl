"""Unit tests for report module."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from quotactl.logging import setup_logging
from quotactl.models import Namespace, Project, QuotaSpec
from quotactl.report import (
    ClusterQuotaData,
    ProjectQuotaData,
    collect_quota_data,
    generate_quota_report,
)


class TestCollectQuotaData:
    """Tests for collect_quota_data."""

    @pytest.fixture
    def logger(self):
        """Create logger for tests."""
        return setup_logging("DEBUG")

    @pytest.fixture
    def mock_client(self, logger):
        """Create mock Rancher client."""
        client = MagicMock()
        client.logger = logger
        return client

    def test_collect_quota_data_all_clusters(self, mock_client, logger):
        """Test collecting quota data for all clusters (uses get_project for full quota)."""
        mock_client._request.return_value = {
            "data": [
                {"id": "local", "name": "local"},
            ]
        }
        # List may return minimal data; get_project returns full project with quota
        mock_client.list_projects.return_value = [
            Project(
                id="local:p-123",
                name="test-project",
                cluster_id="local",
                quota=QuotaSpec(),  # list might omit quota
            )
        ]
        mock_client.get_project.return_value = Project(
            id="local:p-123",
            name="test-project",
            cluster_id="local",
            quota=QuotaSpec(cpu_limit="2000m", memory_limit="4Gi"),
        )
        mock_client.list_namespaces.return_value = [
            Namespace(
                id="local:ns1",
                name="ns1",
                project_id="local:p-123",
                quota=QuotaSpec(cpu_limit="1000m"),
            )
        ]

        clusters = collect_quota_data(mock_client, logger, cluster_ids=None)

        assert len(clusters) == 1
        assert clusters[0].cluster_id == "local"
        assert len(clusters[0].projects) == 1
        assert clusters[0].projects[0].project.name == "test-project"
        assert clusters[0].projects[0].project.quota.cpu_limit == "2000m"
        assert clusters[0].projects[0].project.quota.memory_limit == "4Gi"
        assert len(clusters[0].projects[0].namespaces) == 1
        assert clusters[0].projects[0].namespaces[0].name == "ns1"
        mock_client.get_project.assert_called_once_with("local:p-123")


class TestGenerateQuotaReport:
    """Tests for generate_quota_report."""

    @pytest.fixture
    def logger(self):
        """Create logger for tests."""
        return setup_logging("DEBUG")

    @pytest.fixture
    def mock_client(self, logger):
        """Create mock Rancher client."""
        client = MagicMock()
        client.base_url = "https://rancher.example.com"
        client.logger = logger
        return client

    def test_generate_quota_report(self, mock_client, logger, tmp_path):
        """Test generating HTML report (report fetches full project via get_project)."""
        mock_client._request.return_value = {
            "data": [{"id": "local", "name": "local"}]
        }
        mock_client.list_projects.return_value = [
            Project(
                id="local:p-123",
                name="test-project",
                cluster_id="local",
                quota=QuotaSpec(),  # list may omit quota
            )
        ]
        mock_client.get_project.return_value = Project(
            id="local:p-123",
            name="test-project",
            cluster_id="local",
            quota=QuotaSpec(cpu_limit="2000m", memory_limit="4Gi"),
        )
        mock_client.list_namespaces.return_value = []

        output_path = tmp_path / "report.html"
        generate_quota_report(
            client=mock_client,
            output_path=output_path,
            logger=logger,
            cluster_ids=None,
        )

        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Rancher Quota Overview" in content
        assert "test-project" in content
        assert "2000m" in content
        assert "4Gi" in content
