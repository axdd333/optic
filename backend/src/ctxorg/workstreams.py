from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from . import db, ollama, terms as termsmod

# ---------------------------------------------------------------------------
# Noise detection helpers
# ---------------------------------------------------------------------------

NOISE_EXTS = {
    ".plist", ".tvdb", ".musicdb", ".bkp", ".localized",
    ".photoslibrary", ".mlmodel", ".mlpackage",
}

NOISE_PATH_FRAGMENTS = (
    "tv library.tvlibrary", "media.localized", ".ds_store",
    "spotlight", "com.apple.", ".trash", ".localized",
    "cache", "caches", "/tmp/", "relocated items",
    "music library.musiclibrary", "photos library.photoslibrary",
)

HEX_RE = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_noise_path(path: str) -> bool:
    low = path.lower()
    return any(frag in low for frag in NOISE_PATH_FRAGMENTS)


def _is_hex_name(stem: str) -> bool:
    return bool(HEX_RE.match(stem) or UUID_RE.match(stem))


def _is_meaningful_name(stem: str) -> bool:
    if not stem:
        return False
    if _is_hex_name(stem):
        return False
    # Strip common suffixes like "-2-2-2-2" duplicates
    base = re.sub(r"(-\d+)+$", "", stem)
    if _is_hex_name(base):
        return False
    return len(base) >= 3


# ---------------------------------------------------------------------------
# Category / type helpers
# ---------------------------------------------------------------------------

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".heic", ".bmp", ".tif", ".tiff",
              ".webp", ".svg"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aiff", ".flac", ".ogg"}
DOC_EXTS = termsmod.DOC_EXTS
CODE_EXTS = termsmod.CODE_EXTS


def _file_category(ext: str) -> str:
    e = ext.lower()
    if e in IMAGE_EXTS:
        return "screenshots"
    if e in VIDEO_EXTS or e in AUDIO_EXTS:
        return "media"
    if e in DOC_EXTS:
        return "documents"
    if e in CODE_EXTS:
        return "code"
    return "other"


def _category_color(breakdown: dict) -> str:
    """Pick a CSS color string based on dominant file type."""
    dominant = max(breakdown, key=lambda k: breakdown[k])
    if breakdown[dominant] == 0:
        dominant = "other"
    return {
        "screenshots": "teal",
        "media": "coral",
        "documents": "blue",
        "code": "amber",
        "other": "gray",
    }.get(dominant, "purple")


# ---------------------------------------------------------------------------
# Noise cluster filtering
# ---------------------------------------------------------------------------

def _cluster_is_noise(rows: list[dict]) -> bool:
    """Return True if the cluster should be skipped."""
    if not rows:
        return True
    noise_count = sum(
        1 for r in rows
        if _is_noise_path(r["path"])
        or r.get("ext", "").lower() in NOISE_EXTS
    )
    if noise_count / len(rows) > 0.8:
        return True
    # All filenames are hex hashes and there's no text
    names = [Path(r["path"]).stem for r in rows]
    all_hex = all(_is_hex_name(n) for n in names)
    any_text = any((r.get("text") or "").strip() for r in rows)
    if all_hex and not any_text:
        return True
    return False


# ---------------------------------------------------------------------------
# Naming heuristics (fast, no LLM)
# ---------------------------------------------------------------------------

def _top_folder_names(rows: list[dict], n: int = 3) -> list[str]:
    folders: Counter = Counter()
    for r in rows:
        parent = Path(r["path"]).parent.name
        if parent:
            folders[parent] += 1
    return [name for name, _ in folders.most_common(n)]


def _dominant_ext(rows: list[dict]) -> str | None:
    """Return the single dominant extension if >70% of files share it."""
    exts: Counter = Counter(
        r.get("ext", "").lower() for r in rows if r.get("ext")
    )
    if not exts:
        return None
    top_ext, top_cnt = exts.most_common(1)[0]
    if top_cnt / len(rows) >= 0.7 and top_ext:
        return top_ext
    return None


def _meaningful_name_fragments(rows: list[dict]) -> list[str]:
    """Collect meaningful word fragments from real (non-hex) filenames."""
    words: Counter = Counter()
    for r in rows:
        stem = Path(r["path"]).stem
        if not _is_meaningful_name(stem):
            continue
        # Tokenize the stem
        for tok in re.findall(r"[A-Za-z]{3,}", stem):
            low = tok.lower()
            if low not in termsmod.STOP:
                words[low] += 1
    return [w for w, _ in words.most_common(5)]


_IMAGE_EXTS_LABEL = {".png": "Screenshots", ".jpg": "Photos", ".jpeg": "Photos",
                     ".gif": "Images", ".heic": "Photos", ".webp": "Images",
                     ".svg": "Graphics", ".tiff": "Photos", ".bmp": "Images"}
_DOC_EXTS_LABEL = {".pdf": "PDFs", ".md": "Notes", ".txt": "Notes",
                   ".docx": "Documents", ".doc": "Documents", ".rtf": "Documents",
                   ".pages": "Documents", ".numbers": "Spreadsheets", ".xlsx": "Spreadsheets",
                   ".xls": "Spreadsheets", ".csv": "Data files", ".pptx": "Presentations",
                   ".ppt": "Presentations"}
# Obscure extensions mapped to plain English (no jargon, no ALL-CAPS raw ext)
_TECH_EXTS_LABEL = {
    ".itdb": "iTunes media library", ".itl": "iTunes library",
    ".kicad_sch": "circuit schematics", ".kicad_pcb": "circuit board designs",
    ".sch": "circuit schematics", ".brd": "circuit board designs",
    ".lbr": "electronics component library", ".kicad_mod": "electronics footprints",
    ".dxf": "CAD drawings", ".dwg": "CAD drawings", ".stl": "3D models",
    ".blend": "3D scenes", ".obj": "3D models", ".fbx": "3D models",
    ".sketch": "design files", ".fig": "design files", ".xd": "design files",
    ".sqlite": "database", ".db": "database", ".sql": "database",
    ".psd": "Photoshop files", ".ai": "Illustrator files",
    ".indd": "InDesign files", ".epub": "ebooks", ".mobi": "ebooks",
    ".zip": "archives", ".tar": "archives", ".gz": "archives",
    ".dmg": "disk images", ".iso": "disk images",
    ".ipa": "iOS apps", ".apk": "Android apps",
    ".xcodeproj": "Xcode projects", ".xcworkspace": "Xcode workspaces",
    ".pbxproj": "Xcode project settings",
    ".env": "environment config", ".toml": "config files",
    ".yml": "config files", ".yaml": "config files",
    ".scad": "3D model designs", ".f3d": "3D model designs",
    ".sh": "shell scripts", ".bash": "shell scripts", ".zsh": "shell scripts",
    ".ps1": "PowerShell scripts", ".bat": "batch scripts",
    ".r": "data analysis scripts", ".rmd": "data analysis reports",
    ".ipynb": "Jupyter notebooks",
}

# Words that are tool names, generic OS/filesystem junk, URL fragments, or too vague
_NOISE_WORDS = {
    # Tool/app names
    "removebg", "preview", "capture", "scan", "export", "output",
    # Generic file words
    "image", "images", "file", "files", "copy", "backup", "final", "draft",
    "temp", "untitled", "screenshot", "screenshots", "screen",
    "photo", "photos", "picture", "pictures", "img", "pic",
    "version", "new", "old", "test", "sample", "example", "misc", "various",
    # Generic folder/path names that leak into topics
    "inbox", "downloads", "desktop", "documents", "library", "folder",
    "users", "ahmedm", "home", "root", "local", "mobile",
    # Filesystem metadata that TF-IDF picks up from file contents
    "name", "path", "size", "type", "date", "true", "false", "null", "none",
    # URL/web noise
    "https", "http", "www", "com", "org", "net", "html", "json",
    # Generic programming noise
    "default", "used", "found", "stinct", "ass", "pio", "conf",
    # Short raw extension fragments
    "sch", "pcb", "brd", "lbr", "mod",
}

# Known technical library / tool / framework names → human-readable translations
_TECH_TERM_MAP: dict[str, str] = {
    # Electronics EDA
    "kicad": "Electronics Design", "kicad_sch": "Circuit Schematics",
    "kicad_pcb": "Circuit Boards", "eagle": "Electronics Design",
    # 3D / CAD
    "scad": "3D Modeling", "openscad": "3D Modeling", "blender": "3D Design",
    "freecad": "CAD Design",
    # Python ecosystem
    "anyio": "Async Development", "trio": "Async Development",
    "pytest": "Python Testing", "pytest11": "Python Testing",
    "pyobjctest": "macOS Scripting", "pyobjctools": "macOS Scripting",
    "pyobjc": "macOS Scripting",
    "numpy": "Data Science", "pandas": "Data Analysis", "scipy": "Scientific Computing",
    "sklearn": "Machine Learning", "torch": "Machine Learning",
    "flask": "Web Backend", "fastapi": "Web Backend", "django": "Web Backend",
    # macOS / Apple frameworks
    "objc": "Objective-C", "appkit": "macOS Development", "uikit": "iOS Development",
    "swiftui": "Apple UI", "foundation": "Apple Platform",
    "cocoa": "macOS Development", "xcode": "Apple Development",
    # Media / iTunes
    "itdb": "iTunes Library", "itunes": "iTunes Library",
    # Misc tech
    "bash": "Shell Scripts", "zsh": "Shell Scripts",
    "platformio": "Embedded Systems",
}

# Pattern: looks like a raw compound extension (kicad_sch) or hex fragment
_EXT_LIKE = re.compile(r'^[a-z0-9]{2,12}_[a-z0-9]{2,8}$|^[0-9a-f]{8,}$')


def _clean_frags(frags: list[str]) -> list[str]:
    """Remove tool-name noise and deduplicate fragments."""
    return [f for f in frags if f.lower() not in _NOISE_WORDS]


def _clean_topics(topics: list[str]) -> list[str]:
    """Filter topic list: remove filesystem noise, raw extensions, hex, short tokens."""
    result = []
    for t in topics:
        low = t.lower()
        if low in _NOISE_WORDS:
            continue
        if len(t) < 4:
            continue
        if _EXT_LIKE.match(low):
            continue
        result.append(t)
    return result


def _best_topic_label(topics: list[str]) -> str | None:
    """Pick the most human-readable label from topics, translating tech terms."""
    for t in topics:
        low = t.lower().replace("-", "_")
        if low in _TECH_TERM_MAP:
            return _TECH_TERM_MAP[low]
    clean = _clean_topics(topics)
    if clean:
        return clean[0].replace("_", " ").title()
    return None


def _heuristic_name(rows: list[dict], topics: list[str]) -> str:
    folders = _top_folder_names(rows, 1)
    folder = folders[0] if folders else "files"
    raw_frags = _meaningful_name_fragments(rows)
    frags = _clean_frags(raw_frags)
    dom_ext = _dominant_ext(rows)

    _generic_folders = {"inbox", "downloads", "desktop", "pictures", "2026",
                        "2025", "2024", "temp", "misc", "mobile documents"}

    def _folder_prefix() -> str:
        return folder.title() if folder.lower() not in _generic_folders else ""

    # Translate raw topics through the tech term map first
    best_label = _best_topic_label(topics)   # e.g. "Electronics Design", "3D Modeling"
    clean_t = _clean_topics(topics)

    def _topic_prefix(n: int = 2) -> str:
        chosen = [t.replace("_", " ").replace("-", " ").title()
                  for t in clean_t[:n]]
        return " & ".join(chosen) if chosen else ""

    if dom_ext:
        # Images — translated topic label first, then clean topic, then fragment, then folder
        if dom_ext in _IMAGE_EXTS_LABEL:
            label = _IMAGE_EXTS_LABEL[dom_ext]
            prefix = _topic_prefix(2) or (frags[0].title() if frags else _folder_prefix())
            return f"{prefix} {label}".strip() if prefix else label

        # Docs — use translated label if available, else clean topic
        if dom_ext in _DOC_EXTS_LABEL:
            label = _DOC_EXTS_LABEL[dom_ext]
            # Prefer translated tech term (e.g. "Async Development Notes") over raw topic
            prefix = best_label or (frags[0].title() if frags else _folder_prefix())
            return f"{prefix} {label}".strip() if prefix else label

        # Known technical types — clean ext label only; no jargon prefix
        if dom_ext in _TECH_EXTS_LABEL:
            raw = _TECH_EXTS_LABEL[dom_ext]
            # Preserve known brand/product casings after .title()
            return (raw.title()
                    .replace("Itunes", "iTunes")
                    .replace("Macos", "macOS")
                    .replace("Ios", "iOS")
                    .replace("Javascript", "JavaScript")
                    .replace("Typescript", "TypeScript")
                    .replace("Openscad", "OpenSCAD")
                    .replace("Kicad", "KiCad"))

        # Unknown extension — readable prefix only, no raw ext
        prefix = best_label or (frags[0].title() if frags else _folder_prefix())
        return f"{prefix} files".strip() if prefix else f"{folder} files"

    # No dominant extension — prefer tech-translated label, then clean frags, then clean topics
    if best_label:
        if frags:
            return f"{best_label} — {frags[0].title()}"
        return best_label

    if frags:
        label = frags[0].replace("-", " ").replace("_", " ").title()
        if len(frags) > 1:
            label2 = frags[1].replace("-", " ").replace("_", " ").title()
            return f"{label} & {label2}"
        return label

    if len(clean_t) >= 2:
        t1, t2 = clean_t[0].replace("_", " ").title(), clean_t[1].replace("_", " ").title()
        return f"{t1} & {t2}"
    if clean_t:
        return clean_t[0].replace("_", " ").title()

    return folder.title() if folder else "Mixed files"


# ---------------------------------------------------------------------------
# Summary heuristic (fast, no LLM)
# ---------------------------------------------------------------------------

def _heuristic_summary(rows: list[dict], topics: list[str],
                        folders: list[str]) -> str:
    count = len(rows)
    dom_ext = _dominant_ext(rows)
    # Pick a readable folder description, skip generic names
    _generic = {"inbox", "downloads", "desktop", "pictures", "temp", "misc",
                "documents", "2026", "2025", "2024", "library", "mobile documents"}
    clean_folders = [f for f in folders if f.lower() not in _generic]
    location = clean_folders[0] if clean_folders else (folders[0] if folders else None)

    file_word = "file" if count == 1 else "files"

    if dom_ext:
        # Images
        if dom_ext in _IMAGE_EXTS_LABEL:
            label = _IMAGE_EXTS_LABEL[dom_ext].lower()
            good = _clean_topics(topics)
            translated = _best_topic_label(topics)
            if translated and translated.lower() not in {"screenshots", "photos", "images"}:
                return f"{count} {label} — {translated}" + (f", from {location}." if location else ".")
            if good:
                t = good[0].replace("_", " ")
                return f"{count} {label} related to {t}" + (f", from {location}." if location else ".")
            return f"{count} {label}" + (f" from {location}." if location else ".")

        # Docs
        if dom_ext in _DOC_EXTS_LABEL:
            label = _DOC_EXTS_LABEL[dom_ext].lower()
            good_topics = _clean_topics(topics)
            translated = _best_topic_label(topics)
            if translated and translated.lower() not in label:
                return f"{count} {label} on {translated}" + (f", from {location}." if location else ".")
            if good_topics:
                t = ", ".join(t.replace("_", " ") for t in good_topics[:2])
                return f"{count} {label} covering {t}" + (f", from {location}." if location else ".")
            return f"{count} {label}" + (f" from {location}." if location else ".")

        # Known technical types
        if dom_ext in _TECH_EXTS_LABEL:
            label = _TECH_EXTS_LABEL[dom_ext]
            plural = label if label.endswith("s") else f"{label} files"
            return f"{count} {plural}" + (f" from {location}." if location else ".")

        # Unknown extension — at least show it readably
        ext_readable = dom_ext.lstrip(".").replace("_", " ")
        return f"{count} {ext_readable} {file_word}" + (f" from {location}." if location else ".")

    # Mixed file types — use translated label if available, else clean topics
    translated = _best_topic_label(topics)
    good_topics = _clean_topics(topics)
    if translated:
        return f"{count} {file_word} — {translated}" + (f", from {location}." if location else ".")
    if good_topics:
        t = ", ".join(t.replace("_", " ") for t in good_topics[:3])
        return f"{count} {file_word} covering {t}" + (f", stored in {location}." if location else ".")

    return f"{count} {file_word}" + (f" from {location}." if location else ".")


# ---------------------------------------------------------------------------
# Gemma naming (top clusters only)
# ---------------------------------------------------------------------------

def _gemma_name(cfg: dict, folders: list[str], topics: list[str],
                key_files: list[str]) -> str | None:
    try:
        folders_str = ", ".join(folders[:3]) if folders else "unknown"
        topics_str = ", ".join(topics[:5]) if topics else "unknown"
        files_str = ", ".join(Path(f).name for f in key_files[:5]) or "unknown"
        prompt = (
            f"Name this file cluster in 3-5 words. "
            f"Files are in folders: {folders_str}. "
            f"Topics: {topics_str}. "
            f"Sample filenames: {files_str}. "
            f"Return ONLY the name, nothing else."
        )
        name = ollama.text(
            cfg,
            prompt,
            feature="workstreams",
            temp=0.1,
            num_ctx=512,
            timeout=8,
        ).strip().strip('"').strip("'")
        words = name.split()
        if 2 <= len(words) <= 8:
            return name
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Confidence from link scores
# ---------------------------------------------------------------------------

def _load_all_embeddings(conn) -> dict[str, list[float]]:
    """Bulk-load all cached embeddings into memory (id → vector)."""
    try:
        from . import embed as embedmod
        embedmod.ensure_embed_table(conn)
        rows = db.rows(conn, "SELECT id, vec FROM embeddings")
        result: dict[str, list[float]] = {}
        for r in rows:
            vec = embedmod.load_embed(r["vec"])
            if vec:
                result[r["id"]] = vec
        return result
    except Exception:
        return {}


def _cluster_confidence(cluster_ids: list[str],
                         embed_cache: dict[str, list[float]],
                         conn, run_id: str | None) -> float:
    if len(cluster_ids) < 2:
        return 0.5

    # --- Try neural cosine similarity (in-memory, no per-item DB query) ---
    if embed_cache:
        import math
        vecs = [embed_cache[iid] for iid in cluster_ids[:30] if iid in embed_cache]
        if len(vecs) >= 3:
            def cosine(a: list[float], b: list[float]) -> float:
                dot = sum(x * y for x, y in zip(a, b))
                na = math.sqrt(sum(x * x for x in a))
                nb = math.sqrt(sum(y * y for y in b))
                return dot / (na * nb) if na and nb else 0.0

            pairs = [
                (vecs[i], vecs[j])
                for i in range(len(vecs))
                for j in range(i + 1, min(i + 4, len(vecs)))
            ]
            if pairs:
                avg_sim = sum(cosine(a, b) for a, b in pairs) / len(pairs)
                return round(min(1.0, max(0.0, avg_sim)), 3)

    # --- Fall back to link-score method ---
    ph = ",".join("?" for _ in cluster_ids)
    run_filter = ""
    args: list = list(cluster_ids) + list(cluster_ids)
    if run_id:
        run_filter = " AND run = ?"
        args.append(run_id)
    sql = (f"SELECT score FROM links "
           f"WHERE a IN ({ph}) AND b IN ({ph}){run_filter} LIMIT 200")
    try:
        scores = [r["score"] for r in db.rows(conn, sql, args)]
    except Exception:
        return 0.5
    if not scores:
        return 0.3
    avg = sum(scores) / len(scores)
    return round(min(1.0, max(0.0, (avg - 0.5) / 0.5)), 3)


# ---------------------------------------------------------------------------
# Main compute function
# ---------------------------------------------------------------------------

def compute(conn, cfg: dict, run_id: str | None = None,
            limit: int = 30, gemma_budget: int = 10) -> list[dict]:
    """Return list of workstream card dicts, largest clusters first.

    gemma_budget: max number of Gemma LLM calls for naming (0 = heuristic only).
    """

    # Bulk-load all embeddings once (avoids N×30 per-item DB queries)
    embed_cache = _load_all_embeddings(conn)

    # Fetch all items grouped by cluster
    all_items = db.rows(conn,
        "SELECT id, path, kind, ext, size, cluster, text "
        "FROM items WHERE cluster != '' ORDER BY cluster")

    # Group by cluster
    cluster_map: dict[str, list[dict]] = {}
    for item in all_items:
        cid = item["cluster"]
        cluster_map.setdefault(cid, []).append(item)

    # Sort by file count so we can compute confidence then re-sort by quality
    sorted_clusters = sorted(cluster_map.items(),
                             key=lambda kv: len(kv[1]), reverse=True)

    cards = []

    for cid, rows in sorted_clusters:
        if len(cards) >= limit:
            break

        # Skip noise clusters
        if _cluster_is_noise(rows):
            continue

        # --- Basic stats ---
        file_count = len(rows)

        breakdown = {"screenshots": 0, "documents": 0, "code": 0,
                     "media": 0, "other": 0}
        for r in rows:
            cat = _file_category(r.get("ext", ""))
            breakdown[cat] = breakdown.get(cat, 0) + 1

        folders = _top_folder_names(rows, 3)

        # --- Key files: prefer real names with text content, skip noise paths ---
        def _key_score(r: dict) -> int:
            if _is_noise_path(r["path"]):
                return -1  # always exclude noise paths
            stem = Path(r["path"]).stem
            if _is_hex_name(stem):
                return -1  # exclude hex/uuid-named files
            has_text = bool((r.get("text") or "").strip())
            is_real = _is_meaningful_name(stem)
            return (2 if has_text else 0) + (1 if is_real else 0)

        sorted_rows = sorted(rows, key=_key_score, reverse=True)
        # Take up to 5, excluding noise and hex-named files
        key_files = [r["path"] for r in sorted_rows if _key_score(r) >= 0][:5]
        if not key_files:  # fallback: any non-hex, non-noise file
            key_files = [
                r["path"] for r in rows
                if not _is_noise_path(r["path"])
                and not _is_hex_name(Path(r["path"]).stem)
            ][:5]
        if not key_files:  # last resort
            key_files = [r["path"] for r in rows[:5]]

        # --- Topics from TF-IDF over text + paths ---
        combined_text = " ".join(
            (r.get("text") or "") + " " + Path(r["path"]).stem.replace("-", " ")
            for r in rows
        )
        topics_raw = termsmod.top_toks(combined_text, 20)
        # Filter out hex-like tokens and pure numeric strings
        topics = [
            t for t, _ in topics_raw
            if len(t) > 2 and not HEX_RE.match(t)
            and not re.match(r"^[0-9a-f]{6,}$", t, re.I)
        ][:8]

        # --- Summary ---
        summary_text = _heuristic_summary(rows, topics, folders)

        # --- Confidence ---
        cluster_ids = [r["id"] for r in rows]
        confidence = _cluster_confidence(cluster_ids, embed_cache, conn, run_id)

        # Skip very low confidence clusters (likely noise)
        if confidence < 0.12 and file_count < 10:
            continue

        # --- Name: heuristic first, Gemma for top clusters ---
        name = _heuristic_name(rows, topics)
        if gemma_budget > 0:
            gemma_name = _gemma_name(cfg, folders, topics, key_files)
            if gemma_name:
                name = gemma_name
            gemma_budget -= 1

        # --- Color ---
        color = _category_color(breakdown)

        cards.append({
            "id": cid,
            "name": name,
            "file_count": file_count,
            "type_breakdown": breakdown,
            "folders": folders,
            "key_files": key_files,
            "topics": topics,
            "summary": summary_text,
            "confidence": confidence,
            "color": color,
        })

    # --- Post-process: sort by quality score, then deduplicate names ---
    # Quality = confidence * log2(file_count + 1) so high-confidence mid-sized
    # clusters rank above low-confidence mega-clusters (noise catch-alls).
    import math
    # Cap file_count at 150 so huge catch-all clusters don't out-rank tight ones
    cards.sort(
        key=lambda c: c["confidence"] * math.log2(min(c["file_count"], 150) + 1),
        reverse=True,
    )
    _dedupe_names(cards)
    return cards


def _dedupe_names(cards: list[dict]) -> None:
    """Append a differentiating topic/folder suffix to duplicate card names."""
    from collections import Counter
    name_count: Counter = Counter(c["name"] for c in cards)
    seen: dict[str, int] = {}
    for card in cards:
        name = card["name"]
        if name_count[name] <= 1:
            continue
        # Pick best differentiator: first unique topic not in name
        diff = ""
        for t in card.get("topics", []):
            label = t.replace("_", " ").title()
            if label.lower() not in name.lower() and len(label) > 3:
                diff = label
                break
        if not diff:
            folders = card.get("folders", [])
            for f in folders:
                if f.lower() not in name.lower():
                    diff = f
                    break
        if diff:
            card["name"] = f"{name} · {diff}"
        else:
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:
                card["name"] = f"{name} ({seen[name]})"
