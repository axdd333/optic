"""Optic CLI — audit signals from the command line.

Usage:
  optic audit <text|file>         Audit a single signal or file
  optic batch <path>              Batch audit from CSV/JSON
  optic history                   View audit history
  optic show <audit_id>           Show audit details by ID
  optic config                    Manage configuration
  optic ml-audit <text>           ML-based audit of a single signal
  optic ml-audit-file <path>      ML audit from a text file
  optic ml-audit-batch <path>     Batch ML audit from CSV/JSON
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import click

from optic.signal import (
    AnomalyDetector,
    AuditConfig,
    AuditResult,
    PatternDetector,
    SignalAudit,
    SignalAuditor,
    SignalSource,
    ThresholdDetector,
)
from optic.signal.ml_detector import MLDetector, create_ml_detector

# ── helpers ──────────────────────────────────────────────────────────────────

HISTORY_DIR = Path(os.path.expanduser("~/.optic"))
HISTORY_FILE = HISTORY_DIR / "audit_history.json"
CONFIG_FILE = HISTORY_DIR / "config.json"


def ensure_history_dir() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def load_history() -> dict[str, Any]:
    ensure_history_dir()
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return {}


def save_history(history: dict[str, Any]) -> None:
    ensure_history_dir()
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str))


def load_config() -> dict[str, Any]:
    ensure_history_dir()
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {"detectors": [], "min_confidence": 0.0, "max_detections": 50}


def save_config(config: dict[str, Any]) -> None:
    ensure_history_dir()
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def _build_auditor() -> SignalAuditor:
    """Build an auditor with default detectors and config."""
    cfg = load_config()
    config = AuditConfig(
        detectors=cfg.get("detectors", []),
        min_confidence=cfg.get("min_confidence", 0.0),
        max_detections_per_signal=cfg.get("max_detections", 50),
    )
    auditor = SignalAuditor(config)
    auditor.add_detector(PatternDetector.default_bias_patterns())
    auditor.add_detector(AnomalyDetector())
    return auditor


def run_audit(content: str, source: SignalSource = SignalSource.TEXT) -> SignalAudit:
    """Run the full auditing pipeline on a single piece of content."""
    auditor = _build_auditor()
    return auditor.audit(content, source)


def format_result(audit: SignalAudit, verbose: bool = False) -> str:
    """Format a SignalAudit for human-readable display."""
    lines: list[str] = []
    lines.append(f"Audit ID: {audit.id}")
    lines.append(f"Created: {audit.created_at}")
    lines.append(f"Detections: {len(audit.detections)}")
    lines.append("")

    for d in audit.detections:
        severity_icon = {
            "critical": "\U0001f534",
            "high": "\U0001f7e0",
            "medium": "\U0001f7e1",
            "low": "\U0001f7e2",
            "info": "\U0001f535",
        }.get(d.severity.value, "\u26aa")
        lines.append(f"  {severity_icon} [{d.severity.value.upper():>8}] {d.attribute}")
        lines.append(f"     Confidence: {d.confidence:.2%}")
        lines.append(f"     {d.description}")
        if verbose and d.location:
            lines.append(f"     Location: {d.location}")
        lines.append("")

    if not audit.detections:
        lines.append("  \u2705 No issues detected.")

    return "\n".join(lines)


def format_ml_result(detections: list[dict[str, Any]], verbose: bool = False) -> str:
    """Format MLDetector results for human-readable display."""
    lines: list[str] = []
    lines.append(f"ML Detections: {len(detections)}")
    lines.append("")

    for d in detections:
        severity_icon = {
            "critical": "\U0001f534",
            "high": "\U0001f7e0",
            "medium": "\U0001f7e1",
            "low": "\U0001f7e2",
            "info": "\U0001f535",
        }.get(d.get("severity", "info"), "\u26aa")
        attr = d.get("attribute", "?")
        conf = d.get("confidence", 0)
        desc = d.get("description", "")
        lines.append(f"  {severity_icon} [{d.get('severity', 'info').upper():>8}] {attr}")
        lines.append(f"     Confidence: {conf:.2%}")
        lines.append(f"     {desc}")
        if verbose and d.get("evidence"):
            lines.append(f"     Evidence: {d['evidence']}")
        lines.append("")

    if not detections:
        lines.append("  \u2705 No ML issues detected.")

    return "\n".join(lines)


# ── CLI commands ─────────────────────────────────────────────────────────────


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """Optic — audits the perceived signal, not the person."""


@cli.command()
@click.argument("content")
@click.option("--source", "-s", type=click.Choice([s.value for s in SignalSource]),
              default="text", help="Source type of the signal.")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output.")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
def audit(content: str, source: str, verbose: bool, json_output: bool) -> None:
    """Audit a single signal (text or file path).

    If CONTENT is a path to an existing file, its contents will be read.
    """
    content_path = Path(content)
    if content_path.exists() and content_path.is_file():
        actual_content = content_path.read_text(encoding="utf-8")
        source_str = source
    else:
        actual_content = content
        source_str = source

    try:
        signal_source = SignalSource(source_str)
    except ValueError:
        click.echo(f"Invalid source: {source_str}", err=True)
        sys.exit(1)

    audit_result = run_audit(actual_content, signal_source)

    # Save to history
    history = load_history()
    history[audit_result.id] = audit_result.to_dict()
    save_history(history)

    if json_output:
        click.echo(audit_result.to_json())
    else:
        click.echo(format_result(audit_result, verbose))


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--verbose", "-v", is_flag=True)
@click.option("--json", "json_output", is_flag=True)
def batch(path: str, verbose: bool, json_output: bool) -> None:
    """Batch audit signals from a CSV or JSON file.

    CSV format: content[,source][,metadata...]
    JSON format: list of objects with 'content' and optional 'source' fields
    """
    path_obj = Path(path)
    ext = path_obj.suffix.lower()
    items: list[dict[str, Any]] = []

    if ext == ".csv":
        with path_obj.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                items.append({
                    "content": row.get("content", row.get("text", "")),
                    "source": row.get("source", "text"),
                })
    elif ext == ".json":
        data = json.loads(path_obj.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for item in data:
                items.append({
                    "content": item.get("content", item.get("text", "")),
                    "source": item.get("source", "text"),
                })
        else:
            click.echo("JSON must be an array of objects", err=True)
            sys.exit(1)
    else:
        click.echo(f"Unsupported file format: {ext} (use .csv or .json)", err=True)
        sys.exit(1)

    if not items:
        click.echo("No items found in file", err=True)
        sys.exit(1)

    auditor = _build_auditor()
    audit_results: list[SignalAudit] = []

    for i, item in enumerate(items):
        try:
            source = SignalSource(item["source"])
        except ValueError:
            source = SignalSource.TEXT

        if not item["content"]:
            continue

        click.echo(f"[{i + 1}/{len(items)}] Auditing...", err=True)
        audit_result = auditor.audit(item["content"], source)
        audit_results.append(audit_result)

        # Save each to history
        history = load_history()
        history[audit_result.id] = audit_result.to_dict()
        save_history(history)

    if json_output:
        click.echo(json.dumps([a.to_dict() for a in audit_results], indent=2))
    else:
        click.echo(f"\nBatch complete: {len(audit_results)}/{len(items)} audited")
        click.echo("\u2500" * 50)
        for r in audit_results:
            total = len(r.detections)
            max_sev = r.max_severity.value
            click.echo(f"  {r.id} — detections: {total}, max severity: {max_sev}")


@cli.command()
@click.option("--limit", "-n", default=20, help="Number of recent audits to show.")
@click.option("--json", "json_output", is_flag=True)
def history(limit: int, json_output: bool) -> None:
    """View recent audit history."""
    hist = load_history()
    if not hist:
        click.echo("No audit history found.")
        return

    sorted_items = sorted(hist.items(), key=lambda x: x[1].get("created_at", ""), reverse=True)
    entries = sorted_items[:limit]

    if json_output:
        click.echo(json.dumps(dict(entries), indent=2))
        return

    click.echo(f"Recent audits (last {len(entries)}/{len(hist)}):")
    click.echo("\u2500" * 80)
    for audit_id, data in entries:
        timestamp = data.get("created_at", "?")
        detections = data.get("detection_count", len(data.get("detections", [])))
        max_sev = data.get("max_severity", "?")
        preview = data.get("content_summary", "")[:60]
        click.echo(f"  {audit_id}")
        click.echo(f"    Time: {timestamp}  Severity: {max_sev}  Detections: {detections}")
        click.echo(f"    Summary: {preview}")
        click.echo()


@cli.command()
@click.argument("audit_id")
@click.option("--json", "json_output", is_flag=True)
def show(audit_id: str, json_output: bool) -> None:
    """Show detailed results for a specific audit by ID."""
    hist = load_history()
    if audit_id not in hist:
        click.echo(f"Audit '{audit_id}' not found.", err=True)
        sys.exit(1)

    data = hist[audit_id]
    if json_output:
        click.echo(json.dumps(data, indent=2, default=str))
        return

    click.echo(f"Audit: {audit_id}")
    click.echo(f"Created: {data.get('created_at', '?')}")
    click.echo(f"Source: {data.get('source', '?')}")
    click.echo(f"\nContent: {data.get('content_summary', '')[:200]}")
    click.echo(f"\nDetections ({len(data.get('detections', []))}):")
    click.echo("\u2500" * 50)

    for d in data.get("detections", []):
        click.echo(f"  [{d.get('severity', 'info').upper():>8}] {d.get('attribute', '?')}")
        click.echo(f"       Confidence: {d.get('confidence', 0):.2%}")
        click.echo(f"       {d.get('description', '')}")
        click.echo()


@cli.group()
def config() -> None:
    """Manage audit configuration."""


@config.command("show")
def config_show() -> None:
    """Show current configuration."""
    cfg = load_config()
    click.echo(json.dumps(cfg, indent=2))


@config.command("set")
@click.option("--min-confidence", type=float, help="Minimum confidence threshold (0.0-1.0).")
@click.option("--max-detections", type=int, help="Maximum detections per signal.")
@click.option("--detectors", help="Comma-separated list of detector names.")
def config_set(min_confidence: float | None, max_detections: int | None,
               detectors: str | None) -> None:
    """Set configuration values."""
    cfg = load_config()
    if min_confidence is not None:
        cfg["min_confidence"] = max(0.0, min(1.0, min_confidence))
    if max_detections is not None:
        cfg["max_detections"] = max(1, max_detections)
    if detectors is not None:
        cfg["detectors"] = [d.strip() for d in detectors.split(",") if d.strip()]
    save_config(cfg)
    click.echo("Configuration updated:")
    click.echo(json.dumps(cfg, indent=2))


@config.command("reset")
def config_reset() -> None:
    """Reset configuration to defaults."""
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
    click.echo("Configuration reset to defaults.")


# ── ML Audit Commands ────────────────────────────────────────────────────────


def _build_ml_detector(**kwargs: Any) -> MLDetector:
    """Build an MLDetector with default settings."""
    return create_ml_detector(**kwargs)


@cli.command()
@click.argument("content")
@click.option("--confidence-threshold", type=float, default=0.3,
              help="Minimum confidence threshold (0.0-1.0).")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output.")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
def ml_audit(content: str, confidence_threshold: float, verbose: bool, json_output: bool) -> None:
    """Run ML-based audit on a single signal (text or file path).

    Uses the MLDetector for keyword analysis, pattern analysis,
    and sentiment divergence detection.
    """
    content_path = Path(content)
    if content_path.exists() and content_path.is_file():
        actual_content = content_path.read_text(encoding="utf-8")
    else:
        actual_content = content

    ml_detector = _build_ml_detector(confidence_threshold=confidence_threshold)
    results = ml_detector.analyze(actual_content)

    # Save to ML history
    history = load_history()
    ml_entry = {
        "type": "ml_audit",
        "content_summary": actual_content[:100],
        "created_at": datetime.now().isoformat(),
        "detections": results,
        "detection_count": len(results),
        "confidence_threshold": confidence_threshold,
    }
    audit_id = f"ml-{datetime.now().strftime('%Y%m%d%H%M%S')}-{hash(actual_content) % 10000:04d}"
    history[audit_id] = ml_entry
    save_history(history)

    if json_output:
        click.echo(json.dumps({
            "audit_id": audit_id,
            "detections": results,
            "detection_count": len(results),
        }, indent=2))
    else:
        click.echo(f"ML Audit ID: {audit_id}")
        click.echo(format_ml_result(results, verbose))


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--confidence-threshold", type=float, default=0.3,
              help="Minimum confidence threshold (0.0-1.0).")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output.")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
def ml_audit_file(path: str, confidence_threshold: float, verbose: bool, json_output: bool) -> None:
    """Run ML-based audit on a text file.

    Reads the file and runs ML detection on its contents.
    """
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        click.echo(f"File not found: {path}", err=True)
        sys.exit(1)

    actual_content = file_path.read_text(encoding="utf-8")

    ml_detector = _build_ml_detector(confidence_threshold=confidence_threshold)
    results = ml_detector.analyze(actual_content)

    history = load_history()
    ml_entry = {
        "type": "ml_audit_file",
        "file_path": str(file_path.resolve()),
        "content_summary": actual_content[:100],
        "created_at": datetime.now().isoformat(),
        "detections": results,
        "detection_count": len(results),
        "confidence_threshold": confidence_threshold,
    }
    audit_id = f"ml-file-{datetime.now().strftime('%Y%m%d%H%M%S')}-{file_path.stem[:20]}"
    history[audit_id] = ml_entry
    save_history(history)

    if json_output:
        click.echo(json.dumps({
            "audit_id": audit_id,
            "file_path": str(file_path.resolve()),
            "detections": results,
            "detection_count": len(results),
        }, indent=2))
    else:
        click.echo(f"ML Audit ID: {audit_id}")
        click.echo(f"File: {file_path.resolve()}")
        click.echo(format_ml_result(results, verbose))


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--confidence-threshold", type=float, default=0.3,
              help="Minimum confidence threshold (0.0-1.0).")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output.")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
def ml_audit_batch(path: str, confidence_threshold: float, verbose: bool, json_output: bool) -> None:
    """Run ML-based audit on multiple signals from a CSV or JSON file.

    CSV format: content[,metadata...]
    JSON format: list of objects with 'content' field
    """
    path_obj = Path(path)
    ext = path_obj.suffix.lower()
    items: list[str] = []

    if ext == ".csv":
        with path_obj.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                content = row.get("content", row.get("text", "")).strip()
                if content:
                    items.append(content)
    elif ext == ".json":
        data = json.loads(path_obj.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for item in data:
                content = item.get("content", item.get("text", "")).strip()
                if content:
                    items.append(content)
        else:
            click.echo("JSON must be an array of objects", err=True)
            sys.exit(1)
    else:
        click.echo(f"Unsupported file format: {ext} (use .csv or .json)", err=True)
        sys.exit(1)

    if not items:
        click.echo("No items found in file", err=True)
        sys.exit(1)

    ml_detector = _build_ml_detector(confidence_threshold=confidence_threshold)
    all_results: list[dict[str, Any]] = []

    for i, content in enumerate(items):
        click.echo(f"[{i + 1}/{len(items)}] ML Auditing...", err=True)
        results = ml_detector.analyze(content)
        all_results.append({
            "content_summary": content[:100],
            "detections": results,
            "detection_count": len(results),
        })

    if json_output:
        click.echo(json.dumps(all_results, indent=2))
    else:
        click.echo(f"\nBatch ML complete: {len(all_results)}/{len(items)} audited")
        click.echo("\u2500" * 50)
        for r in all_results:
            preview = r["content_summary"][:60]
            click.echo(f"  Detections: {r['detection_count']} | {preview}...")


if __name__ == "__main__":
    cli()
