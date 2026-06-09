"""Report generator for Optic audit results.

Supports HTML, JSON, and PDF output formats.
Integrates with the FastAPI API layer.
"""

from __future__ import annotations

import json
import html
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import markdown as md_lib

    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

try:
    from jinja2 import Environment, FileSystemLoader, PackageLoader

    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False

try:
    from fpdf import FPDF

    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
REPORT_DIR = Path.home() / ".optic" / "reports"


def _ensure_report_dir():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


class ReportGenerator:
    """Generate audit reports in multiple formats."""

    def __init__(self, template_dir: str | Path | None = None):
        self.template_dir = Path(template_dir) if template_dir else TEMPLATE_DIR
        self._jinja_env: Environment | None = None
        if HAS_JINJA2:
            self._jinja_env = Environment(
                loader=FileSystemLoader(str(self.template_dir)),
                autoescape=True,
            )

    # ── JSON Report ──────────────────────────────────────────────────────

    def to_json(self, audit_data: dict[str, Any], indent: int = 2) -> str:
        """Generate a JSON report string from audit data.

        Args:
            audit_data: Dict with audit fields (id, source, content_summary,
                       created_at, detections, metadata, score, etc.)
            indent: JSON indentation level.

        Returns:
            Formatted JSON string.
        """
        report = {
            "report_type": "audit",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "optic_version": "0.1.0",
            "audit": audit_data,
        }
        return json.dumps(report, indent=indent, default=str)

    def to_json_file(
        self, audit_data: dict[str, Any], filepath: str | Path | None = None
    ) -> Path:
        """Write a JSON report to disk.

        Args:
            audit_data: Dict with audit fields.
            filepath: Output path. Auto-generated if None.

        Returns:
            Path to the written file.
        """
        _ensure_report_dir()
        if filepath is None:
            audit_id = audit_data.get("id", "unknown")
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            filepath = REPORT_DIR / f"audit_{audit_id}_{timestamp}.json"
        filepath = Path(filepath)
        filepath.write_text(self.to_json(audit_data))
        logger.info(f"JSON report written to {filepath}")
        return filepath

    # ── HTML Report ──────────────────────────────────────────────────────

    def _default_html_report(self, audit_data: dict[str, Any]) -> str:
        """Fallback HTML report when Jinja2 templates are unavailable."""
        detections = audit_data.get("detections", [])
        severity_colors = {
            "critical": "#dc3545",
            "high": "#fd7e14",
            "medium": "#ffc107",
            "low": "#28a745",
            "info": "#17a2b8",
        }
        detection_rows = ""
        for d in detections:
            color = severity_colors.get(d.get("severity", "").lower(), "#6c757d")
            attr = html.escape(str(d.get("attribute", "")))
            sev = html.escape(str(d.get("severity", "")))
            desc = html.escape(str(d.get("description", "")))
            conf = d.get("confidence", 0)
            src = html.escape(str(d.get("source", "rule")))
            detection_rows += f"""
            <tr>
                <td>{attr}</td>
                <td><span class="badge" style="background:{color}">{sev}</span></td>
                <td>{conf:.3f}</td>
                <td>{src}</td>
                <td>{desc}</td>
            </tr>"""

        score = audit_data.get("score")
        score_html = ""
        if score is not None:
            score_html = f'<p><strong>Overall Score:</strong> {html.escape(str(score))}</p>'

        audit_id = html.escape(str(audit_data.get("id", "")))
        audit_source = html.escape(str(audit_data.get("source", "N/A")))
        audit_created = html.escape(str(audit_data.get("created_at", "N/A")))
        content_summary = html.escape(str(audit_data.get("content_summary", "")))
        gen_time = html.escape(datetime.now(timezone.utc).isoformat())

        rec_html = ""
        if audit_data.get("recommendations"):
            rec_items = "".join(
                f"<li>{html.escape(str(r))}</li>"
                for r in audit_data.get("recommendations", [])
            )
            rec_html = f'<div class="recommendations"><strong>Recommendations:</strong><ul>{rec_items}</ul></div>'

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Optic Audit Report — {audit_id}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f8f9fa; color: #333; }}
        .container {{ max-width: 960px; margin: 0 auto; background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 30px; }}
        h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        .meta {{ color: #6c757d; font-size: 0.9em; margin-bottom: 20px; }}
        .meta span {{ margin-right: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #dee2e6; }}
        th {{ background: #f1f3f5; font-weight: 600; }}
        .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; color: #fff; font-size: 0.85em; font-weight: 600; text-transform: uppercase; }}
        .summary {{ background: #e8f4f8; padding: 15px; border-radius: 6px; margin: 15px 0; }}
        .recommendations {{ background: #fff3cd; padding: 15px; border-radius: 6px; margin: 15px 0; }}
        .recommendations ul {{ margin: 5px 0; padding-left: 20px; }}
        .footer {{ margin-top: 30px; color: #6c757d; font-size: 0.8em; text-align: center; border-top: 1px solid #dee2e6; padding-top: 15px; }}
        .no-detections {{ text-align: center; padding: 30px; color: #6c757d; font-style: italic; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Optic Audit Report</h1>
        <div class="meta">
            <span><strong>Audit ID:</strong> {audit_id}</span>
            <span><strong>Source:</strong> {audit_source}</span>
            <span><strong>Created:</strong> {audit_created}</span>
            <span><strong>Generated:</strong> {gen_time}</span>
        </div>

        {score_html}

        {f'<div class="summary"><strong>Content:</strong> {content_summary}</div>' if audit_data.get('content_summary') else ''}

        {rec_html}

        <h2>Detections ({len(detections)})</h2>
        {"<table><thead><tr><th>Attribute</th><th>Severity</th><th>Confidence</th><th>Source</th><th>Description</th></tr></thead><tbody>" + detection_rows + "</tbody></table>" if detections else '<div class="no-detections">No detections found — signal appears clean.</div>'}
    </div>
    <div class="footer">
        <p>Generated by Optic v0.1.0 — audit the perceived signal, not the person.</p>
    </div>
</body>
</html>"""

    def to_html(self, audit_data: dict[str, Any]) -> str:
        """Generate an HTML report string from audit data.

        Uses Jinja2 templating if available, falls back to inline HTML.
        """
        if HAS_JINJA2 and self._jinja_env:
            try:
                template = self._jinja_env.get_template("audit_report.html")
                return template.render(
                    audit=audit_data,
                    generated_at=datetime.now(timezone.utc).isoformat(),
                    datetime=datetime,
                )
            except Exception as e:
                logger.warning(f"Jinja2 template rendering failed: {e}. Falling back.")
        return self._default_html_report(audit_data)

    def to_html_file(
        self, audit_data: dict[str, Any], filepath: str | Path | None = None
    ) -> Path:
        """Write an HTML report to disk.

        Args:
            audit_data: Dict with audit fields.
            filepath: Output path. Auto-generated if None.

        Returns:
            Path to the written file.
        """
        _ensure_report_dir()
        if filepath is None:
            audit_id = audit_data.get("id", "unknown")
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            filepath = REPORT_DIR / f"audit_{audit_id}_{timestamp}.html"
        filepath = Path(filepath)
        filepath.write_text(self.to_html(audit_data))
        logger.info(f"HTML report written to {filepath}")
        return filepath

    # ── PDF Report ───────────────────────────────────────────────────────

    def to_pdf(self, audit_data: dict[str, Any]) -> bytes:
        """Generate a PDF report as bytes from audit data."""
        if not HAS_FPDF:
            raise RuntimeError(
                "PDF generation requires fpdf2. Install with: pip install fpdf2"
            )

        pdf = FPDF()
        pdf.add_page()

        # Header
        pdf.set_font("Helvetica", "B", 20)
        pdf.set_text_color(52, 73, 94)
        pdf.cell(0, 15, "Optic Audit Report", new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(52, 152, 219)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

        # Meta info
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(108, 117, 125)
        audit_id = audit_data.get("id", "N/A")
        source = audit_data.get("source", "N/A")
        created = audit_data.get("created_at", "N/A")
        pdf.cell(0, 6, f"Audit ID: {audit_id}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Source: {source}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Created: {created}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

        # Content summary
        content_summary = audit_data.get("content_summary", "")
        if content_summary:
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(44, 62, 80)
            pdf.cell(0, 8, "Content:", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(52, 73, 94)
            pdf.multi_cell(0, 5, content_summary)
            pdf.ln(3)

        # Score
        score = audit_data.get("score")
        if score is not None:
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(44, 62, 80)
            pdf.cell(0, 8, f"Overall Score: {score:.3f}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)

        # Detections
        detections = audit_data.get("detections", [])
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(44, 62, 80)
        pdf.cell(0, 10, f"Detections ({len(detections)})", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        severity_colors_pdf = {
            "critical": (220, 53, 69),
            "high": (253, 126, 20),
            "medium": (255, 193, 7),
            "low": (40, 167, 69),
            "info": (23, 162, 184),
        }

        if not detections:
            pdf.set_font("Helvetica", "I", 10)
            pdf.set_text_color(108, 117, 125)
            pdf.cell(0, 8, "No detections found.", new_x="LMARGIN", new_y="NEXT")
        else:
            # Table header
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_fill_color(241, 243, 245)
            pdf.set_text_color(52, 73, 94)
            col_widths = [40, 22, 22, 18, 88]
            headers = ["Attribute", "Severity", "Confidence", "Src", "Description"]
            for i, header in enumerate(headers):
                pdf.cell(col_widths[i], 7, header, border=1, fill=True, align="C")
            pdf.ln()

            # Table rows
            pdf.set_font("Helvetica", "", 8)
            for d in detections:
                sev = d.get("severity", "").lower()
                color = severity_colors_pdf.get(sev, (108, 117, 125))
                pdf.set_text_color(*color)
                pdf.cell(col_widths[0], 6, d.get("attribute", "")[:38], border=1)
                pdf.cell(col_widths[1], 6, d.get("severity", ""), border=1, align="C")
                pdf.cell(
                    col_widths[2],
                    6,
                    f"{d.get('confidence', 0):.3f}",
                    border=1,
                    align="C",
                )
                pdf.cell(col_widths[3], 6, d.get("source", "rule"), border=1, align="C")
                pdf.cell(
                    col_widths[4], 6, d.get("description", "")[:80], border=1
                )
                pdf.ln()
            pdf.set_text_color(52, 73, 94)

        # Recommendations
        recommendations = audit_data.get("recommendations", [])
        if recommendations:
            pdf.ln(5)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(44, 62, 80)
            pdf.cell(0, 8, "Recommendations:", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 10)
            for r in recommendations:
                pdf.cell(5)  # indent
                pdf.cell(0, 6, f"- {r}", new_x="LMARGIN", new_y="NEXT")

        # Footer
        pdf.ln(10)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(108, 117, 125)
        pdf.cell(
            0,
            5,
            f"Generated by Optic v0.1.0 on {datetime.now(timezone.utc).isoformat()}",
            new_x="LMARGIN",
            new_y="NEXT",
            align="C",
        )

        return bytes(pdf.output())

    def to_pdf_file(
        self, audit_data: dict[str, Any], filepath: str | Path | None = None
    ) -> Path:
        """Write a PDF report to disk.

        Args:
            audit_data: Dict with audit fields.
            filepath: Output path. Auto-generated if None.

        Returns:
            Path to the written file.
        """
        _ensure_report_dir()
        if filepath is None:
            audit_id = audit_data.get("id", "unknown")
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            filepath = REPORT_DIR / f"audit_{audit_id}_{timestamp}.pdf"
        filepath = Path(filepath)
        filepath.write_bytes(self.to_pdf(audit_data))
        logger.info(f"PDF report written to {filepath}")
        return filepath
