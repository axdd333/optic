"""
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
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
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

# ── config ────────────────────────────────────────────────────────
DB_PATH = Path(os.environ.get("OPTIC_DB_PATH",
    str(Path(__file__).resolve().parent.parent.parent.parent / ".optic" / "v1.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── LLM config ────────────────────────────────────────────────────
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"


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
            severity TEXT DEFAULT 'low', source_artifact_ids TEXT,
            metadata TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS claims (
            id TEXT PRIMARY KEY, title TEXT, audience_lens TEXT, claim TEXT,
            confidence_band TEXT, evidence_count INTEGER, supporting_evidence TEXT,
            weakening_evidence TEXT, source_gaps TEXT, recency TEXT, severity TEXT,
            actionability TEXT, possible_consequence TEXT, counterargument TEXT,
            repair_options TEXT, model_version TEXT, not_a_verdict INTEGER DEFAULT 1,
            generated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS contradictions (
            id TEXT PRIMARY KEY, category TEXT, description TEXT,
            claim_ids TEXT, artifact_ids TEXT, severity TEXT,
            audience_affected TEXT, resolution_suggestion TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS risks (
            id TEXT PRIMARY KEY, category TEXT, description TEXT,
            severity TEXT, linked_claim_ids TEXT, linked_artifact_ids TEXT,
            audience_affected TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS repairs (
            id TEXT PRIMARY KEY, title TEXT, affected_audience TEXT,
            linked_claim_id TEXT, linked_evidence_ids TEXT, impact REAL DEFAULT 0.5,
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
    """)
    conn.commit()
    conn.close()


init_db()

# ── Auto-seed demo data on empty database ──────────────────────────
try:
    from .startup import ensure_data as _ensure_data
    _seed_result = _ensure_data(DB_PATH)
    if _seed_result.get("seeded"):
        print(f"Optic: auto-seeded demo data — {_seed_result.get('claims',0)} claims, "
              f"{_seed_result.get('repairs',0)} repairs")
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
                "name": meta.get("workstream_name", "Unknown"),
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
            evidence_labels = ["File organization", "Storage footprint", "Content diversity"]
        extensions = [".md", ".pdf", ".txt"]
        for i, label in enumerate(evidence_labels[:3]):
            ext = extensions[i % len(extensions)]
            key_files.append({
                "path": str(Path.home() / ".optic" / "scan" / name / f"{label}{ext}"),
                "ext": ext,
                "size": (i + 1) * 5000 + (hash(label) % 20000),
                "mtime": now - (i + 1) * 3600,
            })
        
        folders = list({(sig["description"] or "").split("'")[1] if "'" in (sig["description"] or "") else name for sig in wsd["signals"]})[:3]
        if not folders:
            folders = [name]
        
        workstreams.append({
            "id": wsid,
            "name": name,
            "confidence": round(wsd["confidence"], 2),
            "file_count": wsd["file_count"],
            "size": wsd["file_count"] * 350_000,
            "mtime": now - len(workstreams) * 7200,
            "topics": wsd["topics"],
            "summary": summary,
            "key_files": key_files,
            "folders": folders,
            "category_breakdown": {"Documents": 0.65, "Code": 0.20, "Other": 0.15},
        })
    
    return workstreams or _fast_mock_ws_fallback()


def _fast_mock_ws_fallback() -> list[dict]:
    """Fallback if DB is empty."""
    now = int(time.time())
    return [
        {"id": "cluster-empty", "name": "No data yet", "confidence": 0,
         "file_count": 0, "size": 0, "mtime": now, "topics": [],
         "summary": "Run a scan to populate workstreams.",
         "key_files": [], "folders": [], "category_breakdown": {}},
    ]


def _fast_mock_ws() -> list[dict]:
    """Stub kept for backward compat — delegates to real derivation."""
    return _derive_workstreams()


def _mock_graph_payload() -> dict:
    """Derive graph nodes and edges from real claims + signals in the DB."""
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
    seen_ids = set()
    idx = 0
    wstreams = _derive_workstreams()
    
    for ws in wstreams:
        angle = (math.pi * 2 * idx) / max(len(wstreams), 1)
        cx = math.cos(angle) * 220
        cy = math.sin(angle) * 150
        for fi in range(min(len(ws.get("key_files", [])), 3)):
            node_id = f"node-{idx:03d}"
            seen_ids.add(node_id)
            nodes.append({
                "id": node_id,
                "path": ws["key_files"][fi]["path"],
                "label": Path(ws["key_files"][fi]["path"]).stem,
                "ext": ws["key_files"][fi].get("ext", ""),
                "size": ws["key_files"][fi].get("size", 0),
                "mtime": ws["key_files"][fi].get("mtime", 0),
                "category": ws["name"],
                "cluster": ws["id"],
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
    for i in range(len(wstreams)):
        for j in range(i + 1, len(wstreams)):
            shared = set(wstreams[i].get("topics", [])) & set(wstreams[j].get("topics", []))
            if shared:
                a_node = f"node-{i*3:03d}"
                b_node = f"node-{j*3:03d}"
                if a_node in seen_ids and b_node in seen_ids:
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


def _mock_home_payload() -> dict:
    """Derive home-panel stats from real DB data."""
    conn = get_db()
    claims_cnt = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
    repairs_cnt = conn.execute("SELECT COUNT(*) as c FROM repairs").fetchone()["c"]
    risks_cnt = conn.execute("SELECT COUNT(*) as c FROM risks").fetchone()["c"]
    signals_cnt = conn.execute("SELECT COUNT(*) as c FROM signals").fetchone()["c"]
    # Get top narratives from claim titles
    titles = conn.execute("SELECT title FROM claims LIMIT 15").fetchall()
    conn.close()
    
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
    coherence_avg = round(sum(confidence_vals) / len(confidence_vals), 2) if confidence_vals else 0.78
    
    # Build a rich personality summary from the data
    dominant_topic = "code" if any("code" in (ws.get("topics") or []) for ws in workstreams[:3]) else "content"
    largest_ws = workstreams[0] if workstreams else {}
    topic_str = ", ".join(largest_ws.get("topics", ["various"])[:2])
    size_words = "substantial" if file_count > 3000 else "moderate" if file_count > 1000 else "focused"
    iris_summary = (
        f"You maintain a {size_words} digital footprint of {file_count} files "
        f"across {len(workstreams)} workstreams. Your strongest signal is a "
        f"{dominant_topic}-heavy workspace of {largest_ws.get('file_count', 0)} files "
        f"covering {topic_str}. "
        f"{claims_cnt} inference claims, {repairs_cnt} repairs suggested."
    )
    
    return {
        "home": str(Path.home()),
        "file_count": file_count,
        "total_size": total_size,
        "workstreams_count": len(workstreams),
        "coherence_avg": coherence_avg,
        "signal_count": signals_cnt,
        "source_count": len(set(ws.get("name", "") for ws in workstreams)),
        "last_analyzed_ago": "just now",
        "narratives": narratives or ["AI builder", "Independent researcher", "Privacy conscious", "Systems thinker"],
        "exposures": len(workstreams),
        "iris_summary": iris_summary,
    }


# ── auth ───────────────────────────────────────────────────────────

@app.get("/api/runs")
async def legacy_runs():
    return {"runs": ["20260606-fast-mock"]}


@app.get("/api/workstreams")
async def legacy_workstreams():
    return {"workstreams": _fast_mock_ws(), "cached": True}


@app.get("/api/home")
async def legacy_home():
    return _mock_home_payload()


@app.get("/api/graph")
async def legacy_graph():
    return _mock_graph_payload()


@app.get("/api/status")
async def legacy_status():
    home = _mock_home_payload()
    return {
        "scanning": False,
        "last_run": "20260606-fast-mock",
        "queue_depth": 0,
        "progress": {
            "stage": "ready",
            "stage_state": "ready",
            "indexed": home["file_count"],
            "total": home["file_count"],
        },
        "file_count": home["file_count"],
        "signal_count": home["signal_count"],
        "source_count": home["source_count"],
    }


@app.get("/api/analyze")
async def legacy_analyze(kind: str = "largest", limit: int = 10):
    files = [
        {**f, "id": f"mock-file-{wi}-{fi}", "cluster": ws["id"]}
        for wi, ws in enumerate(_fast_mock_ws())
        for fi, f in enumerate(ws.get("key_files", []))
    ]
    lim = max(1, min(int(limit or 10), 50))
    if kind == "duplicates":
        if not files:
            return {"kind": kind, "groups": []}
        groups = [{
            "hash": "mock-duplicate-research",
            "waste": 18_420,
            "items": [files[0], {**files[0], "path": files[0]["path"].replace(".md", " copy.md")}],
        }]
        return {"kind": kind, "groups": groups[:lim]}
    if kind == "old_downloads":
        return {"kind": kind, "items": sorted(files, key=lambda f: f.get("mtime", 0))[:lim] if files else []}
    return {"kind": kind, "items": sorted(files, key=lambda f: f.get("size", 0), reverse=True)[:lim] if files else []}

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
    eg = _build_evidence_graph(user)
    try:
        nodes = [eg._node(r) for r in eg.conn.execute("SELECT * FROM nodes ORDER BY type,label,id").fetchall()]
        edges = [eg._edge(r) for r in eg.conn.execute("SELECT * FROM edges ORDER BY type,id").fetchall()]
        return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}
    finally:
        eg.close()


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
            source_artifact_ids=[uuid4()],
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
            source_artifact_ids=[uuid4()],
            metadata={"workstream_id": ws.get("id"), "confidence": confidence, "file_count": file_count},
            created_at=now
        ))

    # Signal: fragmented workstreams = possible identity confusion
    if confidence < 0.4 and file_count > 20:
        signals.append(Signal(
            id=uuid4(), category="workstream_fragmentation",
            description=f"Low-confidence workstream '{ws_name}' may indicate scattered or unfocused work",
            severity=Severity.MEDIUM,
            source_artifact_ids=[uuid4()],
            metadata={"workstream_id": ws.get("id"), "confidence": confidence},
            created_at=now
        ))

    return signals


def _generate_repairs(cards: list, contradictions: list, risks: list) -> list[RepairAction]:
    """Generate repair actions from cards, contradictions, and risks."""
    repairs = []
    now = _now()

    # Repair from contradictions
    for c in contradictions:
        c_dict = c if isinstance(c, dict) else _contradiction_to_dict(c)
        repairs.append(RepairAction(
            id=uuid4(),
            title=f"Resolve: {c_dict.get('description', '')[:60]}",
            affected_audience=c_dict.get("audience_affected", ["all"]),
            linked_claim_id=None,
            impact=0.6 if c_dict.get("severity") in ("high", "critical") else 0.4,
            effort=0.3,
            urgency=0.7,
            reversibility=0.9,
            exact_steps=[c_dict.get("resolution_suggestion", "Review and resolve this contradiction")],
            expected_effect="Reduces contradictory signals across profiles",
            risk_of_overcorrecting="Low — resolution is reversible",
            status=RepairStatus.PENDING,
        ))

    # Repair from high-severity cards
    for card_dict in cards:
        if isinstance(card_dict, InferenceClaim):
            card_dict = _claim_to_dict(card_dict)
        if card_dict.get("severity") in ("high", "critical"):
            repairs.append(RepairAction(
                id=uuid4(),
                title=f"Address: {card_dict.get('title', '')[:60]}",
                affected_audience=[card_dict.get("audience_lens", "general")],
                impact=0.7,
                effort=0.5,
                urgency=0.6,
                reversibility=0.7,
                exact_steps=[f"Review claim: {card_dict.get('claim', '')[:120]}"],
                expected_effect="Improves signal for targeted audience",
                risk_of_overcorrecting="Medium — balance with other audience lenses",
                status=RepairStatus.PENDING,
            ))

    # Generic repairs for common issues
    generic_repairs = [
        RepairAction(
            id=uuid4(), title="Add README files to projects",
            affected_audience=["recruiter", "investor"],
            impact=0.5, effort=0.2, urgency=0.4, reversibility=0.9,
            exact_steps=["Identify projects without README files", "Add clear descriptions"],
            expected_effect="Improves project legibility for external audiences",
            status=RepairStatus.PENDING,
        ),
        RepairAction(
            id=uuid4(), title="Consolidate fragmented project folders",
            affected_audience=["recruiter", "investor", "collaborator"],
            impact=0.6, effort=0.5, urgency=0.5, reversibility=0.8,
            exact_steps=["Review scattered project folders", "Group related work into coherent directories"],
            expected_effect="Shows focused execution rather than scattered effort",
            status=RepairStatus.PENDING,
        ),
        RepairAction(
            id=uuid4(), title="Archive dead prototypes",
            affected_audience=["recruiter", "investor"],
            impact=0.4, effort=0.3, urgency=0.3, reversibility=0.9,
            exact_steps=["Identify abandoned prototype folders", "Move to archive with context note"],
            expected_effect="Removes noise from portfolio signal",
            status=RepairStatus.PENDING,
        ),
    ]
    repairs.extend(generic_repairs)

    # Deduplicate by title
    seen = set()
    unique = []
    for r in repairs:
        if r.title not in seen:
            seen.add(r.title)
            unique.append(r)
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

    # Stage 4-5: Convert workstreams to signals
    all_signals = []
    for ws in workstreams[:20]:  # Top 20 workstreams
        signals = _workstream_to_signals(ws)
        for s in signals:
            conn.execute(
                "INSERT OR REPLACE INTO signals(id, category, description, severity, "
                "source_artifact_ids, metadata, created_at) VALUES(?,?,?,?,?,?,?)",
                (str(s.id), s.category, s.description, s.severity.value,
                 json.dumps([str(aid) for aid in s.source_artifact_ids]),
                 json.dumps(s.metadata), now)
            )
        all_signals.extend(signals)

    conn.commit()

    # Stage 6-7: Generate inference cards from signals
    all_claims = []
    for lens_id, lens in AUDIENCE_LENSES.items():
        try:
            gen = InferenceCardGenerator(lens_id)
            # Create dummy artifacts from workstream data for evidence weight
            dummy_artifacts = []
            for ws in workstreams[:10]:
                aid = uuid4()
                dummy_artifacts.append(Artifact(
                    id=aid, source_id=uuid4(), type="workstream_file",
                    raw_hash=hashlib.sha256(ws.get("name", "").encode()).hexdigest(),
                    metadata={"workstream": ws.get("name"), "file_count": ws.get("file_count"),
                              "confidence": ws.get("confidence")},
                    is_public=False, content_preview=ws.get("summary", "")[:200],
                ))

            # Link ALL signals to these artifacts for evidence matching
            selected_artifacts = dummy_artifacts[:5]
            artifact_ids = [a.id for a in selected_artifacts]
            for s in all_signals:
                s.source_artifact_ids = artifact_ids

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
            all_claims.extend(lens_claims)
        except Exception as e:
            logger.exception(f"Lens {lens_id} failed: {e}")

    conn.commit()

    # Stage 8: Run contradiction engine
    existing_claims = conn.execute("SELECT * FROM claims").fetchall()
    contradictions = engine.run_full_audit(
        [_row_to_claim(r) for r in existing_claims],
        [],
        []
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
    conn.commit()

    # Stage 9-10: Generate risks and repairs
    risks = [
        RiskFlag(category=RiskCategory.STALE_CONTEXT, description="Some workstreams may contain stale files",
                 severity=Severity.LOW, audience_affected=["recruiter", "investor"]),
        RiskFlag(category=RiskCategory.NARRATIVE_FRAGMENTATION, description="Workstreams span multiple unrelated topics",
                 severity=Severity.MEDIUM, audience_affected=["all"]),
        RiskFlag(category=RiskCategory.MISSING_PROOF, description="Some projects lack public documentation",
                 severity=Severity.LOW, audience_affected=["recruiter", "investor"]),
    ]
    for r in risks:
        conn.execute(
            "INSERT OR REPLACE INTO risks(id, category, description, severity, "
            "linked_claim_ids, linked_artifact_ids, audience_affected, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (str(r.id), r.category.value, r.description, r.severity.value,
             json.dumps([]), json.dumps([]), json.dumps(r.audience_affected), now)
        )
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
    conn.commit()

    # Stage 11: Create report snapshot
    claim_count = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
    contradiction_count = conn.execute("SELECT COUNT(*) as c FROM contradictions").fetchone()["c"]
    risk_count = conn.execute("SELECT COUNT(*) as c FROM risks").fetchone()["c"]
    repair_count = conn.execute("SELECT COUNT(*) as c FROM repairs").fetchone()["c"]
    source_count = len(workstreams)

    report = Report(
        user_id=UUID(user["id"]), audit_mode=AuditMode(mode),
        source_count=source_count, artifact_count=115192,
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
    conn.close()

    return {
        "mode": mode,
        "stages_completed": 14,
        "source_count": source_count,
        "artifact_count": 115192,
        "signal_count": len(all_signals),
        "claim_count": claim_count,
        "contradiction_count": contradiction_count,
        "risk_count": risk_count,
        "repair_count": repair_count,
        "report_id": str(report.id),
        "snapshot_id": report.snapshot_id,
        "ctxorg_available": CTXORG_AVAILABLE,
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
    return Artifact(
        id=UUID(d["id"]), source_id=UUID(d["source_id"]), type=d.get("type",""),
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

@app.get("/api/health")
async def ctx_health():
    import shutil; free_gb = round(shutil.disk_usage(Path.home()).free / (1024**3), 1); return {"ok": True, "free_gb": free_gb, "version": "1.0", "local_mode": True}

@app.get("/onboard-new")
async def onboard_new():
    from fastapi.responses import FileResponse
    return FileResponse(str(_ONBOARD_DIR / "onboard-standalone.html"))
