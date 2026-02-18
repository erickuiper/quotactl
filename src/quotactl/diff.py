"""Diff generation and formatting."""

from typing import List

from quotactl.models import PlanItem, QuotaDiff


def format_quota_value(value: str) -> str:
    """Format quota value for display."""
    return value if value else "(unset)"


def format_diff(plan_item: PlanItem) -> str:
    """Format plan item as human-readable diff."""
    lines: List[str] = []
    diff = plan_item.diff

    resource_desc = f"{plan_item.resource_type} '{plan_item.resource_name}'"

    if not diff.has_changes():
        lines.append(f"  {resource_desc}: No changes needed")
        return "\n".join(lines)

    lines.append(f"  {resource_desc}:")

    if diff.cpu_limit_changed:
        lines.append(
            f"    CPU Limit: {format_quota_value(diff.cpu_limit_old)} → "
            f"{format_quota_value(diff.cpu_limit_new)}"
        )

    if diff.memory_limit_changed:
        lines.append(
            f"    Memory Limit: {format_quota_value(diff.memory_limit_old)} → "
            f"{format_quota_value(diff.memory_limit_new)}"
        )

    if diff.cpu_reservation_changed:
        lines.append(
            f"    CPU Reservation: {format_quota_value(diff.cpu_reservation_old)} → "
            f"{format_quota_value(diff.cpu_reservation_new)}"
        )

    if diff.memory_reservation_changed:
        lines.append(
            f"    Memory Reservation: {format_quota_value(diff.memory_reservation_old)} → "
            f"{format_quota_value(diff.memory_reservation_new)}"
        )

    return "\n".join(lines)


def format_plan_summary(plan_items: List[PlanItem]) -> str:
    """Format execution plan summary."""
    total = len(plan_items)
    changes = sum(1 for item in plan_items if item.diff.has_changes())

    if total == 0:
        return "No resources to process"

    lines = [f"Execution Plan: {changes} change(s) needed out of {total} resource(s)"]

    for item in plan_items:
        if item.diff.has_changes():
            lines.append(format_diff(item))

    return "\n".join(lines)

