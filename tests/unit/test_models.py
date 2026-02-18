"""Unit tests for models."""

import pytest

from quotactl.models import Namespace, Project, QuotaDiff, QuotaSpec


class TestQuotaSpec:
    """Tests for QuotaSpec."""

    def test_empty_quota_spec(self):
        """Test empty quota spec."""
        quota = QuotaSpec()
        assert quota.is_empty()
        assert quota.to_rancher_dict() == {}

    def test_quota_spec_with_values(self):
        """Test quota spec with values."""
        quota = QuotaSpec(
            cpu_limit="2000m",
            memory_limit="4Gi",
            cpu_reservation="1000m",
            memory_reservation="2Gi",
        )
        assert not quota.is_empty()

        rancher_dict = quota.to_rancher_dict()
        assert rancher_dict["resourceQuota"]["limit"]["cpu"] == "2000m"
        assert rancher_dict["resourceQuota"]["limit"]["memory"] == "4Gi"
        assert rancher_dict["resourceQuota"]["reservation"]["cpu"] == "1000m"
        assert rancher_dict["resourceQuota"]["reservation"]["memory"] == "2Gi"

    def test_quota_spec_from_rancher_dict(self):
        """Test creating QuotaSpec from Rancher API dict (limit.cpu format)."""
        rancher_data = {
            "resourceQuota": {
                "limit": {"cpu": "2000m", "memory": "4Gi"},
                "reservation": {"cpu": "1000m", "memory": "2Gi"},
            }
        }

        quota = QuotaSpec.from_rancher_dict(rancher_data)
        assert quota.cpu_limit == "2000m"
        assert quota.memory_limit == "4Gi"
        assert quota.cpu_reservation == "1000m"
        assert quota.memory_reservation == "2Gi"

    def test_quota_spec_from_rancher_dict_camel_case(self):
        """Test creating QuotaSpec from Rancher API dict (limitsCpu / requestsCpu format)."""
        rancher_data = {
            "resourceQuota": {
                "limit": {
                    "limitsCpu": "3000m",
                    "limitsMemory": "6Gi",
                    "requestsCpu": "1500m",
                    "requestsMemory": "3Gi",
                }
            }
        }

        quota = QuotaSpec.from_rancher_dict(rancher_data)
        assert quota.cpu_limit == "3000m"
        assert quota.memory_limit == "6Gi"
        assert quota.cpu_reservation == "1500m"
        assert quota.memory_reservation == "3Gi"

    def test_quota_spec_from_rancher_dict_spec_resource_quota(self):
        """Test QuotaSpec from management API style (spec.resourceQuota like testing123)."""
        rancher_data = {
            "id": "local:p-65xfh",
            "name": "p-65xfh",
            "spec": {
                "displayName": "testing123",
                "clusterName": "local",
                "resourceQuota": {
                    "limit": {
                        "limitsCpu": "1000m",
                        "limitsMemory": "8000Mi",
                        "requestsMemory": "4000Mi",
                    }
                },
            },
        }
        quota = QuotaSpec.from_rancher_dict(rancher_data)
        assert quota.cpu_limit == "1000m"
        assert quota.memory_limit == "8000Mi"
        assert quota.memory_reservation == "4000Mi"
        assert quota.cpu_reservation is None

    def test_quota_spec_equality(self):
        """Test quota spec equality."""
        quota1 = QuotaSpec(cpu_limit="2000m", memory_limit="4Gi")
        quota2 = QuotaSpec(cpu_limit="2000m", memory_limit="4Gi")
        quota3 = QuotaSpec(cpu_limit="1000m", memory_limit="4Gi")

        assert quota1 == quota2
        assert quota1 != quota3


class TestQuotaDiff:
    """Tests for QuotaDiff."""

    def test_no_changes(self):
        """Test diff with no changes."""
        current = QuotaSpec(cpu_limit="2000m", memory_limit="4Gi")
        desired = QuotaSpec(cpu_limit="2000m", memory_limit="4Gi")

        diff = QuotaDiff.compute(current, desired)
        assert not diff.has_changes()

    def test_cpu_limit_change(self):
        """Test diff with CPU limit change."""
        current = QuotaSpec(cpu_limit="2000m")
        desired = QuotaSpec(cpu_limit="3000m")

        diff = QuotaDiff.compute(current, desired)
        assert diff.has_changes()
        assert diff.cpu_limit_changed
        assert diff.cpu_limit_old == "2000m"
        assert diff.cpu_limit_new == "3000m"

    def test_all_fields_changed(self):
        """Test diff with all fields changed."""
        current = QuotaSpec(
            cpu_limit="2000m",
            memory_limit="4Gi",
            cpu_reservation="1000m",
            memory_reservation="2Gi",
        )
        desired = QuotaSpec(
            cpu_limit="3000m",
            memory_limit="8Gi",
            cpu_reservation="1500m",
            memory_reservation="4Gi",
        )

        diff = QuotaDiff.compute(current, desired)
        assert diff.has_changes()
        assert diff.cpu_limit_changed
        assert diff.memory_limit_changed
        assert diff.cpu_reservation_changed
        assert diff.memory_reservation_changed


class TestProject:
    """Tests for Project."""

    def test_project_from_rancher_dict(self):
        """Test creating Project from Rancher API dict."""
        rancher_data = {
            "id": "project-123",
            "name": "test-project",
            "clusterId": "cluster-456",
            "resourceQuota": {
                "limit": {"cpu": "2000m", "memory": "4Gi"},
            },
        }

        project = Project.from_rancher_dict(rancher_data)
        assert project.id == "project-123"
        assert project.name == "test-project"
        assert project.cluster_id == "cluster-456"
        assert project.quota.cpu_limit == "2000m"
        assert project.quota.memory_limit == "4Gi"

    def test_project_from_rancher_dict_spec_style(self):
        """Test Project from management API (spec.displayName, spec.resourceQuota)."""
        rancher_data = {
            "id": "local:p-65xfh",
            "name": "p-65xfh",
            "metadata": {"namespace": "local"},
            "spec": {
                "displayName": "testing123",
                "clusterName": "local",
                "resourceQuota": {
                    "limit": {
                        "limitsCpu": "1000m",
                        "limitsMemory": "8000Mi",
                        "requestsMemory": "4000Mi",
                    }
                },
            },
        }
        project = Project.from_rancher_dict(rancher_data)
        assert project.id == "local:p-65xfh"
        assert project.name == "testing123"
        assert project.cluster_id == "local"
        assert project.quota.cpu_limit == "1000m"
        assert project.quota.memory_limit == "8000Mi"
        assert project.quota.memory_reservation == "4000Mi"


class TestNamespace:
    """Tests for Namespace."""

    def test_namespace_from_rancher_dict(self):
        """Test creating Namespace from Rancher API dict."""
        rancher_data = {
            "id": "namespace-123",
            "name": "test-namespace",
            "projectId": "project-456",
            "resourceQuota": {
                "limit": {"cpu": "1000m", "memory": "2Gi"},
            },
        }

        namespace = Namespace.from_rancher_dict(rancher_data)
        assert namespace.id == "namespace-123"
        assert namespace.name == "test-namespace"
        assert namespace.project_id == "project-456"
        assert namespace.quota.cpu_limit == "1000m"
        assert namespace.quota.memory_limit == "2Gi"

