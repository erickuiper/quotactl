"""Quota enforcement executor."""

from typing import List

from quotactl.logging import ContextLogger
from quotactl.models import ExecutionResult, PlanItem
from quotactl.rancher_client import RancherAPIError, RancherClient


class Executor:
    """Executes quota enforcement plan."""

    def __init__(self, client: RancherClient, logger: ContextLogger):
        """Initialize executor."""
        self.client = client
        self.logger = logger

    def execute(
        self, plan_items: List[PlanItem], dry_run: bool = False
    ) -> List[ExecutionResult]:
        """Execute plan items."""
        results: List[ExecutionResult] = []

        for item in plan_items:
            self.logger.set_context(
                cluster=item.cluster_id,
                project=item.resource_name if item.resource_type == "project" else None,
                namespace=item.resource_name if item.resource_type == "namespace" else None,
            )

            if dry_run:
                self.logger.info(f"[DRY RUN] Would update {item.resource_type} '{item.resource_name}'")
                results.append(
                    ExecutionResult(success=True, plan_item=item, error=None)
                )
                continue

            try:
                if item.resource_type == "project":
                    self._execute_project_update(item)
                elif item.resource_type == "namespace":
                    self._execute_namespace_update(item)
                else:
                    raise ValueError(f"Unknown resource type: {item.resource_type}")

                self.logger.info(f"Successfully updated {item.resource_type} '{item.resource_name}'")
                results.append(ExecutionResult(success=True, plan_item=item, error=None))

            except RancherAPIError as e:
                error_msg = f"Failed to update {item.resource_type} '{item.resource_name}': {e}"
                self.logger.error(error_msg)
                results.append(ExecutionResult(success=False, plan_item=item, error=str(e)))

            except Exception as e:
                error_msg = f"Unexpected error updating {item.resource_type} '{item.resource_name}': {e}"
                self.logger.error(error_msg, exc_info=True)
                results.append(ExecutionResult(success=False, plan_item=item, error=str(e)))

        return results

    def _execute_project_update(self, item: PlanItem) -> None:
        """Execute project quota update."""
        quota_data = item.desired.to_rancher_dict()
        self.client.update_project(item.resource_id, quota_data)

    def _execute_namespace_update(self, item: PlanItem) -> None:
        """Execute namespace quota update."""
        quota_data = item.desired.to_rancher_dict()
        self.client.update_namespace(item.resource_id, quota_data)

    @staticmethod
    def summarize(results: List[ExecutionResult]) -> str:
        """Generate execution summary."""
        total = len(results)
        successful = sum(1 for r in results if r.success)
        failed = total - successful

        lines = [
            f"\nExecution Summary:",
            f"  Total: {total}",
            f"  Successful: {successful}",
            f"  Failed: {failed}",
        ]

        if failed > 0:
            lines.append("\nFailures:")
            for result in results:
                if not result.success:
                    lines.append(
                        f"  - {result.plan_item.resource_type} '{result.plan_item.resource_name}': "
                        f"{result.error}"
                    )

        return "\n".join(lines)

