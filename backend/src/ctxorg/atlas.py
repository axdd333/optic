from __future__ import annotations

from pathlib import Path

from . import cfg as cfgmod
from . import db, terms


def write(conn, cfg: dict, run_id: str) -> Path:
    plans = db.plan_rows(conn, run_id)
    items = db.item_map(conn)
    groups = by_cluster(plans)
    path = cfgmod.state_dir(cfg, "atlas") / f"{run_id}.md"
    path.write_text(render(run_id, groups, items), encoding="utf-8")
    return path


def by_cluster(plans: list[dict]) -> dict[str, list[dict]]:
    out = {}
    for rec in plans:
        out.setdefault(rec["cluster"], []).append(rec)
    return out


def render(run_id: str, groups: dict, items: dict) -> str:
    parts = [f"# Context Atlas {run_id}", "", mermaid(groups), ""]
    for cid, rows in groups.items():
        parts.extend(cluster_md(cid, rows, items))
    return "\n".join(parts)


def mermaid(groups: dict) -> str:
    lines = ["```mermaid", "flowchart TD"]
    for idx, (cid, rows) in enumerate(groups.items(), start=1):
        label = f"{idx}: {len(rows)} items"
        lines.append(f'  C{idx}["{label}"]')
    lines.append("```")
    return "\n".join(lines)


def cluster_md(cid: str, rows: list[dict], items: dict) -> list[str]:
    out = [f"## Cluster {cid}", ""]
    for rec in rows[:80]:
        item = items.get(rec["id"], {})
        out.append(f"- `{rec['dst']}`")
        out.append(f"  from `{rec['src']}`")
        out.append(f"  evidence: {terms.summary(item.get('text', ''), 240)}")
    out.append("")
    return out

