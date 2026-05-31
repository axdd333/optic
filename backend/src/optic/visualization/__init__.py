"""Signal visualization module for Optic — audit result charts and PDF reports."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

from optic.signal.models import AuditResult, Severity

# Color palette
COLORS = {
    "info": "#6b7280",
    "low": "#f59e0b",
    "medium": "#f97316",
    "high": "#ef4444",
    "critical": "#7f1d1d",
}
SEVERITY_ORDER = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


def _severity_color(severity: Severity) -> str:
    return COLORS.get(severity.value, "#6b7280")


def _severity_score(severity: Severity) -> int:
    return SEVERITY_ORDER.index(severity)


# ── Chart Functions ────────────────────────────────────────────────────────────


def plot_severity_distribution(
    result: AuditResult,
    title: str = "Detection Severity Distribution",
    figsize: tuple[int, int] = (10, 6),
) -> Figure:
    """Plot a bar chart of detection counts by severity level."""
    counts = {s.value: 0 for s in SEVERITY_ORDER}
    for s in result.signals:
        for d in s.detections:
            counts[d.severity.value] = counts.get(d.severity.value, 0) + 1

    fig, ax = plt.subplots(figsize=figsize)
    severities = [s.value for s in SEVERITY_ORDER]
    values = [counts[s] for s in severities]
    colors = [COLORS[s] for s in severities]

    bars = ax.bar(severities, values, color=colors, edgecolor="white", linewidth=1.2)

    for bar, val in zip(bars, values):
        if val > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(values) * 0.02,
                str(val),
                ha="center",
                va="bottom",
                fontweight="bold",
            )

    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Severity", fontsize=11)
    ax.set_ylabel("Detection Count", fontsize=11)
    ax.set_ylim(0, max(values) * 1.2 if values else 1)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="x", rotation=0)

    fig.tight_layout()
    return fig


def plot_detection_timeline(
    result: AuditResult,
    title: str = "Detection Timeline",
    figsize: tuple[int, int] = (12, 5),
) -> Figure:
    """Plot a timeline/heatmap of detections across signals."""
    if not result.signals:
        fig, ax = plt.subplots(figsize=figsize)
        ax.text(0.5, 0.5, "No signals to plot", ha="center", va="center", fontsize=14)
        ax.set_title(title)
        return fig

    signal_labels = [s.content_summary[:30] if s.content_summary else s.id[:20] for s in result.signals]

    max_dets = max(len(s.detections) for s in result.signals)
    if max_dets == 0:
        fig, ax = plt.subplots(figsize=figsize)
        ax.text(0.5, 0.5, "No detections found", ha="center", va="center", fontsize=14)
        ax.set_title(title)
        return fig

    data = np.zeros((len(result.signals), max_dets))
    for i, s in enumerate(result.signals):
        for j, d in enumerate(s.detections[:max_dets]):
            data[i, j] = _severity_score(d.severity)

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(data, cmap="YlOrRd", aspect="auto", vmin=0, vmax=len(SEVERITY_ORDER) - 1)

    ax.set_yticks(range(len(result.signals)))
    ax.set_yticklabels(signal_labels, fontsize=9)
    ax.set_xlabel("Detection Index", fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)

    cbar = fig.colorbar(im, ax=ax, ticks=range(len(SEVERITY_ORDER)))
    cbar.set_ticklabels([s.value for s in SEVERITY_ORDER])
    cbar.ax.tick_params(labelsize=8)

    fig.tight_layout()
    return fig


def plot_signal_score_heatmap(
    result: AuditResult,
    title: str = "Signal Score Heatmap",
    figsize: Optional[tuple[int, int]] = None,
) -> Figure:
    """Plot a horizontal bar chart of each signal's score contribution."""
    if not result.signals:
        fig, ax = plt.subplots(figsize=figsize or (8, 6))
        ax.text(0.5, 0.5, "No signals to plot", ha="center", va="center", fontsize=14)
        ax.set_title(title)
        return fig

    scores = []
    labels = []
    colors_list = []

    for s in result.signals:
        score = s.detection_count / max(len(result.signals), 1)
        scores.append(score)
        label = s.content_summary[:35] if s.content_summary else s.id[:25]
        labels.append(label)
        severity_score = max((_severity_score(d.severity) for d in s.detections), default=0)
        colors_list.append(COLORS[SEVERITY_ORDER[severity_score].value])

    if figsize is None:
        figsize = (8, max(4, len(result.signals) * 0.5 + 2))
    fig, ax = plt.subplots(figsize=figsize)
    y_pos = range(len(labels))
    bars = ax.barh(y_pos, scores, color=colors_list, edgecolor="white", linewidth=0.8)

    for bar, score in zip(bars, scores):
        if score > 0:
            ax.text(
                bar.get_width() + max(scores) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{score:.2f}",
                ha="left",
                va="center",
                fontsize=9,
            )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Detection Density Score", fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    ax.invert_yaxis()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return fig


def plot_attribute_summary(
    result: AuditResult,
    title: str = "Detection Attributes Summary",
    figsize: tuple[int, int] = (10, 6),
) -> Figure:
    """Plot a pie chart or bar chart of detection attributes."""
    attr_counts: dict[str, int] = {}
    for s in result.signals:
        for d in s.detections:
            attr_counts[d.attribute] = attr_counts.get(d.attribute, 0) + 1

    if not attr_counts:
        fig, ax = plt.subplots(figsize=figsize)
        ax.text(0.5, 0.5, "No attributes found", ha="center", va="center", fontsize=14)
        ax.set_title(title)
        return fig

    fig, ax = plt.subplots(figsize=figsize)
    attributes = list(attr_counts.keys())
    values = list(attr_counts.values())
    colors_pie = plt.cm.Set3(np.linspace(0, 1, len(attributes)))

    wedges, texts, autotexts = ax.pie(
        values,
        labels=None,
        autopct="%1.1f%%",
        startangle=90,
        colors=colors_pie,
        textprops={"fontsize": 9},
    )

    legend_labels = [f"{a} ({v})" for a, v in zip(attributes, values)]
    ax.legend(wedges, legend_labels, title="Attributes", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1), fontsize=9)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)

    fig.tight_layout()
    return fig


# ── PDF Report Generator ────────────────────────────────────────────────────────


def generate_report(
    result: AuditResult,
    output_path: str | Path,
    include_charts: bool = True,
) -> Path:
    """Generate a PDF report for an audit result.

    Uses matplotlib's PDF backend to create a multi-page report with charts.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    figures: list[Figure] = []
    if include_charts:
        figures.append(plot_severity_distribution(result))
        figures.append(plot_detection_timeline(result))
        figures.append(plot_signal_score_heatmap(result))
        if result.signals:
            figures.append(plot_attribute_summary(result))

    # Create a summary page
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(output_path) as pdf:
        # Title page
        fig_title, ax = plt.subplots(figsize=(8.5, 11))
        ax.axis("off")
        ax.text(
            0.5, 0.85, "Optic Audit Report",
            ha="center", va="center", fontsize=24, fontweight="bold",
        )
        ax.text(0.5, 0.75, f"Audit ID: {result.audit_id}", ha="center", va="center", fontsize=14)
        ax.text(0.5, 0.70, f"Created: {result.created_at}", ha="center", va="center", fontsize=12)
        ax.text(0.5, 0.65, f"Overall Score: {result.score:.3f}", ha="center", va="center", fontsize=14, fontweight="bold")

        if result.summary:
            ax.text(0.5, 0.55, "Summary", ha="center", va="center", fontsize=16, fontweight="bold")
            ax.text(0.5, 0.48, result.summary, ha="center", va="center", fontsize=11, wrap=True)

        if result.recommendations:
            ax.text(0.5, 0.35, "Recommendations", ha="center", va="center", fontsize=16, fontweight="bold")
            for i, rec in enumerate(result.recommendations):
                ax.text(0.5, 0.30 - i * 0.04, f"{i+1}. {rec}", ha="center", va="center", fontsize=10, wrap=True)

        stats_text = (
            f"Signals analyzed: {len(result.signals)}\n"
            f"Total detections: {result.total_detections}\n"
            f"Critical: {result.critical_count}  |  High: {result.high_count}"
        )
        ax.text(0.5, 0.15, stats_text, ha="center", va="center", fontsize=12,
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#f3f4f6"))

        pdf.savefig(fig_title)
        plt.close(fig_title)

        for fig in figures:
            pdf.savefig(fig)
            plt.close(fig)

        # Summary stats page
        fig_stats, ax = plt.subplots(figsize=(8.5, 11))
        ax.axis("off")
        ax.text(0.5, 0.95, "Detection Details", ha="center", va="center", fontsize=18, fontweight="bold")

        y = 0.88
        for s in result.signals:
            label = s.content_summary[:50] if s.content_summary else s.id[:40]
            ax.text(0.1, y, f"Signal: {label}", ha="left", va="center", fontsize=10, fontweight="bold")
            y -= 0.04
            if not s.detections:
                ax.text(0.15, y, "No detections", ha="left", va="center", fontsize=9, style="italic")
                y -= 0.03
            for d in s.detections:
                sev_color = _severity_color(d.severity)
                det_text = f"  [{d.severity.value.upper()}] {d.attribute}: {d.description[:60]}"
                ax.text(0.15, y, det_text, ha="left", va="center", fontsize=8, color=sev_color)
                y -= 0.03
            y -= 0.02

            if y < 0.05:
                pdf.savefig(fig_stats)
                plt.close(fig_stats)
                fig_stats, ax = plt.subplots(figsize=(8.5, 11))
                ax.axis("off")
                y = 0.95

        pdf.savefig(fig_stats)
        plt.close(fig_stats)

    plt.close("all")
    return output_path


def save_charts(
    result: AuditResult,
    output_dir: str | Path,
    prefix: str = "optic_audit",
) -> list[Path]:
    """Save individual chart figures to PNG files.

    Returns a list of saved file paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved: list[Path] = []

    charts = [
        ("severity_distribution", plot_severity_distribution(result)),
        ("detection_timeline", plot_detection_timeline(result)),
        ("signal_score_heatmap", plot_signal_score_heatmap(result)),
        ("attribute_summary", plot_attribute_summary(result)),
    ]

    for name, fig in charts:
        path = output_dir / f"{prefix}_{name}.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        saved.append(path)

    return saved
