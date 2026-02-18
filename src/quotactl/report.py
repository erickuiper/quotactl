"""Generate HTML reports of project and namespace quotas."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from quotactl.logging import ContextLogger
from quotactl.models import Namespace, Project, QuotaSpec
from quotactl.rancher_client import RancherAPIError, RancherClient


@dataclass
class ClusterQuotaData:
    """Quota data for a cluster."""

    cluster_id: str
    cluster_name: str
    projects: List["ProjectQuotaData"] = field(default_factory=list)


@dataclass
class ProjectQuotaData:
    """Quota data for a project."""

    project: Project
    namespaces: List[Namespace] = field(default_factory=list)


def _format_quota_value(val: Optional[str]) -> str:
    """Format quota value for display."""
    return val if val else "—"


def _quota_row_html(q: QuotaSpec) -> str:
    """Generate HTML table row for a quota spec."""
    return f"""
        <tr>
            <td>{_format_quota_value(q.cpu_limit)}</td>
            <td>{_format_quota_value(q.memory_limit)}</td>
            <td>{_format_quota_value(q.cpu_reservation)}</td>
            <td>{_format_quota_value(q.memory_reservation)}</td>
        </tr>"""


def _project_section_html(cluster: ClusterQuotaData) -> str:
    """Generate HTML section for a cluster with its projects and namespaces."""
    sections: List[str] = []
    for pdata in cluster.projects:
        p = pdata.project
        project_quota_html = _quota_row_html(p.quota) if not p.quota.is_empty() else """
        <tr><td colspan="4"><em>No quota set</em></td></tr>"""
        sections.append(f"""
        <div class="project">
            <h3>{p.name} <span class="project-id">({p.id})</span></h3>
            <h4>Project quota</h4>
            <table>
                <thead>
                    <tr>
                        <th>CPU limit</th>
                        <th>Memory limit</th>
                        <th>CPU reservation</th>
                        <th>Memory reservation</th>
                    </tr>
                </thead>
                <tbody>
                    {project_quota_html}
                </tbody>
            </table>
            <h4>Namespaces ({len(pdata.namespaces)})</h4>
""")
        if pdata.namespaces:
            ns_rows = []
            for ns in pdata.namespaces:
                ns_quota_html = _quota_row_html(ns.quota) if not ns.quota.is_empty() else """
                <tr><td colspan="4"><em>No quota set</em></td></tr>"""
                ns_rows.append(f"""
            <div class="namespace">
                <h5>{ns.name}</h5>
                <table>
                    <thead>
                        <tr>
                            <th>CPU limit</th>
                            <th>Memory limit</th>
                            <th>CPU reservation</th>
                            <th>Memory reservation</th>
                        </tr>
                    </thead>
                    <tbody>
                        {ns_quota_html}
                    </tbody>
                </table>
            </div>""")
            sections[-1] += "\n".join(ns_rows)
        else:
            sections[-1] += "<p><em>No namespaces in project</em></p>"
        sections[-1] += "\n        </div>"
    return "\n".join(sections)


def _html_template(
    title: str,
    rancher_url: str,
    generated_at: str,
    clusters: List[ClusterQuotaData],
) -> str:
    """Generate full HTML document."""
    cluster_sections = []
    for cluster in clusters:
        section = f"""
    <section class="cluster">
        <h2>{cluster.cluster_name} <span class="cluster-id">({cluster.cluster_id})</span></h2>
        {_project_section_html(cluster)}
    </section>"""
        cluster_sections.append(section)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        :root {{
            --bg: #f5f5f5;
            --card: #fff;
            --border: #ddd;
            --text: #333;
            --muted: #666;
            --accent: #2563eb;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 2rem;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
        }}
        .header {{
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border);
        }}
        .header h1 {{ margin: 0 0 0.5rem 0; }}
        .meta {{ color: var(--muted); font-size: 0.9rem; }}
        section.cluster {{
            background: var(--card);
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .project {{
            margin-top: 1.5rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--border);
        }}
        .project:first-of-type {{ margin-top: 0; padding-top: 0; border-top: none; }}
        .namespace {{
            margin: 1rem 0 1rem 2rem;
            padding: 1rem;
            background: var(--bg);
            border-radius: 4px;
        }}
        h2 {{ margin-top: 0; color: var(--accent); }}
        h3 {{ margin: 0 0 0.5rem 0; }}
        h4 {{ margin: 1rem 0 0.5rem 0; font-size: 0.95rem; }}
        h5 {{ margin: 0 0 0.5rem 0; font-size: 0.9rem; color: var(--muted); }}
        .cluster-id, .project-id {{ font-weight: normal; color: var(--muted); font-size: 0.85em; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        th, td {{
            padding: 0.5rem 0.75rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            background: var(--bg);
            font-weight: 600;
        }}
        tr:hover {{ background: #fafafa; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <div class="meta">
            Rancher: {rancher_url} · Generated: {generated_at}
        </div>
    </div>
{chr(10).join(cluster_sections)}
</body>
</html>"""


def collect_quota_data(
    client: RancherClient,
    logger: ContextLogger,
    cluster_ids: Optional[List[str]] = None,
) -> List[ClusterQuotaData]:
    """Collect project and namespace quota data from Rancher and Kubernetes APIs."""
    clusters: List[ClusterQuotaData] = []

    # Get clusters
    if cluster_ids:
        cluster_list = [client.get_cluster(cid) for cid in cluster_ids]
    else:
        response = client._request("GET", "/v3/clusters")
        cluster_list = response.get("data", [])

    for cluster_data in cluster_list:
        cluster_id = cluster_data.get("id", "")
        cluster_name = cluster_data.get("name", cluster_id)
        logger.set_context(cluster=cluster_id)
        logger.info(f"Collecting quotas for cluster: {cluster_name}")

        cluster_quota = ClusterQuotaData(
            cluster_id=cluster_id,
            cluster_name=cluster_name,
        )

        try:
            projects = client.list_projects(cluster_id)
        except RancherAPIError as e:
            logger.warning(f"Failed to list projects for {cluster_name}: {e}")
            clusters.append(cluster_quota)
            continue

        for project in projects:
            logger.set_context(project=project.name)
            # Fetch full project by ID so we get spec.resourceQuota (list may omit it)
            try:
                project = client.get_project(project.id)
            except RancherAPIError as e:
                logger.warning(f"Failed to get project {project.name}: {e}")
                continue
            try:
                namespaces = client.list_namespaces(project.id)
            except RancherAPIError as e:
                logger.warning(f"Failed to list namespaces for project {project.name}: {e}")
                namespaces = []

            cluster_quota.projects.append(
                ProjectQuotaData(project=project, namespaces=namespaces)
            )

        clusters.append(cluster_quota)

    return clusters


def generate_quota_report(
    client: RancherClient,
    output_path: Path,
    logger: ContextLogger,
    cluster_ids: Optional[List[str]] = None,
    title: str = "Rancher Quota Overview",
) -> None:
    """Generate an HTML report of all project and namespace quotas.

    Args:
        client: Rancher API client.
        output_path: Path to write the HTML file.
        logger: Logger for progress and errors.
        cluster_ids: Optional list of cluster IDs to include. If None, all clusters are included.
        title: Report title.
    """
    clusters = collect_quota_data(client, logger, cluster_ids)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = _html_template(
        title=title,
        rancher_url=client.base_url,
        generated_at=generated_at,
        clusters=clusters,
    )
    output_path.write_text(html, encoding="utf-8")
    logger.info(f"Report written to {output_path}")
