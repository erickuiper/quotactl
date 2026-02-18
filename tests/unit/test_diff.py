"""Unit tests for diff formatting."""

from quotactl.diff import format_diff, format_plan_summary, format_quota_value
from quotactl.models import PlanItem, QuotaDiff, QuotaSpec


class TestDiffFormatting:
    """Tests for diff formatting."""

    def test_format_quota_value(self):
        """Test quota value formatting."""
        assert format_quota_value("2000m") == "2000m"
        assert format_quota_value("") == "(unset)"
        assert format_quota_value(None) == "(unset)"

    def test_format_diff_no_changes(self):
        """Test formatting diff with no changes."""
        plan_item = PlanItem(
            resource_type="project",
            resource_id="p-123",
            resource_name="test-project",
            cluster_id="c-456",
            current=QuotaSpec(cpu_limit="2000m"),
            desired=QuotaSpec(cpu_limit="2000m"),
            diff=QuotaDiff(),
        )

        result = format_diff(plan_item)
        assert "No changes needed" in result

    def test_format_diff_with_changes(self):
        """Test formatting diff with changes."""
        diff = QuotaDiff()
        diff.cpu_limit_changed = True
        diff.cpu_limit_old = "2000m"
        diff.cpu_limit_new = "3000m"
        diff.memory_limit_changed = True
        diff.memory_limit_old = "4Gi"
        diff.memory_limit_new = "8Gi"

        plan_item = PlanItem(
            resource_type="project",
            resource_id="p-123",
            resource_name="test-project",
            cluster_id="c-456",
            current=QuotaSpec(cpu_limit="2000m", memory_limit="4Gi"),
            desired=QuotaSpec(cpu_limit="3000m", memory_limit="8Gi"),
            diff=diff,
        )

        result = format_diff(plan_item)
        assert "test-project" in result
        assert "2000m → 3000m" in result
        assert "4Gi → 8Gi" in result

    def test_format_plan_summary_empty(self):
        """Test formatting empty plan summary."""
        result = format_plan_summary([])
        assert "No resources to process" in result

    def test_format_plan_summary_with_items(self):
        """Test formatting plan summary with items."""
        diff = QuotaDiff()
        diff.cpu_limit_changed = True
        diff.cpu_limit_old = "2000m"
        diff.cpu_limit_new = "3000m"

        plan_item = PlanItem(
            resource_type="project",
            resource_id="p-123",
            resource_name="test-project",
            cluster_id="c-456",
            current=QuotaSpec(cpu_limit="2000m"),
            desired=QuotaSpec(cpu_limit="3000m"),
            diff=diff,
        )

        result = format_plan_summary([plan_item])
        assert "1 change(s)" in result
        assert "test-project" in result

