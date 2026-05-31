"""Interactive dashboard module for Optic — HTMX-powered submission, search, and SSE."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

# ── SSE Event Manager ───────────────────────────────────────────────────


class SSEEventManager:
    """Manages Server-Sent Events subscribers and broadcasts."""

    def __init__(self):
        self._subscribers: dict[str, asyncio.Queue] = {}
        self._counter = 0

    def subscribe(self) -> tuple[str, asyncio.Queue]:
        self._counter += 1
        sub_id = f"sub-{self._counter}"
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[sub_id] = queue
        logger.info("SSE subscriber %s connected (%d total)", sub_id, len(self._subscribers))
        return sub_id, queue

    def unsubscribe(self, sub_id: str) -> None:
        self._subscribers.pop(sub_id, None)
        logger.info("SSE subscriber %s disconnected (%d remaining)", sub_id, len(self._subscribers))

    async def broadcast(self, event: str, data: dict[str, Any]) -> None:
        payload = {"event": event, "data": json.dumps(data, default=str)}
        for sub_id, queue in list(self._subscribers.items()):
            try:
                await queue.put(payload)
            except Exception:
                self._subscribers.pop(sub_id, None)

    async def event_stream(self, request: Request) -> AsyncGenerator[dict[str, str], None]:
        sub_id, queue = self.subscribe()
        try:
            # Send initial heartbeat
            yield {"event": "connected", "data": json.dumps({"status": "ok"})}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield payload
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"event": "ping", "data": ""}
        finally:
            self.unsubscribe(sub_id)


# Singleton event manager
event_manager = SSEEventManager()


# ── HTML Templates ──────────────────────────────────────────────────────

SEVERITY_COLORS = {
    "critical": "#dc3545",
    "high": "#fd7e14",
    "medium": "#ffc107",
    "low": "#28a745",
    "info": "#17a2b8",
}

DASHBOARD_CSS = """
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: #f0f2f5;
        color: #333;
        padding: 20px;
    }
    .header {
        max-width: 1100px; margin: 0 auto 20px;
        display: flex; justify-content: space-between; align-items: center;
        flex-wrap: wrap; gap: 10px;
    }
    .header h1 { font-size: 1.6em; color: #1a1a2e; }
    .header h1 span { color: #6c757d; font-weight: 400; font-size: 0.6em; }
    .header .nav a { color: #1976d2; text-decoration: none; margin-left: 15px; font-size: 0.9em; }
    .header .nav a:hover { text-decoration: underline; }
    .container { max-width: 1100px; margin: 0 auto; background: #fff; border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); overflow: hidden; }
    table { width: 100%; border-collapse: collapse; font-size: 0.88em; }
    th { background: #f8f9fa; padding: 12px 14px; text-align: left; font-weight: 600; color: #495057; border-bottom: 2px solid #dee2e6; white-space: nowrap; }
    td { padding: 10px 14px; border-bottom: 1px solid #e9ecef; }
    tr:hover { background: #f8f9fa; }
    .audit-link { color: #1976d2; text-decoration: none; font-weight: 500; font-family: monospace; }
    .audit-link:hover { text-decoration: underline; }
    .severity-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; color: #fff; font-size: 0.78em; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
    .count-badge { display: inline-block; background: #e9ecef; color: #495057; padding: 1px 8px; border-radius: 10px; font-size: 0.85em; font-weight: 600; }
    .download-links a { display: inline-block; margin-right: 6px; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: 600; text-decoration: none; color: #fff; background: #6c757d; }
    .download-links a:hover { opacity: 0.85; }
    .download-links a.pdf-link { background: #dc3545; }
    .empty-state { text-align: center; padding: 60px 20px; color: #6c757d; }
    .empty-icon { font-size: 3em; margin-bottom: 10px; }
    .stats-bar {
        display: flex; gap: 20px; padding: 16px 20px; background: #f8f9fa;
        border-bottom: 1px solid #dee2e6; font-size: 0.88em; flex-wrap: wrap;
    }
    .stat { text-align: center; }
    .stat .num { font-size: 1.5em; font-weight: 700; color: #1a1a2e; }
    .stat .label { color: #6c757d; font-size: 0.78em; text-transform: uppercase; }
    .footer { max-width: 1100px; margin: 15px auto 0; text-align: center; color: #adb5bd; font-size: 0.8em; }

    /* New: Submission form */
    .submit-section {
        padding: 20px;
        background: #f8f9fa;
        border-bottom: 1px solid #dee2e6;
    }
    .submit-section h3 { margin-bottom: 10px; font-size: 1em; color: #495057; }
    .submit-form { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; }
    .submit-form textarea {
        flex: 1; min-width: 250px;
        padding: 10px; border: 1px solid #ced4da; border-radius: 6px;
        font-family: inherit; font-size: 0.9em; resize: vertical; min-height: 50px;
    }
    .submit-form textarea:focus { outline: none; border-color: #1976d2; box-shadow: 0 0 0 2px rgba(25,118,210,0.15); }
    .submit-form select {
        padding: 10px; border: 1px solid #ced4da; border-radius: 6px;
        font-size: 0.9em; background: #fff;
    }
    .submit-form select:focus { outline: none; border-color: #1976d2; }
    .submit-form button {
        padding: 10px 24px; background: #1976d2; color: #fff;
        border: none; border-radius: 6px; font-size: 0.9em; font-weight: 600;
        cursor: pointer; transition: background 0.2s;
    }
    .submit-form button:hover { background: #1565c0; }
    .submit-form button:disabled { opacity: 0.6; cursor: not-allowed; }
    .submit-result {
        margin-top: 10px; padding: 10px; border-radius: 6px;
        font-size: 0.85em; display: none;
    }
    .submit-result.success { display: block; background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .submit-result.error { display: block; background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    .submit-result.loading { display: block; background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }

    /* New: Search/filter bar */
    .search-bar {
        padding: 12px 20px;
        background: #fff;
        border-bottom: 1px solid #dee2e6;
        display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
    }
    .search-bar input {
        flex: 1; min-width: 180px;
        padding: 8px 12px; border: 1px solid #ced4da; border-radius: 6px;
        font-size: 0.88em;
    }
    .search-bar input:focus { outline: none; border-color: #1976d2; }
    .search-bar select {
        padding: 8px 12px; border: 1px solid #ced4da; border-radius: 6px;
        font-size: 0.88em; background: #fff;
    }
    .search-bar .filter-label { font-size: 0.85em; color: #6c757d; }

    /* New: Toast notifications for SSE */
    .toast-container {
        position: fixed; top: 20px; right: 20px; z-index: 9999;
    }
    .toast {
        padding: 12px 20px; background: #1a1a2e; color: #fff;
        border-radius: 8px; font-size: 0.85em;
        margin-bottom: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        animation: slideIn 0.3s ease-out;
    }
    @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
    .toast.success { border-left: 4px solid #28a745; }
    .toast.info { border-left: 4px solid #17a2b8; }

    /* Loading spinner for HTMX */
    .htmx-indicator { opacity: 0; transition: opacity 0.2s; }
    .htmx-request .htmx-indicator { opacity: 1; }
    .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #adb5bd; border-top-color: #1976d2; border-radius: 50%; animation: spin 0.6s linear infinite; margin-left: 8px; vertical-align: middle; }
    @keyframes spin { to { transform: rotate(360deg); } }
</style>
"""


def _build_table_rows(items: list[dict]) -> str:
    """Build HTML table rows from audit items."""
    rows = ""
    for item in items:
        sev = item["max_severity"]
        color = SEVERITY_COLORS.get(sev, "#6c757d")
        rows += f"""
        <tr>
            <td><a href="/api/audits/{item['id']}/report?format=html" class="audit-link">{item['id']}</a></td>
            <td>{item['source']}</td>
            <td>{item['content_summary'][:60]}</td>
            <td>{item['created_at']}</td>
            <td><span class="severity-badge" style="background:{color}">{sev.upper()}</span></td>
            <td><span class="count-badge">{item['detection_count']}</span></td>
            <td class="download-links">
                <a href="/api/audits/{item['id']}/report?format=html&download=true">HTML</a>
                <a href="/api/audits/{item['id']}/report?format=json&download=true">JSON</a>
                <a href="/api/audits/{item['id']}/report?format=pdf&download=true" class="pdf-link">PDF</a>
            </td>
        </tr>"""
    return rows


def _build_stats_bar(items: list[dict]) -> str:
    """Build stats bar HTML."""
    total = len(items)
    high_sev = sum(1 for i in items if i["max_severity"] in ("critical", "high"))
    total_detections = sum(i["detection_count"] for i in items)
    return f"""
    <div class="stats-bar" id="stats-bar">
        <div class="stat">
            <div class="num" id="stat-total">{total}</div>
            <div class="label">Total Audits</div>
        </div>
        <div class="stat">
            <div class="num" id="stat-high">{high_sev}</div>
            <div class="label">High Severity</div>
        </div>
        <div class="stat">
            <div class="num" id="stat-detections">{total_detections}</div>
            <div class="label">Total Detections</div>
        </div>
    </div>"""


def _build_table(items: list[dict]) -> str:
    """Build the full table HTML (rows wrapped in table structure)."""
    rows = _build_table_rows(items)
    if not rows:
        return """<div class="empty-state" id="table-body">
            <div class="empty-icon">📋</div>
            <h3>No audits yet</h3>
            <p>Submit an audit using the form above to see results here.</p>
        </div>"""
    return f"""<table id="audit-table" hx-swap-oob="true">
        <thead>
            <tr>
                <th>Audit ID</th><th>Source</th><th>Content</th>
                <th>Timestamp</th><th>Severity</th><th>Detections</th><th>Download</th>
            </tr>
        </thead>
        <tbody id="table-body">{rows}</tbody>
    </table>"""


def _process_items(audit_history: dict[str, dict]) -> list[dict]:
    """Convert audit history dict to sorted list of items with severity info."""
    items = []
    for aid, ah in sorted(
        audit_history.items(),
        key=lambda x: x[1].get("created_at", ""),
        reverse=True,
    ):
        detections = ah.get("detections", [])
        max_severity = "info"
        severity_order_rev = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        for d in detections:
            s = d.get("severity", "info").lower()
            if severity_order_rev.get(s, 5) < severity_order_rev.get(max_severity, 5):
                max_severity = s

        items.append({
            "id": aid,
            "source": ah.get("source", ""),
            "content_summary": ah.get("content_summary", "")[:100],
            "created_at": ah.get("created_at", ""),
            "detection_count": len(detections),
            "max_severity": max_severity,
        })
    return items


# ── Router ──────────────────────────────────────────────────────────────


def create_dashboard_router(audit_history: dict, auditor_factory, ml_detector=None) -> APIRouter:
    """Create a router with interactive dashboard endpoints.

    Args:
        audit_history: In-memory dict of audit results (mutable, shared with app)
        auditor_factory: Callable that returns a SignalAuditor
        ml_detector: Optional MLDetector instance
    """
    router = APIRouter(tags=["dashboard"])
    ev_mgr = event_manager

    @router.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request):
        """Interactive dashboard with HTMX-powered submission and search."""
        items = _process_items(audit_history)
        table_html = _build_table_items(items)
        stats_html = _build_stats_bar(items)

        empty_state = ""
        if not items:
            empty_state = """<div class="empty-state" id="table-body">
                <div class="empty-icon">📋</div>
                <h3>No audits yet</h3>
                <p>Submit an audit using the form above to see results here.</p>
            </div>"""

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Optic Dashboard</title>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    {DASHBOARD_CSS}
</head>
<body hx-headers='{{"X-Requested-With": "XMLHttpRequest"}}'>
    <div class="toast-container" id="toast-container"></div>

    <div class="header">
        <h1>🔍 Optic <span>Dashboard</span></h1>
        <div class="nav">
            <a href="/docs">API Docs</a>
            <a href="/health" hx-boost="false">Health</a>
        </div>
    </div>

    <div class="container">
        <!-- Submission form -->
        <div class="submit-section">
            <h3>📝 Submit Content for Audit</h3>
            <form class="submit-form" hx-post="/dashboard/submit"
                  hx-target="#submit-result" hx-swap="innerHTML"
                  hx-indicator="#submit-spinner">
                <textarea name="content" placeholder="Enter text to audit for bias, anomalies, or threshold violations..." required></textarea>
                <select name="source">
                    <option value="text">Text</option>
                    <option value="social_media">Social Media</option>
                    <option value="news">News</option>
                    <option value="document">Document</option>
                    <option value="other">Other</option>
                </select>
                <button type="submit">
                    Audit
                    <span id="submit-spinner" class="htmx-indicator"><span class="spinner"></span></span>
                </button>
            </form>
            <div id="submit-result"></div>
        </div>

        <!-- Stats bar -->
        {stats_html}

        <!-- Search/filter bar -->
        <div class="search-bar">
            <span class="filter-label">🔍</span>
            <input type="text" id="search-input" name="q" placeholder="Search by content, ID, or source..."
                   hx-get="/dashboard/search" hx-trigger="keyup changed delay:300ms"
                   hx-target="#table-body" hx-swap="innerHTML"
                   hx-indicator="#search-spinner">
            <select name="severity" id="severity-filter"
                    hx-get="/dashboard/search" hx-trigger="change"
                    hx-target="#table-body" hx-swap="innerHTML"
                    hx-include="#search-input">
                <option value="">All Severities</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
                <option value="info">Info</option>
            </select>
            <span id="search-spinner" class="htmx-indicator"><span class="spinner"></span></span>
        </div>

        <!-- Audit history table -->
        <div id="table-container">
            {f'''<table id="audit-table">
                <thead>
                    <tr>
                        <th>Audit ID</th><th>Source</th><th>Content</th>
                        <th>Timestamp</th><th>Severity</th><th>Detections</th><th>Download</th>
                    </tr>
                </thead>
                <tbody id="table-body">{table_html}</tbody>
            </table>''' if items else empty_state}
        </div>
    </div>

    <div class="footer">
        Generated by Optic v0.1.0 — Audit the perceived signal, not the person.
    </div>

    <!-- SSE for live updates -->
    <script>
        (function() {{
            const evtSource = new EventSource('/dashboard/events');

            evtSource.addEventListener('connected', function(e) {{
                console.log('SSE connected');
            }});

            evtSource.addEventListener('new_audit', function(e) {{
                const data = JSON.parse(e.data);
                showToast(data.summary || 'New audit completed', 'success');

                // Reload the table and stats via HTMX
                htmx.ajax('GET', '/dashboard/search', {{
                    target: '#table-body',
                    swap: 'innerHTML'
                }});
                htmx.ajax('GET', '/dashboard/stats', {{
                    target: '#stats-bar',
                    swap: 'outerHTML'
                }});
            }});

            evtSource.addEventListener('ping', function(e) {{
                // Keepalive, do nothing
            }});

            function showToast(message, type) {{
                const container = document.getElementById('toast-container');
                const toast = document.createElement('div');
                toast.className = 'toast ' + (type || 'info');
                toast.textContent = message;
                container.appendChild(toast);
                setTimeout(function() {{ toast.remove(); }}, 4000);
            }}
        }})();
    </script>
</body>
</html>"""
        return HTMLResponse(content=html_content)

    @router.post("/dashboard/submit")
    async def dashboard_submit(
        content: str = Form(...),
        source: str = Form("text"),
    ):
        """Submit content for auditing via the dashboard form (HTMX)."""
        from optic.api.models import AuditSingleRequest

        auditor = auditor_factory()
        request = AuditSingleRequest(content=content, source=source)

        try:
            result = auditor.audit_single(request)

            # Store in audit history
            from datetime import datetime, timezone
            audit_id = result.audit_id
            audit_hash = {
                "id": audit_id,
                "source": source,
                "content_summary": content[:200],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "detections": [
                    {
                        "attribute": d.attribute,
                        "value": d.value,
                        "confidence": d.confidence,
                        "severity": d.severity,
                        "description": d.description,
                        "source": getattr(d, 'source', 'rule'),
                    }
                    for d in (result.detections or [])
                ],
                "metadata": {},
            }

            # Add ML detections if available
            if ml_detector and hasattr(result, 'ml_detections') and result.ml_detections:
                for ml_d in result.ml_detections:
                    audit_hash["detections"].append({
                        "attribute": f"ml_{ml_d.attribute}",
                        "value": ml_d.value,
                        "confidence": ml_d.confidence,
                        "severity": ml_d.severity,
                        "description": ml_d.description,
                        "source": "ml",
                    })

            audit_history[audit_id] = audit_hash

            # Broadcast via SSE
            num_detections = len(audit_hash["detections"])
            max_sev = "info"
            sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
            for d in audit_hash["detections"]:
                s = d.get("severity", "info").lower()
                if sev_order.get(s, 5) < sev_order.get(max_sev, 5):
                    max_sev = s

            await ev_mgr.broadcast("new_audit", {
                "audit_id": audit_id,
                "summary": f"Audit {audit_id[:8]} — {num_detections} detection(s), severity: {max_sev}",
                "severity": max_sev,
            })

            # Return result HTML (HTMX swap target)
            return HTMLResponse(f"""<div class="submit-result success">
                ✅ <strong>Audit complete!</strong>
                ID: <code>{audit_id}</code> |
                {num_detections} detection(s) found |
                <a href="/api/audits/{audit_id}/report?format=html">View Report</a>
            </div>""")

        except Exception as e:
            logger.exception("Dashboard audit submission failed")
            return HTMLResponse(f"""<div class="submit-result error">
                ❌ Audit failed: {str(e)}
            </div>""")

    @router.get("/dashboard/search")
    async def dashboard_search(
        q: str = Query(""),
        severity: str = Query(""),
    ):
        """Search audit history and return HTML table rows (HTMX)."""
        try:
            items = _process_items(audit_history)

            # Apply filters
            if q:
                q_lower = q.lower()
                items = [
                    i for i in items
                    if q_lower in i["id"].lower()
                    or q_lower in i["content_summary"].lower()
                    or q_lower in i["source"].lower()
                ]

            if severity:
                items = [i for i in items if i["max_severity"] == severity.lower()]

            if not items:
                return HTMLResponse("""<tr><td colspan="7" style="text-align:center;padding:40px;color:#6c757d;">
                    🔍 No matching audits found.
                </td></tr>""")

            rows = _build_table_rows(items)
            return HTMLResponse(rows)
        except Exception as e:
            logger.exception("Dashboard search failed")
            return HTMLResponse(f"""<tr><td colspan="7" style="text-align:center;padding:40px;color:#dc3545;">
                ❌ Search failed: {str(e)}
            </td></tr>""", status_code=500)

    @router.get("/dashboard/stats")
    async def dashboard_stats():
        """Return stats bar HTML (for HTMX swap)."""
        try:
            items = _process_items(audit_history)
            return HTMLResponse(_build_stats_bar(items))
        except Exception as e:
            logger.exception("Dashboard stats failed")
            return HTMLResponse(f"""<div class="stats-bar" id="stats-bar">
                <div class="stat"><div class="num">0</div><div class="label">Error loading stats</div></div>
            </div>""", status_code=500)

    @router.get("/dashboard/events")
    async def dashboard_events(request: Request):
        """SSE endpoint for live audit notifications."""
        try:
            return EventSourceResponse(ev_mgr.event_stream(request))
        except Exception as e:
            logger.exception("SSE event stream failed")
            return HTMLResponse(f"SSE connection error: {str(e)}", status_code=500)

    return router
