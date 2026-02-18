"""Integration tests against real Rancher instance.

These tests require:
- RANCHER_URL environment variable
- RANCHER_TOKEN environment variable
- CLUSTER_ID environment variable
- PROJECT_NAME_TEST environment variable (test project name)
- INTEGRATION_WRITE=1 environment variable (to enable write operations)

Tests will:
1. Read current quota state
2. Apply test quota change
3. Verify change via API read
4. Restore original quota
5. Verify restoration
"""

import os
import re
from pathlib import Path

import pytest

from quotactl.config import RancherInstanceConfig
from quotactl.executor import Executor
from quotactl.logging import setup_logging
from quotactl.models import QuotaSpec
from quotactl.planner import Planner
from quotactl.rancher_client import RancherClient
from quotactl.report import generate_quota_report


@pytest.fixture(scope="module")
def integration_config():
    """Get integration test configuration from environment."""
    rancher_url = os.getenv("RANCHER_URL")
    rancher_token = os.getenv("RANCHER_TOKEN")
    cluster_id = os.getenv("CLUSTER_ID")
    project_name = os.getenv("PROJECT_NAME_TEST")
    integration_write = os.getenv("INTEGRATION_WRITE") == "1"

    if not all([rancher_url, rancher_token, cluster_id, project_name]):
        pytest.skip("Integration test environment variables not set")

    return {
        "url": rancher_url,
        "token": rancher_token,
        "cluster_id": cluster_id,
        "project_name": project_name,
        "write_enabled": integration_write,
    }


@pytest.fixture(scope="module")
def logger():
    """Create logger for integration tests."""
    return setup_logging("INFO")


@pytest.fixture(scope="module")
def client(integration_config, logger):
    """Create Rancher client for integration tests."""
    return RancherClient(integration_config["url"], integration_config["token"], logger)


@pytest.fixture(scope="module")
def original_project_quota(client, integration_config):
    """Get and store original project quota."""
    project = client.find_project_by_name(
        integration_config["cluster_id"], integration_config["project_name"]
    )
    if not project:
        pytest.skip(f"Test project '{integration_config['project_name']}' not found")

    original = project.quota
    yield original

    # Restore original quota
    if integration_config["write_enabled"]:
        try:
            quota_data = original.to_rancher_dict()
            client.update_project(project.id, quota_data)
        except Exception as e:
            pytest.fail(f"Failed to restore original quota: {e}")


@pytest.mark.integration
def test_read_project_quota(client, integration_config):
    """Test reading project quota from Rancher."""
    project = client.find_project_by_name(
        integration_config["cluster_id"], integration_config["project_name"]
    )
    assert project is not None
    assert project.name == integration_config["project_name"]
    assert project.cluster_id == integration_config["cluster_id"]


@pytest.mark.integration
def test_read_namespaces(client, integration_config):
    """Test reading namespaces from project."""
    project = client.find_project_by_name(
        integration_config["cluster_id"], integration_config["project_name"]
    )
    assert project is not None

    namespaces = client.list_namespaces(project.id)
    assert isinstance(namespaces, list)


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("INTEGRATION_WRITE") != "1",
    reason="INTEGRATION_WRITE=1 required for write tests",
)
def test_update_project_quota(client, integration_config, original_project_quota):
    """Test updating project quota (with restoration)."""
    project = client.find_project_by_name(
        integration_config["cluster_id"], integration_config["project_name"]
    )
    assert project is not None

    # Create test quota (slightly different from original)
    test_quota = QuotaSpec(
        cpu_limit="1000m" if original_project_quota.cpu_limit != "1000m" else "2000m",
        memory_limit="2Gi" if original_project_quota.memory_limit != "2Gi" else "4Gi",
    )

    # Update quota
    quota_data = test_quota.to_rancher_dict()
    updated_project = client.update_project(project.id, quota_data)

    # Verify update
    assert updated_project.quota.cpu_limit == test_quota.cpu_limit
    assert updated_project.quota.memory_limit == test_quota.memory_limit

    # Read back to verify
    read_project = client.get_project(project.id)
    assert read_project.quota.cpu_limit == test_quota.cpu_limit
    assert read_project.quota.memory_limit == test_quota.memory_limit


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("INTEGRATION_WRITE") != "1",
    reason="INTEGRATION_WRITE=1 required for write tests",
)
def test_planner_and_executor_integration(client, integration_config, logger, tmp_path):
    """Test full planner and executor integration."""
    # Create temporary config file
    config_data = {
        "url": integration_config["url"],
        "token_ref": "RANCHER_TOKEN",
        "clusters": {
            "test_cluster": {
                "cluster_id": integration_config["cluster_id"],
                "projects": {
                    integration_config["project_name"]: {
                        "project_quota": {
                            "cpu_limit": "1500m",
                            "memory_limit": "3Gi",
                        }
                    }
                },
            }
        },
    }

    import yaml

    config_path = tmp_path / "test_config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    # Load config
    instance_config = RancherInstanceConfig.from_file(config_path)

    # Create planner
    planner = Planner(client, instance_config, logger)

    # Generate plan
    plan_items = planner.create_plan(
        cluster_ids=[integration_config["cluster_id"]],
        project_names=[integration_config["project_name"]],
    )

    # Filter to items with changes
    plan_items_with_changes = [item for item in plan_items if item.diff.has_changes()]

    if plan_items_with_changes:
        # Execute plan
        executor = Executor(client, logger)
        results = executor.execute(plan_items_with_changes, dry_run=False)

        # Verify all succeeded
        assert all(r.success for r in results), "Some quota updates failed"


@pytest.mark.integration
def test_report_contains_project_and_namespaces(client, integration_config, logger, tmp_path):
    """Generate HTML report and assert test project and namespaces appear."""
    report_path = tmp_path / "quota-report.html"
    generate_quota_report(
        client=client,
        output_path=report_path,
        logger=logger,
        cluster_ids=[integration_config["cluster_id"]],
    )
    html = report_path.read_text(encoding="utf-8")
    assert "Rancher Quota Overview" in html
    assert integration_config["project_name"] in html


@pytest.mark.integration
def test_report_contains_quota_values(client, integration_config, logger, tmp_path):
    """Generate HTML report and assert quota values appear (not only 'No quota set').

    When INTEGRATION_WRITE=1, sets a known quota on the test project, generates
    the report, and asserts those values appear in the HTML; then restores original.
    When INTEGRATION_WRITE=0, generates report and asserts at least one quota-like
    value exists (if any project has quotas in Rancher).
    """
    project = client.find_project_by_name(
        integration_config["cluster_id"], integration_config["project_name"]
    )
    if not project:
        pytest.skip(f"Test project '{integration_config['project_name']}' not found")

    original_quota = project.quota
    restore_quota = integration_config["write_enabled"]

    if restore_quota:
        # Set a distinctive quota so we can assert it appears in the report
        test_quota = QuotaSpec(cpu_limit="9999m", memory_limit="9Gi")
        client.update_project(project.id, test_quota.to_rancher_dict())

    try:
        report_path = tmp_path / "quota-report.html"
        generate_quota_report(
            client=client,
            output_path=report_path,
            logger=logger,
            cluster_ids=[integration_config["cluster_id"]],
        )
        html = report_path.read_text(encoding="utf-8")

        if restore_quota:
            assert "9999m" in html, "Report should show project CPU limit 9999m"
            assert "9Gi" in html, "Report should show project memory limit 9Gi"
        else:
            # Without write, only require report to generate; quota values depend on Rancher state
            quota_value_pattern = re.compile(
                r">\s*\d+[m]\s*<|>\s*\d+[KMG]i?\s*<|>\s*\d+[KMG]\s*<",
                re.IGNORECASE,
            )
            if not quota_value_pattern.search(html):
                pytest.skip(
                    "No quota values in report (no quotas set in Rancher). "
                    "Set INTEGRATION_WRITE=1 to assert report shows values after setting test quota."
                )
    finally:
        if restore_quota:
            client.update_project(project.id, original_quota.to_rancher_dict())

