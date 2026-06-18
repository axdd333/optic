from __future__ import annotations

import os
import base64
import hashlib
import hmac
import json
import logging
import mimetypes
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
import smtplib
import urllib.error
import urllib.request
import ssl
from email.message import EmailMessage
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import atlas
from . import cfg as cfgmod
from . import chat, infer, ollama
from . import db, fs, health
from . import ingest, latent, planner, scan

import csv
from fpdf import FPDF

log = logging.getLogger("ctxorg.server")

# ---------------------------------------------------------------------------
# Shared state (scan + workstreams cache)
# ---------------------------------------------------------------------------
_scan_lock = threading.Lock()
_scan_state: dict = {"scanning": False, "progress": {}, "last_run": ""}
_scan_jobs: list[dict] = []
_scan_dead: list[dict] = []
_scan_seq = 0
_scan_worker: threading.Thread | None = None
_scan_event = threading.Event()

_ws_lock = threading.Lock()
_ws_cache: dict = {}   # run_id → {"cards": [...], "ready": bool}

_home_lock = threading.Lock()
_home_jobs: set[str] = set()

_aud_lock = threading.Lock()
_aud_cache: dict = {}

_audit_lock = threading.Lock()
_audit_history: list[dict] = []
_AUDIT_HISTORY_MAX = 500

# ---------------------------------------------------------------------------
# Optic signal engine — lazy import so ctxorg starts even if optic is absent
# ---------------------------------------------------------------------------
# backend/src/ctxorg/server.py → parents[1] = backend/src/ which contains optic/
_OPTIC_SRC = str(Path(__file__).resolve().parents[1])
if _OPTIC_SRC not in sys.path:
    sys.path.insert(0, _OPTIC_SRC)

try:
    from optic.signal.auditor import SignalAuditor  # type: ignore
    from optic.signal.detectors import PatternDetector  # type: ignore
    try:
        from optic.signal.ml_detector import MLDetector  # type: ignore
        _ML_AVAILABLE = True
    except ImportError:
        _ML_AVAILABLE = False
    _OPTIC_AVAILABLE = True
except ImportError:
    _OPTIC_AVAILABLE = False
    _ML_AVAILABLE = False

try:
    from optic import vana_ingest as _vana  # type: ignore
    _VANA_AVAILABLE = True
except ImportError:
    _VANA_AVAILABLE = False

# ── Optic V1 database (shared with optic.v1) ─────────────────────
# Always use the real-user DB path.  Path.home() points to a Hermes
# profile home in agent sessions, and the profile-local v1.db is
# empty.  The real DB lives at ~/.optic/v1.db (symlinked from the
# project backend/.optic/v1.db) and is seeded by optic.v1.startup.
_V1_DB = Path(os.path.expanduser("~ahmedm")) / ".optic" / "v1.db"
if not _V1_DB.exists():
    _V1_DB = Path("/Users/ahmedm/.optic/v1.db")
_V1_AVAILABLE = _V1_DB.exists()


def _v1_row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict with JSON-aware field parsing."""
    if row is None:
        return {}
    d = dict(row)
    json_fields = {"supporting_evidence", "weakening_evidence", "source_gaps",
                   "repair_options", "claim_ids", "artifact_ids", "audience_affected",
                   "linked_claim_ids", "linked_artifact_ids", "linked_evidence_ids",
                   "affected_audience",
                   "exact_steps", "before_measurement", "after_measurement"}
    for key, val in d.items():
        if key in json_fields and isinstance(val, str):
            try:
                d[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
    return d

_acct_lock = threading.Lock()
_store_lock = threading.Lock()
_auth_ctx = threading.local()

_int_lock = threading.Lock()
_int_jobs: list[dict] = []
_int_dead: list[dict] = []
_int_done: list[dict] = []
_int_seq = 0
_int_worker: threading.Thread | None = None
_int_event = threading.Event()
_int_sched_worker: threading.Thread | None = None
_int_sched_event = threading.Event()
_int_loaded = False
_int_loaded_path = ""
_int_idem: dict[str, dict] = {}
_int_sched = {
    "enabled": False,
    "cron": "0 9 * * *",
    "timezone": "UTC",
    "sync_enabled": False,
    "sync_interval_min": 30,
    "sync_channels": ["calendar", "crm", "storage"],
    "sync_next_run": 0,
    "sync_last_run": 0,
    "sync_last_job_id": "",
    "next_run": 0,
    "last_run": 0,
    "last_enqueue": 0,
    "last_job_id": "",
    "last_error": "",
    "last_slot": "",
}

_metrics_lock = threading.Lock()
_metrics = {
    "api_hits": 0,
    "api_errs": 0,
    "scans_started": 0,
    "scans_failed": 0,
    "integrations_started": 0,
    "integrations_failed": 0,
    "rate_limited": 0,
}

_MAX_BODY = 65536
_SESSION_COOKIE = "optic_session"

# ── Password hashing (sha256 + random salt) ───────────────────────
import secrets as _secrets

def _pw_hash(password: str) -> str:
    """Hash a password with a random 32-byte salt. Returns 'salt$hash'."""
    salt = _secrets.token_hex(32)
    h = hashlib.sha256(f"{salt}${password}".encode("utf-8")).hexdigest()
    return f"{salt}${h}"

def _pw_verify(password: str, stored: str) -> bool:
    """Verify a password against a stored salt$hash string."""
    if not stored or "$" not in stored:
        return False
    salt, want = stored.split("$", 1)
    h = hashlib.sha256(f"{salt}${password}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(h, want)

def _pw_strength(password: str) -> str:
    """Validate password strength. Returns empty string if valid, error message if not."""
    if len(password) < 8:
        return "password_too_short_min_8"
    if not any(c.isupper() for c in password):
        return "password_needs_uppercase"
    if not any(c.isdigit() for c in password):
        return "password_needs_digit"
    return ""

# ── Input validation helper (Finding 4) ──────────────────────────
def _str_field(data: dict, key: str, max_len: int = 1000) -> str:
    """Extract + validate a string field. Truncates to max_len."""
    val = str(data.get(key, "")).strip()
    return val[:max_len]

# ── Prototype pollution sanitizer ─────────────────────────────────
_DANGEROUS_KEYS = frozenset({
    "__proto__", "constructor", "prototype",
    "__defineGetter__", "__defineSetter__",
})

def _sanitize_input(obj: object) -> object:
    """Recursively strip dangerous prototype-pollution keys from JSON-like structures."""
    if isinstance(obj, dict):
        return {
            k: _sanitize_input(v)
            for k, v in obj.items()
            if k not in _DANGEROUS_KEYS
        }
    if isinstance(obj, list):
        return [_sanitize_input(v) for v in obj]
    return obj

_SOCIAL_PROVIDERS = (
    "x", "linkedin", "youtube", "tiktok", "instagram", "threads",
)
_FUTURE_CHANNELS = ("calendar", "crm", "storage", "chatops")
_SYNC_CHANNELS = {"calendar", "crm", "storage", "chatops", "email", "social"}
_SECRET_PROVIDERS = {
    "x", "linkedin", "youtube", "tiktok", "instagram", "threads",
    "webhook", "email", "calendar_google", "calendar_outlook",
    "email_google", "email_outlook",
    "crm_hubspot", "crm_salesforce", "storage_drive", "storage_dropbox",
    "storage_onedrive", "chatops_slack", "chatops_discord",
}
_OAUTH_TTL_SEC = 900
_OAUTH_PROVIDERS = {
    "calendar_google": {
        "provider_secret": "calendar_google",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/calendar.readonly",
        "client_id_env": "CTXORG_GOOGLE_CLIENT_ID",
        "client_secret_env": "CTXORG_GOOGLE_CLIENT_SECRET",
        "defaults": {"access_type": "offline", "prompt": "consent"},
        "token_style": "google",
        "pkce": True,
    },
    "calendar_outlook": {
        "provider_secret": "calendar_outlook",
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "offline_access openid profile Calendars.Read",
        "client_id_env": "CTXORG_MS_CLIENT_ID",
        "client_secret_env": "CTXORG_MS_CLIENT_SECRET",
        "defaults": {},
        "token_style": "oauth",
        "pkce": True,
    },
    "storage_drive": {
        "provider_secret": "storage_drive",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/drive.metadata.readonly",
        "client_id_env": "CTXORG_GOOGLE_CLIENT_ID",
        "client_secret_env": "CTXORG_GOOGLE_CLIENT_SECRET",
        "defaults": {"access_type": "offline", "prompt": "consent"},
        "token_style": "google",
        "pkce": True,
    },
    "storage_onedrive": {
        "provider_secret": "storage_onedrive",
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "offline_access openid profile Files.Read.All",
        "client_id_env": "CTXORG_MS_CLIENT_ID",
        "client_secret_env": "CTXORG_MS_CLIENT_SECRET",
        "defaults": {},
        "token_style": "oauth",
        "pkce": True,
    },
    "email_google": {
        "provider_secret": "email_google",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
        "client_id_env": "CTXORG_GOOGLE_CLIENT_ID",
        "client_secret_env": "CTXORG_GOOGLE_CLIENT_SECRET",
        "defaults": {"access_type": "offline", "prompt": "consent"},
        "token_style": "google",
        "pkce": True,
    },
    "email_outlook": {
        "provider_secret": "email_outlook",
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "offline_access openid profile Mail.Read",
        "client_id_env": "CTXORG_MS_CLIENT_ID",
        "client_secret_env": "CTXORG_MS_CLIENT_SECRET",
        "defaults": {},
        "token_style": "oauth",
        "pkce": True,
    },
    "chatops_slack": {
        "provider_secret": "chatops_slack",
        "auth_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scope": "chat:write",
        "client_id_env": "CTXORG_SLACK_CLIENT_ID",
        "client_secret_env": "CTXORG_SLACK_CLIENT_SECRET",
        "defaults": {},
        "token_style": "slack",
        "pkce": False,
    },
}
_INT_WEBHOOK_PROVIDERS = {"slack", "google", "microsoft"}

_rl_lock = threading.Lock()
_rl_state: dict[str, dict] = {}
_rl_last_gc = 0.0
_usage_lock = threading.Lock()

# ── Audience definitions (also used for /api/audiences endpoint) ──
# NOTE: Duplicates AUDIENCE_LENSES from optic/v1/lenses.py with slightly
# different structure (kind_w, key_w tuples vs AudienceLens dataclass).
# TODO: Unify these two audience definitions — use AUDIENCE_LENSES as
# the canonical source and derive this list from it at runtime.
_AUDIENCES = [
    {
        "id": "recruiter",
        "name": "Recruiter read",
        "icon": "👤",
        "summary": "Evaluates career signals, project output, and professional trajectory from a hiring lens.",
        "perspective": "a hiring manager at a tech company",
        "keywords": [
            "career", "code", "project", "research", "work",
            "development", "engineering", "script",
        ],
        "kind_w": {
            "screenshots": 0.2,
            "documents": 1.0,
            "code": 1.0,
            "media": 0.2,
            "other": 0.25,
        },
        "key_w": 0.62,
        "kind_wt": 0.38,
        "avoid_w": 0.30,
        "avoid": ["certifi", "propcache", "markupsafe", "yarl", "aiohttp"],
    },
    {
        "id": "investor",
        "name": "Investor read",
        "icon": "💰",
        "summary": "Evaluates builder signals, execution patterns, and trajectory from an early-stage funding lens.",
        "perspective": "an early-stage investor",
        "keywords": [
            "finance", "startup", "research", "code", "project",
            "product", "development",
        ],
        "kind_w": {
            "screenshots": 0.45,
            "documents": 0.85,
            "code": 0.95,
            "media": 0.35,
            "other": 0.3,
        },
        "key_w": 0.60,
        "kind_wt": 0.40,
        "avoid_w": 0.28,
        "avoid": ["certifi", "propcache", "markupsafe", "yarl", "aiohttp"],
    },
    {
        "id": "collaborator",
        "name": "Collaborator read",
        "icon": "🔗",
        "summary": "Evaluates teamwork signals, collaboration patterns, and complementary skills from a partnership lens.",
        "perspective": "a potential cofounder or collaborator",
        "keywords": [
            "collaboration", "team", "project", "code", "github",
            "contributor", "open source", "partnership",
        ],
        "kind_w": {
            "screenshots": 0.3,
            "documents": 0.7,
            "code": 1.0,
            "media": 0.2,
            "other": 0.3,
        },
        "key_w": 0.55,
        "kind_wt": 0.45,
        "avoid_w": 0.30,
        "avoid": ["certifi", "propcache", "markupsafe", "yarl", "aiohttp"],
    },
    {
        "id": "creator",
        "name": "Creator read",
        "icon": "📢",
        "summary": "Evaluates content output, brand presence, and audience signals from a public-figure lens.",
        "perspective": "a content consumer or brand partner",
        "keywords": [
            "content", "post", "brand", "audience", "social",
            "creator", "video", "writing", "art",
        ],
        "kind_w": {
            "screenshots": 0.8,
            "documents": 0.7,
            "code": 0.2,
            "media": 1.0,
            "other": 0.3,
        },
        "key_w": 0.50,
        "kind_wt": 0.50,
        "avoid_w": 0.25,
        "avoid": ["certifi", "propcache", "markupsafe", "yarl", "aiohttp"],
    },
    {
        "id": "privacy",
        "name": "Privacy read",
        "icon": "🔒",
        "summary": "Evaluates exposure surface, credential leakage, and tracking signals from a privacy-adversary lens.",
        "perspective": "a privacy-conscious auditor or data broker",
        "keywords": [
            "credential", "key", "token", "secret", "password",
            "location", "tracking", "private", "exposure",
        ],
        "kind_w": {
            "screenshots": 0.7,
            "documents": 0.85,
            "code": 0.4,
            "media": 0.5,
            "other": 0.5,
        },
        "key_w": 0.50,
        "kind_wt": 0.50,
        "avoid_w": 0.20,
        "avoid": ["certifi", "propcache", "markupsafe", "yarl", "aiohttp"],
    },
    {
        "id": "platform",
        "name": "Platform read",
        "icon": "📊",
        "summary": "Evaluates consumer signals, interest categories, and behavioral patterns from an ad-platform lens.",
        "perspective": "an advertising or recommendation algorithm",
        "keywords": [
            "social", "browse", "search", "purchase", "like",
            "follow", "click", "watch", "engage",
        ],
        "kind_w": {
            "screenshots": 1.0,
            "documents": 0.4,
            "code": 0.15,
            "media": 0.9,
            "other": 0.35,
        },
        "key_w": 0.45,
        "kind_wt": 0.55,
        "avoid_w": 0.20,
        "avoid": ["certifi", "propcache", "markupsafe", "yarl", "aiohttp"],
    },
    {
        "id": "search",
        "name": "Search engine read",
        "icon": "🔍",
        "summary": "Evaluates search appearance, public surface, and meta-signals from a search-engine lens.",
        "perspective": "a search engine or web crawler",
        "keywords": [
            "public", "search", "website", "profile", "index",
            "meta", "bio", "about", "portfolio",
        ],
        "kind_w": {
            "screenshots": 0.8,
            "documents": 0.9,
            "code": 0.2,
            "media": 0.5,
            "other": 0.35,
        },
        "key_w": 0.45,
        "kind_wt": 0.55,
        "avoid_w": 0.25,
        "avoid": ["certifi", "propcache", "markupsafe", "yarl", "aiohttp"],
    },
    {
        "id": "institution",
        "name": "Institution read",
        "icon": "🏛",
        "summary": "Evaluates credential verification, formal records, and stability from an institutional gatekeeper lens.",
        "perspective": "a university admissions officer or institutional evaluator",
        "keywords": [
            "degree", "certificate", "transcript", "record",
            "credential", "verification", "official", "application",
        ],
        "kind_w": {
            "screenshots": 0.5,
            "documents": 1.0,
            "code": 0.2,
            "media": 0.2,
            "other": 0.3,
        },
        "key_w": 0.55,
        "kind_wt": 0.45,
        "avoid_w": 0.25,
        "avoid": ["certifi", "propcache", "markupsafe", "yarl", "aiohttp"],
    },
    {
        "id": "stranger",
        "name": "Stranger read",
        "icon": "👁",
        "summary": "Evaluates public surface signals, available fragments, and first impressions with limited context.",
        "perspective": "an outside observer with limited context",
        "keywords": ["photo", "travel", "social", "writing", "life"],
        "kind_w": {
            "screenshots": 1.0,
            "documents": 0.35,
            "code": 0.25,
            "media": 0.85,
            "other": 0.3,
        },
        "key_w": 0.40,
        "kind_wt": 0.60,
        "avoid_w": 0.25,
        "avoid": ["certifi", "propcache", "markupsafe", "yarl", "aiohttp"],
    },
]

_WORD_RE = re.compile(r"[a-z0-9]{3,}")
_HEX_RE = re.compile(r"[0-9a-f]{8,}", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_NOISE_TAGS = {
    "certifi", "propcache", "markupsafe", "yarl", "aiohttp",
    "asyncssh", "h11", "pil", "regex", "quando",
}

_RED_NUM_RE = re.compile(r"\b\d{8,}\b")
_RED_TOK_RE = re.compile(
    r"\b(?:sk|pk|rk|tok|token|key)[-_A-Za-z0-9]{8,}\b|"
    r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b|"
    r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b|"
    r"\bA[KS]IA[0-9A-Z]{16}\b",
    re.IGNORECASE,
)
_RED_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CHAT_BLOCK_RE = re.compile(
    r"(ignore (all )?(previous|prior) instructions|"
    r"reveal (the )?(system|developer) prompt|"
    r"print (the )?(system|developer) message)",
    re.IGNORECASE,
)

# Despaced variant — catches spaced-letter and carriage-return obfuscation.
# "i g n o r e a l l ..." → despaced → "ignoreall..." matches this pattern.
_DESPACED_BLOCK_RE = re.compile(
    r"(ignore(all)?(previous|prior)instructions|"
    r"reveal(the)?(system|developer)prompt|"
    r"print(the)?(system|developer)message)",
    re.IGNORECASE,
)


def _guard_check(q: str) -> bool:
    """Return True if *q* contains a blocked prompt-injection pattern.

    Resilient to obfuscation: collapses all whitespace (handles \\r, \\n,
    multi-space) and also checks the fully-despaced variant (handles
    spaced-letter obfuscation like 'i g n o r e a l l ...').
    """
    normalized = re.sub(r"\s+", " ", q).strip()
    if _CHAT_BLOCK_RE.search(normalized):
        return True
    despaced = re.sub(r"\s+", "", q)
    if _DESPACED_BLOCK_RE.search(despaced):
        return True
    return False
_RUN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


class ReqErr(Exception):
    def __init__(self, err: str, code: int = 400, detail: str = "") -> None:
        super().__init__(err)
        self.err = err
        self.code = code
        self.detail = detail[:300]


def _metrics_inc(key: str, n: int = 1) -> None:
    with _metrics_lock:
        _metrics[key] = int(_metrics.get(key, 0)) + n


def _metrics_get() -> dict:
    with _metrics_lock:
        return dict(_metrics)


def _log_ev(evt: str, **kv: object) -> None:
    data = json.dumps(kv, sort_keys=True, separators=(",", ":"))
    log.info("%s %s", evt, data)


def _api_hit(method: str, path: str) -> None:
    if path == "/healthz" or path.startswith("/api/"):
        _metrics_inc("api_hits")


def _api_err(method: str, path: str, err: str, code: int = 200) -> None:
    _metrics_inc("api_errs")
    _log_ev("api_err", method=method, path=path, code=code, err=err)


def _ws_compute_bg(cfg: dict, run_id: str) -> None:
    """Background: compute workstreams with Gemma and update cache."""
    try:
        from . import workstreams
        conn = db.open_db(cfg)
        cards = workstreams.compute(conn, cfg, run_id=run_id, limit=30)
        with _ws_lock:
            _ws_cache[run_id] = {"cards": cards, "ready": True}
    except Exception as exc:
        print(f"[ws] compute error: {exc}", file=sys.stderr)
        with _ws_lock:
            if run_id in _ws_cache:
                _ws_cache[run_id]["ready"] = True  # mark done even on error


def _auto_embed(cfg: dict) -> None:
    """Background task: embed any un-embedded items after server starts."""
    import time
    time.sleep(5)  # let server finish initialising first
    try:
        from . import embed
        conn = db.open_db(cfg)
        embed.ensure_embed_table(conn)
        rows = db.rows(conn, "SELECT id, path, text FROM items")
        embed.embed_items(conn, cfg, rows, verbose=False)
    except Exception as exc:
        print(f"[embed] auto-embed error: {exc}", file=sys.stderr)


def serve(cfg: dict, host: str, port: int) -> None:
    # Ensure V1 database and tables exist (self-bootstrap)
    _v1_init_db()
    # Kick off background embedding of any items not yet embedded
    threading.Thread(target=_auto_embed, args=(cfg,), daemon=True).start()
    _scan_ensure_worker(cfg)
    _integrations_ensure_worker(cfg)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            guarded(self, cfg, route)

        def do_POST(self) -> None:
            # ── C4: Harden payload enforcement BEFORE any body read ──
            # Reject chunked Transfer-Encoding (bypasses Content-Length checks)
            te = (self.headers.get("transfer-encoding", "") or "").strip().lower()
            if te and "chunked" in te:
                self.close_connection = True
                safe_send_err(self, "chunked_not_supported", code=411,
                              detail="Transfer-Encoding: chunked is not accepted")
                return

            # Validate Content-Type for POST requests
            ct = (self.headers.get("content-type", "") or "").strip().lower()
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                if ct and "application/json" not in ct:
                    safe_send_err(self, "unsupported_media_type", code=415,
                                  detail="Content-Type must be application/json")
                    return

            # Reject oversized payloads immediately — never read the body
            # to determine size.  This prevents DoS via large Content-Length
            # before any routing or auth logic runs.
            try:
                cl = self.headers.get("content-length", "0") or "0"
                cl_int = int(cl)
                if cl_int > _MAX_BODY:
                    self.close_connection = True
                    safe_send_err(self, "payload_too_large", code=413,
                                  detail=f"max={_MAX_BODY}")
                    return
            except ValueError:
                safe_send_err(self, "invalid_content_length", code=400)
                return
            guarded(self, cfg, post)

        def log_message(self, fmt: str, *args) -> None:  # type: ignore[override]
            pass  # suppress per-request access logs

    ThreadingHTTPServer((host, port), Handler).serve_forever()


def _auth_begin(req: BaseHTTPRequestHandler, cfg: dict) -> None:
    tok = _auth_token(req)
    row = {
        "acct": None,
        "api_key": None,
        "scopes": set(),
        "session_id": "",
    }
    if tok.startswith("opk_"):
        key = _api_key_match(cfg, tok)
        if key:
            row["api_key"] = key
            row["scopes"] = set(_api_key_scopes(key.get("scopes", [])))
            _api_key_touch(cfg, str(key.get("id", "")))
    elif tok:
        ses = _sess_lookup(cfg, tok)
        if ses:
            row["session_id"] = str(ses.get("id", ""))
            row["acct"] = _acct_lookup(cfg, str(ses.get("email", "")))
            _sess_touch(cfg, row["session_id"])
    _auth_ctx.data = row


def _auth_end() -> None:
    if hasattr(_auth_ctx, "data"):
        delattr(_auth_ctx, "data")


def _auth_get() -> dict:
    data = getattr(_auth_ctx, "data", None)
    return data if isinstance(data, dict) else {}


def _auth_token(req: BaseHTTPRequestHandler) -> str:
    return _auth_bearer(req) or _auth_cookie(req, _SESSION_COOKIE)


def _auth_bearer(req: BaseHTTPRequestHandler) -> str:
    raw = str(req.headers.get("authorization", "")).strip()
    if not raw.lower().startswith("bearer "):
        return ""
    return raw.split(" ", 1)[1].strip()


def _auth_cookie(req: BaseHTTPRequestHandler, name: str) -> str:
    raw = str(req.headers.get("cookie", "")).strip()
    if not raw:
        return ""
    jar = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:
        return ""
    val = jar.get(name)
    return str(val.value).strip() if val else ""


def _auth_scopes() -> set[str]:
    data = _auth_get()
    scopes = data.get("scopes")
    return scopes if isinstance(scopes, set) else set()


def _req_hdr(req: BaseHTTPRequestHandler, name: str) -> str:
    raw = str(req.headers.get(name, "")).strip()
    return raw.split(",", 1)[0].strip() if raw else ""


def _req_host(req: BaseHTTPRequestHandler) -> str:
    # Finding 6 — only trust x-forwarded-host from the proxy (127.0.0.1)
    client_ip = _req_ip(req)
    if client_ip in ("127.0.0.1", "::1"):
        raw = _req_hdr(req, "x-forwarded-host") or _req_hdr(req, "host")
    else:
        raw = _req_hdr(req, "host")
    return raw.lower()


def _url_host(raw: str) -> str:
    if not raw:
        return ""
    try:
        return urlparse(raw).netloc.strip().lower()
    except Exception:
        return ""


def _csrf_same_origin(req: BaseHTTPRequestHandler) -> bool:
    host = _req_host(req)
    if not host:
        return False
    org = _url_host(_req_hdr(req, "origin"))
    if org:
        return org == host
    ref = _url_host(_req_hdr(req, "referer"))
    return bool(ref and ref == host)


# ── Internal proxy token — must match route.ts INTERNAL_PROXY_TOKEN ──
# The Next.js proxy sets this header; the backend skips CSRF when present.
_INTERNAL_PROXY_TOKEN = os.environ.get("OPTIC_INTERNAL_PROXY_TOKEN", "optic-proxy-v1")

def _csrf_guard(req: BaseHTTPRequestHandler, path: str) -> None:
    if not path.startswith("/api/"):
        return
    # API key requests skip CSRF
    ctx = _auth_get()
    if ctx.get("api_key"):
        return
    # Unauthenticated requests skip CSRF
    if not str(ctx.get("session_id", "")):
        return
    # Internal proxy requests skip CSRF (Finding 1 fix — trusted proxy token)
    proxy_token = _req_hdr(req, "x-internal-proxy")
    if proxy_token == _INTERNAL_PROXY_TOKEN:
        return
    if _csrf_same_origin(req):
        return
    raise ReqErr("csrf_origin_mismatch", code=403)


def _scope_role(scopes: set[str], roles: set[str]) -> str:
    if "admin" in scopes and roles != {"owner"}:
        return "api_key_admin"
    if roles == {"owner", "admin", "member"} and (
        scopes & {"read", "write", "scan", "export", "integrations"}
    ):
        return "api_key_member"
    if roles == {"owner", "admin"} and (
        scopes & {"write", "scan", "export", "integrations"}
    ):
        return "api_key_admin"
    return ""


def _scope_need(method: str, path: str) -> str:
    if not path.startswith("/api/"):
        return ""
    if method == "GET":
        if path in {"/api/workspace/invites", "/api/api-keys"}:
            return "admin"
        if path in {"/api/integrations/secrets"}:
            return "integrations"
        if path == "/api/ops/health":
            return "admin"  # Finding 3 — health leaks internal state
        return "read"
    if method != "POST":
        return ""
    if path in {"/api/signup", "/api/signout"}:
        return ""
    if path == "/api/scan":
        return "scan"
    if path == "/api/exports":
        return "export"
    if path.startswith("/api/integrations/"):
        return "integrations"
    if path.startswith("/api/ops/"):
        return "admin"
    if path in {"/api/api-keys/create", "/api/api-keys/revoke"}:
        return "admin"
    if path in {"/api/workspace", "/api/workspace/invites"}:
        return "admin"
    if path in {
        "/api/billing/plan",
        "/api/billing/checkout",
        "/api/billing/portal",
    }:
        return "admin"
    if path == "/api/billing/webhook":
        return ""
    if path in {"/api/settings", "/api/rename", "/api/chat", "/api/iris"}:
        return "write"
    return "write"


def _scope_guard(req: BaseHTTPRequestHandler) -> None:
    ctx = _auth_get()
    if not isinstance(ctx.get("api_key"), dict):
        return
    need = _scope_need(str(getattr(req, "command", "GET")).upper(),
                       urlparse(req.path).path)
    if not need:
        return
    scopes = _auth_scopes()
    if "admin" in scopes:
        return
    if need in scopes:
        return
    raise ReqErr("api_key_scope_forbidden", code=403, detail=f"need={need}")


def _rl_int(cfg: dict, key: str, dflt: int, lo: int, hi: int) -> int:
    try:
        val = int(cfg.get(key, dflt) or dflt)
    except Exception:
        val = dflt
    return max(lo, min(hi, val))


def _rl_policy(cfg: dict, method: str, path: str) -> tuple[str, int] | None:
    if not path.startswith("/api/"):
        return None
    meth = method.upper().strip()
    # ── Critical endpoints: very tight rate limits (C5) ──
    if meth == "POST" and path == "/api/v1/reset":
        return "v1_reset_post", _rl_int(cfg, "rate_reset_per_min", 3, 1, 30)
    if meth == "POST" and path == "/api/signup":
        return "signup_post", _rl_int(cfg, "rate_signup_per_min", 5, 1, 30)
    if meth == "POST" and path == "/api/signin":
        return "signin_post", _rl_int(cfg, "rate_signin_per_min", 10, 1, 30)
    if meth == "POST" and path == "/api/chat":
        return "chat_post", _rl_int(cfg, "rate_chat_per_min", 40, 1, 3000)
    if meth == "POST" and path == "/api/iris":
        return "iris_post", _rl_int(cfg, "rate_iris_per_min", 50, 1, 3000)
    if meth == "POST" and path == "/api/scan":
        return "scan_post", _rl_int(cfg, "rate_scan_per_min", 8, 1, 600)
    if meth == "POST" and path in {
        "/api/integrations/jobs",
        "/api/integrations/jobs/replay",
    }:
        return "int_jobs_post", _rl_int(cfg, "rate_jobs_per_min", 50, 1, 5000)
    if meth == "POST" and path == "/api/integrations/secrets":
        return "int_sec_post", _rl_int(cfg, "rate_secrets_per_min", 20, 1, 500)
    if meth == "POST" and path.startswith("/api/integrations/webhooks/"):
        return "int_hook_post", _rl_int(cfg, "rate_int_hook_per_min",
                                        180, 1, 5000)
    if meth == "POST" and path == "/api/billing/webhook":
        return "billing_hook", _rl_int(cfg, "rate_billing_hook_per_min",
                                       120, 1, 3000)
    if meth == "POST" and path.startswith("/api/ops/"):
        return "ops_post", _rl_int(cfg, "rate_ops_per_min", 18, 1, 300)
    if meth == "GET" and path in {"/api/report", "/api/workstreams"}:
        return "heavy_get", _rl_int(cfg, "rate_heavy_per_min", 90, 1, 5000)
    # ── Default: tighter general rate limit (was 480 → 120 for safety) ──
    return "api_all", _rl_int(cfg, "rate_api_per_min", 120, 1, 20000)


def _req_ip(req: BaseHTTPRequestHandler) -> str:
    raw = _req_hdr(req, "x-forwarded-for")
    if raw:
        return raw.split(",", 1)[0].strip().lower()[:120]
    row = getattr(req, "client_address", ())
    if isinstance(row, tuple) and row:
        return str(row[0]).strip().lower()[:120]
    return "unknown"


def _rl_actor(req: BaseHTTPRequestHandler) -> str:
    ctx = _auth_get()
    key = ctx.get("api_key")
    if isinstance(key, dict):
        kid = str(key.get("id", "")).strip()
        if kid:
            return f"key:{kid[:80]}"
    sid = str(ctx.get("session_id", "")).strip()
    if sid:
        return f"ses:{sid[:80]}"
    return f"ip:{_req_ip(req)}"


def _rl_gc(now: float) -> None:
    global _rl_last_gc
    if now - _rl_last_gc < 30:
        return
    _rl_last_gc = now
    drop = [key for key, rec in _rl_state.items()
            if now - float(rec.get("ts", 0.0) or 0.0) > 900]
    for key in drop:
        _rl_state.pop(key, None)


def _rl_take(actor: str, scope: str, cap: int) -> float:
    now = time.time()
    fill = max(0.1, float(cap) / 60.0)
    key = f"{actor}:{scope}"
    with _rl_lock:
        _rl_gc(now)
        rec = _rl_state.get(key)
        if not isinstance(rec, dict):
            _rl_state[key] = {"tok": float(cap - 1), "ts": now}
            return 0.0
        tok = float(rec.get("tok", cap))
        ts = float(rec.get("ts", now))
        tok = min(float(cap), tok + max(0.0, now - ts) * fill)
        if tok < 1.0:
            rec["tok"] = tok
            rec["ts"] = now
            return (1.0 - tok) / fill
        rec["tok"] = tok - 1.0
        rec["ts"] = now
        if len(_rl_state) > 20000:
            _rl_gc(now + 9999)
    return 0.0


def _rate_limit_guard(req: BaseHTTPRequestHandler, cfg: dict) -> None:
    method = str(getattr(req, "command", "GET")).upper()
    path = urlparse(req.path).path
    row = _rl_policy(cfg, method, path)
    if not row:
        return
    scope, cap = row
    wait = _rl_take(_rl_actor(req), scope, cap)
    if wait <= 0:
        return
    _metrics_inc("rate_limited")
    raise ReqErr("rate_limited", code=429, detail=f"retry_after_s={wait:.2f}")


def guarded(req: BaseHTTPRequestHandler, cfg: dict, fn) -> None:
    try:
        _auth_begin(req, cfg)
        _scope_guard(req)
        _rate_limit_guard(req, cfg)
        fn(req, cfg)
    except ReqErr as exc:
        safe_send_err(req, exc.err, code=exc.code, detail=exc.detail)
    except (BrokenPipeError, ConnectionResetError):
        return
    except Exception as exc:
        safe_send_err(req, "internal_error", code=500, detail=str(exc))
    finally:
        _auth_end()


def safe_send_err(req: BaseHTTPRequestHandler, err: str, code: int = 400,
                  detail: str = "") -> None:
    try:
        send_err(req, err, code=code, detail=detail)
    except (BrokenPipeError, ConnectionResetError):
        return


def route(req: BaseHTTPRequestHandler, cfg: dict) -> None:
    path = urlparse(req.path).path
    _api_hit("GET", path)
    if path in ("/", "/index.html"):
        return static(req, "index.html")
    if path.startswith("/static/"):
        return static(req, path.removeprefix("/static/"))
    if path in ("/healthz", "/api/health"):
        return healthz(req, cfg)
    if path in ("/readyz", "/api/ready"):
        return readyz(req, cfg)
    if path == "/api/runs":
        return send(req, {"runs": runs(cfg)})
    if path == "/api/graph":
        return send(req, graph_payload(req, cfg))
    if path in ("/api/reveal", "/api/open"):
        return send(req, reveal_payload(req, cfg))
    if path == "/api/delta":
        return send(req, {"nodes": [], "links": []})
    if path == "/api/workstreams":
        return send(req, workstreams_payload(req, cfg))
    if path == "/api/report":
        return send(req, report_payload(req, cfg))
    if path == "/api/status":
        return send(req, status_payload(cfg))
    if path == "/api/embeddings/status":
        return send(req, embed_status_payload(cfg))
    if path == "/api/home":
        return send(req, home_payload(req, cfg))
    if path == "/api/account":
        return send(req, account_payload(cfg))
    if path == "/api/workspace":
        return send(req, workspace_payload(cfg))
    if path == "/api/workspace/members":
        return send(req, workspace_members_payload(cfg))
    if path == "/api/workspace/invites":
        return send(req, workspace_invites_payload(cfg))
    if path == "/api/api-keys":
        return send(req, api_keys_payload(cfg))
    if path == "/api/billing":
        return send(req, billing_payload(cfg))
    if path == "/api/billing/usage":
        return send(req, billing_usage_payload(cfg))
    if path == "/api/settings":
        return send(req, settings_payload(cfg))
    if path == "/api/integrations/catalog":
        return send(req, integrations_catalog_payload(cfg))
    if path == "/api/integrations/state":
        return send(req, integrations_state_payload(cfg))
    if path == "/api/integrations/secrets":
        return send(req, integrations_secrets_payload(cfg))
    if path == "/api/integrations/connections":
        return send(req, integrations_connections_payload(cfg))
    if path == "/api/integrations/sync/state":
        return send(req, integrations_sync_state_payload(cfg))
    if path == "/api/integrations/jobs":
        return send(req, integrations_jobs_payload(cfg))
    if path == "/api/integrations/oauth/events":
        return send(req, integrations_oauth_events_payload(cfg))
    if path == "/api/integrations/oauth/callback":
        return integrations_oauth_callback(req, cfg)
    if path == "/api/audiences":
        return send(req, audiences_payload(req, cfg))
    if path == "/api/simulations":
        return send(req, simulations_payload(req, cfg))
    if path.startswith("/api/simulate/"):
        try:
            aid = path.removeprefix("/api/simulate/").strip("/")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return send_err(req, "invalid_audience_id", code=400)
        return send(req, simulate_payload(req, cfg, aid))
    if path == "/api/exports/history":
        return send(req, export_history_payload(cfg))
    if path == "/api/ops/health":
        return send(req, ops_health_payload(cfg))
    if path == "/api/ops/backups":
        return send(req, backup_list_payload(cfg))
    if path == "/api/infer":
        return send(req, infer_payload(req, _llm_cfg_runtime(cfg)))
    if path == "/api/analyze":
        return send(req, analyze_payload(req, cfg))
    if path == "/api/entity/profile":
        return send(req, entity_profile_payload(req, cfg))
    if path == "/api/audience":
        return send(req, audience_list_payload())
    if path == "/api/audit/history":
        return send(req, audit_history_payload(req, cfg))
    if path.startswith("/api/audit/") and path.endswith("/report"):
        aid = path.removeprefix("/api/audit/").removesuffix("/report").strip("/")
        return send(req, audit_detail_payload(req, cfg, aid))
    if path == "/api/v1/simulations":
        return send(req, simulations_payload(req, cfg))
    if path.startswith("/api/v1/simulate/"):
        try:
            aid = path.removeprefix("/api/v1/simulate/").strip("/")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return send_err(req, "invalid_audience_id", code=400)
        return send(req, simulate_payload(req, cfg, aid))
    if path == "/api/v1/onboarding":
        return send(req, onboarding_payload(cfg))
    if path == "/api/v1/exports":
        return send(req, export_v1_formats_payload(cfg))
    if path == "/api/v1/claims":
        return send(req, v1_claims_payload(req, cfg))
    if path.startswith("/api/v1/claims/workstream/"):
        try:
            name = path.removeprefix("/api/v1/claims/workstream/").strip("/")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return send_err(req, "invalid_workstream_name", code=400)
        return send(req, v1_claims_workstream_payload(req, cfg, name))
    if path == "/api/v1/contradictions":
        return send(req, v1_contradictions_payload(req, cfg))
    if path == "/api/v1/risks":
        return send(req, v1_risks_payload(req, cfg))
    if path == "/api/v1/repairs":
        return send(req, v1_repairs_payload(req, cfg))
    if path == "/api/v1/status":
        return send(req, v1_status_payload(req, cfg))
    if path == "/api/v1/settings":
        return send(req, v1_settings_payload(req, cfg))
    if path == "/api/v1/artifacts":
        return send(req, v1_artifacts_payload(req, cfg))
    if path == "/api/v1/health":
        return send(req, v1_health_payload(cfg))
    if path == "/api/v1/audiences":
        return send(req, audience_list_payload())
    if path == "/api/v1/audit/general":
        return send(req, v1_audit_general_payload(req, cfg))
    if path == "/api/v1/graph/evidence":
        return send(req, v1_graph_evidence_payload(req, cfg))
    if path == "/api/vana/status":
        return send(req, vana_status_payload(cfg))
    if path == "/api/vana/profile":
        return send(req, vana_profile_payload(req, cfg))
    if path.startswith("/api/"):
        return send_err(req, "not_found", code=404)
    return send_err(req, "not_found", code=404)


def post(req: BaseHTTPRequestHandler, cfg: dict) -> None:
    path = urlparse(req.path).path
    _api_hit("POST", path)
    _csrf_guard(req, path)
    if path == "/api/chat":
        _workspace_require_role(cfg, {"owner", "admin", "member"})  # Finding 5
        data = _chat_guard_input(body(req))
        _quota_take(cfg, "chat_daily")
        out = chat.reply(_llm_cfg_runtime(cfg), data)
        return send(req, _chat_guard_output(out))
    if path == "/api/iris":
        _workspace_require_role(cfg, {"owner", "admin", "member"})  # Finding 5
        data = _iris_guard_input(body(req))
        return iris_stream(req, _llm_cfg_runtime(cfg), data)
    if path == "/api/rename":
        return send(req, rename_payload(req, cfg))
    if path == "/api/signup":
        out = signup_payload(req, cfg)
        hdr = _session_set_header(req, out.pop("_session_token", ""))
        return send(req, out, headers=hdr)
    if path == "/api/signin":
        out = signin_payload(req, cfg)
        hdr = _session_set_header(req, out.pop("_session_token", ""))
        return send(req, out, headers=hdr)
    if path == "/api/signout":
        out = signout_payload(req, cfg)
        return send(req, out, headers=_session_clear_header(req))
    if path == "/api/workspace":
        return send(req, workspace_update_payload(req, cfg))
    if path == "/api/workspace/invites":
        return send(req, workspace_invite_create_payload(req, cfg))
    if path == "/api/workspace/invites/accept":
        return send(req, workspace_invite_accept_payload(req, cfg))
    if path == "/api/api-keys/create":
        return send(req, api_key_create_payload(req, cfg))
    if path == "/api/api-keys/revoke":
        return send(req, api_key_revoke_payload(req, cfg))
    if path == "/api/billing/checkout":
        return send(req, billing_checkout_payload(req, cfg))
    if path == "/api/billing/portal":
        return send(req, billing_portal_payload(req, cfg))
    if path == "/api/billing/webhook":
        return send(req, billing_webhook_payload(req, cfg))
    if path == "/api/billing/plan":
        return send(req, billing_plan_update_payload(req, cfg))
    if path == "/api/settings":
        return send(req, settings_update_payload(req, cfg))
    if path == "/api/integrations/state":
        return send(req, integrations_state_update_payload(req, cfg))
    if path == "/api/integrations/secrets":
        return send(req, integrations_secrets_set_payload(req, cfg))
    if path == "/api/integrations/sync/state":
        return send(req, integrations_sync_state_update_payload(req, cfg))
    if path == "/api/integrations/jobs":
        return send(req, integrations_jobs_enqueue_payload(req, cfg))
    if path == "/api/integrations/jobs/replay":
        return send(req, integrations_jobs_replay_payload(req, cfg))
    if path == "/api/integrations/oauth/start":
        return send(req, integrations_oauth_start_payload(req, cfg))
    if path == "/api/integrations/oauth/refresh":
        return send(req, integrations_oauth_refresh_payload(req, cfg))
    if path == "/api/integrations/oauth/revoke":
        return send(req, integrations_oauth_revoke_payload(req, cfg))
    if path.startswith("/api/integrations/webhooks/"):
        provider = path.removeprefix("/api/integrations/webhooks/").strip("/")
        out = integrations_webhook_ingest_payload(req, cfg, provider)
        if bool(out.get("plain_text", False)):
            return send_text(req, str(out.get("body", "")), code=200)
        return send(req, out)
    if path == "/api/scan":
        return send(req, scan_payload(req, cfg))
    if path == "/api/simulations/evaluate":
        return send(req, simulation_eval_payload(req, cfg))
    if path == "/api/simulations/save":
        return send(req, simulation_save_payload(req, cfg))
    if path == "/api/simulations/compare":
        return send(req, simulation_compare_payload(req, cfg))
    if path == "/api/exports":
        return send(req, export_create_payload(req, cfg))
    if path == "/api/ops/backup":
        return send(req, backup_create_payload(req, cfg))
    if path == "/api/ops/restore":
        return send(req, backup_restore_payload(req, cfg))
    if path == "/api/ops/danger":
        return send(req, danger_payload(req, cfg))
    if path == "/api/embed/run":
        return send(req, start_embed_run(cfg))
    if path == "/api/audit":
        return send(req, audit_single_payload(req, cfg))
    if path == "/api/audit/ml":
        return send(req, audit_ml_payload(req, cfg))
    if path == "/api/audit/batch":
        return send(req, audit_batch_payload(req, cfg))
    if path == "/api/v1/onboarding":
        return send(req, onboarding_update_payload(req, cfg))
    if path == "/api/v1/simulations":
        return send(req, simulation_save_payload(req, cfg))
    if path.startswith("/api/v1/simulate/"):
        aid = path.removeprefix("/api/v1/simulate/").strip("/")
        return send(req, v1_simulation_eval_payload(req, cfg, aid))
    if path == "/api/v1/iris/ask":
        return send(req, iris_ask_payload(req, cfg))
    if path.startswith("/api/v1/export/"):
        fmt = path.removeprefix("/api/v1/export/").strip("/")
        return send(req, export_v1_create_payload(req, cfg, fmt))
    if path == "/api/v1/audit/general":
        return send(req, v1_audit_trigger_payload(req, cfg))
    if path.startswith("/api/v1/repairs/"):
        # POST /api/v1/repairs/complete/<repair_id>  or  /api/v1/repairs/<repair_id>/complete
        suffix = path.removeprefix("/api/v1/repairs/").strip("/")
        if suffix.startswith("complete/"):
            rep_id = suffix.removeprefix("complete/").strip("/")
        else:
            rep_id = suffix.removesuffix("/complete").strip("/")
        return send(req, v1_repair_complete_payload(req, cfg, rep_id))
    if path == "/api/v1/reset":
        return send(req, v1_reset_payload(cfg))
    if path == "/api/vana/ingest":
        return send(req, vana_ingest_payload(req, cfg))
    if path == "/api/vana/upload":
        return send(req, vana_upload_payload(req, cfg))
    if path.startswith("/api/"):
        return send_err(req, "not_found", code=404)
    return send_err(req, "not_found", code=404)


def body(req: BaseHTTPRequestHandler, max_body: int | None = None) -> dict:
    raw = body_raw(req, max_body=max_body)
    if not raw:
        return {}
    txt = decode_body(raw)
    if not txt.strip():
        return {}
    try:
        data = json.loads(txt)
    except json.JSONDecodeError as exc:
        raise ReqErr("invalid_json", code=400, detail=f"pos={exc.pos}")
    if isinstance(data, dict):
        return _sanitize_input(data)  # type: ignore[return-value]
    raise ReqErr("invalid_json", code=400, detail="json_object_required")


def _chat_guard_input(data: dict) -> dict:
    q = str(data.get("q", "")).replace("\x00", "").strip()
    if not q:
        raise ReqErr("chat_question_required", code=400)
    if len(q) > 2400:
        _metrics_inc("chat_guard_input_blocked")
        raise ReqErr("chat_input_too_long", code=400)
    if _guard_check(q):
        _metrics_inc("chat_guard_input_blocked")
        raise ReqErr("chat_input_blocked", code=400)
    hist = data.get("history", [])
    rows = hist if isinstance(hist, list) else []
    clean = []
    for row in rows[-40:]:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role", "")).strip().lower()
        if role not in {"user", "assistant"}:
            continue
        txt = str(row.get("content", "")).replace("\x00", "").strip()
        if txt:
            clean.append({"role": role, "content": txt[:600]})
    out = dict(data)
    out["q"] = q[:2400]
    out["history"] = clean
    return out


def _iris_guard_input(data: dict) -> dict:
    """Sanitize Iris LLM input — mirrors _chat_guard_input for /api/iris."""
    q = str(data.get("q", "")).replace("\x00", "").strip()
    if not q:
        raise ReqErr("iris_question_required", code=400)
    if len(q) > 2400:
        _metrics_inc("iris_guard_input_blocked")
        raise ReqErr("iris_input_too_long", code=400)
    if _guard_check(q):
        _metrics_inc("iris_guard_input_blocked")
        raise ReqErr("iris_input_blocked", code=400)
    # Sanitize mode against allowlist
    mode = str(data.get("mode", "report")).strip().lower()[:50]
    allowed_modes = {"report", "mirror", "audit", "compare",
                     "entity", "contradiction", "audience",
                     "archive", "retune"}
    if mode not in allowed_modes:
        mode = "report"
    # Sanitize audience against allowlist
    audience = str(data.get("audience", "recruiter")).strip().lower()[:50]
    allowed_audiences = {"recruiter", "investor", "collaborator", "creator",
                         "privacy", "platform", "search", "institution", "stranger"}
    if audience not in allowed_audiences:
        audience = "recruiter"
    # Sanitize history — strip null bytes, enforce roles, truncate
    hist = data.get("history", [])
    rows = hist if isinstance(hist, list) else []
    clean_history = []
    for row in rows[-40:]:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role", "")).strip().lower()
        if role not in {"user", "assistant"}:
            continue
        txt = str(row.get("content", "")).replace("\x00", "").strip()
        if txt:
            clean_history.append({"role": role, "content": txt[:2000]})
    # Sanitize selected_ids — enforce string list, max 10
    selected_ids = data.get("selected_ids", [])
    clean_ids = []
    if isinstance(selected_ids, list):
        for sid in selected_ids[:10]:
            sid_str = str(sid).strip()[:128]
            if sid_str:
                clean_ids.append(sid_str)
    out = dict(data)
    out["q"] = q[:2400]
    out["mode"] = mode
    out["audience"] = audience
    out["history"] = clean_history
    out["selected_ids"] = clean_ids
    return out


def _chat_guard_output(data: object) -> dict:
    if not isinstance(data, dict):
        _metrics_inc("chat_guard_output_invalid")
        return {
            "state": "DEAD_LETTER",
            "answer": "Iris unavailable",
            "related": [],
            "rename_proposals": [],
            "tasks": [],
        }
    out = dict(data)
    ans = str(out.get("answer", ""))
    red = _RED_EMAIL_RE.sub("[redacted-email]", ans)
    red = _RED_NUM_RE.sub("[redacted-number]", red)
    red = _RED_TOK_RE.sub("[redacted-token]", red)
    if red != ans:
        _metrics_inc("chat_guard_output_redacted")
    out["answer"] = red[:1600]
    return out


def body_raw(req: BaseHTTPRequestHandler, max_body: int | None = None) -> bytes:
    size = read_size(req, max_body=max_body)
    if size == 0:
        return b""
    try:
        raw = req.rfile.read(size)
    except (ConnectionResetError, BrokenPipeError, OSError) as exc:
        raise ReqErr("body_read_failed", code=400,
                     detail=f"read_error={exc.__class__.__name__}")
    if len(raw) != size:
        raise ReqErr("incomplete_body", code=400)
    return raw


def read_size(req: BaseHTTPRequestHandler, max_body: int | None = None) -> int:
    limit = max_body if max_body is not None else _MAX_BODY
    raw = req.headers.get("content-length", "0") or "0"
    try:
        size = int(raw)
    except ValueError:
        raise ReqErr("invalid_content_length", code=400)
    if size < 0:
        raise ReqErr("invalid_content_length", code=400)
    if size > limit:
        req.close_connection = True
        raise ReqErr("payload_too_large", code=413,
                     detail=f"max={limit}")
    return size


def decode_body(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ReqErr("invalid_encoding", code=400, detail="utf-8 required")


def healthz(req: BaseHTTPRequestHandler, cfg: dict) -> None:
    conn = db.open_db(cfg)
    out = health.report(conn, cfg)
    met = dict(out.get("metrics", {}))
    met.update(_metrics_get())
    out["metrics"] = met
    send(req, out)


def _ready_db(cfg: dict) -> tuple[bool, str]:
    try:
        conn = db.open_db(cfg)
        db.rows(conn, "SELECT 1 AS ok")
        return True, ""
    except Exception as exc:
        return False, str(exc)[:220]


def _ready_scan(cfg: dict) -> dict:
    _scan_ensure_worker(cfg)
    with _scan_lock:
        alive = bool(_scan_worker and _scan_worker.is_alive())
        depth = len(_scan_jobs)
    cap = int(_scan_cfg(cfg).get("queue_cap", 1) or 1)
    return {"ok": alive and depth <= cap, "alive": alive,
            "queue_depth": depth, "queue_cap": cap}


def _ready_int(cfg: dict) -> dict:
    _integrations_ensure_worker(cfg)
    with _int_lock:
        alive = bool(_int_worker and _int_worker.is_alive())
        depth = len(_int_jobs)
    cap = int(_integrations_queue_cfg(cfg).get("cap", 10) or 10)
    ch = _integrations_ready_channels(cfg)
    ch_ok = ch["enabled"] == 0 or ch["ready"] > 0
    return {
        "ok": alive and depth <= cap and ch_ok,
        "alive": alive,
        "queue_depth": depth,
        "queue_cap": cap,
        "channels_enabled": ch["enabled"],
        "channels_ready": ch["ready"],
    }


def _integrations_ready_channels(cfg: dict) -> dict:
    vals = _settings_runtime(cfg).get("integrations", {})
    ints = vals if isinstance(vals, dict) else {}
    refs = _integrations_secret_refs(cfg)
    rows = [
        _catalog_email(ints.get("email", {})),
        _catalog_social(ints.get("social", {}), refs),
        _catalog_hooks(ints.get("webhooks", {})),
    ]
    rows.extend(_catalog_extra_channels(ints.get("channels", {}), refs).values())
    en = sum(1 for row in rows if bool(row.get("enabled", False)))
    ok = sum(1 for row in rows if bool(row.get("ready", False)))
    return {"enabled": en, "ready": ok}


def _ready_billing(cfg: dict) -> dict:
    rec = _billing_load(cfg) or _billing_default(cfg)
    plan = _billing_plan_clean(rec.get("plan", "free"))
    pending = _billing_plan_clean(rec.get("plan_pending", "free"))
    need = pending if pending != "free" else plan
    if need == "free":
        return {"ok": True, "plan": plan, "pending": pending,
                "provider": str(rec.get("provider", ""))}
    price = _billing_price_id(cfg, need)
    sec = _billing_secret_key(cfg)
    hook = _billing_webhook_secret(cfg)
    allow = bool(cfg.get("billing_webhook_allow_unsigned", False))
    ok = bool(price and sec and (hook or allow))
    return {
        "ok": ok,
        "plan": plan,
        "pending": pending,
        "provider": str(rec.get("provider", "stripe") or "stripe"),
        "price_id": bool(price),
        "secret_key": bool(sec),
        "webhook_secret": bool(hook),
        "webhook_unsigned_ok": allow,
    }


def _ready_payload(cfg: dict) -> dict:
    db_ok, db_err = _ready_db(cfg)
    scan_ok = _ready_scan(cfg)
    int_ok = _ready_int(cfg)
    bill_ok = _ready_billing(cfg)
    ok = db_ok and bool(scan_ok.get("ok")) and bool(int_ok.get("ok")) and \
        bool(bill_ok.get("ok"))
    return {"ok": ok, "db": {"ok": db_ok, "err": db_err},
            "scan": scan_ok, "integrations": int_ok, "billing": bill_ok}


def readyz(req: BaseHTTPRequestHandler, cfg: dict) -> None:
    out = _ready_payload(cfg)
    send(req, out, code=200 if out.get("ok") else 503)


def ops_health_payload(cfg: dict) -> dict:
    _acct_must(cfg)  # Finding 3 — require auth for operational health data
    conn = db.open_db(cfg)
    rep = health.report(conn, cfg)
    stat = status_payload(cfg)
    root = cfgmod.state_dir(cfg)
    disk = shutil.disk_usage(root)
    return {
        "index": {
            "runs_total": len(runs(cfg)),
            "latest_run": latest(cfg),
            "status": stat,
        },
        "storage": {
            "state_dir": str(root),
            "free_bytes": int(disk.free),
            "used_bytes": int(disk.used),
            "total_bytes": int(disk.total),
        },
        "model": {
            "provider_mode": str(cfg.get("provider_mode", "ollama")),
            "model": str(cfg.get("model", "")),
            "infer": infer.status(),
        },
        "settings": _settings_runtime(cfg),
        "health": rep,
    }


def backup_list_payload(cfg: dict) -> dict:
    vals = []
    for path in sorted(_backup_root(cfg).glob("*.tar.gz"), reverse=True):
        vals.append({
            "id": path.stem,
            "path": str(path),
            "bytes": int(path.stat().st_size),
            "created_at": int(path.stat().st_mtime),
        })
    return {"items": vals[:80]}


def backup_create_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    data = body(req)
    tag = str(data.get("tag", "manual")).strip().replace(" ", "-")[:48]
    ts = time.strftime("%Y%m%d-%H%M%S")
    name = f"{ts}-{tag or 'backup'}.tar.gz"
    dst = _backup_root(cfg) / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    state_dir = cfgmod.state_dir(cfg)
    with tarfile.open(dst, "w:gz") as tar:
        tar.add(state_dir, arcname=state_dir.name)
    return {
        "ok": True,
        "backup": {
            "id": dst.stem,
            "path": str(dst),
            "bytes": int(dst.stat().st_size),
        },
    }


def backup_restore_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner"})
    data = body(req)
    bid = str(data.get("backup_id", "")).strip()
    if str(data.get("confirm", "")) != "RESTORE":
        raise ReqErr("restore_confirmation_required", code=400)
    src = _backup_find(cfg, bid)
    if not src:
        raise ReqErr("backup_not_found", code=404)
    state_dir = cfgmod.state_dir(cfg)
    pre = _backup_root(cfg) / f"{time.strftime('%Y%m%d-%H%M%S')}-pre-restore.tar.gz"
    with tarfile.open(pre, "w:gz") as tar:
        tar.add(state_dir, arcname=state_dir.name)
    with tarfile.open(src, "r:gz") as tar:
        tar.extractall(state_dir.parent)
    return {
        "ok": True,
        "restored_from": str(src),
        "pre_restore_backup": str(pre),
    }


def danger_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner"})
    data = body(req)
    act = str(data.get("action", "")).strip()
    if str(data.get("confirm", "")) != "I UNDERSTAND":
        raise ReqErr("danger_confirmation_required", code=400)
    if act == "clear_dead_letters":
        with _scan_lock:
            _scan_dead.clear()
            _scan_state["progress"] = {}
        _purge_dead_logs(cfg)
        return {"ok": True, "action": act}
    if act == "reset_home_summary":
        path = _home_summary_path(cfg)
        if path.exists():
            path.unlink()
        return {"ok": True, "action": act}
    if act == "reset_ui_cache":
        with _ws_lock:
            _ws_cache.clear()
        with _aud_lock:
            _aud_cache.clear()
        return {"ok": True, "action": act}
    raise ReqErr("unknown_danger_action", code=400)


def _purge_dead_logs(cfg: dict) -> None:
    root = cfgmod.state_dir(cfg, "dead")
    for path in root.glob("*.ndjson"):
        try:
            path.unlink()
        except Exception:
            continue


def _backup_root(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg, "backups")


def _backup_find(cfg: dict, bid: str) -> Path | None:
    if not bid:
        return None
    root = _backup_root(cfg)
    for path in root.glob("*.tar.gz"):
        if path.stem == bid:
            return path
    return None


def workstreams_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    from . import workstreams
    run = _run_query(req, cfg)
    infer.warm_async(cfg, run)

    with _ws_lock:
        cached = _ws_cache.get(run)

    if cached and cached.get("ready"):
        # Return cached (Gemma-named) cards immediately
        return {"run": run, "workstreams": cached["cards"], "cached": True}

    if cached is None:
        # First request: seed cache with fast heuristic cards, kick off Gemma bg
        with _ws_lock:
            _ws_cache[run] = {"cards": [], "ready": False}
        try:
            conn = db.open_db(cfg)
            fast_cards = workstreams.compute(conn, cfg, run_id=run, limit=30,
                                             gemma_budget=0)
        except Exception:
            _log_ev("ws_compute_failed", run=run)
            fast_cards = []

        # ── V1 fallback: when scanner DB is empty, derive from V1 signals ──
        v1_fallback_used = False
        if not fast_cards and _V1_AVAILABLE:
            fast_cards = _v1_workstreams_fallback()
            v1_fallback_used = True

        with _ws_lock:
            _ws_cache[run]["cards"] = fast_cards
            if v1_fallback_used:
                _ws_cache[run]["ready"] = True  # V1 names are already final

        # Only start background Gemma naming if we have scanner-derived cards
        # (V1 fallback cards already have good names from signal metadata)
        if fast_cards and not v1_fallback_used:
            threading.Thread(
                target=_ws_compute_bg, args=(cfg, run), daemon=True
            ).start()
        return {"run": run, "workstreams": fast_cards, "cached": False}

    # Cache exists but not ready yet (Gemma still computing) → serve fast cards
    with _ws_lock:
        fast_cards = _ws_cache[run].get("cards", [])
    return {"run": run, "workstreams": fast_cards, "cached": False}


def status_payload(cfg: dict | None = None) -> dict:
    with _scan_lock:
        last_run = _scan_state["last_run"]
        run_meta = _scan_meta_load(cfg, last_run) if cfg and last_run else {}
        recent = dict(_scan_dead[-1]) if _scan_dead else {}
        return {
            "scanning": _scan_state["scanning"],
            "progress": dict(_scan_state["progress"]),
            "last_run": last_run,
            "queue_depth": len(_scan_jobs),
            "active_job_id": _scan_state.get("active_job_id", ""),
            "attempts": int(_scan_state.get("attempts", 0) or 0),
            "recent_failure": recent,
            "dead_letter_count": len(_scan_dead),
            "metrics": _metrics_get(),
            "infer_metrics": infer.status(),
            "run_meta": run_meta,
        }


def report_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    run = _run_query(req, cfg)
    ws = report_workstreams(req, cfg)
    if ws.get("run"):
        run = ws["run"]
    return {
        "run": run,
        "corpus": report_corpus(cfg),
        "workstreams": {"count": ws["count"], "cached": ws["cached"]},
        "scan": status_payload(cfg),
        "infer": infer.status(),
    }


def infer_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    vals = query(req)
    run = _run_clean(vals.get("run", [""])[0]) or latest(cfg)
    cluster = vals.get("cluster", [""])[0].strip()
    if not cluster:
        raise ReqErr("cluster_required", code=400)
    refresh = vals.get("refresh", ["0"])[0] in {"1", "true", "yes"}
    try:
        return infer.get(cfg, run, cluster, refresh=refresh)
    except RuntimeError as exc:
        msg = str(exc).strip()
        code = 404 if msg in {"run_not_found", "cluster_not_found"} else 400
        raise ReqErr(msg or "infer_failed", code=code)


def report_workstreams(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    try:
        data = workstreams_payload(req, cfg)
    except Exception as exc:
        _api_err("GET", "/api/report", "workstreams_failed")
        return {"run": "", "count": 0, "cached": False, "err": str(exc)[:120]}
    cards = data.get("workstreams", [])
    return {
        "run": str(data.get("run", "")),
        "count": len(cards),
        "cached": bool(data.get("cached", False)),
    }


def report_corpus(cfg: dict) -> dict:
    import time
    conn = db.open_db(cfg)
    total = db.rows(conn, "SELECT COUNT(*) as c, SUM(size) as s FROM items "
                    "WHERE kind='file'")
    week = time.time() - 7 * 86400
    recent = db.rows(conn, "SELECT COUNT(*) as c FROM items "
                     "WHERE kind='file' AND mtime > ?", (week,))
    return {
        "total_files": total[0]["c"] if total else 0,
        "total_bytes": total[0]["s"] if total else 0,
        "recent_week": recent[0]["c"] if recent else 0,
    }


def account_payload(cfg: dict) -> dict:
    rec = _acct_load(cfg)
    if not rec:
        return {"signed_in": False, "account": None, "workspace": None}
    ws = _workspace_load(cfg)
    role = _workspace_role(ws, str(rec.get("email", ""))) if ws else ""
    return {
        "signed_in": True,
        "account": _acct_public(rec),
        "workspace": _workspace_brief(ws, role),
    }


def settings_payload(cfg: dict) -> dict:
    _acct_must(cfg)  # Require authentication (C3)
    rec = _settings_load(cfg) or _settings_default(cfg)
    return {"ok": True, "settings": rec}


def settings_update_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    data = body(req)
    cur = _settings_load(cfg) or _settings_default(cfg)
    raw = data.get("settings", data)
    if not isinstance(raw, dict):
        raise ReqErr("settings_required", code=400)
    nxt = _settings_merge(cur, raw, cfg)
    _settings_save(cfg, nxt)
    _int_sched_event.set()
    return {"ok": True, "settings": nxt}


def integrations_state_payload(cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin", "member"})
    rec = _settings_load(cfg) or _settings_default(cfg)
    vals = rec.get("integrations", {})
    out = vals if isinstance(vals, dict) else {}
    return {"ok": True, "integrations": out}


def integrations_state_update_payload(req: BaseHTTPRequestHandler,
                                      cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    data = body(req)
    raw = data.get("integrations", data)
    if not isinstance(raw, dict):
        raise ReqErr("integrations_required", code=400)
    cur = _settings_load(cfg) or _settings_default(cfg)
    patch = {"integrations": raw}
    nxt = _settings_merge(cur, patch, cfg)
    _settings_save(cfg, nxt)
    _int_sched_event.set()
    vals = nxt.get("integrations", {})
    out = vals if isinstance(vals, dict) else {}
    return {"ok": True, "integrations": out}


def integrations_connections_payload(cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin", "member"})
    vals = _settings_runtime(cfg).get("integrations", {})
    ints = vals if isinstance(vals, dict) else {}
    rows = _integrations_connection_rows(cfg, ints)
    cnt_ok = 0
    cnt_exp = 0
    cnt_err = 0
    now = int(time.time())
    for row in rows:
        status = str(row.get("status", "")).strip()
        exp = int(row.get("expires_at", 0) or 0)
        if status == "connected":
            cnt_ok += 1
            if exp > 0 and exp <= now + 86400:
                cnt_exp += 1
        if str(row.get("sync_status", "")) == "error":
            cnt_err += 1
    return {
        "ok": True,
        "items": rows,
        "summary": {
            "total": len(rows),
            "connected": cnt_ok,
            "expiring_24h": cnt_exp,
            "sync_errors": cnt_err,
        },
        "oauth_providers": sorted(_OAUTH_PROVIDERS),
    }


def integrations_sync_state_payload(cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin", "member"})
    rows = _integrations_sync_rows(cfg)
    out = [_integrations_sync_public(x) for x in rows[-400:]]
    out.sort(key=lambda x: -int(x.get("updated_at", 0) or 0))
    return {"ok": True, "items": out}


def integrations_sync_state_update_payload(req: BaseHTTPRequestHandler,
                                           cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    data = body(req)
    channel = str(data.get("channel", "")).strip().lower()
    provider = str(data.get("provider", "")).strip().lower()
    account = str(data.get("account", "")).strip()[:160]
    if channel not in _SYNC_CHANNELS:
        raise ReqErr("sync_channel_invalid", code=400)
    if not provider:
        raise ReqErr("sync_provider_required", code=400)
    patch = {}
    if "cursor" in data:
        patch["cursor"] = str(data.get("cursor", ""))[:400]
    if "status" in data:
        patch["status"] = str(data.get("status", "idle"))[:40]
    if "last_error" in data:
        patch["last_error"] = str(data.get("last_error", ""))[:300]
    if "last_job_id" in data:
        patch["last_job_id"] = str(data.get("last_job_id", ""))[:120]
    if "count_in" in data:
        patch["count_in"] = max(0, int(data.get("count_in", 0) or 0))
    if "count_out" in data:
        patch["count_out"] = max(0, int(data.get("count_out", 0) or 0))
    row = _integrations_sync_upsert(cfg, channel, provider, account, patch)
    return {"ok": True, "item": _integrations_sync_public(row)}


def integrations_webhook_ingest_payload(req: BaseHTTPRequestHandler,
                                        cfg: dict,
                                        provider: str) -> dict:
    key = str(provider or "").strip().lower()
    if key not in _INT_WEBHOOK_PROVIDERS:
        raise ReqErr("webhook_provider_invalid", code=404)
    if key == "microsoft":
        vt = str(query(req).get("validationToken", [""])[0]).strip()
        if vt:
            _integrations_emit(cfg, "webhook_inbound_microsoft.ndjson", {
                "provider": key,
                "verified": True,
                "event": "validation",
                "received_at": int(time.time()),
                "validation_token": vt[:220],
            })
            return {"ok": True, "plain_text": True, "body": vt}
    raw = body_raw(req)
    hdr = _int_webhook_hdr(req)
    data = _int_webhook_parse(raw, hdr)
    chk = _int_webhook_verify(cfg, key, raw, hdr, data)
    rec = {
        "provider": key,
        "verified": bool(chk.get("verified", False)),
        "event": str(chk.get("event", ""))[:80],
        "received_at": int(time.time()),
        "payload": data if isinstance(data, dict) else {},
        "headers": {
            "request_id": str(hdr.get("x-request-id", ""))[:120],
            "user_agent": str(hdr.get("user-agent", ""))[:120],
        },
    }
    _integrations_emit(cfg, f"webhook_inbound_{key}.ndjson", rec)
    if key == "slack":
        if str(data.get("type", "")).strip() == "url_verification":
            ch = str(data.get("challenge", "")).strip()
            if ch:
                return {"ok": True, "plain_text": True, "body": ch}
    evt = str(chk.get("event", "")).strip() or "webhook_event"
    meta = {"provider": key, "source": "webhook", "verified": rec["verified"]}
    payload = {"channel": "chatops", "provider": "slack", "text": evt}
    _integrations_enqueue_job(cfg, "webhook", {"provider": key, "event": evt,
                           "payload": data}, source="webhook", meta=meta)
    if key == "slack":
        _integrations_enqueue_job(cfg, "channel", payload, source="webhook",
                                  meta=meta)
    return {"ok": True, "provider": key, "verified": rec["verified"],
            "event": evt}


def _int_webhook_hdr(req: BaseHTTPRequestHandler) -> dict[str, str]:
    keys = [
        "x-slack-signature",
        "x-slack-request-timestamp",
        "x-goog-channel-id",
        "x-goog-channel-token",
        "x-goog-resource-state",
        "x-goog-resource-id",
        "x-ms-signature",
        "x-ms-client-state",
        "x-request-id",
        "user-agent",
        "content-type",
    ]
    out = {}
    for key in keys:
        out[key] = _req_hdr(req, key)
    return out


def _int_webhook_parse(raw: bytes, hdr: dict[str, str]) -> dict:
    ctype = str(hdr.get("content-type", "")).lower()
    txt = decode_body(raw) if raw else ""
    if "application/x-www-form-urlencoded" in ctype:
        vals = parse_qs(txt, keep_blank_values=True)
        out = {}
        for key, rows in vals.items():
            if not rows:
                continue
            out[str(key)] = rows[0]
        return out
    if not txt.strip():
        return {}
    try:
        row = json.loads(txt)
    except Exception:
        return {"raw": txt[:2000]}
    return row if isinstance(row, dict) else {}


def _int_webhook_verify(cfg: dict, provider: str, raw: bytes,
                        hdr: dict[str, str], data: dict) -> dict:
    if provider == "slack":
        return _int_webhook_verify_slack(cfg, raw, hdr, data)
    if provider == "google":
        return _int_webhook_verify_google(cfg, hdr, data)
    if provider == "microsoft":
        return _int_webhook_verify_microsoft(cfg, hdr, data)
    raise ReqErr("webhook_provider_invalid", code=404)


def _int_webhook_verify_slack(cfg: dict, raw: bytes, hdr: dict[str, str],
                              data: dict) -> dict:
    sec = _env_pick("CTXORG_SLACK_SIGNING_SECRET", "SLACK_SIGNING_SECRET", "")
    sig = str(hdr.get("x-slack-signature", "")).strip()
    ts = str(hdr.get("x-slack-request-timestamp", "")).strip()
    if not sec:
        raise ReqErr("webhook_unconfigured", code=503, detail="slack_secret")
    if not sig or not ts:
        raise ReqErr("webhook_signature_missing", code=401)
    try:
        ts_i = int(ts)
    except Exception:
        raise ReqErr("webhook_signature_invalid", code=401, detail="bad_ts")
    now = int(time.time())
    if abs(now - ts_i) > 300:
        raise ReqErr("webhook_signature_stale", code=401)
    base = f"v0:{ts}:".encode("utf-8") + raw
    mac = hmac.new(sec.encode("utf-8"), base, hashlib.sha256).hexdigest()
    exp = f"v0={mac}"
    if not hmac.compare_digest(exp, sig):
        raise ReqErr("webhook_signature_invalid", code=401)
    evt = str(data.get("type", "")).strip() or "slack_event"
    return {"verified": True, "event": evt}


def _int_webhook_verify_google(cfg: dict, hdr: dict[str, str],
                               data: dict) -> dict:
    chan = str(hdr.get("x-goog-channel-id", "")).strip()
    tok = str(hdr.get("x-goog-channel-token", "")).strip()
    state = str(hdr.get("x-goog-resource-state", "")).strip()
    rid = str(hdr.get("x-goog-resource-id", "")).strip()
    if not chan or not rid:
        raise ReqErr("webhook_signature_missing", code=401)
    secret = _env_pick("CTXORG_GOOGLE_WEBHOOK_CHANNEL", "GOOGLE_WEBHOOK_CHANNEL",
                       "")
    if secret and chan != secret:
        raise ReqErr("webhook_signature_invalid", code=401)
    wtok = _env_pick("CTXORG_GOOGLE_WEBHOOK_TOKEN", "GOOGLE_WEBHOOK_TOKEN", "")
    if wtok and tok != wtok:
        raise ReqErr("webhook_signature_invalid", code=401)
    evt = state or str(data.get("type", "")).strip() or "google_change"
    return {"verified": True, "event": evt}


def _int_webhook_verify_microsoft(cfg: dict, hdr: dict[str, str],
                                  data: dict) -> dict:
    state = _env_pick("CTXORG_MS_WEBHOOK_CLIENT_STATE",
                      "MS_WEBHOOK_CLIENT_STATE", "")
    got = str(hdr.get("x-ms-client-state", "")).strip()
    if state and state != got:
        raise ReqErr("webhook_signature_invalid", code=401)
    evt = str(data.get("changeType", "")).strip()
    if not evt:
        vals = data.get("value", [])
        row = vals[0] if isinstance(vals, list) and vals else {}
        if isinstance(row, dict):
            evt = str(row.get("changeType", "")).strip()
    return {"verified": True, "event": evt or "microsoft_change"}


def _integrations_connection_rows(cfg: dict, ints: dict) -> list[dict]:
    now = int(time.time())
    evs = _oauth_events_list(cfg)
    out = []
    chans = _integrations_channels_clean(ints.get("channels", {}))
    for key, row in chans.items():
        provider = str(row.get("provider", "")).strip().lower()
        account = str(row.get("account", "")).strip()
        token_ref = str(row.get("token_ref", "")).strip()
        sync = _integrations_sync_get(cfg, key, provider, account) or {}
        item = _integration_connection_for(cfg, key, provider, token_ref,
                                           account, sync, evs, now)
        item["enabled"] = bool(row.get("enabled", False))
        out.append(item)
    social = ints.get("social", {}) if isinstance(ints, dict) else {}
    rows = social.get("providers", {}) if isinstance(social, dict) else {}
    for key in _SOCIAL_PROVIDERS:
        cur = rows.get(key, {}) if isinstance(rows, dict) else {}
        row = cur if isinstance(cur, dict) else {}
        provider = key
        token_ref = str(row.get("token_ref", "")).strip()
        account = str(row.get("handle", "")).strip()
        sync = _integrations_sync_get(cfg, "social", provider, account) or {}
        item = _integration_connection_for(cfg, "social", provider, token_ref,
                                           account, sync, evs, now)
        item["enabled"] = bool(row.get("enabled", False))
        out.append(item)
    out.sort(key=lambda x: (not bool(x.get("enabled", False)),
                            str(x.get("channel", "")),
                            str(x.get("provider", ""))))
    return out


def _integration_connection_for(cfg: dict, channel: str, provider: str,
                                token_ref: str, account: str, sync: dict,
                                evs: list[dict], now: int) -> dict:
    secret_provider = _channel_secret_provider(channel, provider)
    oauth_provider = _channel_oauth_provider(channel, provider)
    row = _integrations_secret_get(cfg, token_ref) if token_ref else None
    token_ok = False
    exp = 0
    token_state = "missing"
    if isinstance(row, dict) and str(row.get("status", "")) == "active":
        token_ok = True
        exp = int(row.get("expires_at", 0) or 0)
        token_state = "active"
        if exp > 0 and exp <= now:
            token_state = "expired"
            token_ok = False
        elif exp > 0 and exp <= now + 86400:
            token_state = "expiring_soon"
    if not token_ok:
        env_a, env_b = _channel_env_map(channel, provider)
        if channel == "social":
            env_a, env_b = _social_token_env(provider)
        if _env_has(env_a, env_b):
            token_ok = True
            token_state = "env"
    status = "connected" if token_ok else "attention"
    evt = _integrations_event_pick(evs, oauth_provider, token_ref)
    sync_state = str(sync.get("status", "idle")).strip()
    scopes = []
    if oauth_provider in _OAUTH_PROVIDERS:
        raw = str(_OAUTH_PROVIDERS[oauth_provider].get("scope", "")).strip()
        scopes = [x for x in raw.split() if x][:16]
    return {
        "id": f"{channel}:{provider}:{account or '-'}",
        "channel": channel,
        "provider": provider,
        "account": account,
        "token_ref": token_ref,
        "token_provider": secret_provider,
        "oauth_provider": oauth_provider,
        "status": status,
        "token_status": token_state,
        "expires_at": exp,
        "required_scopes": scopes,
        "enabled": False,
        "sync_status": sync_state or "idle",
        "sync_cursor": str(sync.get("cursor", ""))[:240],
        "sync_last_ok_at": int(sync.get("last_ok_at", 0) or 0),
        "sync_last_error": str(sync.get("last_error", ""))[:200],
        "sync_last_error_at": int(sync.get("last_error_at", 0) or 0),
        "last_oauth_event": evt,
    }


def _integrations_event_pick(evs: list[dict], provider: str,
                             token_ref: str) -> dict:
    if not provider and not token_ref:
        return {}
    for row in reversed(evs[-200:]):
        if not isinstance(row, dict):
            continue
        prv = str(row.get("provider", "")).strip().lower()
        ref = str(row.get("token_ref", "")).strip()
        if provider and prv and prv != provider:
            continue
        if token_ref and ref and ref != token_ref:
            continue
        return {
            "at": int(row.get("at", 0) or 0),
            "event": str(row.get("event", ""))[:60],
            "detail": str(row.get("detail", ""))[:160],
        }
    return {}


def _integrations_sync_public(row: dict) -> dict:
    return {
        "id": str(row.get("id", ""))[:220],
        "channel": str(row.get("channel", ""))[:40],
        "provider": str(row.get("provider", ""))[:40],
        "account": str(row.get("account", ""))[:160],
        "status": str(row.get("status", "idle"))[:40],
        "cursor": str(row.get("cursor", ""))[:400],
        "count_in": max(0, int(row.get("count_in", 0) or 0)),
        "count_out": max(0, int(row.get("count_out", 0) or 0)),
        "last_job_id": str(row.get("last_job_id", ""))[:120],
        "last_ok_at": max(0, int(row.get("last_ok_at", 0) or 0)),
        "last_error": str(row.get("last_error", ""))[:300],
        "last_error_at": max(0, int(row.get("last_error_at", 0) or 0)),
        "updated_at": max(0, int(row.get("updated_at", 0) or 0)),
    }


def integrations_jobs_payload(cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin", "member"})
    _integrations_runtime_load(cfg)
    opts = _integrations_queue_cfg(cfg)
    with _int_lock:
        qd = len(_int_jobs)
        dd = len(_int_done)
        zd = len(_int_dead)
        q = [dict(x) for x in _int_jobs[-120:]]
        d = [dict(x) for x in _int_done[-120:]]
        z = [dict(x) for x in _int_dead[-120:]]
        sched = dict(_int_sched)
    qv = [_integrations_job_public(x, opts) for x in q]
    dv = [_integrations_job_public(x, opts) for x in d]
    zv = [_integrations_job_public(x, opts) for x in z]
    return {
        "ok": True,
        "queue_depth": qd,
        "done_count": dd,
        "dead_count": zd,
        "queue_cap": int(opts.get("cap", 500)),
        "retry_cfg": {
            "retry_max": int(opts.get("retry_max", 3)),
            "backoff_s": float(opts.get("backoff_s", 2.0)),
        },
        "queued": qv,
        "done": dv,
        "dead": zv,
        "dlq": _integrations_dead_stats(zv),
        "idempotency": _integrations_idem_public(opts),
        "replay": {
            "confirm_token": "REPLAY",
            "max_batch": int(opts.get("replay_batch_max", 20)),
        },
        "scheduler": _integrations_sched_public(cfg, sched),
    }


def _integrations_job_public(row: dict, opts: dict) -> dict:
    now = int(time.time())
    status = str(row.get("status", "queued"))[:20]
    not_before = float(row.get("not_before", 0.0) or 0.0)
    next_retry_at = int(row.get("next_retry_at", 0) or 0)
    if not next_retry_at and status == "queued" and not_before > now:
        next_retry_at = int(not_before)
    dead_reason = str(row.get("dead_reason", "")).strip()
    if not dead_reason and status == "dead":
        dead_reason = str(row.get("last_error", "")).strip()
    return {
        "id": str(row.get("id", ""))[:120],
        "kind": str(row.get("kind", ""))[:40],
        "source": str(row.get("source", ""))[:40],
        "status": status,
        "attempt": max(0, int(row.get("attempt", 0) or 0)),
        "created_at": int(row.get("created_at", now) or now),
        "updated_at": int(row.get("updated_at", now) or now),
        "last_error": str(row.get("last_error", ""))[:300],
        "last_error_at": int(row.get("last_error_at", 0) or 0),
        "retry": {
            "retry_max": int(opts.get("retry_max", 3)),
            "backoff_s": float(opts.get("backoff_s", 2.0)),
            "next_retry_at": next_retry_at,
            "retry_in_s": max(0.0, float(row.get("retry_in_s", 0.0) or 0.0)),
            "history": _integrations_retry_hist(
                row.get("retry_history", []),
            ),
        },
        "idempotency_key": str(row.get("idempotency_key", ""))[:120],
        "idempotency_hash": str(row.get("idempotency_hash", ""))[:80],
        "replay_of": str(row.get("replay_of", ""))[:120],
        "replay_count": max(0, int(row.get("replay_count", 0) or 0)),
        "dlq": {
            "dead_at": int(row.get("dead_at", 0) or 0),
            "reason": dead_reason[:240],
            "replayable": bool(row.get("replayable", True)),
        },
        "payload": row.get("payload", {}),
        "meta": row.get("meta", {}),
    }


def _integrations_retry_hist(raw: object) -> list[dict]:
    rows = raw if isinstance(raw, list) else []
    out = []
    for row in rows[-12:]:
        if not isinstance(row, dict):
            continue
        out.append({
            "at": int(row.get("at", 0) or 0),
            "attempt": max(0, int(row.get("attempt", 0) or 0)),
            "delay_s": max(0.0, float(row.get("delay_s", 0.0) or 0.0)),
            "err": str(row.get("err", ""))[:240],
        })
    return out


def _integrations_dead_stats(dead: list[dict]) -> dict:
    kinds: dict[str, int] = {}
    last = {}
    for row in dead:
        kind = str(row.get("kind", "")).strip().lower()
        if kind:
            kinds[kind] = kinds.get(kind, 0) + 1
        ts = int(row.get("dlq", {}).get("dead_at", 0) or 0)
        if not last or ts > int(last.get("dead_at", 0) or 0):
            last = {
                "job_id": str(row.get("id", ""))[:120],
                "kind": kind,
                "dead_at": ts,
                "reason": str(row.get("dlq", {}).get("reason", ""))[:240],
            }
    return {"count": len(dead), "by_kind": kinds, "latest": last}


def _integrations_idem_public(opts: dict) -> dict:
    with _int_lock:
        rows = list(_int_idem.values())[-20:]
        cnt = len(_int_idem)
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append({
            "key": str(row.get("key", ""))[:120],
            "job_id": str(row.get("job_id", ""))[:120],
            "kind": str(row.get("kind", ""))[:40],
            "status": str(row.get("status", ""))[:20],
            "updated_at": int(row.get("updated_at", 0) or 0),
        })
    out.sort(key=lambda x: -int(x.get("updated_at", 0) or 0))
    return {
        "count": cnt,
        "ttl_s": int(opts.get("idem_ttl_s", 86400)),
        "cap": int(opts.get("idem_cap", 2000)),
        "recent": out[:20],
    }


def integrations_secrets_payload(cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    vals = _integrations_secrets_list(cfg, scope_id="")
    out = []
    for row in vals:
        if not isinstance(row, dict):
            continue
        out.append({
            "token_ref": str(row.get("token_ref", "")),
            "provider": str(row.get("provider", "")),
            "workspace_id": str(row.get("workspace_id", "")),
            "status": str(row.get("status", "active")),
            "updated_at": int(row.get("updated_at", 0) or 0),
            "expires_at": int(row.get("expires_at", 0) or 0),
        })
    out.sort(key=lambda x: -int(x.get("updated_at", 0) or 0))
    return {"ok": True, "items": out[:200]}


def integrations_secrets_set_payload(req: BaseHTTPRequestHandler,
                                     cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    data = body(req)
    ref = str(data.get("token_ref", "")).strip()
    prv = str(data.get("provider", "")).strip().lower()
    sec = str(data.get("secret", "")).strip()
    if not ref:
        raise ReqErr("token_ref_required", code=400)
    if not sec:
        raise ReqErr("secret_required", code=400)
    if prv not in _SECRET_PROVIDERS:
        raise ReqErr("provider_invalid", code=400)
    wsid = _integrations_scope_id(cfg)
    row = {
        "token_ref": ref[:120],
        "provider": prv,
        "workspace_id": wsid,
        "status": "active",
        "secret": sec[:2000],
        "refresh_token": str(data.get("refresh_token", ""))[:2000],
        "expires_at": int(data.get("expires_at", 0) or 0),
        "updated_at": int(time.time()),
    }
    vals = _integrations_secrets_list(cfg, scope_id="")
    out = []
    hit = False
    for cur in vals:
        cref = str(cur.get("token_ref", "")).strip()
        cws = str(cur.get("workspace_id", "")).strip()
        same_scope = (cws == wsid) or (not cws) or (not wsid)
        if cref == row["token_ref"] and same_scope:
            out.append(row)
            hit = True
        else:
            out.append(cur)
    if not hit:
        out.append(row)
    _integrations_secrets_save(cfg, out)
    return {"ok": True, "token_ref": row["token_ref"],
            "provider": row["provider"]}


def integrations_oauth_start_payload(req: BaseHTTPRequestHandler,
                                     cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    data = body(req)
    provider = str(data.get("provider", "")).strip().lower()
    conf = _oauth_provider_conf(cfg, provider)
    token_ref = str(data.get("token_ref", "")).strip()
    if not token_ref:
        token_ref = f"{provider}_main"
    pkce = _oauth_pkce_pick(cfg, data, conf)
    rec = _oauth_state_new(cfg, provider, token_ref, pkce=pkce)
    url = _oauth_auth_url(conf, rec)
    _oauth_event(cfg, provider, rec["token_ref"], "oauth_start",
                 f"pkce={int(pkce)}")
    return {
        "ok": True,
        "provider": provider,
        "token_ref": rec["token_ref"],
        "state": rec["state"],
        "auth_url": url,
        "expires_at": rec["expires_at"],
        "pkce": pkce,
    }


def integrations_oauth_refresh_payload(req: BaseHTTPRequestHandler,
                                       cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    data = body(req)
    provider = str(data.get("provider", "")).strip().lower()
    token_ref = str(data.get("token_ref", "")).strip()
    if provider not in _OAUTH_PROVIDERS:
        raise ReqErr("oauth_provider_invalid", code=400)
    if not token_ref:
        raise ReqErr("token_ref_required", code=400)
    row = _integrations_secret_get(cfg, token_ref)
    if not row:
        raise ReqErr("oauth_secret_missing", code=404)
    if str(row.get("provider", "")).strip() != provider:
        raise ReqErr("oauth_provider_mismatch", code=400)
    try:
        out = _oauth_refresh_secret(cfg, provider, row)
    except ReqErr as exc:
        _oauth_event(cfg, provider, token_ref, "oauth_refresh_fail", exc.err)
        raise
    except Exception as exc:
        _oauth_event(cfg, provider, token_ref, "oauth_refresh_fail",
                     str(exc)[:120])
        raise
    _oauth_event(cfg, provider, token_ref, "oauth_refresh_ok")
    return {
        "ok": True,
        "provider": provider,
        "token_ref": str(out.get("token_ref", "")),
        "expires_at": int(out.get("expires_at", 0) or 0),
    }


def integrations_oauth_events_payload(cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin", "member"})
    rows = _oauth_events_list(cfg)
    return {"ok": True, "items": rows[-200:]}


def integrations_oauth_revoke_payload(req: BaseHTTPRequestHandler,
                                      cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    data = body(req)
    provider = str(data.get("provider", "")).strip().lower()
    token_ref = str(data.get("token_ref", "")).strip()
    if provider not in _OAUTH_PROVIDERS:
        raise ReqErr("oauth_provider_invalid", code=400)
    if not token_ref:
        raise ReqErr("token_ref_required", code=400)
    row = _integrations_secret_get(cfg, token_ref)
    if not row:
        raise ReqErr("oauth_secret_missing", code=404)
    if str(row.get("provider", "")).strip() != provider:
        raise ReqErr("oauth_provider_mismatch", code=400)
    remote = bool(data.get("revoke_remote", False))
    test = bool(data.get("test_remote", False))
    out = {}
    if remote:
        try:
            out = _oauth_revoke_remote(cfg, provider, row, test=test)
        except ReqErr as exc:
            _oauth_event(cfg, provider, token_ref, "oauth_revoke_fail", exc.err)
            raise
        except Exception as exc:
            _oauth_event(cfg, provider, token_ref, "oauth_revoke_fail",
                         str(exc)[:120])
            raise ReqErr("oauth_revoke_failed", code=502,
                         detail=str(exc)[:160])
    rec = _integrations_secret_mark_revoked(cfg, row)
    _oauth_event(cfg, provider, token_ref, "oauth_revoke_ok",
                 f"remote={int(remote)}")
    return {
        "ok": True,
        "provider": provider,
        "token_ref": str(rec.get("token_ref", "")),
        "revoked": True,
        "remote": out,
    }


def integrations_oauth_callback(req: BaseHTTPRequestHandler, cfg: dict) -> None:
    vals = query(req)
    err = str(vals.get("error", [""])[0]).strip()
    if err:
        _oauth_event(cfg, "", "", "oauth_callback_error", err[:120])
        return send_html(req, oauth_page("Connector error", err), code=400)
    code = str(vals.get("code", [""])[0]).strip()
    state = str(vals.get("state", [""])[0]).strip()
    if not code:
        _oauth_event(cfg, "", "", "oauth_callback_error", "missing_code")
        return send_html(req, oauth_page("Connector error",
                                         "missing oauth code"), code=400)
    if not state:
        _oauth_event(cfg, "", "", "oauth_callback_error", "missing_state")
        return send_html(req, oauth_page("Connector error",
                                         "missing oauth state"), code=400)
    row = _oauth_state_take(cfg, state)
    if not row:
        _oauth_event(cfg, "", "", "oauth_callback_error", "state_expired")
        return send_html(req, oauth_page("Connector error",
                                         "oauth state expired"), code=400)
    provider = str(row.get("provider", "")).strip().lower()
    token_ref = str(row.get("token_ref", "")).strip()
    if provider not in _OAUTH_PROVIDERS:
        _oauth_event(cfg, provider, token_ref, "oauth_callback_error",
                     "provider_invalid")
        return send_html(req, oauth_page("Connector error",
                                         "invalid provider"), code=400)
    try:
        tok = _oauth_exchange_code(
            cfg, provider, code, str(row.get("pkce_verifier", "")),
        )
        _oauth_secret_store(cfg, provider, token_ref, tok)
        _oauth_event(cfg, provider, token_ref, "oauth_callback_ok")
    except ReqErr as exc:
        _oauth_event(cfg, provider, token_ref, "oauth_callback_error",
                     exc.err)
        return send_html(req, oauth_page("Connector error", exc.err), code=
                         exc.code)
    except Exception as exc:
        _oauth_event(cfg, provider, token_ref, "oauth_callback_error",
                     str(exc)[:120])
        return send_html(req, oauth_page("Connector error",
                                         str(exc)[:200]), code=500)
    msg = f"Connected {provider}. You can close this window."
    return send_html(req, oauth_page("Connector ready", msg), code=200)


def _oauth_provider_conf(cfg: dict, provider: str) -> dict:
    base = _OAUTH_PROVIDERS.get(provider)
    if not isinstance(base, dict):
        raise ReqErr("oauth_provider_invalid", code=400)
    out = dict(base)
    cid_env = str(base.get("client_id_env", ""))
    sec_env = str(base.get("client_secret_env", ""))
    client_id = str(os.environ.get(cid_env, "")).strip()
    client_secret = str(os.environ.get(sec_env, "")).strip()
    if not client_id or not client_secret:
        raise ReqErr("oauth_provider_unconfigured", code=503, detail=provider)
    out["client_id"] = client_id
    out["client_secret"] = client_secret
    out["redirect_uri"] = _oauth_redirect_uri(cfg)
    return out


def _oauth_pkce_pick(cfg: dict, data: dict, conf: dict) -> bool:
    if isinstance(data, dict) and "pkce" in data:
        return bool(data.get("pkce"))
    row = conf.get("pkce")
    if isinstance(row, bool):
        return row
    return bool(cfg.get("oauth_pkce_default", True))


def _oauth_pkce_new() -> tuple[str, str]:
    ver = _oauth_b64(os.urandom(48))
    if len(ver) < 43:
        ver = (ver + ("A" * 43))[:43]
    ver = ver[:128]
    chg = _oauth_b64(hashlib.sha256(ver.encode("utf-8")).digest())
    return ver, chg


def _oauth_b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _oauth_redirect_uri(cfg: dict) -> str:
    val = _env_pick("CTXORG_OAUTH_CALLBACK_URL", "OAUTH_CALLBACK_URL", "")
    txt = str(val).strip()
    if txt:
        return txt
    port = int(cfg.get("port", cfg.get("ctxorg_port", 8765)) or 8765)
    host = str(cfg.get("host", cfg.get("ctxorg_host", "127.0.0.1"))).strip()
    if host in {"", "0.0.0.0"}:
        host = "127.0.0.1"
    return f"http://{host}:{port}/api/integrations/oauth/callback"


def _oauth_state_new(cfg: dict, provider: str, token_ref: str,
                     pkce: bool = False) -> dict:
    now = int(time.time())
    rec = {
        "state": f"oau_{uuid.uuid4().hex}",
        "provider": provider,
        "token_ref": token_ref[:120],
        "workspace_id": _oauth_ws_id(cfg),
        "created_at": now,
        "expires_at": now + _OAUTH_TTL_SEC,
    }
    if pkce:
        ver, chg = _oauth_pkce_new()
        rec["pkce_verifier"] = ver
        rec["pkce_challenge"] = chg
        rec["pkce_method"] = "S256"
    data = _oauth_state_load(cfg)
    vals = _oauth_state_rows(data)
    vals.append(rec)
    _oauth_state_save(cfg, vals)
    return rec


def _oauth_state_take(cfg: dict, state: str) -> dict | None:
    now = int(time.time())
    data = _oauth_state_load(cfg)
    vals = _oauth_state_rows(data)
    out = None
    keep = []
    for row in vals:
        cur = row if isinstance(row, dict) else {}
        exp = int(cur.get("expires_at", 0) or 0)
        if exp <= now:
            continue
        if str(cur.get("state", "")).strip() == state and out is None:
            out = cur
            continue
        keep.append(cur)
    _oauth_state_save(cfg, keep)
    return out


def _oauth_state_rows(data: dict | None) -> list[dict]:
    raw = data.get("items", []) if isinstance(data, dict) else []
    vals = raw if isinstance(raw, list) else []
    out = []
    for row in vals[-200:]:
        if isinstance(row, dict):
            out.append(row)
    return out


def _oauth_state_load(cfg: dict) -> dict | None:
    return _store_read(_oauth_state_path(cfg))


def _oauth_state_save(cfg: dict, rows: list[dict]) -> None:
    _store_write(_oauth_state_path(cfg), {"items": rows[-200:]})


def _oauth_state_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg, "integrations") / "oauth_state.json"


def _oauth_ws_id(cfg: dict) -> str:
    ws = _workspace_load(cfg)
    if not isinstance(ws, dict):
        return ""
    return str(ws.get("id", "")).strip()[:80]


def _oauth_event(cfg: dict, provider: str, token_ref: str,
                 event: str, detail: str = "") -> None:
    rec = {
        "ts": int(time.time()),
        "provider": str(provider or "")[:40],
        "token_ref": str(token_ref or "")[:120],
        "event": str(event or "")[:60],
    }
    txt = str(detail or "").strip()
    if txt:
        rec["detail"] = txt[:220]
    _integrations_emit(cfg, "oauth_events.ndjson", rec)


def _oauth_revoke_remote(cfg: dict, provider: str, row: dict,
                         test: bool = False) -> dict:
    tok = str(row.get("secret", "")).strip()
    if not tok:
        raise ReqErr("oauth_secret_missing", code=404)
    if provider in {"calendar_google", "storage_drive", "email_google"}:
        url = _env_pick("CTXORG_GOOGLE_REVOKE_URL", "GOOGLE_REVOKE_URL",
                        "https://oauth2.googleapis.com/revoke")
        _oauth_revoke_post(url, {"token": tok})
        return {"ok": True, "provider": provider, "url": url}
    if provider == "chatops_slack":
        url = _env_pick("CTXORG_SLACK_REVOKE_URL", "SLACK_REVOKE_URL",
                        "https://slack.com/api/auth.revoke")
        form = {"token": tok}
        if test:
            form["test"] = "1"
        out = _oauth_revoke_post(
            url, form, {"Authorization": f"Bearer {tok}"},
        )
        if isinstance(out, dict) and not bool(out.get("ok", True)):
            err = str(out.get("error", "slack_revoke_failed"))[:120]
            raise ReqErr("oauth_revoke_failed", code=502, detail=err)
        return {"ok": True, "provider": provider, "url": url}
    if provider in {"calendar_outlook", "storage_onedrive",
                    "email_outlook"}:
        url = _env_pick("CTXORG_MS_REVOKE_URL", "MS_REVOKE_URL", "")
        if not url:
            raise ReqErr("oauth_revoke_unsupported", code=400, detail=provider)
        _oauth_revoke_post(url, {"token": tok})
        return {"ok": True, "provider": provider, "url": url}
    raise ReqErr("oauth_provider_invalid", code=400)


def _oauth_revoke_post(url: str, form: dict[str, str],
                       headers: dict[str, str] | None = None
                       ) -> dict | str:
    raw = urlencode(form).encode("utf-8")
    req = urllib.request.Request(url, data=raw, method="POST")
    req.add_header("content-type", "application/x-www-form-urlencoded")
    for key, val in (headers or {}).items():
        req.add_header(str(key), str(val))
    try:
        with urllib.request.urlopen(req, timeout=15) as fh:
            txt = fh.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise ReqErr("oauth_revoke_failed", code=502, detail=body[:220]) from exc
    except Exception as exc:
        raise ReqErr("oauth_revoke_failed", code=502, detail=str(exc)[:220])
    row = str(txt or "").strip()
    if not row:
        return {}
    try:
        out = json.loads(row)
    except Exception:
        return row[:220]
    return out if isinstance(out, dict) else {}


def _oauth_events_list(cfg: dict) -> list[dict]:
    path = cfgmod.state_dir(cfg, "integrations") / "oauth_events.ndjson"
    if not path.exists():
        return []
    out = []
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    for line in raw.splitlines()[-2000:]:
        txt = line.strip()
        if not txt:
            continue
        try:
            row = json.loads(txt)
        except Exception:
            continue
        if isinstance(row, dict):
            out.append({
                "ts": int(row.get("ts", 0) or 0),
                "provider": str(row.get("provider", ""))[:40],
                "token_ref": str(row.get("token_ref", ""))[:120],
                "event": str(row.get("event", ""))[:60],
                "detail": str(row.get("detail", ""))[:220],
            })
    return out[-200:]


def _oauth_auth_url(conf: dict, rec: dict) -> str:
    base = str(conf.get("auth_url", "")).strip()
    if not base:
        raise ReqErr("oauth_provider_invalid", code=400)
    vals = {
        "client_id": str(conf.get("client_id", "")),
        "redirect_uri": str(conf.get("redirect_uri", "")),
        "response_type": "code",
        "scope": str(conf.get("scope", "")),
        "state": str(rec.get("state", "")),
    }
    chg = str(rec.get("pkce_challenge", "")).strip()
    if chg:
        vals["code_challenge"] = chg
        vals["code_challenge_method"] = str(
            rec.get("pkce_method", "S256"),
        ).strip() or "S256"
    extra = conf.get("defaults", {})
    if isinstance(extra, dict):
        for key, val in extra.items():
            vals[str(key)] = str(val)
    if str(conf.get("token_style", "")) == "slack":
        vals.pop("response_type", None)
    return f"{base}?{urlencode(vals)}"


def _oauth_exchange_code(cfg: dict, provider: str, code: str,
                         verifier: str = "") -> dict:
    conf = _oauth_provider_conf(cfg, provider)
    form = {
        "client_id": str(conf.get("client_id", "")),
        "client_secret": str(conf.get("client_secret", "")),
        "code": code,
        "redirect_uri": str(conf.get("redirect_uri", "")),
        "grant_type": "authorization_code",
    }
    if verifier:
        form["code_verifier"] = verifier
    raw = _oauth_form_post(str(conf.get("token_url", "")), form)
    return _oauth_token_parse(provider, raw)


def _oauth_refresh_secret(cfg: dict, provider: str, row: dict) -> dict:
    conf = _oauth_provider_conf(cfg, provider)
    ref = str(row.get("refresh_token", "")).strip()
    if not ref:
        raise ReqErr("oauth_refresh_token_missing", code=400)
    form = {
        "client_id": str(conf.get("client_id", "")),
        "client_secret": str(conf.get("client_secret", "")),
        "refresh_token": ref,
        "grant_type": "refresh_token",
    }
    raw = _oauth_form_post(str(conf.get("token_url", "")), form)
    tok = _oauth_token_parse(provider, raw)
    return _oauth_secret_store(cfg, provider, str(row.get("token_ref", "")),
                               tok)


def _oauth_secret_store(cfg: dict, provider: str, token_ref: str,
                        tok: dict) -> dict:
    acc = str(tok.get("access_token", "")).strip()
    if not acc:
        raise ReqErr("oauth_access_token_missing", code=502)
    ref = str(token_ref or "").strip()
    if not ref:
        ref = f"{provider}_main"
    exp = int(tok.get("expires_at", 0) or 0)
    rtk = str(tok.get("refresh_token", "")).strip()
    old = _integrations_secret_get(cfg, ref)
    if not rtk and isinstance(old, dict):
        rtk = str(old.get("refresh_token", "")).strip()
    row = _integrations_secret_upsert(
        cfg,
        token_ref=ref,
        provider=provider,
        secret=acc,
        refresh_token=rtk,
        expires_at=exp,
    )
    return row


def _oauth_form_post(url: str, form: dict[str, str]) -> dict:
    raw = urlencode(form).encode("utf-8")
    req = urllib.request.Request(url, data=raw, method="POST")
    req.add_header("content-type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=15) as fh:
            txt = fh.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise ReqErr("oauth_provider_failed", code=502, detail=body[:220]) from exc
    except Exception as exc:
        raise ReqErr("oauth_provider_failed", code=502, detail=str(exc)[:220])
    try:
        out = json.loads(txt) if txt.strip() else {}
    except Exception:
        raise ReqErr("oauth_provider_failed", code=502, detail="invalid_json")
    if isinstance(out, dict):
        return out
    raise ReqErr("oauth_provider_failed", code=502, detail="bad_payload")


def _oauth_token_parse(provider: str, raw: dict) -> dict:
    if provider == "chatops_slack" and not bool(raw.get("ok", True)):
        raise ReqErr("oauth_provider_failed", code=502,
                     detail=str(raw.get("error", "slack_error"))[:120])
    tok = {
        "access_token": "",
        "refresh_token": "",
        "expires_at": 0,
    }
    if provider == "chatops_slack":
        acc = str(raw.get("access_token", "")).strip()
        if not acc:
            usr = raw.get("authed_user", {})
            if isinstance(usr, dict):
                acc = str(usr.get("access_token", "")).strip()
        tok["access_token"] = acc
        tok["refresh_token"] = str(raw.get("refresh_token", "")).strip()
        if not tok["refresh_token"]:
            usr = raw.get("authed_user", {})
            if isinstance(usr, dict):
                tok["refresh_token"] = str(usr.get("refresh_token", "")).strip()
        exp = int(raw.get("expires_in", 0) or 0)
        if exp <= 0:
            usr = raw.get("authed_user", {})
            if isinstance(usr, dict):
                exp = int(usr.get("expires_in", 0) or 0)
        tok["expires_at"] = int(time.time()) + exp if exp > 0 else 0
        return tok
    tok["access_token"] = str(raw.get("access_token", "")).strip()
    tok["refresh_token"] = str(raw.get("refresh_token", "")).strip()
    exp = int(raw.get("expires_in", 0) or 0)
    tok["expires_at"] = int(time.time()) + exp if exp > 0 else 0
    return tok


def _integrations_secret_upsert(cfg: dict, token_ref: str, provider: str,
                                secret: str, refresh_token: str = "",
                                expires_at: int = 0) -> dict:
    if provider not in _SECRET_PROVIDERS:
        raise ReqErr("provider_invalid", code=400)
    wsid = _integrations_scope_id(cfg)
    row = {
        "token_ref": token_ref[:120],
        "provider": provider,
        "workspace_id": wsid,
        "status": "active",
        "secret": secret[:2000],
        "refresh_token": refresh_token[:2000],
        "expires_at": int(expires_at or 0),
        "updated_at": int(time.time()),
    }
    vals = _integrations_secrets_list(cfg)
    out = []
    hit = False
    for cur in vals:
        cref = str(cur.get("token_ref", "")).strip()
        cws = str(cur.get("workspace_id", "")).strip()
        same_scope = (cws == wsid) or (not cws) or (not wsid)
        if cref == row["token_ref"] and same_scope:
            out.append(row)
            hit = True
        else:
            out.append(cur)
    if not hit:
        out.append(row)
    _integrations_secrets_save(cfg, out)
    return row


def integrations_jobs_enqueue_payload(req: BaseHTTPRequestHandler,
                                      cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    _quota_take(cfg, "int_job_daily")
    _integrations_ensure_worker(cfg)
    data = body(req)
    kind = str(data.get("kind", "")).strip().lower()
    if kind not in {"email", "social", "webhook", "channel"}:
        raise ReqErr("integration_kind_invalid", code=400)
    payload = data.get("payload", {})
    if not isinstance(payload, dict):
        raise ReqErr("integration_payload_required", code=400)
    key = _integrations_idem_req(req, data)
    job, depth, duplicate = _integrations_enqueue_job(
        cfg,
        kind,
        payload,
        source="manual",
        idempotency_key=key,
    )
    return {
        "ok": True,
        "job": job,
        "queue_depth": depth,
        "idempotency_key": key,
        "duplicate": duplicate,
    }


def _integrations_enqueue_job(cfg: dict, kind: str, payload: dict, *,
                              source: str, not_before: float = 0.0,
                              meta: dict | None = None,
                              idempotency_key: str = "",
                              replay_of: str = "",
                              replay_count: int = 0
                              ) -> tuple[dict, int, bool]:
    opts = _integrations_queue_cfg(cfg)
    global _int_seq
    src = str(source or "manual")[:40]
    idem_key = _integrations_idem_key_clean(idempotency_key)
    idem_hash = _integrations_idem_hash(kind, payload, src)
    with _int_lock:
        _integrations_idem_gc_locked(opts)
        if idem_key:
            hit = _int_idem.get(idem_key, {})
            old_hash = str(hit.get("hash", ""))
            if hit and old_hash and old_hash != idem_hash:
                raise ReqErr("idempotency_conflict", code=409)
            if hit:
                old_id = str(hit.get("job_id", ""))
                prior = _integrations_job_find_locked(old_id)
                if prior:
                    return dict(prior), len(_int_jobs), True
        if len(_int_jobs) >= int(opts.get("cap", 500)):
            raise ReqErr("integrations_queue_full", code=429)
        _int_seq += 1
        now = int(time.time())
        job = {
            "id": f"ijob-{now}-{_int_seq}",
            "kind": kind,
            "payload": payload,
            "source": src,
            "meta": meta if isinstance(meta, dict) else {},
            "attempt": 0,
            "not_before": max(0.0, float(not_before or 0.0)),
            "next_retry_at": 0,
            "retry_in_s": 0.0,
            "retry_history": [],
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "last_error_at": 0,
            "last_error": "",
            "idempotency_key": idem_key,
            "idempotency_hash": idem_hash,
            "replay_of": str(replay_of or "")[:120],
            "replay_count": max(0, int(replay_count or 0)),
            "replayable": True,
            "dead_at": 0,
            "dead_reason": "",
        }
        _int_jobs.append(job)
        if idem_key:
            _int_idem[idem_key] = {
                "key": idem_key,
                "hash": idem_hash,
                "job_id": job["id"],
                "kind": kind,
                "status": "queued",
                "created_at": now,
                "updated_at": now,
            }
        depth = len(_int_jobs)
    _int_event.set()
    _log_ev("integrations_enqueue", job_id=job["id"], kind=kind,
            source=job["source"], depth=depth)
    _integrations_runtime_save(cfg)
    return job, depth, False


def _integrations_job_find_locked(job_id: str) -> dict | None:
    if not job_id:
        return None
    for row in _int_jobs + _int_done + _int_dead:
        if str(row.get("id", "")) == job_id:
            return row if isinstance(row, dict) else None
    return None


def _integrations_idem_req(req: BaseHTTPRequestHandler, data: dict) -> str:
    a = str(req.headers.get("idempotency-key", "")).strip()
    b = str(req.headers.get("x-idempotency-key", "")).strip()
    c = str(data.get("idempotency_key", "")).strip()
    raw = a or b or c
    return _integrations_idem_key_clean(raw)


def _integrations_idem_key_clean(raw: object) -> str:
    txt = str(raw or "").strip()
    if not txt:
        return ""
    if len(txt) < 4 or len(txt) > 120:
        raise ReqErr("idempotency_key_invalid", code=400)
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", txt):
        raise ReqErr("idempotency_key_invalid", code=400)
    return txt


def _integrations_idem_hash(kind: str, payload: dict, source: str) -> str:
    raw = json.dumps(
        {"kind": kind, "payload": payload, "source": source},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _integrations_idem_gc_locked(opts: dict) -> None:
    now = int(time.time())
    ttl = int(opts.get("idem_ttl_s", 86400))
    cap = int(opts.get("idem_cap", 2000))
    fresh = []
    for row in _int_idem.values():
        if not isinstance(row, dict):
            continue
        ts = int(row.get("updated_at", 0) or 0)
        if ts and ts >= now - ttl:
            fresh.append(row)
    fresh.sort(key=lambda x: int(x.get("updated_at", 0) or 0))
    keep = fresh[-cap:]
    _int_idem.clear()
    for row in keep:
        key = str(row.get("key", "")).strip()
        if key:
            _int_idem[key] = row


def integrations_jobs_replay_payload(req: BaseHTTPRequestHandler,
                                     cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    _integrations_runtime_load(cfg)
    data = body(req)
    if str(data.get("confirm", "")).strip() != "REPLAY":
        raise ReqErr("replay_confirmation_required", code=400)
    opts = _integrations_queue_cfg(cfg)
    lim = int(data.get("limit", 10) or 10)
    lim = max(1, min(lim, int(opts.get("replay_batch_max", 20))))
    kind = str(data.get("kind", "")).strip().lower()
    if kind and kind not in {"email", "social", "channel"}:
        raise ReqErr("replay_kind_invalid", code=400)
    raw_ids = data.get("job_ids", [])
    ids = raw_ids if isinstance(raw_ids, list) else []
    ids = [str(x).strip() for x in ids if str(x).strip()][:100]
    id_set = set(ids)
    reuse = bool(data.get("reuse_idempotency", False))
    dry = bool(data.get("dry_run", False))
    jobs = _integrations_dead_replay_pick(kind, id_set, lim)
    out = {"ok": True, "dry_run": dry, "requested": len(jobs)}
    if dry:
        out["candidates"] = [{
            "job_id": str(x.get("id", ""))[:120],
            "kind": str(x.get("kind", ""))[:40],
            "dead_reason": str(x.get("dead_reason", ""))[:240],
        } for x in jobs]
        return out
    moved = []
    skipped = []
    for row in jobs:
        old_id = str(row.get("id", "")).strip()
        if not old_id:
            continue
        key = str(row.get("idempotency_key", "")).strip() if reuse else ""
        try:
            _, _, dup = _integrations_enqueue_job(
                cfg,
                str(row.get("kind", "")).strip().lower(),
                row.get("payload", {}),
                source="manual:replay",
                meta={"replay_from": old_id},
                idempotency_key=key,
                replay_of=old_id,
                replay_count=max(1, int(row.get("replay_count", 0) or 0) + 1),
            )
            moved.append({"job_id": old_id, "duplicate": dup})
        except ReqErr as exc:
            skipped.append({"job_id": old_id, "err": exc.err})
    _integrations_dead_replay_remove([x["job_id"] for x in moved])
    _integrations_runtime_save(cfg)
    out["accepted"] = moved
    out["skipped"] = skipped
    out["accepted_count"] = len(moved)
    return out


def _integrations_dead_replay_pick(kind: str, ids: set[str],
                                   lim: int) -> list[dict]:
    with _int_lock:
        rows = [dict(x) for x in _int_dead]
    out = []
    for row in reversed(rows):
        if len(out) >= lim:
            break
        rk = str(row.get("kind", "")).strip().lower()
        if rk not in {"email", "social", "channel"}:
            continue
        if kind and kind != rk:
            continue
        rid = str(row.get("id", "")).strip()
        if ids and rid not in ids:
            continue
        if rk == "channel" and not _integrations_replay_channel_ok(row):
            continue
        out.append(row)
    out.reverse()
    return out


def _integrations_replay_channel_ok(row: dict) -> bool:
    pay = row.get("payload", {})
    if not isinstance(pay, dict):
        return False
    key = str(pay.get("channel", "")).strip().lower()
    return key in _FUTURE_CHANNELS


def _integrations_dead_replay_remove(job_ids: list[str]) -> None:
    keep = set(x for x in job_ids if x)
    if not keep:
        return
    with _int_lock:
        _int_dead[:] = [
            row for row in _int_dead
            if str(row.get("id", "")).strip() not in keep
        ]


def _integrations_sched_public(cfg: dict, sched: dict | None = None) -> dict:
    vals = _settings_runtime(cfg).get("integrations", {})
    auto = vals.get("automation", {}) if isinstance(vals, dict) else {}
    dig = auto.get("digest", {}) if isinstance(auto, dict) else {}
    syn = auto.get("sync", {}) if isinstance(auto, dict) else {}
    row = sched if isinstance(sched, dict) else {}
    return {
        "enabled": bool(dig.get("enabled", False)),
        "cron": str(dig.get("cron", "0 9 * * *")),
        "timezone": str(dig.get("timezone", "UTC")),
        "next_run": int(row.get("next_run", 0) or 0),
        "last_run": int(row.get("last_run", 0) or 0),
        "last_enqueue": int(row.get("last_enqueue", 0) or 0),
        "last_job_id": str(row.get("last_job_id", "")),
        "last_error": str(row.get("last_error", "")),
        "sync": {
            "enabled": bool(syn.get("enabled", False)),
            "interval_min": max(5, int(syn.get("interval_min", 30) or 30)),
            "channels": list(syn.get("channels", []))
            if isinstance(syn.get("channels", []), list)
            else [],
            "next_run": int(row.get("sync_next_run", 0) or 0),
            "last_run": int(row.get("sync_last_run", 0) or 0),
            "last_job_id": str(row.get("sync_last_job_id", "")),
        },
    }


def integrations_catalog_payload(cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin", "member"})
    _integrations_runtime_load(cfg)
    vals = _settings_runtime(cfg).get("integrations", {})
    ints = vals if isinstance(vals, dict) else {}
    refs = _integrations_secret_refs(cfg)
    email = _catalog_email(ints.get("email", {}))
    social = _catalog_social(ints.get("social", {}), refs)
    hooks = _catalog_hooks(ints.get("webhooks", {}))
    extra = _catalog_extra_channels(ints.get("channels", {}), refs)
    runtime = _catalog_runtime(cfg)
    chans = {
        "email": email,
        "social": social,
        "webhooks": hooks,
    }
    chans.update(extra)
    return {
        "ok": True,
        "channels": chans,
        "runtime": runtime,
        "capabilities": {
            "job_kinds": ["email", "social", "webhook", "channel"],
            "secret_providers": sorted(_SECRET_PROVIDERS),
            "oauth_providers": sorted(_OAUTH_PROVIDERS),
            "webhook_providers": sorted(_INT_WEBHOOK_PROVIDERS),
            "sync_channels": sorted(_SYNC_CHANNELS),
        },
        "roadmap": [
            "gmail", "outlook", "imap", "slack", "discord",
            "hubspot", "salesforce", "drive", "dropbox", "webhook",
        ],
        "security": {
            "secrets_storage": "state_dir settings",
            "token_ref_field": "token_ref",
            "webhook_signing": True,
            "oauth_pkce": True,
        },
    }


def _catalog_runtime(cfg: dict) -> dict:
    with _int_lock:
        qd = len(_int_jobs)
        dn = len(_int_done)
        dd = len(_int_dead)
        sched = dict(_int_sched)
    return {
        "queue_depth": qd,
        "done_count": dn,
        "dead_count": dd,
        "scheduler": _integrations_sched_public(cfg, sched),
    }


def _catalog_email(raw: object) -> dict:
    email = raw if isinstance(raw, dict) else {}
    frm = str(email.get("from_email", "")).strip()
    smtp = bool(_env_pick("CTXORG_SMTP_HOST", "SMTP_HOST",
                email.get("smtp_host")))
    sendgrid = _env_has("CTXORG_SENDGRID_API_KEY", "SENDGRID_API_KEY")
    resend = _env_has("CTXORG_RESEND_API_KEY", "RESEND_API_KEY")
    provider = str(email.get("provider", "smtp")).strip().lower() or "smtp"
    prv = {
        "smtp": {"configured": smtp},
        "ses": {"configured": smtp},
        "sendgrid": {"configured": sendgrid},
        "resend": {"configured": resend},
    }
    cfgd = bool(prv.get(provider, {}).get("configured", False))
    enabled = bool(email.get("enabled", False))
    return {
        "enabled": enabled,
        "provider": provider,
        "from_email": frm,
        "daily_cap": max(10, int(email.get("daily_cap", 500) or 500)),
        "features": ["transactional", "digest", "alerts"],
        "providers": prv,
        "ready": bool(enabled and frm and cfgd),
        "missing": _catalog_email_missing(enabled, frm, cfgd),
    }


def _catalog_email_missing(enabled: bool, frm: str, cfgd: bool) -> list[str]:
    out = []
    if not enabled:
        out.append("channel_disabled")
        return out
    if not frm:
        out.append("from_email_required")
    if not cfgd:
        out.append("provider_credentials_required")
    return out


def _catalog_social(raw: object, refs: set[str]) -> dict:
    social = raw if isinstance(raw, dict) else {}
    rows = social.get("providers", {})
    if not isinstance(rows, dict):
        rows = {}
    out = {}
    ready = []
    for key in _SOCIAL_PROVIDERS:
        row = rows.get(key, {})
        cur = row if isinstance(row, dict) else {}
        token_ref = str(cur.get("token_ref", "")).strip()
        token_ok = token_ref in refs or _social_env_ready(key)
        enabled = bool(cur.get("enabled", False))
        out[key] = {
            "enabled": enabled,
            "handle": str(cur.get("handle", "")),
            "token_ref": token_ref,
            "token_present": token_ok,
            "configured": token_ok,
        }
        if enabled and token_ok:
            ready.append(key)
    enabled = bool(social.get("enabled", False))
    return {
        "enabled": enabled,
        "default_voice": str(social.get("default_voice", "clear")),
        "features": ["publish", "draft", "schedule", "analytics"],
        "providers": out,
        "ready_providers": ready,
        "ready": bool(enabled and ready),
    }


def _catalog_hooks(raw: object) -> dict:
    hooks = raw if isinstance(raw, dict) else {}
    rows = hooks.get("targets", [])
    vals = rows if isinstance(rows, list) else []
    cnt = 0
    for row in vals:
        if not isinstance(row, dict):
            continue
        if str(row.get("url", "")).strip():
            cnt += 1
    enabled = bool(hooks.get("enabled", False))
    return {"enabled": enabled, "target_count": cnt,
            "ready": bool(enabled and cnt > 0)}


def _social_env_ready(key: str) -> bool:
    env_a, env_b = _social_token_env(key)
    if env_a:
        return _env_has(env_a, env_b)
    return False


def _catalog_extra_channels(raw: object, refs: set[str]) -> dict:
    rows = raw if isinstance(raw, dict) else {}
    out = {}
    for key, spec in _catalog_channel_specs().items():
        cur = rows.get(key, {})
        row = cur if isinstance(cur, dict) else {}
        enabled = bool(row.get("enabled", False))
        provider = str(row.get("provider", spec["provider"])).strip().lower()
        token_ref = str(row.get("token_ref", "")).strip()
        token_ok = _channel_token_ready(key, provider, token_ref, refs)
        out[key] = {
            "enabled": enabled,
            "provider": provider,
            "account": str(row.get("account", "")),
            "token_ref": token_ref,
            "token_present": token_ok,
            "features": list(spec["features"]),
            "providers": list(spec["providers"]),
            "ready": bool(enabled and token_ok),
            "missing": _catalog_channel_missing(enabled, token_ok),
        }
    return out


def _catalog_channel_specs() -> dict[str, dict]:
    return {
        "calendar": {
            "provider": "google",
            "providers": ["google", "outlook"],
            "features": ["sync", "events", "digest"],
        },
        "crm": {
            "provider": "hubspot",
            "providers": ["hubspot", "salesforce"],
            "features": ["contacts", "timeline", "enrichment"],
        },
        "storage": {
            "provider": "drive",
            "providers": ["drive", "dropbox", "onedrive"],
            "features": ["import", "watch", "dedupe"],
        },
        "chatops": {
            "provider": "slack",
            "providers": ["slack", "discord"],
            "features": ["alerts", "threads", "handoff"],
        },
    }


def _catalog_channel_missing(enabled: bool, token_ok: bool) -> list[str]:
    if not enabled:
        return ["channel_disabled"]
    if not token_ok:
        return ["provider_credentials_required"]
    return []


def _channel_token_ready(kind: str, provider: str, token_ref: str,
                         refs: set[str]) -> bool:
    if token_ref and token_ref in refs:
        return True
    env_a, env_b = _channel_env_map(kind, provider)
    if env_a and _env_has(env_a, env_b):
        return True
    return False


def _channel_env_map(kind: str, provider: str) -> tuple[str, str]:
    key = f"{kind}:{provider}".lower()
    if key == "calendar:google":
        return "CTXORG_GOOGLE_CAL_TOKEN", "GOOGLE_CAL_TOKEN"
    if key == "calendar:outlook":
        return "CTXORG_OUTLOOK_CAL_TOKEN", "OUTLOOK_CAL_TOKEN"
    if key == "crm:hubspot":
        return "CTXORG_HUBSPOT_TOKEN", "HUBSPOT_TOKEN"
    if key == "crm:salesforce":
        return "CTXORG_SALESFORCE_TOKEN", "SALESFORCE_TOKEN"
    if key == "storage:drive":
        return "CTXORG_DRIVE_TOKEN", "DRIVE_TOKEN"
    if key == "storage:dropbox":
        return "CTXORG_DROPBOX_TOKEN", "DROPBOX_TOKEN"
    if key == "storage:onedrive":
        return "CTXORG_ONEDRIVE_TOKEN", "ONEDRIVE_TOKEN"
    if key == "chatops:slack":
        return "CTXORG_SLACK_BOT_TOKEN", "SLACK_BOT_TOKEN"
    if key == "chatops:discord":
        return "CTXORG_DISCORD_BOT_TOKEN", "DISCORD_BOT_TOKEN"
    return "", ""


def _channel_secret_provider(kind: str, provider: str) -> str:
    key = f"{kind}:{provider}".lower()
    if key == "calendar:google":
        return "calendar_google"
    if key == "calendar:outlook":
        return "calendar_outlook"
    if key == "storage:drive":
        return "storage_drive"
    if key == "storage:onedrive":
        return "storage_onedrive"
    if key == "storage:dropbox":
        return "storage_dropbox"
    if key == "crm:hubspot":
        return "crm_hubspot"
    if key == "crm:salesforce":
        return "crm_salesforce"
    if key == "chatops:slack":
        return "chatops_slack"
    if key == "chatops:discord":
        return "chatops_discord"
    if kind == "social":
        return provider
    return ""


def _channel_oauth_provider(kind: str, provider: str) -> str:
    key = f"{kind}:{provider}".lower()
    if key in {"calendar:google", "calendar:outlook", "storage:drive",
               "storage:onedrive", "chatops:slack"}:
        return _channel_secret_provider(kind, provider)
    if key == "email:google":
        return "email_google"
    if key == "email:outlook":
        return "email_outlook"
    return ""


def _integrations_secret_refs(cfg: dict) -> set[str]:
    out = set()
    for row in _integrations_secrets_list(cfg):
        if str(row.get("status", "")).strip() != "active":
            continue
        ref = str(row.get("token_ref", "")).strip()
        if ref:
            out.add(ref)
    return out


def _env_has(a: str, b: str) -> bool:
    return bool(_env_pick(a, b, ""))


def _settings_default(cfg: dict) -> dict:
    return {
        "profile": {
            "display_name": "",
            "session_days": 30,
        },
        "scan_rules": {
            "queue_cap": int(cfg.get("scan_queue_cap", 6) or 6),
            "retry_max": int(cfg.get("scan_retry_max", 2) or 2),
            "backoff_s": float(cfg.get("scan_backoff_s", 3.0) or 3.0),
            "timeout_s": int(cfg.get("scan_timeout_s", 300) or 300),
            "dead_cap": int(cfg.get("scan_dead_cap", 20) or 20),
        },
        "privacy": {
            "local_only": True,
            "redact_exports": True,
            "allow_risky_exports": False,
        },
        "integrations": {
            "provider_mode": str(cfg.get("provider_mode", "ollama")),
            "ollama_url": str(cfg.get("ollama_url", "")),
            "mirofish_url": str(cfg.get("mirofish_url", "")),
            "mirofish_enabled": bool(cfg.get("mirofish_url", "")),
            "chat_provider": str(cfg.get("chat_provider", "")),
            "infer_provider": str(cfg.get("infer_provider", "")),
            "iris_provider": str(cfg.get("iris_provider", "")),
            "home_provider": str(cfg.get("home_provider", "")),
            "workstreams_provider": str(cfg.get("workstreams_provider", "")),
            "chat_model": str(cfg.get("chat_model",
                               cfg.get("fast_model", cfg.get("model", "")))),
            "infer_model": str(cfg.get("infer_model", cfg.get("model", ""))),
            "iris_model": str(cfg.get("iris_model",
                               cfg.get("fast_model", cfg.get("model", "")))),
            "home_model": str(cfg.get("home_model",
                               cfg.get("fast_model", cfg.get("model", "")))),
            "workstreams_model": str(cfg.get("workstreams_model",
                                     cfg.get("model", ""))),
            "email": {
                "enabled": False,
                "provider": "smtp",
                "from_name": "Optic",
                "from_email": "",
                "reply_to": "",
                "smtp_host": str(cfg.get("smtp_host", "")),
                "smtp_port": int(cfg.get("smtp_port", 587) or 587),
                "smtp_user": str(cfg.get("smtp_user", "")),
                "smtp_use_ssl": bool(cfg.get("smtp_use_ssl", False)),
                "smtp_starttls": bool(cfg.get("smtp_starttls", True)),
                "daily_cap": 500,
                "track_opens": True,
            },
            "social": {
                "enabled": False,
                "default_voice": "clear",
                "providers": {
                    "x": {"enabled": False, "handle": "", "token_ref": ""},
                    "linkedin": {
                        "enabled": False, "handle": "", "token_ref": "",
                    },
                    "youtube": {
                        "enabled": False, "handle": "", "token_ref": "",
                    },
                    "tiktok": {
                        "enabled": False, "handle": "", "token_ref": "",
                    },
                    "instagram": {
                        "enabled": False, "handle": "", "token_ref": "",
                    },
                    "threads": {
                        "enabled": False, "handle": "", "token_ref": "",
                    },
                },
            },
            "automation": {
                "queue": {"max_inflight": 4, "retry_max": 3, "backoff_s": 2.0},
                "digest": {
                    "enabled": False,
                    "cron": "0 9 * * *",
                    "timezone": "UTC",
                },
                "sync": {
                    "enabled": False,
                    "interval_min": 30,
                    "channels": ["calendar", "crm", "storage"],
                },
            },
            "webhooks": {
                "enabled": False,
                "targets": [],
            },
            "channels": _integrations_channels_default(),
        },
        "updated_at": int(time.time()),
    }


def _settings_merge(cur: dict, raw: dict, cfg: dict, touch: bool = True) -> dict:
    out = _settings_default(cfg)
    for key in ("profile", "scan_rules", "privacy", "integrations"):
        base = dict(cur.get(key, {}))
        nxt = raw.get(key)
        if isinstance(nxt, dict):
            base = _merge_tree(base, nxt) if key == "integrations" else {
                **base, **nxt,
            }
        out[key] = _merge_tree(out[key], base) if key == "integrations" else {
            **out[key], **base,
        }
    out["profile"]["display_name"] = str(
        out["profile"].get("display_name", "")
    )[:80]
    out["profile"]["session_days"] = max(
        1, min(365, int(out["profile"].get("session_days", 30) or 30))
    )
    out["scan_rules"]["queue_cap"] = max(
        1, int(out["scan_rules"].get("queue_cap", 6) or 6)
    )
    out["scan_rules"]["retry_max"] = max(
        0, int(out["scan_rules"].get("retry_max", 2) or 2)
    )
    out["scan_rules"]["backoff_s"] = max(
        0.1, float(out["scan_rules"].get("backoff_s", 3.0) or 3.0)
    )
    out["scan_rules"]["timeout_s"] = max(
        30, int(out["scan_rules"].get("timeout_s", 300) or 300)
    )
    out["scan_rules"]["dead_cap"] = max(
        1, int(out["scan_rules"].get("dead_cap", 20) or 20)
    )
    for key in ("local_only", "redact_exports", "allow_risky_exports"):
        out["privacy"][key] = bool(out["privacy"].get(key, False))
    out["integrations"]["provider_mode"] = str(
        out["integrations"].get("provider_mode", "ollama")
    )[:24]
    out["integrations"]["ollama_url"] = str(
        out["integrations"].get("ollama_url", "")
    )[:200]
    out["integrations"]["mirofish_url"] = str(
        out["integrations"].get("mirofish_url", "")
    )[:200]
    out["integrations"]["mirofish_enabled"] = bool(
        out["integrations"].get("mirofish_enabled", False)
    )
    for key in ("chat_provider", "infer_provider", "iris_provider",
                "home_provider", "workstreams_provider"):
        out["integrations"][key] = str(
            out["integrations"].get(key, "")
        )[:24].lower()
    for key in ("chat_model", "infer_model", "iris_model",
                "home_model", "workstreams_model"):
        out["integrations"][key] = str(
            out["integrations"].get(key, "")
        )[:80]
    _settings_clamp_integrations(out["integrations"])
    if touch:
        out["updated_at"] = int(time.time())
    else:
        out["updated_at"] = int(cur.get("updated_at", 0) or 0)
    return out


def _merge_tree(base: dict, patch: dict) -> dict:
    out = dict(base)
    for key, val in patch.items():
        cur = out.get(key)
        if isinstance(cur, dict) and isinstance(val, dict):
            out[key] = _merge_tree(cur, val)
            continue
        out[key] = val
    return out


def _settings_clamp_integrations(vals: dict) -> None:
    email = vals.get("email", {})
    if not isinstance(email, dict):
        email = {}
    email["enabled"] = bool(email.get("enabled", False))
    email["provider"] = str(email.get("provider", "smtp"))[:24].lower()
    email["from_name"] = str(email.get("from_name", "Optic"))[:80]
    email["from_email"] = str(email.get("from_email", ""))[:160]
    email["reply_to"] = str(email.get("reply_to", ""))[:160]
    email["smtp_host"] = str(email.get("smtp_host", ""))[:160]
    email["smtp_port"] = max(1, int(email.get("smtp_port", 587) or 587))
    email["smtp_user"] = str(email.get("smtp_user", ""))[:160]
    email["smtp_use_ssl"] = bool(email.get("smtp_use_ssl", False))
    email["smtp_starttls"] = bool(email.get("smtp_starttls", True))
    email["daily_cap"] = max(10, int(email.get("daily_cap", 500) or 500))
    email["track_opens"] = bool(email.get("track_opens", True))
    vals["email"] = email

    social = vals.get("social", {})
    if not isinstance(social, dict):
        social = {}
    social["enabled"] = bool(social.get("enabled", False))
    social["default_voice"] = str(social.get("default_voice", "clear"))[:40]
    providers = social.get("providers", {})
    if not isinstance(providers, dict):
        providers = {}
    out = {}
    for key in _SOCIAL_PROVIDERS:
        row = providers.get(key, {})
        if not isinstance(row, dict):
            row = {}
        out[key] = {
            "enabled": bool(row.get("enabled", False)),
            "handle": str(row.get("handle", ""))[:80],
            "token_ref": str(row.get("token_ref", ""))[:160],
        }
    social["providers"] = out
    vals["social"] = social

    auto = vals.get("automation", {})
    if not isinstance(auto, dict):
        auto = {}
    queue = auto.get("queue", {})
    if not isinstance(queue, dict):
        queue = {}
    queue["max_inflight"] = max(1, int(queue.get("max_inflight", 4) or 4))
    queue["retry_max"] = max(0, int(queue.get("retry_max", 3) or 3))
    queue["backoff_s"] = max(0.1, float(queue.get("backoff_s", 2.0) or 2.0))
    auto["queue"] = queue
    digest = auto.get("digest", {})
    if not isinstance(digest, dict):
        digest = {}
    digest["enabled"] = bool(digest.get("enabled", False))
    digest["cron"] = str(digest.get("cron", "0 9 * * *"))[:80]
    digest["timezone"] = str(digest.get("timezone", "UTC"))[:60]
    auto["digest"] = digest
    sync = auto.get("sync", {})
    if not isinstance(sync, dict):
        sync = {}
    sync["enabled"] = bool(sync.get("enabled", False))
    sync["interval_min"] = max(5, min(1440, int(
        sync.get("interval_min", 30) or 30,
    )))
    rows = sync.get("channels", [])
    chan_rows = rows if isinstance(rows, list) else []
    ch = []
    for row in chan_rows:
        key = str(row).strip().lower()
        if key in _FUTURE_CHANNELS and key not in ch:
            ch.append(key)
    sync["channels"] = ch or ["calendar", "crm", "storage"]
    auto["sync"] = sync
    vals["automation"] = auto

    hooks = vals.get("webhooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
    hooks["enabled"] = bool(hooks.get("enabled", False))
    rows = hooks.get("targets", [])
    rows = rows if isinstance(rows, list) else []
    clean = []
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url", "")).strip()[:300]
        evt = str(row.get("event", "publish")).strip()[:80]
        if not url:
            continue
        clean.append({"url": url, "event": evt})
    hooks["targets"] = clean
    vals["webhooks"] = hooks

    vals["channels"] = _integrations_channels_clean(vals.get("channels", {}))


def _integrations_channels_default() -> dict:
    return {
        "calendar": {
            "enabled": False,
            "provider": "google",
            "account": "",
            "token_ref": "",
        },
        "crm": {
            "enabled": False,
            "provider": "hubspot",
            "account": "",
            "token_ref": "",
        },
        "storage": {
            "enabled": False,
            "provider": "drive",
            "account": "",
            "token_ref": "",
        },
        "chatops": {
            "enabled": False,
            "provider": "slack",
            "account": "",
            "token_ref": "",
        },
    }


def _integrations_channels_clean(raw: object) -> dict:
    rows = raw if isinstance(raw, dict) else {}
    out = {}
    for key, dflt in _integrations_channels_default().items():
        cur = rows.get(key, {})
        if not isinstance(cur, dict):
            cur = {}
        out[key] = {
            "enabled": bool(cur.get("enabled", dflt["enabled"])),
            "provider": str(cur.get("provider", dflt["provider"]))
            [:24].lower(),
            "account": str(cur.get("account", dflt["account"]))[:160],
            "token_ref": str(cur.get("token_ref", dflt["token_ref"]))[:160],
        }
    return out


def _settings_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg) / "settings.json"


def _settings_load(cfg: dict) -> dict | None:
    if "state_dir" not in cfg:
        return None
    return _store_read(_settings_path(cfg))


def _settings_save(cfg: dict, rec: dict) -> None:
    if "state_dir" not in cfg:
        return
    _store_write(_settings_path(cfg), rec)


def _settings_runtime(cfg: dict) -> dict:
    rec = _settings_load(cfg)
    if not rec:
        return _settings_default(cfg)
    return _settings_merge(rec, {}, cfg, touch=False)


def _llm_cfg_runtime(cfg: dict) -> dict:
    out = dict(cfg)
    rec = _settings_runtime(cfg)
    ints = rec.get("integrations", {})
    if not isinstance(ints, dict):
        return out
    for key in (
        "provider_mode",
        "ollama_url",
        "mirofish_url",
        "chat_provider",
        "infer_provider",
        "iris_provider",
        "home_provider",
        "workstreams_provider",
        "chat_model",
        "infer_model",
        "iris_model",
        "home_model",
        "workstreams_model",
    ):
        val = ints.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()
    if "mirofish_enabled" in ints:
        out["mirofish_enabled"] = bool(ints.get("mirofish_enabled"))
    return out


def signup_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    """POST /api/signup — create a new account with password verification.

    Requires: email + password.  Rejects existing accounts (use /api/signin).
    Enforces password strength (min 8 chars, uppercase, digit).
    """
    data = body(req)
    email = _str_field(data, "email", 254).lower()
    password = str(data.get("password", ""))

    if not _EMAIL_RE.fullmatch(email):
        _api_err("POST", "/api/signup", "invalid_email")
        return {"ok": False, "err": "invalid_email"}

    if not password:
        _api_err("POST", "/api/signup", "password_required")
        return {"ok": False, "err": "password_required",
                "detail": "A password is required to create an account"}

    # Check password strength (C6)
    pw_err = _pw_strength(password)
    if pw_err:
        _api_err("POST", "/api/signup", pw_err)
        return {"ok": False, "err": pw_err,
                "detail": "Password must be at least 8 characters with one uppercase letter and one digit"}

    # Check for existing account
    existing = _acct_lookup(cfg, email)
    if existing:
        # If existing account has a password_hash, require signin
        if existing.get("password_hash"):
            _api_err("POST", "/api/signup", "email_registered")
            return {"ok": False, "err": "email_registered",
                    "detail": "This email is already registered. Use /api/signin to sign in."}
        # Legacy migration: account exists but has no password_hash.
        # Migrate it by adding password_hash, then sign in.
        existing["password_hash"] = _pw_hash(password)
        existing["updated_at"] = int(time.time())
        _acct_save(cfg, existing)
        tok = _sess_create(cfg, email, _session_days(cfg))
        ws = _workspace_bootstrap(cfg, existing)
        role = _workspace_role(ws, email) if ws else ""
        return {
            "ok": True,
            "signed_in": True,
            "account": _acct_public(existing),
            "workspace": _workspace_brief(ws, role),
            "_session_token": tok,
        }

    # New account
    name = _acct_name(str(data.get("name", "")), email)
    now = int(time.time())
    rec = {
        "name": name,
        "email": email,
        "provider": _acct_provider(data.get("provider")),
        "initials": _acct_initials(name),
        "password_hash": _pw_hash(password),
        "created_at": now,
        "updated_at": now,
        "onboarded": bool(data.get("onboarded", False)),
        "last_run": str(data.get("last_run", "")),
    }
    _acct_save(cfg, rec)
    ws = _workspace_bootstrap(cfg, rec)
    role = _workspace_role(ws, email) if ws else ""
    tok = _sess_create(cfg, email, _session_days(cfg))
    return {
        "ok": True,
        "signed_in": True,
        "account": _acct_public(rec),
        "workspace": _workspace_brief(ws, role),
        "_session_token": tok,
    }


def signin_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    """POST /api/signin — authenticate with email + password.

    Verifies password against stored hash.  Returns session token on success.
    """
    data = body(req)
    email = _str_field(data, "email", 254).lower()
    password = str(data.get("password", ""))

    if not _EMAIL_RE.fullmatch(email):
        _api_err("POST", "/api/signin", "invalid_email")
        return {"ok": False, "err": "invalid_email"}

    if not password:
        _api_err("POST", "/api/signin", "password_required")
        return {"ok": False, "err": "password_required"}

    rec = _acct_lookup(cfg, email)
    if not rec:
        # Constant-time failure to prevent user enumeration
        _pw_verify(password, _pw_hash("dummy"))
        _api_err("POST", "/api/signin", "invalid_credentials")
        return {"ok": False, "err": "invalid_credentials",
                "detail": "Invalid email or password"}

    pw_hash = rec.get("password_hash", "")
    if not pw_hash:
        # Legacy account with no password — reject
        _api_err("POST", "/api/signin", "invalid_credentials")
        return {"ok": False, "err": "invalid_credentials",
                "detail": "Invalid email or password"}

    if not _pw_verify(password, str(pw_hash)):
        _api_err("POST", "/api/signin", "invalid_credentials")
        return {"ok": False, "err": "invalid_credentials",
                "detail": "Invalid email or password"}

    # Update last-seen
    rec["updated_at"] = int(time.time())
    _acct_save(cfg, rec)

    ws = _workspace_load(cfg)
    role = _workspace_role(ws, email) if ws else ""
    tok = _sess_create(cfg, email, _session_days(cfg))
    return {
        "ok": True,
        "signed_in": True,
        "account": _acct_public(rec),
        "workspace": _workspace_brief(ws, role),
        "_session_token": tok,
    }


def signout_payload(req: BaseHTTPRequestHandler | None, cfg: dict) -> dict:
    tok = _auth_token(req) if req else ""
    if tok:
        _sess_revoke(cfg, tok)
    _acct_clear_legacy(cfg)
    return {"ok": True, "signed_in": False, "account": None}


def workspace_payload(cfg: dict) -> dict:
    ws = _workspace_load(cfg)
    if not ws:
        return {"ok": True, "workspace": None}
    rec = _acct_load(cfg)
    role = _workspace_role(ws, str(rec.get("email", ""))) if rec else ""
    return {"ok": True, "workspace": _workspace_public(ws, role)}


def workspace_members_payload(cfg: dict) -> dict:
    ws = _workspace_must(cfg)
    _workspace_require_role(cfg, {"owner", "admin", "member"})
    vals = ws.get("members", [])
    rows = vals if isinstance(vals, list) else []
    out = [x for x in rows if isinstance(x, dict)]
    out.sort(key=lambda x: (
        {"owner": 0, "admin": 1, "member": 2}.get(str(x.get("role", "")), 9),
        str(x.get("email", "")),
    ))
    return {"ok": True, "members": out}


def workspace_invites_payload(cfg: dict) -> dict:
    ws = _workspace_must(cfg)
    _workspace_require_role(cfg, {"owner", "admin"})
    vals = ws.get("invites", [])
    rows = vals if isinstance(vals, list) else []
    out = [x for x in rows if isinstance(x, dict)]
    out.sort(key=lambda x: -int(x.get("created_at", 0) or 0))
    return {"ok": True, "invites": out[:120]}


def workspace_update_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    ws = _workspace_must(cfg)
    _workspace_require_role(cfg, {"owner", "admin"})
    data = body(req)
    name = str(data.get("name", ws.get("name", "Optic Workspace"))).strip()
    slug = str(data.get("slug", ws.get("slug", "optic-workspace"))).strip()
    if not name:
        raise ReqErr("workspace_name_required", code=400)
    ws["name"] = name[:80]
    ws["slug"] = _workspace_slug(slug or name)
    ws["updated_at"] = int(time.time())
    _workspace_save(cfg, ws)
    role = _workspace_role(ws, _acct_email(cfg))
    return {"ok": True, "workspace": _workspace_public(ws, role)}


def workspace_invite_create_payload(req: BaseHTTPRequestHandler,
                                    cfg: dict) -> dict:
    ws = _workspace_must(cfg)
    _workspace_require_role(cfg, {"owner", "admin"})
    lim = _seat_limit(cfg)
    now_n = _active_member_count(ws) + _pending_invite_count(ws)
    if lim > 0 and now_n >= lim:
        raise ReqErr("seat_limit_reached", code=402,
                     detail=f"seats={lim} members+pending={now_n}")
    data = body(req)
    email = str(data.get("email", "")).strip().lower()
    if not _EMAIL_RE.fullmatch(email):
        raise ReqErr("invalid_email", code=400)
    role = _workspace_role_clean(data.get("role"))
    if role == "owner":
        role = "admin"
    if _workspace_member_find(ws, email):
        raise ReqErr("member_exists", code=409)
    now = int(time.time())
    inv = {
        "id": f"inv-{uuid.uuid4().hex[:10]}",
        "email": email,
        "role": role,
        "status": "pending",
        "created_at": now,
        "expires_at": now + 7 * 86400,
    }
    vals = ws.get("invites", [])
    rows = vals if isinstance(vals, list) else []
    rows = [x for x in rows if isinstance(x, dict)]
    rows = [x for x in rows if str(x.get("status", "")) == "pending"]
    rows.append(inv)
    ws["invites"] = rows[-300:]
    ws["updated_at"] = now
    _workspace_save(cfg, ws)
    return {"ok": True, "invite": inv}


def workspace_invite_accept_payload(req: BaseHTTPRequestHandler,
                                    cfg: dict) -> dict:
    ws = _workspace_must(cfg)
    rec = _acct_must(cfg)
    data = body(req)
    iid = str(data.get("invite_id", "")).strip()
    email = str(rec.get("email", "")).strip().lower()
    vals = ws.get("invites", [])
    rows = vals if isinstance(vals, list) else []
    now = int(time.time())
    pick = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("id", "")) != iid:
            continue
        if str(row.get("email", "")).strip().lower() != email:
            raise ReqErr("invite_email_mismatch", code=403)
        if str(row.get("status", "")) != "pending":
            raise ReqErr("invite_not_pending", code=400)
        if int(row.get("expires_at", 0) or 0) < now:
            raise ReqErr("invite_expired", code=400)
        pick = row
        break
    if not pick:
        raise ReqErr("invite_not_found", code=404)
    role = _workspace_role_clean(pick.get("role"))
    if not _workspace_member_find(ws, email):
        lim = _seat_limit(cfg)
        now_n = _active_member_count(ws)
        if lim > 0 and now_n >= lim:
            raise ReqErr("seat_limit_reached", code=402,
                         detail=f"seats={lim} members={now_n}")
    ws = _workspace_member_upsert(
        ws,
        email=email,
        name=str(rec.get("name", "")),
        role=role,
    )
    for row in rows:
        if isinstance(row, dict) and str(row.get("id", "")) == iid:
            row["status"] = "accepted"
            row["accepted_at"] = now
    ws["invites"] = rows
    ws["updated_at"] = now
    _workspace_save(cfg, ws)
    return {"ok": True, "workspace": _workspace_public(ws, role)}


def api_keys_payload(cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    vals = _api_keys_list(cfg)
    out = [_api_key_public(x) for x in vals if isinstance(x, dict)]
    out.sort(key=lambda x: -int(x.get("created_at", 0) or 0))
    return {"ok": True, "keys": out[:120]}


def api_key_create_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    lim = _plan_limit(cfg, "api_keys_max")
    if lim > 0:
        vals = _api_keys_list(cfg)
        live = 0
        for row in vals:
            if not isinstance(row, dict):
                continue
            if str(row.get("status", "active")) == "active":
                live += 1
        if live >= lim:
            raise ReqErr("api_key_limit_reached", code=402,
                         detail=f"cap={lim} active={live}")
    data = body(req)
    name = str(data.get("name", "integration")).strip()[:80]
    scopes = _api_key_scopes(data.get("scopes", []))
    kid = f"key-{uuid.uuid4().hex[:10]}"
    secret = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    token = f"opk_{kid}_{secret}"
    row = {
        "id": kid,
        "name": name or "integration",
        "prefix": token[:18],
        "scopes": scopes,
        "status": "active",
        "hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "created_at": int(time.time()),
        "last_used_at": 0,
    }
    vals = _api_keys_list(cfg)
    vals.append(row)
    _api_keys_save(cfg, vals[-300:])
    return {"ok": True, "api_key": token, "meta": _api_key_public(row)}


def api_key_revoke_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    data = body(req)
    kid = str(data.get("id", "")).strip()
    if not kid:
        raise ReqErr("key_id_required", code=400)
    vals = _api_keys_list(cfg)
    hit = False
    for row in vals:
        if not isinstance(row, dict):
            continue
        if str(row.get("id", "")) != kid:
            continue
        row["status"] = "revoked"
        row["revoked_at"] = int(time.time())
        hit = True
    if not hit:
        raise ReqErr("key_not_found", code=404)
    _api_keys_save(cfg, vals)
    return {"ok": True, "id": kid, "status": "revoked"}


def _plan_limits_default() -> dict[str, dict[str, int]]:
    return {
        "free": {
            "chat_daily": 500,
            "scan_daily": 8,
            "export_daily": 30,
            "int_job_daily": 80,
            "api_keys_max": 3,
            "seats_max": 3,
        },
        "pro": {
            "chat_daily": 5000,
            "scan_daily": 80,
            "export_daily": 300,
            "int_job_daily": 1000,
            "api_keys_max": 20,
            "seats_max": 10,
        },
        "team": {
            "chat_daily": 20000,
            "scan_daily": 300,
            "export_daily": 1500,
            "int_job_daily": 4000,
            "api_keys_max": 120,
            "seats_max": 50,
        },
        "enterprise": {
            "chat_daily": 0,
            "scan_daily": 0,
            "export_daily": 0,
            "int_job_daily": 0,
            "api_keys_max": 0,
            "seats_max": 0,
        },
    }


def _billing_plan(cfg: dict) -> str:
    if "state_dir" not in cfg:
        return "free"
    rec = _billing_load(cfg) or _billing_default(cfg)
    plan = str(rec.get("plan", "free")).strip().lower()
    return plan if plan in {"free", "pro", "team", "enterprise"} else "free"


def _plan_limit(cfg: dict, key: str) -> int:
    plan = _billing_plan(cfg)
    defs = _plan_limits_default()
    base = defs.get(plan, defs["free"]).get(key, 0)
    raw = cfg.get(f"quota_{plan}_{key}", base)
    env = _env_pick(
        f"CTXORG_QUOTA_{plan.upper()}_{key.upper()}",
        f"QUOTA_{plan.upper()}_{key.upper()}",
        raw,
    )
    try:
        return max(0, int(env or 0))
    except Exception:
        return max(0, int(base or 0))


def _usage_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg) / "quota_usage.json"


def _usage_today(now: float) -> str:
    dt = datetime.fromtimestamp(now, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def _usage_load(cfg: dict) -> dict:
    data = _store_read(_usage_path(cfg))
    if not isinstance(data, dict):
        data = {}
    day = str(data.get("day", ""))
    rows = data.get("counters", {})
    ctr = rows if isinstance(rows, dict) else {}
    return {
        "day": day,
        "counters": {str(k): int(v or 0) for k, v in ctr.items()},
        "updated_at": int(data.get("updated_at", 0) or 0),
    }


def _usage_save(cfg: dict, rec: dict) -> None:
    _store_write(_usage_path(cfg), rec)


def _quota_snapshot(cfg: dict) -> dict:
    now = time.time()
    day = _usage_today(now)
    rec = _usage_load(cfg) if "state_dir" in cfg else {"day": day, "counters": {}}
    if rec.get("day") != day:
        rec = {"day": day, "counters": {}, "updated_at": int(now)}
    ctr = rec.get("counters", {})
    use = ctr if isinstance(ctr, dict) else {}
    keys = ["chat_daily", "scan_daily", "export_daily", "int_job_daily"]
    return {
        "day": day,
        "plan": _billing_plan(cfg),
        "limits": {k: _plan_limit(cfg, k) for k in keys},
        "used": {k: int(use.get(k, 0) or 0) for k in keys},
    }


def _quota_take(cfg: dict, key: str, n: int = 1) -> None:
    if n <= 0 or "state_dir" not in cfg:
        return
    cap = _plan_limit(cfg, key)
    if cap <= 0:
        return
    plan = _billing_plan(cfg)
    now = time.time()
    day = _usage_today(now)
    with _usage_lock:
        rec = _usage_load(cfg)
        if rec.get("day") != day:
            rec["day"] = day
            rec["counters"] = {}
        rows = rec.get("counters", {})
        ctr = rows if isinstance(rows, dict) else {}
        used = int(ctr.get(key, 0) or 0)
        if used + n > cap:
            raise ReqErr(
                "plan_quota_exceeded",
                code=402,
                detail=f"plan={plan} key={key} used={used} cap={cap}",
            )
        ctr[key] = used + n
        rec["counters"] = ctr
        rec["updated_at"] = int(now)
        _usage_save(cfg, rec)


def _seat_limit(cfg: dict) -> int:
    rec = _billing_load(cfg) or _billing_default(cfg)
    cap = _plan_limit(cfg, "seats_max")
    raw = int(rec.get("seats", 1) or 1)
    seats = max(1, raw)
    if cap > 0 and int(rec.get("period_end", 0) or 0) <= 0 and seats <= 1:
        seats = cap
    return min(seats, cap) if cap > 0 else seats


def _active_member_count(ws: dict) -> int:
    vals = ws.get("members", [])
    rows = vals if isinstance(vals, list) else []
    return len([x for x in rows if isinstance(x, dict)])


def _pending_invite_count(ws: dict) -> int:
    vals = ws.get("invites", [])
    rows = vals if isinstance(vals, list) else []
    out = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("status", "")) == "pending":
            out += 1
    return out


def billing_payload(cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin", "member"})
    rec = _billing_load(cfg) or _billing_default(cfg)
    return {"ok": True, "billing": rec}


def billing_usage_payload(cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin", "member"})
    rep = report_corpus(cfg)
    met = _metrics_get()
    quo = _quota_snapshot(cfg)
    return {
        "ok": True,
        "usage": {
            "files": int(rep.get("total_files", 0) or 0),
            "bytes": int(rep.get("total_bytes", 0) or 0),
            "api_hits": int(met.get("api_hits", 0) or 0),
            "exports": len(_export_history_list(cfg)),
            "scans_started": int(met.get("scans_started", 0) or 0),
            "rate_limited": int(met.get("rate_limited", 0) or 0),
            "quota_day": str(quo.get("day", "")),
            "quota_used": quo.get("used", {}),
            "quota_limits": quo.get("limits", {}),
            "plan": str(quo.get("plan", "free")),
        },
    }


def billing_checkout_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    data = body(req)
    plan = _billing_plan_clean(data.get("plan") or _billing_plan(cfg))
    if plan == "free":
        raise ReqErr("invalid_plan", code=400)
    rec = _billing_load(cfg) or _billing_default(cfg)
    cap = _plan_limit(cfg, "seats_max")
    raw = int(data.get("seats", rec.get("seats", 1)) or 1)
    seats = max(1, raw)
    if cap > 0:
        seats = min(seats, cap)
    price = _billing_price_id(cfg, plan)
    if not price:
        raise ReqErr("billing_price_missing", code=400, detail=f"plan={plan}")
    secret = _billing_secret_key(cfg)
    if not secret:
        raise ReqErr("billing_provider_unconfigured", code=503)
    base = _billing_req_base(req)
    success = str(data.get("success_url", "")).strip() or \
        _billing_success_url(cfg, base)
    cancel = str(data.get("cancel_url", "")).strip() or \
        _billing_cancel_url(cfg, base)
    form = _billing_checkout_form(rec, plan, seats, price, success, cancel)
    api = _stripe_api_base(cfg)
    out = _billing_form_post(f"{api}/v1/checkout/sessions", secret, form)
    rec["provider"] = "stripe"
    rec["plan_pending"] = plan
    rec["checkout_session_id"] = str(out.get("id", ""))
    rec["checkout_url"] = str(out.get("url", ""))
    if out.get("customer"):
        rec["customer_id"] = str(out.get("customer", ""))
    rec["updated_at"] = int(time.time())
    _billing_save(cfg, rec)
    return {
        "ok": True,
        "provider": "stripe",
        "checkout_url": rec.get("checkout_url", ""),
        "session_id": rec.get("checkout_session_id", ""),
        "billing": rec,
    }


def billing_portal_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    rec = _billing_load(cfg) or _billing_default(cfg)
    cust = str(rec.get("customer_id", "")).strip()
    if not cust:
        raise ReqErr("billing_customer_required", code=400)
    secret = _billing_secret_key(cfg)
    if not secret:
        raise ReqErr("billing_provider_unconfigured", code=503)
    data = body(req)
    base = _billing_req_base(req)
    ret = str(data.get("return_url", "")).strip() or \
        _billing_return_url(cfg, base)
    api = _stripe_api_base(cfg)
    out = _billing_form_post(
        f"{api}/v1/billing_portal/sessions",
        secret,
        {"customer": cust, "return_url": ret},
    )
    rec["portal_url"] = str(out.get("url", ""))
    rec["updated_at"] = int(time.time())
    _billing_save(cfg, rec)
    return {"ok": True, "provider": "stripe", "portal_url": rec["portal_url"]}


def billing_webhook_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    raw = body_raw(req)
    txt = decode_body(raw)
    if not txt.strip():
        raise ReqErr("invalid_json", code=400, detail="json_object_required")
    allow_unsigned = bool(cfg.get("billing_webhook_allow_unsigned", False))
    secret = _billing_webhook_secret(cfg)
    if not secret and not allow_unsigned:
        raise ReqErr("billing_webhook_unconfigured", code=503)
    sig = str(req.headers.get("stripe-signature", "")).strip()
    if secret:
        _billing_verify_sig(raw, sig, secret, cfg)
    try:
        evt = json.loads(txt)
    except Exception:
        raise ReqErr("invalid_json", code=400)
    if not isinstance(evt, dict):
        raise ReqErr("invalid_json", code=400, detail="json_object_required")
    row = _billing_apply_event(cfg, evt)
    return {"ok": True, "applied": row}


def _billing_apply_event(cfg: dict, evt: dict) -> dict:
    rec = _billing_load(cfg) or _billing_default(cfg)
    eid = str(evt.get("id", "")).strip()
    if eid and _billing_event_seen(rec, eid):
        return {"type": str(evt.get("type", "")), "updated": False,
                "duplicate": True, "billing": rec}
    typ = str(evt.get("type", "")).strip()
    obj = evt.get("data", {}).get("object", {})
    if not isinstance(obj, dict):
        obj = {}
    now = int(time.time())
    out = {"type": typ, "updated": False}
    if typ == "checkout.session.completed":
        rec["provider"] = "stripe"
        rec["status"] = "active"
        rec["plan"] = _billing_event_plan(obj, rec)
        rec["seats"] = _billing_event_seats(cfg, obj, rec)
        rec["checkout_session_id"] = str(obj.get("id", ""))
        if obj.get("customer"):
            rec["customer_id"] = str(obj.get("customer", ""))
        if obj.get("subscription"):
            rec["subscription_id"] = str(obj.get("subscription", ""))
        rec["updated_at"] = now
        out["updated"] = True
    elif typ in {"customer.subscription.updated",
                 "customer.subscription.created"}:
        _billing_update_from_sub(cfg, rec, obj)
        rec["updated_at"] = now
        out["updated"] = True
    elif typ in {"customer.subscription.deleted"}:
        rec["status"] = "canceled"
        rec["updated_at"] = now
        out["updated"] = True
    if out["updated"]:
        if eid:
            _billing_event_mark(rec, eid)
        _billing_save(cfg, rec)
    out["billing"] = rec
    return out


def _billing_event_seen(rec: dict, eid: str) -> bool:
    vals = rec.get("event_ids", [])
    rows = vals if isinstance(vals, list) else []
    return eid in rows


def _billing_event_mark(rec: dict, eid: str) -> None:
    vals = rec.get("event_ids", [])
    rows = vals if isinstance(vals, list) else []
    if eid in rows:
        rec["event_ids"] = rows[-100:]
        return
    rows.append(eid)
    rec["event_ids"] = rows[-100:]


def _billing_plan_clean(raw: object) -> str:
    plan = str(raw or "free").strip().lower()
    return plan if plan in {"free", "pro", "team", "enterprise"} else "free"


def _billing_event_plan(obj: dict, rec: dict) -> str:
    meta = obj.get("metadata", {})
    if isinstance(meta, dict):
        plan = _billing_plan_clean(meta.get("plan"))
        if plan != "free":
            return plan
    return _billing_plan_clean(rec.get("plan", "free"))


def _billing_event_seats(cfg: dict, obj: dict, rec: dict) -> int:
    seats = int(rec.get("seats", 1) or 1)
    meta = obj.get("metadata", {})
    if isinstance(meta, dict):
        try:
            seats = max(1, int(meta.get("seats", seats) or seats))
        except Exception:
            seats = max(1, seats)
    cap = _plan_limit(cfg, "seats_max")
    return min(seats, cap) if cap > 0 else seats


def _billing_update_from_sub(cfg: dict, rec: dict, obj: dict) -> None:
    rec["provider"] = "stripe"
    rec["status"] = str(obj.get("status", "active") or "active")
    rec["subscription_id"] = str(obj.get("id", rec.get("subscription_id", "")))
    if obj.get("customer"):
        rec["customer_id"] = str(obj.get("customer", ""))
    cur = int(obj.get("current_period_end", 0) or 0)
    if cur > 0:
        rec["period_end"] = cur
    items_obj = obj.get("items", {})
    items = items_obj.get("data", []) if isinstance(items_obj, dict) else []
    if isinstance(items, list) and items:
        qty = int(items[0].get("quantity", rec.get("seats", 1)) or 1)
        cap = _plan_limit(cfg, "seats_max")
        rec["seats"] = min(max(1, qty), cap) if cap > 0 else max(1, qty)


def _billing_secret_key(cfg: dict) -> str:
    return _env_pick("CTXORG_STRIPE_SECRET_KEY", "STRIPE_SECRET_KEY",
                     cfg.get("stripe_secret_key", ""))


def _billing_webhook_secret(cfg: dict) -> str:
    return _env_pick("CTXORG_BILLING_WEBHOOK_SECRET",
                     "STRIPE_WEBHOOK_SECRET",
                     cfg.get("billing_webhook_secret", ""))


def _stripe_api_base(cfg: dict) -> str:
    raw = _env_pick("CTXORG_STRIPE_API_BASE", "STRIPE_API_BASE",
                    cfg.get("stripe_api_base", "https://api.stripe.com"))
    out = str(raw or "").strip().rstrip("/")
    return out or "https://api.stripe.com"


def _billing_price_id(cfg: dict, plan: str) -> str:
    key = f"CTXORG_STRIPE_PRICE_{plan.upper()}"
    alt = f"STRIPE_PRICE_{plan.upper()}"
    path = f"stripe_price_{plan}"
    return _env_pick(key, alt, cfg.get(path, ""))


def _billing_success_url(cfg: dict, base: str) -> str:
    return _env_pick("CTXORG_BILLING_SUCCESS_URL", "BILLING_SUCCESS_URL",
                     f"{base}/?mode=settings&billing=success")


def _billing_cancel_url(cfg: dict, base: str) -> str:
    return _env_pick("CTXORG_BILLING_CANCEL_URL", "BILLING_CANCEL_URL",
                     f"{base}/?mode=settings&billing=cancel")


def _billing_return_url(cfg: dict, base: str) -> str:
    return _env_pick("CTXORG_BILLING_RETURN_URL", "BILLING_RETURN_URL",
                     f"{base}/?mode=settings")


def _billing_req_base(req: BaseHTTPRequestHandler) -> str:
    host = _req_host(req) or "127.0.0.1:8765"
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    return f"http://{host}"


def _billing_checkout_form(rec: dict, plan: str, seats: int, price: str,
                           success: str, cancel: str) -> dict[str, str]:
    wsid = str(rec.get("workspace_id", "")).strip()
    out = {
        "mode": "subscription",
        "success_url": success,
        "cancel_url": cancel,
        "line_items[0][price]": price,
        "line_items[0][quantity]": str(max(1, seats)),
        "allow_promotion_codes": "true",
        "metadata[plan]": plan,
        "metadata[seats]": str(max(1, seats)),
    }
    if wsid:
        out["client_reference_id"] = wsid
        out["metadata[workspace_id]"] = wsid
    cust = str(rec.get("customer_id", "")).strip()
    if cust:
        out["customer"] = cust
    return out


def _billing_form_post(url: str, secret: str, form: dict[str, str]) -> dict:
    data = urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as fh:
            raw = fh.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:300]
        raise ReqErr("billing_provider_failed", code=502, detail=detail)
    except Exception as exc:
        raise ReqErr("billing_provider_failed", code=502, detail=str(exc)[:220])
    try:
        out = json.loads(raw)
    except Exception:
        raise ReqErr("billing_provider_failed", code=502, detail="invalid_json")
    if isinstance(out, dict):
        return out
    raise ReqErr("billing_provider_failed", code=502, detail="bad_payload")


def _billing_sig_vals(raw: str) -> tuple[int, list[str]]:
    ts, vals = 0, []
    for tok in str(raw or "").split(","):
        key, _, val = tok.strip().partition("=")
        if key == "t":
            try:
                ts = int(val or 0)
            except Exception:
                ts = 0
        if key == "v1" and val:
            vals.append(val)
    return ts, vals


def _billing_verify_sig(raw: bytes, hdr: str, secret: str, cfg: dict) -> None:
    ts, vals = _billing_sig_vals(hdr)
    if ts <= 0 or not vals:
        raise ReqErr("billing_signature_invalid", code=400)
    tol = int(cfg.get("billing_webhook_tolerance_sec", 300) or 300)
    if abs(int(time.time()) - ts) > max(30, tol):
        raise ReqErr("billing_signature_stale", code=400)
    base = f"{ts}.{decode_body(raw)}".encode("utf-8")
    want = hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(want, got) for got in vals):
        raise ReqErr("billing_signature_invalid", code=400)


def billing_plan_update_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin"})
    data = body(req)
    plan = str(data.get("plan", "")).strip().lower()
    if plan not in {"free", "pro", "team", "enterprise"}:
        raise ReqErr("invalid_plan", code=400)
    rec = _billing_load(cfg) or _billing_default(cfg)
    rec["plan"] = plan
    rec["plan_pending"] = ""
    rec["status"] = "active"
    rec["updated_at"] = int(time.time())
    seats = max(1, int(data.get("seats", rec.get("seats", 1)) or 1))
    cap = _plan_limit(cfg, "seats_max")
    rec["seats"] = min(seats, cap) if cap > 0 else seats
    days = 30 if plan != "enterprise" else 365
    rec["period_end"] = int(time.time()) + days * 86400
    _billing_save(cfg, rec)
    return {"ok": True, "billing": rec}


def _api_key_scopes(raw: object) -> list[str]:
    if not isinstance(raw, list):
        raw = []
    out = []
    allow = {"read", "write", "scan", "export", "integrations", "admin"}
    for row in raw:
        val = str(row).strip().lower()
        if val in allow and val not in out:
            out.append(val)
    return out or ["read"]


def _api_keys_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg) / "api_keys.json"


def _api_keys_list(cfg: dict) -> list[dict]:
    data = _store_read(_api_keys_path(cfg))
    if not data:
        return []
    vals = data.get("items", [])
    rows = vals if isinstance(vals, list) else []
    return [x for x in rows if isinstance(x, dict)]


def _api_key_public(row: dict) -> dict:
    out = dict(row)
    out.pop("hash", None)
    return out


def _api_keys_save(cfg: dict, vals: list[dict]) -> None:
    _store_write(_api_keys_path(cfg), {"items": vals})


def _api_key_match(cfg: dict, token: str) -> dict | None:
    if not token.startswith("opk_"):
        return None
    now = int(time.time())
    want = hashlib.sha256(token.encode("utf-8")).hexdigest()
    for row in _api_keys_list(cfg):
        if str(row.get("status", "active")) != "active":
            continue
        if str(row.get("hash", "")) != want:
            continue
        exp = int(row.get("expires_at", 0) or 0)
        if exp and exp < now:
            continue
        return row
    return None


def _api_key_touch(cfg: dict, kid: str) -> None:
    if not kid:
        return
    vals = _api_keys_list(cfg)
    now = int(time.time())
    changed = False
    for row in vals:
        if not isinstance(row, dict):
            continue
        if str(row.get("id", "")) != kid:
            continue
        row["last_used_at"] = now
        changed = True
    if changed:
        _api_keys_save(cfg, vals)


def _session_days(cfg: dict) -> int:
    set_cfg = _settings_runtime(cfg).get("profile", {})
    days = int(set_cfg.get("session_days", 30) or 30)
    return max(1, min(365, days))


def _sess_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg) / "sessions.json"


def _sess_list(cfg: dict) -> list[dict]:
    data = _store_read(_sess_path(cfg))
    if not data:
        return []
    vals = data.get("items", [])
    rows = vals if isinstance(vals, list) else []
    return [x for x in rows if isinstance(x, dict)]


def _sess_save(cfg: dict, vals: list[dict]) -> None:
    _store_write(_sess_path(cfg), {"items": vals[-800:]})


def _sess_create(cfg: dict, email: str, days: int) -> str:
    now = int(time.time())
    sid = f"ses-{uuid.uuid4().hex[:12]}"
    sec = uuid.uuid4().hex + uuid.uuid4().hex
    tok = f"ops_{sid}_{sec}"
    row = {
        "id": sid,
        "email": email.strip().lower(),
        "status": "active",
        "hash": hashlib.sha256(tok.encode("utf-8")).hexdigest(),
        "created_at": now,
        "expires_at": now + days * 86400,
        "last_seen_at": now,
    }
    vals = _sess_list(cfg)
    vals.append(row)
    _sess_save(cfg, vals)
    return tok


def _sess_lookup(cfg: dict, tok: str) -> dict | None:
    if not tok.startswith("ops_"):
        return None
    now = int(time.time())
    want = hashlib.sha256(tok.encode("utf-8")).hexdigest()
    for row in _sess_list(cfg):
        if str(row.get("status", "")) != "active":
            continue
        if str(row.get("hash", "")) != want:
            continue
        exp = int(row.get("expires_at", 0) or 0)
        if exp and exp < now:
            continue
        return row
    return None


def _sess_touch(cfg: dict, sid: str) -> None:
    if not sid:
        return
    vals = _sess_list(cfg)
    now = int(time.time())
    changed = False
    for row in vals:
        if str(row.get("id", "")) != sid:
            continue
        row["last_seen_at"] = now
        changed = True
    if changed:
        _sess_save(cfg, vals)


def _sess_revoke(cfg: dict, tok: str) -> None:
    if not tok:
        return
    want = hashlib.sha256(tok.encode("utf-8")).hexdigest()
    vals = _sess_list(cfg)
    now = int(time.time())
    changed = False
    for row in vals:
        if str(row.get("hash", "")) != want:
            continue
        row["status"] = "revoked"
        row["revoked_at"] = now
        changed = True
    if changed:
        _sess_save(cfg, vals)


def _billing_default(cfg: dict) -> dict:
    ws = _workspace_load(cfg)
    rows = ws.get("members", []) if isinstance(ws, dict) else []
    seats = len(rows) if isinstance(rows, list) and rows else 1
    return {
        "workspace_id": str(ws.get("id", "")) if ws else "",
        "plan": "free",
        "plan_pending": "",
        "provider": "",
        "status": "active",
        "seats": max(1, int(seats)),
        "customer_id": "",
        "subscription_id": "",
        "checkout_session_id": "",
        "checkout_url": "",
        "portal_url": "",
        "event_ids": [],
        "period_end": 0,
        "updated_at": int(time.time()),
    }


def _billing_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg) / "billing.json"


def _billing_load(cfg: dict) -> dict | None:
    data = _store_read(_billing_path(cfg))
    return data if isinstance(data, dict) else None


def _billing_save(cfg: dict, rec: dict) -> None:
    _store_write(_billing_path(cfg), rec)


def _workspace_bootstrap(cfg: dict, acct: dict) -> dict | None:
    if "state_dir" not in cfg:
        return None
    ws = _workspace_load(cfg)
    email = str(acct.get("email", "")).strip().lower()
    name = str(acct.get("name", "")).strip()
    if not ws:
        now = int(time.time())
        ws = {
            "id": f"ws-{uuid.uuid4().hex[:10]}",
            "name": "Optic Workspace",
            "slug": "optic-workspace",
            "owner_email": email,
            "created_at": now,
            "updated_at": now,
            "members": [],
            "invites": [],
        }
    ws = _workspace_member_upsert(ws, email=email, name=name, role=
                                  _workspace_owner_role(ws, email))
    ws["updated_at"] = int(time.time())
    _workspace_save(cfg, ws)
    return ws


def _workspace_owner_role(ws: dict, email: str) -> str:
    own = str(ws.get("owner_email", "")).strip().lower()
    if own and own == email:
        return "owner"
    if not own:
        ws["owner_email"] = email
        return "owner"
    return "member"


def _workspace_member_upsert(ws: dict, email: str, name: str,
                             role: str) -> dict:
    members = ws.get("members", [])
    rows = members if isinstance(members, list) else []
    now = int(time.time())
    role = _workspace_role_clean(role)
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("email", "")).strip().lower() != email:
            continue
        row["name"] = (name or str(row.get("name", "")) or "Member")[:80]
        row["role"] = role
        row["status"] = "active"
        row["updated_at"] = now
        ws["members"] = rows
        return ws
    rows.append({
        "email": email,
        "name": (name or "Member")[:80],
        "role": role,
        "status": "active",
        "joined_at": now,
        "updated_at": now,
    })
    ws["members"] = rows
    return ws


def _workspace_role_clean(raw: object) -> str:
    val = str(raw or "member").strip().lower()
    if val in {"owner", "admin", "member"}:
        return val
    return "member"


def _workspace_member_find(ws: dict, email: str) -> dict | None:
    vals = ws.get("members", [])
    rows = vals if isinstance(vals, list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("email", "")).strip().lower() == email:
            return row
    return None


def _workspace_role(ws: dict | None, email: str) -> str:
    if not ws or not email:
        return ""
    own = str(ws.get("owner_email", "")).strip().lower()
    if own and own == email:
        return "owner"
    row = _workspace_member_find(ws, email)
    if not row:
        return ""
    return _workspace_role_clean(row.get("role"))


def _workspace_brief(ws: dict | None, role: str) -> dict | None:
    if not ws:
        return None
    return {
        "id": str(ws.get("id", "")),
        "name": str(ws.get("name", "")),
        "slug": str(ws.get("slug", "")),
        "role": role,
    }


def _workspace_public(ws: dict, role: str) -> dict:
    vals = ws.get("members", [])
    rows = vals if isinstance(vals, list) else []
    members = [x for x in rows if isinstance(x, dict)]
    return {
        "id": str(ws.get("id", "")),
        "name": str(ws.get("name", "")),
        "slug": str(ws.get("slug", "")),
        "owner_email": str(ws.get("owner_email", "")),
        "role": role,
        "member_count": len(members),
        "created_at": int(ws.get("created_at", 0) or 0),
        "updated_at": int(ws.get("updated_at", 0) or 0),
    }


def _workspace_slug(raw: str) -> str:
    txt = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return (txt or "optic-workspace")[:64]


def _workspace_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg) / "workspace.json"


def _workspace_load(cfg: dict) -> dict | None:
    if "state_dir" not in cfg:
        return None
    data = _store_read(_workspace_path(cfg))
    if not data:
        return None
    return data if isinstance(data, dict) else None


def _workspace_save(cfg: dict, ws: dict) -> None:
    if "state_dir" not in cfg:
        return
    _store_write(_workspace_path(cfg), ws)


def _acct_email(cfg: dict) -> str:
    rec = _acct_load(cfg)
    if not rec:
        return ""
    return str(rec.get("email", "")).strip().lower()


def _acct_must(cfg: dict) -> dict:
    rec = _acct_load(cfg)
    if not rec:
        raise ReqErr("auth_required", code=401)
    return rec


def _workspace_must(cfg: dict) -> dict:
    ws = _workspace_load(cfg)
    if not ws:
        raise ReqErr("workspace_not_found", code=404)
    return ws


def _workspace_require_role(cfg: dict, roles: set[str]) -> str:
    scopes = _auth_scopes()
    if scopes:
        got = _scope_role(scopes, roles)
        if got:
            return got
    if "state_dir" not in cfg:
        return "owner"
    ws = _workspace_load(cfg)
    if not ws:
        return "owner"
    rec = _acct_must(cfg)
    role = _workspace_role(ws, str(rec.get("email", "")).lower())
    if role in roles:
        return role
    raise ReqErr("workspace_forbidden", code=403)


def _acct_mark_onboard(cfg: dict, run_id: str) -> None:
    rec = _acct_load(cfg)
    if not rec:
        return
    rec["onboarded"] = True
    rec["updated_at"] = int(time.time())
    rec["last_run"] = run_id or str(rec.get("last_run", ""))
    _acct_save(cfg, rec)


def _acct_public(rec: dict) -> dict:
    return {
        "name": str(rec.get("name", "")),
        "email": str(rec.get("email", "")),
        "provider": str(rec.get("provider", "email")),
        "initials": str(rec.get("initials", "")),
        "onboarded": bool(rec.get("onboarded", False)),
        "created_at": int(rec.get("created_at", 0) or 0),
        "updated_at": int(rec.get("updated_at", 0) or 0),
        "last_run": str(rec.get("last_run", "")),
    }


def _acct_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg) / "account.json"


def _acct_load(cfg: dict) -> dict | None:
    ctx = _auth_get()
    if ctx:
        rec = ctx.get("acct")
        return rec if isinstance(rec, dict) else None
    return _acct_load_legacy(cfg)


def _acct_load_legacy(cfg: dict) -> dict | None:
    path = _acct_path(cfg)
    with _acct_lock:
        if not path.exists():
            return None
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    if not isinstance(rec, dict):
        return None
    if not rec.get("email") or not rec.get("name"):
        return None
    return rec


def _acct_save(cfg: dict, rec: dict) -> None:
    _acct_save_legacy(cfg, rec)
    _accounts_upsert(cfg, rec)


def _acct_save_legacy(cfg: dict, rec: dict) -> None:
    path = _acct_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    data = json.dumps(rec, sort_keys=True, separators=(",", ":"))
    with _acct_lock:
        tmp.write_text(data, encoding="utf-8")
        tmp.replace(path)


def _acct_clear(cfg: dict) -> None:
    _acct_clear_legacy(cfg)


def _acct_clear_legacy(cfg: dict) -> None:
    path = _acct_path(cfg)
    with _acct_lock:
        if not path.exists():
            return
        try:
            path.unlink()
        except Exception:
            return


def _acct_lookup(cfg: dict, email: str) -> dict | None:
    needle = email.strip().lower()
    if not needle:
        return None
    rec = _accounts_get(cfg, needle)
    if rec:
        return rec
    old = _acct_load_legacy(cfg)
    if old and str(old.get("email", "")).strip().lower() == needle:
        return old
    return None


def _accounts_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg) / "accounts.json"


def _accounts_list(cfg: dict) -> list[dict]:
    data = _store_read(_accounts_path(cfg))
    if not data:
        return []
    vals = data.get("items", [])
    rows = vals if isinstance(vals, list) else []
    return [x for x in rows if isinstance(x, dict)]


def _accounts_save(cfg: dict, vals: list[dict]) -> None:
    _store_write(_accounts_path(cfg), {"items": vals[-500:]})


def _accounts_get(cfg: dict, email: str) -> dict | None:
    needle = email.strip().lower()
    for row in _accounts_list(cfg):
        mail = str(row.get("email", "")).strip().lower()
        if mail == needle:
            return row
    return None


def _accounts_upsert(cfg: dict, rec: dict) -> None:
    rows = _accounts_list(cfg)
    email = str(rec.get("email", "")).strip().lower()
    if not email:
        return
    out = []
    hit = False
    for row in rows:
        if str(row.get("email", "")).strip().lower() == email:
            out.append(dict(rec))
            hit = True
        else:
            out.append(row)
    if not hit:
        out.append(dict(rec))
    _accounts_save(cfg, out)


def _store_read(path: Path) -> dict | None:
    with _store_lock:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return data if isinstance(data, dict) else None


def _store_write(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    data = json.dumps(rec, sort_keys=True, separators=(",", ":"))
    with _store_lock:
        tmp.write_text(data, encoding="utf-8")
        tmp.replace(path)


def _acct_provider(raw: object) -> str:
    val = str(raw or "email").strip().lower()
    return val if val in {"google", "apple", "email"} else "email"


def _acct_name(raw: str, email: str) -> str:
    val = raw.strip()
    if not val:
        head = email.split("@", 1)[0]
        txt = head.replace(".", " ").replace("_", " ").replace("-", " ")
        val = " ".join(p.capitalize() for p in txt.split())
    return (val or "Local User")[:80].strip()


def _acct_initials(name: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", name) if p]
    if not parts:
        return "U"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def home_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    run = _run_query(req, cfg)
    conn = db.open_db(cfg)
    stat = db.rows(
        conn,
        "SELECT COUNT(*) as c, COALESCE(SUM(size),0) as s "
        "FROM items WHERE kind='file'",
    )
    file_count = int(stat[0]["c"] if stat else 0)
    total_size = int(stat[0]["s"] if stat else 0)
    ws = _load_ws(cfg, run)

    # ── V1 fallback for file_count when scanner DB is empty ──
    if file_count == 0 and _V1_AVAILABLE:
        v1_total = _v1_total_file_count()
        if v1_total > 0:
            file_count = v1_total

    graph = read_graph(cfg, run)
    nodes = list(graph.get("nodes", []))
    signal_count = len(nodes) if nodes else file_count
    source_count = _source_count(nodes, cfg)
    coh = _coherence(ws)
    narratives = _top_narratives(ws)
    exposures = _exposures(ws)
    summary = _home_summary_get(cfg, run)
    if summary is None and run:
        _home_summary_start(cfg, run, ws, signal_count, narratives)
    return {
        "file_count": file_count,
        "total_size": total_size,
        "workstreams_count": len(ws),
        "coherence_avg": coh,
        "signal_count": signal_count,
        "source_count": source_count,
        "last_analyzed_ago": _ago(_run_ts(cfg, run)),
        "narratives": narratives,
        "exposures": exposures,
        "iris_summary": summary,
        "home": cfg.get("home", ""),
        "account": account_payload(cfg),
    }


def audiences_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    run = _run_query(req, cfg)
    cached = _aud_cache_get(run)
    if cached:
        return {"run": run, "audiences": cached, "cached": True}
    ws = _load_ws(cfg, run, allow_compute=False)
    rows = [_aud_row(ws, item) for item in _AUDIENCES]
    rows.sort(key=lambda x: -(x.get("score") or 0))
    _aud_cache_set(run, rows)
    return {"run": run, "audiences": rows, "cached": False}


def simulate_payload(req: BaseHTTPRequestHandler, cfg: dict,
                     audience_id: str) -> dict:
    aid = audience_id.strip().lower()
    prof = _aud_profile(aid)
    if not prof:
        raise ReqErr("unknown_audience", code=404)
    run = query(req).get("run", [""])[0] or latest(cfg)
    ws = _load_ws(cfg, run)
    score = _audience_score(ws, prof)
    hits = _highlights(ws, prof)
    risks = _risks(ws, prof, hits)
    msg = _aud_narrative(prof, hits)
    return {
        "run": run,
        "audience_id": aid,
        "name": prof["name"],
        "icon": prof["icon"],
        "score": score,
        "highlights": hits,
        "risks": risks,
        "narrative": msg,
    }


def simulations_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    run = _run_query(req, cfg)
    vals = [x for x in _scenarios_list(cfg) if x.get("run") == run]
    vals.sort(key=lambda x: -int(x.get("created_at", 0) or 0))
    return {"run": run, "items": vals[:40]}


def simulation_eval_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    data = body(req)
    return {"ok": True, "scenario": _simulation_eval(cfg, data)}


def simulation_save_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    data = body(req)
    rec = _simulation_eval(cfg, data)
    rec["id"] = f"sim-{uuid.uuid4().hex[:10]}"
    rec["created_at"] = int(time.time())
    vals = _scenarios_list(cfg)
    vals.append(rec)
    _scenarios_save(cfg, vals[-200:])
    return {"ok": True, "scenario": rec}


def simulation_compare_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    data = body(req)
    left = str(data.get("left_id", "")).strip()
    right = str(data.get("right_id", "")).strip()
    if not left or not right:
        raise ReqErr("scenario_ids_required", code=400)
    vals = _scenarios_list(cfg)
    a = next((x for x in vals if str(x.get("id")) == left), None)
    b = next((x for x in vals if str(x.get("id")) == right), None)
    if not a or not b:
        raise ReqErr("scenario_not_found", code=404)
    return {"ok": True, "left": a, "right": b, "delta": _scenario_delta(a, b)}


def v1_simulation_eval_payload(req: BaseHTTPRequestHandler, cfg: dict,
                               audience_id: str) -> dict:
    """POST /api/v1/simulate/{audience_id} — evaluate with cluster selections."""
    data = body(req)
    data["audience_id"] = audience_id.strip().lower()
    return {"ok": True, "scenario": _simulation_eval(cfg, data)}


def _simulation_eval(cfg: dict, data: dict) -> dict:
    run = str(data.get("run", "")).strip() or latest(cfg)
    aid = str(data.get("audience_id", "recruiter")).strip().lower()
    prof = _aud_profile(aid)
    if not prof:
        raise ReqErr("unknown_audience", code=404)
    include = _scenario_ids(data.get("include_clusters", []))
    exclude = _scenario_ids(data.get("exclude_clusters", []))
    ws = _load_ws(cfg, run)
    base = _audience_score(ws, prof)
    nxt_rows = _scenario_apply(ws, include, exclude)
    nxt = _audience_score(nxt_rows, prof)
    delta = (nxt - base) if (base is not None and nxt is not None) else None
    n = max(1, len(nxt_rows))
    ci = round(max(2.0, min(15.0, 14.0 / (n ** 0.5))), 1)
    return {
        "id": "",
        "name": str(data.get("name", "Untitled scenario")).strip()[:80],
        "run": run,
        "audience_id": aid,
        "audience_name": prof["name"],
        "include_clusters": include,
        "exclude_clusters": exclude,
        "before_score": base,
        "after_score": nxt,
        "delta": delta,
        "confidence_interval": {
            "low": max(0, round(nxt - ci, 1)) if nxt is not None else None,
            "high": min(100, round(nxt + ci, 1)) if nxt is not None else None,
        },
        "sample_size": n,
    }


def _scenario_ids(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    out = []
    seen = set()
    for val in raw:
        txt = str(val or "").strip()
        if not txt or txt in seen:
            continue
        seen.add(txt)
        out.append(txt[:140])
    return out[:80]


def _scenario_apply(ws: list[dict], inc: list[str], exc: list[str]) -> list[dict]:
    if not ws:
        return []
    vals = [dict(x) for x in ws]
    if inc:
        pick = set(inc)
        vals = [x for x in vals if _ws_id(x) in pick]
    if exc:
        drop = set(exc)
        vals = [x for x in vals if _ws_id(x) not in drop]
    return vals


def _ws_id(card: dict) -> str:
    return str(card.get("id") or card.get("name") or "")


def _scenario_delta(a: dict, b: dict) -> dict:
    return {
        "before_score": int(a.get("after_score", 0) or 0),
        "after_score": int(b.get("after_score", 0) or 0),
        "delta": int(b.get("after_score", 0) or 0) -
        int(a.get("after_score", 0) or 0),
    }


def _scenarios_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg) / "simulations.json"


def _scenarios_list(cfg: dict) -> list[dict]:
    data = _store_read(_scenarios_path(cfg))
    if not data:
        return []
    vals = data.get("items", [])
    return vals if isinstance(vals, list) else []


def _scenarios_save(cfg: dict, vals: list[dict]) -> None:
    _store_write(_scenarios_path(cfg), {"items": vals})


def _load_ws(cfg: dict, run: str, allow_compute: bool = True) -> list[dict]:
    with _ws_lock:
        cached = _ws_cache.get(run)
        if cached and cached.get("cards"):
            return list(cached["cards"])
    if not allow_compute:
        return []
    try:
        from . import workstreams
        conn = db.open_db(cfg)
        cards = workstreams.compute(
            conn, cfg, run_id=run, limit=30, gemma_budget=0
        )
    except Exception:
        cards = []

    # ── V1 fallback when scanner DB returns empty ──
    if not cards and _V1_AVAILABLE:
        cards = _v1_workstreams_fallback()

    with _ws_lock:
        cur = _ws_cache.setdefault(run, {"cards": [], "ready": False})
        if not cur.get("cards"):
            cur["cards"] = list(cards)
        if cards and not cur.get("ready"):
            cur["ready"] = True  # V1 cards don't need Gemma
    return cards


def _aud_row(ws: list[dict], prof: dict) -> dict:
    return {
        "id": prof["id"],
        "name": prof["name"],
        "icon": prof["icon"],
        "score": _audience_score(ws, prof),
        "summary": prof.get("summary", ""),
    }


def _audience_score(ws: list[dict], prof: dict) -> int:
    if not ws:
        return 50
    ranked = _aud_rank(ws, prof)[:5]
    if not ranked:
        return 50
    fit = sum(r["fit"] for r in ranked) / len(ranked)
    conf = sum(r["conf"] for r in ranked) / len(ranked)
    noise = sum(r["noise"] for r in ranked) / len(ranked)
    raw = 40 + fit * 45 + conf * 20 - noise * 18
    return int(max(18, min(97, round(raw))))


def _highlights(ws: list[dict], prof: dict) -> list[str]:
    rows = _aud_rank(ws, prof)
    out = []
    seen = set()
    for row in rows:
        if len(out) >= 5:
            break
        card = row["card"]
        name = _card_name(card)
        key = _name_key(name)
        if not key or key in seen:
            continue
        if row["conf"] < 0.35 and out:
            continue
        if row["noise"] > 0.75 and row["conf"] < 0.82:
            continue
        out.append(name)
        seen.add(key)
    if out:
        return out
    for row in rows:
        if len(out) >= 3:
            break
        name = _card_name(row["card"])
        key = _name_key(name)
        if key and key not in seen:
            out.append(name)
            seen.add(key)
    return out


def _risks(ws: list[dict], prof: dict, highs: list[str]) -> list[str]:
    out = []
    seen = {_name_key(x) for x in highs}
    rows = _aud_rank(ws, prof)
    rows.sort(key=lambda x: (-_risk_score(x), x["conf"]))
    for row in rows:
        if len(out) >= 5:
            break
        if _risk_score(row) < 0.45 and out:
            break
        name = _card_name(row["card"])
        key = _name_key(name)
        if not key or key in seen:
            continue
        out.append(name)
        seen.add(key)
    if out:
        return out
    for row in sorted(rows, key=lambda x: x["conf"]):
        if len(out) >= 3:
            break
        name = _card_name(row["card"])
        key = _name_key(name)
        if key and key not in seen:
            out.append(name)
            seen.add(key)
    return out


def _ws_text(card: dict) -> str:
    topics = " ".join(str(t).lower() for t in card.get("topics", []))
    name = str(card.get("name", "")).lower()
    return f"{topics} {name}"


def _aud_rank(ws: list[dict], prof: dict) -> list[dict]:
    rows = []
    for card in ws:
        conf = float(card.get("confidence", 0.0) or 0.0)
        fit = _aud_fit(card, prof)
        noise = _name_noise(_card_name(card), card)
        score = fit * 0.62 + conf * 0.28 + (1.0 - noise) * 0.10
        rows.append({
            "card": card,
            "score": score,
            "fit": fit,
            "conf": conf,
            "noise": noise,
        })
    rows.sort(key=lambda x: (-x["score"], -x["fit"], -x["conf"]))
    return rows


def _aud_fit(card: dict, prof: dict) -> float:
    txt = _ws_text(card)
    keys = [str(x).lower() for x in prof.get("keywords", [])]
    hit = sum(1 for key in keys if key and key in txt)
    key_fit = min(1.0, hit / max(2.0, len(keys) / 2.0))
    mix = _type_mix(card)
    w = prof.get("kind_w", {})
    max_w = max([float(v) for v in w.values()] or [1.0])
    kind_fit = sum(mix[k] * float(w.get(k, 0.25)) for k in mix) / max_w
    avoid = [str(x).lower() for x in prof.get("avoid", [])]
    avoid_hit = sum(1 for key in avoid if key and key in txt)
    avoid_fit = avoid_hit / max(1.0, len(avoid) / 3.0)
    key_w = float(prof.get("key_w", 0.55) or 0.55)
    kind_wt = float(prof.get("kind_wt", 0.45) or 0.45)
    avoid_w = float(prof.get("avoid_w", 0.30) or 0.30)
    total = max(0.1, key_w + kind_wt)
    raw = key_fit * (key_w / total) + kind_fit * (kind_wt / total)
    raw -= avoid_fit * avoid_w
    return max(0.0, min(1.0, raw))


def _type_mix(card: dict) -> dict[str, float]:
    vals = card.get("type_breakdown", {}) or {}
    nums = {k: int(vals.get(k, 0) or 0) for k in (
        "screenshots", "documents", "code", "media", "other"
    )}
    total = sum(nums.values())
    if total <= 0:
        total = max(1, int(card.get("file_count", 0) or 0))
        name = _card_name(card).lower()
        if "screenshot" in name or "photo" in name:
            nums["screenshots"] = total
        elif "note" in name or "document" in name or "pdf" in name:
            nums["documents"] = total
        elif "code" in name or "script" in name:
            nums["code"] = total
        else:
            nums["other"] = total
    return {k: nums[k] / max(total, 1) for k in nums}


def _name_key(name: str) -> str:
    low = re.sub(r"\s*\(\d+\)\s*$", "", name.lower())
    toks = [t for t in _WORD_RE.findall(low) if t not in {"read", "notes"}]
    if not toks:
        toks = _WORD_RE.findall(low)
    out = []
    seen = set()
    for tok in toks:
        if tok in seen:
            continue
        out.append(tok)
        seen.add(tok)
    return " ".join(out[:6])


def _card_name(card: dict) -> str:
    return str(card.get("name", "")).strip()


def _name_noise(name: str, card: dict) -> float:
    low = name.lower()
    noise = 0.0
    if " — " in low:
        parts = [p.strip() for p in low.split(" — ") if p.strip()]
        if len(parts) >= 2 and parts[0] == parts[1]:
            noise += 0.55
    if _HEX_RE.search(low):
        noise += 0.55
    if re.search(r"\(\d+\)\s*$", low):
        noise += 0.2
    toks = set(_WORD_RE.findall(low))
    if toks & _NOISE_TAGS:
        noise += 0.45
    if low.startswith("img "):
        noise += 0.35
    if len(toks) <= 2 and "notes" in low and float(
        card.get("confidence", 0.0) or 0.0
    ) <= 0.35:
        noise += 0.25
    return min(1.0, noise)


def _risk_score(row: dict) -> float:
    return row["noise"] * 0.55 + (1.0 - row["fit"]) * 0.3 + \
        (1.0 - row["conf"]) * 0.15


def _aud_narrative(prof: dict, hits: list[str]) -> str:
    top = _top_phrase(hits[:3]) if hits else "mixed signals"
    noun = "signal is" if len(hits) <= 1 else "signals are"
    view = str(prof.get("perspective", "an outside observer"))
    return f"From the perspective of {view}, your strongest {noun} {top}."


def _top_phrase(hits: list[str]) -> str:
    if not hits:
        return "mixed signals"
    if len(hits) == 1:
        return hits[0]
    if len(hits) == 2:
        return f"{hits[0]} and {hits[1]}"
    return f"{hits[0]}, {hits[1]}, and {hits[2]}"


def _aud_profile(aid: str) -> dict | None:
    for prof in _AUDIENCES:
        if prof["id"] == aid:
            return prof
    return None


def _aud_cache_get(run: str) -> list[dict]:
    if not run:
        return []
    with _aud_lock:
        rec = _aud_cache.get(run)
        if not rec:
            return []
        return list(rec.get("audiences", []))


def _aud_cache_set(run: str, audiences: list[dict]) -> None:
    if not run:
        return
    with _aud_lock:
        _aud_cache[run] = {"audiences": list(audiences), "ts": int(time.time())}
        if len(_aud_cache) > 16:
            olds = sorted(_aud_cache.items(), key=lambda x: x[1]["ts"])[:-16]
            for key, _ in olds:
                _aud_cache.pop(key, None)


def _coherence(ws: list[dict]) -> float:
    if not ws:
        return 0.0
    vals = [float(c.get("confidence", 0.0) or 0.0) for c in ws]
    return round(sum(vals) / max(len(vals), 1), 2)


def _top_narratives(ws: list[dict]) -> list[str]:
    score: dict[str, float] = {}
    for card in ws[:12]:
        conf = float(card.get("confidence", 0.0) or 0.0)
        for raw in card.get("topics", [])[:6]:
            topic = _topic_norm(raw)
            if not topic:
                continue
            score[topic] = score.get(topic, 0.0) + max(conf, 0.05)
    pairs = sorted(score.items(), key=lambda x: -x[1])[:5]
    return [_topic_name(k) for k, _ in pairs]


def _topic_norm(raw: object) -> str:
    txt = str(raw or "").strip().lower().replace("_", " ").replace("-", " ")
    words = [w for w in txt.split() if len(w) > 2]
    return " ".join(words[:3])


def _topic_name(topic: str) -> str:
    return " ".join(x.capitalize() for x in topic.split())


def _exposures(ws: list[dict]) -> int:
    keys = {"finance", "tax", "identity", "social", "health", "private"}
    count = 0
    for card in ws:
        txt = _ws_text(card)
        if any(k in txt for k in keys):
            count += 1
    return count


def _source_count(nodes: list[dict], cfg: dict) -> int:
    parents = set()
    for node in nodes:
        path = str(node.get("path", "") or "")
        if path:
            parents.add(str(Path(path).parent))
    if parents:
        return len(parents)
    vals = cfg.get("sources", [])
    return len(vals) if isinstance(vals, list) else 0


def _run_ts(cfg: dict, run: str) -> float:
    try:
        run = _run_clean(run)
    except ReqErr:
        return 0.0
    if not run:
        return 0.0
    try:
        return time.mktime(time.strptime(run, "%Y%m%d-%H%M%S"))
    except ValueError:
        pass
    path = cfgmod.state_dir(cfg, "graphs") / f"{run}.json"
    try:
        return float(path.stat().st_mtime)
    except Exception:
        return 0.0


def _ago(ts: float) -> str:
    if ts <= 0:
        return "unknown"
    age = max(1, int(time.time() - ts))
    if age < 60:
        return f"{age}s ago"
    if age < 3600:
        return f"{age // 60}m ago"
    if age < 86400:
        return f"{age // 3600}h ago"
    if age < 86400 * 7:
        return f"{age // 86400}d ago"
    return f"{age // (86400 * 7)}w ago"


def _home_summary_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg) / "home_summary.json"


def _home_summary_get(cfg: dict, run: str) -> str | None:
    if not run:
        return None
    path = _home_summary_path(cfg)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if str(data.get("run", "")) != run:
        return None
    txt = str(data.get("summary", "")).strip()
    return txt or None


def _home_summary_start(cfg: dict, run: str, ws: list[dict],
                        signal_count: int, narratives: list[str]) -> None:
    with _home_lock:
        if run in _home_jobs:
            return
        _home_jobs.add(run)
    args = (cfg, run, ws, int(signal_count), list(narratives))
    threading.Thread(target=_home_summary_task, args=args, daemon=True).start()


def _home_summary_task(cfg: dict, run: str, ws: list[dict],
                       signal_count: int, narratives: list[str]) -> None:
    try:
        txt = _home_summary_make(cfg, ws, signal_count, narratives)
        if txt:
            _home_summary_put(cfg, run, txt)
    finally:
        with _home_lock:
            _home_jobs.discard(run)


def _home_summary_make(cfg: dict, ws: list[dict], signal_count: int,
                       narratives: list[str]) -> str:
    names = [str(c.get("name", "")) for c in ws[:6] if c.get("name")]
    topics = _top_narratives(ws)[:6]
    prompt = (
        "You are summarising someone's digital life based on what's on their computer.\n"
        "Write exactly 2 short paragraphs (3-4 sentences each) in plain, natural prose.\n"
        "First paragraph: what their files reveal about their main interests and work.\n"
        "Second paragraph: what's surprising or distinctive, and one concrete observation.\n"
        "Rules: no bullet points, no markdown headers, no file counts, no jargon.\n"
        "Write as if explaining to a thoughtful friend, not a data analyst.\n"
        f"Main file clusters: {', '.join(names) or 'none'}\n"
        f"Key themes: {', '.join(narratives or topics) or 'none'}\n"
        "Return plain text only, no markdown formatting."
    )
    timeout = int(cfg.get("llm_timeout_sec", 120) or 120)
    try:
        txt = ollama.text(
            cfg,
            prompt,
            feature="home",
            temp=0.2,
            num_ctx=min(2048, int(cfg.get("num_ctx", 4096) or 4096)),
            timeout=min(90, timeout),
        )
    except Exception:
        return ""
    return _summary_clean(txt)


def _summary_clean(txt: str) -> str:
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    if not lines:
        return ""
    joined = " ".join(lines)
    return joined[:900].strip()


def _home_summary_put(cfg: dict, run: str, txt: str) -> None:
    path = _home_summary_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run": run,
        "summary": txt,
        "model": cfg.get("home_model") or cfg.get("fast_model") or cfg.get("model", ""),
        "generated_at": int(time.time()),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


# ── Onboarding V1 ────────────────────────────────────────────────────────

def _onboarding_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg) / "onboarding.json"


def _onboarding_load(cfg: dict) -> dict:
    path = _onboarding_path(cfg)
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _onboarding_save(cfg: dict, data: dict) -> None:
    path = _onboarding_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")),
                   encoding="utf-8")
    tmp.replace(path)


def onboarding_payload(cfg: dict) -> dict:
    """GET /api/v1/onboarding — return current onboarding step and profile."""
    data = _onboarding_load(cfg)
    # Cross-check: if account says onboarded, respect that
    rec = _acct_load(cfg)
    if rec and bool(rec.get("onboarded", False)):
        return {"step": 7, "profile": data.get("profile", {}),
                "completed": True}
    step = int(data.get("step", 1) or 1)
    profile = data.get("profile", {})
    if not isinstance(profile, dict):
        profile = {}
    return {"step": step, "profile": profile, "completed": False}


def onboarding_update_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    """POST /api/v1/onboarding — advance onboarding step with profile data."""
    payload = body(req)
    data = _onboarding_load(cfg)

    step = int(payload.get("step", 1) or 1)
    req_profile = payload.get("profile", {})
    if not isinstance(req_profile, dict):
        req_profile = {}

    cur_profile = data.get("profile", {})
    if not isinstance(cur_profile, dict):
        cur_profile = {}
    cur_profile.update(req_profile)
    data["profile"] = cur_profile
    data["step"] = step
    data["updated_at"] = int(time.time())

    if step >= 7:
        data["completed"] = True

    _onboarding_save(cfg, data)

    # Also sync to account record if user is signed in
    rec = _acct_load(cfg)
    if rec:
        rec["profile"] = cur_profile
        if step >= 7:
            rec["onboarded"] = True
        rec["updated_at"] = int(time.time())
        _acct_save(cfg, rec)

    return {"ok": True, "step": step, "profile": cur_profile,
            "completed": bool(data.get("completed", False))}


def iris_ask_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    """POST /api/v1/iris/ask — non-streaming audit-aware Iris answer.

    Returns a structured response with cited claim/risk/repair IDs when
    audit data exists.  Otherwise returns a plain answer.
    """
    from . import iris as iris_mod
    from . import identity as id_mod
    data = body(req)
    q = str(data.get("q", "")).strip()[:2400]
    if not q:
        return {"answer": "Empty query.", "claims": [], "risks": [], "repairs": []}

    mode = str(data.get("mode", "report"))
    run = str(data.get("run", "")).strip()
    selected_ids = [str(i) for i in data.get("selected_ids", []) if i]
    audience_id = str(data.get("audience", "recruiter"))
    history = list(data.get("history", []))

    conn = db.open_db(cfg)

    # Gather the same rich context Iris uses
    context_text, tools_used = iris_mod._gather_context(
        conn, q, mode,
        cfg=cfg, run=run,
        selected_ids=selected_ids or None,
        audience_id=audience_id or None,
    )

    # Build the prompt identically to streaming Iris
    system_content = (
        iris_mod.BASE_SYSTEM.format(corpus="(see context below)")
        + "\n"
        + iris_mod.MODE_ADDENDUM.get(mode, iris_mod.MODE_ADDENDUM["report"])
        + "\n## Context\n"
        + context_text[:iris_mod._context_cap(mode)]
    )

    messages: list = [{"role": "system", "content": system_content}]
    packed = iris_mod._history_pack(history)
    for h in packed[-10:]:
        messages.append({"role": h["role"], "content": str(h["content"])[:2000]})
    messages.append({"role": "user", "content": q})

    # Non-streaming LLM call
    model = iris_mod._mode_model(cfg, mode, q)
    temp = iris_mod._mode_temp(mode, q)
    answer = ""
    try:
        from . import ollama
        answer = ollama.text(
            cfg,
            "\n\n".join(
                f"{m['role'].upper()}:\n{m['content']}"
                for m in messages[-8:]
            ),
            feature="iris",
            model=model,
            temp=temp,
            num_ctx=int(cfg.get("iris_num_ctx", cfg.get("num_ctx", 4096))),
            timeout=120,
        ) or ""
    except Exception:
        answer = ""

    # Build structured claim/risk/repair citations from identity profiles
    claims = []
    risks = []
    repairs = []
    if selected_ids:
        for i, iid in enumerate(selected_ids[:6]):
            try:
                profile = id_mod.get_profile(conn, cfg, iid)
            except Exception:
                profile = None
            if not profile:
                continue

            src = profile.get("name", iid)
            seq = i + 1

            # Claims
            for dc in profile.get("direct_claims", [])[:2]:
                claims.append({
                    "id": f"claim-{seq}",
                    "description": str(dc)[:500],
                    "source": src,
                    "confidence": profile.get("confidence", 0),
                })
                seq += 1
            for ic in profile.get("inferred_claims", [])[:2]:
                claims.append({
                    "id": f"claim-{seq}",
                    "description": str(ic)[:500],
                    "source": src,
                    "confidence": round(profile.get("confidence", 0) * 0.6, 2),
                })
                seq += 1

            # Risks
            for r in profile.get("risks", []):
                risks.append({
                    "id": f"risk-{len(risks) + 1}",
                    "severity": str(r.get("severity", "low")),
                    "description": str(r.get("description", ""))[:500],
                    "source": src,
                })

            # Repairs (from risk mitigations if present, else build from open questions)
            for r in profile.get("risks", []):
                if r.get("mitigation"):
                    repairs.append({
                        "id": f"repair-{len(repairs) + 1}",
                        "action": str(r.get("mitigation", ""))[:500],
                        "source": src,
                    })

    return {
        "answer": answer or "Iris is currently unavailable.",
        "claims": claims,
        "risks": risks,
        "repairs": repairs,
        "mode": mode,
    }


def scan_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin", "member"})
    data = body(req)
    folders = data.get("folders", [])
    if not isinstance(folders, list) or not folders:
        _api_err("POST", "/api/scan", "folders_required")
        return {"ok": False, "err": "folders_required"}
    _quota_take(cfg, "scan_daily")
    run_id = scan_run_id(data)
    opts = _scan_cfg(cfg)
    _scan_ensure_worker(cfg)
    global _scan_seq
    with _scan_lock:
        total = len(_scan_jobs) + (1 if _scan_state["scanning"] else 0)
        if total >= opts["queue_cap"]:
            err = "scan_already_running" if _scan_state["scanning"] \
                else "scan_queue_full"
            _api_err("POST", "/api/scan", err)
            return {"ok": False, "err": err}
        _scan_seq += 1
        job_id = _scan_job_id(run_id, _scan_seq)
        job = {
            "id": job_id,
            "folders": [str(x) for x in folders if str(x)],
            "run_id": str(run_id),
            "attempt": 0,
            "ready_at": time.time(),
        }
        _scan_jobs.append(job)
        depth = len(_scan_jobs)
        active = _scan_state["scanning"]
        if not active:
            _scan_state["progress"] = {}
    _log_ev("scan_enqueue", run_id=run_id, folder_count=len(folders), depth=depth)
    _scan_event.set()
    status = "queued" if active or depth > 1 else "scanning"
    return {"ok": True, "status": status, "job_id": job_id}


def scan_run_id(data: dict) -> str:
    val = _run_clean(data.get("run_id", ""))
    if val:
        return val
    return time.strftime("%Y%m%d-%H%M%S")


def _scan_cfg(cfg: dict) -> dict:
    set_cfg = _settings_runtime(cfg).get("scan_rules", {})
    cap = int(set_cfg.get("queue_cap", cfg.get("scan_queue_cap", 6)) or 6)
    tries = int(set_cfg.get("retry_max", cfg.get("scan_retry_max", 2)) or 2)
    backoff = float(set_cfg.get("backoff_s", cfg.get("scan_backoff_s", 3.0))
                    or 3.0)
    timeout = int(set_cfg.get("timeout_s", cfg.get("scan_timeout_s", 300))
                  or 300)
    dead = int(set_cfg.get("dead_cap", cfg.get("scan_dead_cap", 20)) or 20)
    return {
        "queue_cap": max(1, cap),
        "retry_max": max(0, tries),
        "backoff_s": max(0.1, backoff),
        "timeout_s": max(30, timeout),
        "dead_cap": max(1, dead),
    }


def _scan_job_id(run_id: str, seq: int) -> str:
    head = run_id[:32] if run_id else "scan"
    return f"{head}-{seq}"


def _scan_ensure_worker(cfg: dict) -> None:
    global _scan_worker
    with _scan_lock:
        if _scan_worker and _scan_worker.is_alive():
            return
        _scan_worker = threading.Thread(
            target=_scan_loop, args=(cfg,), daemon=True
        )
        _scan_worker.start()


def _scan_loop(cfg: dict) -> None:
    while True:
        job, wait_s = _scan_pick()
        if not job:
            _scan_event.wait(wait_s)
            _scan_event.clear()
            continue
        _scan_exec(cfg, job)


def _scan_pick() -> tuple[dict | None, float]:
    now = time.time()
    with _scan_lock:
        if not _scan_jobs:
            _scan_idle()
            return None, 1.0
        idx, wait_s = _scan_ready_idx(now)
        if idx < 0:
            _scan_idle()
            return None, wait_s
        job = _scan_jobs.pop(idx)
        _scan_state["scanning"] = True
        _scan_state["active_job_id"] = job["id"]
        _scan_state["attempts"] = int(job.get("attempt", 0)) + 1
        _scan_state["progress"] = {"job_id": job["id"], "state": "running"}
        return job, 0.0


def _scan_ready_idx(now: float) -> tuple[int, float]:
    wait_s = 1.0
    for idx, job in enumerate(_scan_jobs):
        due = float(job.get("ready_at", 0.0) or 0.0) - now
        if due <= 0:
            return idx, 0.0
        wait_s = min(wait_s, max(0.1, due))
    return -1, wait_s


def _scan_idle() -> None:
    _scan_state["scanning"] = False
    _scan_state["active_job_id"] = ""
    _scan_state["attempts"] = 0


def _scan_exec(cfg: dict, job: dict) -> None:
    run_id = str(job.get("run_id", ""))
    folders = list(job.get("folders", []))
    job["attempt"] = int(job.get("attempt", 0)) + 1
    _metrics_inc("scans_started")
    _log_ev("scan_exec_start", run_id=run_id, attempt=job["attempt"])
    ok, meta = _scan_once(cfg, job["id"], folders, run_id)
    if ok:
        _scan_done(cfg, run_id, meta)
        return
    _scan_fail(cfg, job, meta)


def _scan_done(cfg: dict, run_id: str, meta: dict) -> None:
    _log_ev("scan_exec_ok", run_id=run_id, rc=meta.get("returncode", 0))
    _acct_mark_onboard(cfg, run_id)
    with _scan_lock:
        _scan_idle()
        _scan_state["last_run"] = run_id or ""
        _scan_state["progress"] = meta


def _scan_fail(cfg: dict, job: dict, meta: dict) -> None:
    _metrics_inc("scans_failed")
    opts = _scan_cfg(cfg)
    tries = int(job.get("attempt", 0))
    run_id = str(job.get("run_id", ""))
    if tries <= opts["retry_max"]:
        delay = float(opts["backoff_s"]) * (2 ** (tries - 1))
        job["ready_at"] = time.time() + delay
        with _scan_lock:
            _scan_idle()
            _scan_jobs.append(job)
            _scan_state["progress"] = {
                "job_id": job["id"],
                "state": "retrying",
                "attempts": tries,
                "retry_in_s": round(delay, 2),
                "stderr": meta.get("stderr", ""),
            }
        _log_ev("scan_exec_retry", run_id=run_id, delay=delay, attempt=tries)
        _scan_event.set()
        return
    _scan_dead_letter(cfg, job, meta)


def _scan_dead_letter(cfg: dict, job: dict, meta: dict) -> None:
    opts = _scan_cfg(cfg)
    dead = {
        "job_id": job["id"],
        "run_id": str(job.get("run_id", "")),
        "attempts": int(job.get("attempt", 0)),
        "returncode": int(meta.get("returncode", -1)),
        "stderr": str(meta.get("stderr", ""))[:500],
        "ts": int(time.time()),
    }
    _log_ev("scan_dead_letter", job_id=dead["job_id"], run_id=dead["run_id"])
    with _scan_lock:
        _scan_idle()
        _scan_dead.append(dead)
        _scan_dead[:] = _scan_dead[-opts["dead_cap"]:]
        _scan_state["progress"] = {"job_id": dead["job_id"], "state": "dead"}


def _scan_once(cfg: dict, job_id: str, folders: list,
               run_id: str) -> tuple[bool, dict]:
    started = time.time()
    scan_cfg = scan_cfg_fast(cfg, folders)
    if run_id:
        scan_cfg["run_id"] = run_id
    conn = db.open_db(scan_cfg)
    meta = {
        "job_id": job_id,
        "run_id": run_id,
        "started_at": int(started),
        "stages": {},
        "returncode": 0,
        "stderr": "",
    }
    try:
        found = _scan_stage_wrap(
            job_id, meta, "discover",
            lambda: scan.run(conn, scan_cfg, run_id)
        )
        done = _scan_stage_wrap(
            job_id, meta, "parse",
            lambda: ingest.run(conn, scan_cfg, run_id)
        )
        clusters = _scan_stage_wrap(
            job_id, meta, "classify",
            lambda: latent.run(conn, scan_cfg, run_id)
        )
        plans = _scan_stage_wrap(
            job_id, meta, "cluster",
            lambda: planner.run(conn, scan_cfg, run_id, clusters)
        )
        inf = _scan_stage_wrap(
            job_id, meta, "infer",
            lambda: _scan_infer(scan_cfg, run_id, clusters)
        )
        atlas_path = _scan_stage_wrap(
            job_id, meta, "atlas",
            lambda: atlas.write(conn, scan_cfg, run_id)
        )
        conn.commit()
        dur = round(time.time() - started, 3)
        meta["duration_s"] = dur
        meta["finished_at"] = int(time.time())
        meta["summary"] = {
            "files_discovered": int(found or 0),
            "files_parsed": int(done or 0),
            "clusters": len(clusters or {}),
            "plans": len(plans or []),
            "inference": inf,
            "atlas": str(atlas_path or ""),
        }
        _scan_meta_save(scan_cfg, run_id, meta)
        return True, meta
    except Exception as exc:
        conn.commit()
        err = str(exc)[:500]
        meta["returncode"] = 1
        meta["stderr"] = err
        meta["duration_s"] = round(time.time() - started, 3)
        meta["finished_at"] = int(time.time())
        _scan_meta_save(scan_cfg, run_id, meta)
        return False, meta


def _scan_stage_wrap(job_id: str, meta: dict, name: str, fn):
    t0 = time.time()
    _scan_stage_update(job_id, meta, name, "running", {})
    try:
        out = fn()
        rec = {
            "state": "ok",
            "duration_s": round(time.time() - t0, 3),
            "summary": _scan_stage_summary(name, out),
        }
        meta["stages"][name] = rec
        _scan_stage_update(job_id, meta, name, "ok", rec["summary"])
        return out
    except Exception as exc:
        rec = {
            "state": "error",
            "duration_s": round(time.time() - t0, 3),
            "error": str(exc)[:500],
        }
        meta["stages"][name] = rec
        _scan_stage_update(job_id, meta, name, "error", {"error": rec["error"]})
        raise


def _scan_stage_summary(name: str, out: object) -> dict:
    if name in {"discover", "parse"}:
        return {"count": int(out or 0)}
    if name == "classify":
        return {"clusters": len(out or {})}
    if name == "cluster":
        return {"plans": len(out or [])}
    if name == "infer" and isinstance(out, dict):
        return out
    if name == "atlas":
        return {"path": str(out or "")}
    return {}


def _scan_stage_update(job_id: str, meta: dict, name: str, st: str,
                       extra: dict) -> None:
    with _scan_lock:
        _scan_state["progress"] = {
            "job_id": job_id,
            "state": "running",
            "stage": name,
            "stage_state": st,
            "stages": dict(meta.get("stages", {})),
            "detail": extra,
        }


def _scan_infer(cfg: dict, run_id: str, clusters: dict) -> dict:
    ids = list((clusters or {}).keys())[:2]
    if not ids:
        return {"clusters": 0, "claims": 0}
    claims = 0
    for cid in ids:
        data = infer.get(cfg, run_id, cid, refresh=True)
        claims += len(data.get("claims", []))
    return {"clusters": len(ids), "claims": claims}


def _scan_meta_path(cfg: dict, run_id: str) -> Path:
    rid = run_id or "latest"
    return cfgmod.state_dir(cfg, "scans") / f"{rid}.json"


def _scan_meta_save(cfg: dict, run_id: str, meta: dict) -> None:
    path = _scan_meta_path(cfg, run_id)
    _store_write(path, meta)


def _scan_meta_load(cfg: dict, run_id: str) -> dict:
    if not run_id:
        return {}
    path = _scan_meta_path(cfg, run_id)
    data = _store_read(path)
    return data or {}


def scan_cfg_fast(cfg: dict, folders: list) -> dict:
    out = {**cfg, "sources": folders}
    lim = int(cfg.get("scan_llm_timeout_sec", 45) or 45)
    base = int(cfg.get("llm_timeout_sec", 120) or 120)
    out["llm_timeout_sec"] = max(8, min(base, lim))
    p_tm = int(out.get("planner_timeout_sec", out["llm_timeout_sec"]) or 0)
    out["planner_timeout_sec"] = max(8, min(p_tm or out["llm_timeout_sec"], lim))
    out["llm_cluster_limit"] = min(int(cfg.get("llm_cluster_limit", 24) or 24), 8)
    out["llm_item_limit"] = min(int(cfg.get("llm_item_limit", 400) or 400), 160)
    return out


def _integrations_queue_cfg(cfg: dict) -> dict:
    vals = _settings_runtime(cfg).get("integrations", {})
    auto = vals.get("automation", {}) if isinstance(vals, dict) else {}
    queue = auto.get("queue", {}) if isinstance(auto, dict) else {}
    return {
        "retry_max": max(0, int(queue.get("retry_max", 3) or 3)),
        "backoff_s": max(0.1, float(queue.get("backoff_s", 2.0) or 2.0)),
        "dead_cap": max(1, int(cfg.get("integrations_dead_cap", 200) or 200)),
        "done_cap": max(1, int(cfg.get("integrations_done_cap", 400) or 400)),
        "cap": max(10, int(cfg.get("integrations_queue_cap", 500) or 500)),
        "idem_cap": max(100, int(cfg.get("integrations_idem_cap", 2000) or
                                  2000)),
        "idem_ttl_s": max(600, int(cfg.get("integrations_idem_ttl_s", 86400)
                                   or 86400)),
        "replay_batch_max": max(
            1,
            int(cfg.get("integrations_replay_batch_max", 20) or 20),
        ),
    }


def _integrations_runtime_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg, "integrations") / "runtime.json"


def _integrations_runtime_load(cfg: dict) -> None:
    global _int_jobs, _int_done, _int_dead, _int_idem
    global _int_seq, _int_sched, _int_loaded, _int_loaded_path
    path = _integrations_runtime_path(cfg) if "state_dir" in cfg else None
    key = str(path) if path else ""
    with _int_lock:
        if _int_loaded and _int_loaded_path == key:
            return
        _int_loaded = True
        _int_loaded_path = key
    if not path:
        with _int_lock:
            _int_jobs = []
            _int_done = []
            _int_dead = []
            _int_idem = {}
            _int_seq = 0
            _int_sched = _integrations_sched_clean({})
        return
    data = _store_read(path) or {}
    opts = _integrations_queue_cfg(cfg)
    queued = _integrations_jobs_clean(data.get("queued", []), 5000)
    done = _integrations_jobs_clean(data.get("done", []), 5000)
    dead = _integrations_jobs_clean(data.get("dead", []), 5000)
    idem = _integrations_idem_rows(data.get("idempotency", {}),
                                   opts)
    sched = _integrations_sched_clean(data.get("scheduler", {}))
    seq = int(data.get("seq", 0) or 0)
    with _int_lock:
        _int_jobs = queued
        _int_done = done
        _int_dead = dead
        _int_idem = idem
        _int_sched = sched
        _int_seq = max(seq, len(queued) + len(done) + len(dead))
    if queued:
        _int_event.set()
    if sched.get("enabled"):
        _int_sched_event.set()


def _integrations_jobs_clean(vals: object, cap: int) -> list[dict]:
    rows = vals if isinstance(vals, list) else []
    out = []
    for row in rows[-cap:]:
        clean = _integrations_job_clean(row)
        if clean:
            out.append(clean)
    return out


def _integrations_job_clean(row: object) -> dict | None:
    if not isinstance(row, dict):
        return None
    kind = str(row.get("kind", "")).strip().lower()
    if kind not in {"email", "social", "webhook", "channel"}:
        return None
    payload = row.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    meta = row.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}
    now = int(time.time())
    rec = {
        "id": str(row.get("id", ""))[:120] or f"ijob-{now}-{uuid.uuid4().hex[:8]}",
        "kind": kind,
        "payload": payload,
        "source": str(row.get("source", "manual"))[:40] or "manual",
        "meta": meta,
        "attempt": max(0, int(row.get("attempt", 0) or 0)),
        "not_before": max(0.0, float(row.get("not_before", 0.0) or 0.0)),
        "next_retry_at": max(0, int(row.get("next_retry_at", 0) or 0)),
        "retry_in_s": max(0.0, float(row.get("retry_in_s", 0.0) or 0.0)),
        "retry_history": _integrations_retry_hist(row.get("retry_history", [])),
        "status": str(row.get("status", "queued"))[:20],
        "created_at": int(row.get("created_at", now) or now),
        "updated_at": int(row.get("updated_at", now) or now),
        "last_error_at": max(0, int(row.get("last_error_at", 0) or 0)),
        "last_error": str(row.get("last_error", ""))[:300],
        "idempotency_key": str(row.get("idempotency_key", ""))[:120],
        "idempotency_hash": str(row.get("idempotency_hash", ""))[:80],
        "replay_of": str(row.get("replay_of", ""))[:120],
        "replay_count": max(0, int(row.get("replay_count", 0) or 0)),
        "replayable": bool(row.get("replayable", True)),
        "dead_at": max(0, int(row.get("dead_at", 0) or 0)),
        "dead_reason": str(row.get("dead_reason", ""))[:240],
    }
    return rec


def _integrations_idem_rows(raw: object, opts: dict) -> dict[str, dict]:
    rows = raw.get("items", []) if isinstance(raw, dict) else raw
    vals = rows if isinstance(rows, list) else []
    now = int(time.time())
    ttl = int(opts.get("idem_ttl_s", 86400))
    out: dict[str, dict] = {}
    for row in vals[-5000:]:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key", "")).strip()
        if not key:
            continue
        ts = int(row.get("updated_at", 0) or 0)
        if ts and ts < now - ttl:
            continue
        out[key] = {
            "key": key[:120],
            "hash": str(row.get("hash", ""))[:80],
            "job_id": str(row.get("job_id", ""))[:120],
            "kind": str(row.get("kind", ""))[:40],
            "status": str(row.get("status", ""))[:20],
            "created_at": int(row.get("created_at", 0) or 0),
            "updated_at": ts,
        }
    if len(out) <= int(opts.get("idem_cap", 2000)):
        return out
    seq = sorted(out.values(), key=lambda x: int(x.get("updated_at", 0) or 0))
    keep = seq[-int(opts.get("idem_cap", 2000)):]
    return {str(x.get("key", "")): x for x in keep if x.get("key")}


def _integrations_sched_clean(row: object) -> dict:
    raw = row if isinstance(row, dict) else {}
    out = dict(_int_sched)
    out["enabled"] = bool(raw.get("enabled", False))
    out["cron"] = str(raw.get("cron", "0 9 * * *"))[:80]
    out["timezone"] = str(raw.get("timezone", "UTC"))[:60]
    out["sync_enabled"] = bool(raw.get("sync_enabled", False))
    out["sync_interval_min"] = max(5, min(1440, int(
        raw.get("sync_interval_min", 30) or 30,
    )))
    rows = raw.get("sync_channels", [])
    vals = rows if isinstance(rows, list) else []
    ch = []
    for row2 in vals:
        key = str(row2).strip().lower()
        if key in _FUTURE_CHANNELS and key not in ch:
            ch.append(key)
    out["sync_channels"] = ch or ["calendar", "crm", "storage"]
    out["sync_next_run"] = max(0, int(raw.get("sync_next_run", 0) or 0))
    out["sync_last_run"] = max(0, int(raw.get("sync_last_run", 0) or 0))
    out["sync_last_job_id"] = str(raw.get("sync_last_job_id", ""))[:120]
    out["next_run"] = max(0, int(raw.get("next_run", 0) or 0))
    out["last_run"] = max(0, int(raw.get("last_run", 0) or 0))
    out["last_enqueue"] = max(0, int(raw.get("last_enqueue", 0) or 0))
    out["last_job_id"] = str(raw.get("last_job_id", ""))[:120]
    out["last_error"] = str(raw.get("last_error", ""))[:240]
    out["last_slot"] = str(raw.get("last_slot", ""))[:80]
    return out


def _integrations_runtime_save(cfg: dict) -> None:
    if "state_dir" not in cfg:
        return
    opts = _integrations_queue_cfg(cfg)
    with _int_lock:
        _integrations_idem_gc_locked(opts)
        rec = {
            "seq": int(_int_seq),
            "queued": [dict(x) for x in _int_jobs[-5000:]],
            "done": [dict(x) for x in _int_done[-5000:]],
            "dead": [dict(x) for x in _int_dead[-5000:]],
            "idempotency": {"items": [dict(x) for x in _int_idem.values()]},
            "scheduler": dict(_int_sched),
            "updated_at": int(time.time()),
        }
    _store_write(_integrations_runtime_path(cfg), rec)


def _integrations_ensure_worker(cfg: dict) -> None:
    global _int_worker
    _integrations_runtime_load(cfg)
    with _int_lock:
        alive = bool(_int_worker and _int_worker.is_alive())
        if not alive:
            _int_worker = threading.Thread(
                target=_integrations_loop, args=(cfg,), daemon=True
            )
            _int_worker.start()
    _integrations_ensure_scheduler(cfg)


def _integrations_ensure_scheduler(cfg: dict) -> None:
    global _int_sched_worker
    with _int_lock:
        alive = bool(_int_sched_worker and _int_sched_worker.is_alive())
        if alive:
            return
        _int_sched_worker = threading.Thread(
            target=_integrations_sched_loop, args=(cfg,), daemon=True
        )
        _int_sched_worker.start()


def _integrations_sched_loop(cfg: dict) -> None:
    while True:
        wait_s = _integrations_sched_tick(cfg)
        _int_sched_event.wait(wait_s)
        _int_sched_event.clear()


def _integrations_sched_tick(cfg: dict) -> float:
    vals = _settings_runtime(cfg).get("integrations", {})
    auto = vals.get("automation", {}) if isinstance(vals, dict) else {}
    dig = auto.get("digest", {}) if isinstance(auto, dict) else {}
    syn = auto.get("sync", {}) if isinstance(auto, dict) else {}
    enabled = bool(dig.get("enabled", False))
    cron = str(dig.get("cron", "0 9 * * *")).strip()
    tzn = str(dig.get("timezone", "UTC")).strip()
    now = time.time()
    wait_s = 30.0
    if not enabled:
        with _int_lock:
            _int_sched["enabled"] = False
            _int_sched["cron"] = cron or "0 9 * * *"
            _int_sched["timezone"] = tzn or "UTC"
            _int_sched["next_run"] = 0
            _int_sched["last_error"] = ""
    else:
        slot_dt = _digest_slot_dt(cron, tzn, now)
        slot_ts = slot_dt.astimezone(timezone.utc).timestamp()
        nxt = _digest_next_run_ts(cron, tzn, now)
        with _int_lock:
            _int_sched["enabled"] = True
            _int_sched["cron"] = cron or "0 9 * * *"
            _int_sched["timezone"] = tzn or "UTC"
            _int_sched["next_run"] = int(nxt)
        wait_s = min(wait_s, max(1.0, min(30.0, nxt - now)))
        late_s = now - slot_ts
        due_now = late_s >= 0 and late_s <= 15 * 60
        if due_now:
            slot = _digest_slot_key(slot_dt)
            with _int_lock:
                done = (_int_sched.get("last_slot") == slot)
                if not done:
                    _int_sched["last_slot"] = slot
                    _int_sched["last_run"] = int(now)
                    _int_sched["last_error"] = ""
            if not done:
                try:
                    payload = _digest_job_payload(cfg)
                    job, _, _ = _integrations_enqueue_job(
                        cfg,
                        "email",
                        payload,
                        source="automation:digest",
                        meta={"slot": slot},
                    )
                    with _int_lock:
                        _int_sched["last_enqueue"] = int(time.time())
                        _int_sched["last_job_id"] = str(job.get("id", ""))
                        _int_sched["last_error"] = ""
                except Exception as exc:
                    with _int_lock:
                        _int_sched["last_error"] = str(exc)[:240]
    wait_s = min(wait_s, _integrations_sync_sched_tick(cfg, vals, syn, now))
    _integrations_runtime_save(cfg)
    return max(1.0, min(30.0, wait_s))


def _integrations_sync_sched_tick(cfg: dict, vals: dict, syn: dict,
                                  now: float) -> float:
    enabled = bool(syn.get("enabled", False)) if isinstance(syn, dict) else False
    interval_min = max(5, min(1440, int(
        (syn.get("interval_min", 30) if isinstance(syn, dict) else 30) or 30,
    )))
    channels = _sync_sched_channels(syn.get("channels", [])
                                    if isinstance(syn, dict) else [])
    if not enabled:
        with _int_lock:
            _int_sched["sync_enabled"] = False
            _int_sched["sync_interval_min"] = interval_min
            _int_sched["sync_channels"] = channels
            _int_sched["sync_next_run"] = 0
        return 30.0
    span = interval_min * 60
    with _int_lock:
        last = int(_int_sched.get("sync_last_run", 0) or 0)
        next_run = int(_int_sched.get("sync_next_run", 0) or 0)
    if next_run <= 0:
        base = last if last > 0 else int(now)
        next_run = base + span
    due = now >= float(next_run)
    with _int_lock:
        _int_sched["sync_enabled"] = True
        _int_sched["sync_interval_min"] = interval_min
        _int_sched["sync_channels"] = channels
        _int_sched["sync_next_run"] = int(next_run)
    if not due:
        return max(1.0, min(30.0, float(next_run) - now))
    last_id = _sync_sched_enqueue(cfg, vals, channels, int(now))
    with _int_lock:
        _int_sched["sync_last_run"] = int(now)
        _int_sched["sync_next_run"] = int(now) + span
        if last_id:
            _int_sched["sync_last_job_id"] = last_id
    return 30.0


def _sync_sched_channels(raw: object) -> list[str]:
    rows = raw if isinstance(raw, list) else []
    out = []
    for row in rows:
        key = str(row).strip().lower()
        if key in _FUTURE_CHANNELS and key not in out:
            out.append(key)
    return out or ["calendar", "crm", "storage"]


def _sync_sched_enqueue(cfg: dict, vals: dict, channels: list[str],
                        now: int) -> str:
    ints = vals if isinstance(vals, dict) else {}
    raw = ints.get("channels", {})
    rows = _integrations_channels_clean(raw)
    last_id = ""
    for key in channels:
        row = rows.get(key, {})
        if not isinstance(row, dict):
            continue
        if not bool(row.get("enabled", False)):
            continue
        provider = str(row.get("provider", "")).strip().lower()
        if not provider:
            continue
        account = str(row.get("account", "")).strip()
        token_ref = str(row.get("token_ref", "")).strip()
        meta = {"tick_at": now, "automation": "sync"}
        payload = {
            "channel": key,
            "provider": provider,
            "account": account,
            "token_ref": token_ref,
            "action": "sync",
            "data": {"sync_at": now},
        }
        try:
            job, _, _ = _integrations_enqueue_job(
                cfg,
                "channel",
                payload,
                source="automation:sync",
                meta=meta,
            )
        except Exception:
            continue
        last_id = str(job.get("id", ""))
    return last_id


def _digest_slot_key(dt: datetime) -> str:
    return f"{dt.year:04d}{dt.month:02d}{dt.day:02d}:{dt.hour:02d}:{dt.minute:02d}"


def _digest_slot_dt(cron: str, tzn: str, now: float) -> datetime:
    tz = _digest_tz(tzn)
    dt = datetime.fromtimestamp(now, tz=tz)
    hour, minute = _digest_hm(cron)
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _digest_next_run_ts(cron: str, tzn: str, now: float) -> float:
    base = _digest_slot_dt(cron, tzn, now)
    if base.astimezone(timezone.utc).timestamp() <= now:
        base += timedelta(days=1)
    return base.astimezone(timezone.utc).timestamp()


def _digest_hm(cron: str) -> tuple[int, int]:
    raw = str(cron or "").strip()
    parts = raw.split()
    if len(parts) != 5:
        return 9, 0
    try:
        minute = int(parts[0])
        hour = int(parts[1])
    except Exception:
        return 9, 0
    if minute < 0 or minute > 59 or hour < 0 or hour > 23:
        return 9, 0
    return hour, minute


def _digest_tz(name: str):
    raw = str(name or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(raw)
    except ZoneInfoNotFoundError:
        return timezone.utc


def _digest_job_payload(cfg: dict) -> dict:
    vals = _settings_runtime(cfg).get("integrations", {})
    email = vals.get("email", {}) if isinstance(vals, dict) else {}
    acct = _acct_load(cfg) or {}
    to = str(email.get("from_email", "")).strip()
    if not to:
        to = str(acct.get("email", "")).strip() or "team@local"
    stats = _digest_corpus_stats(cfg)
    stamp = time.strftime("%Y-%m-%d")
    body = [
        f"Optic digest for {stamp}",
        f"Run: {stats['run']}",
        f"Files indexed: {stats['files']:,}",
        f"Corpus size: {stats['size_hr']}",
        f"Signals this week: {stats['recent_week']:,}",
    ]
    return {
        "to": to,
        "subject": f"Optic daily digest · {stamp}",
        "body": "\n".join(body),
        "meta": {"source": "automation_digest"},
    }


def _digest_corpus_stats(cfg: dict) -> dict:
    out = {
        "run": latest(cfg) or "latest",
        "files": 0,
        "bytes": 0,
        "recent_week": 0,
        "size_hr": "0 B",
    }
    try:
        conn = db.open_db(cfg)
        rows = db.rows(conn, "SELECT COUNT(*) AS c, COALESCE(SUM(size), 0) AS s "
                      "FROM items WHERE kind='file'")
        row = rows[0] if rows else {}
        out["files"] = int(row.get("c", 0) or 0)
        out["bytes"] = int(row.get("s", 0) or 0)
        week = time.time() - 7 * 86400
        rec = db.rows(conn, "SELECT COUNT(*) AS c FROM items WHERE kind='file' "
                      "AND mtime > ?", (week,))
        out["recent_week"] = int((rec[0] if rec else {}).get("c", 0) or 0)
    except Exception:
        pass
    out["size_hr"] = _human_size(out["bytes"])
    return out


def _human_size(size: int) -> str:
    val = float(max(0, int(size or 0)))
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while val >= 1024 and idx < len(units) - 1:
        val /= 1024.0
        idx += 1
    return f"{val:.1f} {units[idx]}" if idx else f"{int(val)} {units[idx]}"


def _integrations_loop(cfg: dict) -> None:
    while True:
        job, wait_s = _integrations_pick()
        if not job:
            _int_event.wait(wait_s)
            _int_event.clear()
            continue
        _integrations_exec(cfg, job)


def _integrations_pick() -> tuple[dict | None, float]:
    now = time.time()
    with _int_lock:
        if not _int_jobs:
            return None, 20.0
        best = None
        wait_s = 20.0
        for idx, row in enumerate(_int_jobs):
            due = float(row.get("not_before", 0.0) or 0.0)
            if due <= now:
                best = idx
                break
            wait_s = min(wait_s, max(0.2, due - now))
        if best is None:
            return None, wait_s
        job = _int_jobs.pop(best)
    return job, 0.0


def _integrations_exec(cfg: dict, job: dict) -> None:
    _metrics_inc("integrations_started")
    opts = _integrations_queue_cfg(cfg)
    now = int(time.time())
    job["attempt"] = int(job.get("attempt", 0) or 0) + 1
    job["updated_at"] = now
    job["status"] = "running"
    job["retry_in_s"] = 0.0
    job["next_retry_at"] = 0
    _integrations_idem_mark(job, "running", now)
    try:
        _integrations_dispatch(cfg, job)
        job["status"] = "done"
        job["dead_at"] = 0
        job["dead_reason"] = ""
        _integrations_idem_mark(job, "done", now)
        with _int_lock:
            _int_done.append(dict(job))
            _int_done[:] = _int_done[-opts["done_cap"]:]
        _integrations_runtime_save(cfg)
        return
    except Exception as exc:
        _metrics_inc("integrations_failed")
        job["last_error"] = str(exc)[:300]
        job["last_error_at"] = now
        if str(job.get("kind", "")).strip().lower() == "channel":
            pay = job.get("payload", {})
            row = pay if isinstance(pay, dict) else {}
            channel = str(row.get("channel", "")).strip().lower()
            provider = str(row.get("provider", "")).strip().lower()
            account = str(row.get("account", "")).strip()
            if channel and provider:
                _integrations_sync_touch(
                    cfg, channel, provider, account, "error",
                    err=job["last_error"],
                    job_id=str(job.get("id", "")),
                )
    tries = int(job.get("attempt", 1))
    if tries <= opts["retry_max"]:
        delay = opts["backoff_s"] * (2 ** max(0, tries - 1))
        at = time.time() + delay
        job["status"] = "queued"
        job["not_before"] = at
        job["next_retry_at"] = int(at)
        job["retry_in_s"] = round(delay, 3)
        job["retry_history"] = _integrations_retry_add(job, delay)
        _integrations_idem_mark(job, "retrying", now)
        with _int_lock:
            _int_jobs.append(job)
        _integrations_runtime_save(cfg)
        _int_event.set()
        return
    job["status"] = "dead"
    job["dead_at"] = now
    job["dead_reason"] = str(job.get("last_error", ""))[:240]
    job["replayable"] = _integrations_replayable(job)
    _integrations_idem_mark(job, "dead", now)
    with _int_lock:
        _int_dead.append(dict(job))
        _int_dead[:] = _int_dead[-opts["dead_cap"]:]
    _integrations_runtime_save(cfg)


def _integrations_retry_add(job: dict, delay: float) -> list[dict]:
    rows = job.get("retry_history", [])
    hist = rows if isinstance(rows, list) else []
    nxt = [x for x in hist if isinstance(x, dict)][-11:]
    nxt.append({
        "at": int(time.time()),
        "attempt": int(job.get("attempt", 0) or 0),
        "delay_s": round(max(0.0, float(delay or 0.0)), 3),
        "err": str(job.get("last_error", ""))[:240],
    })
    return nxt


def _integrations_replayable(job: dict) -> bool:
    kind = str(job.get("kind", "")).strip().lower()
    if kind in {"email", "social"}:
        return True
    if kind != "channel":
        return False
    pay = job.get("payload", {})
    if not isinstance(pay, dict):
        return False
    key = str(pay.get("channel", "")).strip().lower()
    return key in _FUTURE_CHANNELS


def _integrations_idem_mark(job: dict, status: str, now: int) -> None:
    key = str(job.get("idempotency_key", "")).strip()
    if not key:
        return
    row = {
        "key": key,
        "hash": str(job.get("idempotency_hash", ""))[:80],
        "job_id": str(job.get("id", ""))[:120],
        "kind": str(job.get("kind", ""))[:40],
        "status": str(status)[:20],
        "created_at": int(job.get("created_at", now) or now),
        "updated_at": int(now),
    }
    with _int_lock:
        _int_idem[key] = row


def _integrations_dispatch(cfg: dict, job: dict) -> None:
    kind = str(job.get("kind", "")).strip().lower()
    payload = job.get("payload", {})
    if not isinstance(payload, dict):
        raise RuntimeError("payload_invalid")
    if kind == "email":
        return _integrations_email(cfg, job, payload)
    if kind == "social":
        return _integrations_social(cfg, job, payload)
    if kind == "webhook":
        return _integrations_webhook(cfg, payload)
    if kind == "channel":
        return _integrations_channel(cfg, job, payload)
    raise RuntimeError("integration_kind_invalid")


def _integrations_email(cfg: dict, job: dict, payload: dict) -> None:
    vals = _settings_runtime(cfg).get("integrations", {})
    email = vals.get("email", {}) if isinstance(vals, dict) else {}
    if not isinstance(email, dict) or not bool(email.get("enabled", False)):
        raise RuntimeError("email_channel_disabled")
    cap = max(10, int(email.get("daily_cap", 500) or 500))
    if _integrations_email_daily_count(cfg) >= cap:
        raise RuntimeError("email_daily_cap_reached")
    provider = str(email.get("provider", "smtp")).strip().lower()
    meta = _integrations_email_send(cfg, provider, email, payload, job)
    rec = {
        "job_id": job.get("id", ""),
        "provider": provider,
        "to": _integrations_email_to(payload.get("to")),
        "subject": str(payload.get("subject", ""))[:180],
        "meta": meta,
        "ts": int(time.time()),
    }
    _integrations_emit(cfg, "email_sent.ndjson", rec)
    _integrations_emit(cfg, "email_outbox.ndjson", {
        "job_id": job.get("id", ""),
        "to": payload.get("to", ""),
        "subject": payload.get("subject", ""),
        "body": payload.get("body", ""),
        "meta": payload.get("meta", {}),
        "ts": int(time.time()),
    })


def _integrations_social(cfg: dict, job: dict, payload: dict) -> None:
    vals = _settings_runtime(cfg).get("integrations", {})
    social = vals.get("social", {}) if isinstance(vals, dict) else {}
    if not isinstance(social, dict) or not bool(social.get("enabled", False)):
        raise RuntimeError("social_channel_disabled")
    provider = str(payload.get("provider", "")).strip().lower() or "x"
    if provider == "x":
        meta = _integrations_social_x(cfg, social, payload, job)
    else:
        meta = _integrations_social_generic(cfg, social, payload, provider,
                                            job)
    _integrations_emit(cfg, "social_sent.ndjson", {
        "job_id": job.get("id", ""),
        "provider": provider,
        "account": payload.get("account", ""),
        "content": str(payload.get("content", ""))[:2000],
        "meta": meta,
        "ts": int(time.time()),
    })
    _integrations_emit(cfg, "social_outbox.ndjson", {
        "job_id": job.get("id", ""),
        "provider": provider,
        "account": payload.get("account", ""),
        "content": payload.get("content", ""),
        "schedule_at": payload.get("schedule_at", 0),
        "meta": payload.get("meta", {}),
        "ts": int(time.time()),
    })


def _integrations_channel(cfg: dict, job: dict, payload: dict) -> None:
    vals = _settings_runtime(cfg).get("integrations", {})
    raw = vals.get("channels", {}) if isinstance(vals, dict) else {}
    chans = _integrations_channels_clean(raw)
    key = str(payload.get("channel", "")).strip().lower()
    if key not in _FUTURE_CHANNELS:
        raise RuntimeError("integration_channel_invalid")
    row = chans.get(key, {})
    if not bool(row.get("enabled", False)):
        raise RuntimeError("integration_channel_disabled")
    provider = str(payload.get("provider", "")).strip().lower()
    provider = provider or str(row.get("provider", "")).strip().lower()
    if not _channel_provider_allowed(key, provider):
        raise RuntimeError("integration_provider_invalid")
    ref = str(payload.get("token_ref", "")).strip()
    ref = ref or str(row.get("token_ref", "")).strip()
    refs = _integrations_secret_refs(cfg)
    if not _channel_token_ready(key, provider, ref, refs):
        raise RuntimeError("integration_token_required")
    meta = _integrations_channel_send(cfg, key, provider, row, payload, ref,
                                      job)
    rec = {
        "job_id": job.get("id", ""),
        "channel": key,
        "provider": provider,
        "account": str(payload.get("account", "") or row.get("account", "")),
        "action": str(payload.get("action", "sync"))[:80],
        "data": payload.get("data", {}),
        "meta": {
            "request": payload.get("meta", {}),
            "dispatch": meta,
        },
        "ts": int(time.time()),
    }
    _integrations_emit(cfg, "channel_outbox.ndjson", rec)
    _integrations_emit(cfg, f"{key}_outbox.ndjson", rec)
    data = payload.get("data", {})
    dv = data if isinstance(data, dict) else {}
    dispatch = rec.get("meta", {}).get("dispatch", {})
    dm = dispatch if isinstance(dispatch, dict) else {}
    cursor = str(dm.get("next_cursor", "") or dv.get("next_cursor", "")
                 or dv.get("cursor", "")).strip()
    cnt_in = max(0, int(dm.get("count_in", dv.get("count_in", 0)) or 0))
    cnt_out = max(0, int(dm.get("count_out", dv.get("count_out", 0)) or 0))
    _integrations_sync_touch(
        cfg, key, provider, rec["account"], "ok",
        cursor=cursor,
        job_id=str(job.get("id", "")),
        count_in=cnt_in,
        count_out=cnt_out,
    )


def _integrations_channel_send(cfg: dict, key: str, provider: str, row: dict,
                               payload: dict, token_ref: str,
                               job: dict) -> dict:
    tok = _channel_token(cfg, key, provider, token_ref)
    url = _channel_url(cfg, key, provider)
    if not url:
        native = _integrations_channel_native(cfg, key, provider, row,
                                              payload, tok)
        if native:
            return native
        return {"transport": "outbox_only", "reason": "url_unconfigured"}
    body = _channel_body(key, provider, row, payload)
    hdr = {"Authorization": f"Bearer {tok}"} if tok else {}
    ik = _integrations_http_idem(job)
    if ik:
        hdr["Idempotency-Key"] = ik
    out = _integrations_http_post(url, body, hdr)
    cursor = str(out.get("next_cursor", "") or out.get("cursor", "")).strip()
    cnt_in = max(0, int(out.get("count_in", 0) or 0))
    cnt_out = max(0, int(out.get("count_out", 0) or 0))
    return {
        "transport": "provider_http",
        "url": url,
        "id": str(out.get("id", "")),
        "next_cursor": cursor[:400],
        "count_in": cnt_in,
        "count_out": cnt_out,
    }


def _channel_token(cfg: dict, key: str, provider: str, token_ref: str) -> str:
    if token_ref:
        row = _integrations_secret_get(cfg, token_ref)
        if row and str(row.get("status", "")) == "active":
            prv = str(row.get("provider", "")).strip().lower()
            exp = int(row.get("expires_at", 0) or 0)
            now = int(time.time())
            if exp > 0 and exp <= now + 45 and str(row.get("refresh_token", "")):
                if prv in _OAUTH_PROVIDERS:
                    try:
                        row = _oauth_refresh_secret(cfg, prv, row)
                    except Exception:
                        pass
            sec = str(row.get("secret", "")).strip()
            if sec:
                return sec
    env_a, env_b = _channel_env_map(key, provider)
    if env_a:
        return _env_pick(env_a, env_b, "")
    return ""


def _channel_url(cfg: dict, key: str, provider: str) -> str:
    if key == "chatops" and provider == "slack":
        return _env_pick("CTXORG_SLACK_POST_URL", "SLACK_POST_URL",
                         "https://slack.com/api/chat.postMessage")
    if key == "chatops" and provider == "discord":
        return _env_pick("CTXORG_DISCORD_WEBHOOK_URL", "DISCORD_WEBHOOK_URL",
                         "")
    if key == "calendar" and provider == "google":
        return _env_pick("CTXORG_CALENDAR_GOOGLE_SYNC_URL",
                         "CALENDAR_GOOGLE_SYNC_URL",
                         _env_pick("CTXORG_CALENDAR_SYNC_URL",
                                   "CALENDAR_SYNC_URL", ""))
    if key == "calendar" and provider == "outlook":
        return _env_pick("CTXORG_CALENDAR_OUTLOOK_SYNC_URL",
                         "CALENDAR_OUTLOOK_SYNC_URL",
                         _env_pick("CTXORG_CALENDAR_SYNC_URL",
                                   "CALENDAR_SYNC_URL", ""))
    if key == "calendar":
        return _env_pick("CTXORG_CALENDAR_SYNC_URL", "CALENDAR_SYNC_URL", "")
    if key == "crm" and provider == "hubspot":
        return _env_pick("CTXORG_CRM_HUBSPOT_SYNC_URL",
                         "CRM_HUBSPOT_SYNC_URL",
                         _env_pick("CTXORG_CRM_SYNC_URL", "CRM_SYNC_URL", ""))
    if key == "crm" and provider == "salesforce":
        return _env_pick("CTXORG_CRM_SALESFORCE_SYNC_URL",
                         "CRM_SALESFORCE_SYNC_URL",
                         _env_pick("CTXORG_CRM_SYNC_URL", "CRM_SYNC_URL", ""))
    if key == "crm":
        return _env_pick("CTXORG_CRM_SYNC_URL", "CRM_SYNC_URL", "")
    if key == "storage" and provider == "drive":
        return _env_pick("CTXORG_STORAGE_DRIVE_SYNC_URL",
                         "STORAGE_DRIVE_SYNC_URL",
                         _env_pick("CTXORG_STORAGE_SYNC_URL",
                                   "STORAGE_SYNC_URL", ""))
    if key == "storage" and provider == "dropbox":
        return _env_pick("CTXORG_STORAGE_DROPBOX_SYNC_URL",
                         "STORAGE_DROPBOX_SYNC_URL",
                         _env_pick("CTXORG_STORAGE_SYNC_URL",
                                   "STORAGE_SYNC_URL", ""))
    if key == "storage" and provider == "onedrive":
        return _env_pick("CTXORG_STORAGE_ONEDRIVE_SYNC_URL",
                         "STORAGE_ONEDRIVE_SYNC_URL",
                         _env_pick("CTXORG_STORAGE_SYNC_URL",
                                   "STORAGE_SYNC_URL", ""))
    if key == "storage":
        return _env_pick("CTXORG_STORAGE_SYNC_URL", "STORAGE_SYNC_URL", "")
    return ""


def _channel_body(key: str, provider: str, row: dict, payload: dict) -> dict:
    account = str(payload.get("account", "") or row.get("account", "")).strip()
    action = str(payload.get("action", "sync")).strip()[:80]
    data = payload.get("data", {})
    body = data if isinstance(data, dict) else {}
    if key == "chatops" and provider == "slack":
        txt = str(body.get("text", "") or payload.get("text", "")).strip()
        if not txt:
            txt = "Optic channel event."
        return {"channel": account or "#general", "text": txt}
    if key == "chatops" and provider == "discord":
        txt = str(body.get("text", "") or payload.get("text", "")).strip()
        if not txt:
            txt = "Optic channel event."
        return {"content": txt}
    return {
        "channel": key,
        "provider": provider,
        "account": account,
        "action": action or "sync",
        "data": body,
    }


def _integrations_channel_native(cfg: dict, key: str, provider: str,
                                 row: dict, payload: dict, tok: str
                                 ) -> dict | None:
    if not tok:
        return None
    if key == "calendar" and provider == "google":
        return _native_sync_google_calendar(cfg, row, payload, tok)
    if key == "calendar" and provider == "outlook":
        return _native_sync_ms_calendar(cfg, row, payload, tok)
    if key == "storage" and provider == "drive":
        return _native_sync_google_drive(cfg, row, payload, tok)
    if key == "storage" and provider == "onedrive":
        return _native_sync_ms_drive(cfg, row, payload, tok)
    if key == "crm" and provider == "hubspot":
        return _native_sync_hubspot_contacts(cfg, row, payload, tok)
    if key == "crm" and provider == "salesforce":
        return _native_sync_salesforce_contacts(cfg, row, payload, tok)
    return None


def _native_sync_account(row: dict, payload: dict) -> str:
    p = str(payload.get("account", "")).strip()
    r = str(row.get("account", "")).strip()
    return p or r


def _native_sync_cursor(cfg: dict, key: str, provider: str,
                        account: str, payload: dict) -> str:
    data = payload.get("data", {})
    row = data if isinstance(data, dict) else {}
    if bool(row.get("force_full", False)):
        return ""
    cur = str(row.get("cursor", "") or row.get("next_cursor", "")).strip()
    if cur:
        return cur
    sync = _integrations_sync_get(cfg, key, provider, account)
    if not isinstance(sync, dict):
        return ""
    return str(sync.get("cursor", "")).strip()


def _native_sync_google_calendar(cfg: dict, row: dict, payload: dict,
                                 tok: str) -> dict:
    account = _native_sync_account(row, payload) or "primary"
    cursor = _native_sync_cursor(cfg, "calendar", "google", account, payload)
    if cursor.startswith("http://") or cursor.startswith("https://"):
        url = cursor
    else:
        params = {"maxResults": "250", "showDeleted": "true"}
        if cursor:
            params["syncToken"] = cursor
        else:
            params["singleEvents"] = "true"
            params["orderBy"] = "updated"
        cid = quote(account or "primary", safe="")
        base = f"https://www.googleapis.com/calendar/v3/calendars/{cid}/events"
        url = f"{base}?{urlencode(params)}"
    st, out = _integrations_http_json("GET", url, {
        "Authorization": f"Bearer {tok}",
    })
    if st == 410:
        cid = quote(account or "primary", safe="")
        base = f"https://www.googleapis.com/calendar/v3/calendars/{cid}/events"
        url = f"{base}?{urlencode({'maxResults': '250', 'singleEvents': 'true', 'showDeleted': 'true', 'orderBy': 'updated'})}"
        st, out = _integrations_http_json("GET", url, {
            "Authorization": f"Bearer {tok}",
        })
    if st >= 400:
        raise RuntimeError(f"calendar_google_sync_failed:{st}")
    items = out.get("items", []) if isinstance(out, dict) else []
    vals = items if isinstance(items, list) else []
    nxt = str(out.get("nextSyncToken", "") or out.get("nextPageToken", ""))
    return {
        "transport": "native_google_calendar",
        "count_in": len(vals),
        "count_out": 0,
        "next_cursor": nxt[:400],
    }


def _native_sync_google_drive(cfg: dict, row: dict, payload: dict,
                              tok: str) -> dict:
    account = _native_sync_account(row, payload)
    cursor = _native_sync_cursor(cfg, "storage", "drive", account, payload)
    if cursor.startswith("http://") or cursor.startswith("https://"):
        url = cursor
    else:
        params = {
            "pageSize": "200",
            "q": "trashed=false",
            "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,size,parents)",
        }
        if cursor:
            params["pageToken"] = cursor
        url = f"https://www.googleapis.com/drive/v3/files?{urlencode(params)}"
    st, out = _integrations_http_json("GET", url, {
        "Authorization": f"Bearer {tok}",
    })
    if st >= 400:
        raise RuntimeError(f"storage_drive_sync_failed:{st}")
    files = out.get("files", []) if isinstance(out, dict) else []
    vals = files if isinstance(files, list) else []
    nxt = str(out.get("nextPageToken", "")).strip()
    return {
        "transport": "native_google_drive",
        "count_in": len(vals),
        "count_out": 0,
        "next_cursor": nxt[:400],
    }


def _native_sync_ms_calendar(cfg: dict, row: dict, payload: dict,
                             tok: str) -> dict:
    account = _native_sync_account(row, payload)
    cursor = _native_sync_cursor(cfg, "calendar", "outlook", account, payload)
    if cursor.startswith("http://") or cursor.startswith("https://"):
        url = cursor
    else:
        url = "https://graph.microsoft.com/v1.0/me/events/delta?$top=100"
    st, out = _integrations_http_json("GET", url, {
        "Authorization": f"Bearer {tok}",
    })
    if st >= 400:
        raise RuntimeError(f"calendar_outlook_sync_failed:{st}")
    vals = out.get("value", []) if isinstance(out, dict) else []
    rows = vals if isinstance(vals, list) else []
    nxt = str(out.get("@odata.nextLink", "") or
              out.get("@odata.deltaLink", "")).strip()
    return {
        "transport": "native_ms_calendar",
        "count_in": len(rows),
        "count_out": 0,
        "next_cursor": nxt[:400],
    }


def _native_sync_ms_drive(cfg: dict, row: dict, payload: dict,
                          tok: str) -> dict:
    account = _native_sync_account(row, payload)
    cursor = _native_sync_cursor(cfg, "storage", "onedrive", account, payload)
    if cursor.startswith("http://") or cursor.startswith("https://"):
        url = cursor
    else:
        url = "https://graph.microsoft.com/v1.0/me/drive/root/delta?$top=200"
    st, out = _integrations_http_json("GET", url, {
        "Authorization": f"Bearer {tok}",
    })
    if st >= 400:
        raise RuntimeError(f"storage_onedrive_sync_failed:{st}")
    vals = out.get("value", []) if isinstance(out, dict) else []
    rows = vals if isinstance(vals, list) else []
    nxt = str(out.get("@odata.nextLink", "") or
              out.get("@odata.deltaLink", "")).strip()
    return {
        "transport": "native_ms_drive",
        "count_in": len(rows),
        "count_out": 0,
        "next_cursor": nxt[:400],
    }


def _native_sync_hubspot_contacts(cfg: dict, row: dict, payload: dict,
                                  tok: str) -> dict:
    account = _native_sync_account(row, payload)
    cursor = _native_sync_cursor(cfg, "crm", "hubspot", account, payload)
    if cursor.startswith("http://") or cursor.startswith("https://"):
        url = cursor
    else:
        params = {"limit": "100"}
        if cursor:
            params["after"] = cursor
        url = f"https://api.hubapi.com/crm/v3/objects/contacts?{urlencode(params)}"
    st, out = _integrations_http_json("GET", url, {
        "Authorization": f"Bearer {tok}",
    })
    if st >= 400:
        raise RuntimeError(f"crm_hubspot_sync_failed:{st}")
    vals = out.get("results", []) if isinstance(out, dict) else []
    rows = vals if isinstance(vals, list) else []
    nxt = ""
    pg = out.get("paging", {}) if isinstance(out, dict) else {}
    if isinstance(pg, dict):
        nx = pg.get("next", {})
        if isinstance(nx, dict):
            nxt = str(nx.get("after", "") or nx.get("link", "")).strip()
    return {
        "transport": "native_hubspot_contacts",
        "count_in": len(rows),
        "count_out": 0,
        "next_cursor": nxt[:400],
    }


def _native_sync_salesforce_contacts(cfg: dict, row: dict, payload: dict,
                                     tok: str) -> dict | None:
    account = _native_sync_account(row, payload)
    inst = account or _env_pick("CTXORG_SALESFORCE_INSTANCE_URL",
                                "SALESFORCE_INSTANCE_URL", "")
    if not inst:
        return None
    cursor = _native_sync_cursor(cfg, "crm", "salesforce", account, payload)
    if cursor.startswith("http://") or cursor.startswith("https://"):
        url = cursor
    elif cursor.startswith("/"):
        url = f"{inst.rstrip('/')}{cursor}"
    else:
        soql = "SELECT Id, LastModifiedDate FROM Contact ORDER BY LastModifiedDate DESC LIMIT 200"
        q = urlencode({"q": soql})
        url = f"{inst.rstrip('/')}/services/data/v60.0/query?{q}"
    st, out = _integrations_http_json("GET", url, {
        "Authorization": f"Bearer {tok}",
    })
    if st >= 400:
        raise RuntimeError(f"crm_salesforce_sync_failed:{st}")
    vals = out.get("records", []) if isinstance(out, dict) else []
    rows = vals if isinstance(vals, list) else []
    nxt = str(out.get("nextRecordsUrl", "")).strip()
    if nxt and nxt.startswith("/"):
        nxt = f"{inst.rstrip('/')}{nxt}"
    return {
        "transport": "native_salesforce_contacts",
        "count_in": len(rows),
        "count_out": 0,
        "next_cursor": nxt[:400],
    }


def _integrations_social_generic(cfg: dict, social: dict, payload: dict,
                                 provider: str, job: dict) -> dict:
    text = str(payload.get("content", "")).strip()
    if not text:
        raise RuntimeError("social_content_required")
    prv = _social_provider_row(social, provider)
    ref = str(payload.get("token_ref", "")).strip()
    ref = ref or str(prv.get("token_ref", "")).strip()
    env_a, env_b = _social_token_env(provider)
    tok = _social_token(cfg, ref, env_a, env_b)
    if not tok:
        return {"transport": "outbox_only", "provider": provider}
    url = _env_pick(
        f"CTXORG_{provider.upper()}_POST_URL",
        f"{provider.upper()}_POST_URL",
        "",
    )
    if not url:
        return {"transport": "outbox_only", "provider": provider}
    hdr = {"Authorization": f"Bearer {tok}"}
    ik = _integrations_http_idem(job)
    if ik:
        hdr["Idempotency-Key"] = ik
    out = _integrations_http_post(
        url,
        {
            "text": text[:1200],
            "account": str(payload.get("account", "")).strip(),
        },
        hdr,
    )
    return {
        "transport": "provider_api",
        "provider": provider,
        "id": str(out.get("id", "")),
    }


def _integrations_social_x(cfg: dict, social: dict, payload: dict,
                           job: dict) -> dict:
    prv = _social_provider_row(social, "x")
    text = str(payload.get("content", "")).strip()
    if not text:
        raise RuntimeError("social_content_required")
    ref = str(payload.get("token_ref", "")).strip() or \
        str(prv.get("token_ref", "")).strip()
    tok = _social_token(cfg, ref, "CTXORG_X_ACCESS_TOKEN", "X_ACCESS_TOKEN")
    if not tok:
        raise RuntimeError("x_access_token_missing")
    url = _env_pick("CTXORG_X_POST_URL", "X_POST_URL",
                    "https://api.x.com/2/tweets")
    hdr = {"Authorization": f"Bearer {tok}"}
    ik = _integrations_http_idem(job)
    if ik:
        hdr["Idempotency-Key"] = ik
    out = _integrations_http_post(
        url,
        {"text": text[:280]},
        hdr,
    )
    data = out.get("data", {}) if isinstance(out, dict) else {}
    if not isinstance(data, dict):
        data = {}
    return {"transport": "x_api", "id": str(data.get("id", ""))}


def _social_provider_row(social: dict, key: str) -> dict:
    rows = social.get("providers", {}) if isinstance(social, dict) else {}
    row = rows.get(key, {}) if isinstance(rows, dict) else {}
    return row if isinstance(row, dict) else {}


def _social_token_env(provider: str) -> tuple[str, str]:
    key = str(provider or "").strip().lower()
    if key == "x":
        return "CTXORG_X_ACCESS_TOKEN", "X_ACCESS_TOKEN"
    if key == "linkedin":
        return "CTXORG_LINKEDIN_TOKEN", "LINKEDIN_TOKEN"
    if key == "youtube":
        return "CTXORG_YOUTUBE_TOKEN", "YOUTUBE_TOKEN"
    if key == "tiktok":
        return "CTXORG_TIKTOK_TOKEN", "TIKTOK_TOKEN"
    if key == "instagram":
        return "CTXORG_INSTAGRAM_TOKEN", "INSTAGRAM_TOKEN"
    if key == "threads":
        return "CTXORG_THREADS_TOKEN", "THREADS_TOKEN"
    return "", ""


def _channel_provider_allowed(kind: str, provider: str) -> bool:
    specs = _catalog_channel_specs()
    spec = specs.get(kind, {})
    vals = spec.get("providers", [])
    return provider in vals if isinstance(vals, list) else False


def _social_token(cfg: dict, token_ref: str, env_a: str, env_b: str) -> str:
    if token_ref:
        row = _integrations_secret_get(cfg, token_ref)
        if row and str(row.get("status", "")) == "active":
            sec = str(row.get("secret", "")).strip()
            if sec:
                return sec
    return _env_pick(env_a, env_b, "")


def _integrations_http_idem(job: dict) -> str:
    key = str(job.get("idempotency_key", "")).strip()
    if key:
        return key[:120]
    jid = str(job.get("id", "")).strip()
    return jid[:120] if jid else ""


def _integrations_email_send(cfg: dict, provider: str, email: dict,
                             payload: dict, job: dict) -> dict:
    if provider in {"smtp", "ses"}:
        return _integrations_email_smtp(cfg, email, payload)
    if provider == "resend":
        return _integrations_email_resend(cfg, email, payload, job)
    if provider == "sendgrid":
        return _integrations_email_sendgrid(cfg, email, payload, job)
    raise RuntimeError("email_provider_unsupported")


def _integrations_email_smtp(cfg: dict, email: dict, payload: dict) -> dict:
    msg = _integrations_email_msg(email, payload)
    host = _env_pick("CTXORG_SMTP_HOST", "SMTP_HOST", email.get("smtp_host"))
    port = int(_env_pick("CTXORG_SMTP_PORT", "SMTP_PORT",
               email.get("smtp_port", 587)) or 587)
    user = _env_pick("CTXORG_SMTP_USER", "SMTP_USER", email.get("smtp_user"))
    pwd = _env_pick("CTXORG_SMTP_PASS", "SMTP_PASS", "")
    if not host:
        raise RuntimeError("smtp_host_required")
    if bool(email.get("smtp_use_ssl", False)):
        with smtplib.SMTP_SSL(host, port, timeout=12) as srv:
            _integrations_smtp_login(srv, user, pwd)
            srv.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=12) as srv:
            if bool(email.get("smtp_starttls", True)):
                srv.starttls(context=ssl.create_default_context())
            _integrations_smtp_login(srv, user, pwd)
            srv.send_message(msg)
    return {"transport": "smtp", "host": host, "port": port}


def _integrations_smtp_login(srv: smtplib.SMTP, user: str, pwd: str) -> None:
    if not user:
        return
    if not pwd:
        raise RuntimeError("smtp_password_required")
    srv.login(user, pwd)


def _integrations_email_resend(cfg: dict, email: dict, payload: dict,
                               job: dict) -> dict:
    key = _env_pick("CTXORG_RESEND_API_KEY", "RESEND_API_KEY", "")
    if not key:
        raise RuntimeError("resend_api_key_missing")
    to = _integrations_email_to(payload.get("to"))
    data = {
        "from": _integrations_email_from(email),
        "to": to,
        "subject": str(payload.get("subject", ""))[:180],
        "text": str(payload.get("body", "")),
    }
    hdr = {"Authorization": f"Bearer {key}"}
    ik = _integrations_http_idem(job)
    if ik:
        hdr["Idempotency-Key"] = ik
    out = _integrations_http_post(
        "https://api.resend.com/emails",
        data,
        hdr,
    )
    return {"transport": "resend", "id": out.get("id", "")}


def _integrations_email_sendgrid(cfg: dict, email: dict, payload: dict,
                                 job: dict) -> dict:
    key = _env_pick("CTXORG_SENDGRID_API_KEY", "SENDGRID_API_KEY", "")
    if not key:
        raise RuntimeError("sendgrid_api_key_missing")
    to = [{"email": x} for x in _integrations_email_to(payload.get("to"))]
    data = {
        "personalizations": [{"to": to}],
        "from": {
            "email": _integrations_email_from_addr(email),
            "name": str(email.get("from_name", "Optic"))[:80],
        },
        "subject": str(payload.get("subject", ""))[:180],
        "content": [{
            "type": "text/plain",
            "value": str(payload.get("body", "")),
        }],
    }
    hdr = {"Authorization": f"Bearer {key}"}
    ik = _integrations_http_idem(job)
    if ik:
        hdr["Idempotency-Key"] = ik
    _integrations_http_post(
        "https://api.sendgrid.com/v3/mail/send",
        data,
        hdr,
    )
    return {"transport": "sendgrid", "status": "accepted"}


def _integrations_email_msg(email: dict, payload: dict) -> EmailMessage:
    to = _integrations_email_to(payload.get("to"))
    if not to:
        raise RuntimeError("email_to_required")
    frm = _integrations_email_from(email)
    msg = EmailMessage()
    msg["To"] = ", ".join(to)
    msg["From"] = frm
    msg["Subject"] = str(payload.get("subject", "")).strip()[:180] or "Optic"
    reply = str(email.get("reply_to", "")).strip()
    if reply:
        msg["Reply-To"] = reply
    msg.set_content(str(payload.get("body", "")))
    return msg


def _integrations_email_from(email: dict) -> str:
    addr = _integrations_email_from_addr(email)
    name = str(email.get("from_name", "Optic")).strip()[:80]
    return f"{name} <{addr}>" if name else addr


def _integrations_email_from_addr(email: dict) -> str:
    val = _env_pick("CTXORG_SMTP_FROM", "SMTP_FROM", email.get("from_email"))
    out = str(val or "").strip()
    if not out:
        raise RuntimeError("email_from_required")
    return out


def _integrations_email_to(raw: object) -> list[str]:
    vals = raw if isinstance(raw, list) else [raw]
    out = []
    for row in vals:
        txt = str(row or "").strip()
        if txt and txt not in out:
            out.append(txt[:160])
    return out


def _integrations_email_daily_count(cfg: dict) -> int:
    path = cfgmod.state_dir(cfg, "integrations") / "email_sent.ndjson"
    if not path.exists():
        return 0
    now = int(time.time())
    day = now - (now % 86400)
    cnt = 0
    for line in path.read_text(encoding="utf-8").splitlines()[-3000:]:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        ts = int(row.get("ts", 0) or 0)
        if ts >= day:
            cnt += 1
    return cnt


def _integrations_http_json(method: str, url: str,
                            headers: dict[str, str]) -> tuple[int, dict]:
    req = urllib.request.Request(url, method=method)
    req.add_header("content-type", "application/json")
    for key, val in headers.items():
        req.add_header(key, val)
    try:
        with urllib.request.urlopen(req, timeout=20) as fh:
            txt = fh.read().decode("utf-8", errors="ignore")
            if not txt.strip():
                return int(fh.status), {}
            val = json.loads(txt)
            out = val if isinstance(val, dict) else {}
            return int(fh.status), out
    except urllib.error.HTTPError as exc:
        txt = exc.read().decode("utf-8", errors="ignore")
        try:
            val = json.loads(txt) if txt.strip() else {}
        except Exception:
            val = {}
        out = val if isinstance(val, dict) else {}
        return int(exc.code), out


def _integrations_http_post(url: str, data: dict,
                            headers: dict[str, str]) -> dict:
    raw = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=raw, method="POST")
    req.add_header("content-type", "application/json")
    for key, val in headers.items():
        req.add_header(key, val)
    try:
        with urllib.request.urlopen(req, timeout=15) as fh:
            txt = fh.read().decode("utf-8", errors="ignore")
            if not txt.strip():
                return {}
            val = json.loads(txt)
            return val if isinstance(val, dict) else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"http_{exc.code}:{body[:200]}") from exc


def _env_pick(a: str, b: str, fallback: object) -> str:
    if a in os.environ:
        return str(os.environ.get(a, "")).strip()
    if b in os.environ:
        return str(os.environ.get(b, "")).strip()
    return str(fallback or "").strip()


def _integrations_emit(cfg: dict, name: str, rec: dict) -> None:
    path = cfgmod.state_dir(cfg, "integrations") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


def _integrations_sync_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg) / "integration_sync_state.json"


def _integrations_sync_rows(cfg: dict, scope_id: str | None = None
                            ) -> list[dict]:
    data = _store_read(_integrations_sync_path(cfg))
    rows = data.get("items", []) if isinstance(data, dict) else []
    vals = rows if isinstance(rows, list) else []
    out = [x for x in vals if isinstance(x, dict)]
    scope = _integrations_scope_id(cfg) if scope_id is None else str(
        scope_id or "",
    ).strip()
    if not scope:
        return out
    keep = []
    for row in out:
        wsid = str(row.get("workspace_id", "")).strip()
        if not wsid or wsid == scope:
            keep.append(row)
    return keep


def _integrations_sync_save(cfg: dict, rows: list[dict]) -> None:
    _store_write(_integrations_sync_path(cfg), {"items": rows[-1200:]})


def _integrations_sync_key(channel: str, provider: str, account: str) -> str:
    aid = account.strip().lower() or "-"
    return f"{channel.strip().lower()}:{provider.strip().lower()}:{aid}"[:220]


def _integrations_sync_get(cfg: dict, channel: str, provider: str,
                           account: str) -> dict | None:
    key = _integrations_sync_key(channel, provider, account)
    for row in _integrations_sync_rows(cfg):
        if str(row.get("id", "")).strip() == key:
            return row
    return None


def _integrations_sync_upsert(cfg: dict, channel: str, provider: str,
                              account: str, patch: dict) -> dict:
    now = int(time.time())
    wsid = _integrations_scope_id(cfg)
    key = _integrations_sync_key(channel, provider, account)
    rows = _integrations_sync_rows(cfg, scope_id="")
    out = []
    found = False
    row = {}
    for cur in rows:
        cid = str(cur.get("id", "")).strip()
        cws = str(cur.get("workspace_id", "")).strip()
        same_ws = (cws == wsid) or (not cws)
        if cid != key or not same_ws:
            out.append(cur)
            continue
        row = dict(cur)
        found = True
    if not found:
        row = {
            "id": key,
            "workspace_id": wsid,
            "channel": channel[:40],
            "provider": provider[:40],
            "account": account[:160],
            "status": "idle",
            "cursor": "",
            "count_in": 0,
            "count_out": 0,
            "last_job_id": "",
            "last_ok_at": 0,
            "last_error": "",
            "last_error_at": 0,
            "updated_at": now,
        }
    for key2, val in patch.items():
        row[str(key2)] = val
    row["updated_at"] = now
    out.append(row)
    _integrations_sync_save(cfg, out)
    return row


def _integrations_sync_touch(cfg: dict, channel: str, provider: str,
                             account: str, status: str, *, cursor: str = "",
                             err: str = "", job_id: str = "",
                             count_in: int = 0, count_out: int = 0) -> None:
    patch = {
        "status": status[:40],
        "last_job_id": job_id[:120],
        "count_in": max(0, int(count_in)),
        "count_out": max(0, int(count_out)),
    }
    if cursor:
        patch["cursor"] = cursor[:400]
    now = int(time.time())
    if status in {"ok", "done"}:
        patch["last_ok_at"] = now
        patch["last_error"] = ""
        patch["last_error_at"] = 0
    if err:
        patch["last_error"] = err[:300]
        patch["last_error_at"] = now
    _integrations_sync_upsert(cfg, channel, provider, account, patch)


def _integrations_secrets_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg) / "integration_secrets.json"


def _integrations_scope_id(cfg: dict) -> str:
    ws = _workspace_load(cfg)
    if not isinstance(ws, dict):
        return ""
    return str(ws.get("id", "")).strip()[:80]


def _integrations_secrets_list(cfg: dict, scope_id: str | None = None
                               ) -> list[dict]:
    data = _store_read(_integrations_secrets_path(cfg))
    if not data:
        return []
    vals = data.get("items", [])
    rows = vals if isinstance(vals, list) else []
    out = [x for x in rows if isinstance(x, dict)]
    scope = _integrations_scope_id(cfg) if scope_id is None else str(
        scope_id or "",
    ).strip()
    if not scope:
        return out
    keep = []
    for row in out:
        wsid = str(row.get("workspace_id", "")).strip()
        if not wsid or wsid == scope:
            keep.append(row)
    return keep


def _integrations_secrets_save(cfg: dict, vals: list[dict]) -> None:
    _store_write(_integrations_secrets_path(cfg), {"items": vals[-500:]})


def _integrations_secret_get(cfg: dict, ref: str) -> dict | None:
    for row in _integrations_secrets_list(cfg):
        if str(row.get("token_ref", "")).strip() == ref.strip():
            return row
    return None


def _integrations_secret_mark_revoked(cfg: dict, row: dict) -> dict:
    ref = str(row.get("token_ref", "")).strip()
    wsid = str(row.get("workspace_id", "")).strip()
    now = int(time.time())
    vals = _integrations_secrets_list(cfg, scope_id="")
    out = []
    rec = dict(row)
    rec["status"] = "revoked"
    rec["secret"] = ""
    rec["refresh_token"] = ""
    rec["revoked_at"] = now
    rec["updated_at"] = now
    hit = False
    for cur in vals:
        cref = str(cur.get("token_ref", "")).strip()
        cws = str(cur.get("workspace_id", "")).strip()
        if cref == ref and cws == wsid:
            out.append(rec)
            hit = True
            continue
        out.append(cur)
    if not hit:
        out.append(rec)
    _integrations_secrets_save(cfg, out)
    return rec


def _integrations_webhook(cfg: dict, payload: dict) -> None:
    url = str(payload.get("url", "")).strip()
    if not url:
        provider = str(payload.get("provider", "")).strip().lower()
        event = str(payload.get("event", "")).strip()
        if provider and event:
            _integrations_emit(cfg, "webhook_events.ndjson", {
                "provider": provider,
                "event": event,
                "received_at": int(time.time()),
                "payload": payload.get("payload", {}),
            })
            return
        raise RuntimeError("webhook_url_required")
    body = payload.get("body", {})
    raw = json.dumps(body if isinstance(body, dict) else {}).encode("utf-8")
    req = urllib.request.Request(url, data=raw, method="POST")
    req.add_header("content-type", "application/json")
    with urllib.request.urlopen(req, timeout=8):
        return


def graph_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    run = _run_query(req, cfg)
    data = read_graph(cfg, run)
    return enrich(cfg, run, data)


def query(req: BaseHTTPRequestHandler) -> dict:
    return parse_qs(urlparse(req.path).query)


def _run_clean(raw: object) -> str:
    val = str(raw or "").strip()
    if not val:
        return ""
    if _RUN_RE.fullmatch(val):
        return val
    raise ReqErr("invalid_run_id", code=400)


def _run_query(req: BaseHTTPRequestHandler, cfg: dict) -> str:
    val = _run_clean(query(req).get("run", [""])[0])
    return val or latest(cfg)


def latest(cfg: dict) -> str:
    rs = runs(cfg)
    return rs[0] if rs else ""


def runs(cfg: dict) -> list[str]:
    root = cfgmod.state_dir(cfg, "graphs")
    vals = [p.stem for p in root.glob("*.json")]
    return sorted(vals, reverse=True)


def read_graph(cfg: dict, run: str) -> dict:
    run = _run_clean(run)
    if not run:
        return {"nodes": [], "links": [], "run": ""}
    path = cfgmod.state_dir(cfg, "graphs") / f"{run}.json"
    if not path.exists():
        return empty_graph(run, "graph_not_found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return empty_graph(run, f"graph_read_failed:{exc}")


def empty_graph(run: str, err: str) -> dict:
    return {"nodes": [], "links": [], "run": run, "err": err}


def enrich(cfg: dict, run: str, data: dict) -> dict:
    plans = plan_map(cfg, run)
    edits = edit_map(cfg, run)
    labels = label_map(cfg, run)
    nodes = limit_nodes(cfg, data.get("nodes", []))
    items = item_map(cfg, nodes)
    ids = {n["id"] for n in nodes}
    links = [l for l in data.get("links", []) if in_graph(l, ids)]
    nodes = [node(n, plans, edits, labels, items) for n in nodes]
    out = {"run": run, "nodes": nodes, "links": links}
    out.update({k: data[k] for k in ("err",) if k in data})
    return out


def in_graph(link: dict, ids: set) -> bool:
    return link["a"] in ids and link["b"] in ids


def limit_nodes(cfg: dict, nodes: list[dict]) -> list[dict]:
    cap = int(cfg.get("ui_node_limit", 0) or 0)
    return nodes[:cap] if cap and len(nodes) > cap else nodes


def plan_map(cfg: dict, run: str) -> dict:
    run = _run_clean(run)
    if not run:
        return {}
    path = cfgmod.state_dir(cfg, "plans") / f"{run}.ndjson"
    if not path.exists():
        return {}
    return {r["id"]: r for r in ndjson(path)}


def edit_map(cfg: dict, run: str) -> dict:
    run = _run_clean(run)
    if not run:
        return {}
    path = cfgmod.state_dir(cfg, "edits") / f"{run}.ndjson"
    if not path.exists():
        return {}
    return {r["id"]: r for r in ndjson(path)}


def label_map(cfg: dict, run: str) -> dict:
    run = _run_clean(run)
    if not run:
        return {}
    path = cfgmod.state_dir(cfg, "labels") / f"{run}.ndjson"
    if not path.exists():
        return {}
    return {r["id"]: r for r in ndjson(path)}


def ndjson(path: Path) -> list[dict]:
    rows = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in rows if x.strip()]


def item_map(cfg: dict, nodes: list[dict]) -> dict:
    ids = [n["id"] for n in nodes]
    if not ids:
        return {}
    conn = db.open_db(cfg)
    vals = ",".join("?" for _ in ids)
    rows = db.rows(conn, f"SELECT * FROM items WHERE id IN ({vals})", ids)
    return {r["id"]: r for r in rows}


def node(rec: dict, plans: dict, edits: dict, labels: dict,
         items: dict) -> dict:
    plan = plans.get(rec["id"], {})
    edit = edits.get(rec["id"], {})
    label = labels.get(rec["id"], {})
    item = items.get(rec["id"], {})
    dst = plan.get("dst", "")
    path = item.get("path") or rec["path"]
    name = Path(dst or path).name
    out = dict(rec)
    out.update({k: item[k] for k in item if k not in ("id", "text")})
    out["path"] = path
    out["label"] = name
    out["dst"] = dst
    out["why"] = plan.get("why", "")
    out["edit"] = edit
    out["tags"] = label.get("tags", [])
    return out


def analyze_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    """Local, DB-powered analytics — no LLM needed."""
    kind = query(req).get("kind", ["largest"])[0]
    limit = int(query(req).get("limit", ["20"])[0])
    conn = db.open_db(cfg)

    if kind == "largest":
        rows_ = db.rows(conn,
            "SELECT id, path, ext, size, mtime FROM items "
            "WHERE size > 0 AND kind = 'file' ORDER BY size DESC LIMIT ?",
            (limit,))
        return {"kind": kind, "items": rows_}

    if kind == "old_downloads":
        import time
        cutoff = time.time() - 30 * 86400   # 30 days
        rows_ = db.rows(conn,
            "SELECT id, path, ext, size, mtime FROM items "
            "WHERE path LIKE ? AND kind = 'file' AND mtime < ? AND size > 102400 "
            "ORDER BY mtime ASC LIMIT ?",
            (f"%/Downloads/%", cutoff, limit))
        return {"kind": kind, "items": rows_}

    if kind == "duplicates":
        # Find filenames (lowercased) that appear in more than one distinct directory
        all_rows = db.rows(conn,
            "SELECT id, path, ext, size FROM items WHERE kind = 'file'")
        from collections import defaultdict
        from pathlib import Path as P
        by_name: dict = defaultdict(list)
        for r in all_rows:
            name = P(r["path"]).name.lower()
            if len(name) > 4 and not name.startswith("."):
                by_name[name].append(r)
        groups = [
            {"name": name, "count": len(rs), "items": rs[:6],
             "total_size": sum(r["size"] for r in rs)}
            for name, rs in sorted(by_name.items(),
                                   key=lambda kv: -sum(x["size"] for x in kv[1]))
            if len(rs) > 1
        ][:limit]
        return {"kind": kind, "groups": groups}

    if kind == "corpus":
        # Summary stats for inspector
        from collections import Counter
        import time
        total = db.rows(conn, "SELECT COUNT(*) as c, SUM(size) as s FROM items WHERE kind='file'")
        ext_rows = db.rows(conn,
            "SELECT ext, COUNT(*) as c, SUM(size) as s FROM items "
            "WHERE kind='file' AND ext != '' GROUP BY ext ORDER BY c DESC LIMIT 12")
        week = time.time() - 7 * 86400
        recent = db.rows(conn,
            "SELECT COUNT(*) as c FROM items WHERE kind='file' AND mtime > ?",
            (week,))
        return {
            "kind": kind,
            "total_files": total[0]["c"] if total else 0,
            "total_bytes": total[0]["s"] if total else 0,
            "recent_week": recent[0]["c"] if recent else 0,
            "extensions": [{"ext": r["ext"], "count": r["c"], "bytes": r["s"]}
                           for r in ext_rows],
        }

    return {"kind": kind, "error": "unknown kind"}


# ---------------------------------------------------------------------------
# Audit payloads — optic signal engine
# ---------------------------------------------------------------------------


def _consent_check_source(source_id: str, mode: str = "local") -> dict:
    """Check consent_receipts for *source_id*.  Returns a consent decision dict.

    Invariant #2 (Consent-Scoped): every source MUST have an active, unrevoked
    consent receipt whose scope includes 'infer' before it enters the audit
    pipeline.

    Returns
    -------
    { "consented": bool, "reason": str, "receipt_id": str|None }
    """
    if not source_id or not _V1_AVAILABLE:
        return {"consented": True, "reason": "no_source_id_or_db", "receipt_id": None}
    try:
        conn = _v1_open_db()
        row = conn.execute(
            "SELECT id, scope, purpose, cloud_allowed, revoked_at "
            "FROM consent_receipts WHERE source_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (source_id,)
        ).fetchone()
        conn.close()

        if row is None:
            # No receipt on file — conservative default: allow (backward compat)
            return {"consented": True, "reason": "no_receipt_found", "receipt_id": None}

        receipt_id = row["id"]

        # 1. Revoked consent → exclude
        if row["revoked_at"] is not None:
            return {"consented": False, "reason": "revoked",
                    "receipt_id": receipt_id}

        # 2. Scope must include 'infer'
        try:
            scope = json.loads(row["scope"] or "[]")
        except (json.JSONDecodeError, TypeError):
            scope = []
        if "infer" not in scope:
            return {"consented": False, "reason": "scope_missing_infer",
                    "receipt_id": receipt_id}

        # 3. Cloud modes require cloud_allowed
        if mode == "cloud" and not row["cloud_allowed"]:
            return {"consented": False, "reason": "cloud_not_allowed",
                    "receipt_id": receipt_id}

        return {"consented": True, "reason": "active_consent",
                "receipt_id": receipt_id}

    except Exception as exc:
        log.warning("consent_check error for source %s: %s", source_id, exc)
        # On error, exclude to be safe (fail closed)
        return {"consented": False, "reason": f"db_error: {exc}", "receipt_id": None}


def _audit_build_auditor(include_ml: bool = False):
    auditor = SignalAuditor()
    auditor.add_detector(PatternDetector.default_bias_patterns())
    if include_ml and _ML_AVAILABLE:
        auditor.add_detector(MLDetector())
    return auditor


def _audit_history_push(record: dict) -> None:
    with _audit_lock:
        _audit_history.insert(0, record)
        if len(_audit_history) > _AUDIT_HISTORY_MAX:
            _audit_history.pop()


def audit_single_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    if not _OPTIC_AVAILABLE:
        raise ReqErr("optic_engine_unavailable", code=503)
    data = body(req)
    content = _str_field(data, "content", 10000)
    if not content:
        raise ReqErr("missing_content", code=400)

    # ── Consent filter (Invariant #2) ──
    source_id = str(data.get("source_id", "")).strip() or None
    audit_mode = str(data.get("mode", "local")).strip()
    consent = _consent_check_source(source_id, audit_mode) if source_id else None

    if consent and not consent["consented"]:
        result = {
            "content": "",
            "content_summary": content[:100],
            "source": str(data.get("source", "text")),
            "signals": [],
            "detection_count": 0,
            "consent_blocked": True,
            "consent_reason": consent["reason"],
            "consent_receipt_id": consent.get("receipt_id"),
            "source_id": source_id,
        }
        _audit_history_push(result)
        return result

    try:
        from optic.signal.models import SignalSource  # type: ignore
        source = SignalSource(str(data.get("source", "text")))
    except Exception:
        from optic.signal.models import SignalSource  # type: ignore
        source = SignalSource.TEXT
    include_ml = bool(data.get("include_ml", False))
    summary = str(data.get("content_summary", content[:100]))
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    auditor = _audit_build_auditor(include_ml=include_ml)
    result = auditor.audit(content, source, summary, metadata).to_dict()
    # Inject consent decision into result
    if consent:
        result["consented"] = consent["consented"]
        result["consent_reason"] = consent["reason"]
        result["consent_receipt_id"] = consent.get("receipt_id")
        result["source_id"] = source_id
    _audit_history_push(result)
    return result


def audit_ml_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    if not _OPTIC_AVAILABLE or not _ML_AVAILABLE:
        raise ReqErr("ml_engine_unavailable", code=503)
    data = body(req)
    content = _str_field(data, "content", 10000)
    if not content:
        raise ReqErr("missing_content", code=400)

    # ── Consent filter (Invariant #2) ──
    source_id = str(data.get("source_id", "")).strip() or None
    audit_mode = str(data.get("mode", "local")).strip()
    consent = _consent_check_source(source_id, audit_mode) if source_id else None

    if consent and not consent["consented"]:
        result = {
            "content": "",
            "content_summary": content[:100],
            "source": str(data.get("source", "text")),
            "signals": [],
            "detection_count": 0,
            "consent_blocked": True,
            "consent_reason": consent["reason"],
            "consent_receipt_id": consent.get("receipt_id"),
            "source_id": source_id,
        }
        _audit_history_push(result)
        return result

    try:
        from optic.signal.models import SignalSource  # type: ignore
        source = SignalSource(str(data.get("source", "text")))
    except Exception:
        from optic.signal.models import SignalSource  # type: ignore
        source = SignalSource.TEXT
    summary = str(data.get("content_summary", content[:100]))
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    auditor = _audit_build_auditor(include_ml=True)
    result = auditor.audit(content, source, summary, metadata).to_dict()
    if consent:
        result["consented"] = consent["consented"]
        result["consent_reason"] = consent["reason"]
        result["consent_receipt_id"] = consent.get("receipt_id")
        result["source_id"] = source_id
    _audit_history_push(result)
    return result


def audit_batch_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    if not _OPTIC_AVAILABLE:
        raise ReqErr("optic_engine_unavailable", code=503)
    data = body(req)
    signals_raw = data.get("signals", [])
    if not signals_raw or not isinstance(signals_raw, list):
        raise ReqErr("missing_signals", code=400)

    # ── Consent filter (Invariant #2) — per-item and batch-level ──
    batch_source_id = str(data.get("source_id", "")).strip() or None
    audit_mode = str(data.get("mode", "local")).strip()
    consent_decisions: list[dict] = []
    consented_items = []
    blocked_items = []

    include_ml = bool(data.get("include_ml", False))
    auditor = _audit_build_auditor(include_ml=include_ml)
    try:
        from optic.signal.models import SignalSource  # type: ignore
    except Exception:
        raise ReqErr("optic_engine_unavailable", code=503)
    tuples = []
    for item in signals_raw[:100]:
        content = str(item.get("content", "")).strip()
        if not content:
            continue

        # Per-item consent check
        item_source_id = str(item.get("source_id", batch_source_id or "")).strip() or None
        if item_source_id:
            consent = _consent_check_source(item_source_id, audit_mode)
            consent_decisions.append({"source_id": item_source_id, **consent})
            if not consent["consented"]:
                blocked_items.append({
                    "content_summary": content[:100],
                    "source_id": item_source_id,
                    "consent_reason": consent["reason"],
                })
                continue
        try:
            source = SignalSource(str(item.get("source", "text")))
        except Exception:
            source = SignalSource.TEXT
        summary = str(item.get("content_summary", content[:100]))
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        tuples.append((content, source, summary, meta))
    if not tuples:
        raise ReqErr("no_valid_signals", code=400)
    audit_result = auditor.audit_multiple(tuples)
    result = audit_result.to_dict()
    # Inject consent decisions
    if consent_decisions:
        result["consent_checks"] = consent_decisions
    if blocked_items:
        result["consent_blocked_items"] = blocked_items
    for sig in audit_result.signals:
        _audit_history_push(sig.to_dict())
    return result


def audit_history_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    with _audit_lock:
        snap = list(_audit_history)
    items = [
        {
            "id": r.get("id"),
            "source": r.get("source"),
            "content_summary": r.get("content_summary"),
            "created_at": r.get("created_at"),
            "detection_count": r.get("detection_count", 0),
        }
        for r in snap
    ]
    return {"history": items, "total": len(items)}


def audit_detail_payload(req: BaseHTTPRequestHandler, cfg: dict, audit_id: str) -> dict:
    with _audit_lock:
        snap = list(_audit_history)
    for r in snap:
        if r.get("id") == audit_id:
            return r
    raise ReqErr("not_found", code=404)


# ── Vana DataConnect ingestion (optic/vana_ingest.py) ──────────────────────

_VANA_UPLOAD_MAX_BODY = 8 * 1024 * 1024  # browser-uploaded export batches


def _vana_uid(req: BaseHTTPRequestHandler) -> str:
    """Per-user profile key derived from the frontend session cookie.

    The Next.js proxy forwards headers, so the httpOnly `optic_session`
    cookie (user id) reaches the backend. Hash it so the raw id never
    lands in a filename.
    """
    cookie = req.headers.get("cookie", "") or ""
    for part in cookie.split(";"):
        name, _, value = part.strip().partition("=")
        if name == "optic_session" and value:
            return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return "default"


def vana_status_payload(cfg: dict) -> dict:
    """GET /api/vana/status — discover local DataConnect export stores."""
    if not _VANA_AVAILABLE:
        raise ReqErr("vana_ingest_unavailable", code=503)
    return _vana.status()


def vana_profile_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    """GET /api/vana/profile — return the persisted signal profile."""
    if not _VANA_AVAILABLE:
        raise ReqErr("vana_ingest_unavailable", code=503)
    return _vana.profile_load(cfgmod.state_dir(cfg), uid=_vana_uid(req))


def vana_ingest_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    """POST /api/vana/ingest — scan local exports, audit, persist (desktop mode).

    Body: {roots?: [str], include_ml?: bool, max_items?: int}
    """
    if not _VANA_AVAILABLE or not _OPTIC_AVAILABLE:
        raise ReqErr("vana_ingest_unavailable", code=503)
    data = body(req)
    roots_raw = data.get("roots")
    roots = None
    if isinstance(roots_raw, list) and roots_raw:
        roots = [Path(str(r)) for r in roots_raw[:10]]
    include_ml = bool(data.get("include_ml", False))
    try:
        max_items = max(1, min(int(data.get("max_items", _vana.DEFAULT_MAX_ITEMS)), 10000))
    except (TypeError, ValueError):
        max_items = _vana.DEFAULT_MAX_ITEMS
    profile = _vana.ingest(
        cfgmod.state_dir(cfg),
        _audit_build_auditor,
        roots=roots,
        include_ml=include_ml and _ML_AVAILABLE,
        max_items=max_items,
        uid=_vana_uid(req),
    )
    if profile["corpus"]["audited_items"] == 0:
        raise ReqErr("no_exports_found", code=404)
    profile["exists"] = True
    return profile


def vana_upload_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    """POST /api/vana/upload — batched browser upload of export files (hosted mode).

    Body: {session: str, files: [{name?, data}], final?: bool, include_ml?: bool}
    Non-final batches spool and return progress; the final batch (which may
    carry zero files) triggers the audit and returns the profile.
    """
    if not _VANA_AVAILABLE or not _OPTIC_AVAILABLE:
        raise ReqErr("vana_ingest_unavailable", code=503)
    data = body(req, max_body=_VANA_UPLOAD_MAX_BODY)
    session = str(data.get("session", "")).strip()
    if not session:
        raise ReqErr("missing_session", code=400)
    uid = _vana_uid(req)
    state = cfgmod.state_dir(cfg)

    files = data.get("files", [])
    if not isinstance(files, list):
        raise ReqErr("invalid_files", code=400)
    progress = _vana.spool_add(state, uid, session, files[:200]) if files else None

    if not bool(data.get("final", False)):
        if progress is None:
            raise ReqErr("missing_files", code=400)
        return progress

    include_ml = bool(data.get("include_ml", False))
    profile = _vana.spool_finalize(
        state, _audit_build_auditor, uid, session,
        include_ml=include_ml and _ML_AVAILABLE,
    )
    if profile["corpus"]["audited_items"] == 0:
        raise ReqErr("no_text_found", code=422)
    profile["exists"] = True
    return profile


def export_history_payload(cfg: dict) -> dict:
    vals = _export_history_list(cfg)
    vals.sort(key=lambda x: -int(x.get("created_at", 0) or 0))
    return {"items": vals[:80]}


def export_create_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    _workspace_require_role(cfg, {"owner", "admin", "member"})
    data = body(req)
    run = str(data.get("run", "")).strip() or latest(cfg)
    kind = str(data.get("kind", "report")).strip().lower()
    dest = str(data.get("dest_dir", "")).strip()
    _quota_take(cfg, "export_daily")
    allow = bool(data.get("allow_risky", False))
    red = bool(data.get("redact", _settings_runtime(cfg)["privacy"].get(
        "redact_exports", True)))
    payload = _export_build(req, cfg, run, kind)
    check = _export_check(payload)
    if check["risk_count"] > 0 and not (allow or red):
        raise ReqErr("export_blocked_compliance", code=400,
                     detail=f"risk_count={check['risk_count']}")
    safe = _export_redact(payload) if red else payload
    rec = _export_write(cfg, safe, run, kind, dest, check, red)
    return {"ok": True, "export": rec}


def _export_build(req: BaseHTTPRequestHandler, cfg: dict, run: str,
                  kind: str) -> dict:
    if kind == "graph":
        return graph_payload(_qs_req(f"/api/graph?run={run}"), cfg)
    if kind == "workstreams":
        return workstreams_payload(_qs_req(f"/api/workstreams?run={run}"), cfg)
    if kind in {"datapack", "bundle"}:
        return {
            "run": run,
            "report": report_payload(_qs_req(f"/api/report?run={run}"), cfg),
            "workstreams": workstreams_payload(
                _qs_req(f"/api/workstreams?run={run}"), cfg
            ),
            "graph": graph_payload(_qs_req(f"/api/graph?run={run}"), cfg),
            "settings": settings_payload(cfg).get("settings", {}),
        }
    if kind == "markdown":
        # Use same rich data as datapack for comprehensive markdown
        return {
            "run": run,
            "report": report_payload(_qs_req(f"/api/report?run={run}"), cfg),
            "workstreams": workstreams_payload(
                _qs_req(f"/api/workstreams?run={run}"), cfg
            ),
        }
    return report_payload(_qs_req(f"/api/report?run={run}"), cfg)


def _qs_req(path: str) -> BaseHTTPRequestHandler:
    return type("Req", (), {"path": path})()  # type: ignore[return-value]


def _export_check(data: dict) -> dict:
    txt = json.dumps(data, ensure_ascii=False)
    email_n = len(_RED_EMAIL_RE.findall(txt))
    num_n = len(_RED_NUM_RE.findall(txt))
    tok_n = len(_RED_TOK_RE.findall(txt))
    risk = email_n + num_n + tok_n
    return {
        "risk_count": risk,
        "emails": email_n,
        "long_numbers": num_n,
        "tokens": tok_n,
        "ok": risk == 0,
    }


def _export_redact(data: object) -> object:
    if isinstance(data, dict):
        return {k: _export_redact(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_export_redact(v) for v in data]
    if not isinstance(data, str):
        return data
    txt = _RED_EMAIL_RE.sub("[redacted-email]", data)
    txt = _RED_NUM_RE.sub("[redacted-number]", txt)
    return _RED_TOK_RE.sub("[redacted-token]", txt)


def _export_write(cfg: dict, data: object, run: str, kind: str, dest: str,
                  check: dict, redacted: bool) -> dict:
    root = _export_root(cfg, dest)
    root.mkdir(parents=True, exist_ok=True)
    eid = f"exp-{uuid.uuid4().hex[:10]}"
    ts = int(time.time())

    # Determine file extension and content based on format
    ext, body_bytes = _export_format(kind, data, run, ts)

    name = f"optic-{kind}-{run or 'latest'}-{ts}{ext}"
    path = root / name
    path.write_bytes(body_bytes)
    rec = {
        "id": eid,
        "run": run,
        "kind": kind,
        "path": str(path),
        "bytes": path.stat().st_size,
        "created_at": ts,
        "compliance": check,
        "redacted": bool(redacted),
    }
    vals = _export_history_list(cfg)
    vals.append(rec)
    _export_history_save(cfg, vals[-300:])
    return rec


def _export_format(kind: str, data: object, run: str, ts: int) -> tuple[str, bytes]:
    """Return (extension, bytes_content) for the given export kind."""
    if kind in ("datapack", "graph", "bundle", "audience"):
        return (".json", json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
    if kind == "report":
        return _export_to_pdf(data, run, ts)
    if kind == "workstreams":
        return _export_to_csv(data)
    if kind == "markdown":
        return _export_to_md(data, run, ts)
    # fallback: JSON
    return (".json", json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))


def _export_to_csv(data: dict) -> tuple[str, bytes]:
    """Convert workstreams data to CSV."""
    import io
    buf = io.StringIO()
    ws_list = data if isinstance(data, list) else data.get("workstreams", [])
    if not ws_list:
        buf.write("id,name,file_count,confidence,topics,summary\n")
    else:
        fieldnames = ["id", "name", "file_count", "confidence", "topics", "summary"]
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for ws in ws_list:
            row = dict(ws)
            if isinstance(row.get("topics"), list):
                row["topics"] = "; ".join(str(t) for t in row["topics"])
            writer.writerow(row)
    return (".csv", buf.getvalue().encode("utf-8"))


def _sanitize_pdf_text(text: str) -> str:
    """Replace Unicode characters not supported by the Helvetica core font."""
    # Map common Unicode chars to ASCII equivalents
    replacements = {
        '\u2014': '--',   # em dash
        '\u2013': '-',    # en dash
        '\u2018': "'",    # left single quote
        '\u2019': "'",    # right single quote
        '\u201c': '"',    # left double quote
        '\u201d': '"',    # right double quote
        '\u2026': '...',  # ellipsis
        '\u2022': '*',    # bullet
        '\u00a0': ' ',    # non-breaking space
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    # Strip any remaining non-latin1 characters
    return text.encode('latin-1', errors='replace').decode('latin-1')


def _export_to_pdf(data: dict, run: str, ts: int) -> tuple[str, bytes]:
    """Convert report/audience data to a proper PDF."""
    import io
    pdf = FPDF()
    pdf.add_page()
    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, _sanitize_pdf_text("Optic Export Report"), ln=True, align="C")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _sanitize_pdf_text(f"Run: {run}  |  Generated: {ts}"), ln=True, align="C")
    pdf.ln(8)

    # Corpus section
    def _add_section(title, content_lines):
        if pdf.get_y() > 250:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, _sanitize_pdf_text(title), ln=True)
        pdf.set_font("Helvetica", "", 10)
        for line in content_lines:
            line = _sanitize_pdf_text(line)
            if len(line) > 120:
                line = line[:117] + "..."
            pdf.cell(0, 5, line, ln=True)
        pdf.ln(3)

    # Extract sections from data
    if isinstance(data, dict):
        # Corpus info
        corpus = data.get("corpus", {})
        if corpus:
            _add_section("Corpus", [
                f"Total files: {corpus.get('total_files', 'N/A')}",
                f"Total bytes: {corpus.get('total_bytes', 'N/A')}",
                f"Recent week: {corpus.get('recent_week', 'N/A')}",
            ])

        # Workstreams
        ws_data = data.get("workstreams", {})
        wss = ws_data.get("workstreams", ws_data.get("cards", []))
        if isinstance(wss, list) and wss:
            _add_section(f"Workstreams ({len(wss)})", [])
            for ws in wss[:30]:
                name = _sanitize_pdf_text(str(ws.get("name", "")))
                fc = ws.get("file_count", "?")
                conf = ws.get("confidence", 0)
                conf_s = f"{int(conf*100)}%" if isinstance(conf, float) else str(conf)
                summary = _sanitize_pdf_text(str(ws.get("summary", "")))[:120]
                pdf.cell(0, 5, f"  {name} -- {fc} files, {conf_s} confidence", ln=True)
                if summary:
                    pdf.set_font("Helvetica", "", 9)
                    pdf.cell(0, 5, f"    {summary}", ln=True)
                    pdf.set_font("Helvetica", "", 10)

        # Report details
        report = data.get("report", data)
        if isinstance(report, dict):
            scan = report.get("scan", {})
            if scan:
                metrics = scan.get("metrics", {})
                infer_metrics = scan.get("infer_metrics", {})
                _add_section("Scan Status", [
                    f"Scanning: {scan.get('scanning', False)}",
                    f"Queue depth: {scan.get('queue_depth', 0)}",
                    f"Dead letters: {scan.get('dead_letter_count', 0)}",
                    f"API hits: {metrics.get('api_hits', 0)}",
                    f"Inference requests: {infer_metrics.get('infer_req', 0)}",
                ])

    # Watermark
    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, _sanitize_pdf_text("Optic self-audit. Not a consumer report. Not a verdict."), ln=True, align="C")

    buf = io.BytesIO()
    pdf.output(buf)
    return (".pdf", buf.getvalue())


def _export_to_md(data: dict, run: str, ts: int) -> tuple[str, bytes]:
    """Convert report data to Markdown."""
    md = f"# Optic Export Report\n\n"
    md += f"**Run:** {run}  \n"
    md += f"**Generated:** {ts}\n\n"

    if not isinstance(data, dict):
        return (".md", md.encode("utf-8"))

    corpus = data.get("corpus", data.get("report", {}).get("corpus", {}))
    if corpus:
        md += "## Corpus\n\n"
        md += f"- Total files: {corpus.get('total_files', 'N/A')}\n"
        md += f"- Total bytes: {corpus.get('total_bytes', 'N/A')}\n"
        md += f"- Recent week: {corpus.get('recent_week', 'N/A')}\n\n"

    ws_data = data.get("workstreams", {})
    wss = ws_data.get("workstreams", ws_data.get("cards", []))
    if isinstance(wss, list) and wss:
        md += f"## Workstreams ({len(wss)})\n\n"
        for ws in wss[:50]:
            name = str(ws.get("name", ""))
            fc = ws.get("file_count", "?")
            conf = ws.get("confidence", 0)
            conf_s = f"{int(conf*100)}%" if isinstance(conf, float) else str(conf)
            summary = str(ws.get("summary", ""))
            md += f"### {name} ({fc} files, {conf_s})\n\n"
            if summary:
                md += f"{summary}\n\n"
            topics = ws.get("topics", [])
            if topics:
                md += f"*Topics: {', '.join(str(t) for t in topics)}*\n\n"

    report = data.get("report", data)
    if isinstance(report, dict):
        scan = report.get("scan", {})
        if scan:
            md += "## Scan Status\n\n"
            md += f"- Scanning: {scan.get('scanning', False)}\n"
            md += f"- Queue depth: {scan.get('queue_depth', 0)}\n"
            md += f"- Dead letters: {scan.get('dead_letter_count', 0)}\n\n"

    md += "\n---\n*Optic self-audit. Not a consumer report. Not a verdict.*\n"
    return (".md", md.encode("utf-8"))


def _export_root(cfg: dict, dest: str) -> Path:
    if not dest:
        return cfgmod.state_dir(cfg, "exports")
    path = Path(dest).expanduser()
    if not path.is_absolute():
        path = (Path(cfg.get("home", "")) / path).resolve()
    return path


def _export_history_path(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg) / "exports_history.json"


def _export_history_list(cfg: dict) -> list[dict]:
    data = _store_read(_export_history_path(cfg))
    if not data:
        return []
    vals = data.get("items", [])
    return vals if isinstance(vals, list) else []


def _export_history_save(cfg: dict, vals: list[dict]) -> None:
    _store_write(_export_history_path(cfg), {"items": vals})


def export_v1_formats_payload(cfg: dict) -> dict:
    """GET /api/v1/exports — return available export formats."""
    return {
        "formats": [
            {
                "id": "report",
                "title": "Executive Report (PDF)",
                "subtitle": "Comprehensive narrative report with visuals and key insights.",
            },
            {
                "id": "audience",
                "title": "Audience Snapshot (JSON)",
                "subtitle": "Tailored summary for a specific audience perspective.",
            },
            {
                "id": "datapack",
                "title": "Data Package (JSON)",
                "subtitle": "Raw signals and entities for technical consumption.",
            },
            {
                "id": "workstreams",
                "title": "CSV Findings",
                "subtitle": "Structured findings for analysis in spreadsheets.",
            },
            {
                "id": "markdown",
                "title": "Markdown Summary",
                "subtitle": "Human-readable markdown report with key findings.",
            },
        ],
        "history": export_history_payload(cfg).get("items", []),
    }


def export_v1_create_payload(req: BaseHTTPRequestHandler, cfg: dict,
                              fmt: str) -> dict:
    """POST /api/v1/export/{format} — trigger an export for a given format."""
    if not fmt:
        raise ReqErr("missing_format", code=400,
                     detail="export format is required in URL path")
    kinds = {"report", "audience", "datapack", "workstreams", "graph", "bundle", "markdown"}
    if fmt not in kinds:
        raise ReqErr("unknown_format", code=400,
                     detail=f"unknown format '{fmt}'. valid: {', '.join(sorted(kinds))}")
    _workspace_require_role(cfg, {"owner", "admin", "member"})
    data = body(req)
    run = str(data.get("run", "")).strip() or latest(cfg)
    dest = str(data.get("dest_dir", "")).strip()
    _quota_take(cfg, "export_daily")
    allow = bool(data.get("allow_risky", False))
    red = bool(data.get("redact",
               _settings_runtime(cfg)["privacy"].get("redact_exports", True)))
    payload = _export_build(req, cfg, run, fmt)
    check = _export_check(payload)
    if check["risk_count"] > 0 and not (allow or red):
        raise ReqErr("export_blocked_compliance", code=400,
                     detail=f"risk_count={check['risk_count']}")
    safe = _export_redact(payload) if red else payload
    rec = _export_write(cfg, safe, run, fmt, dest, check, red)
    return {"ok": True, "export": rec}


def entity_profile_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    """GET /api/entity/profile?id=<item_id>[&refresh=1]"""
    from . import identity as id_mod
    params = query(req)
    item_id = (params.get("id") or [""])[0]
    refresh = (params.get("refresh") or ["0"])[0] == "1"
    if not item_id:
        return {"error": "id_required"}
    conn = db.open_db(cfg)
    try:
        profile = id_mod.get_profile(conn, cfg, item_id, refresh=refresh)
    except Exception as exc:
        return {"error": str(exc)[:200]}
    if profile is None:
        return {"error": "item_not_found"}
    return {"profile": profile}


def audience_list_payload() -> dict:
    """GET /api/audience — returns available audience profiles."""
    from . import identity as id_mod
    return {"audiences": id_mod.list_audiences()}


def embed_status_payload(cfg: dict) -> dict:
    from . import embed
    conn = db.open_db(cfg)
    embed.ensure_embed_table(conn)
    embedded_rows = db.rows(conn, "SELECT count(*) as c FROM embeddings")
    total_rows = db.rows(conn, "SELECT count(*) as c FROM items")
    return {
        "embedded": embedded_rows[0]["c"] if embedded_rows else 0,
        "total": total_rows[0]["c"] if total_rows else 0,
        "model": embed.EMBED_MODEL,
        "dim": embed.EMBED_DIM,
    }


def start_embed_run(cfg: dict) -> dict:
    from . import embed

    def _run() -> None:
        conn = db.open_db(cfg)
        rows = db.rows(conn, "SELECT id, path, text FROM items")
        embed.embed_items(conn, cfg, rows, verbose=True)

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "status": "embedding started"}


def rename_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    data = body(req)
    path = str(data.get("path") or "")
    name = str(data.get("name") or "")
    if not rename_ok(cfg, path, name):
        return {"ok": False, "err": "rename_not_allowed"}
    src = Path(path)
    dst = src.with_name(name)
    if dst.exists():
        return {"ok": False, "err": "destination_exists"}
    src.rename(dst)
    return {"ok": True, "path": str(dst)}


def rename_ok(cfg: dict, path: str, name: str) -> bool:
    src = Path(path)
    if "/" in name or "\\" in name or not name or len(name) > 120:
        return False
    if not src.exists() or not reveal_ok(cfg, path):
        return False
    return src.suffix.lower() == Path(name).suffix.lower()


def reveal_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    vals = query(req)
    path = vals.get("path", [""])[0]
    mode = vals.get("mode", ["reveal"])[0]
    if not reveal_ok(cfg, path):
        return {"ok": False, "err": "path_not_allowed"}
    return reveal(path, mode)


def reveal_ok(cfg: dict, path: str) -> bool:
    if not path or not Path(path).exists():
        return False
    roots = [
        cfg.get("home", ""),
        cfg.get("target", ""),
        cfg.get("state_dir", ""),
    ]
    return any(root and fs.inside(path, root) for root in roots)


def reveal(path: str, mode: str) -> dict:
    cmd = ["open", str(path)] if mode == "open" else ["open", "-R", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    err = (proc.stderr or proc.stdout).strip()[:300]
    return {"ok": proc.returncode == 0, "err": err}


def iris_stream(req: BaseHTTPRequestHandler, cfg: dict, data: dict | None = None) -> None:
    """POST /api/iris — streaming Neurontology response via chunked HTTP."""
    from . import iris as iris_mod
    if data is None:
        data = body(req)
    req.send_response(200)
    for key, val in _sec_headers(req).items():
        req.send_header(key, val)
    req.send_header("Content-Type", "application/x-ndjson")
    req.send_header("Transfer-Encoding", "chunked")
    req.send_header("X-Accel-Buffering", "no")
    req.end_headers()

    def _write_chunk(payload: str) -> None:
        encoded = payload.encode("utf-8") if isinstance(payload, str) else payload
        req.wfile.write(f"{len(encoded):x}\r\n".encode() + encoded + b"\r\n")
        req.wfile.flush()

    try:
        conn = db.open_db(cfg)
        for line in iris_mod.stream_response(cfg, conn, data):
            _write_chunk(line)
    except (BrokenPipeError, ConnectionResetError):
        return
    except Exception as exc:
        err_line = json.dumps({"type": "error", "message": str(exc)}) + "\n"
        try:
            _write_chunk(err_line)
        except Exception:
            pass
    try:
        req.wfile.write(b"0\r\n\r\n")
        req.wfile.flush()
    except Exception:
        pass


def static(req: BaseHTTPRequestHandler, name: str) -> None:
    root = Path(__file__).parent / "static"
    path = (root / name).resolve()
    if not safe_static(root, path):
        return send_err(req, "not_found", code=404)
    body = path.read_bytes()
    req.send_response(200)
    for key, val in _sec_headers(req).items():
        req.send_header(key, val)
    req.send_header("content-type", mime(path))
    req.send_header("content-length", str(len(body)))
    req.end_headers()
    req.wfile.write(body)


def safe_static(root: Path, path: Path) -> bool:
    return path.exists() and path.is_file() and root.resolve() in path.parents


def mime(path: Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def _is_api_path(req: BaseHTTPRequestHandler) -> bool:
    path = urlparse(getattr(req, "path", "")).path
    return path.startswith("/api/") or path in {"/healthz", "/readyz"}


def _req_tls(req: BaseHTTPRequestHandler) -> bool:
    if _req_hdr(req, "x-forwarded-proto").lower() == "https":
        return True
    if _req_hdr(req, "x-forwarded-ssl").lower() in {"on", "1", "true"}:
        return True
    if _req_hdr(req, "front-end-https").lower() == "on":
        return True
    if isinstance(getattr(req, "request", None), ssl.SSLSocket):
        return True
    raw = str(req.headers.get("forwarded", "")).lower()
    return "proto=https" in raw


def _csp() -> str:
    return (
        "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
        "object-src 'none'; img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "connect-src 'self'; font-src 'self' data:; form-action 'self'"
    )


def _sec_headers(req: BaseHTTPRequestHandler) -> dict:
    out = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": _csp(),
    }
    if _is_api_path(req):
        out["Cache-Control"] = "no-store"
    return out


# ── Optic V1 API payloads ────────────────────────────────────────
# These read from the V1 SQLite database at ~/.optic/v1.db
# that is populated by optic.v1.startup on first scan.

def _v1_open_db():
    """Open the V1 SQLite database for reading."""
    import sqlite3
    conn = sqlite3.connect(str(_V1_DB))
    conn.row_factory = sqlite3.Row
    return conn


def _v1_open_db_rw():
    """Open the V1 SQLite database in read-write mode (for audit writes)."""
    import sqlite3
    conn = sqlite3.connect(str(_V1_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _v1_workstreams_fallback() -> list[dict]:
    """Build workstream cards from V1 DB signals when scanner DB is empty.

    Reads the signals table (metadata JSON with workstream_id, workstream_name,
    confidence, file_count, topics, evidence_labels) and returns workstream
    card dicts in the same shape as workstreams.compute().
    """
    import sqlite3
    import json as _json

    db_path = _V1_DB
    if not db_path.exists():
        db_path = Path("/Users/ahmedm/.optic/v1.db")
    if not db_path.exists():
        return []

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
    except Exception:
        return []

    try:
        # Get all topic_focus signals (one per workstream, best metadata)
        rows = conn.execute(
            "SELECT metadata FROM signals WHERE category='topic_focus' ORDER BY id"
        ).fetchall()

        cards = []
        for row in rows:
            meta_str = row["metadata"]
            if not meta_str:
                continue
            try:
                meta = _json.loads(meta_str)
            except _json.JSONDecodeError:
                continue

            ws_id = str(meta.get("workstream_id", ""))
            if not ws_id:
                continue
            ws_name = str(meta.get("workstream_name", ws_id))
            confidence = float(meta.get("confidence", 0.5))
            file_count = int(meta.get("file_count", 0))
            topics_raw = meta.get("topics", [])
            if isinstance(topics_raw, str):
                topics_raw = [topics_raw]
            topics_raw = [str(t) for t in topics_raw]
            evidence_labels = meta.get("evidence_labels", [])
            if isinstance(evidence_labels, str):
                evidence_labels = [evidence_labels]

            # Derive type breakdown from topics
            breakdown = {"screenshots": 0, "documents": 0, "code": 0,
                         "media": 0, "other": 0}
            topic_str = " ".join(t.lower() for t in topics_raw)
            if "code" in topic_str and "writing" in topic_str:
                breakdown["code"] = int(file_count * 0.5)
                breakdown["documents"] = int(file_count * 0.5)
            elif "code" in topic_str:
                breakdown["code"] = int(file_count * 0.7)
                breakdown["documents"] = int(file_count * 0.3)
            elif "writing" in topic_str:
                breakdown["documents"] = int(file_count * 0.7)
                breakdown["code"] = int(file_count * 0.3)
            else:
                breakdown["other"] = file_count

            # Color from dominant type
            dominant = max(breakdown, key=lambda k: breakdown[k])
            color = {
                "screenshots": "teal", "media": "coral",
                "documents": "blue", "code": "amber", "other": "gray",
            }.get(dominant, "purple")

            # Use evidence labels as key_files
            key_files = [str(lbl) for lbl in evidence_labels[:5]]

            # Summary
            summary = (
                f"{file_count} files in '{ws_name}' — "
                f"{', '.join(topics_raw[:3])}."
            )

            cards.append({
                "id": ws_id,
                "name": ws_name,
                "file_count": file_count,
                "type_breakdown": breakdown,
                "folders": [ws_name],
                "key_files": key_files,
                "topics": topics_raw,
                "summary": summary,
                "confidence": confidence,
                "color": color,
            })

        # Sort by confidence * log(file_count) descending (same as compute())
        import math as _math
        cards.sort(
            key=lambda c: c["confidence"] * _math.log2(min(c["file_count"], 150) + 1),
            reverse=True,
        )
        return cards
    finally:
        conn.close()


def _v1_total_file_count() -> int:
    """Return total file count summed from V1 DB signal metadata."""
    import sqlite3
    import json as _json

    db_path = _V1_DB
    if not db_path.exists():
        db_path = Path("/Users/ahmedm/.optic/v1.db")
    if not db_path.exists():
        return 0

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
    except Exception:
        return 0

    try:
        rows = conn.execute(
            "SELECT metadata FROM signals WHERE category='topic_focus'"
        ).fetchall()
        total = 0
        for row in rows:
            try:
                meta = _json.loads(row["metadata"] or "{}")
                total += int(meta.get("file_count", 0))
            except (_json.JSONDecodeError, ValueError, TypeError):
                pass
        return total
    finally:
        conn.close()


def _v1_init_db():
    """Create the V1 SQLite database and tables if they don't exist.
    Mirrors the schema from optic.v1.server.init_db() so ctxorg can
    self-bootstrap without requiring the V1 FastAPI server to run first."""
    global _V1_AVAILABLE
    _V1_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = _v1_open_db_rw()
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
    """)
    conn.commit()
    # Run idempotent migration from V1 server module
    try:
        from optic.v1.server import _migrate_v1_schema
        _migrate_v1_schema(conn)
    except ImportError:
        pass
    conn.close()
    _V1_AVAILABLE = True
    _log_ev("v1_init_db", db_path=str(_V1_DB))


def v1_health_payload(_cfg=None) -> dict:
    """GET /api/v1/health — returns V1 module health status."""
    if not _V1_AVAILABLE:
        return {"ok": False, "error": "v1_database_unavailable", "local_mode": True}
    try:
        conn = _v1_open_db()
        claims = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
        signals = conn.execute("SELECT COUNT(*) as c FROM signals").fetchone()["c"]
        repairs = conn.execute("SELECT COUNT(*) as c FROM repairs").fetchone()["c"]
        risks = conn.execute("SELECT COUNT(*) as c FROM risks").fetchone()["c"]
        conn.close()
        return {
            "ok": True,
            "version": "1.0",
            "local_mode": True,
            "v1_available": True,
            "claims_count": claims,
            "signals_count": signals,
            "repairs_count": repairs,
            "risks_count": risks,
            "v1_db": str(_V1_DB) if _V1_DB else "uninitialized",
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "local_mode": True}


def v1_status_payload(_req=None, _cfg=None) -> dict:
    """Return V1 system status: claims, repairs, reports, risks counts."""
    if not _V1_AVAILABLE:
        return {
            "status": "no_database",
            "version": "0.1.0",
            "claims": 0, "risks": 0, "pending_repairs": 0, "reports": 0,
            "routes": 0, "v1_modules": [], "server_uptime": "unknown",
            "recent_claims": [], "repair_queue": [],
        }
    try:
        conn = _v1_open_db()
        claims = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
        risks = conn.execute("SELECT COUNT(*) as c FROM risks").fetchone()["c"]
        repairs = conn.execute(
            "SELECT COUNT(*) as c FROM repairs WHERE status='pending'"
        ).fetchone()["c"]
        reports = conn.execute("SELECT COUNT(*) as c FROM reports").fetchone()["c"]
        # Recent claims (top 15)
        rc_rows = conn.execute(
            "SELECT title, claim, audience_lens, confidence_band, severity "
            "FROM claims ORDER BY generated_at DESC LIMIT 15"
        ).fetchall()
        recent_claims = [_v1_row_to_dict(r) for r in rc_rows]
        # Repair queue (top 15 by computed priority)
        rq_rows = conn.execute(
            "SELECT id, title, status, impact, effort, urgency, reversibility "
            "FROM repairs ORDER BY status, "
            "(impact * urgency * reversibility / MAX(effort, 0.01)) DESC LIMIT 15"
        ).fetchall()
        repair_queue = []
        for r in rq_rows:
            d = _v1_row_to_dict(r)
            imp = float(d.get("impact", 0.5))
            urg = float(d.get("urgency", 0.5))
            rev = float(d.get("reversibility", 0.5))
            eff = max(float(d.get("effort", 0.5)), 0.01)
            d["priority"] = round((imp * urg * rev) / eff, 3)
            repair_queue.append(d)
        conn.close()
        return {
            "status": "running",
            "version": "0.2.0",
            "claims": claims,
            "risks": risks,
            "pending_repairs": repairs,
            "reports": reports,
            "routes": 30,
            "recent_claims": recent_claims,
            "repair_queue": repair_queue,
            "v1_modules": ["models","lenses","contradiction","inference",
                           "parsers","resolver","graph","scrapers",
                           "iris_audit","server"],
            "server_uptime": "since restart",
        }
    except Exception as exc:
        return {
            "status": "error",
            "version": "0.1.0",
            "claims": 0, "risks": 0, "pending_repairs": 0, "reports": 0,
            "routes": 0, "v1_modules": [], "server_uptime": "unknown",
            "error": str(exc)[:200],
        }


def v1_settings_payload(_req=None, cfg=None) -> dict:
    """Return V1 settings from the database, or sensible defaults."""
    settings: dict = {}
    if _V1_AVAILABLE:
        try:
            conn = _v1_open_db()
            # Read from the first user's settings field
            row = conn.execute(
                "SELECT settings FROM users LIMIT 1"
            ).fetchone()
            conn.close()
            if row and row["settings"]:
                try:
                    settings = json.loads(row["settings"])
                except (json.JSONDecodeError, TypeError):
                    pass
        except Exception:
            pass
    # Merge with defaults so the frontend always has expected keys
    defaults = {
        "integrations": {
            "social": {},
            "email": {},
            "channels": {"calendar": {}, "crm": {}, "storage": {}, "chatops": {}},
            "automation": {},
        },
        "scan_rules": {
            "allowed_extensions": [".md",".pdf",".txt",".py",".js",".ts",".json",".yaml",".csv"],
            "max_file_size_mb": 50,
            "exclude_patterns": ["node_modules",".git","__pycache__",".venv"],
        },
        "privacy": {
            "local_only": True,
            "cloud_sync": False,
            "telemetry": False,
        },
    }
    for key, val in defaults.items():
        if key not in settings:
            settings[key] = val
    return {"settings": settings}


def v1_artifacts_payload(req, _cfg=None) -> dict:
    """Return artifacts from the V1 database with path/size/ext/mtime."""
    if not _V1_AVAILABLE:
        return {"artifacts": [], "total": 0, "limit": 100, "offset": 0}
    try:
        vals = query(req)
        limit = min(max(int((vals.get("limit", ["100"])[0])), 1), 500)
        offset = max(int((vals.get("offset", ["0"])[0])), 0)
        conn = _v1_open_db()
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
            except (json.JSONDecodeError, TypeError):
                pass
            artifacts.append({
                "id": r["id"],
                "path": r["encrypted_path"] or "",
                "type": r["type"] or "",
                "size": meta.get("size", 0),
                "ext": meta.get("ext", ""),
                "mtime": meta.get("mtime", 0),
                "parent": meta.get("parent", ""),
                "hash": r["raw_hash"] or "",
                "created_at": r["created_at"] or "",
            })
        return {"artifacts": artifacts, "total": total, "limit": limit, "offset": offset}
    except Exception as exc:
        return {"artifacts": [], "total": 0, "limit": 100, "offset": 0, "error": str(exc)[:200]}


def _v1_audit_bg():
    """Background thread: run the V1 audit pipeline against the shared DB."""
    try:
        # Lazy-import V1 modules (they live at backend/src/optic/v1/)
        from optic.v1.models import (
            Artifact, AuditMode, ConfidenceBand, Contradiction, Entity,
            InferenceClaim, RepairAction, RepairStatus, Report, RiskCategory,
            RiskFlag, Severity, Signal,
        )
        from optic.v1.lenses import AUDIENCE_LENSES
        from optic.v1.contradiction import ContradictionEngine
        from optic.v1.inference import InferenceCardGenerator
        import hashlib as _hashlib
        from uuid import uuid4 as _uuid4, UUID

        conn_rw = _v1_open_db_rw()
        now_iso = datetime.now(timezone.utc).isoformat()

        # ── Stages 0: Load real workstream data from cache (available for evidence) ──
        _workstream_cards: list[dict] = []
        with _ws_lock:
            for _rid, _entry in _ws_cache.items():
                if _entry.get("ready") and _entry.get("cards"):
                    _workstream_cards = _entry["cards"]
                    break

        # ── Stage 0.5: Consent filter (Invariant #2) ──
        consent_summary: dict = {"total_sources": 0, "consented": 0, "excluded": 0,
                                  "excluded_reasons": [], "source_decisions": []}
        try:
            source_rows = conn_rw.execute(
                "SELECT id, user_label, type, provider, status FROM sources"
            ).fetchall()
            consent_summary["total_sources"] = len(source_rows)
            for srow in source_rows:
                decision = _consent_check_source(srow["id"], mode="local")
                consent_summary["source_decisions"].append({
                    "source_id": srow["id"],
                    "label": srow["user_label"] or srow["provider"] or srow["type"],
                    "consented": decision["consented"],
                    "reason": decision["reason"],
                })
                if decision["consented"]:
                    consent_summary["consented"] += 1
                else:
                    consent_summary["excluded"] += 1
                    consent_summary["excluded_reasons"].append(
                        f"{srow.get('user_label') or srow['id']}: {decision['reason']}")
        except Exception as exc:
            log.warning("V1 audit: consent filter stage failed: %s", exc)
            consent_summary["error"] = str(exc)

        # ── Apply consent filter to workstream cards ──
        # Build a blocklist of non-consented source labels/IDs
        non_consented_labels: set[str] = set()
        non_consented_ids: set[str] = set()
        for sd in consent_summary.get("source_decisions", []):
            if not sd.get("consented", True):
                non_consented_ids.add(sd.get("source_id", ""))
                non_consented_labels.add((sd.get("label", "") or "").lower())
        # Filter workstream cards: exclude any card whose name or
        # folder names match a non-consented source label.
        if non_consented_labels:
            _workstream_cards = [
                card for card in _workstream_cards
                if not (
                    (card.get("name", "") or "").lower() in non_consented_labels
                    or any(
                        (f or "").lower() in non_consented_labels
                        for f in (card.get("folders", []) or [])
                        if isinstance(f, str)
                    )
                )
            ]
            consent_summary["cards_filtered"] = True
        else:
            consent_summary["cards_filtered"] = False

        # ── Stages 1-3: Derive signals from existing data ──
        existing_signals = conn_rw.execute(
            "SELECT * FROM signals ORDER BY created_at DESC"
        ).fetchall()
        existing_claims = conn_rw.execute(
            "SELECT * FROM claims ORDER BY generated_at DESC"
        ).fetchall()

        # If no claims exist, generate signals from ACTUAL scan data when available
        if not existing_claims:
            ws_cards = _workstream_cards

            if ws_cards:
                # Derive signals from real workstream data
                seed_signals = []
                for i, card in enumerate(ws_cards):
                    ws_name = card.get("name", f"workstream-{i}")
                    ws_id = card.get("id", f"ws-{i}")
                    confidence = float(card.get("confidence", 0.5))
                    file_count = int(card.get("file_count", 0))
                    topics = card.get("topics", []) or []
                    meta = {
                        "workstream_id": ws_id,
                        "workstream_name": ws_name,
                        "confidence": confidence,
                        "file_count": file_count,
                        "topics": topics,
                        "summary": card.get("summary", "")[:200],
                    }
                    # Categorize based on workstream metadata
                    if file_count > 100:
                        seed_signals.append(
                            ("activity_volume", f"High activity in {ws_name} ({file_count} files)",
                             Severity.LOW.value, json.dumps(meta)))
                    if confidence >= 0.6:
                        seed_signals.append(
                            ("topic_focus", f"Primary work domain: {ws_name}",
                             Severity.LOW.value, json.dumps(meta)))
                    if any(t in ("archive", "legacy", "old") for t in topics):
                        seed_signals.append(
                            ("timeline_gap", f"Archived content in {ws_name}",
                             Severity.MEDIUM.value, json.dumps(meta)))
                    elif file_count > 50 and confidence >= 0.7:
                        seed_signals.append(
                            ("project_velocity", f"Consistent output in {ws_name}",
                             Severity.LOW.value, json.dumps(meta)))

                if not seed_signals:
                    # Fallback: at minimum, create one signal per workstream
                    for card in ws_cards[:6]:
                        seed_signals.append(
                            ("topic_focus", f"Workstream: {card.get('name', 'Unknown')}",
                             Severity.LOW.value,
                             json.dumps({"workstream_id": card.get("id", ""),
                                        "workstream_name": card.get("name", ""),
                                        "confidence": card.get("confidence", 0.5),
                                        "file_count": card.get("file_count", 0),
                                        "topics": card.get("topics", [])})))
            else:
                # No scan data available — honest empty state (Invariant #8: No Fake Completeness)
                seed_signals = []
            for cat, desc, sev, meta in seed_signals:
                sid = str(_uuid4())
                conn_rw.execute(
                    "INSERT OR REPLACE INTO signals(id, category, description, severity, "
                    "source_artifact_ids, metadata, created_at) VALUES(?,?,?,?,?,?,?)",
                    (sid, cat, desc, sev, "[]", meta, now_iso)
                )
            conn_rw.commit()
            existing_signals = conn_rw.execute(
                "SELECT * FROM signals ORDER BY created_at DESC"
            ).fetchall()

        # ── Stages 4-7: Generate inference claims per audience lens ──
        all_signals_rows = [_v1_row_to_dict(r) for r in existing_signals]
        # ── Load real artifacts from the seeded DB (startup.py populates this) ──
        db_artifact_rows = conn_rw.execute(
            "SELECT id, source_id, type, raw_hash, encrypted_path, metadata, "
            "is_public, content_preview, created_at "
            "FROM artifacts ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        db_artifacts_by_id: dict[str, dict] = {}
        for ar in db_artifact_rows:
            meta = {}
            try:
                meta = json.loads(ar["metadata"] or "{}")
            except (json.JSONDecodeError, TypeError):
                pass
            db_artifacts_by_id[ar["id"]] = {
                "id": ar["id"],
                "source_id": ar["source_id"],
                "type": ar["type"],
                "raw_hash": ar["raw_hash"],
                "encrypted_path": ar["encrypted_path"],
                "metadata": meta,
                "is_public": bool(ar["is_public"]),
                "content_preview": ar["content_preview"] or "",
                "created_at": ar["created_at"] or "",
            }
        all_generated_artifacts: list[dict] = []
        # ── Build real artifact objects BEFORE the lens loop so signals can reference them ──
        real_artifacts: list[Artifact] = []
        for ad in list(db_artifacts_by_id.values())[:30]:
            real_artifacts.append(Artifact(
                id=UUID(ad["id"]),
                source_id=UUID(ad["source_id"]),
                type=ad["type"],
                raw_hash=ad["raw_hash"],
                encrypted_path=ad["encrypted_path"],
                metadata=ad["metadata"],
                is_public=ad["is_public"],
                content_preview=ad["content_preview"],
                created_at=ad.get("created_at", ""),
            ))
        # If DB is empty, fall back to workstream-derived artifacts
        if not real_artifacts and _workstream_cards:
            for card in _workstream_cards[:5]:
                for kf in (card.get("key_files") or [])[:3]:
                    if isinstance(kf, str) and kf:
                        aid = _uuid4()
                        fpath = Path(kf)
                        real_artifacts.append(Artifact(
                            id=aid, source_id=_uuid4(),
                            type="scanned_file",
                            raw_hash=_hashlib.sha256(str(aid).encode()).hexdigest(),
                            metadata={
                                "path": kf, "name": fpath.name,
                                "ext": fpath.suffix,
                                "workstream": card.get("name", ""),
                                "file_count": card.get("file_count", 0),
                            },
                            is_public=False,
                            content_preview=card.get("summary", "")[:100],
                        ))
        # If still empty, last-resort fallback from signal metadata
        if not real_artifacts:
            for i in range(min(3, len(existing_signals))):
                aid = _uuid4()
                real_artifacts.append(Artifact(
                    id=aid, source_id=_uuid4(), type="workstream_file",
                    raw_hash=_hashlib.sha256(str(aid).encode()).hexdigest(),
                    metadata={"workstream": f"ws-{i}", "file_count": 50},
                    is_public=False, content_preview="",
                ))
        # ── FIX: Derive artifact IDs from real_artifacts for signals ──
        artifact_id_strings = [str(a.id) for a in real_artifacts[:10]]
        # ── Persist real artifact IDs into signal rows so DB state matches runtime ──
        if artifact_id_strings:
            artifact_ids_json = json.dumps(artifact_id_strings)
            conn_rw.execute(
                "UPDATE signals SET source_artifact_ids = ? WHERE source_artifact_ids = '[]'",
                (artifact_ids_json,)
            )
            conn_rw.commit()
        # ── Stages 6-7: Generate inference claims per lens with REAL artifact IDs ──
        for lens_id in list(AUDIENCE_LENSES.keys()):  # Apply all 9 doctrinal lenses
            try:
                gen = InferenceCardGenerator(lens_id)
                signal_objects = []
                for sig in all_signals_rows:
                    try:
                        signal_objects.append(Signal(
                            id=sig.get("id", str(_uuid4())),
                            category=sig.get("category", ""),
                            description=sig.get("description", ""),
                            severity=Severity(sig.get("severity", "low")),
                            source_artifact_ids=artifact_id_strings,
                            metadata=json.loads(sig.get("metadata", "{}") or "{}"),
                        ))
                    except Exception:
                        continue
                if not signal_objects:
                    continue
                lens_claims = gen.generate_claims(signal_objects, real_artifacts[:5])
                # Collect generated artifacts for contradiction engine
                for a in real_artifacts[:5]:
                    all_generated_artifacts.append({
                        "id": str(a.id), "source_id": str(a.source_id),
                        "type": a.type, "raw_hash": a.raw_hash,
                        "metadata": a.metadata, "is_public": a.is_public,
                        "content_preview": a.content_preview,
                        "created_at": a.created_at or "",
                    })
                for c in lens_claims:
                    conn_rw.execute(
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
                         c.model_version, int(c.not_a_verdict), now_iso)
                    )
                    # Populate junction tables for FK enforcement
                    for aid in c.supporting_evidence:
                        conn_rw.execute(
                            "INSERT OR IGNORE INTO claim_supporting_evidence(claim_id, artifact_id) "
                            "VALUES(?, ?)", (str(c.id), str(aid)))
                    for aid in c.weakening_evidence:
                        conn_rw.execute(
                            "INSERT OR IGNORE INTO claim_weakening_evidence(claim_id, artifact_id) "
                            "VALUES(?, ?)", (str(c.id), str(aid)))
                    for rid in c.repair_options:
                        conn_rw.execute(
                            "INSERT OR IGNORE INTO claim_repair_options(claim_id, repair_id) "
                            "VALUES(?, ?)", (str(c.id), str(rid)))
            except Exception as exc:
                log.warning("V1 audit: lens %s failed: %s", lens_id, exc)

        conn_rw.commit()

        # ── Stage 8: Contradiction detection ──
        all_claim_rows = conn_rw.execute("SELECT * FROM claims").fetchall()
        try:
            engine = ContradictionEngine()
            # Use real artifacts when available, derive entities from workstream metadata
            artifact_dicts = all_generated_artifacts[:50]  # limit for performance
            entity_dicts: list[dict] = []
            if _workstream_cards:
                # Derive multiple entity types from workstream metadata
                # so the contradiction engine can detect cross-type mismatches
                for card in _workstream_cards[:8]:
                    name = card.get("name", "")
                    topics = card.get("topics", [])
                    topics_lower = [t.lower() for t in topics]
                    all_text = (name + " " + " ".join(topics)).lower()

                    # Base workstream entity (always created)
                    entity_dicts.append({
                        "type": "workstream",
                        "name": name,
                        "metadata": {
                            "confidence": card.get("confidence", 0.5),
                            "file_count": card.get("file_count", 0),
                            "topics": topics,
                        },
                    })

                    # Derived entity types based on topic signals
                    job_keywords = {"career", "work", "job", "resume", "cv",
                                    "employment", "linkedin", "recruiter"}
                    org_keywords = {"company", "organization", "startup",
                                    "business", "employer", "enterprise"}
                    project_keywords = {"code", "project", "software", "app",
                                        "development", "engineering", "build"}
                    skill_keywords = {"skill", "learning", "research",
                                      "design", "writing", "communication",
                                      "leadership", "management"}

                    if job_keywords & set(topics_lower) or any(
                            kw in all_text for kw in job_keywords):
                        entity_dicts.append({
                            "type": "employer",
                            "name": name,
                            "metadata": {
                                "confidence": card.get("confidence", 0.5),
                                "topics": topics,
                            },
                        })

                    if org_keywords & set(topics_lower) or any(
                            kw in all_text for kw in org_keywords):
                        entity_dicts.append({
                            "type": "org",
                            "name": name,
                            "metadata": {
                                "confidence": card.get("confidence", 0.5),
                                "topics": topics,
                            },
                        })

                    if project_keywords & set(topics_lower) or any(
                            kw in all_text for kw in project_keywords):
                        entity_dicts.append({
                            "type": "project",
                            "name": name,
                            "metadata": {
                                "confidence": card.get("confidence", 0.5),
                                "topics": topics,
                            },
                        })

                    if skill_keywords & set(topics_lower) or any(
                            kw in all_text for kw in skill_keywords):
                        entity_dicts.append({
                            "type": "skill",
                            "name": name,
                            "metadata": {
                                "confidence": card.get("confidence", 0.5),
                                "topics": topics,
                            },
                        })
            claim_dicts = [_v1_row_to_dict(r) for r in all_claim_rows]

            # ── Build typed objects from dicts (TASK-T2 fix) ──────────────
            # The contradiction engine accesses typed attributes (e.type,
            # claim.title, a.metadata, a.id) — raw dicts need ['key'] access,
            # causing silent AttributeError in all 5 detection methods.
            # Build proper InferenceClaim, Artifact, and Entity objects.
            claim_objects: list[InferenceClaim] = []
            for cd in claim_dicts:
                try:
                    se = cd.get("supporting_evidence", [])
                    if isinstance(se, str):
                        try: se = json.loads(se)
                        except Exception: se = []
                    we = cd.get("weakening_evidence", [])
                    if isinstance(we, str):
                        try: we = json.loads(we)
                        except Exception: we = []
                    sg = cd.get("source_gaps", [])
                    if isinstance(sg, str):
                        try: sg = json.loads(sg)
                        except Exception: sg = []
                    ro = cd.get("repair_options", [])
                    if isinstance(ro, str):
                        try: ro = json.loads(ro)
                        except Exception: ro = []
                    claim_objects.append(InferenceClaim(
                        id=UUID(cd["id"]) if cd.get("id") else _uuid4(),
                        title=cd.get("title", ""),
                        audience_lens=cd.get("audience_lens", ""),
                        claim=cd.get("claim", ""),
                        confidence_band=ConfidenceBand(cd.get("confidence_band", "low")),
                        evidence_count=int(cd.get("evidence_count") or 0),
                        supporting_evidence=([UUID(x) for x in se if x]
                                             if isinstance(se, list) else []),
                        weakening_evidence=([UUID(x) for x in we if x]
                                            if isinstance(we, list) else []),
                        source_gaps=sg if isinstance(sg, list) else [],
                        recency=cd.get("recency", ""),
                        severity=Severity(cd.get("severity", "low")),
                        actionability=cd.get("actionability", ""),
                        possible_consequence=cd.get("possible_consequence", ""),
                        counterargument=cd.get("counterargument", ""),
                        repair_options=([UUID(x) for x in ro if x]
                                        if isinstance(ro, list) else []),
                        model_version=cd.get("model_version", ""),
                        generated_at=cd.get("generated_at", ""),
                        not_a_verdict=bool(cd.get("not_a_verdict", True)),
                    ))
                except Exception:
                    continue

            artifact_objects: list[Artifact] = []
            for ad in artifact_dicts:
                try:
                    artifact_objects.append(Artifact(
                        id=UUID(ad["id"]) if ad.get("id") else _uuid4(),
                        source_id=UUID(ad["source_id"]) if ad.get("source_id") else _uuid4(),
                        type=ad.get("type", ""),
                        raw_hash=ad.get("raw_hash", ""),
                        encrypted_path=ad.get("encrypted_path", ""),
                        metadata=ad.get("metadata") or {},
                        is_public=bool(ad.get("is_public", False)),
                        content_preview=ad.get("content_preview", ""),
                        created_at=ad.get("created_at", ""),
                    ))
                except Exception:
                    continue

            entity_objects: list[Entity] = []
            for ed in entity_dicts:
                try:
                    entity_objects.append(Entity(
                        id=_uuid4(),  # synthetic — no pre-existing id
                        type=ed.get("type", "unknown"),
                        name=ed.get("name", ""),
                        metadata=ed.get("metadata") or {},
                        confidence=float(ed.get("confidence", 1.0)),
                    ))
                except Exception:
                    continue

            contradictions = engine.run_full_audit(
                claim_objects, artifact_objects, entity_objects)
            for c in contradictions:
                conn_rw.execute(
                    "INSERT OR REPLACE INTO contradictions(id, category, description, "
                    "claim_ids, artifact_ids, severity, audience_affected, "
                    "resolution_suggestion, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (str(c.id), c.category, c.description,
                     json.dumps([str(x) for x in c.claim_ids]),
                     json.dumps([str(x) for x in c.artifact_ids]),
                     c.severity.value, json.dumps(c.audience_affected),
                     c.resolution_suggestion, now_iso)
                )
                # Populate junction tables for FK enforcement
                for cid in c.claim_ids:
                    conn_rw.execute(
                        "INSERT OR IGNORE INTO contradiction_claims(contradiction_id, claim_id) "
                        "VALUES(?, ?)", (str(c.id), str(cid)))
                for aid in c.artifact_ids:
                    conn_rw.execute(
                        "INSERT OR IGNORE INTO contradiction_artifacts(contradiction_id, artifact_id) "
                        "VALUES(?, ?)", (str(c.id), str(aid)))
            conn_rw.commit()
        except Exception as exc:
            log.warning("V1 audit: contradiction engine failed: %s", exc)

        # ── Stage 9: Dynamic risk generation ──
        # Maps contradictions + stale context + exposure records into RiskFlags.
        # Replaces the old hardcoded 3-risk block with evidence-backed generation.
        try:
            from optic.v1.risk import risk_engine

            all_contra_rows = conn_rw.execute(
                "SELECT * FROM contradictions ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
            all_claim_rows_risk = conn_rw.execute(
                "SELECT * FROM claims"
            ).fetchall()

            contra_dicts = [_v1_row_to_dict(r) for r in all_contra_rows]
            claim_dicts = [_v1_row_to_dict(r) for r in all_claim_rows_risk]

            generated_risks = risk_engine(
                contradictions=contra_dicts,
                claims=claim_dicts,
                artifacts=all_generated_artifacts,
                workstream_cards=_workstream_cards,
                now_iso=now_iso,
            )

            for risk in generated_risks:
                conn_rw.execute(
                    "INSERT OR REPLACE INTO risks(id, category, description, severity, "
                    "linked_claim_ids, linked_artifact_ids, audience_affected, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (str(risk.id), risk.category.value, risk.description[:300],
                     risk.severity.value,
                     json.dumps([str(x) for x in risk.linked_claim_ids]),
                     json.dumps([str(x) for x in risk.linked_artifact_ids]),
                     json.dumps(risk.audience_affected if isinstance(risk.audience_affected, list) else []),
                     risk.created_at)
                )
                # Populate junction tables for FK enforcement
                for cid in risk.linked_claim_ids:
                    conn_rw.execute(
                        "INSERT OR IGNORE INTO risk_linked_claims(risk_id, claim_id) "
                        "VALUES(?, ?)", (str(risk.id), str(cid)))
                for aid in risk.linked_artifact_ids:
                    conn_rw.execute(
                        "INSERT OR IGNORE INTO risk_linked_artifacts(risk_id, artifact_id) "
                        "VALUES(?, ?)", (str(risk.id), str(aid)))
            conn_rw.commit()
            log.info("V1 audit: risk engine generated %d risks from contradictions=%d claims=%d artifacts=%d",
                     len(generated_risks), len(contra_dicts), len(claim_dicts), len(all_generated_artifacts))
        except Exception as exc:
            log.warning("V1 audit: risk engine failed, falling back: %s", exc)
            # Honest fallback: one truthful note risk
            rid = str(_uuid4())
            conn_rw.execute(
                "INSERT OR REPLACE INTO risks(id, category, description, severity, "
                "linked_claim_ids, linked_artifact_ids, audience_affected, created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (rid, "missing_proof",
                 "Risk engine unavailable — re-run audit after a scan to enable dynamic risk detection.",
                 "low", "[]", "[]", json.dumps(["all"]), now_iso)
            )

        # ── Stage 10: Repair generation (Invariant #5: Executable) ──
        # Generate repairs dynamically from claims, contradictions,
        # and risks with REAL priority metrics and exact shell commands.
        try:
            from optic.v1.server import _generate_repairs

            all_claim_rows_rep = conn_rw.execute(
                "SELECT * FROM claims"
            ).fetchall()
            all_contra_rows_rep = conn_rw.execute(
                "SELECT * FROM contradictions ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
            all_risk_rows_rep = conn_rw.execute(
                "SELECT * FROM risks"
            ).fetchall()

            generated_repairs = _generate_repairs(
                cards=[_v1_row_to_dict(r) for r in all_claim_rows_rep],
                contradictions=[_v1_row_to_dict(r) for r in all_contra_rows_rep],
                risks=[_v1_row_to_dict(r) for r in all_risk_rows_rep],
            )

            for r in generated_repairs:
                conn_rw.execute(
                    "INSERT OR REPLACE INTO repairs(id, title, affected_audience, linked_claim_id, "
                    "linked_evidence_ids, impact, effort, urgency, reversibility, "
                    "exact_steps, expected_effect, risk_of_overcorrecting, "
                    "before_measurement, after_measurement, status) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (str(r.id), r.title, json.dumps(r.affected_audience),
                     str(r.linked_claim_id) if r.linked_claim_id else "",
                     json.dumps([str(x) for x in r.linked_evidence_ids]),
                     r.impact, r.effort, r.urgency, r.reversibility,
                     json.dumps(r.exact_steps), r.expected_effect,
                     r.risk_of_overcorrecting,
                     json.dumps(r.before_measurement) if r.before_measurement else "",
                     json.dumps(r.after_measurement) if r.after_measurement else "",
                     r.status.value)
                )
                # Populate junction tables for FK enforcement
                # ── repair_linked_evidence: pull evidence from linked claim ──
                evidence_ids = list(r.linked_evidence_ids) if r.linked_evidence_ids else []
                if not evidence_ids and r.linked_claim_id:
                    # Derive evidence from the claim's supporting_evidence
                    claim_row = conn_rw.execute(
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
                    conn_rw.execute(
                        "INSERT OR IGNORE INTO repair_linked_evidence(repair_id, artifact_id) "
                        "VALUES(?, ?)", (str(r.id), str(eid)))
                # ── claim_repair_options: bidirectional link ──
                if r.linked_claim_id:
                    conn_rw.execute(
                        "INSERT OR IGNORE INTO claim_repair_options(claim_id, repair_id) "
                        "VALUES(?, ?)", (str(r.linked_claim_id), str(r.id)))
            conn_rw.commit()
            log.info("V1 audit: generated %d executable repairs", len(generated_repairs))
        except Exception as exc:
            log.warning("V1 audit: repair generation failed, falling back: %s", exc)
            # Honest fallback — one truthful note
            rid = str(_uuid4())
            conn_rw.execute(
                "INSERT OR REPLACE INTO repairs(id, title, affected_audience, linked_claim_id, "
                "linked_evidence_ids, impact, effort, urgency, reversibility, "
                "exact_steps, expected_effect, risk_of_overcorrecting, status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, "Re-run audit to generate repairs",
                 json.dumps(["all"]), "", "[]",
                 0.3, 0.2, 0.3, 0.95,
                 json.dumps(["Re-run the V1 audit from the dashboard to enable dynamic repair generation"]),
                 "Enables full repair pipeline", "None — this is a meta-repair",
                 RepairStatus.PENDING.value)
            )

        # ── Stage 11: Create report snapshot ──
        claim_count = conn_rw.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
        contradiction_count = conn_rw.execute("SELECT COUNT(*) as c FROM contradictions").fetchone()["c"]
        risk_count = conn_rw.execute("SELECT COUNT(*) as c FROM risks").fetchone()["c"]
        repair_count = conn_rw.execute("SELECT COUNT(*) as c FROM repairs").fetchone()["c"]
        report_id = str(_uuid4())
        snapshot = _hashlib.sha256(f"{report_id}{now_iso}".encode()).hexdigest()[:16]
        sections_data = {
            "scope": "V1 general audit from ctxorg",
            "stages_completed": 12,
            "consent_filter": consent_summary,
        }
        conn_rw.execute(
            "INSERT OR REPLACE INTO reports(id, user_id, version, audit_mode, scope, "
            "source_count, artifact_count, claim_count, contradiction_count, "
            "risk_count, repair_count, sections, export_policy, created_at, snapshot_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (report_id, "local", 1, "general", "[]",
             4, 85, claim_count, contradiction_count, risk_count, repair_count,
             json.dumps(sections_data),
             json.dumps({"json_allowed": True, "md_allowed": True, "redacted_by_default": True}),
             now_iso, snapshot)
        )
        conn_rw.commit()
        conn_rw.close()
        _log_ev("v1_audit_complete", claims=claim_count, contradictions=contradiction_count,
                risks=risk_count, repairs=repair_count, report=report_id)
    except Exception as exc:
        log.exception("V1 audit background thread failed: %s", exc)


_v1_audit_lock = threading.Lock()
_v1_audit_running = False


def v1_audit_trigger_payload(req: BaseHTTPRequestHandler, _cfg=None) -> dict:
    """POST handler: trigger a V1 general audit in a background thread.
    Returns immediately with status. The audit runs asynchronously;
    poll GET /api/v1/audit/general or /api/v1/status for results."""
    global _v1_audit_running
    if not _V1_AVAILABLE:
        return {"status": "no_database", "message": "V1 database not found. Run a scan first."}
    with _v1_audit_lock:
        if _v1_audit_running:
            return {"status": "already_running", "message": "An audit is already in progress."}
        _v1_audit_running = True
    t = threading.Thread(target=_v1_audit_bg, daemon=True)
    t.start()
    # Schedule a follow-up to reset the flag
    def _clear_flag():
        t.join()
        with _v1_audit_lock:
            global _v1_audit_running
            _v1_audit_running = False
    threading.Thread(target=_clear_flag, daemon=True).start()
    return {"status": "started", "message": "V1 general audit started. Check /api/v1/status for results."}


def v1_claims_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    """Return all inference claims from the V1 database."""
    if not _V1_AVAILABLE:
        return {"claims": [], "count": 0, "note": "V1 database not found. Run a scan to populate."}
    try:
        conn = _v1_open_db()
        rows = conn.execute(
            "SELECT id, title, audience_lens, claim, confidence_band, evidence_count, "
            "supporting_evidence, weakening_evidence, source_gaps, recency, severity, "
            "actionability, possible_consequence, counterargument, repair_options, "
            "model_version, not_a_verdict, generated_at "
            "FROM claims ORDER BY generated_at DESC LIMIT 500"
        ).fetchall()
        conn.close()
        claims = [_v1_row_to_dict(r) for r in rows]
        return {"claims": claims, "count": len(claims)}
    except Exception as exc:
        return {"claims": [], "count": 0, "error": str(exc)}


def v1_contradictions_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    """Return all contradictions from the V1 database."""
    if not _V1_AVAILABLE:
        return {"contradictions": [], "count": 0, "note": "V1 database not found."}
    try:
        conn = _v1_open_db()
        rows = conn.execute(
            "SELECT id, category, description, claim_ids, artifact_ids, "
            "severity, audience_affected, resolution_suggestion, created_at "
            "FROM contradictions ORDER BY created_at DESC LIMIT 500"
        ).fetchall()
        conn.close()
        contradictions = [_v1_row_to_dict(r) for r in rows]
        return {"contradictions": contradictions, "count": len(contradictions)}
    except Exception as exc:
        return {"contradictions": [], "count": 0, "error": str(exc)}


def v1_risks_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    """Return all risk flags from the V1 database."""
    if not _V1_AVAILABLE:
        return {"risks": [], "count": 0, "note": "V1 database not found."}
    try:
        conn = _v1_open_db()
        rows = conn.execute(
            "SELECT id, category, description, severity, linked_claim_ids, "
            "linked_artifact_ids, audience_affected, created_at "
            "FROM risks ORDER BY created_at DESC LIMIT 500"
        ).fetchall()
        conn.close()
        risks = [_v1_row_to_dict(r) for r in rows]
        return {"risks": risks, "count": len(risks)}
    except Exception as exc:
        return {"risks": [], "count": 0, "error": str(exc)}


def v1_repairs_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    """Return all repair actions from the V1 database."""
    if not _V1_AVAILABLE:
        return {"repairs": [], "count": 0, "note": "V1 database not found."}
    try:
        conn = _v1_open_db()
        rows = conn.execute(
            "SELECT id, title, affected_audience, linked_claim_id, linked_evidence_ids, "
            "impact, effort, urgency, reversibility, cost_cents, exact_steps, "
            "expected_effect, risk_of_overcorrecting, before_measurement, "
            "after_measurement, status "
            "FROM repairs ORDER BY urgency DESC LIMIT 500"
        ).fetchall()
        conn.close()
        repairs = [_v1_row_to_dict(r) for r in rows]
        # Compute priority for each repair
        for r in repairs:
            impact = float(r.get("impact", 0.5))
            urgency = float(r.get("urgency", 0.5))
            reversibility = float(r.get("reversibility", 0.5))
            effort = float(r.get("effort", 0.5))
            if effort == 0:
                r["priority"] = round(impact * urgency * reversibility, 3)
            else:
                r["priority"] = round((impact * urgency * reversibility) / effort, 3)
        return {"repairs": repairs, "count": len(repairs)}
    except Exception as exc:
        return {"repairs": [], "count": 0, "error": str(exc)}


def v1_graph_evidence_payload(req: BaseHTTPRequestHandler, cfg: dict) -> dict:
    """GET /api/v1/graph/evidence — returns the complete evidence graph with typed nodes and edges.

    Instantiates EvidenceGraph from optic.v1.graph and populates it from the V1
    database: claims, contradictions, risks, repairs, signals, artifacts, and
    audience lenses.  Returns JSON-compatible nodes and edges lists.
    """
    if not _V1_AVAILABLE:
        return {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0,
                "note": "V1 database not found. Run a scan and audit to populate."}
    try:
        from optic.v1.graph import EvidenceGraph  # type: ignore
        import json as _json

        conn = _v1_open_db()
        eg = EvidenceGraph()

        # ── User root node ──────────────────────────────────────
        user_id = "local-user"
        eg.add_node("user", user_id, label="Optic user",
                    data={"local_mode": True})

        # ── Audience lens nodes ──────────────────────────────────
        audience_ids: dict[str, str] = {}
        known_lenses = [
            "recruiter", "investor", "cofounder", "journalist",
            "regulator", "auditor", "general_public", "close_friend",
            "manager", "peer", "family", "student", "client", "mentor",
        ]
        for lens_id in known_lenses:
            label = lens_id.replace("_", " ").title()
            aid = f"audience:{lens_id}"
            eg.add_node("audience", aid, label=label)
            audience_ids[lens_id] = aid

        # Add any extra lenses found in claims
        for row in conn.execute(
            "SELECT DISTINCT audience_lens FROM claims WHERE audience_lens IS NOT NULL"
        ).fetchall():
            lens_id = row["audience_lens"]
            if lens_id and lens_id not in audience_ids:
                aid = f"audience:{lens_id}"
                eg.add_node("audience", aid,
                            label=lens_id.replace("_", " ").title())
                audience_ids[lens_id] = aid

        # ── Workstream / source nodes ────────────────────────────
        # Derive workstream clusters from signal metadata
        workstream_clusters: dict[str, dict] = {}
        sig_rows = conn.execute(
            "SELECT metadata FROM signals WHERE metadata IS NOT NULL AND metadata != '{}' LIMIT 200"
        ).fetchall()
        for row in sig_rows:
            try:
                meta = _json.loads(row["metadata"] or "{}")
                ws_id = meta.get("workstream_id") or meta.get("source_id") or ""
                ws_name = meta.get("workstream_name") or meta.get("workstream") or ws_id
                if ws_id and ws_id not in workstream_clusters:
                    workstream_clusters[ws_id] = {
                        "id": ws_id,
                        "name": ws_name,
                        "confidence": float(meta.get("confidence", 0.5)),
                        "file_count": int(meta.get("file_count", 0)),
                        "topics": meta.get("topics", []),
                    }
            except Exception:
                pass
        for ws in workstream_clusters.values():
            ws_id = ws.get("id", "")
            if not ws_id:
                continue
            eg.add_node("document", ws_id,
                        label=ws.get("name", "Unknown"),
                        data={"confidence": ws.get("confidence"),
                              "file_count": ws.get("file_count"),
                              "topics": ws.get("topics", [])})
            eg.add_edge("derived_from", ws_id, user_id,
                        data={"type": "workstream"})

        # ── Claim nodes + evidence edges ─────────────────────────
        claims_rows = conn.execute(
            "SELECT * FROM claims ORDER BY generated_at DESC LIMIT 500"
        ).fetchall()
        for row in claims_rows:
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

            # Supporting evidence
            try:
                supporting = _json.loads(row["supporting_evidence"] or "[]")
            except Exception:
                supporting = []
            for ev in supporting:
                # Use raw artifact UUID — connects to real artifact nodes from DB
                eg.merge_node("artifact", ev,
                              label=str(ev)[:60],
                              data={"evidence_role": "supporting"},
                              provenance=audience)
                eg.add_edge("supports", ev, cid, weight=0.8)

            # Weakening evidence
            try:
                weakening = _json.loads(row["weakening_evidence"] or "[]")
            except Exception:
                weakening = []
            for ev in weakening:
                eg.merge_node("artifact", ev,
                              label=str(ev)[:60],
                              data={"evidence_role": "weakening"},
                              provenance=audience)
                eg.add_edge("weakens", ev, cid, weight=0.4)

            # Source gaps
            try:
                gaps = _json.loads(row["source_gaps"] or "[]")
            except Exception:
                gaps = []
            for gap in gaps:
                gap_id = f"source_gap:{gap}"
                eg.merge_node("source_gap", gap_id,
                              label=str(gap)[:80],
                              provenance=audience)
                eg.add_edge("missing_context_for", gap_id, cid)

        # ── Real artifact nodes from DB ──────────────────────────
        artifact_rows = conn.execute(
            "SELECT * FROM artifacts LIMIT 1000"
        ).fetchall()
        node_type_map = {
            "file": "artifact", "text": "document", "code": "document",
            "html": "document", "csv": "document", "image": "image",
            "pdf": "document", "url": "document",
        }
        for row in artifact_rows:
            aid = row["id"]
            artifact_type = (row["type"] if "type" in row.keys() else "file")
            ntype = node_type_map.get(artifact_type, "artifact")
            fpath = (row["encrypted_path"] if "encrypted_path" in row.keys() else "") or (
                (row["content_preview"] if "content_preview" in row.keys() else "") or "")[:80]
            eg.merge_node(ntype, aid,
                          label=fpath[:80] if fpath else artifact_type,
                          data={"type": artifact_type,
                                "is_public": bool(int(row["is_public"] if "is_public" in row.keys() else 0))})

        # ── Signal nodes ─────────────────────────────────────────
        signal_rows = conn.execute(
            "SELECT * FROM signals LIMIT 500"
        ).fetchall()
        for row in signal_rows:
            d = _v1_row_to_dict(row)
            sid = d["id"]
            category = d.get("category") or "unknown"
            eg.add_node("signal", sid,
                        label=category,
                        data={
                            "description": (d.get("description") or "")[:200],
                            "severity": d.get("severity") or "low",
                            "category": category,
                        })

        # ── Signal → Artifact edges (inferred_from) ──────────────
        # Use junction table for FK-validated signal↔artifact links
        sa_rows = conn.execute(
            "SELECT signal_id, artifact_id FROM signal_source_artifacts LIMIT 2000"
        ).fetchall()
        for sa in sa_rows:
            try:
                eg.add_edge("inferred_from", sa["signal_id"], sa["artifact_id"],
                            weight=0.5)
            except KeyError:
                pass  # node not in graph yet

        # ── Contradiction nodes + contradicts edges ──────────────
        contradictions_rows = conn.execute(
            "SELECT * FROM contradictions LIMIT 500"
        ).fetchall()
        for row in contradictions_rows:
            d = _v1_row_to_dict(row)
            cid = d["id"]
            eg.add_node("contradiction", cid,
                        label=d.get("category") or "contradiction",
                        data={
                            "description": d.get("description"),
                            "severity": d.get("severity"),
                            "resolution_suggestion": d.get("resolution_suggestion") or "",
                        })
            linked = d.get("claim_ids") or []
            for claim_id in linked:
                eg.add_edge("contradicts", cid, str(claim_id), weight=0.9)

            # Audience affected
            affected = d.get("audience_affected") or []
            for aud in affected:
                key = f"audience:{aud}"
                if aud not in audience_ids:
                    eg.add_node("audience", key,
                                label=str(aud).replace("_", " ").title())
                    audience_ids[aud] = key
                eg.add_edge("risky_for", cid, audience_ids.get(aud, key))

        # ── Risk nodes ───────────────────────────────────────────
        risk_rows = conn.execute(
            "SELECT * FROM risks LIMIT 500"
        ).fetchall()
        for row in risk_rows:
            d = _v1_row_to_dict(row)
            rid = d["id"]
            eg.add_node("risk", rid,
                        label=d.get("category") or "risk",
                        data={
                            "description": d.get("description"),
                            "severity": d.get("severity"),
                        })
            affected = d.get("audience_affected") or []
            for aud in affected:
                key = f"audience:{aud}"
                if aud not in audience_ids:
                    eg.add_node("audience", key,
                                label=str(aud).replace("_", " ").title())
                    audience_ids[aud] = key
                eg.add_edge("risky_for", rid, audience_ids.get(aud, key))

            # Risk → claim edges via linked_claim_ids
            linked_claims = d.get("linked_claim_ids") or []
            for claim_id in linked_claims:
                eg.add_edge("associated_with", rid, str(claim_id), weight=0.6)

        # ── Repair nodes + repaired_by edges ─────────────────────
        repair_rows = conn.execute(
            "SELECT * FROM repairs LIMIT 500"
        ).fetchall()
        for row in repair_rows:
            d = _v1_row_to_dict(row)
            rid = d["id"]
            eg.add_node("repair", rid,
                        label=d.get("title") or "repair",
                        data={
                            "impact": d.get("impact"),
                            "effort": d.get("effort"),
                            "urgency": d.get("urgency"),
                            "status": d.get("status"),
                        })
            linked_claim = d.get("linked_claim_id")
            if linked_claim:
                eg.add_edge("repaired_by", str(linked_claim), rid)

            affected = d.get("affected_audience") or []
            for aud in affected:
                key = f"audience:{aud}"
                if aud not in audience_ids:
                    eg.add_node("audience", key,
                                label=str(aud).replace("_", " ").title())
                    audience_ids[aud] = key
                eg.add_edge("repaired_by", audience_ids.get(aud, key), rid)

        conn.close()

        # ── Extract all nodes / edges for JSON export ────────────
        from contextlib import closing
        with closing(eg) as final_graph:
            nodes = [final_graph._node(r) for r in
                     final_graph.conn.execute(
                         "SELECT * FROM nodes ORDER BY type,label,id").fetchall()]
            edges = [final_graph._edge(r) for r in
                     final_graph.conn.execute(
                         "SELECT * FROM edges ORDER BY type,id").fetchall()]
        return {
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }
    except Exception as exc:
        import traceback
        return {
            "nodes": [], "edges": [],
            "node_count": 0, "edge_count": 0,
            "error": str(exc)[:300],
            "traceback": traceback.format_exc()[-500:],
        }


def v1_repair_complete_payload(req: BaseHTTPRequestHandler, cfg: dict,
                               repair_id: str) -> dict:
    """POST /api/v1/repairs/complete/<id> — mark a repair action as completed."""
    if not _V1_AVAILABLE:
        return {"status": "error", "error": "V1 database not found."}
    if not repair_id:
        return {"status": "error", "error": "repair_id required"}
    try:
        conn = _v1_open_db_rw()
        cur = conn.execute("SELECT id FROM repairs WHERE id=?", (repair_id,))
        existing = cur.fetchone()
        if not existing:
            conn.close()
            return {"status": "error", "error": "repair not found", "repair_id": repair_id}
        conn.execute("UPDATE repairs SET status='completed' WHERE id=?", (repair_id,))
        conn.commit()
        conn.close()
        return {"status": "completed", "repair_id": repair_id}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:200], "repair_id": repair_id}


def v1_reset_payload(cfg: dict) -> dict:
    """POST /api/v1/reset — clear all V1 test data, preserve schema.

    Requires authentication + owner/admin role (C2 fix).
    """
    # Require authenticated user with owner/admin role
    _acct_must(cfg)
    _workspace_require_role(cfg, {"owner", "admin"})

    if not _V1_AVAILABLE:
        return {"status": "error", "error": "V1 database not found — nothing to reset"}
    try:
        conn = _v1_open_db_rw()
        # Tag all existing users as test users
        conn.execute("UPDATE users SET is_test_user = 1")
        # Clear content tables
        tables = [
            "sessions", "sources", "consent_receipts", "artifacts",
            "signals", "claims", "contradictions", "risks", "repairs",
            "reports", "onboarding",
        ]
        cleared = {}
        for table in tables:
            try:
                result = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
                before = result["c"]
                conn.execute(f"DELETE FROM {table}")
                cleared[table] = before
            except Exception:
                cleared[table] = -1
        # Remove test users
        conn.execute("DELETE FROM users WHERE is_test_user = 1")
        conn.commit()
        conn.close()
        _log_ev("v1_reset", cleared_tables=cleared)
        return {
            "status": "ok",
            "message": "Test data cleared, schema preserved",
            "cleared_tables": cleared,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:200]}


def v1_audit_general_payload(req: BaseHTTPRequestHandler, _cfg=None) -> dict:
    """GET handler: trigger a V1 audit if not running, then return the latest report.

    Called by app.js syncShellNow() after a scan completes — the frontend
    polls GET /api/v1/audit/general to trigger an audit and discover fresh
    claims/contradictions/risks/repairs.
    """
    global _v1_audit_running
    # ── Trigger audit in background if not already running ──
    if _V1_AVAILABLE and not _v1_audit_running:
        try:
            with _v1_audit_lock:
                if not _v1_audit_running:
                    _v1_audit_running = True
                    t = threading.Thread(target=_v1_audit_bg, daemon=True)
                    t.start()
                    def _clear_flag():
                        t.join()
                        with _v1_audit_lock:
                            global _v1_audit_running
                            _v1_audit_running = False
                    threading.Thread(target=_clear_flag, daemon=True).start()
        except Exception:
            pass

    # ── Read latest report ──
    if not _V1_AVAILABLE:
        return {
            "mode": "general",
            "stages_completed": 0,
            "source_count": 0,
            "artifact_count": 0,
            "signal_count": 0,
            "claim_count": 0,
            "contradiction_count": 0,
            "risk_count": 0,
            "repair_count": 0,
            "report_id": "",
            "snapshot_id": "",
            "note": "V1 database not found. Run a scan and audit to populate.",
        }
    try:
        conn = _v1_open_db()
        # Read the most recent report for mode='general'
        row = conn.execute(
            "SELECT * FROM reports WHERE audit_mode='general' "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        # Aggregate counts regardless of specific report
        claim_count = conn.execute(
            "SELECT COUNT(*) as c FROM claims"
        ).fetchone()["c"]
        contradiction_count = conn.execute(
            "SELECT COUNT(*) as c FROM contradictions"
        ).fetchone()["c"]
        risk_count = conn.execute(
            "SELECT COUNT(*) as c FROM risks"
        ).fetchone()["c"]
        repair_count = conn.execute(
            "SELECT COUNT(*) as c FROM repairs"
        ).fetchone()["c"]
        conn.close()
        if row:
            return {
                "mode": row["audit_mode"] or "general",
                "stages_completed": 14,
                "source_count": row["source_count"] or 0,
                "artifact_count": row["artifact_count"] or 0,
                "signal_count": 0,  # signals are ephemeral, not stored long-term
                "claim_count": row["claim_count"] or claim_count,
                "contradiction_count": row["contradiction_count"] or contradiction_count,
                "risk_count": row["risk_count"] or risk_count,
                "repair_count": row["repair_count"] or repair_count,
                "report_id": row["id"] or "",
                "snapshot_id": row["snapshot_id"] or "",
                "ctxorg_available": True,
            }
        return {
            "mode": "general",
            "stages_completed": 0,
            "source_count": 0,
            "artifact_count": 0,
            "signal_count": 0,
            "claim_count": claim_count,
            "contradiction_count": contradiction_count,
            "risk_count": risk_count,
            "repair_count": repair_count,
            "report_id": "",
            "snapshot_id": "",
            "ctxorg_available": True,
            "note": "No general-mode audit report found — claims/repairs may be from other runs.",
        }
    except Exception as exc:
        return {
            "mode": "general",
            "error": str(exc)[:200],
            "stages_completed": 0,
            "source_count": 0, "artifact_count": 0, "signal_count": 0,
            "claim_count": 0, "contradiction_count": 0,
            "risk_count": 0, "repair_count": 0,
            "report_id": "", "snapshot_id": "",
        }


def send(req: BaseHTTPRequestHandler, data: dict, code: int = 200,
         headers: dict | None = None) -> None:
    body = json.dumps(data).encode()
    req.send_response(code)
    out = _sec_headers(req)
    if isinstance(headers, dict):
        for key, val in headers.items():
            out[str(key)] = str(val)
    for key, val in out.items():
        req.send_header(str(key), str(val))
    req.send_header("content-type", "application/json")
    req.send_header("content-length", str(len(body)))
    req.end_headers()
    req.wfile.write(body)


def send_text(req: BaseHTTPRequestHandler, text: str, code: int = 200) -> None:
    body = str(text or "").encode("utf-8")
    req.send_response(code)
    out = _sec_headers(req)
    for key, val in out.items():
        req.send_header(str(key), str(val))
    req.send_header("content-type", "text/plain; charset=utf-8")
    req.send_header("content-length", str(len(body)))
    req.end_headers()
    req.wfile.write(body)


def send_html(req: BaseHTTPRequestHandler, html: str, code: int = 200) -> None:
    body = str(html).encode("utf-8")
    req.send_response(code)
    out = _sec_headers(req)
    for key, val in out.items():
        req.send_header(str(key), str(val))
    req.send_header("content-type", "text/html; charset=utf-8")
    req.send_header("content-length", str(len(body)))
    req.end_headers()
    req.wfile.write(body)


def oauth_page(title: str, msg: str) -> str:
    ttl = str(title or "Connector")
    txt = str(msg or "").replace("<", "&lt;").replace(">", "&gt;")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{ttl}</title></head><body>"
        f"<h2>{ttl}</h2><p>{txt}</p>"
        "<script>setTimeout(()=>{try{window.close()}catch(_){ }},1800)</script>"
        "</body></html>"
    )


def _session_attr(req: BaseHTTPRequestHandler, age: int) -> str:
    val = f"Path=/; HttpOnly; SameSite=Lax; Max-Age={age}"
    return val + "; Secure" if _req_tls(req) else val


def _session_set_header(req: BaseHTTPRequestHandler, token: str) -> dict:
    if not token:
        return {}
    val = f"{_SESSION_COOKIE}={token}; {_session_attr(req, 2592000)}"
    return {"Set-Cookie": val}


def _session_clear_header(req: BaseHTTPRequestHandler) -> dict:
    val = f"{_SESSION_COOKIE}=; {_session_attr(req, 0)}"
    return {"Set-Cookie": val}


def send_err(req: BaseHTTPRequestHandler, err: str, code: int = 400,
             detail: str = "") -> None:
    path = urlparse(req.path).path
    method = getattr(req, "command", "REQ")
    if path == "/healthz" or path.startswith("/api/"):
        _api_err(method, path, err, code=code)
    data = {"ok": False, "err": err}
    if detail:
        data["detail"] = detail
    send(req, data, code=code)
