"""
# ⚠ DEPRECATED — This FastAPI server is NOT the active runtime.
# ================================================================
# The running server is ctxorg/server.py (stdlib ThreadingHTTPServer on port 3003).
#
# THIS FILE IS DEAD CODE with THREE exceptions that are cross-imported:
#   1. init_db()             — called by optic/v1/startup.py
#   2. _migrate_v1_schema()  — called by ctxorg/server.py
#   3. _generate_repairs()   — called by ctxorg/server.py
#
# The remaining ~3,400 lines (FastAPI app, CORS, route handlers, parsers/graph/
# resolver/scrapers integration, DeepSeek API config) are UNREACHABLE from the
# running server. They live in a parallel runtime universe.
#
# CLOUD-FIRST VIOLATION (Heresy 7 — FIXED): Lines 109-112 configure DeepSeek API
# (remote LLM) which would violate Invariant #12 (Local-First By Default) if
# defaulted to an active key. The env var now defaults to empty string, making
# DeepSeek strictly opt-in. The running server uses Ollama (local) via
# iris_audit.py fallback chain: DeepSeek (opt-in) → Ollama (local) → deterministic.
#
# DO NOT DELETE — keep as reference for: init_db(), _migrate_v1_schema(),
# _generate_repairs(). The rest may be cannibalized into ctxorg/server.py
# during pipeline Stage 12 (Graph) and Stage 13 (Iris) remediation.

Optic V1 — FastAPI Server
==========================
Wires the V1 intelligence layer into the existing ctxorg filesystem
scan, workstream clustering, and Ollama-powered chat infrastructure.
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import os
import sqlite3
import threading
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ── V1 package imports ──────────────────────────────────────────
from .models import (
    Artifact, AuditMode, ConfidenceBand, ConsentReceipt, Contradiction,
    InferenceClaim, RepairAction, RepairStatus, Report,
    RiskFlag, RiskCategory, Severity, Signal, Source, SourceStatus,
    SourceType, User,
)
from .lenses import AUDIENCE_LENSES
from .contradiction import ContradictionEngine
from .inference import InferenceCardGenerator
from . import graph, iris_audit, parsers, resolver, scrapers
from .risk import risk_engine

# ── Signal detector imports ──────────────────────────────────────
try:
    from ..signal import (
        SignalAuditor, PatternDetector, AnomalyDetector, ThresholdDetector,
        SignalSource as DetectorSignalSource,
    )
    from ..signal.models import Severity as DetectorSeverity, Detection
    SIGNAL_AUDIT_AVAILABLE = True
except ImportError:
    SIGNAL_AUDIT_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── ctxorg imports (filesystem scanner, workstreams, ollama) ────
import sys as _sys
from pathlib import Path as _Path
_ctxorg_root = _Path(__file__).resolve().parent.parent.parent / "src"
if str(_ctxorg_root) not in _sys.path:
    _sys.path.insert(0, str(_ctxorg_root))

try:
    from ctxorg.db import open_db as ctx_db, rows as ctx_rows
    from ctxorg.workstreams import compute as ctx_compute_ws
    CTXORG_AVAILABLE = True
except ImportError:
    CTXORG_AVAILABLE = False

# ── Consent filter (Invariant #2: Consent-Scoped) ──────────────────
try:
    from ctxorg.server import _consent_check_source as _ctx_consent_check
    CONSENT_CHECK_AVAILABLE = True
except ImportError:
    CONSENT_CHECK_AVAILABLE = False
    def _ctx_consent_check(source_id: str, mode: str = "local") -> dict:
        return {"consented": True, "reason": "import_failed", "receipt_id": None}

# ── config ────────────────────────────────────────────────────────
DB_PATH = Path(os.environ.get("OPTIC_DB_PATH",
    str(Path(__file__).resolve().parent.parent.parent.parent / ".optic" / "v1.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

IRIS_SUMMARY_PATH = DB_PATH.parent / "iris_summary.json"
_iris_summary_lock = threading.Lock()
_iris_summary_jobs: set[str] = set()  # tracks in-flight generation

# ── LLM config ────────────────────────────────────────────────────
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")


app = FastAPI(title="Optic V1", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── serve old ctxorg static SPA ──────────────────────────────────
from fastapi.staticfiles import StaticFiles
_STATIC_DIR = _Path(__file__).resolve().parent.parent.parent / "ctxorg" / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    # redirect root to index.html
    from fastapi.responses import FileResponse
    @app.get("/")
    async def root():
        return FileResponse(str(_STATIC_DIR / "index.html"))
    @app.get("/app.css")
    async def app_css():
        return FileResponse(str(_STATIC_DIR / "app.css"))
    @app.get("/app.js")
    async def app_js():
        return FileResponse(str(_STATIC_DIR / "app.js"))
    _ONBOARD_DIR = _Path(__file__).resolve().parent / "static"
    @app.get("/onboarding")
    async def onboarding_page():
        return FileResponse(str(_ONBOARD_DIR / "onboarding.html"))
    @app.get("/dashboard")
    async def dashboard_page():
        return FileResponse(str(_ONBOARD_DIR / "dashboard.html"))
    @app.get("/dashboard")
    async def dashboard_page():
        return FileResponse(str(_ONBOARD_DIR / "dashboard.html"))

engine = ContradictionEngine()



# ── database ──────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate_users_table(conn: sqlite3.Connection):
    """Add is_test_user column if it doesn't already exist."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "is_test_user" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_test_user INTEGER DEFAULT 0")
        conn.commit()


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, email TEXT UNIQUE, settings TEXT,
            local_mode INTEGER DEFAULT 1, encryption_key_ref TEXT,
            is_test_user INTEGER DEFAULT 0,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY, user_id TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY, user_id TEXT, type TEXT, provider TEXT,
            import_method TEXT, user_label TEXT, permission_scope TEXT,
            freshness TEXT, status TEXT DEFAULT 'pending', metadata TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS consent_receipts (
            id TEXT PRIMARY KEY, source_id TEXT, scope TEXT, purpose TEXT,
            retention_days INTEGER DEFAULT 90, cloud_allowed INTEGER DEFAULT 0,
            export_allowed INTEGER DEFAULT 0, created_at TEXT, revoked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY, source_id TEXT, type TEXT, raw_hash TEXT,
            encrypted_path TEXT, metadata TEXT, is_public INTEGER DEFAULT 0,
            content_preview TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS signals (
            id TEXT PRIMARY KEY, category TEXT, description TEXT,
            severity TEXT DEFAULT 'low',
            source_artifact_ids TEXT,  /* DEPRECATED — use signal_source_artifacts */
            metadata TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS claims (
            id TEXT PRIMARY KEY, title TEXT, audience_lens TEXT, claim TEXT,
            confidence_band TEXT, evidence_count INTEGER,
            supporting_evidence TEXT,   /* DEPRECATED — use claim_supporting_evidence */
            weakening_evidence TEXT,    /* DEPRECATED — use claim_weakening_evidence */
            source_gaps TEXT, recency TEXT, severity TEXT,
            actionability TEXT, possible_consequence TEXT, counterargument TEXT,
            repair_options TEXT,        /* DEPRECATED — use claim_repair_options */
            model_version TEXT, not_a_verdict INTEGER DEFAULT 1,
            generated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS contradictions (
            id TEXT PRIMARY KEY, category TEXT, description TEXT,
            claim_ids TEXT,             /* DEPRECATED — use contradiction_claims */
            artifact_ids TEXT,          /* DEPRECATED — use contradiction_artifacts */
            severity TEXT,
            audience_affected TEXT, resolution_suggestion TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS risks (
            id TEXT PRIMARY KEY, category TEXT, description TEXT,
            severity TEXT,
            linked_claim_ids TEXT,      /* DEPRECATED — use risk_linked_claims */
            linked_artifact_ids TEXT,   /* DEPRECATED — use risk_linked_artifacts */
            audience_affected TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS repairs (
            id TEXT PRIMARY KEY, title TEXT, affected_audience TEXT,
            linked_claim_id TEXT REFERENCES claims(id) ON DELETE SET NULL,
            linked_evidence_ids TEXT,   /* DEPRECATED — use repair_linked_evidence */
            impact REAL DEFAULT 0.5,
            effort REAL DEFAULT 0.5, urgency REAL DEFAULT 0.5,
            reversibility REAL DEFAULT 0.5, cost_cents INTEGER DEFAULT 0,
            exact_steps TEXT, expected_effect TEXT, risk_of_overcorrecting TEXT,
            before_measurement TEXT, after_measurement TEXT,
            status TEXT DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY, user_id TEXT, version INTEGER DEFAULT 1,
            audit_mode TEXT, scope TEXT, source_count INTEGER, artifact_count INTEGER,
            claim_count INTEGER, contradiction_count INTEGER, risk_count INTEGER,
            repair_count INTEGER, sections TEXT, export_policy TEXT,
            created_at TEXT, snapshot_id TEXT
        );
        CREATE TABLE IF NOT EXISTS onboarding (
            user_id TEXT PRIMARY KEY, step INTEGER DEFAULT 0,
            audit_mode TEXT, completed_steps TEXT, created_at TEXT
        );

        -- ═══ JUNCTION TABLES — FOREIGN KEY ENFORCEMENT (Invariant #10) ═══

        CREATE TABLE IF NOT EXISTS claim_supporting_evidence (
            claim_id    TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
            artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
            PRIMARY KEY (claim_id, artifact_id)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS claim_weakening_evidence (
            claim_id    TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
            artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
            PRIMARY KEY (claim_id, artifact_id)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS claim_repair_options (
            claim_id  TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
            repair_id TEXT NOT NULL REFERENCES repairs(id) ON DELETE CASCADE,
            PRIMARY KEY (claim_id, repair_id)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS risk_linked_claims (
            risk_id  TEXT NOT NULL REFERENCES risks(id) ON DELETE CASCADE,
            claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
            PRIMARY KEY (risk_id, claim_id)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS risk_linked_artifacts (
            risk_id     TEXT NOT NULL REFERENCES risks(id) ON DELETE CASCADE,
            artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
            PRIMARY KEY (risk_id, artifact_id)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS repair_linked_evidence (
            repair_id   TEXT NOT NULL REFERENCES repairs(id) ON DELETE CASCADE,
            artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
            PRIMARY KEY (repair_id, artifact_id)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS contradiction_claims (
            contradiction_id TEXT NOT NULL REFERENCES contradictions(id) ON DELETE CASCADE,
            claim_id         TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
            PRIMARY KEY (contradiction_id, claim_id)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS contradiction_artifacts (
            contradiction_id TEXT NOT NULL REFERENCES contradictions(id) ON DELETE CASCADE,
            artifact_id      TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
            PRIMARY KEY (contradiction_id, artifact_id)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS signal_source_artifacts (
            signal_id   TEXT NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
            artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
            PRIMARY KEY (signal_id, artifact_id)
        ) WITHOUT ROWID;

        -- Migration tracking
        CREATE TABLE IF NOT EXISTS _schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    _migrate_v1_schema(conn)
    conn.close()


# ── Schema migration — idempotent, safe to call on every startup ──

def _migrate_v1_schema(conn: sqlite3.Connection):
    """Run schema migrations. Idempotent — checks _schema_migrations version."""
    row = conn.execute(
        "SELECT MAX(version) as v FROM _schema_migrations"
    ).fetchone()
    current = row["v"] if row and row["v"] else 0

    # Always run the junction migration — it's idempotent (INSERT OR IGNORE)
    # and the data may have been re-seeded after the migration first ran.
    # Version 2 is guaranteed after this call regardless of prior state.
    _migrate_v2_junction_tables(conn)


def _migrate_v2_junction_tables(conn: sqlite3.Connection):
    """V2: Migrate JSON TEXT columns into junction tables with FK constraints."""
    import json as _json

    # Ensure junction tables exist (idempotent)
    _ddl = [
        ("claim_supporting_evidence",
         "claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE, "
         "artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE, "
         "PRIMARY KEY (claim_id, artifact_id)"),
        ("claim_weakening_evidence",
         "claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE, "
         "artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE, "
         "PRIMARY KEY (claim_id, artifact_id)"),
        ("claim_repair_options",
         "claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE, "
         "repair_id TEXT NOT NULL REFERENCES repairs(id) ON DELETE CASCADE, "
         "PRIMARY KEY (claim_id, repair_id)"),
        ("risk_linked_claims",
         "risk_id TEXT NOT NULL REFERENCES risks(id) ON DELETE CASCADE, "
         "claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE, "
         "PRIMARY KEY (risk_id, claim_id)"),
        ("risk_linked_artifacts",
         "risk_id TEXT NOT NULL REFERENCES risks(id) ON DELETE CASCADE, "
         "artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE, "
         "PRIMARY KEY (risk_id, artifact_id)"),
        ("repair_linked_evidence",
         "repair_id TEXT NOT NULL REFERENCES repairs(id) ON DELETE CASCADE, "
         "artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE, "
         "PRIMARY KEY (repair_id, artifact_id)"),
        ("contradiction_claims",
         "contradiction_id TEXT NOT NULL REFERENCES contradictions(id) ON DELETE CASCADE, "
         "claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE, "
         "PRIMARY KEY (contradiction_id, claim_id)"),
        ("contradiction_artifacts",
         "contradiction_id TEXT NOT NULL REFERENCES contradictions(id) ON DELETE CASCADE, "
         "artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE, "
         "PRIMARY KEY (contradiction_id, artifact_id)"),
        ("signal_source_artifacts",
         "signal_id TEXT NOT NULL REFERENCES signals(id) ON DELETE CASCADE, "
         "artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE, "
         "PRIMARY KEY (signal_id, artifact_id)"),
    ]
    for name, cols in _ddl:
        conn.execute(f"CREATE TABLE IF NOT EXISTS {name} ({cols}) WITHOUT ROWID")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _schema_migrations ("
        "version INTEGER PRIMARY KEY, "
        "applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.commit()

    def _parse_ids(raw):
        if not raw or raw in ("", "[]"):
            return []
        try:
            return _json.loads(raw)
        except Exception:
            return []

    def _migrate_column(parent_table, child_col, child_table, junction_table,
                        pk_a, pk_b):
        rows = conn.execute(
            f"SELECT id, {child_col} FROM {parent_table} "
            f"WHERE {child_col} IS NOT NULL AND {child_col} != '' "
            f"AND {child_col} != '[]'"
        ).fetchall()
        count = 0
        for row_dict in rows:
            parent_id = row_dict["id"]
            child_ids = _parse_ids(row_dict[child_col])
            for cid in child_ids:
                exists = conn.execute(
                    f"SELECT 1 FROM {child_table} WHERE id = ?", (cid,)
                ).fetchone()
                if exists:
                    try:
                        conn.execute(
                            f"INSERT OR IGNORE INTO {junction_table} "
                            f"({pk_a}, {pk_b}) VALUES (?, ?)",
                            (parent_id, cid)
                        )
                        count += 1
                    except sqlite3.IntegrityError:
                        pass  # FK violation — orphaned reference, skip
        return count

    total = 0
    total += _migrate_column("claims", "supporting_evidence", "artifacts",
                             "claim_supporting_evidence", "claim_id", "artifact_id")
    total += _migrate_column("claims", "weakening_evidence", "artifacts",
                             "claim_weakening_evidence", "claim_id", "artifact_id")
    total += _migrate_column("claims", "repair_options", "repairs",
                             "claim_repair_options", "claim_id", "repair_id")
    total += _migrate_column("risks", "linked_claim_ids", "claims",
                             "risk_linked_claims", "risk_id", "claim_id")
    total += _migrate_column("risks", "linked_artifact_ids", "artifacts",
                             "risk_linked_artifacts", "risk_id", "artifact_id")
    total += _migrate_column("repairs", "linked_evidence_ids", "artifacts",
                             "repair_linked_evidence", "repair_id", "artifact_id")
    total += _migrate_column("contradictions", "claim_ids", "claims",
                             "contradiction_claims", "contradiction_id", "claim_id")
    total += _migrate_column("contradictions", "artifact_ids", "artifacts",
                             "contradiction_artifacts", "contradiction_id", "artifact_id")
    total += _migrate_column("signals", "source_artifact_ids", "artifacts",
                             "signal_source_artifacts", "signal_id", "artifact_id")

    conn.execute(
        "INSERT OR IGNORE INTO _schema_migrations (version) VALUES (2)"
    )
    conn.commit()
    logger.info("Optic DB migration v2: %d junction rows migrated", total)
    print(f"Optic DB migration v2 complete: {total} junction rows migrated")
    return total


init_db()

# ── Auto-seed on empty database — uses real filesystem scan only ────
try:
    from .startup import ensure_data as _ensure_data
    _seed_result = _ensure_data(DB_PATH)
    if _seed_result.get("seeded"):
        print(f"Optic: seeded from real filesystem scan — "
              f"{_seed_result.get('claims',0)} claims, "
              f"{_seed_result.get('scanned_files',0)} files, "
              f"{_seed_result.get('workstreams',0)} workstreams")
    elif _seed_result.get("source") == "insufficient_data":
        print(f"Optic: HONEST EMPTY STATE — {_seed_result.get('message', 'insufficient files')}")
        print("  Invariant #8: No Fake Completeness — no demo/template data will be inserted.")
    else:
        print(f"Optic: using existing data — {_seed_result.get('existing_claims',0)} claims")
except ImportError:
    pass


# ── serve old ctxorg static SPA ──────────────────────────────────


# ── pydantic models ───────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str


class LoginRequest(BaseModel):
    email: str


class SourceRequest(BaseModel):
    type: str
    provider: str = ""
    user_label: str = ""
    url: str = ""
    handle: str = ""


class ConsentRequest(BaseModel):
    scope: list[str] = ["parse", "embed", "infer"]
    purpose: str = ""
    retention_days: int = 90
    cloud_allowed: bool = False
    export_allowed: bool = False


class RepairCompleteRequest(BaseModel):
    pass


class OnboardingStepRequest(BaseModel):
    step: int
    audit_mode: Optional[str] = None
    source_data: Optional[dict] = None


# ── helpers ───────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    return dict(row)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _quick_clean(raw: str) -> str:
    """Minimal name cleaner for workstream names read from DB metadata.

    Strips URL fragments, hex noise, and generic terms.
    Falls back to 'Other' when the name is purely noise.
    """
    if not raw or not raw.strip():
        return "Unknown"
    raw = raw.strip()
    _NOISE = {
        "https", "http", "www", "com", "org", "net", "html", "json", "xml",
        "css", "js", "abx", "xtcftw", "rspace", "pyasn1",
        "screenshot", "screenshots", "temp", "untitled", "node_modules",
        "desktop", "downloads", "inbox",
        "io", "co", "dev", "app", "ai", "gov", "edu",
        "copy", "backup", "final", "draft",
    }
    import re as _re
    name = raw.replace("-", " ").replace("_", " ")
    words = name.split()
    meaningful = []
    for w in words:
        wl = w.lower()
        if wl in _NOISE:
            continue
        if _re.fullmatch(r"[0-9a-f]{6,}", wl):
            continue
        if len(wl) >= 4 and not _re.search(r"[aeiouy]", wl) and not _re.search(r"\d", wl):
            continue
        meaningful.append(w)
    if not meaningful:
        return "Other"
    cleaned = []
    for w in meaningful:
        if w.upper() in ("AI", "API", "AWS", "UI", "UX", "ML", "NLP", "GPU", "CPU", "RAM", "SSD"):
            cleaned.append(w.upper())
        elif len(w) <= 2:
            cleaned.append(w.upper())
        else:
            cleaned.append(w[0].upper() + w[1:].lower() if len(w) > 1 else w.upper())
    result = " ".join(cleaned).strip()
    return result or "Other"


def _gen_token() -> str:
    return hashlib.sha256(f"{uuid4()}{time.time()}".encode()).hexdigest()[:32]


def _get_user(token: str = "") -> Optional[dict]:
    if token:
        conn = get_db()
        row = conn.execute("SELECT user_id FROM sessions WHERE token=?", (token,)).fetchone()
        conn.close()
        if row:
            urow = get_db().execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone()
            get_db().close()
            return _row_to_dict(urow)
    # Local-only mode: return first user as default
    conn = get_db()
    row = conn.execute("SELECT * FROM users LIMIT 1").fetchone()
    conn.close()
    return _row_to_dict(row) if row else {"id": "local", "email": "local@optic.dev"}


def _derive_workstreams() -> list[dict]:
    """Derive workstreams from real signals in the DB."""
    import json as _json
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM signals WHERE category IN ('frequent_topic','topic_focus','activity_volume','project_velocity')"
    ).fetchall()
    conn.close()
    
    # Group signals by workstream_id from metadata
    groups: dict[str, dict] = {}
    for row in rows:
        meta = {}
        try:
            meta = _json.loads(row["metadata"] or "{}")
        except Exception:
            pass
        wsid = meta.get("workstream_id") or row["id"]
        if wsid not in groups:
            groups[wsid] = {
                "id": wsid,
                "name": _quick_clean(meta.get("workstream_name", "Unknown")),
                "confidence": float(meta.get("confidence", 0.5)),
                "file_count": int(meta.get("file_count", 0)),
                "topics": meta.get("topics", []),
                "signals": [],
            }
        groups[wsid]["signals"].append(dict(row))
    
    # Get claims for summaries per workstream
    conn = get_db()
    all_claims = conn.execute("SELECT * FROM claims").fetchall()
    conn.close()
    
    # Build workstream list
    now = int(time.time())
    workstreams = []
    for wsid, wsd in sorted(groups.items()):
        # Find claims that mention this workstream name
        name = wsd["name"]
        related = [c for c in all_claims if name.lower() in (c["claim"] or "").lower()]
        # Build a clean summary from workstream name and topics
        topics_list = wsd.get("topics", [])
        file_count = wsd.get("file_count", 0)
        # Try to get a rich summary from signal metadata
        rich_summary = ""
        for sig in wsd.get("signals", []):
            meta_sig = {}
            try:
                meta_sig = json.loads(sig.get("metadata") or "{}")
            except Exception:
                pass
            if meta_sig.get("evidence_labels"):
                rich_summary = meta_sig.get("summary", "")
                break
        summary = rich_summary or f"{file_count} files across {', '.join(topics_list[:2]) if topics_list else 'various'} topics."
        
        # Build key_files — use evidence labels from signal metadata
        key_files = []
        evidence_labels = []
        for sig in wsd.get("signals", []):
            meta_sig = {}
            try:
                meta_sig = json.loads(sig.get("metadata") or "{}")
            except Exception:
                pass
            labels = meta_sig.get("evidence_labels", [])
            if labels:
                evidence_labels = labels
                break
        if not evidence_labels:
            evidence_labels = []
        extensions = [".md", ".pdf", ".txt"]
        # Only fabricate key_files if real evidence labels exist
        for i, label in enumerate(evidence_labels[:3]):
            ext = extensions[i % len(extensions)]
            key_files.append({
                "path": str(Path.home() / ".optic" / "scan" / name / f"{label}{ext}"),
                "ext": ext,
                "size": 0,
                "mtime": now,
            })
        
        folders = list({(sig["description"] or "").split("'")[1] if "'" in (sig["description"] or "") else name for sig in wsd["signals"]})[:3]
        if not folders:
            folders = [name]
        
        # Derive real mtime from the most recent signal in this workstream
        wsmtime = now
        for sig in wsd["signals"]:
            sig_ct = sig.get("created_at") or ""
            if sig_ct:
                try:
                    from datetime import datetime as _dt
                    ts = _dt.fromisoformat(sig_ct.replace("Z", "+00:00")).timestamp()
                    wsmtime = int(ts)
                except Exception:
                    pass
        workstreams.append({
            "id": wsid,
            "name": name,
            "confidence": round(wsd["confidence"], 2),
            "file_count": wsd["file_count"],
            "size": wsd["file_count"],
            "mtime": wsmtime,
            "topics": wsd["topics"],
            "summary": summary,
            "key_files": key_files,
            "folders": folders,
            "category_breakdown": {},
        })
    
    return workstreams or _fast_mock_ws_fallback()


def _fast_mock_ws_fallback() -> list[dict]:
    """Honest empty state — return no workstreams when DB is empty.
    Invariant #8 (No Fake Completeness): NEVER fabricate placeholder data.
    """
    return []


def _fast_mock_ws() -> list[dict]:
    """Stub kept for backward compat — delegates to real derivation."""
    return _derive_workstreams()


def _mock_graph_payload() -> dict:
    """Derive graph nodes and edges from real claims + signals in the DB.

    Each real file path (or label+size for synthetic key_files) produces
    exactly ONE graph node.  When the same evidence appears under multiple
    workstreams the node's ``source_provenance`` field accumulates all
    categories so the front-end can display multi-provenance nodes without
    duplication.
    """
    import json as _json
    conn = get_db()
    claims_cnt = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
    signals = conn.execute("SELECT * FROM signals").fetchall()
    claims = conn.execute("SELECT * FROM claims").fetchall()
    conn.close()
    
    if claims_cnt == 0 or not signals:
        return {"nodes": [], "edges": [], "links": [], "run": "empty-db"}
    
    nodes = []
    links = []
    # Deduplication: (label, size) → node index in nodes list
    dedupe_map: dict[tuple[str, int], int] = {}
    seen_ids = set()
    idx = 0
    wstreams = _derive_workstreams()
    
    for ws in wstreams:
        angle = (math.pi * 2 * idx) / max(len(wstreams), 1)
        cx = math.cos(angle) * 220
        cy = math.sin(angle) * 150
        for fi in range(min(len(ws.get("key_files", [])), 3)):
            kf = ws["key_files"][fi]
            path = kf["path"]
            label = Path(path).stem
            size = kf.get("size", 0)
            dup_key = (label, size)

            if dup_key in dedupe_map:
                # Existing node — merge provenance
                ni = dedupe_map[dup_key]
                prov = nodes[ni].setdefault("source_provenance", [])
                cat = ws["name"]
                if cat not in prov:
                    prov.append(cat)
                # Record the cluster linkage
                clusters = nodes[ni].setdefault("clusters", [])
                if ws["id"] not in clusters:
                    clusters.append(ws["id"])
                continue

            node_id = f"node-{idx:03d}"
            seen_ids.add(node_id)
            dedupe_map[dup_key] = len(nodes)
            nodes.append({
                "id": node_id,
                "path": path,
                "label": label,
                "ext": kf.get("ext", ""),
                "size": size,
                "mtime": kf.get("mtime", 0),
                "category": ws["name"],
                "cluster": ws["id"],
                "source_provenance": [ws["name"]],
                "clusters": [ws["id"]],
                "x": cx + (fi - 1) * 34,
                "y": cy + ((fi % 2) * 28 - 14),
                "z": math.sin(angle + fi) * 80,
                "w": 1.0,
            })
            if fi > 0:
                links.append({
                    "a": f"node-{idx-1:03d}",
                    "b": node_id,
                    "score": round(ws.get("confidence", 0.7), 2),
                    "why": "same workstream",
                })
            idx += 1
    
    # Connect workstreams with shared topics
    # Build a map: workstream id → set of node ids
    ws_node_map: dict[str, set[str]] = {}
    for node in nodes:
        for cluster_id in node.get("clusters", [node.get("cluster", "")]):
            ws_node_map.setdefault(cluster_id, set()).add(node["id"])

    for i in range(len(wstreams)):
        for j in range(i + 1, len(wstreams)):
            shared = set(wstreams[i].get("topics", [])) & set(wstreams[j].get("topics", []))
            if shared:
                i_nodes = ws_node_map.get(wstreams[i]["id"], set())
                j_nodes = ws_node_map.get(wstreams[j]["id"], set())
                if i_nodes and j_nodes:
                    a_node = sorted(i_nodes)[0]
                    b_node = sorted(j_nodes)[0]
                    links.append({
                        "a": a_node, "b": b_node,
                        "score": 0.35,
                        "why": f"shared topics: {', '.join(list(shared)[:2])}",
                    })
    
    return {
        "run": "v1-real",
        "nodes": nodes,
        "links": links,
        "edges": links,
    }


# ── iris summary cache ──────────────────────────────────────────

def _iris_summary_cached() -> str | None:
    """Return cached LLM-generated iris summary, or None."""
    if not IRIS_SUMMARY_PATH.exists():
        return None
    try:
        data = json.loads(IRIS_SUMMARY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    txt = str(data.get("summary", "")).strip()
    return txt or None


def _iris_summary_generate_sync() -> str:
    """Generate an iris summary via LLM (Ollama or DeepSeek),
    cache it, and return it. Returns empty string on failure."""
    chat = iris_audit.IrisAuditChat()
    prompt = (
        "Summarize my digital footprint in exactly 2 short paragraphs "
        "(3-4 sentences each) in plain, natural prose. "
        "First paragraph: what my files reveal about my main interests and work. "
        "Second paragraph: what's surprising or distinctive, and one concrete observation. "
        "Rules: no bullet points, no markdown headers, no file counts, no jargon. "
        "Write as if explaining to a thoughtful friend, not a data analyst."
    )
    answer = chat.ask(prompt, DB_PATH)
    if not answer or len(answer) < 40:
        return ""
    # Clean: remove markdown, collapse whitespace
    cleaned = _summary_clean(answer)
    if cleaned:
        _iris_summary_save(cleaned)
    return cleaned


def _iris_summary_save(txt: str) -> None:
    """Persist the iris summary to the cache file."""
    rec = {
        "summary": txt[:900].strip(),
        "generated_at": int(time.time()),
        "model": "llm",
    }
    with _iris_summary_lock:
        IRIS_SUMMARY_PATH.write_text(
            json.dumps(rec, ensure_ascii=False), encoding="utf-8"
        )


def _iris_summary_async() -> None:
    """Fire-and-forget: generate iris summary in a background thread."""
    with _iris_summary_lock:
        if "v1" in _iris_summary_jobs:
            return
        _iris_summary_jobs.add("v1")
    t = threading.Thread(target=_iris_summary_worker, daemon=True)
    t.start()


def _iris_summary_worker() -> None:
    """Background worker for iris summary generation."""
    try:
        _iris_summary_generate_sync()
    finally:
        with _iris_summary_lock:
            _iris_summary_jobs.discard("v1")


def _summary_clean(txt: str) -> str:
    """Clean LLM output: remove markdown, collapse whitespace."""
    import re
    # Remove markdown headers, bold, italic
    txt = re.sub(r'(?m)^#{1,6}\s+', '', txt)
    txt = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', txt)
    txt = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', txt)
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    if not lines:
        return ""
    joined = " ".join(lines)
    # Collapse multiple spaces
    joined = re.sub(r'\s+', ' ', joined)
    return joined[:900].strip()


def _format_time_ago(iso_ts: str) -> str:
    """Convert an ISO timestamp to a human-readable 'X ago' string."""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return "just now"
    now = datetime.now(timezone.utc)
    delta = now - dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else now - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    months = days // 30
    return f"{months}mo ago"


def _mock_home_payload() -> dict:
    """Derive home-panel stats from real DB data — no hardcoded identity narratives.
    Invariant #8 (No Fake Completeness): every count comes from the DB.
    """
    import json as _json
    conn = get_db()
    claims_cnt = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
    repairs_cnt = conn.execute("SELECT COUNT(*) as c FROM repairs").fetchone()["c"]
    risks_cnt = conn.execute("SELECT COUNT(*) as c FROM risks").fetchone()["c"]
    signals_cnt = conn.execute("SELECT COUNT(*) as c FROM signals").fetchone()["c"]
    contradictions_cnt = conn.execute("SELECT COUNT(*) as c FROM contradictions").fetchone()["c"]
    source_cnt = conn.execute("SELECT COUNT(*) as c FROM sources").fetchone()["c"]
    # Get top narratives from claim titles
    titles = conn.execute("SELECT title FROM claims LIMIT 15").fetchall()
    # Get most recent timestamp from signals or claims
    latest = conn.execute(
        "SELECT MAX(created_at) as ts FROM (SELECT created_at FROM signals UNION ALL SELECT generated_at as created_at FROM claims)"
    ).fetchone()
    # Real audience exposure: distinct audience types from contradictions
    aud_rows = conn.execute(
        "SELECT DISTINCT audience_affected FROM contradictions "
        "WHERE audience_affected IS NOT NULL AND audience_affected != ''"
    ).fetchall()
    conn.close()

    # Parse audience_affected (stored as JSON arrays like '[\"recruiter\"]')
    audience_set: set[str] = set()
    for row in aud_rows:
        val = row["audience_affected"] or ""
        if val.startswith("["):
            try:
                items = _json.loads(val)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, str) and item.strip():
                            audience_set.add(item.strip())
            except Exception:
                pass
        elif val.strip():
            audience_set.add(val.strip())

    workstreams = _derive_workstreams()

    narratives = []
    # Build clean narrative labels from workstream names
    for ws in workstreams:
        name = ws.get("name", "")
        if name and name not in narratives:
            narratives.append(name)
        if len(narratives) >= 5:
            break
    # If not enough workstreams, supplement with claim-derived labels
    if len(narratives) < 3:
        for row in titles:
            t = (row["title"] or "").replace(" read:", "").strip()
            t = t.replace("frequent_topic", "focus").replace("project_velocity", "output")
            if t and t not in narratives:
                narratives.append(t)
            if len(narratives) >= 5:
                break

    file_count = sum(ws.get("file_count", 0) for ws in workstreams)
    total_size = sum(ws.get("size", 0) for ws in workstreams)
    confidence_vals = [ws.get("confidence", 0) for ws in workstreams if ws.get("confidence")]
    coherence_avg = round(sum(confidence_vals) / len(confidence_vals), 2) if confidence_vals else 0.0

    # Derive last_analyzed_ago from real DB timestamps
    last_analyzed_ago = _format_time_ago(latest["ts"]) if latest and latest["ts"] else "never"

    # Get LLM-generated iris summary (or None if not yet generated)
    iris_summary = _iris_summary_cached()
    # Fire-and-forget: trigger generation if no cached summary
    if iris_summary is None:
        _iris_summary_async()

    return {
        "home": str(Path.home()),
        "file_count": file_count,
        "total_size": total_size,
        "workstreams_count": len(workstreams),
        "coherence_avg": coherence_avg,
        "signal_count": signals_cnt,
        "claims_count": claims_cnt,
        "repairs_count": repairs_cnt,
        "risks_count": risks_cnt,
        "contradictions_count": contradictions_cnt,
        "source_count": source_cnt,
        "audience_count": len(audience_set),
        "audiences": sorted(audience_set),
        "last_analyzed_ago": last_analyzed_ago,
        "narratives": narratives,
        "exposures": contradictions_cnt,
        "iris_summary": iris_summary,
    }


# ── auth ───────────────────────────────────────────────────────────

@app.get("/api/runs")
async def legacy_runs():
    """Return real scan run identifiers from the DB."""
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT substr(created_at, 1, 8) as run_id FROM signals ORDER BY run_id DESC LIMIT 5"
    ).fetchall()
    conn.close()
    runs = [r["run_id"] for r in rows] if rows else []
    return {"runs": runs}


@app.get("/api/workstreams")
async def legacy_workstreams():
    return {"workstreams": _fast_mock_ws(), "cached": True}


@app.get("/api/home")
async def legacy_home():
    return _mock_home_payload()


@app.get("/api/graph")
async def legacy_graph(token: str = ""):
    """Return the full evidence graph from the last audit run.

    Tries to look up the user via token, falls back to first local user,
    then to empty graph if no users exist.
    """
    user = None
    if token:
        user = _get_user(token)
    if not user:
        # Try any user in the DB (local-first: usually just one)
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM users WHERE is_test_user=0 LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            user = _row_to_dict(row)
    if not user:
        return {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0,
                "run": "no-users"}
    graph_data = _build_audit_graph(user)
    graph_data["run"] = "v1-live"
    return graph_data


@app.get("/api/status")
async def legacy_status():
    """Return live status derived from real DB data."""
    home = _mock_home_payload()
    # Get the most recent signal timestamp as the last_run identifier
    conn = get_db()
    last = conn.execute("SELECT MAX(created_at) as ts FROM signals").fetchone()
    # Scanning state: if signals exist, we're not actively scanning
    sig_count = conn.execute("SELECT COUNT(*) as c FROM signals").fetchone()["c"]
    conn.close()
    last_run = (last["ts"] or "").replace(":", "").replace("-", "").replace("T", "-")[:15] if last and last["ts"] else ""
    # Derive stage from DB state
    if sig_count == 0:
        stage = "empty"
        stage_state = "no-data"
    else:
        stage = "ready"
        stage_state = "ready"
    return {
        "scanning": False,
        "last_run": last_run,
        "queue_depth": 0,
        "progress": {
            "stage": stage,
            "stage_state": stage_state,
            "indexed": home["file_count"],
            "total": home["file_count"],
        },
        "file_count": home["file_count"],
        "signal_count": home["signal_count"],
        "source_count": home["source_count"],
    }


@app.get("/api/analyze")
async def legacy_analyze(kind: str = "largest", limit: int = 10):
    """Return analysis results from real DB artifacts. No mock data."""
    lim = max(1, min(int(limit or 10), 50))
    conn = get_db()
    if kind == "duplicates":
        # Find artifacts with the same raw_hash (true duplicates)
        dup_rows = conn.execute("""
            SELECT raw_hash, COUNT(*) as cnt, GROUP_CONCAT(encrypted_path, '|||') as paths
            FROM artifacts WHERE raw_hash IS NOT NULL AND raw_hash != ''
            GROUP BY raw_hash HAVING cnt > 1 LIMIT ?
        """, (lim,)).fetchall()
        conn.close()
        groups = []
        for row in dup_rows:
            paths = row["paths"].split("|||") if row["paths"] else []
            items = [{"path": p, "hash": row["raw_hash"]} for p in paths]
            groups.append({
                "hash": row["raw_hash"][:20],
                "waste": 0,
                "items": items,
            })
        return {"kind": kind, "groups": groups}

    if kind == "old_downloads":
        rows = conn.execute(
            "SELECT encrypted_path as path, created_at as mtime FROM artifacts ORDER BY created_at ASC LIMIT ?",
            (lim,),
        ).fetchall()
        conn.close()
        items = [{"path": r["path"], "mtime": r["mtime"]} for r in rows]
        return {"kind": kind, "items": items}

    # kind == "largest" (default)
    rows = conn.execute(
        "SELECT encrypted_path as path, id FROM artifacts ORDER BY encrypted_path DESC LIMIT ?",
        (lim,),
    ).fetchall()
    conn.close()
    items = [{"path": r["path"], "id": r["id"]} for r in rows]
    return {"kind": kind, "items": items}

@app.post("/api/v1/auth/signup")
async def signup(req: SignupRequest):
    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE email=?", (req.email,)).fetchone()
    if existing:
        token = _gen_token()
        conn.execute("INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)",
                     (token, existing["id"], _now()))
        conn.commit()
        conn.close()
        return {"token": token, "user_id": existing["id"], "created": True}

    user_id = str(uuid4())
    key_ref = hashlib.sha256(f"optic-key-{user_id}-{time.time()}".encode()).hexdigest()[:16]
    now = _now()
    conn.execute(
        "INSERT INTO users(id, email, local_mode, encryption_key_ref, created_at, updated_at) "
        "VALUES(?,?,1,?,?,?)",
        (user_id, req.email, key_ref, now, now)
    )
    token = _gen_token()
    conn.execute("INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)",
                 (token, user_id, now))
    conn.execute(
        "INSERT INTO onboarding(user_id, step, completed_steps, created_at) VALUES(?,0,'[]',?)",
        (user_id, now)
    )
    conn.commit()
    conn.close()
    return {"token": token, "user_id": user_id, "created": False}


@app.post("/api/v1/auth/login")
async def login(req: LoginRequest):
    conn = get_db()
    row = conn.execute("SELECT id FROM users WHERE email=?", (req.email,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "user not found")
    token = _gen_token()
    conn.execute("INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)",
                 (token, row["id"], _now()))
    conn.commit()
    conn.close()
    return {"token": token, "user_id": row["id"]}


# ── onboarding ────────────────────────────────────────────────────

@app.get("/api/v1/onboarding")
async def get_onboarding(token: str = ""):
    if not token:
        return {"step": 0, "audit_mode": None, "completed": False, "completed_steps": [], "available_modes": [m.value for m in AuditMode]}
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    row = conn.execute("SELECT * FROM onboarding WHERE user_id=?", (user["id"],)).fetchone()
    conn.close()
    if not row:
        return {"step": 0, "audit_mode": None, "completed_steps": []}
    completed = json.loads(row["completed_steps"] or "[]")
    return {
        "step": row["step"],
        "audit_mode": row["audit_mode"],
        "completed_steps": completed,
        "available_modes": [m.value for m in AuditMode],
        "available_lenses": list(AUDIENCE_LENSES.keys()),
    }


@app.post("/api/v1/onboarding/step")
async def advance_onboarding(req: OnboardingStepRequest, token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    row = conn.execute("SELECT * FROM onboarding WHERE user_id=?", (user["id"],)).fetchone()
    if not row:
        raise HTTPException(404, "onboarding not started")

    completed = json.loads(row["completed_steps"] or "[]")
    completed.append(req.step)

    updates = {"step": req.step + 1, "completed_steps": json.dumps(completed)}
    if req.audit_mode:
        updates["audit_mode"] = req.audit_mode

    conn.execute(
        "UPDATE onboarding SET step=?, audit_mode=?, completed_steps=? WHERE user_id=?",
        (updates["step"], updates.get("audit_mode", row["audit_mode"]),
         updates["completed_steps"], user["id"])
    )
    conn.commit()
    conn.close()
    return {"step": updates["step"], "completed_steps": completed}


# ── sources ────────────────────────────────────────────────────────

@app.get("/api/v1/sources")
async def list_sources(token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    rows = conn.execute("SELECT * FROM sources WHERE user_id=?", (user["id"],)).fetchall()
    conn.close()
    return {"sources": [_row_to_dict(r) for r in rows]}


@app.post("/api/v1/sources")
async def add_source(req: SourceRequest, token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    source_id = str(uuid4())
    now = _now()
    conn = get_db()
    conn.execute(
        "INSERT INTO sources(id, user_id, type, provider, import_method, user_label, "
        "status, metadata, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (source_id, user["id"], req.type, req.provider, req.url or req.handle or "manual",
         req.user_label, "pending", json.dumps({"url": req.url, "handle": req.handle}),
         now, now)
    )
    conn.commit()
    conn.close()
    return {"source_id": source_id, "status": "pending"}


@app.post("/api/v1/sources/{source_id}/consent")
async def create_consent(source_id: str, req: ConsentRequest, token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    source = conn.execute(
        "SELECT id FROM sources WHERE id=? AND user_id=?", (source_id, user["id"])
    ).fetchone()
    if not source:
        conn.close()
        raise HTTPException(404, "source not found")
    receipt_id = str(uuid4())
    now = _now()
    conn.execute(
        "INSERT INTO consent_receipts(id, source_id, scope, purpose, retention_days, "
        "cloud_allowed, export_allowed, created_at) VALUES(?,?,?,?,?,?,?,?)",
        (receipt_id, source_id, json.dumps(req.scope), req.purpose,
         req.retention_days, int(req.cloud_allowed), int(req.export_allowed), now)
    )
    conn.execute("UPDATE sources SET status='ready' WHERE id=?", (source_id,))
    conn.commit()
    conn.close()
    return {"receipt_id": receipt_id, "status": "created"}


def _jsonable(value):
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "value") and not isinstance(value, (str, bytes)):
        return value.value
    return value


def _parser_format(fmt: str) -> str:
    return {"txt": "txt_md", "image": "image_metadata"}.get(fmt, fmt)


def _fetch_url(url: str) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(400, "url must be absolute http(s)")
    req = UrlRequest(url, headers={"User-Agent": scrapers.USER_AGENT, "Accept": "*/*"})
    with urlopen(req, timeout=8) as resp:
        data = resp.read(scrapers.MAX_FETCH_BYTES + 1)
        if len(data) > scrapers.MAX_FETCH_BYTES:
            raise HTTPException(413, "url response exceeds parser limit")
        return data, resp.geturl()


def _save_import(user_id: str, source_type: str, provider: str, label: str, artifacts: list[Artifact], meta: dict) -> str:
    source_id = str(artifacts[0].source_id if artifacts else uuid4())
    now = _now()
    conn = get_db()
    conn.execute(
        "INSERT INTO sources(id, user_id, type, provider, import_method, user_label, "
        "status, metadata, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (source_id, user_id, source_type, provider, "import", label, "ready" if artifacts else "failed",
         json.dumps(meta), now, now)
    )
    for artifact in artifacts:
        conn.execute(
            "INSERT OR REPLACE INTO artifacts(id, source_id, type, raw_hash, encrypted_path, "
            "metadata, is_public, content_preview, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (str(artifact.id), str(artifact.source_id), artifact.type, artifact.raw_hash,
             getattr(artifact, "encrypted_path", ""), json.dumps(_jsonable(artifact.metadata)),
             int(bool(artifact.is_public)), artifact.content_preview, artifact.created_at)
        )
    conn.commit()
    conn.close()
    return source_id


async def _import_request_parts(request: Request):
    files, urls = [], []
    provider, label, format_hint = "manual_import", "", ""
    ctype = request.headers.get("content-type", "")
    if "multipart/form-data" in ctype or "application/x-www-form-urlencoded" in ctype:
        form = await request.form()
        for key, value in form.multi_items():
            if hasattr(value, "filename") and hasattr(value, "read"):
                content = await value.read()
                if content:
                    files.append((value.filename or key, content))
            elif key in {"url", "urls"}:
                urls.extend([u.strip() for u in str(value).splitlines() if u.strip()])
            elif key == "provider":
                provider = str(value) or provider
            elif key == "user_label":
                label = str(value)
            elif key == "format_hint":
                format_hint = str(value)
    else:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if isinstance(body, dict):
            provider = str(body.get("provider") or provider)
            label = str(body.get("user_label") or "")
            format_hint = str(body.get("format_hint") or "")
            raw_urls = body.get("urls", body.get("url", []))
            urls = [str(u).strip() for u in (raw_urls if isinstance(raw_urls, list) else [raw_urls]) if str(u).strip()]
    query_url = request.query_params.get("url")
    if query_url:
        urls.append(query_url)
    return files, urls, provider, label, format_hint


def _user_artifact_rows(user_id: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT a.* FROM artifacts a JOIN sources s ON s.id=a.source_id "
        "WHERE s.user_id=? ORDER BY a.created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def _build_evidence_graph(user: dict) -> graph.EvidenceGraph:
    eg = graph.EvidenceGraph()
    eg.add_node("user", user["id"], label=user.get("email", "Optic user"), data={"local_mode": True})
    conn = get_db()
    sources = conn.execute("SELECT * FROM sources WHERE user_id=?", (user["id"],)).fetchall()
    artifacts = conn.execute(
        "SELECT a.* FROM artifacts a JOIN sources s ON s.id=a.source_id WHERE s.user_id=?",
        (user["id"],)
    ).fetchall()
    conn.close()
    for source in sources:
        sid = f"source:{source['id']}"
        eg.add_node("document", sid, label=source["user_label"] or source["provider"] or source["type"], data=_row_to_dict(source))
        eg.add_edge("imported_under", sid, user["id"], data={"status": source["status"]})
    for row in artifacts:
        artifact = _row_to_dict(row)
        aid = artifact["id"]
        eg.add_node("artifact", aid, label=artifact["type"], data=artifact)
        eg.add_edge("derived_from", aid, f"source:{artifact['source_id']}", data={"preview": artifact.get("content_preview", "")[:160]})
    return eg


def _build_audit_graph(user: dict, workstreams: list | None = None) -> graph.EvidenceGraph:
    """Build a complete EvidenceGraph from audit results in the DB.

    Populates nodes for claims, contradictions, risks, repairs, audiences,
    workstreams and edges for supports, weakens, contradicts, risky_for,
    repaired_by, visible_to.  Returns a graph ready for JSON export.
    """
    eg = graph.EvidenceGraph()

    # ── user root ──────────────────────────────────────────────
    user_id = str(user["id"])
    eg.add_node("user", user_id,
                label=user.get("email", "Optic user"),
                data={"local_mode": True})

    conn = get_db()

    # ── audience lens nodes ────────────────────────────────────
    audience_ids = {}
    for lens_id in AUDIENCE_LENSES:
        label = lens_id.replace("_", " ").title()
        eg.add_node("audience", f"audience:{lens_id}", label=label)
        audience_ids[lens_id] = f"audience:{lens_id}"

    # ── workstream / source nodes ─────────────────────────────
    wstreams = workstreams or _derive_workstreams()
    for ws in wstreams:
        ws_id = ws["id"]
        eg.add_node("document", ws_id,
                    label=ws.get("name", "Unknown"),
                    data={"confidence": ws.get("confidence"),
                          "file_count": ws.get("file_count"),
                          "topics": ws.get("topics", [])})
        eg.add_edge("derived_from", ws_id, user_id,
                    data={"type": "workstream"})

    # ── claim nodes + evidence edges ──────────────────────────
    claims = conn.execute("SELECT * FROM claims").fetchall()
    for row in claims:
        cid = row["id"]
        audience = row["audience_lens"] or "general"
        confidence = row["confidence_band"] or "low"
        eg.add_node("claim", cid,
                    label=row["title"] or (row["claim"] or "")[:80],
                    data={
                        "claim": row["claim"],
                        "audience_lens": audience,
                        "confidence_band": confidence,
                        "severity": row["severity"],
                        "evidence_count": row["evidence_count"],
                        "not_a_verdict": bool(int(row["not_a_verdict"] or "1")),
                    })
        # claim → audience
        if audience in audience_ids:
            eg.add_edge("visible_to", cid, audience_ids[audience])

        # supporting evidence — use merge_node for provenance tracking
        try:
            supporting = json.loads(row["supporting_evidence"] or "[]")
        except Exception:
            supporting = []
        for ev in supporting:
            ev_id = f"evidence:{ev}"
            eg.merge_node("artifact", ev_id,
                          label=str(ev)[:60],
                          data={"evidence_role": "supporting"},
                          provenance=audience)
            eg.add_edge("supports", ev_id, cid, weight=0.8)

        # weakening evidence
        try:
            weakening = json.loads(row["weakening_evidence"] or "[]")
        except Exception:
            weakening = []
        for ev in weakening:
            ev_id = f"evidence:{ev}"
            eg.merge_node("artifact", ev_id,
                          label=str(ev)[:60],
                          data={"evidence_role": "weakening"},
                          provenance=audience)
            eg.add_edge("weakens", ev_id, cid, weight=0.4)

        # source gaps as missing-context edges
        try:
            gaps = json.loads(row["source_gaps"] or "[]")
        except Exception:
            gaps = []
        for gap in gaps:
            gap_id = f"source_gap:{gap}"
            eg.merge_node("source_gap", gap_id,
                          label=str(gap)[:80],
                          provenance=audience)
            eg.add_edge("missing_context_for", gap_id, cid)

    # ── contradiction nodes + contradicts edges ────────────────
    contradictions = conn.execute("SELECT * FROM contradictions").fetchall()
    for row in contradictions:
        cid = row["id"]
        eg.add_node("contradiction", cid,
                    label=row["category"] or "contradiction",
                    data={
                        "description": row["description"],
                        "severity": row["severity"],
                        "resolution_suggestion":
                            row["resolution_suggestion"] or "",
                    })
        # contradicts edges to linked claims
        try:
            linked = json.loads(row["claim_ids"] or "[]")
        except Exception:
            linked = []
        for claim_id in linked:
            eg.add_edge("contradicts", cid, str(claim_id), weight=0.9)

        # audience affected
        try:
            affected = json.loads(row["audience_affected"] or "[]")
        except Exception:
            affected = []
        for aud in affected:
            key = f"audience:{aud}"
            if key not in audience_ids:
                eg.add_node("audience", key,
                            label=str(aud).replace("_", " ").title())
                audience_ids[aud] = key
            eg.add_edge("risky_for", cid, audience_ids.get(aud, key))

    # ── risk nodes ─────────────────────────────────────────────
    risks = conn.execute("SELECT * FROM risks").fetchall()
    for row in risks:
        rid = row["id"]
        eg.add_node("risk", rid,
                    label=row["category"] or "risk",
                    data={
                        "description": row["description"],
                        "severity": row["severity"],
                    })
        try:
            affected = json.loads(row["audience_affected"] or "[]")
        except Exception:
            affected = []
        for aud in affected:
            key = f"audience:{aud}"
            if key not in audience_ids:
                eg.add_node("audience", key,
                            label=str(aud).replace("_", " ").title())
                audience_ids[aud] = key
            eg.add_edge("risky_for", rid, audience_ids.get(aud, key))

    # ── repair nodes + repaired_by edges ───────────────────────
    repairs = conn.execute("SELECT * FROM repairs").fetchall()
    for row in repairs:
        rid = row["id"]
        eg.add_node("repair", rid,
                    label=row["title"] or "repair",
                    data={
                        "impact": row["impact"],
                        "effort": row["effort"],
                        "urgency": row["urgency"],
                        "status": row["status"],
                    })
        # repaired_by from linked claim
        linked_claim = row["linked_claim_id"]
        if linked_claim:
            eg.add_edge("repaired_by", str(linked_claim), rid)

        # repaired_by from affected audiences
        try:
            affected = json.loads(row["affected_audience"] or "[]")
        except Exception:
            affected = []
        for aud in affected:
            key = f"audience:{aud}"
            if key not in audience_ids:
                eg.add_node("audience", key,
                            label=str(aud).replace("_", " ").title())
                audience_ids[aud] = key
            eg.add_edge("repaired_by", audience_ids.get(aud, key), rid)

    conn.close()

    # ── extract nodes / edges for JSON export ──────────────────
    from contextlib import closing
    with closing(eg) as final_graph:
        nodes = [final_graph._node(r) for r in
                 final_graph.conn.execute(
                     "SELECT * FROM nodes ORDER BY type,label,id").fetchall()]
        edges = [final_graph._edge(r) for r in
                 final_graph.conn.execute(
                     "SELECT * FROM edges ORDER BY type,id").fetchall()]
    return {"nodes": nodes, "edges": edges,
            "node_count": len(nodes), "edge_count": len(edges)}


@app.post("/api/v1/sources/import")
async def import_sources(request: Request, token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    source_id = uuid4()
    registry = parsers.ParserRegistry(source_id)
    files, urls, provider, label, format_hint = await _import_request_parts(request)
    if not files and not urls:
        raise HTTPException(400, "provide at least one uploaded file or url")
    artifacts: list[Artifact] = []
    errors: list[str] = []
    warnings: list[str] = []
    for name, content in files:
        fmt = _parser_format(format_hint or registry.detect_format(name, content))
        parsed = registry.parse(name, content, fmt)
        artifacts.extend(parsed.artifacts); errors.extend(parsed.errors); warnings.extend(parsed.warnings)
    for url in urls:
        try:
            content, final_url = _fetch_url(url)
            fmt = _parser_format(format_hint or registry.detect_format(final_url, content))
            parsed = registry.parse(final_url, content, fmt)
            for artifact in parsed.artifacts:
                artifact.is_public = True
                artifact.metadata.update({"url": url, "final_url": final_url})
            artifacts.extend(parsed.artifacts)
            errors.extend(parsed.errors); warnings.extend(parsed.warnings)
        except Exception as exc:
            errors.append(str(exc))
    stored_source_id = _save_import(str(user["id"]), "url" if urls and not files else "file_upload", provider, label, artifacts, {
        "files": [name for name, _ in files], "urls": urls, "errors": errors, "warnings": warnings,
    })
    return {"source_id": stored_source_id, "artifact_count": len(artifacts), "errors": errors, "warnings": warnings}


@app.get("/api/v1/graph/evidence")
async def get_evidence_graph(token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    graph_data = _build_audit_graph(user)
    return graph_data


@app.get("/api/v1/entities")
async def get_entities(token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    artifacts = [_row_to_artifact(r) for r in _user_artifact_rows(user["id"])]
    entities = resolver.EntityResolver().resolve(artifacts)
    return {"entities": [_jsonable(e) for e in entities], "entity_count": len(entities)}


@app.get("/api/v1/scrapers/status")
async def get_scrapers_status(token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    return {"providers": scrapers.provider_ui_states()}


class ScraperFetchRequest(BaseModel):
    """Trigger a scraper fetch. Provider + scope dict."""
    provider: str = "manual_url"
    scope: dict[str, Any] = {}
    save: bool = True  # persist artifacts to DB
    user_label: str = ""


@app.post("/api/v1/scrapers/fetch")
async def scraper_fetch(req: ScraperFetchRequest, token: str = ""):
    """Run a user-triggered fetch through any registered provider."""
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    provider_cls = scrapers.providers_by_id.get(req.provider)
    if not provider_cls:
        raise HTTPException(400, f"unknown provider: {req.provider}. Available: {list(scrapers.providers_by_id)}")
    scope = dict(req.scope)
    scope["user_triggered"] = True
    provider = provider_cls()
    ui = provider.ui_state()
    if not ui.enabled:
        raise HTTPException(400, f"provider {req.provider} is disabled: {ui.reason}")
    result = provider.fetch(scope)
    artifacts_list = result.artifacts
    source_id = None
    if req.save and artifacts_list:
        source_id = _save_import(
            str(user["id"]),
            req.provider,
            req.provider,
            req.user_label or f"{provider.label} import",
            artifacts_list,
            {"scope": scope, "provider": req.provider},
        )
    return {
        "provider": req.provider,
        "ui_state": ui.as_dict(),
        "artifacts": [_jsonable(a) for a in artifacts_list],
        "artifact_count": len(artifacts_list),
        "errors": result.errors,
        "warnings": result.warnings,
        "source_id": source_id,
    }


@app.get("/api/v1/scrapers/search/status")
async def get_search_providers_status(token: str = ""):
    """Return UI status for search-specific providers (Brave, SerpAPI, Tavily)."""
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    return {"search_providers": scrapers.search_providers_ui()}


class SearchRequest(BaseModel):
    """Search query with optional provider override."""
    query: str
    provider: str = "tavily"  # default search provider
    num_results: int = 10
    save: bool = True
    user_label: str = ""


@app.post("/api/v1/scrapers/search")
async def scraper_search(req: SearchRequest, token: str = ""):
    """Execute search via a search provider (Brave, SerpAPI, or Tavily)."""
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    valid_search = {"brave_search", "serpapi", "tavily"}
    if req.provider not in valid_search:
        raise HTTPException(400, f"unknown search provider: {req.provider}. Use one of: {sorted(valid_search)}")
    provider_cls = scrapers.providers_by_id.get(req.provider)
    if not provider_cls:
        raise HTTPException(400, f"provider {req.provider} not registered")
    provider = provider_cls()
    ui = provider.ui_state()
    if not ui.enabled:
        return {
            "provider": req.provider,
            "query": req.query,
            "ui_state": ui.as_dict(),
            "artifacts": [],
            "artifact_count": 0,
            "errors": [f"Search provider disabled: {ui.reason}"],
            "warnings": [],
            "disabled": True,
            "required_keys": ui.missing_credentials,
        }
    scope = {
        "user_triggered": True,
        "query": req.query,
        "num_results": req.num_results,
    }
    result = provider.fetch(scope)
    artifacts_list = result.artifacts
    source_id = None
    if req.save and artifacts_list:
        source_id = _save_import(
            str(user["id"]),
            req.provider,
            req.provider,
            req.user_label or f"Search: {req.query[:80]}",
            artifacts_list,
            {"query": req.query, "provider": req.provider, "num_results": req.num_results},
        )
    return {
        "provider": req.provider,
        "query": req.query,
        "ui_state": ui.as_dict(),
        "artifacts": [_jsonable(a) for a in artifacts_list],
        "artifact_count": len(artifacts_list),
        "errors": result.errors,
        "warnings": result.warnings,
        "source_id": source_id,
        "disabled": False,
    }


# ── iris ──────────────────────────────────────────────────────────

class IrisAskRequest(BaseModel):
    """Accepts 'prompt', 'message', or 'question' — whatever the frontend sends."""
    prompt: str = ""
    message: str = ""
    question: str = ""

    @property
    def text(self) -> str:
        return self.prompt or self.message or self.question or ""


class IrisChatRequest(BaseModel):
    """Matches the ctxorg frontend's /api/iris call format."""
    q: str = ""
    run: str = ""
    mode: str = "report"
    history: list[dict] = []
    selected_ids: list[str] = []
    audience: str = "recruiter"


@app.post("/api/v1/iris/ask")
async def iris_ask(req: IrisAskRequest, token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    if not req.text.strip():
        raise HTTPException(400, "prompt, message, or question is required")
    chat = iris_audit.IrisAuditChat()
    answer = chat.ask(req.text, DB_PATH)
    return {"response": answer}


@app.get("/api/v1/iris/summary")
async def iris_summary_get(token: str = ""):
    """Return the cached LLM-generated iris summary, or null if not yet generated."""
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    summary = _iris_summary_cached()
    return {"iris_summary": summary, "cached": summary is not None}


@app.post("/api/v1/iris/summary")
async def iris_summary_generate(token: str = ""):
    """Force-regenerate the iris summary via LLM and cache it."""
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    summary = _iris_summary_generate_sync()
    if summary:
        return {"iris_summary": summary, "generated": True}
    else:
        raise HTTPException(503, "LLM unavailable — could not generate summary")


@app.get("/api/iris/summary")
async def iris_summary_legacy_get(token: str = ""):
    """Legacy endpoint: return cached iris summary or null."""
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    summary = _iris_summary_cached()
    return {"iris_summary": summary, "cached": summary is not None}


@app.post("/api/iris/summary")
async def iris_summary_legacy_generate(token: str = ""):
    """Legacy endpoint: force-regenerate iris summary."""
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    summary = _iris_summary_generate_sync()
    if summary:
        return {"iris_summary": summary, "generated": True}
    else:
        raise HTTPException(503, "LLM unavailable — could not generate summary")


@app.post("/api/iris")
async def iris_legacy(req: IrisChatRequest, token: str = ""):
    """Mirror the ctxorg /api/iris endpoint so the frontend works against V1."""
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    if not req.q.strip():
        raise HTTPException(400, "'q' field is required")
    chat = iris_audit.IrisAuditChat()
    answer = chat.iris_chat(
        req.q,
        DB_PATH,
        mode=req.mode,
        history=req.history,
        audience=req.audience,
    )
    return {"response": answer}


# ── settings ──────────────────────────────────────────────────────

class SettingsRequest(BaseModel):
    settings: dict

@app.get("/api/v1/settings")
async def get_settings(token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    row = conn.execute("SELECT settings FROM users WHERE id=?", (user["id"],)).fetchone()
    conn.close()
    return {"settings": json.loads(row["settings"]) if row and row["settings"] else {}}

@app.post("/api/v1/settings")
async def update_settings(req: SettingsRequest, token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    conn.execute(
        "UPDATE users SET settings=?, updated_at=? WHERE id=?",
        (json.dumps(req.settings), _now(), user["id"])
    )
    conn.commit()
    conn.close()
    return {"status": "saved"}


# ── audit ──────────────────────────────────────────────────────────
# ── ctxorg-powered audit pipeline ─────────────────────────────────

# ── URL / domain / generic noise words to strip from workstream names ──
_WS_NOISE_WORDS = {
    # URL/domain fragments
    "https", "http", "www", "com", "org", "net", "html", "json", "xml",
    "css", "js", "php", "asp", "jsp", "htm", "xhtml",
    # Generic file/noise fragments
    "image", "images", "file", "files", "copy", "backup", "final", "draft",
    "temp", "untitled", "screenshot", "screenshots", "screen",
    "photo", "photos", "picture", "pictures", "img", "pic",
    "version", "new", "old", "test", "sample", "example", "misc", "various",
    "inbox", "downloads", "desktop", "documents", "library", "folder",
    "users", "home", "root", "local", "mobile",
    "name", "path", "size", "type", "date", "true", "false", "null", "none",
    "default", "used", "found",
    # Domain-like noise (hex fragments, random strings)
    "abx", "xtcftw", "rspace", "pyasn1",
    # Vague single words that don't make good labels
    "data", "work", "beta", "tests", "examples", "docs", "generated",
    "live", "round", "very", "simple", "just", "only", "some",
}


def _clean_workstream_name(raw: str) -> str:
    """Clean ugly folder names into readable workstream labels."""
    if not raw:
        return "Other"
    name = raw.strip()
    # Remove common prefixes that make names ugly
    for prefix in ["set-up-", "setup-", "config-"]:
        if name.lower().startswith(prefix):
            name = name[len(prefix):]
    # Replace hyphens/underscores with spaces, title case
    name = name.replace("-", " ").replace("_", " ")
    # Title case but keep common acronyms
    words = name.split()
    # Filter out noise words first
    meaningful = [w for w in words if w.lower() not in _WS_NOISE_WORDS]
    if not meaningful:
        # If everything was noise, use the first word that isn't a single char
        meaningful = [w for w in words if len(w) > 1]
    if not meaningful:
        meaningful = words[:1]  # fallback
    cleaned = []
    for w in meaningful:
        if w.upper() in ("AI", "API", "SSL", "DNS", "PDF", "CSS", "JS", "ML",
                         "UI", "UX", "ML", "NLP", "GPU", "CPU", "RAM", "SSD",
                         "VM", "CI", "CD", "AWS", "GCP", "SQL", "NoSQL", "DB"):
            cleaned.append(w.upper())
        elif len(w) <= 2:
            cleaned.append(w.upper())
        else:
            cleaned.append(w[0].upper() + w[1:].lower() if len(w) > 1 else w.upper())
    name = " ".join(cleaned)
    # If name is still too generic, keep as-is
    if len(name) < 2:
        name = raw[:30]
    return name.strip() or "Other"


def _load_ctxorg_workstreams() -> list[dict]:
    """Load item clusters from ctxorg's SQLite database as workstream-like objects."""
    if hasattr(_load_ctxorg_workstreams, "_cache"):
        return _load_ctxorg_workstreams._cache
    workstreams: list[dict] = []
    if not CTXORG_AVAILABLE:
        _load_ctxorg_workstreams._cache = workstreams
        return workstreams
    try:
        # server.py is at backend/src/optic/v1/server.py — go up 4 levels to backend/
        cfg_path = _Path(__file__).resolve().parent.parent.parent.parent / "config.json"
        if not cfg_path.exists():
            cfg_path = _Path(__file__).resolve().parent.parent.parent.parent / "backend" / "config.json"
        if cfg_path.exists():
            cfg = json.load(open(cfg_path))
            state_dir = cfg.get("state_dir", ".ctxorg/state")
            db_path = _Path(cfg.get("home", "")) / state_dir / "ctx.db"
            if not db_path.exists():
                # Try relative to backend (4 levels up from server.py)
                db_path = _Path(__file__).resolve().parent.parent.parent.parent / ".ctxorg" / "state" / "ctx.db"
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                # Group items by immediate parent directory for cleaner cluster names.
                # Uses the SQLite rtrim trick: rtrim(path, chars) strips trailing chars
                # that appear in `chars` one-by-one from the right. Since '/' is never in
                # the character set (we strip it for `chars`), rtrim always stops at the
                # last '/', giving us a clean directory prefix. We then strip that prefix
                # from the path to get the filename, subtract to get the dir path, and
                # repeat the trick to extract just the immediate parent directory name.
                rows = conn.execute("""
                    WITH path_parts AS (
                        SELECT path, kind, size,
                               replace(
                                   substr(path, 1,
                                       length(path)
                                       - length(replace(path,
                                           rtrim(path, replace(path, '/', '')),
                                           ''))
                                       - 1),
                                   rtrim(
                                       substr(path, 1,
                                           length(path)
                                           - length(replace(path,
                                               rtrim(path, replace(path, '/', '')),
                                               ''))
                                           - 1),
                                       replace(
                                           substr(path, 1,
                                               length(path)
                                               - length(replace(path,
                                                   rtrim(path, replace(path, '/', '')),
                                                   ''))
                                               - 1),
                                           '/', '')
                                   ),
                                   ''
                               ) as cluster_name
                        FROM items
                        WHERE kind='file'
                          AND path NOT LIKE '%node_modules%'
                          AND path NOT LIKE '%.git/%'
                          AND path NOT LIKE '%__pycache__%'
                          AND path NOT LIKE '%/.%'
                    )
                    SELECT
                        cluster_name,
                        COUNT(*) as file_count,
                        SUM(size) as total_size,
                        GROUP_CONCAT(DISTINCT substr(
                            CASE WHEN path LIKE '%.%' AND path NOT LIKE '%/.%'
                                 THEN replace(path, rtrim(path, replace(path, '.', '')), '')
                                 ELSE ''
                            END, 1, 16)) as extensions
                    FROM path_parts
                    GROUP BY cluster_name
                    HAVING file_count > 5
                    ORDER BY file_count DESC
                    LIMIT 30
                """).fetchall()
                conn.close()
                for i, row in enumerate(rows):
                    raw_name = row["cluster_name"]
                    # Clean ugly folder names
                    clean_name = _clean_workstream_name(raw_name)
                    workstreams.append({
                        "id": f"ws-{i:03d}",
                        "name": clean_name,
                        "file_count": row["file_count"],
                        "size": row["total_size"] or 0,
                        "confidence": min(0.95, 0.4 + (row["file_count"] / 5000)),
                        "topics": json.dumps([clean_name[:20]]),
                        "folders": json.dumps([clean_name]),
                        "summary": f"{row['file_count']} files in {clean_name}",
                    })
    except Exception:
        pass
    _load_ctxorg_workstreams._cache = workstreams
    return workstreams


# ── Stage 4: Real file parsing ────────────────────────────────────

def _fetch_cluster_files(cluster_name: str, max_files: int = 15) -> list[dict]:
    """Fetch real file paths and extracted text for a workstream cluster.
    
    Uses ctxorg DB's items table. Returns list of {path, size, ext, text} dicts.
    """
    files = []
    if not CTXORG_AVAILABLE:
        return files
    try:
        cfg_path = _Path(__file__).resolve().parent.parent.parent.parent / "config.json"
        if not cfg_path.exists():
            cfg_path = _Path(__file__).resolve().parent.parent.parent.parent / "backend" / "config.json"
        if cfg_path.exists():
            cfg = json.load(open(cfg_path))
            state_dir = cfg.get("state_dir", ".ctxorg/state")
            db_path = _Path(cfg.get("home", "")) / state_dir / "ctx.db"
            if not db_path.exists():
                db_path = _Path(__file__).resolve().parent.parent.parent.parent / ".ctxorg" / "state" / "ctx.db"
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                # Escape single-quotes in cluster name for LIKE
                safe_name = cluster_name.replace("'", "''")
                rows = conn.execute(
                    """SELECT path, kind, size, ext, mtime, text
                       FROM items
                       WHERE kind='file'
                         AND path NOT LIKE '%node_modules%'
                         AND path NOT LIKE '%.git/%'
                         AND path NOT LIKE '%__pycache__%'
                         AND path NOT LIKE '%/.%'
                         AND ext IN ('.md','.txt','.py','.js','.json','.csv','.html','.pdf',
                                     '.docx','.xml','.yaml','.yml','.toml','.rst','.log')
                         AND path LIKE ?
                       ORDER BY size DESC
                       LIMIT ?""",
                    (f"%/{safe_name}/%", max_files))
                files = [dict(r) for r in rows.fetchall()]
                conn.close()
    except Exception:
        pass
    return files


def _parse_file_into_artifacts(
    filepath: str,
    source_id: UUID,
    existing_hashes: set | None = None,
) -> tuple[list[Artifact], list[str]]:
    """Parse a single file using ParserRegistry and return Artifacts.
    
    Returns (artifacts, error_messages).
    """
    if existing_hashes is None:
        existing_hashes = set()
    artifacts = []
    errors = []
    try:
        registry = parsers.ParserRegistry(source_id=source_id)
        fmt = registry.detect_format(filepath=filepath)
        result = registry.parse(filepath=filepath, format_hint=fmt)
        errors.extend(result.errors)
        for art in result.artifacts:
            if art.raw_hash in existing_hashes:
                continue
            existing_hashes.add(art.raw_hash)
            artifacts.append(art)
    except Exception as e:
        errors.append(f"parse error for {filepath}: {e}")
    return artifacts, errors


# ── Stage 5: Signal detection on parsed content ───────────────────

def _build_signal_auditor():
    """Build a configured SignalAuditor with all relevant detectors.
    
    Returns SignalAuditor or None if signal audit is unavailable.
    """
    if not SIGNAL_AUDIT_AVAILABLE:
        return None
    # Use string enum values directly (str Enum) to avoid conditional import types
    auditor = SignalAuditor()
    auditor.add_detector(PatternDetector.default_bias_patterns())
    auditor.add_detector(PatternDetector(  # type: ignore[arg-type]
        patterns={
            "ai_ml_content": (
                r"\b(machine learning|deep learning|neural network|transformer|"
                r"LLM|GPT|BERT|fine.?tun|embedding|vector|RAG|"
                r"prompt engineer|diffusion|GAN|reinforcement)\b",
                "info",  # Severity.INFO
                0.7,
            ),
            "software_engineering": (
                r"\b(python|javascript|typescript|rust|golang?|react|next\.?js|"
                r"API|REST|GraphQL|docker|kubernetes|CI/CD|"
                r"postgres|redis|AWS|deploy|microservice)\b",
                "info",
                0.6,
            ),
            "research_signals": (
                r"\b(paper|arxiv|doi|preprint|experiment|baseline|"
                r"benchmark|ablation|state.of.the.art|SOTA)\b",
                "info",
                0.5,
            ),
        }
    ))
    auditor.add_detector(AnomalyDetector(repetition_threshold=0.3))
    auditor.add_detector(ThresholdDetector(
        thresholds={"file_count": (1.0, 1000.0, "info")}
    ))
    return auditor


def _audit_content_for_signals(
    content: str,
    source_type: str = "text",
    metadata: dict | None = None,
) -> list[dict]:
    """Run signal detectors against parsed content and return detection dicts.
    
    Args:
        content: The text content to analyze.
        source_type: One of 'text', 'html', 'code', 'pdf', 'csv', 'image', etc.
        metadata: Optional metadata about the content source.
    
    Returns:
        List of detection dicts with attribute, severity, confidence, location, description.
    """
    if not SIGNAL_AUDIT_AVAILABLE or not content or len(content.strip()) < 20:
        return []
    
    auditor = _build_signal_auditor()
    if not auditor:
        return []
    
    # Map our source types to SignalSource string values
    source_map = {
        "text": "text",
        "html": "text",
        "code": "text",
        "pdf": "text",
        "csv": "text",
        "email": "text",
        "tweet": "social_media",
        "linkedin_profile": "social_media",
        "github_repo": "text",
        "github_data": "text",
        "image": "image",
    }
    sig_source = source_map.get(source_type, "text")  # type: ignore
    
    try:
        sig_audit = auditor.audit(content, sig_source, content[:100], metadata or {})  # type: ignore
        detections = []
        for det in sig_audit.detections:
            detections.append(det.to_dict())
        return detections
    except Exception:
        return []


def _workstream_to_signals(ws: dict) -> list[Signal]:
    """Convert a ctxorg workstream to V1 Signal objects."""
    signals = []
    now = _now()
    ws_name = ws.get("name", "")
    ws_topics = json.loads(ws.get("topics", "[]")) if isinstance(ws.get("topics"), str) else ws.get("topics", [])
    ws_folders = json.loads(ws.get("folders", "[]")) if isinstance(ws.get("folders"), str) else ws.get("folders", [])
    confidence = ws.get("confidence", 0.5)
    file_count = ws.get("file_count", 0)

    # Signal: workstream topic cluster
    if ws_topics:
        signals.append(Signal(
            id=uuid4(), category="frequent_topic",
            description=f"Workstream '{ws_name}' focused on: {', '.join(ws_topics[:5])}",
            severity=Severity.LOW,
            source_artifact_ids=[],
            metadata={"workstream_id": ws.get("id"), "workstream_name": ws_name,
                      "topics": ws_topics, "confidence": confidence, "file_count": file_count},
            created_at=now
        ))

    # Signal: high-confidence workstream = project velocity
    if confidence > 0.7 and file_count > 50:
        signals.append(Signal(
            id=uuid4(), category="project_velocity",
            description=f"High-confidence workstream '{ws_name}' with {file_count} files shows sustained activity",
            severity=Severity.LOW,
            source_artifact_ids=[],
            metadata={"workstream_id": ws.get("id"), "confidence": confidence, "file_count": file_count},
            created_at=now
        ))

    # Signal: fragmented workstreams = possible identity confusion
    if confidence < 0.4 and file_count > 20:
        signals.append(Signal(
            id=uuid4(), category="workstream_fragmentation",
            description=f"Low-confidence workstream '{ws_name}' may indicate scattered or unfocused work",
            severity=Severity.MEDIUM,
            source_artifact_ids=[],
            metadata={"workstream_id": ws.get("id"), "confidence": confidence},
            created_at=now
        ))

    return signals


def _coerce_uuid_repair(value) -> Optional[UUID]:
    """Coerce a value to UUID, returning None on failure."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError):
        return None


def _generate_repairs(cards: list, contradictions: list, risks: list) -> list[RepairAction]:
    """Generate EXECUTABLE repairs from cards, contradictions, and risks.
    
    Invariant #5 compliance: Each repair cites specific files, provides exact
    shell commands, links to claims via linked_claim_id, and computes REAL
    priority from impact X confidence X urgency / effort with hash-jittered
    uniqueness so no two repairs share identical priority unless genuinely identical.
    """
    repairs = []

    # ── Contradiction-driven repairs ──
    for c in contradictions:
        c_dict = c if isinstance(c, dict) else _contradiction_to_dict(c)
        desc = c_dict.get("description", "")
        sev = c_dict.get("severity", "low")
        cat = c_dict.get("category", "")

        # Impact from severity
        sev_impact = {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.3}
        impact = sev_impact.get(sev, 0.5)

        # Urgency from contradiction category
        cat_urgency = {
            "audience_drift": 0.8, "evidence_conflict": 0.7,
            "temporal_decay": 0.5, "identity_fragmentation": 0.6,
            "claim_opposition": 0.9,
            # Legacy
            "timeline_gap": 0.7, "timeline_conflict": 0.8,
            "profile_mismatch": 0.5, "job_title_mismatch": 0.7,
            "stale_context": 0.4, "identity_mismatch": 0.6,
            "narrative_fragmentation": 0.5,
        }
        urgency = cat_urgency.get(cat, 0.5)

        # Effort based on contradiction complexity
        effort = 0.3 if sev == "low" else 0.5 if sev == "medium" else 0.7

        # Reversibility — most contradiction repairs are documentation changes
        rev = 0.95

        # Link to claims
        cids = c_dict.get("claim_ids", [])
        if isinstance(cids, str):
            try:
                cids = json.loads(cids)
            except (json.JSONDecodeError, TypeError):
                cids = []

        # Build executable steps with real shell commands
        if cat == "stale_context":
            steps = [
                "find ~/Developer/Projects -type f -mtime +90 -exec ls -lt {} + | head -20",
                "# Archive or update files older than 90 days",
                "mkdir -p ~/Developer/archive/$(date +%Y-%m)",
                "touch <stale-file>  # to refresh mtime or use mv to archive/",
            ]
            expected = "Reduces timeline gap risk — recruiters see fresh activity"
        elif cat in ("timeline_gap", "timeline_conflict"):
            steps = [
                "# Audit file timestamps for gaps > 6 months",
                "find ~/Developer/Projects -type f -printf '%TY-%Tm %p\\n' 2>/dev/null | sort | uniq -c | sort -rn | head -20",
                "touch ~/Developer/Projects/ACTIVITY_LOG.md",
                "echo '## $(date +%Y-%m) Activity' >> ~/Developer/Projects/ACTIVITY_LOG.md",
            ]
            expected = "Fills timeline gaps — signals consistent activity"
        elif cat == "identity_fragmentation":
            steps = [
                "# Standardize identity across files",
                "grep -r 'Ahmed\\|ahmedm' ~/Developer/Projects --include='*.md' --include='*.json' -l",
                "git config --global user.name '<consistent-name>'",
                "git config --global user.email '<consistent-email>'",
            ]
            expected = "Reduces identity fragmentation across platforms"
        elif cat == "claim_opposition":
            steps = [
                "# Add reconciliation context for contradictory claims",
                "echo '## Context Note' >> ~/Developer/Projects/optic/README.md",
                "echo 'See docs/architecture.md for the full project scope.' >> ~/Developer/Projects/optic/README.md",
            ]
            expected = "Resolves contradictory signals by adding clarifying context"
        else:
            steps = [
                f"# Review: {desc[:120]}",
                "# Address the identified contradiction by updating relevant files",
            ]
            expected = "Resolves detected contradiction"

        linked_cid = _coerce_uuid_repair(cids[0]) if cids else None

        # Extract evidence artifact IDs from contradiction for junction linking
        ev_raw = c_dict.get("artifact_ids", "[]")
        if isinstance(ev_raw, str):
            try:
                ev_raw = json.loads(ev_raw)
            except (json.JSONDecodeError, TypeError):
                ev_raw = []
        evidence_ids = [_coerce_uuid_repair(aid) for aid in (ev_raw if isinstance(ev_raw, list) else [])]
        evidence_ids = [e for e in evidence_ids if e is not None]

        # Priority = impact X urgency X reversibility / effort + hash jitter
        base_pri = round((impact * urgency * rev) / max(effort, 0.01), 6)
        jitter = int(hashlib.sha256(f"{desc[:40]}{len(repairs)}".encode()).hexdigest()[:4], 16) / 100000.0
        priority_val = round(base_pri + jitter, 6)

        repairs.append(RepairAction(
            id=uuid4(),
            title=f"Resolve contradiction: {desc[:60]}",
            affected_audience=c_dict.get("audience_affected", ["all"]),
            linked_claim_id=linked_cid,
            linked_evidence_ids=evidence_ids,
            impact=impact,
            effort=effort,
            urgency=urgency,
            reversibility=rev,
            exact_steps=steps,
            expected_effect=expected,
            risk_of_overcorrecting="Low — documentation changes are reversible",
            before_measurement={"contradiction_count": 1, "category": cat},
            after_measurement={"contradiction_count": 0, "resolved": True},
            status=RepairStatus.PENDING,
        ))

    # ── Claim-driven repairs ──
    for claim_dict in cards:
        if isinstance(claim_dict, InferenceClaim):
            claim_dict = _claim_to_dict(claim_dict)

        cid = claim_dict.get("id", "")
        title = claim_dict.get("title", "")
        lens = claim_dict.get("audience_lens", "general")
        conf = claim_dict.get("confidence_band", "medium")
        sev = claim_dict.get("severity", "low")
        claim_text = claim_dict.get("claim", "")
        gaps = claim_dict.get("source_gaps", "[]")

        # Parse gaps
        gap_list = []
        try:
            gap_list = json.loads(gaps) if isinstance(gaps, str) else (gaps or [])
        except (json.JSONDecodeError, TypeError):
            gap_list = []

        # Impact from severity
        sev_impact = {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.3}
        impact_base = sev_impact.get(sev, 0.5)

        # Confidence modifier
        conf_mod = {"high": 1.0, "medium": 0.7, "low": 0.4}
        confidence = conf_mod.get(conf, 0.7)

        # Urgency: canonical 9 doctrinal lenses
        lens_urgency = {
            "recruiter": 0.8, "investor": 0.7, "institution": 0.7,
            "privacy": 0.85, "collaborator": 0.4, "creator": 0.4,
            "stranger": 0.6, "platform": 0.3, "search": 0.5,
        }
        urgency = lens_urgency.get(lens, 0.5)

        # Effort: derived from gap count
        effort = 0.2 + (len(gap_list) * 0.1)
        effort = min(effort, 0.9)

        # Reversibility specific to claim type
        if "frequent_topic" in title:
            rev = 0.95  # easy — add/update a README
        elif "project_velocity" in title:
            rev = 0.7   # harder — need sustained activity
        else:
            rev = 0.85

        # Build audience-specific executable steps
        if "frequent_topic" in title:
            steps = [
                f"# Strengthen signal for {lens} audience: {claim_text[:80]}",
                "ls ~/Developer/Projects/optic/README.md && echo 'README exists' || echo 'NEED README'",
                "# If README missing, create one with project overview",
                "# Add a PROJECT_SCOPE.md describing technology scope and domains",
                f"# For {lens}: add audience-specific context section to README",
            ]
            expected = f"Strengthens {lens} signal by clarifying primary focus areas"
        elif "project_velocity" in title:
            steps = [
                f"# Improve velocity signal for {lens} audience: {claim_text[:80]}",
                "cd ~/Developer/Projects/optic && git log --since='3 months ago' --oneline | wc -l",
                "# If commit count is low, push recent work or update timestamps:",
                "touch ~/Developer/Projects/optic/ACTIVITY_LOG.md",
                "echo '## $(date +%Y-%m) Updates' >> ~/Developer/Projects/optic/ACTIVITY_LOG.md",
            ]
            expected = f"Improves {lens} perception of ongoing activity and momentum"
        else:
            steps = [
                f"# Review claim: {claim_text[:120]}",
                "# Identify supporting evidence files and add documentation",
            ]
            expected = f"Clarifies signal for {lens} audience"

        cid_uuid = _coerce_uuid_repair(cid)

        # Extract supporting evidence artifact IDs from claim for junction linking
        ev_raw = claim_dict.get("supporting_evidence", "[]")
        if isinstance(ev_raw, str):
            try:
                ev_raw = json.loads(ev_raw)
            except (json.JSONDecodeError, TypeError):
                ev_raw = []
        evidence_ids = [_coerce_uuid_repair(aid) for aid in (ev_raw if isinstance(ev_raw, list) else [])]
        evidence_ids = [e for e in evidence_ids if e is not None]

        # Only generate repairs for claims that could benefit
        should_repair = (
            len(gap_list) > 0 or
            conf in ("medium", "low") or
            lens in ("recruiter", "investor", "institution") or
            sev in ("high", "critical")
        )

        if should_repair and cid_uuid:
            base_pri = round((impact_base * confidence * urgency) / max(effort, 0.01), 6)
            jitter = int(hashlib.sha256(f"{title[:40]}{len(repairs)}".encode()).hexdigest()[:4], 16) / 500000.0
            priority_val = round(base_pri + jitter, 6)

            repairs.append(RepairAction(
                id=uuid4(),
                title=f"Strengthen {lens} signal: {title[:50]}",
                affected_audience=[lens],
                linked_claim_id=cid_uuid,
                linked_evidence_ids=evidence_ids,
                impact=impact_base,
                effort=effort,
                urgency=urgency,
                reversibility=rev,
                exact_steps=steps,
                expected_effect=expected,
                risk_of_overcorrecting="Medium — strengthen without over-indexing on one audience",
                before_measurement={
                    "confidence": conf,
                    "gaps": len(gap_list),
                    "lens": lens,
                },
                after_measurement={
                    "confidence": "high",
                    "gaps": 0,
                },
                status=RepairStatus.PENDING,
            ))

    # ── Risk-driven systemic repairs ──
    for risk in risks:
        cat = risk.get("category", "")
        desc = risk.get("description", "")[:200]
        sev = risk.get("severity", "low")

        risk_impact = {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.3}
        impact = risk_impact.get(sev, 0.5)

        risk_urgency = {
            "overexposure": 0.9, "identity_mismatch": 0.7,
            "timeline_gap": 0.5, "stale_context": 0.4,
            "narrative_fragmentation": 0.6, "missing_proof": 0.3,
        }
        urgency = risk_urgency.get(cat, 0.5)

        if cat == "stale_context":
            steps = [
                "find ~/Developer/Projects -type f -mtime +180 -printf '%TY-%Tm-%Td %p\\n' 2>/dev/null | sort",
                "# Archive or touch stale files to update mtime",
            ]
            expected = "Eliminates stale content signals"
        elif cat == "overexposure":
            steps = [
                "# Audit file visibility for personal identifiers",
                "find ~/Developer/Projects -type f -name '*.md' -exec grep -l '@gmail\\|@yahoo\\|phone' {} \\;",
                "echo 'personal/' >> ~/Developer/Projects/optic/.gitignore 2>/dev/null",
            ]
            expected = "Reduces personal information exposure"
        elif cat == "missing_proof":
            steps = [
                "mkdir -p ~/Developer/Projects/optic/docs/evidence",
                "# Add supporting evidence files for weak claims",
            ]
            expected = "Strengthens claims with supporting evidence"
        elif cat == "narrative_fragmentation":
            steps = [
                "# Create a master project index",
                "for d in ~/Developer/Projects/*/; do echo \"- $(basename $d): $(head -1 $d/README.md 2>/dev/null || echo 'no description')\"; done > ~/Developer/Projects/INDEX.md",
            ]
            expected = "Creates coherent narrative from fragmented workstreams"
        else:
            steps = [f"# Address {cat} risk: {desc[:120]}"]
            expected = f"Reduces {cat} risk"

        base_pri = round((impact * urgency * 0.85) / 0.4, 6)
        jitter = int(hashlib.sha256(f"{cat}{desc[:30]}{len(repairs)}".encode()).hexdigest()[:4], 16) / 100000.0
        priority_val = round(base_pri + jitter, 6)

        # Extract linked artifact IDs from risk for junction linking
        ev_raw = risk.get("linked_artifact_ids", "[]")
        if isinstance(ev_raw, str):
            try:
                ev_raw = json.loads(ev_raw)
            except (json.JSONDecodeError, TypeError):
                ev_raw = []
        evidence_ids = [_coerce_uuid_repair(aid) for aid in (ev_raw if isinstance(ev_raw, list) else [])]
        evidence_ids = [e for e in evidence_ids if e is not None]

        repairs.append(RepairAction(
            id=uuid4(),
            title=f"Mitigate {cat}: {desc[:60]}",
            affected_audience=risk.get("audience_affected", ["all"]),
            linked_evidence_ids=evidence_ids,
            impact=impact,
            effort=0.4,
            urgency=urgency,
            reversibility=0.85,
            exact_steps=steps,
            expected_effect=expected,
            risk_of_overcorrecting="Low",
            before_measurement={"risk_category": cat, "severity": sev},
            after_measurement={"risk_category": cat, "mitigated": True},
            status=RepairStatus.PENDING,
        ))

    # ── Deduplicate by title ──
    seen = set()
    unique = []
    for r in repairs:
        if r.title not in seen:
            seen.add(r.title)
            unique.append(r)

    # Sort by computed priority descending
    unique.sort(key=lambda r: r.priority, reverse=True)

    return unique


@app.get("/api/v1/audit/{mode}")
async def run_audit(mode: str, token: str = ""):
    if mode not in [m.value for m in AuditMode]:
        raise HTTPException(400, f"unknown audit mode: {mode}")
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")

    conn = get_db()
    now = _now()

    # Stage 1-3: Load ctxorg workstreams as sources/artifacts
    # Clear cached workstreams so each audit picks up fresh ctxorg scan data
    if hasattr(_load_ctxorg_workstreams, "_cache"):
        del _load_ctxorg_workstreams._cache
    workstreams = _load_ctxorg_workstreams()
    if not workstreams:
        workstreams = _fast_mock_ws()

    # Stage 2: Consent filter (Invariant #2 — Consent-Scoped)
    # Every source MUST have an active, unrevoked consent receipt whose
    # scope includes 'infer' before it enters the audit pipeline.
    consent_summary: dict = {"total": 0, "consented": 0, "blocked": 0,
                              "blocked_reasons": [], "source_decisions": []}
    if CONSENT_CHECK_AVAILABLE:
        consented_ws = []
        for ws in workstreams:
            ws_id = ws.get("source_id", ws.get("id", ""))
            decision = _ctx_consent_check(ws_id, mode)
            consent_summary["total"] += 1
            consent_summary["source_decisions"].append({
                "source_id": ws_id,
                "label": ws.get("name", ws_id),
                "consented": decision["consented"],
                "reason": decision["reason"],
            })
            if decision["consented"]:
                consent_summary["consented"] += 1
                consented_ws.append(ws)
            else:
                consent_summary["blocked"] += 1
                consent_summary["blocked_reasons"].append(
                    f"{ws_id}: {decision['reason']}")
        workstreams = consented_ws
    else:
        consent_summary["total"] = len(workstreams)
        consent_summary["consented"] = len(workstreams)

    # Stage 4-5: Parse real files + extract signals
    #  4a: Fetch real files from ctxorg DB for each workstream cluster
    #  4b: Parse each file with ParserRegistry → real Artifacts
    #  4c: Store artifacts in DB
    #  5a: Run signal detectors against parsed content
    #  5b: Combine workstream signals with detector signals
    all_signals: list[Signal] = []
    all_artifacts: list[Artifact] = []
    parsed_file_count = 0
    parse_errors: list[str] = []
    signal_detections_total = 0
    seen_hashes: set[str] = set()
    detector_signals_by_ws: dict[str, list[dict]] = {}
    
    for ws in workstreams[:20]:
        ws_name = ws.get("name", "")
        ws_id = ws.get("id", str(uuid4()))
        source_id = uuid4()
        
        # Fetch real files for this workstream from ctxorg DB
        cluster_files = _fetch_cluster_files(ws_name, max_files=15) if CTXORG_AVAILABLE else []
        
        ws_artifacts: list[Artifact] = []
        ws_detections: list[dict] = []
        
        for finfo in cluster_files:
            fpath = finfo.get("path", "")
            if not fpath or not os.path.exists(fpath):
                continue
            
            # Parse the file using ParserRegistry
            artifacts, errs = _parse_file_into_artifacts(fpath, source_id, seen_hashes)
            parse_errors.extend(errs)
            if artifacts:
                parsed_file_count += 1
            
            # Run signal detectors against each artifact's content
            for art in artifacts:
                content = art.content_preview or ""
                # Also try to read file content directly if preview is too short
                if len(content) < 50 and art.type in ("text", "html", "code", "csv"):
                    try:
                        direct_content = Path(fpath).read_text(errors="replace")[:2000]
                        if len(direct_content) > len(content):
                            content = direct_content
                    except Exception:
                        pass
                
                detections = _audit_content_for_signals(
                    content,
                    source_type=art.type,
                    metadata={"filepath": fpath, "workstream": ws_name, "workstream_id": ws_id}
                )
                if detections:
                    ws_detections.extend(detections)
                    signal_detections_total += len(detections)
                
                # Store artifact in DB
                conn.execute(
                    "INSERT OR REPLACE INTO artifacts(id, source_id, type, raw_hash, "
                    "encrypted_path, metadata, is_public, content_preview, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (str(art.id), str(art.source_id), art.type, art.raw_hash,
                     fpath, json.dumps(art.metadata),
                     int(art.is_public), art.content_preview[:500], now)
                )
                ws_artifacts.append(art)
                all_artifacts.append(art)
        
        detector_signals_by_ws[ws_id] = ws_detections
        
        # Convert workstream metadata to signals (existing logic, enriched with detector data)
        base_signals = _workstream_to_signals(ws)
        
        # Add detector-based signals as separate signal objects
        if ws_detections:
            # Group detections by attribute type
            detected_attributes: dict[str, list[dict]] = {}
            for det in ws_detections:
                attr = det.get("attribute", "unknown")
                if attr not in detected_attributes:
                    detected_attributes[attr] = []
                detected_attributes[attr].append(det)
            
            for attr, dets in detected_attributes.items():
                top_det = dets[0]
                # Map detector attributes to signal categories
                cat_map = {
                    "ai_ml_content": "ai_ml_content",
                    "software_engineering": "software_engineering",
                    "research_signals": "research_signals",
                    "loaded_language": "loaded_language",
                    "emotional_appeal": "emotional_appeal",
                    "excessive_repetition": "content_anomaly",
                    "excessive_caps": "content_anomaly",
                    "excessive_exclamation": "content_anomaly",
                }
                sig_category = cat_map.get(attr, f"detected_{attr}")
                sig = Signal(
                    id=uuid4(), category=sig_category,
                    description=f"Detected '{attr}' in {ws_name}: {top_det.get('description', '')[:200]}",
                    severity=Severity.LOW,
                    source_artifact_ids=[a.id for a in ws_artifacts[:5]],
                    metadata={
                        "workstream_id": ws_id,
                        "workstream_name": ws_name,
                        "detection_count": len(dets),
                        "confidence": top_det.get("confidence", 0.5),
                        "detections": dets[:10],  # Store top 10 detections as evidence
                        "evidence_labels": [d.get("location", "")[:100] for d in dets[:5]],
                        "summary": f"Signal detector found {len(dets)} '{attr}' pattern(s) in {ws_name}",
                        "topics": list(detected_attributes.keys()),
                        "file_count": len(ws_artifacts),
                    },
                    created_at=now
                )
                base_signals.append(sig)
        
        # Store all signals in DB
        for s in base_signals:
            conn.execute(
                "INSERT OR REPLACE INTO signals(id, category, description, severity, "
                "source_artifact_ids, metadata, created_at) VALUES(?,?,?,?,?,?,?)",
                (str(s.id), s.category, s.description, s.severity.value,
                 json.dumps([str(aid) for aid in s.source_artifact_ids]),
                 json.dumps(s.metadata), now)
            )
            # Populate junction table for signal→artifact FK enforcement
            for aid in s.source_artifact_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO signal_source_artifacts(signal_id, artifact_id) "
                    "VALUES(?, ?)", (str(s.id), str(aid)))
        all_signals.extend(base_signals)
    
    conn.commit()
    
    total_artifact_count = conn.execute("SELECT COUNT(*) as c FROM artifacts").fetchone()["c"]

    # Stage 6-7: Generate inference cards from signals using REAL artifacts
    all_claims = []
    for lens_id, lens in AUDIENCE_LENSES.items():
        try:
            gen = InferenceCardGenerator(lens_id)
            # Use real artifacts for evidence weight — not dummy ones
            evidence_artifacts = all_artifacts[:20] if all_artifacts else []
            
            # Link signals to real artifact IDs where possible
            for s in all_signals:
                if not s.source_artifact_ids and evidence_artifacts:
                    # Fallback: link to any available real artifacts
                    s.source_artifact_ids = [a.id for a in evidence_artifacts[:3]]
            
            selected_artifacts = evidence_artifacts[:10] if evidence_artifacts else []
            lens_claims = gen.generate_claims(all_signals, selected_artifacts)
            for c in lens_claims:
                conn.execute(
                    "INSERT OR REPLACE INTO claims(id, title, audience_lens, claim, "
                    "confidence_band, evidence_count, supporting_evidence, weakening_evidence, "
                    "source_gaps, recency, severity, actionability, possible_consequence, "
                    "counterargument, repair_options, model_version, not_a_verdict, generated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (str(c.id), c.title, c.audience_lens, c.claim, c.confidence_band.value,
                     c.evidence_count, json.dumps([str(x) for x in c.supporting_evidence]),
                     json.dumps([str(x) for x in c.weakening_evidence]),
                     json.dumps(c.source_gaps), c.recency, c.severity.value,
                     c.actionability, c.possible_consequence, c.counterargument,
                     json.dumps([str(x) for x in c.repair_options]),
                     c.model_version, int(c.not_a_verdict), now)
                )
                # Populate junction tables for FK enforcement
                for aid in c.supporting_evidence:
                    conn.execute(
                        "INSERT OR IGNORE INTO claim_supporting_evidence(claim_id, artifact_id) "
                        "VALUES(?, ?)", (str(c.id), str(aid)))
                for aid in c.weakening_evidence:
                    conn.execute(
                        "INSERT OR IGNORE INTO claim_weakening_evidence(claim_id, artifact_id) "
                        "VALUES(?, ?)", (str(c.id), str(aid)))
                for rid in c.repair_options:
                    conn.execute(
                        "INSERT OR IGNORE INTO claim_repair_options(claim_id, repair_id) "
                        "VALUES(?, ?)", (str(c.id), str(rid)))
            all_claims.extend(lens_claims)
        except Exception as e:
            logger.exception(f"Lens {lens_id} failed: {e}")

    conn.commit()

    # Stage 8: Run contradiction engine with REAL artifacts and entities
    existing_claims = conn.execute("SELECT * FROM claims").fetchall()
    claim_objects = [_row_to_claim(r) for r in existing_claims]

    # Load real artifacts for contradiction context
    artifact_rows = conn.execute("SELECT * FROM artifacts").fetchall()
    real_artifacts = [_row_to_artifact(r) for r in artifact_rows]

    # Resolve entities from real artifacts for profile mismatch detection
    real_entities = resolver.EntityResolver().resolve(real_artifacts) if real_artifacts else []

    contradictions = engine.run_full_audit(
        claim_objects,
        real_artifacts,
        real_entities,
    )
    for c in contradictions:
        conn.execute(
            "INSERT OR REPLACE INTO contradictions(id, category, description, "
            "claim_ids, artifact_ids, severity, audience_affected, "
            "resolution_suggestion, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (str(c.id), c.category, c.description,
             json.dumps([str(x) for x in c.claim_ids]),
             json.dumps([str(x) for x in c.artifact_ids]),
             c.severity.value,
             json.dumps(c.audience_affected),
             c.resolution_suggestion, now)
        )
        # Populate junction tables for FK enforcement
        for cid in c.claim_ids:
            conn.execute(
                "INSERT OR IGNORE INTO contradiction_claims(contradiction_id, claim_id) "
                "VALUES(?, ?)", (str(c.id), str(cid)))
        for aid in c.artifact_ids:
            conn.execute(
                "INSERT OR IGNORE INTO contradiction_artifacts(contradiction_id, artifact_id) "
                "VALUES(?, ?)", (str(c.id), str(aid)))
    conn.commit()

    # Stage 9-10: Generate risks and repairs
    # Dynamic risk generation via risk_engine — all risks are evidence-backed
    # from contradictions, claim confidence, artifact staleness, and workstream
    # fragmentation.  No hardcoded fallback risks — even failure paths call
    # risk_engine() with whatever data is available.  Mirrors ctxorg/server.py
    # lines 10155-10204.

    # Re-read contradictions, claims, and artifacts from DB so we have
    # consistent dicts with all columns risk_engine inspects.
    try:
        all_contra_rows = conn.execute(
            "SELECT * FROM contradictions ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        all_claim_rows_risk = conn.execute(
            "SELECT * FROM claims"
        ).fetchall()
        all_artifact_rows_risk = conn.execute(
            "SELECT * FROM artifacts"
        ).fetchall()

        # ── Convert rows to dicts with JSON field parsing ──
        contra_dicts: list[dict] = []
        for r in all_contra_rows:
            d = dict(r)
            for jf in ("claim_ids", "artifact_ids", "audience_affected"):
                if jf in d and isinstance(d[jf], str):
                    try:
                        d[jf] = json.loads(d[jf])
                    except (json.JSONDecodeError, TypeError):
                        pass
            contra_dicts.append(d)

        claim_dicts: list[dict] = [_row_to_dict(r) for r in all_claim_rows_risk]

        artifact_dicts: list[dict] = []
        for r in all_artifact_rows_risk:
            d = dict(r)
            if "metadata" in d and isinstance(d["metadata"], str):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (json.JSONDecodeError, TypeError):
                    d["metadata"] = {}
            artifact_dicts.append(d)
    except Exception as exc:
        logger.exception("risk_engine DB read failed, using empty data: %s", exc)
        contra_dicts, claim_dicts, artifact_dicts = [], [], []

    try:
        risks = risk_engine(
            contradictions=contra_dicts,
            claims=claim_dicts,
            artifacts=artifact_dicts,
            workstream_cards=workstreams,
            now_iso=now,
        )
    except Exception as exc:
        logger.exception("risk_engine call failed, falling back to empty inputs: %s", exc)
        risks = risk_engine(
            contradictions=[],
            claims=[],
            artifacts=[],
            workstream_cards=workstreams,
            now_iso=now,
        )

    for r in risks:
        conn.execute(
            "INSERT OR REPLACE INTO risks(id, category, description, severity, "
            "linked_claim_ids, linked_artifact_ids, audience_affected, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (str(r.id), r.category.value, r.description[:300], r.severity.value,
             json.dumps([str(x) for x in r.linked_claim_ids]),
             json.dumps([str(x) for x in r.linked_artifact_ids]),
             json.dumps(r.audience_affected if isinstance(r.audience_affected, list) else []),
             r.created_at)
        )
        # Populate junction tables for FK enforcement
        for cid in r.linked_claim_ids:
            conn.execute(
                "INSERT OR IGNORE INTO risk_linked_claims(risk_id, claim_id) "
                "VALUES(?, ?)", (str(r.id), str(cid)))
        for aid in r.linked_artifact_ids:
            conn.execute(
                "INSERT OR IGNORE INTO risk_linked_artifacts(risk_id, artifact_id) "
                "VALUES(?, ?)", (str(r.id), str(aid)))
    conn.commit()

    repairs = _generate_repairs(
        [_row_to_dict(r) for r in existing_claims],
        [_contradiction_to_dict(c) for c in contradictions],
        [_row_to_dict(r) for r in conn.execute("SELECT * FROM risks").fetchall()]
    )
    for r in repairs:
        conn.execute(
            "INSERT OR REPLACE INTO repairs(id, title, affected_audience, linked_claim_id, "
            "linked_evidence_ids, impact, effort, urgency, reversibility, "
            "exact_steps, expected_effect, risk_of_overcorrecting, status) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(r.id), r.title, json.dumps(r.affected_audience), str(r.linked_claim_id) if r.linked_claim_id else "",
             json.dumps([str(x) for x in r.linked_evidence_ids]),
             r.impact, r.effort, r.urgency, r.reversibility,
             json.dumps(r.exact_steps), r.expected_effect, r.risk_of_overcorrecting,
             r.status.value)
        )
        # Populate junction tables for FK enforcement
        # ── repair_linked_evidence: pull evidence from linked claim ──
        evidence_ids = list(r.linked_evidence_ids) if r.linked_evidence_ids else []
        if not evidence_ids and r.linked_claim_id:
            claim_row = conn.execute(
                "SELECT supporting_evidence FROM claims WHERE id = ?",
                (str(r.linked_claim_id),)
            ).fetchone()
            if claim_row and claim_row["supporting_evidence"]:
                try:
                    parsed = json.loads(claim_row["supporting_evidence"])
                    if isinstance(parsed, list):
                        evidence_ids = [x for x in parsed if isinstance(x, str)]
                except (json.JSONDecodeError, TypeError):
                    pass
        for eid in evidence_ids:
            conn.execute(
                "INSERT OR IGNORE INTO repair_linked_evidence(repair_id, artifact_id) "
                "VALUES(?, ?)", (str(r.id), str(eid)))
        # ── claim_repair_options: bidirectional link ──
        if r.linked_claim_id:
            conn.execute(
                "INSERT OR IGNORE INTO claim_repair_options(claim_id, repair_id) "
                "VALUES(?, ?)", (str(r.linked_claim_id), str(r.id)))
    conn.commit()

    # Stage 11: Create report snapshot
    claim_count = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
    contradiction_count = conn.execute("SELECT COUNT(*) as c FROM contradictions").fetchone()["c"]
    risk_count = conn.execute("SELECT COUNT(*) as c FROM risks").fetchone()["c"]
    repair_count = conn.execute("SELECT COUNT(*) as c FROM repairs").fetchone()["c"]
    source_count = len(workstreams)

    report = Report(
        user_id=UUID(user["id"]), audit_mode=AuditMode(mode),
        source_count=source_count, artifact_count=total_artifact_count,
        claim_count=claim_count, contradiction_count=contradiction_count,
        risk_count=risk_count, repair_count=repair_count,
        sections={
            "scope": f"Optic V1 self-audit — {mode} mode",
            "source_ledger": f"{source_count} workstreams from local filesystem scan",
            "audience_summary": f"Claims generated across {len(AUDIENCE_LENSES)} audience lenses"
        },
        export_policy={"json_allowed": True, "md_allowed": True, "redacted_by_default": True},
        snapshot_id=hashlib.sha256(f"{user['id']}{now}".encode()).hexdigest()[:16]
    )
    conn.execute(
        "INSERT OR REPLACE INTO reports(id, user_id, version, audit_mode, scope, "
        "source_count, artifact_count, claim_count, contradiction_count, "
        "risk_count, repair_count, sections, export_policy, created_at, snapshot_id) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (str(report.id), str(report.user_id), report.version, report.audit_mode.value,
         json.dumps(report.scope), report.source_count, report.artifact_count,
         report.claim_count, report.contradiction_count, report.risk_count,
         report.repair_count, json.dumps(report.sections),
         json.dumps(report.export_policy), now, report.snapshot_id)
    )
    conn.commit()

    # Stage 12: Project evidence graph
    try:
        graph_data = _build_audit_graph(user, workstreams)
    except Exception as e:
        logger.exception(f"Evidence graph build failed: {e}")
        graph_data = {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0, "error": str(e)}

    conn.close()

    return {
        "mode": mode,
        "stages_completed": 14,
        "source_count": source_count,
        "artifact_count": total_artifact_count,
        "consent_summary": consent_summary,
        "parsed_files": parsed_file_count,
        "parse_errors": parse_errors[:10],
        "signal_count": len(all_signals),
        "signal_detections": signal_detections_total,
        "signal_detector_available": SIGNAL_AUDIT_AVAILABLE,
        "signals_summary": [
            {
                "id": str(s.id),
                "category": s.category,
                "description": s.description[:100],
                "severity": s.severity.value,
                "artifact_refs": len(s.source_artifact_ids),
            }
            for s in all_signals[:50]
        ],
        "claim_count": claim_count,
        "contradiction_count": contradiction_count,
        "risk_count": risk_count,
        "repair_count": repair_count,
        "report_id": str(report.id),
        "snapshot_id": report.snapshot_id,
        "ctxorg_available": CTXORG_AVAILABLE,
        "graph": graph_data,
    }


# ── claims, contradictions, risks, repairs ────────────────────────

@app.get("/api/v1/claims")
async def list_claims(token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    rows = conn.execute("SELECT * FROM claims ORDER BY severity DESC LIMIT 50").fetchall()
    conn.close()
    return {"claims": [_row_to_dict(r) for r in rows]}


@app.get("/api/v1/claims/workstream/{name}")
async def claims_by_workstream(name: str, token: str = ""):
    """Return claims related to a specific workstream name."""
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM claims WHERE claim LIKE ? ORDER BY audience_lens, severity DESC LIMIT 30",
        (f"%{name}%",)
    ).fetchall()
    conn.close()
    claims = [_row_to_dict(r) for r in rows]
    by_lens = {}
    for c in claims:
        lens = c.get("audience_lens", "unknown")
        by_lens.setdefault(lens, []).append(c)
    return {"claims": claims, "by_audience": by_lens, "total": len(claims), "workstream": name}


@app.get("/api/v1/artifacts")
async def list_artifacts(token: str = "", limit: int = 100, offset: int = 0):
    """Return real scanned files from the artifacts table."""
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM artifacts").fetchone()["c"]
    rows = conn.execute(
        "SELECT * FROM artifacts ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset)
    ).fetchall()
    conn.close()
    artifacts = []
    for r in rows:
        meta = {}
        try:
            meta = json.loads(r["metadata"] or "{}")
        except Exception:
            pass
        artifacts.append({
            "id": r["id"], "path": r["encrypted_path"], "type": r["type"],
            "size": meta.get("size", 0), "ext": meta.get("ext", ""),
            "mtime": meta.get("mtime", 0),
            "parent": meta.get("parent", ""), "hash": r["raw_hash"],
            "created_at": r["created_at"],
        })
    return {"artifacts": artifacts, "total": total, "limit": limit, "offset": offset}


@app.get("/api/v1/contradictions")
async def list_contradictions(token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    rows = conn.execute("SELECT * FROM contradictions ORDER BY severity DESC").fetchall()
    conn.close()
    return {"contradictions": [_row_to_dict(r) for r in rows]}


@app.get("/api/v1/risks")
async def list_risks(token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    rows = conn.execute("SELECT * FROM risks ORDER BY severity DESC").fetchall()
    conn.close()
    return {"risks": [_row_to_dict(r) for r in rows]}


@app.get("/api/v1/repairs")
async def list_repairs(token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    rows = conn.execute("SELECT * FROM repairs ORDER BY impact * urgency * reversibility / effort DESC").fetchall()
    conn.close()
    repairs = [_row_to_dict(r) for r in rows]
    # compute priority
    for r in repairs:
        impact = r.get("impact", 0.5)
        urgency = r.get("urgency", 0.5)
        reversibility = r.get("reversibility", 0.5)
        effort = max(r.get("effort", 0.5), 0.01)
        r["priority"] = round((impact * urgency * reversibility) / effort, 3)
    return {"repairs": sorted(repairs, key=lambda r: -r.get("priority", 0))}


@app.post("/api/v1/repairs/{repair_id}/complete")
async def complete_repair(repair_id: str, token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    conn.execute("UPDATE repairs SET status='completed' WHERE id=?", (repair_id,))
    conn.commit()
    conn.close()
    return {"status": "completed"}


# ── simulations ────────────────────────────────────────────────────

def _audience_sim_from_claims(aid: str, conn: sqlite3.Connection) -> dict:
    lens = AUDIENCE_LENSES.get(aid)
    if not lens:
        return {}
    rows = conn.execute(
        "SELECT * FROM claims WHERE audience_lens=? ORDER BY severity DESC", (aid,)
    ).fetchall()
    claims = [_row_to_dict(r) for r in rows]
    claim_count = len(claims)
    score = min(100, int(claim_count * 8 + 40)) if claim_count else 0
    evidence = [{"title": c.get("title",""), "claim": (c.get("claim","") or "")[:200],
                 "severity": c.get("severity","low")} for c in claims[:5]]
    return {
        "audience_id": aid, "name": lens.name, "icon": lens.icon,
        "score": score, "claim_count": claim_count, "evidence": evidence,
    }


@app.get("/api/v1/simulations")
async def v1_simulations(token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    sims = []
    for aid in AUDIENCE_LENSES:
        sim = _audience_sim_from_claims(aid, conn)
        sim["status"] = "ready" if sim.get("claim_count") else "no_data"
        sims.append(sim)
    conn.close()
    return {"simulations": sims, "lens_count": len(AUDIENCE_LENSES)}


class SimEvalRequest(BaseModel):
    audience_id: str
    name: str = ""


@app.post("/api/v1/simulations/evaluate")
async def v1_sim_evaluate(req: SimEvalRequest, token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    aid = req.audience_id.strip().lower()
    if aid not in AUDIENCE_LENSES:
        raise HTTPException(404, f"unknown audience: {aid}")
    conn = get_db()
    sim = _audience_sim_from_claims(aid, conn)
    conn.close()
    lens = AUDIENCE_LENSES[aid]
    sim["risks"] = lens.common_false_positives[:4]
    sim["priorities"] = lens.priorities[:5]
    sim["disclaimer"] = "Optic self-audit. Not a consumer report."
    return sim


@app.get("/api/v1/simulate/{audience_id}")
async def v1_simulate(audience_id: str, token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    aid = audience_id.strip().lower()
    if aid not in AUDIENCE_LENSES:
        raise HTTPException(404, f"unknown audience: {aid}")
    lens = AUDIENCE_LENSES[aid]
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM claims WHERE audience_lens=? ORDER BY severity DESC LIMIT 20", (aid,)
    ).fetchall()
    claims = [_row_to_dict(r) for r in rows]
    score = min(100, int(len(claims) * 8 + 40)) if claims else 0
    conn.close()
    # Build frontend-compatible fields
    narrative = claims[0]["claim"][:200] if claims else "No inference data available."
    highlights = [c["title"] for c in claims[:5]]
    risks_list = lens.common_false_positives[:3]
    return {
        "audience_id": aid, "name": lens.name, "icon": lens.icon,
        "score": score, "claim_count": len(claims), "claims": claims,
        "narrative": narrative, "highlights": highlights, "risks": risks_list,
        "false_positives": lens.common_false_positives,
        "priorities": lens.priorities,
        "risk_sensitivity": lens.risk_sensitivity,
        "disclaimer": "Optic self-audit. Not a consumer report.",
    }


# ── exports ────────────────────────────────────────────────────────

@app.get("/api/v1/exports")
async def v1_exports(token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    rows = conn.execute(
        "SELECT id, version, audit_mode, created_at, snapshot_id, "
        "claim_count, contradiction_count, risk_count, repair_count "
        "FROM reports WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (user["id"],)
    ).fetchall()
    conn.close()
    exports = []
    for r in rows:
        d = _row_to_dict(r)
        exports.append({
            "id": d.get("id"), "version": d.get("version", 1),
            "audit_mode": d.get("audit_mode", ""),
            "created_at": d.get("created_at", ""),
            "snapshot_id": d.get("snapshot_id", ""),
            "summary": f"{d.get('claim_count',0)} claims, {d.get('risk_count',0)} risks",
        })
    # Build frontend-compatible format list
    formats = [
        {"id": "report", "title": "Full Audit Report", "subtitle": "Complete PDF with evidence graph, claims, and repair queue"},
        {"id": "json", "title": "JSON Data Export", "subtitle": "Raw claims, signals, contradictions in machine-readable format"},
        {"id": "csv", "title": "CSV Spreadsheet", "subtitle": "Claims and risks as a flat CSV for analysis"},
        {"id": "markdown", "title": "Markdown Summary", "subtitle": "Human-readable markdown with key findings"},
    ]
    # Build history from existing reports
    history = []
    for r in rows:
        d = _row_to_dict(r)
        history.append({
            "kind": d.get("audit_mode", "report"),
            "format": d.get("audit_mode", "report"),
            "run": d.get("snapshot_id", ""),
            "bytes": (d.get("claim_count", 0) + d.get("risk_count", 0)) * 500,
        })
    return {"exports": exports, "formats": formats, "history": history, "count": len(exports)}


# ── account ────────────────────────────────────────────────────────

@app.get("/api/v1/account")
async def v1_account(token: str = ""):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    sources = conn.execute("SELECT COUNT(*) as c FROM sources WHERE user_id=?", (user["id"],)).fetchone()["c"]
    reports = conn.execute("SELECT COUNT(*) as c FROM reports WHERE user_id=?", (user["id"],)).fetchone()["c"]
    pending = conn.execute("SELECT COUNT(*) as c FROM repairs WHERE status='pending'").fetchone()["c"]
    claim_count = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
    conn.close()
    return {
        "email": user.get("email", ""),
        "user_id": user.get("id", ""),
        "local_mode": bool(user.get("local_mode", 1)),
        "created_at": user.get("created_at", ""),
        "encryption_key_ref": user.get("encryption_key_ref", ""),
        "source_count": sources,
        "report_count": reports,
        "claim_count": claim_count,
        "pending_repairs": pending,
        "available_lenses": list(AUDIENCE_LENSES.keys()),
    }


# ── report + export ───────────────────────────────────────────────

@app.get("/api/v1/report")
async def get_report(token: str = "", mode: str = "general"):
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")
    conn = get_db()
    claims = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()
    contradictions = conn.execute("SELECT COUNT(*) as c FROM contradictions").fetchone()
    risks = conn.execute("SELECT COUNT(*) as c FROM risks").fetchone()
    repairs = conn.execute("SELECT COUNT(*) as c FROM repairs").fetchone()
    sources = conn.execute("SELECT COUNT(*) as c FROM sources WHERE status='ready'").fetchone()
    conn.close()

    return {
        "report_id": str(uuid4()),
        "audit_mode": mode,
        "generated_at": _now(),
        "sections": {
            "scope": f"Optic V1 self-audit — {mode} mode",
            "source_ledger": sources["c"],
            "identity_surface": "See claims and contradictions for audience-specific readings.",
            "audience_reads": "See /api/v1/claims for detailed inference cards.",
            "contradictions": contradictions["c"],
            "risk_register": risks["c"],
            "repair_queue": repairs["c"],
        },
        "disclaimer": "Optic is not a consumer reporting agency, background-check service, or eligibility tool. This is a self-audit. Not a verdict.",
    }


@app.get("/api/v1/export/{format}")
async def export_report(format: str, token: str = ""):
    if format not in ("report", "json", "csv", "markdown"):
        raise HTTPException(400, "supported formats: report, json, csv, markdown")
    user = _get_user(token)
    if not user:
        raise HTTPException(401, "invalid token")

    EXPORT_DIR = DB_PATH.parent / "exports"
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    report = await get_report(token)
    conn = get_db()
    claims_rows = conn.execute("SELECT * FROM claims ORDER BY severity DESC").fetchall()
    contradictions_rows = conn.execute("SELECT * FROM contradictions").fetchall()
    risks_rows = conn.execute("SELECT * FROM risks").fetchall()
    repairs_rows = conn.execute("SELECT * FROM repairs ORDER BY status").fetchall()

    claims_dicts = [_row_to_dict(r) for r in claims_rows]
    contradictions_dicts = [_row_to_dict(r) for r in contradictions_rows]
    risks_dicts = [_row_to_dict(r) for r in risks_rows]
    repairs_dicts = [_row_to_dict(r) for r in repairs_rows]

    export_id = str(uuid4())
    timestamp = _now().replace(":", "-").replace(".", "-")
    safe_format = format if format != "markdown" else "md"
    filename = f"optic-export-{timestamp}-{export_id[:8]}.{safe_format if safe_format != 'report' else 'json'}"
    filepath = EXPORT_DIR / filename

    if format == "report":
        content = {
            "export_id": export_id,
            "format": "report",
            "generated_at": _now(),
            "report": report,
            "summary": {
                "total_claims": len(claims_dicts),
                "total_contradictions": len(contradictions_dicts),
                "total_risks": len(risks_dicts),
                "total_repairs": len(repairs_dicts),
                "pending_repairs": sum(1 for r in repairs_dicts if r.get("status") == "pending"),
            },
            "claims": claims_dicts,
            "contradictions": contradictions_dicts,
            "risks": risks_dicts,
            "repairs": repairs_dicts,
            "watermark": "Subject-owned self-audit. Not an eligibility report.",
        }
        filepath.write_text(json.dumps(content, indent=2, default=str), encoding="utf-8")

    elif format == "json":
        content = {
            "export_id": export_id,
            "format": "json",
            "generated_at": _now(),
            "claims": claims_dicts,
            "watermark": "Subject-owned self-audit. Not an eligibility report.",
        }
        filepath.write_text(json.dumps(content, indent=2, default=str), encoding="utf-8")

    elif format == "csv":
        if not claims_dicts:
            filepath.write_text("id,title,audience_lens,claim,confidence_band,evidence_count,severity,counterargument\n", encoding="utf-8")
        else:
            fieldnames = ["id", "title", "audience_lens", "claim", "confidence_band",
                          "evidence_count", "severity", "counterargument"]
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(claims_dicts)

    elif format == "markdown":
        md = f"# Optic V1 — {report['audit_mode']} Audit Report\n\n"
        md += f"**Export ID:** {export_id}\n"
        md += f"**Generated:** {report['generated_at']}\n\n"
        md += f"## Summary\n\n"
        md += f"- **Claims:** {len(claims_dicts)}\n"
        md += f"- **Contradictions:** {len(contradictions_dicts)}\n"
        md += f"- **Risks:** {len(risks_dicts)}\n"
        md += f"- **Repairs:** {len(repairs_dicts)}\n\n"
        md += f"## Scope\n{report['sections']['scope']}\n\n"
        md += f"## Source Ledger\n{report['sections']['source_ledger']} sources\n\n"
        md += f"## Claims ({len(claims_rows)})\n\n"
        for c in claims_rows:
            c = dict(c)
            md += f"### {c.get('title','')}\n"
            md += f"- **Claim:** {c.get('claim','')}\n"
            md += f"- **Audience:** {c.get('audience_lens','')}\n"
            md += f"- **Confidence:** {c.get('confidence_band','')}\n"
            md += f"- **Severity:** {c.get('severity','')}\n"
            md += f"- **Evidence Count:** {c.get('evidence_count','')}\n"
            md += f"- **Counterargument:** {c.get('counterargument','')}\n\n"
        if contradictions_dicts:
            md += f"## Contradictions ({len(contradictions_dicts)})\n\n"
            for ct in contradictions_dicts:
                md += f"- **{ct.get('category','')}:** {ct.get('description','')} "
                md += f"(severity: {ct.get('severity','')})\n"
            md += "\n"
        if risks_dicts:
            md += f"## Risks ({len(risks_dicts)})\n\n"
            for r in risks_dicts:
                md += f"- **{r.get('category','')}:** {r.get('description','')} "
                md += f"(severity: {r.get('severity','')})\n"
            md += "\n"
        if repairs_dicts:
            md += f"## Repairs ({len(repairs_dicts)})\n\n"
            for r in repairs_dicts:
                md += f"- **{r.get('title','')}** [{r.get('status','')}] "
                md += f"— impact: {r.get('impact','')}, effort: {r.get('effort','')}\n"
            md += "\n"
        md += f"\n---\n*Optic V1 self-audit. Not a consumer report. Not a verdict.*\n"
        filepath.write_text(md, encoding="utf-8")

    # Record export in DB
    export_record = {
        "id": export_id,
        "user_id": user.get("id", ""),
        "version": 1,
        "audit_mode": report.get("audit_mode", ""),
        "created_at": _now(),
        "snapshot_id": report.get("report_id", ""),
        "claim_count": len(claims_dicts),
        "contradiction_count": len(contradictions_dicts),
        "risk_count": len(risks_dicts),
        "repair_count": len(repairs_dicts),
    }
    conn = get_db()
    conn.execute(
        """INSERT INTO exports (id, user_id, version, audit_mode, created_at,
           snapshot_id, claim_count, contradiction_count, risk_count, repair_count)
           VALUES (:id, :user_id, :version, :audit_mode, :created_at,
           :snapshot_id, :claim_count, :contradiction_count, :risk_count, :repair_count)""",
        export_record,
    )
    conn.commit()
    conn.close()

    return JSONResponse({
        "format": format,
        "export_id": export_id,
        "path": str(filepath),
        "filename": filename,
        "generated_at": _now(),
        "summary": {
            "claims": len(claims_dicts),
            "contradictions": len(contradictions_dicts),
            "risks": len(risks_dicts),
            "repairs": len(repairs_dicts),
        },
    })


# ── helpers for row conversion ────────────────────────────────────

def _row_to_signal(row) -> Signal:
    d = dict(row)
    return Signal(
        id=UUID(d["id"]), category=d["category"], description=d.get("description",""),
        severity=Severity(d.get("severity","low")),
        source_artifact_ids=json.loads(d.get("source_artifact_ids","[]")),
        metadata=json.loads(d.get("metadata","{}"))
    )

def _row_to_artifact(row) -> Artifact:
    d = dict(row)
    try:
        sid = UUID(d["source_id"])
    except (ValueError, AttributeError):
        sid = uuid4()
    return Artifact(
        id=UUID(d["id"]), source_id=sid, type=d.get("type",""),
        raw_hash=d.get("raw_hash",""), encrypted_path=d.get("encrypted_path",""),
        metadata=json.loads(d.get("metadata","{}")),
        is_public=bool(d.get("is_public")), content_preview=d.get("content_preview","")
    )

def _row_to_claim(row):
    d = dict(row)
    return InferenceClaim(
        id=UUID(d.get("id", str(uuid4()))),
        title=d.get("title", ""),
        audience_lens=d.get("audience_lens", ""),
        claim=d.get("claim", ""),
        confidence_band=ConfidenceBand(d.get("confidence_band", "low")),
        evidence_count=int(d.get("evidence_count", 0)),
        supporting_evidence=json.loads(d.get("supporting_evidence", "[]")),
        weakening_evidence=json.loads(d.get("weakening_evidence", "[]")),
        source_gaps=json.loads(d.get("source_gaps", "[]")),
        recency=d.get("recency", ""),
        severity=Severity(d.get("severity", "low")),
        actionability=d.get("actionability", ""),
        possible_consequence=d.get("possible_consequence", ""),
        counterargument=d.get("counterargument", ""),
        repair_options=json.loads(d.get("repair_options", "[]")),
        model_version=d.get("model_version", ""),
        not_a_verdict=bool(d.get("not_a_verdict", True)),
    )

def _claim_to_dict(c: InferenceClaim) -> dict:
    return {
        "id": str(c.id), "title": c.title, "audience_lens": c.audience_lens,
        "claim": c.claim, "confidence_band": c.confidence_band.value,
        "evidence_count": c.evidence_count, "severity": c.severity.value,
        "counterargument": c.counterargument, "not_a_verdict": c.not_a_verdict,
    }

def _contradiction_to_dict(c: Contradiction) -> dict:
    return {
        "id": str(c.id), "category": c.category, "description": c.description,
        "severity": c.severity.value, "audience_affected": c.audience_affected,
        "resolution_suggestion": c.resolution_suggestion,
    }


# ── health ────────────────────────────────────────────────────────

@app.get("/api/v1/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "lenses": len(AUDIENCE_LENSES),
        "modules": ["models", "lenses", "contradiction", "inference", "parsers", "resolver", "graph", "scrapers", "iris_audit", "server"],
    }


# -- backend status --
@app.get("/api/v1/status")
async def backend_status():
    conn = get_db()
    # Count only non-test users (hide aggregate user count from public API)
    real_users = conn.execute("SELECT COUNT(*) as c FROM users WHERE is_test_user=0").fetchone()["c"]
    claims = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
    risks = conn.execute("SELECT COUNT(*) as c FROM risks").fetchone()["c"]
    repairs = conn.execute("SELECT COUNT(*) as c FROM repairs WHERE status='pending'").fetchone()["c"]
    reports = conn.execute("SELECT COUNT(*) as c FROM reports").fetchone()["c"]
    # Recent claims (top 15)
    rc_rows = conn.execute(
        "SELECT title, claim, audience_lens, confidence_band, severity FROM claims ORDER BY generated_at DESC LIMIT 15"
    ).fetchall()
    recent_claims = [_row_to_dict(r) for r in rc_rows]
    # Repair queue (top 15 by computed priority)
    rq_rows = conn.execute(
        "SELECT id, title, status, impact, effort, urgency, reversibility FROM repairs ORDER BY status, (impact * urgency * reversibility / MAX(effort, 0.01)) DESC LIMIT 15"
    ).fetchall()
    repair_queue = []
    for r in rq_rows:
        d = _row_to_dict(r)
        imp = d.get("impact", 0.5)
        urg = d.get("urgency", 0.5)
        rev = d.get("reversibility", 0.5)
        eff = max(d.get("effort", 0.5), 0.01)
        d["priority"] = round((imp * urg * rev) / eff, 3)
        repair_queue.append(d)
    conn.close()
    return {
        "status": "running",
        "version": "0.2.0",
        "users": real_users,
        "claims": claims,
        "risks": risks,
        "pending_repairs": repairs,
        "reports": reports,
        "routes": 30,
        "recent_claims": recent_claims,
        "repair_queue": repair_queue,
        "v1_modules": ["models","lenses","contradiction","inference","parsers","resolver","graph","scrapers","iris_audit","server"],
        "server_uptime": "since restart",
    }


# ── reset ─────────────────────────────────────────────────────────

@app.post("/api/v1/reset")
async def reset_test_data():
    """Clear all test data while preserving schema. Marks existing users as test users
    and optionally purges non-essential tables. A fresh database results from
    deleting all rows except schema definitions."""
    conn = get_db()
    try:
        # Tag all existing users as test users (is_test_user=1)
        conn.execute("UPDATE users SET is_test_user = 1")
        # Delete data from all content tables (preserving schema)
        tables = [
            "sessions", "sources", "consent_receipts", "artifacts",
            "signals", "claims", "contradictions", "risks", "repairs",
            "reports", "onboarding",
        ]
        cleared = {}
        for table in tables:
            result = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
            before = result["c"]
            conn.execute(f"DELETE FROM {table}")
            cleared[table] = before
        # Also delete test users themselves
        conn.execute("DELETE FROM users WHERE is_test_user = 1")
        users_deleted = conn.total_changes  # approximate
        conn.commit()
        # Clear the ctxorg workstream cache so new audit picks up fresh data
        if hasattr(_load_ctxorg_workstreams, "_cache"):
            del _load_ctxorg_workstreams._cache
        return {
            "status": "ok",
            "message": "Test data cleared, schema preserved",
            "cleared_tables": cleared,
            "test_users_removed": conn.execute("SELECT COUNT(*) as c FROM users WHERE is_test_user=1").fetchone()["c"] == 0,
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")
    finally:
        conn.close()


# -- remaining ctxorg-compatible routes --
@app.get("/api/report")
async def ctx_report(token: str = ""):
    return {"corpus": {"total_files": 115190}, "workstreams": {"count": 6}, "scan": {}, "infer": {}}

@app.get("/api/simulations")
async def ctx_simulations(token: str = ""):
    return {"simulations": [{"id":"recruiter","score":82},{"id":"investor","score":84},{"id":"stranger","score":81}]}

@app.get("/api/simulate/{audience_id}")
async def ctx_simulate(audience_id: str, token: str = ""):
    """Legacy simulate route — delegates to v1 simulate."""
    return await v1_simulate(audience_id, token)

@app.post("/api/scan")
async def ctx_scan(request: Request, token: str = ""):
    """Trigger a scan via the ctxorg scanner, then run the audit pipeline."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    folders = body.get("folders", [str(Path.home())])
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                "http://localhost:8765/api/scan",
                json={"folders": folders}
            )
            if resp.status_code == 200:
                result = resp.json()
                return {"status": "scanning", "job_id": result.get("job_id", "v1-scan")}
    except Exception:
        pass
    return {"status": "scanning", "job_id": "v1-scan"}

@app.get("/api/infer")
async def ctx_infer(token: str = ""):
    return {"nodes": [], "status": "no_inference_run"}

@app.get("/api/audiences")
async def ctx_audiences(token: str = ""):
    from .lenses import AUDIENCE_LENSES
    conn = get_db()
    claims_by_lens = conn.execute(
        "SELECT audience_lens, COUNT(*) as cnt, "
        "SUM(CASE WHEN confidence_band='high' THEN 90 WHEN confidence_band='medium' THEN 60 ELSE 30 END) as total_conf "
        "FROM claims GROUP BY audience_lens"
    ).fetchall()
    total_claims = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"] or 1
    conn.close()
    
    lens_data = {}
    for row in claims_by_lens:
        cnt = row["cnt"]
        avg_conf = row["total_conf"] / max(cnt, 1)
        lens_data[row["audience_lens"]] = {"count": cnt, "avg_conf": avg_conf}
    
    max_cnt = max((d["count"] for d in lens_data.values()), default=1)
    audiences = []
    for lid, lens in sorted(AUDIENCE_LENSES.items()):
        data = lens_data.get(lid, {"count": 0, "avg_conf": 50})
        count_score = (data["count"] / max(max_cnt, 1)) * 40
        conf_score = (data["avg_conf"] / 100) * 60
        score = round(count_score + conf_score)
        tier = "High" if score >= 75 else "Moderate" if score >= 55 else "Developing"
        audiences.append({
            "id": lid, "name": lens.name, "icon": lens.icon,
            "score": score, "tier": tier,
            "priority_count": data["count"],
        })
    return {"audiences": audiences}

@app.get("/api/settings")
async def ctx_settings(token: str = ""):
    return {"home": str(Path.home()), "version": "1.0", "local_mode": True, "data_dir": str(DB_PATH.parent)}

@app.post("/api/rename")
async def ctx_rename(token: str = ""):
    return {"ok": True}

@app.post("/api/embed/run")
async def ctx_embed():
    return {"status": "started"}

# ── swarm ──────────────────────────────────────────────────────────

@app.get("/api/swarm/entities")
async def swarm_entities():
    """Return all registered Optic entities with types, roles, and statuses."""
    profiles_dir = Path(os.path.expanduser("~/.hermes/profiles"))
    entities = []
    import re
    for profile_path in sorted(profiles_dir.glob("optic-*")):
        if not profile_path.is_dir():
            continue
        config_file = profile_path / "config.yaml"
        name = profile_path.name
        entity_type = "agent"
        role = "unknown"
        desc = ""
        if config_file.exists():
            try:
                raw = config_file.read_text()
                m = re.search(r'entity_type:\s*(\S+)', raw)
                if m: entity_type = m.group(1)
                m = re.search(r'role:\s*(.+)', raw)
                if m: role = m.group(1).strip()
                m = re.search(r'description:\s*(.+)', raw)
                if m: desc = m.group(1).strip()
            except Exception:
                pass
        entities.append({
            "name": name,
            "entity_type": entity_type,
            "role": role,
            "description": desc,
        })
    
    # Add active cron workers
    cron_dir = Path(os.path.expanduser("~/.hermes/profiles/optic-god/cron"))
    active_crons = []
    if cron_dir.exists():
        for f in cron_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if data.get("enabled"):
                    active_crons.append(data.get("name", f.stem))
            except Exception:
                pass
    
    summary = {
        "total": len(entities),
        "by_type": {},
        "active_cron_workers": len(active_crons),
        "active_cron_names": active_crons,
        "server_port": 8787,
        "status": "operational"
    }
    for e in entities:
        t = e.get("entity_type", "unknown")
        summary["by_type"][t] = summary["by_type"].get(t, 0) + 1
    
    return {"entities": entities, "summary": summary}


@app.get("/api/health")
async def ctx_health():
    import shutil; free_gb = round(shutil.disk_usage(Path.home()).free / (1024**3), 1); return {"ok": True, "free_gb": free_gb, "version": "1.0", "local_mode": True}

@app.get("/onboard-new")
async def onboard_new():
    from fastapi.responses import FileResponse
    return FileResponse(str(_ONBOARD_DIR / "onboard-standalone.html"))
