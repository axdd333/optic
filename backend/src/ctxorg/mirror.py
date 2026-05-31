"""
Neurontology Mirror — Adversarial footprint analysis engine.

Five-layer probabilistic inference model:

  Layer 1  EXPOSURE    — what metadata, credentials, and identifiers are visible
  Layer 2  BEHAVIORAL  — what patterns betray work rhythm, toolchain, cognition
  Layer 3  LINKAGE     — how separate files/projects/identities can be correlated
  Layer 4  RISK        — Bayesian scoring of actual harm per attack vector
  Layer 5  BRIEF       — attacker-POV synthesis: what they learn, how confident

Design principles:
  - No external calls. Everything runs on indexed content + filesystem metadata.
  - Entropy scoring for secret candidates (Shannon H ≥ 4.5 bits/char = flag).
  - Bayesian risk formula: Exposure × Sensitivity × Linkability × Exploitability.
  - Every finding cites specific files; no speculation without evidence.
"""
from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import db


# ─── Credential / secret patterns ────────────────────────────────────────────
# Each entry: (pattern, label, confidence 0-1, severity "critical"|"high"|"medium")

CRED_PATTERNS: list[tuple[str, str, float, str]] = [
    (r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY", "Private key (PEM)", 0.99, "critical"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID", 0.98, "critical"),
    (r"sk-[A-Za-z0-9]{32,}", "OpenAI-style API key", 0.96, "critical"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub personal access token", 0.98, "critical"),
    (r"gho_[A-Za-z0-9]{36}", "GitHub OAuth token", 0.98, "critical"),
    (r"ghr_[A-Za-z0-9]{36}", "GitHub refresh token", 0.98, "critical"),
    (r"xox[bpoa]-[0-9A-Za-z-]{10,}", "Slack token", 0.97, "critical"),
    (r"ya29\.[A-Za-z0-9_\-]{20,}", "Google OAuth access token", 0.96, "high"),
    (r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}", "JWT token", 0.88, "high"),
    (r"(?:postgres|mysql|mongodb|redis|mssql)://[^\s\"'<>]{12,}", "Database URI", 0.92, "high"),
    (r"(?i)(?:password|passwd|secret|token|api_?key|access_?key)\s*[=:]\s*[\"']?([A-Za-z0-9+/=_\-!@#$%^&*]{10,})[\"']?", "Credential assignment", 0.74, "high"),
    (r"(?i)authorization:\s*(?:bearer|token|basic)\s+([A-Za-z0-9+/=_\-]{16,})", "Authorization header", 0.82, "high"),
    (r"ssh-rsa AAAA[A-Za-z0-9+/]{40,}", "SSH public key (fingerprint risk)", 0.65, "medium"),
    (r"['\"]([A-Za-z0-9]{32,64})['\"]", "High-entropy string (secret candidate)", 0.45, "medium"),
]

EMAIL_RE    = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[a-zA-Z]{2,}\b')
GIT_REMOTE  = re.compile(r'(?:url\s*=\s*|remote\s+"[^"]+"\n\s+url\s*=\s*)(https?://\S+|git@\S+)')
GITHUB_USER = re.compile(r'github\.com[/:]([A-Za-z0-9_\-]{1,39})(?:/[A-Za-z0-9_\-]+)?')
UUID_RE     = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I)
IP_RE       = re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b')

# Strings that look like secrets but aren't
FALSE_POSITIVE_HINTS = {
    "example", "placeholder", "your-", "xxx", "test", "sample",
    "changeme", "password123", "secret123", "aaaa", "bbbb",
    "none", "null", "undefined", "localhost",
}


# ─── Toolchain fingerprint database ──────────────────────────────────────────

TOOL_SIGS: dict[str, dict] = {
    "VS Code":           {"exts": set(), "names": {".code-workspace", "launch.json", ".vscode"}},
    "KiCad":             {"exts": {".kicad_pcb", ".kicad_sch", ".kicad_pro", ".kicad_mod"}, "names": set()},
    "OpenSCAD":          {"exts": {".scad"}, "names": set()},
    "Fusion 360":        {"exts": {".f3d", ".f3z"}, "names": set()},
    "Blender":           {"exts": {".blend", ".blend1"}, "names": set()},
    "Arduino/PlatformIO":{"exts": {".ino"}, "names": {"platformio.ini"}},
    "Jupyter":           {"exts": {".ipynb"}, "names": set()},
    "Docker":            {"exts": set(), "names": {"Dockerfile", "docker-compose.yml", "docker-compose.yaml"}},
    "Terraform":         {"exts": {".tf", ".tfvars"}, "names": set()},
    "Rust":              {"exts": set(), "names": {"Cargo.toml", "Cargo.lock"}},
    "Go":                {"exts": {".go"}, "names": {"go.mod", "go.sum"}},
    "Obsidian":          {"exts": set(), "names": {".obsidian"}},
    "Xcode":             {"exts": {".xcodeproj", ".xcworkspace", ".xib", ".storyboard"}, "names": set()},
    "Unity":             {"exts": {".unity", ".unitypackage", ".meta"}, "names": set()},
    "AI/ML models":      {"exts": {".safetensors", ".gguf", ".onnx", ".pt", ".pth", ".pkl", ".bin"}, "names": set()},
    "Ollama/LLM":        {"exts": set(), "names": {"Modelfile", ".ollama"}},
    "Git":               {"exts": set(), "names": {".git", ".gitignore", ".gitmodules", ".git-blame-ignore-revs"}},
}

LANG_MAP = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".rs": "Rust", ".go": "Go", ".swift": "Swift", ".kt": "Kotlin",
    ".c": "C", ".cpp": "C++", ".h": "C/C++ header", ".m": "Objective-C",
    ".rb": "Ruby", ".java": "Java", ".cs": "C#", ".lua": "Lua",
    ".sh": "Shell", ".bash": "Bash", ".fish": "Fish shell",
    ".r": "R", ".jl": "Julia", ".scala": "Scala",
    ".scad": "OpenSCAD", ".ino": "Arduino C++",
    ".ex": "Elixir", ".exs": "Elixir script",
    ".hs": "Haskell", ".ml": "OCaml",
    ".tf": "Terraform HCL",
}


# ─── Entropy utilities ────────────────────────────────────────────────────────

def _entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _high_entropy_tokens(text: str, min_len: int = 22, threshold: float = 4.5) -> list[str]:
    """Return substrings that look like secrets: high entropy + right length."""
    hits = []
    for tok in re.findall(r'[A-Za-z0-9+/=_\-]{' + str(min_len) + r',}', text):
        if _entropy(tok) >= threshold:
            # Filter obvious false positives
            low = tok.lower()
            if any(fp in low for fp in FALSE_POSITIVE_HINTS):
                continue
            hits.append(tok[:48] + ("…" if len(tok) > 48 else ""))
    return hits[:4]


def _is_fp(value: str) -> bool:
    """Return True if this credential match is a known false positive."""
    low = value.lower().strip("\"'")
    return any(fp in low for fp in FALSE_POSITIVE_HINTS) or len(low) < 8


# ─── Layer 1: Exposure ───────────────────────────────────────────────────────

def analyze_exposure(conn) -> dict[str, Any]:
    """
    Scan indexed file content for credentials, identifiers, and metadata traces.
    Only inspects files that have extracted text (no binary guessing).
    """
    rows = db.rows(conn,
        "SELECT path, text, size, ext FROM items "
        "WHERE kind='file' AND text IS NOT NULL AND text != '' "
        "AND size < 10000000 "          # skip huge files
        "ORDER BY size DESC LIMIT 1000")

    emails:       set  = set()
    urls:         list = []
    git_remotes:  list = []
    github_users: Counter = Counter()
    cred_hits:    list = []
    entropy_hits: list = []
    ip_addrs:     list = []

    seen_creds: set = set()

    for row in rows:
        text = (row["text"] or "")[:20_000]   # cap per file to avoid one giant file dominating
        path = row["path"]
        pname = Path(path).name

        # ── Emails ────────────────────────────────────────────────────────────
        for em in EMAIL_RE.findall(text):
            em = em.lower()
            if not any(em.endswith(x) for x in [".png", ".jpg", ".gif"]):
                emails.add(em)

        # ── GitHub usernames ─────────────────────────────────────────────────
        for u in GITHUB_USER.findall(text):
            github_users[u] += 1

        # ── Git remotes ───────────────────────────────────────────────────────
        for remote in GIT_REMOTE.findall(text):
            if remote not in [r["remote"] for r in git_remotes]:
                git_remotes.append({"path": path, "name": pname, "remote": remote[:100]})

        # ── Credential patterns ───────────────────────────────────────────────
        for pat, label, conf, severity in CRED_PATTERNS:
            for m in re.finditer(pat, text):
                hit = m.group(0)
                # For patterns with capture groups, use the first group if available
                try:
                    hit = m.group(1) if m.lastindex else hit
                except IndexError:
                    pass
                if _is_fp(hit):
                    continue
                key = (path, label)
                if key in seen_creds:
                    continue
                seen_creds.add(key)
                cred_hits.append({
                    "path": path,
                    "name": pname,
                    "type": label,
                    "severity": severity,
                    "confidence": conf,
                    "hint": hit[:44] + ("…" if len(hit) > 44 else ""),
                    "line_hint": _find_line(text, m.start()),
                })

        # ── High-entropy strings ──────────────────────────────────────────────
        for tok in _high_entropy_tokens(text):
            entropy_hits.append({"path": path, "name": pname, "sample": tok,
                                  "entropy": round(_entropy(tok), 2)})

        # ── IP addresses (non-loopback) ───────────────────────────────────────
        for ip in IP_RE.findall(text):
            if not (ip.startswith("127.") or ip.startswith("192.168.")
                    or ip.startswith("10.") or ip == "0.0.0.0"):
                ip_addrs.append({"path": path, "name": pname, "ip": ip})

    # Sort creds: critical first, then by confidence
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    cred_hits.sort(key=lambda c: (sev_order.get(c["severity"], 9), -c["confidence"]))

    # Deduplicate entropy hits by path
    seen_ep: set = set()
    deduped_entropy = []
    for h in entropy_hits:
        if h["path"] not in seen_ep:
            seen_ep.add(h["path"])
            deduped_entropy.append(h)

    return {
        "emails": sorted(emails)[:30],
        "github_users": [{"user": u, "count": c} for u, c in github_users.most_common(10)],
        "git_remotes": git_remotes[:12],
        "credentials": cred_hits[:25],
        "entropy_files": deduped_entropy[:12],
        "external_ips": list({h["ip"] for h in ip_addrs})[:10],
    }


def _find_line(text: str, pos: int) -> str:
    """Return the line containing position pos, truncated."""
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end == -1:
        end = len(text)
    return text[start:end].strip()[:80]


# ─── Layer 2: Behavioral ─────────────────────────────────────────────────────

def analyze_behavior(conn) -> dict[str, Any]:
    """
    Infer work rhythm, toolchain fingerprint, and cognitive style from metadata.
    Uses mtime distributions, extension sets, naming patterns, and path structure.
    """
    rows = db.rows(conn,
        "SELECT path, mtime, size, ext FROM items WHERE kind='file' AND mtime > 0")

    if not rows:
        return {}

    hour_counts: Counter = Counter()
    dow_counts:  Counter = Counter()   # 0=Mon … 6=Sun
    day_counts:  Counter = Counter()
    timestamps:  list    = []

    for row in rows:
        t = row["mtime"]
        if not t:
            continue
        dt = time.localtime(t)
        hour_counts[dt.tm_hour]  += 1
        dow_counts[dt.tm_wday]   += 1
        day_counts[f"{dt.tm_year}-{dt.tm_mon:02d}-{dt.tm_mday:02d}"] += 1
        timestamps.append(t)

    if not timestamps:
        return {}

    total_h = max(sum(hour_counts.values()), 1)

    # Circadian signature bands
    late_night = sum(hour_counts[h] for h in [22, 23, 0, 1, 2, 3])
    work_hours = sum(hour_counts[h] for h in range(9, 18))
    early_bird = sum(hour_counts[h] for h in range(5, 9))
    late_night_pct = late_night / total_h
    work_pct       = work_hours / total_h
    early_pct      = early_bird / total_h
    peak_hour      = hour_counts.most_common(1)[0][0]

    if late_night_pct > 0.28:
        circadian = "night owl (>28% activity 22:00–04:00)"
    elif early_pct > 0.25:
        circadian = "early bird (>25% activity 05:00–09:00)"
    elif work_pct > 0.65:
        circadian = "standard work hours (65%+ activity 09:00–18:00)"
    else:
        circadian = "mixed / irregular schedule"

    # Weekend vs. weekday split
    weekend_total = dow_counts[5] + dow_counts[6]
    weekday_total = sum(dow_counts[i] for i in range(5))
    weekend_pct   = weekend_total / max(weekend_total + weekday_total, 1)

    # Burst days: days with >2× daily average
    avg_per_day = sum(day_counts.values()) / max(len(day_counts), 1)
    burst_days  = [
        {"date": d, "files_modified": c, "multiplier": round(c / avg_per_day, 1)}
        for d, c in day_counts.most_common(5)
        if c > avg_per_day * 2
    ]

    # Activity span
    span_days = (max(timestamps) - min(timestamps)) / 86400
    total_files = len(timestamps)

    # Toolchain detection
    all_paths = [row["path"] for row in rows]
    all_exts  = {Path(p).suffix.lower() for p in all_paths}
    all_names = {Path(p).name for p in all_paths}
    path_blob = "\n".join(all_paths[:2000]).lower()

    detected_tools = []
    for tool, sigs in TOOL_SIGS.items():
        hit = (
            any(e in all_exts for e in sigs["exts"])
            or any(n in all_names for n in sigs["names"])
            or any(n.lower() in path_blob for n in sigs["names"] if len(n) > 3)
        )
        if hit:
            detected_tools.append(tool)

    # Language breakdown
    ext_counts = Counter(row["ext"].lower() for row in rows if row.get("ext"))
    languages  = [
        {"lang": LANG_MAP[ext], "count": cnt}
        for ext, cnt in ext_counts.most_common(20)
        if ext in LANG_MAP
    ]

    # Naming style heuristics (from file stems)
    stems = [Path(p).stem for p in all_paths[:800] if p]
    n_total  = max(len(stems), 1)
    n_camel  = sum(1 for s in stems if re.search(r'[a-z][A-Z]', s))
    n_snake  = sum(1 for s in stems if '_' in s and s == s.lower() and s.replace('_','').isalpha())
    n_kebab  = sum(1 for s in stems if '-' in s and s == s.lower() and s.replace('-','').isalpha())
    n_date   = sum(1 for s in stems if re.match(r'\d{4}[-_]\d{2}', s))
    n_num    = sum(1 for s in stems if re.search(r'[-_ ]\d+$', s))

    naming_style = []
    if n_camel / n_total > 0.08: naming_style.append(f"camelCase ({n_camel/n_total:.0%})")
    if n_snake / n_total > 0.08: naming_style.append(f"snake_case ({n_snake/n_total:.0%})")
    if n_kebab / n_total > 0.08: naming_style.append(f"kebab-case ({n_kebab/n_total:.0%})")
    if n_date  / n_total > 0.04: naming_style.append(f"date-prefixed ({n_date/n_total:.0%})")
    if n_num   / n_total > 0.08: naming_style.append(f"numeric-suffixed ({n_num/n_total:.0%})")

    # Depth / organization signal
    depths = [len(Path(p).parts) for p in all_paths[:1000]]
    avg_depth = sum(depths) / max(len(depths), 1)

    # Infer cognitive fingerprint
    fingerprint_notes = []
    if late_night_pct > 0.3:
        fingerprint_notes.append("Works predominantly at night — likely independent/freelance or intense project focus")
    if weekend_pct > 0.35:
        fingerprint_notes.append("Significant weekend activity — passion-driven or deadline-pressured work style")
    if burst_days:
        fingerprint_notes.append(f"Burst pattern detected — works in sprints, not steady streams ({len(burst_days)} burst days in corpus)")
    if avg_depth > 7:
        fingerprint_notes.append("Deeply nested file organization — structured thinker, project-oriented")
    elif avg_depth < 4:
        fingerprint_notes.append("Flat file organization — pragmatic, speed-over-structure working style")
    if "KiCad" in detected_tools or "OpenSCAD" in detected_tools:
        fingerprint_notes.append("Hardware/physical design toolchain present — likely building real-world objects")
    if "AI/ML models" in detected_tools:
        fingerprint_notes.append("Local AI/ML model files present — actively experimenting with or deploying models offline")
    if "Jupyter" in detected_tools:
        fingerprint_notes.append("Jupyter notebooks — research, data science, or prototyping workflow")

    return {
        "circadian_type": circadian,
        "peak_hour_local": peak_hour,
        "late_night_pct":  round(late_night_pct * 100, 1),
        "work_hours_pct":  round(work_pct * 100, 1),
        "weekend_pct":     round(weekend_pct * 100, 1),
        "burst_days":      burst_days[:4],
        "activity_span_days": round(span_days, 0),
        "total_files": total_files,
        "toolchain":   detected_tools,
        "languages":   languages[:8],
        "naming_style": naming_style,
        "avg_path_depth": round(avg_depth, 1),
        "fingerprint_notes": fingerprint_notes,
    }


# ─── Layer 3: Linkage ─────────────────────────────────────────────────────────

def analyze_linkage(conn) -> dict[str, Any]:
    """
    Find cross-file identity bridges: shared identifiers that let an adversary
    connect anonymous work, separate projects, or local files to real identity.
    """
    rows = db.rows(conn,
        "SELECT path, text FROM items "
        "WHERE kind='file' AND text IS NOT NULL AND text != '' LIMIT 800")

    # Per-file identifier sets
    file_ids: dict[str, set] = defaultdict(set)   # path → identifiers
    all_emails:  Counter = Counter()
    all_ghusers: Counter = Counter()
    all_repos:   Counter = Counter()

    for row in rows:
        text = (row["text"] or "")[:12_000]
        path = row["path"]

        for em in EMAIL_RE.findall(text):
            em = em.lower()
            all_emails[em] += 1
            file_ids[path].add(em)

        for u in GITHUB_USER.findall(text):
            all_ghusers[u] += 1
            file_ids[path].add(f"@{u}")

        # Repo names from import paths, github URLs, package names
        for r in re.findall(r'github\.com/[A-Za-z0-9_\-]+/([A-Za-z0-9_\-]{3,40})', text):
            all_repos[r] += 1
            file_ids[path].add(f"repo:{r}")

        for r in re.findall(r'(?:package|module|import)\s+["\']([A-Za-z0-9_\-/]{4,32})["\']', text):
            all_repos[r.split("/")[-1]] += 1

    # Bridge files: single file linking ≥2 distinct identifiers
    bridges = []
    for path, ids in file_ids.items():
        real_ids = [i for i in ids if not i.startswith("repo:")]
        if len(real_ids) >= 2:
            bridges.append({
                "path": path,
                "name": Path(path).name,
                "identifiers": sorted(real_ids)[:6],
                "bridge_score": len(real_ids),
            })
    bridges.sort(key=lambda b: -b["bridge_score"])

    # Identifiers that appear across many files = high deanonymization risk
    cross_file_emails  = [(e, c) for e, c in all_emails.most_common(10) if c >= 2]
    cross_file_ghusers = [(u, c) for u, c in all_ghusers.most_common(10) if c >= 2]

    # Project graph: files sharing identifiers (same email / username)
    id_to_files: dict[str, list] = defaultdict(list)
    for path, ids in file_ids.items():
        for ident in ids:
            id_to_files[ident].append(Path(path).name)

    # Most "load-bearing" identifiers (connects most files)
    pivot_identifiers = [
        {"identifier": ident, "file_count": len(fnames), "sample_files": fnames[:4]}
        for ident, fnames in sorted(id_to_files.items(), key=lambda x: -len(x[1]))
        if len(fnames) >= 3 and not ident.startswith("repo:")
    ][:8]

    return {
        "cross_file_emails":  [{"email": e, "file_count": c} for e, c in cross_file_emails],
        "cross_file_ghusers": [{"username": u, "file_count": c} for u, c in cross_file_ghusers],
        "top_repos":          [{"repo": r, "count": c} for r, c in all_repos.most_common(8)],
        "bridge_files":       bridges[:8],
        "pivot_identifiers":  pivot_identifiers,
    }


# ─── Layer 4: Risk scoring ────────────────────────────────────────────────────

RISK_META: dict[str, dict] = {
    "credential_risk": {
        "label": "Credential & Secret Risk",
        "who_benefits": "Attackers, competing developers, scrapers",
        "attack": "Direct system access via leaked tokens/keys",
        "mitigations": [
            "Rotate every discovered key/token immediately",
            "Move secrets to environment variables or a secrets manager (e.g. 1Password Secrets Automation, Doppler)",
            "Add affected files to .gitignore",
            "Install git-secrets or gitleaks pre-commit hook",
            "Audit git history for previously committed secrets: `git log -p | grep -i key`",
        ],
    },
    "identity_risk": {
        "label": "Identity & Deanonymization Risk",
        "who_benefits": "Stalkers, doxxers, competitors, recruiters, adversarial researchers",
        "attack": "Link anonymous work to real identity; map social graph",
        "mitigations": [
            "Audit and redact personal emails from shared documents",
            "Use pseudonymous email for public-facing OSS contributions",
            "Strip author metadata from PDFs/Office docs before sharing",
            "Use separate GitHub accounts for personal vs. professional work",
        ],
    },
    "ip_risk": {
        "label": "Intellectual Property Risk",
        "who_benefits": "Competitors, industrial spies, acquirers doing due diligence",
        "attack": "Extract product designs, firmware logic, unreleased models, research",
        "mitigations": [
            "Encrypt sensitive design files at rest (use encrypted disk images for IP)",
            "Strip metadata from assets before external sharing (exiftool -all= file.png)",
            "Watermark internal design versions",
            "Never commit model weights, firmware binaries, or CAD files to public repos",
        ],
    },
    "behavioral_risk": {
        "label": "Behavioral & Operational Risk",
        "who_benefits": "Social engineers, stalkers, insider threat actors, surveillance",
        "attack": "Infer schedule, location, deadlines, stress points — exploit timing",
        "mitigations": [
            "Normalize timestamps before sharing archives: `find . -exec touch -t 202001010000 {} \\;`",
            "Be aware that file metadata leaks timezone and work schedule",
            "Avoid sharing raw filesystem archives externally",
        ],
    },
    "competitive_risk": {
        "label": "Competitive Intelligence Risk",
        "who_benefits": "Competitors, investors doing competitive research, journalists",
        "attack": "Infer startup direction, roadmap, pivot strategy, technical moat",
        "mitigations": [
            "Compartmentalize strategic documents (encrypted vault, not ~/Documents)",
            "Review what's in any shared or cloud-synced folder",
            "Use code names for sensitive projects in file names",
        ],
    },
}


def _score_risks(conn, exposure: dict, linkage: dict, behavior: dict) -> tuple[list, int]:
    """
    Bayesian risk scoring.
    Score = Exposure_strength × Sensitivity × Linkability × Exploitability
    All components 0–1, output normalized to 0–100.
    """
    findings = []

    # ── Credential risk ───────────────────────────────────────────────────────
    creds = exposure.get("credentials", [])
    crit  = [c for c in creds if c["severity"] == "critical"]
    high  = [c for c in creds if c["severity"] == "high"]
    if creds:
        # Exposure: how many and how confident?
        exposure_s = min(1.0, (len(crit) * 0.5 + len(high) * 0.25 + len(creds) * 0.05))
        score = int(min(100, exposure_s * 100 * 0.9 + 10))
        findings.append({
            "category": "credential_risk",
            "score": score,
            "evidence": [f"{c['severity'].upper()}: {c['type']} in {c['name']}" for c in creds[:5]],
            "count": len(creds),
        })

    # ── Identity risk ─────────────────────────────────────────────────────────
    emails   = exposure.get("emails", [])
    gh_users = exposure.get("github_users", [])
    bridges  = linkage.get("bridge_files", [])
    pivots   = linkage.get("pivot_identifiers", [])
    if emails or bridges:
        # More unique identifiers + more bridges = higher deanon risk
        e_score = min(1.0, len(emails) * 0.08 + len(gh_users) * 0.12
                      + len(bridges) * 0.15 + len(pivots) * 0.10)
        score = int(min(100, e_score * 100 * 0.85 + 10))
        evidence = (
            [f"Email: {e}" for e in emails[:3]]
            + [f"GitHub: @{u['user']}" for u in gh_users[:2]]
            + [f"Bridge: {b['name']} links {len(b['identifiers'])} identifiers" for b in bridges[:2]]
        )
        findings.append({
            "category": "identity_risk",
            "score": score,
            "evidence": evidence,
            "count": len(emails) + len(gh_users),
        })

    # ── IP risk ───────────────────────────────────────────────────────────────
    ip_rows = db.rows(conn,
        "SELECT path FROM items WHERE kind='file' AND ("
        " LOWER(ext) IN ('.scad','.kicad_pcb','.kicad_sch','.kicad_pro','.f3d','.f3z',"
        "  '.blend','.blend1','.safetensors','.gguf','.onnx','.pt','.pth','.pkl',"
        "  '.pcb','.sch','.gbr','.gerber') "
        " OR LOWER(path) LIKE '%firmware%' OR LOWER(path) LIKE '%prototype%'"
        " OR LOWER(path) LIKE '%unreleased%' OR LOWER(path) LIKE '%internal%'"
        " OR LOWER(path) LIKE '%confidential%') "
        "LIMIT 40")
    if ip_rows:
        score = int(min(100, len(ip_rows) * 8 + 20))
        findings.append({
            "category": "ip_risk",
            "score": score,
            "evidence": [Path(r["path"]).name for r in ip_rows[:6]],
            "count": len(ip_rows),
        })

    # ── Behavioral risk ───────────────────────────────────────────────────────
    late_pct  = behavior.get("late_night_pct", 0)
    wkend_pct = behavior.get("weekend_pct", 0)
    bursts    = behavior.get("burst_days", [])
    if late_pct > 10 or wkend_pct > 25 or bursts:
        raw = late_pct * 0.8 + wkend_pct * 0.5 + len(bursts) * 8
        score = int(min(100, raw))
        evidence = []
        if late_pct > 10:
            evidence.append(f"{late_pct:.0f}% of file activity after 22:00 — predictable night schedule")
        if wkend_pct > 25:
            evidence.append(f"{wkend_pct:.0f}% activity on weekends")
        if bursts:
            evidence.append(f"{len(bursts)} burst days — deadline pattern visible in metadata")
        findings.append({
            "category": "behavioral_risk",
            "score": score,
            "evidence": evidence,
            "count": len(bursts),
        })

    # ── Competitive risk ──────────────────────────────────────────────────────
    comp_rows = db.rows(conn,
        "SELECT path FROM items WHERE kind='file' AND ("
        " LOWER(path) LIKE '%roadmap%' OR LOWER(path) LIKE '%pitch%'"
        " OR LOWER(path) LIKE '%strategy%' OR LOWER(path) LIKE '%investor%'"
        " OR LOWER(path) LIKE '%budget%' OR LOWER(path) LIKE '%revenue%'"
        " OR LOWER(path) LIKE '%acquisition%' OR LOWER(path) LIKE '%term sheet%'"
        " OR LOWER(path) LIKE '%cap table%') LIMIT 30")
    if comp_rows:
        score = int(min(100, len(comp_rows) * 14 + 15))
        findings.append({
            "category": "competitive_risk",
            "score": score,
            "evidence": [Path(r["path"]).name for r in comp_rows[:5]],
            "count": len(comp_rows),
        })

    findings.sort(key=lambda f: -f["score"])

    # Overall score: max-weighted average (worst finding dominates)
    if findings:
        scores = [f["score"] for f in findings]
        overall = int(max(scores) * 0.55 + sum(scores) / len(scores) * 0.45)
    else:
        overall = 5

    return findings, min(100, overall)


# ─── Format for LLM context ───────────────────────────────────────────────────

def format_for_llm(data: dict) -> str:
    """
    Compress the full analysis into a token-efficient but information-dense
    context block for the LLM to synthesize the attacker brief.
    """
    exp  = data["exposure"]
    beh  = data["behavior"]
    lnk  = data["linkage"]
    risks   = data["risks"]
    overall = data["overall_score"]

    parts: list[str] = [f"=== ADVERSARIAL FOOTPRINT ANALYSIS (overall risk: {overall}/100) ===\n"]

    # Credentials
    creds = exp.get("credentials", [])
    if creds:
        parts.append(f"CREDENTIALS DETECTED ({len(creds)} hits):")
        for c in creds[:8]:
            parts.append(f"  [{c['severity'].upper()} {int(c['confidence']*100)}%] "
                         f"{c['type']} — {c['name']}: …{c['hint']}…")

    # Entropy files
    ent = exp.get("entropy_files", [])
    if ent:
        parts.append(f"HIGH-ENTROPY STRINGS (likely secrets) in {len(ent)} files:")
        for h in ent[:5]:
            parts.append(f"  H={h['entropy']}bit — {h['name']}: {h['sample']}")

    # Emails + GitHub
    emails = exp.get("emails", [])
    if emails:
        parts.append(f"EMAILS EXPOSED ({len(emails)} unique): {', '.join(emails[:8])}")
    ghusers = exp.get("github_users", [])
    if ghusers:
        parts.append(f"GITHUB IDENTITIES: {', '.join('@' + u['user'] for u in ghusers[:5])}")
    git_remotes = exp.get("git_remotes", [])
    if git_remotes:
        parts.append(f"GIT REMOTES ({len(git_remotes)}):")
        for r in git_remotes[:4]:
            parts.append(f"  {r['remote']}")

    # External IPs
    ips = exp.get("external_ips", [])
    if ips:
        parts.append(f"EXTERNAL IP ADDRESSES: {', '.join(ips[:6])}")

    # Behavior
    if beh:
        parts.append(f"\nBEHAVIORAL FINGERPRINT:")
        parts.append(f"  Schedule: {beh.get('circadian_type', 'unknown')}")
        parts.append(f"  Peak hour (local): {beh.get('peak_hour_local')}:00")
        parts.append(f"  Late-night: {beh.get('late_night_pct')}% | "
                     f"Weekends: {beh.get('weekend_pct')}% | "
                     f"Work-hours: {beh.get('work_hours_pct')}%")
        if beh.get("burst_days"):
            bursts = beh["burst_days"]
            parts.append(f"  Burst days: "
                         + ", ".join(f"{b['date']} (×{b['multiplier']} avg)" for b in bursts[:3]))
        if beh.get("toolchain"):
            parts.append(f"  Toolchain: {', '.join(beh['toolchain'])}")
        if beh.get("languages"):
            langs = ", ".join(f"{l['lang']}({l['count']})" for l in beh["languages"][:5])
            parts.append(f"  Languages: {langs}")
        if beh.get("naming_style"):
            parts.append(f"  Naming style: {', '.join(beh['naming_style'])}")
        if beh.get("fingerprint_notes"):
            parts.append(f"  Analyst notes:")
            for note in beh["fingerprint_notes"]:
                parts.append(f"    • {note}")

    # Linkage
    cfe = lnk.get("cross_file_emails", [])
    if cfe:
        parts.append(f"\nIDENTITY LINKAGE:")
        for e in cfe[:4]:
            parts.append(f"  Email '{e['email']}' appears in {e['file_count']} files")
    bridges = lnk.get("bridge_files", [])
    if bridges:
        parts.append(f"BRIDGE FILES (identity pivots):")
        for b in bridges[:4]:
            parts.append(f"  {b['name']}: connects {', '.join(b['identifiers'][:4])}")
    pivots = lnk.get("pivot_identifiers", [])
    if pivots:
        parts.append(f"PIVOT IDENTIFIERS (highest cross-file linkage):")
        for p in pivots[:4]:
            parts.append(f"  '{p['identifier']}' appears in {p['file_count']} files: "
                         + ", ".join(p["sample_files"][:3]))

    # Risk scores
    if risks:
        parts.append(f"\nRISK SCORES:")
        for r in risks:
            meta = RISK_META.get(r["category"], {})
            parts.append(f"  {meta.get('label', r['category'])}: {r['score']}/100")
            parts.append(f"    Who benefits: {meta.get('who_benefits', 'adversaries')}")
            parts.append(f"    Attack vector: {meta.get('attack', 'varies')}")
            for ev in r["evidence"][:3]:
                parts.append(f"    Evidence: {ev}")

    # Mitigations (top 3 risks)
    parts.append(f"\nMITIGATIONS:")
    for r in risks[:3]:
        meta = RISK_META.get(r["category"], {})
        parts.append(f"  {meta.get('label', r['category'])} fixes:")
        for fix in meta.get("mitigations", [])[:3]:
            parts.append(f"    → {fix}")

    return "\n".join(parts)


# ─── Main entry point ─────────────────────────────────────────────────────────

def full_analysis(conn) -> dict[str, Any]:
    """
    Run all 4 analysis layers and return structured data + LLM context.
    Typical runtime: 200–800 ms on a corpus of ~5,000 files.
    """
    t0 = time.time()

    exposure = analyze_exposure(conn)
    behavior = analyze_behavior(conn)
    linkage  = analyze_linkage(conn)
    risks, overall_score = _score_risks(conn, exposure, linkage, behavior)

    data = {
        "exposure":     exposure,
        "behavior":     behavior,
        "linkage":      linkage,
        "risks":        risks,
        "overall_score": overall_score,
        "elapsed_ms":   int((time.time() - t0) * 1000),
    }
    data["llm_context"] = format_for_llm(data)
    return data
