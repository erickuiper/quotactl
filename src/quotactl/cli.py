"""Command-line interface for quota management."""

import sys
from pathlib import Path
from typing import List, Optional

import click

from quotactl.config import RancherInstanceConfig
from quotactl.diff import format_plan_summary
from quotactl.executor import Executor
from quotactl.logging import setup_logging
from quotactl.planner import Planner
from quotactl.rancher_client import RancherAPIError, RancherClient
from quotactl.report import generate_quota_report


@click.group()
def cli() -> None:
    """Rancher Quota Automation Tool."""
    pass


@cli.command("apply")
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to Rancher instance configuration file",
)
@click.option(
    "--cluster",
    multiple=True,
    help="Cluster ID(s) to process (can be specified multiple times)",
)
@click.option(
    "--project",
    multiple=True,
    help="Project name(s) to process (can be specified multiple times)",
)
@click.option(
    "--all-projects",
    is_flag=True,
    help="Process all projects in selected clusters",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show planned changes without applying them",
)
@click.option(
    "--apply",
    is_flag=True,
    help="Apply quota changes (required for write operations)",
)
@click.option(
    "--continue-on-error",
    is_flag=True,
    help="Continue processing after errors (default: fail-fast)",
)
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="Logging level",
)
@click.option(
    "--token-env-var",
    help="Environment variable name containing Rancher API token",
)
@click.pass_context
def apply_cmd(
    ctx: click.Context,
    config: Path,
    cluster: tuple,
    project: tuple,
    all_projects: bool,
    dry_run: bool,
    apply: bool,
    continue_on_error: bool,
    log_level: str,
    token_env_var: Optional[str],
) -> None:
    """Enforce project and namespace quotas (dry-run or apply)."""
    # Setup logging
    logger = setup_logging(log_level)

    # Validate arguments
    if not dry_run and not apply:
        click.echo("Error: Either --dry-run or --apply must be specified", err=True)
        sys.exit(1)

    if dry_run and apply:
        click.echo("Error: --dry-run and --apply cannot be used together", err=True)
        sys.exit(1)

    # Load configuration
    try:
        instance_config = RancherInstanceConfig.from_file(config, token_env_var)
        logger.set_context(instance=instance_config.url)
    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)

    # Convert cluster and project tuples to lists
    cluster_ids: Optional[List[str]] = list(cluster) if cluster else None
    project_names: Optional[List[str]] = list(project) if project else None

    # Initialize Rancher client
    try:
        client = RancherClient(instance_config.url, instance_config.token, logger)
    except Exception as e:
        click.echo(f"Error initializing Rancher client: {e}", err=True)
        sys.exit(1)

    # Create planner
    planner = Planner(client, instance_config, logger)

    # Generate execution plan
    try:
        plan_items = planner.create_plan(
            cluster_ids=cluster_ids,
            project_names=project_names,
            all_projects=all_projects,
        )
    except RancherAPIError as e:
        click.echo(f"Error creating execution plan: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        if not continue_on_error:
            sys.exit(1)

    # Filter plan items to only those with changes
    plan_items_with_changes = [item for item in plan_items if item.diff.has_changes()]

    if not plan_items_with_changes:
        click.echo("No quota changes needed. All resources match desired state.")
        sys.exit(0)

    # Display plan
    click.echo(format_plan_summary(plan_items_with_changes))

    if dry_run:
        click.echo("\n[DRY RUN] No changes applied.")
        sys.exit(0)

    # Execute plan
    executor = Executor(client, logger)
    results = executor.execute(plan_items_with_changes, dry_run=False)

    # Display summary
    summary = Executor.summarize(results)
    click.echo(summary)

    # Determine exit code
    failed = sum(1 for r in results if not r.success)
    if failed > 0:
        if continue_on_error:
            sys.exit(2)  # Partial failure
        else:
            sys.exit(1)  # Fatal error

    sys.exit(0)


@cli.command("report")
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to Rancher instance configuration file",
)
@click.option(
    "--output",
    "-o",
    required=True,
    type=click.Path(path_type=Path),
    help="Output HTML file path",
)
@click.option(
    "--cluster",
    multiple=True,
    help="Cluster ID(s) to include (default: all clusters)",
)
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="Logging level",
)
@click.option(
    "--token-env-var",
    help="Environment variable name containing Rancher API token",
)
def report_cmd(
    config: Path,
    output: Path,
    cluster: tuple,
    log_level: str,
    token_env_var: Optional[str],
) -> None:
    """Generate HTML report of all project and namespace quotas."""
    logger = setup_logging(log_level)

    try:
        instance_config = RancherInstanceConfig.from_file(config, token_env_var)
    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)

    try:
        client = RancherClient(
            instance_config.url, instance_config.token, logger
        )
    except Exception as e:
        click.echo(f"Error initializing Rancher client: {e}", err=True)
        sys.exit(1)

    cluster_ids = list(cluster) if cluster else None
    try:
        generate_quota_report(
            client=client,
            output_path=output,
            logger=logger,
            cluster_ids=cluster_ids,
        )
    except RancherAPIError as e:
        click.echo(f"Error generating report: {e}", err=True)
        sys.exit(1)

    click.echo(f"Report written to {output}")


def main() -> None:
    """Entry point for quotactl."""
    cli()


if __name__ == "__main__":
    main()

