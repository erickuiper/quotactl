"""Unit tests for executor."""

from unittest.mock import MagicMock, Mock

import pytest

from quotactl.executor import Executor
from quotactl.logging import setup_logging
from quotactl.models import PlanItem, QuotaSpec
from quotactl.rancher_client import RancherAPIError, RancherClient


class TestExecutor:
    """Tests for Executor."""

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
    def executor(self, mock_client, logger):
        """Create executor for tests."""
        return Executor(mock_client, logger)

    def test_execute_dry_run(self, executor, mock_client):
        """Test dry-run execution."""
        plan_item = PlanItem(
            resource_type="project",
            resource_id="p-123",
            resource_name="test-project",
            cluster_id="c-456",
            current=QuotaSpec(cpu_limit="2000m"),
            desired=QuotaSpec(cpu_limit="3000m"),
        )
        plan_item.diff.cpu_limit_changed = True

        results = executor.execute([plan_item], dry_run=True)

        assert len(results) == 1
        assert results[0].success
        # Should not call update methods in dry-run
        mock_client.update_project.assert_not_called()
        mock_client.update_namespace.assert_not_called()

    def test_execute_project_update(self, executor, mock_client):
        """Test executing project update."""
        updated_project = Mock()
        updated_project.quota = QuotaSpec(cpu_limit="3000m")
        mock_client.update_project.return_value = updated_project

        plan_item = PlanItem(
            resource_type="project",
            resource_id="p-123",
            resource_name="test-project",
            cluster_id="c-456",
            current=QuotaSpec(cpu_limit="2000m"),
            desired=QuotaSpec(cpu_limit="3000m"),
        )
        plan_item.diff.cpu_limit_changed = True

        results = executor.execute([plan_item], dry_run=False)

        assert len(results) == 1
        assert results[0].success
        mock_client.update_project.assert_called_once()

    def test_execute_namespace_update(self, executor, mock_client):
        """Test executing namespace update."""
        updated_namespace = Mock()
        updated_namespace.quota = QuotaSpec(cpu_limit="1000m")
        mock_client.update_namespace.return_value = updated_namespace

        plan_item = PlanItem(
            resource_type="namespace",
            resource_id="ns-123",
            resource_name="test-namespace",
            cluster_id="c-456",
            project_id="p-789",
            current=QuotaSpec(cpu_limit="500m"),
            desired=QuotaSpec(cpu_limit="1000m"),
        )
        plan_item.diff.cpu_limit_changed = True

        results = executor.execute([plan_item], dry_run=False)

        assert len(results) == 1
        assert results[0].success
        mock_client.update_namespace.assert_called_once()

    def test_execute_with_error(self, executor, mock_client):
        """Test execution with API error."""
        mock_client.update_project.side_effect = RancherAPIError("Update failed")

        plan_item = PlanItem(
            resource_type="project",
            resource_id="p-123",
            resource_name="test-project",
            cluster_id="c-456",
            current=QuotaSpec(cpu_limit="2000m"),
            desired=QuotaSpec(cpu_limit="3000m"),
        )
        plan_item.diff.cpu_limit_changed = True

        results = executor.execute([plan_item], dry_run=False)

        assert len(results) == 1
        assert not results[0].success
        assert "Update failed" in results[0].error

    def test_summarize_success(self, executor):
        """Test execution summary with all successes."""
        plan_item = PlanItem(
            resource_type="project",
            resource_id="p-123",
            resource_name="test-project",
            cluster_id="c-456",
        )

        results = [
            type("ExecutionResult", (), {"success": True, "plan_item": plan_item, "error": None})()
        ]

        summary = Executor.summarize(results)
        assert "Total: 1" in summary
        assert "Successful: 1" in summary
        assert "Failed: 0" in summary

    def test_summarize_with_failures(self, executor):
        """Test execution summary with failures."""
        plan_item = PlanItem(
            resource_type="project",
            resource_id="p-123",
            resource_name="test-project",
            cluster_id="c-456",
        )

        results = [
            type("ExecutionResult", (), {"success": True, "plan_item": plan_item, "error": None})(),
            type("ExecutionResult", (), {"success": False, "plan_item": plan_item, "error": "API Error"})(),
        ]

        summary = Executor.summarize(results)
        assert "Total: 2" in summary
        assert "Successful: 1" in summary
        assert "Failed: 1" in summary
        assert "Failures:" in summary
        assert "API Error" in summary

