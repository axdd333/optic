"""Vana DataConnect ingestion — feeds DataConnect exports into the Optic
signal engine.

DataConnect (https://github.com/vana-com/data-connect) exports platform data
as JSON to the user's disk. Two ways that data reaches Optic:

  1. DESKTOP MODE — the Optic backend runs on the same machine as
     DataConnect and scans the export stores directly:
       {app_data_dir}/exported_data/{Company}/{Name}/{run_id}/{platform}_{ts}.json
         (macOS app_data_dir: ~/Library/Application Support/dev.dataconnect)
       ~/.dataconnect/data/{scope}/..., ~/.dataconnect/personal-server/data/...

  2. HOSTED MODE (tryoptic.app) — the customer drags export files into the
     onboarding page; the browser uploads them in batches to a per-user
     spool (`spool_add`), and the final batch triggers the audit
     (`spool_finalize`).

Each export file is a wrapper {company, name, run_id, timestamp, content},
where `content` follows the per-scope schemas from vana-com/data-connectors
(e.g. chatgpt.conversations → {conversations: [...], total}).

Profiles are keyed per user (uid derived from the session cookie) so a
hosted backend can serve many customers. Everything is processed in-place;
no third-party calls.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterator

# ── Tunables ────────────────────────────────────────────────────────────────

MAX_ITEM_CHARS = 8000        # chunk size for long texts (e.g. full conversations)
MAX_FILE_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_ITEMS = 2000     # safety cap on audited items per ingest run
MIN_TEXT_CHARS = 12          # ignore trivial fragments
WORST_OFFENDERS = 10
SPOOL_TTL_S = 6 * 3600       # abandoned upload sessions are reaped after this
SPOOL_MAX_ITEMS = 20000

_UID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Severity weights mirror SignalAuditor.audit_multiple
_SEVERITY_WEIGHTS = {
    "critical": 1.0,
    "high": 0.8,
    "medium": 0.5,
    "low": 0.3,
    "info": 0.1,
}

# Keys whose string values count as user-authored text in the generic walker
_TEXT_KEYS = {
    "content", "text", "caption", "bio", "description", "about",
    "body", "note", "summary", "headline", "memory",
}

# Collection keys that are consumption data → profiled, never audited.
# NOTE: compared against lowercased keys — keep every entry lowercase.
_PROFILE_ONLY_KEYS = {
    "history", "likes", "subscriptions", "playlists", "playlistitems",
    "savedtracks", "watchlater", "connections", "following", "orders",
    "ads", "starred", "skills", "languages", "activity", "readiness",
    "sleep", "nutrition",
}

_KNOWN_PLATFORMS = {
    "chatgpt", "claude", "linkedin", "instagram", "github", "spotify",
    "youtube", "shop", "shopify", "amazon", "doordash", "oura", "uber",
    "tinder", "heb", "icloud_notes", "openai", "anthropic", "meta",
    "google", "valve", "wholefoods",
}


def _safe_uid(uid: str | None) -> str:
    uid = (uid or "").strip()
    return uid if _UID_RE.match(uid) else "default"


# ── Discovery (desktop mode) ────────────────────────────────────────────────

def export_roots() -> list[Path]:
    """All candidate DataConnect export roots for the current OS."""
    home = Path.home()
    roots: list[Path] = [
        # Tauri app-data dir (identifier: dev.dataconnect)
        home / "Library" / "Application Support" / "dev.dataconnect" / "exported_data",
        home / ".local" / "share" / "dev.dataconnect" / "exported_data",
    ]
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "dev.dataconnect" / "exported_data")
    # Scoped stores (mirrors data-connect file_ops.rs candidates)
    for base in (home / ".dataconnect", home / "dev.dataconnect", home / "data-connect"):
        roots.append(base / "data")
        roots.append(base / "personal-server" / "data")
    return roots


def iter_export_files(roots: list[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.json")):
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path


def _load_export(path: Path) -> dict | None:
    """Parse an export file into {company, name, timestamp, content}."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return _coerce_export(raw, fallback=_guess_platform_from_path(path))


def _coerce_export(raw: Any, fallback: str = "unknown") -> dict | None:
    if not isinstance(raw, dict):
        return None
    if "content" in raw and isinstance(raw.get("content"), (dict, list)):
        return {
            "company": str(raw.get("company", "")) or fallback,
            "name": str(raw.get("name", "")) or fallback,
            "timestamp": raw.get("timestamp"),
            "content": raw["content"],
        }
    # Scoped-store files have no wrapper — the whole document is content
    return {"company": fallback, "name": fallback, "timestamp": None, "content": raw}


def _norm_platform(value: str) -> str:
    norm = value.lower().replace("-", "_").strip()
    return norm if norm in _KNOWN_PLATFORMS else ""


def _guess_platform_from_path(path: Path) -> str:
    for part in reversed(path.parts[:-1]):
        hit = _norm_platform(part)
        if hit:
            return hit
    return "unknown"


def _guess_platform_from_name(*candidates: str) -> str:
    """Infer platform from filename / wrapper fields (upload mode)."""
    for cand in candidates:
        if not cand:
            continue
        # exact token match first, then substring scan
        hit = _norm_platform(cand)
        if hit:
            return hit
        low = cand.lower()
        for known in _KNOWN_PLATFORMS:
            if known in low:
                return known
    for cand in candidates:
        if cand:
            return cand.lower()[:24]
    return "unknown"


def status(roots: list[Path] | None = None) -> dict:
    """Lightweight discovery summary for the onboarding poller (desktop mode)."""
    roots = roots or export_roots()
    platforms: dict[str, dict] = {}
    total_files = 0
    roots_found: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        roots_found.append(str(root))
        for path in root.rglob("*.json"):
            total_files += 1
            key = _guess_platform_from_path(path)
            entry = platforms.setdefault(key, {"platform": key, "files": 0, "latest_export": 0})
            entry["files"] += 1
            try:
                mtime = int(path.stat().st_mtime)
                entry["latest_export"] = max(entry["latest_export"], mtime)
            except OSError:
                pass
    return {
        "available": total_files > 0,
        "mode": "desktop" if total_files > 0 else "hosted",
        "roots_checked": [str(r) for r in roots],
        "roots_found": roots_found,
        "total_files": total_files,
        "platforms": sorted(platforms.values(), key=lambda p: -p["files"]),
    }


# ── Normalization ───────────────────────────────────────────────────────────

def _chunk(text: str) -> list[str]:
    text = text.strip()
    if len(text) <= MAX_ITEM_CHARS:
        return [text] if len(text) >= MIN_TEXT_CHARS else []
    return [text[i:i + MAX_ITEM_CHARS] for i in range(0, len(text), MAX_ITEM_CHARS)]


def _items_from_conversations(platform: str, convs: list) -> list[dict]:
    """chatgpt.conversations / claude.conversations → user-authored text."""
    items: list[dict] = []
    for conv in convs:
        if not isinstance(conv, dict):
            continue
        title = str(conv.get("title", ""))[:80]
        messages = conv.get("messages", [])
        if not isinstance(messages, list):
            continue
        user_text = "\n".join(
            str(m.get("content", "")) for m in messages
            if isinstance(m, dict) and m.get("role") == "user" and m.get("content")
        )
        for i, chunk in enumerate(_chunk(user_text)):
            items.append({
                "content": chunk,
                "summary": f"{platform}: {title or 'conversation'}"
                           + (f" (part {i + 1})" if i else ""),
                "platform": platform,
                "kind": "conversation",
                "metadata": {"platform": platform, "kind": "conversation",
                             "conversation_id": str(conv.get("id", "")), "title": title},
            })
    return items


def _items_from_string_list(platform: str, kind: str, values: list) -> list[dict]:
    items = []
    for v in values:
        text = v if isinstance(v, str) else (
            str(v.get("content") or v.get("text") or v.get("memory") or "")
            if isinstance(v, dict) else ""
        )
        for chunk in _chunk(text):
            items.append({
                "content": chunk,
                "summary": f"{platform} {kind}: {chunk[:60]}",
                "platform": platform,
                "kind": kind,
                "metadata": {"platform": platform, "kind": kind},
            })
    return items


def _items_from_generic(platform: str, node: Any, depth: int = 0) -> list[dict]:
    """Fallback: walk a structure collecting user-authored-looking text fields."""
    if depth > 6:
        return []
    items: list[dict] = []
    if isinstance(node, dict):
        for key, value in node.items():
            lk = str(key).lower()
            if lk in _PROFILE_ONLY_KEYS:
                continue
            if lk in _TEXT_KEYS and isinstance(value, str):
                for chunk in _chunk(value):
                    items.append({
                        "content": chunk,
                        "summary": f"{platform} {lk}: {chunk[:60]}",
                        "platform": platform,
                        "kind": lk,
                        "metadata": {"platform": platform, "kind": lk},
                    })
            else:
                items.extend(_items_from_generic(platform, value, depth + 1))
    elif isinstance(node, list):
        for value in node[:500]:
            items.extend(_items_from_generic(platform, value, depth + 1))
    return items


def _count_leaf_items(node: Any) -> int:
    if isinstance(node, list):
        return len(node)
    if isinstance(node, dict):
        return sum(_count_leaf_items(v) for v in node.values() if isinstance(v, (list, dict)))
    return 0


def normalize(platform: str, content: Any) -> tuple[list[dict], dict]:
    """Split export content into (audit_items, profile_stats)."""
    audit_items: list[dict] = []
    stats: dict[str, int] = defaultdict(int)

    if isinstance(content, dict):
        handled_keys: set[str] = set()
        for key, value in content.items():
            lk = str(key).lower()
            if lk == "conversations" and isinstance(value, list):
                audit_items.extend(_items_from_conversations(platform, value))
                stats["conversations"] += len(value)
                handled_keys.add(key)
            elif lk in {"memories", "notes"} and isinstance(value, list):
                audit_items.extend(_items_from_string_list(platform, lk.rstrip("s"), value))
                stats[lk] += len(value)
                handled_keys.add(key)
            elif lk == "posts" and isinstance(value, list):
                captions = [p.get("caption", "") for p in value if isinstance(p, dict)]
                audit_items.extend(_items_from_string_list(platform, "post", captions))
                stats["posts"] += len(value)
                handled_keys.add(key)
            elif lk == "repositories" and isinstance(value, list):
                descs = [r.get("description", "") for r in value if isinstance(r, dict)]
                audit_items.extend(_items_from_string_list(platform, "repository", descs))
                stats["repositories"] += len(value)
                handled_keys.add(key)
            elif lk == "experience" and isinstance(value, list):
                descs = [e.get("description", "") for e in value if isinstance(e, dict)]
                audit_items.extend(_items_from_string_list(platform, "experience", descs))
                stats["experience"] += len(value)
                handled_keys.add(key)
            elif lk in _PROFILE_ONLY_KEYS and isinstance(value, (list, dict)):
                stats[lk] += len(value) if isinstance(value, list) else _count_leaf_items(value)
                handled_keys.add(key)
        remainder = {k: v for k, v in content.items() if k not in handled_keys}
        audit_items.extend(_items_from_generic(platform, remainder))
    else:
        audit_items.extend(_items_from_generic(platform, content))

    return audit_items, dict(stats)


# ── Corpus assembly (shared by desktop + upload modes) ──────────────────────

class _Corpus:
    """Accumulates normalized items + per-source stats with dedupe."""

    def __init__(self) -> None:
        self.items: list[dict] = []
        self.source_stats: dict[str, dict] = {}
        self.seen: set[int] = set()
        self.files_seen = 0
        self.files_parsed = 0

    def _entry(self, platform: str) -> dict:
        return self.source_stats.setdefault(platform, {
            "platform": platform, "files": 0, "audit_items": 0,
            "profiled_items": 0, "kinds": {},
        })

    def add_export(self, platform: str, content: Any) -> None:
        self.files_parsed += 1
        items, stats = normalize(platform, content)
        entry = self._entry(platform)
        entry["files"] += 1
        for kind, count in stats.items():
            entry["kinds"][kind] = entry["kinds"].get(kind, 0) + count
            if kind in _PROFILE_ONLY_KEYS:
                entry["profiled_items"] += count
        # Dedupe across runs (same conversation re-exported in a later run)
        for item in items:
            h = hash((item["platform"], item["kind"], item["content"]))
            if h in self.seen:
                continue
            self.seen.add(h)
            self.items.append(item)
            entry["audit_items"] += 1

    def add_normalized(self, item: dict) -> bool:
        h = hash((item["platform"], item["kind"], item["content"]))
        if h in self.seen:
            return False
        self.seen.add(h)
        self.items.append(item)
        self._entry(item["platform"])["audit_items"] += 1
        return True

    def merge_stats(self, platform: str, files: int, kinds: dict) -> None:
        entry = self._entry(platform)
        entry["files"] += files
        for kind, count in kinds.items():
            entry["kinds"][kind] = entry["kinds"].get(kind, 0) + count
            if kind in _PROFILE_ONLY_KEYS:
                entry["profiled_items"] += count


def _aggregate(
    corpus: _Corpus,
    build_auditor: Callable[..., Any],
    include_ml: bool,
    max_items: int,
    origin: str,
    started: float,
) -> dict:
    """Run the signal audit over a corpus and produce the profile dict."""
    try:
        from optic.signal.models import SignalSource  # type: ignore
    except ImportError:
        from .signal.models import SignalSource

    all_items = corpus.items
    truncated = len(all_items) > max_items
    if truncated:
        all_items = all_items[:max_items]

    auditor = build_auditor(include_ml=include_ml)
    severity_counts: Counter = Counter()
    attribute_counts: Counter = Counter()
    attribute_confidence: dict[str, float] = defaultdict(float)
    platform_detections: Counter = Counter()
    scored: list[tuple[float, dict]] = []
    total_detections = 0
    total_chars = 0

    for item in all_items:
        total_chars += len(item["content"])
        audit = auditor.audit(
            item["content"], SignalSource.TEXT, item["summary"], item["metadata"]
        )
        weight = 0.0
        for det in audit.detections:
            sev = det.severity.value
            severity_counts[sev] += 1
            attribute_counts[det.attribute] += 1
            attribute_confidence[det.attribute] += det.confidence
            platform_detections[item["platform"]] += 1
            weight += _SEVERITY_WEIGHTS.get(sev, 0.0) * det.confidence
            total_detections += 1
        if audit.detections:
            scored.append((weight, audit.to_dict()))

    scored.sort(key=lambda pair: -pair[0])
    worst = [audit_dict for _, audit_dict in scored[:WORST_OFFENDERS]]

    top_attributes = [
        {
            "attribute": attr,
            "count": count,
            "avg_confidence": round(attribute_confidence[attr] / count, 3),
        }
        for attr, count in attribute_counts.most_common(12)
    ]

    audited = len(all_items)
    profiled = sum(s["profiled_items"] for s in corpus.source_stats.values())
    flagged = len(scored)
    score = min(1.0, sum(w for w, _ in scored) / audited) if audited else 0.0

    for entry in corpus.source_stats.values():
        entry["detections"] = platform_detections.get(entry["platform"], 0)

    return {
        "generated_at": int(started),
        "duration_s": round(time.time() - started, 2),
        "engine": {"include_ml": include_ml},
        "corpus": {
            "origin": origin,
            "files_seen": corpus.files_seen,
            "files_parsed": corpus.files_parsed,
            "audited_items": audited,
            "flagged_items": flagged,
            "profiled_items": profiled,
            "total_chars": total_chars,
            "truncated": truncated,
        },
        "sources": sorted(corpus.source_stats.values(), key=lambda s: -s["audit_items"]),
        "audit": {
            "score": round(score, 4),
            "total_detections": total_detections,
            "severity": dict(severity_counts),
            "top_attributes": top_attributes,
            "worst_offenders": worst,
        },
    }


# ── Desktop mode: scan local export stores ──────────────────────────────────

def ingest(
    state_dir: Path,
    build_auditor: Callable[..., Any],
    roots: list[Path] | None = None,
    include_ml: bool = False,
    max_items: int = DEFAULT_MAX_ITEMS,
    uid: str = "default",
) -> dict:
    """Scan export stores on local disk, audit the corpus, persist profile."""
    roots = [Path(r) for r in roots] if roots else export_roots()
    started = time.time()
    corpus = _Corpus()

    for path in iter_export_files(roots):
        corpus.files_seen += 1
        export = _load_export(path)
        if export is None:
            continue
        platform = _guess_platform_from_path(path)
        if platform == "unknown":
            platform = _guess_platform_from_name(export["name"], export["company"])
        corpus.add_export(platform, export["content"])

    profile = _aggregate(corpus, build_auditor, include_ml, max_items, "disk", started)
    profile["corpus"]["roots"] = [str(r) for r in roots]
    _profile_save(state_dir, profile, uid)
    return profile


# ── Hosted mode: batched browser uploads ────────────────────────────────────

def _spool_dir(state_dir: Path) -> Path:
    return Path(state_dir) / "vana_uploads"


def _spool_paths(state_dir: Path, uid: str, session: str) -> tuple[Path, Path]:
    base = _spool_dir(state_dir) / f"{_safe_uid(uid)}__{_safe_uid(session)}"
    return base.with_suffix(".items.jsonl"), base.with_suffix(".meta.json")


def reap_spools(state_dir: Path) -> None:
    """Delete abandoned upload sessions."""
    spool = _spool_dir(state_dir)
    if not spool.is_dir():
        return
    cutoff = time.time() - SPOOL_TTL_S
    for path in spool.iterdir():
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def spool_add(state_dir: Path, uid: str, session: str, files: list[dict]) -> dict:
    """Normalize a batch of uploaded export documents into the user's spool.

    Each file: {name?: str, data: <parsed export JSON>}.
    Returns running counts for upload progress UI.
    """
    items_path, meta_path = _spool_paths(state_dir, uid, session)
    items_path.parent.mkdir(parents=True, exist_ok=True)
    reap_spools(state_dir)

    meta: dict = {"files_seen": 0, "files_parsed": 0, "stats": {}}
    try:
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass

    spooled_items = 0
    with items_path.open("a", encoding="utf-8") as fh:
        for doc in files:
            if not isinstance(doc, dict):
                continue
            meta["files_seen"] += 1
            export = _coerce_export(doc.get("data"))
            if export is None:
                continue
            meta["files_parsed"] += 1
            platform = _guess_platform_from_name(
                str(doc.get("name", "")), export["name"], export["company"]
            )
            items, stats = normalize(platform, export["content"])
            pstats = meta["stats"].setdefault(platform, {"files": 0, "kinds": {}})
            pstats["files"] += 1
            for kind, count in stats.items():
                pstats["kinds"][kind] = pstats["kinds"].get(kind, 0) + count
            for item in items:
                fh.write(json.dumps(item, separators=(",", ":")) + "\n")
                spooled_items += 1

    meta["updated_at"] = int(time.time())
    meta_path.write_text(json.dumps(meta, separators=(",", ":")), encoding="utf-8")

    total_items = 0
    try:
        with items_path.open("r", encoding="utf-8") as fh:
            total_items = sum(1 for _ in fh)
    except OSError:
        pass

    return {
        "session": _safe_uid(session),
        "batch_items": spooled_items,
        "spooled_items": total_items,
        "files_seen": meta["files_seen"],
        "files_parsed": meta["files_parsed"],
        "platforms": sorted(meta["stats"].keys()),
    }


def spool_finalize(
    state_dir: Path,
    build_auditor: Callable[..., Any],
    uid: str,
    session: str,
    include_ml: bool = False,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> dict:
    """Audit everything spooled for this upload session and persist profile."""
    items_path, meta_path = _spool_paths(state_dir, uid, session)
    started = time.time()
    corpus = _Corpus()

    meta: dict = {"files_seen": 0, "files_parsed": 0, "stats": {}}
    try:
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    corpus.files_seen = int(meta.get("files_seen", 0))
    corpus.files_parsed = int(meta.get("files_parsed", 0))
    for platform, pstats in meta.get("stats", {}).items():
        corpus.merge_stats(platform, int(pstats.get("files", 0)), pstats.get("kinds", {}))

    loaded = 0
    try:
        with items_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if loaded >= SPOOL_MAX_ITEMS:
                    break
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict) and item.get("content"):
                    corpus.add_normalized(item)
                    loaded += 1
    except OSError:
        pass

    profile = _aggregate(corpus, build_auditor, include_ml, max_items, "upload", started)
    _profile_save(state_dir, profile, uid)

    for path in (items_path, meta_path):
        try:
            path.unlink()
        except OSError:
            pass
    return profile


# ── Persistence (per-user) ──────────────────────────────────────────────────

def _profile_path(state_dir: Path, uid: str = "default") -> Path:
    uid = _safe_uid(uid)
    name = "vana_profile.json" if uid == "default" else f"vana_profile_{uid}.json"
    return Path(state_dir) / name


def _profile_save(state_dir: Path, profile: dict, uid: str = "default") -> None:
    path = _profile_path(state_dir, uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(profile, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def profile_load(state_dir: Path, uid: str = "default") -> dict:
    path = _profile_path(state_dir, uid)
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["exists"] = True
                return data
    except (OSError, ValueError):
        pass
    return {"exists": False}
