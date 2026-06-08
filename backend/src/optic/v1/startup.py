"""
Optic V1 — Workstream builder (rewritten).
Groups scanned files into meaningful workstreams with proper naming,
varying confidence, and signal-based evidence labels.
"""
from __future__ import annotations

import os
import json
import hashlib
import sqlite3
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone


# ── Path config ─────────────────────────────────────────────────────

def get_data_dir() -> Path:
    env_dir = os.environ.get("OPTIC_DATA_DIR", "")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".optic"


def get_db_path() -> Path:
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "v1.db"


# ── Scanner ──────────────────────────────────────────────────────────

SCAN_DIRS = ["Desktop", "Documents", "Downloads"]
SCAN_EXTRA = ["Projects", "Dev", "Developer", "Code", "Repos", "workspace", "src"]
SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".svn", "Library", ".Trash",
             ".npm", ".cargo", ".rustup", ".cache", ".local", ".vscode",
             "venv", ".venv", "env", ".env", "dist", "build", ".next",
             "target", ".pytest_cache", ".mypy_cache", "__MACOSX"}
MAX_FILES = 5000


def quick_scan(directory: str, max_files: int = MAX_FILES) -> list[dict]:
    results = []
    base = Path(directory).expanduser().resolve()
    if not base.exists():
        return results
    try:
        for root, dirs, files in os.walk(str(base)):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS]
            for fname in files:
                if fname.startswith("."):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    stat = os.stat(fpath)
                except OSError:
                    continue
                results.append({
                    "path": fpath,
                    "name": fname,
                    "size": stat.st_size,
                    "mtime": int(stat.st_mtime),
                    "ext": os.path.splitext(fname)[1].lower() or ".noext",
                    "parent": os.path.basename(os.path.dirname(fpath)),
                })
                if len(results) >= max_files:
                    return results
    except PermissionError:
        pass
    return results


def scan_all(dirs: list[str] | None = None) -> list[dict]:
    if dirs is None:
        dirs = [str(Path.home() / d) for d in SCAN_DIRS]
        for extra in SCAN_EXTRA:
            p = Path.home() / extra
            if p.exists():
                dirs.append(str(p))
    all_files = []
    for d in dirs:
        files = quick_scan(d)
        all_files.extend(files)
    return all_files


# ── Workstream builder ──────────────────────────────────────────────

EVIDENCE_TYPES = {
    "code": [
        "Source file structure", "Build & dependency pattern",
        "Code organization signal", "Implementation consistency",
    ],
    "writing": [
        "Documentation depth", "Written communication volume",
        "Note-taking pattern", "Knowledge capture habit",
    ],
    "documents": [
        "Document organization", "Formal document presence",
        "Record-keeping signal", "Professional documentation",
    ],
    "images": [
        "Visual asset collection", "Screenshot activity",
        "Image organization pattern", "Media library signal",
    ],
    "data": [
        "Data management pattern", "Spreadsheet & analysis habit",
        "Structured data presence", "Analytics signal",
    ],
    "video": [
        "Media collection signal", "Video content presence",
    ],
    "files": [
        "File organization", "Storage footprint",
        "Digital activity level", "Content diversity",
    ],
}


def _clean_name(raw: str) -> str:
    """Clean folder names into readable labels."""
    if not raw:
        return "Other"
    name = raw.strip()
    for prefix in ["set-up-", "setup-", "config-"]:
        if name.lower().startswith(prefix):
            name = name[len(prefix):]
    name = name.replace("-", " ").replace("_", " ")
    words = name.split()
    cleaned = []
    for w in words:
        if w.upper() in ("AI", "API", "HTTPS", "SSL", "DNS", "PDF", "CSS", "JS", "ML"):
            cleaned.append(w.upper())
        elif len(w) <= 2:
            cleaned.append(w.upper())
        else:
            cleaned.append(w[0].upper() + w[1:].lower() if len(w) > 1 else w.upper())
    name = " ".join(cleaned)
    return name.strip() or raw[:30] or "Other"


def _confidence(fc: int, total_files: int = 5000) -> float:
    """Compute a realistic confidence score that varies with file count.
    Uses a Michaelis-Menten-like curve: fc / (fc + K) * scale + offset.
    Small folders get 30-60%, medium get 60-80%, large get 80-92%.
    """
    K = max(total_files // 20, 50)  # half-saturation point
    raw = fc / (fc + K)
    return round(min(0.92, 0.28 + 0.64 * raw), 2)


def _primary_topic(exts: set) -> str:
    """Identify the dominant category from extensions."""
    scores = {}
    for ext in exts:
        if ext in {".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".h"}:
            scores["code"] = scores.get("code", 0) + 1
        elif ext in {".md", ".txt", ".rst", ".org", ".tex"}:
            scores["writing"] = scores.get("writing", 0) + 1
        elif ext in {".pdf", ".doc", ".docx", ".pages", ".ppt", ".pptx"}:
            scores["documents"] = scores.get("documents", 0) + 1
        elif ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".svg"}:
            scores["images"] = scores.get("images", 0) + 1
        elif ext in {".csv", ".xlsx", ".xls", ".numbers", ".json", ".xml"}:
            scores["data"] = scores.get("data", 0) + 1
        elif ext in {".mp4", ".mov", ".avi", ".mkv"}:
            scores["video"] = scores.get("video", 0) + 1
    if not scores:
        return "files"
    return max(scores, key=scores.get)


def _summary(name: str, fc: int, primary: str, topics: list[str]) -> str:
    """Generate a human-readable summary for a workstream."""
    topic_str = ", ".join(topics[:3]) if topics else "various content"
    if primary == "code":
        return f"{fc} files suggest an active development workspace covering {topic_str}."
    elif primary == "writing":
        return f"{fc} text-based files indicate strong writing and documentation habits."
    elif primary == "documents":
        return f"{fc} formal documents suggest organized record-keeping across {topic_str}."
    elif primary == "images":
        return f"{fc} images and media files show a visual content collection."
    elif primary == "data":
        return f"{fc} data files point to analytical or reporting workflows."
    return f"{fc} files spanning {topic_str}."


def _evidence_labels(topics: list[str], fc: int) -> list[str]:
    """Generate 3 signal-based evidence labels (not audience lens names)."""
    primary = topics[0] if topics else "files"
    pool = EVIDENCE_TYPES.get(primary, EVIDENCE_TYPES["files"])
    labels = []
    for i in range(min(3, len(pool))):
        labels.append(pool[i])
    while len(labels) < 3:
        labels.append("File organization")
    return labels[:3]


def build_workstreams(files: list[dict]) -> list[dict]:
    """Group scanned files into meaningful workstreams."""
    groups = {}
    for f in files:
        parent = f.get("parent", "Other")
        if parent not in groups:
            groups[parent] = {"files": [], "total_size": 0, "exts": set()}
        groups[parent]["files"].append(f)
        groups[parent]["total_size"] += f.get("size", 0)
        groups[parent]["exts"].add(f.get("ext", ""))

    # Sort by file count and merge tiny groups into "Other"
    sorted_groups = sorted(groups.items(), key=lambda x: -len(x[1]["files"]))
    total_files = sum(len(d["files"]) for _, d in sorted_groups)

    workstreams = []
    other_files = []
    for folder, data in sorted_groups:
        fc = len(data["files"])
        if fc < 5:  # merge tiny folders
            other_files.extend(data["files"])
            continue
        clean_name = _clean_name(folder)
        primary = _primary_topic(data["exts"])
        topics = [primary]
        if data["exts"] & {".md", ".txt", ".rst"} and primary != "writing":
            topics.append("writing")
        if data["exts"] & {".py", ".js", ".ts"} and primary != "code":
            topics.append("code")
        confidence = _confidence(fc, total_files)
        workstreams.append({
            "id": f"ws-{len(workstreams):03d}",
            "name": clean_name,
            "file_count": fc,
            "size": data["total_size"],
            "confidence": confidence,
            "topics": topics,
            "primary_topic": primary,
            "folders": [folder],
            "summary": _summary(clean_name, fc, primary, topics),
            "evidence_labels": _evidence_labels(topics, fc),
        })

    # Add "Other" if there are enough merged files
    if len(other_files) >= 10:
        total_size = sum(f.get("size", 0) for f in other_files)
        exts = set(f.get("ext", "") for f in other_files)
        primary = _primary_topic(exts)
        topics = [primary]
        workstreams.append({
            "id": f"ws-{len(workstreams):03d}",
            "name": "Other files",
            "file_count": len(other_files),
            "size": total_size,
            "confidence": _confidence(len(other_files), total_files),
            "topics": topics,
            "primary_topic": primary,
            "folders": list(set(f.get("parent", "") for f in other_files))[:5],
            "summary": f"{len(other_files)} files across various smaller folders.",
            "evidence_labels": _evidence_labels(topics, len(other_files)),
        })

    # Cap at 12 workstreams
    return workstreams[:12]


# ── Narrative generator ─────────────────────────────────────────────

def generate_narratives(workstreams: list[dict]) -> list[str]:
    """Generate human-readable narrative labels from workstream analysis."""
    narratives = []
    total_files = sum(ws.get("file_count", 0) for ws in workstreams)
    topic_counts = {}
    for ws in workstreams:
        for t in ws.get("topics", []):
            topic_counts[t] = topic_counts.get(t, 0) + ws.get("file_count", 0)

    primary_topic = max(topic_counts, key=topic_counts.get) if topic_counts else "files"
    code_pct = topic_counts.get("code", 0) / max(total_files, 1)
    writing_pct = topic_counts.get("writing", 0) / max(total_files, 1)
    image_pct = topic_counts.get("images", 0) / max(total_files, 1)

    if code_pct > 0.3:
        narratives.append("Active developer")
    if code_pct > 0.5:
        narratives.append("Deep technical builder")
    if writing_pct > 0.15:
        narratives.append("Consistent writer")
    if writing_pct > 0.3:
        narratives.append("Heavy documenter")
    if image_pct > 0.2:
        narratives.append("Visual collector")
    if len(workstreams) >= 8:
        narratives.append("Digitally organized")
    if total_files > 3000:
        narratives.append("High digital footprint")
    if total_files < 500:
        narratives.append("Minimal digital presence")

    if len(narratives) < 3:
        narratives = [w["name"] for w in workstreams[:3]]
    return narratives[:5]


# ── Lens relevance ──────────────────────────────────────────────────

def _lens_relevant(lens: str, topics: list[str], fc: int, conf: float) -> bool:
    """Determine if a lens should generate claims for a given workstream.
    Different lenses care about different signal types, creating natural score variation.
    """
    primary = topics[0] if topics else "files"
    # Recruiter cares about code, career, project work — not images or admin
    if lens == "recruiter":
        return primary in ("code", "writing") and fc > 50
    # Investor cares about scale — large file counts, high confidence
    if lens == "investor":
        return fc > 150 or conf > 0.55
    # Admissions cares about writing, documentation, organized work
    if lens == "admissions":
        return primary in ("writing", "documents", "code")
    # Creator cares about diverse content — images, writing, code
    if lens == "creator":
        return primary in ("images", "writing", "code")
    # Stranger sees everything public — images, documents, large footprint
    if lens == "stranger":
        return primary in ("images", "documents") or fc > 200
    # Customer cares about professional output, code, products
    if lens == "customer":
        return primary in ("code", "documents", "data")
    # Collaborator cares about code, writing, shared work
    if lens == "collaborator":
        return primary in ("code", "writing") and fc > 50
    # Ad platform sees media, images, large data
    if lens == "ad_platform":
        return primary in ("images", "data", "documents")
    # Future AI agent sees everything
    if lens == "future_agent":
        return True
    return True


# ── Seed functions ──────────────────────────────────────────────────

def _seed_from_scan(conn, workstreams: list[dict], files: list[dict]):
    """Populate database with real scan data."""
    now = datetime.now(timezone.utc).isoformat()
    user = conn.execute("SELECT * FROM users LIMIT 1").fetchone()
    if not user:
        uid = str(uuid4())
        conn.execute(
            "INSERT INTO users(id, email, settings, local_mode, created_at) VALUES(?,?,?,?,?)",
            (uid, "local@optic.app", "{}", 1, now))
        user_id = uid
    else:
        user_id = user["id"]

    # Store scanned files as artifacts
    for f in files:
        aid = str(uuid4())
        conn.execute(
            "INSERT INTO artifacts(id, source_id, type, raw_hash, encrypted_path, "
            "metadata, is_public, content_preview, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (aid, "scan", "file", hashlib.sha256(f["path"].encode()).hexdigest()[:16],
             f["path"], json.dumps({"size": f["size"], "ext": f["ext"], "mtime": f["mtime"],
                                    "parent": f["parent"]}), 0, "", now))

    # Generate signals per workstream
    for ws in workstreams:
        name = ws["name"]
        fc = ws["file_count"]
        topics = ws.get("topics", [])
        evidence = ws.get("evidence_labels", ["File organization", "Storage footprint", "Content diversity"])
        for signal_type in ["topic_focus", "activity_volume"]:
            desc = (
                f"Workstream '{name}' shows concentrated {topics[0] if topics else 'file'} activity"
                if signal_type == "topic_focus" else
                f"{fc} files in '{name}' indicate sustained digital engagement"
            )
            meta = json.dumps({
                "workstream_id": ws["id"], "workstream_name": name,
                "confidence": ws["confidence"], "file_count": fc,
                "topics": topics, "evidence_labels": evidence,
            })
            conn.execute(
                "INSERT INTO signals(id,category,description,severity,"
                "source_artifact_ids,metadata,created_at) VALUES(?,?,?,?,?,?,?)",
                (str(uuid4()), signal_type, desc, "low", "[]", meta, now))

    # Generate claims per workstream per audience lens
    lenses = ["recruiter", "investor", "admissions", "creator", "stranger",
              "customer", "collaborator", "ad_platform", "future_agent"]
    for ws in workstreams:
        name = ws["name"]
        fc = ws["file_count"]
        topics = ws.get("topics", [])
        conf = ws["confidence"]
        evidence = ws.get("evidence_labels", ["File organization"])
        for lens in lenses:
            # Only generate claims for relevant lens-workstream pairs
            if not _lens_relevant(lens, topics, fc, conf):
                continue
            for sig in ["focus", "volume"]:
                title = f"{lens.replace('_',' ').title()} read: {sig}"
                claim = (
                    f"A {lens.replace('_',' ')} read may infer sustained "
                    f"{topics[0] if topics else 'activity'} in '{name}' "
                    f"from the scale and organization of {fc} files"
                    if sig == "volume" else
                    f"A {lens.replace('_',' ')} read may notice concentrated "
                    f"focus on {topics[0] if topics else 'content'} within '{name}'"
                )
                conn.execute(
                    "INSERT INTO claims(id,title,audience_lens,claim,confidence_band,"
                    "evidence_count,supporting_evidence,weakening_evidence,source_gaps,"
                    "recency,severity,actionability,possible_consequence,counterargument,"
                    "repair_options,model_version,not_a_verdict,generated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (str(uuid4()), title, lens, claim,
                     "high" if conf >= 0.60 else "low" if conf < 0.45 else "medium",
                     5, "[]", "[]", "[]", "recent", "low", "medium", "", "", "[]", "v1", 1, now))

    # Generate narratives and store in reports
    narratives = generate_narratives(workstreams)
    risks = [
        ("Large footprint", f"Largest file: {max((f['size'], f['name']) for f in files)[1]} "
         f"({max(f['size'] for f in files) // 1024 // 1024}MB)"),
        ("Signal surface", f"{len(files)} files across {len(workstreams)} workstreams "
         f"creates a broad inference surface"),
        ("Stale content", "Some files may contain outdated information"),
        ("Identity exposure", "Personal details may be visible in file metadata"),
        ("Blind spots", "Some folders may not be fully represented"),
        ("Organization", "File organization patterns affect how signals are read"),
    ]
    strategies = ["review largest files", "archive stale content", "audit metadata",
                  "review permissions", "consolidate folders", "add documentation"]
    for i, (cat, desc) in enumerate(risks):
        rid = str(uuid4())
        conn.execute(
            "INSERT INTO risks(id,category,description,severity,linked_claim_ids,"
            "linked_artifact_ids,audience_affected,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (rid, cat, desc, "medium", "[]", "[]", "all", now))
        conn.execute(
            "INSERT INTO repairs(id,title,affected_audience,linked_claim_id,"
            "linked_evidence_ids,impact,effort,urgency,reversibility,exact_steps,"
            "expected_effect,risk_of_overcorrecting,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(uuid4()), f"Fix: {desc}", "all", "", "[]", 0.7, 0.3, 0.6, 0.9,
             f"Step: {strategies[i]}", f"Reduced {cat} risk", "minimal", "pending"))

    n = len(workstreams) * len(lenses) * 2
    conn.execute(
        "INSERT INTO reports(id,user_id,version,audit_mode,created_at,snapshot_id,"
        "claim_count,contradiction_count,risk_count,repair_count) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (str(uuid4()), user_id, 1, "general", now,
         hashlib.md5(b"real-scan").hexdigest()[:16], n, 0, len(risks), len(risks)))
    conn.commit()
    return n


def ensure_data(db_path: Path) -> dict:
    """Ensure the database has data. Scan filesystem on first run."""
    if not db_path.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        from optic.v1.server import init_db
        init_db()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    count = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
    conn.close()

    if count > 0:
        return {"seeded": False, "existing_claims": count, "source": "existing"}

    print("Optic: first run — scanning your files...")
    files = scan_all()
    workstreams = build_workstreams(files)
    print(f"Optic: scanned {len(files)} files → {len(workstreams)} workstreams")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    if len(workstreams) >= 3 and len(files) >= 50:
        n = _seed_from_scan(conn, workstreams, files)
        conn.close()
        return {
            "seeded": True, "source": "real_scan",
            "scanned_files": len(files), "workstreams": len(workstreams),
            "claims": n, "signals": len(workstreams) * 2,
        }
    else:
        conn.close()
        return {"seeded": False, "source": "insufficient_data",
                "message": f"Only {len(files)} files found"}
