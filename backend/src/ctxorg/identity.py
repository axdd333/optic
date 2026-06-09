"""
Identity inference — entity profile generation for Optic/Iris.

Each local file becomes an EntityProfile: a structured evidence record of what
the file contains, what it implies, and what audiences would infer from it.

V1 entity type: local file (asset). The schema generalises to emails, tweets,
calendar events, contacts, transactions, and social media exports — add those
entity types by extending detect_role() and the ROLE_PATTERNS list.

Architecture mirrors the MiroFish pattern:
  asset → heuristic extraction → optional LLM deepening → EntityProfile
  EntityProfile → cached in DB → retrieved by Iris for inference queries
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from . import db, terms


# ---------------------------------------------------------------------------
# Role detection
# ---------------------------------------------------------------------------

ROLE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"resume|curriculum.vitae", re.I), "resume"),
    (re.compile(r"cover.letter", re.I), "cover_letter"),
    (re.compile(r"bank.?statement|statement.of.account|account.summary", re.I), "bank_statement"),
    (re.compile(r"invoice|receipt|payment|expense", re.I), "financial_document"),
    (re.compile(r"contract|agreement|lease|nda|non.disclosure", re.I), "legal_document"),
    (re.compile(r"medical|health|prescription|diagnosis", re.I), "medical_document"),
    (re.compile(r"passport|visa|id.card|driver.?s.license", re.I), "identity_document"),
    (re.compile(r"ssh|\.pem|private.?key|\.env|credentials|secrets", re.I), "credential"),
    (re.compile(r"calendar|schedule|meeting|appointment", re.I), "calendar"),
    (re.compile(r"transcript|grade|diploma|certificate|degree", re.I), "academic"),
    (re.compile(r"linkedin|portfolio|bio|about.me", re.I), "professional_profile"),
    (re.compile(r"tax|irs|w.?2|1099|filing", re.I), "tax_document"),
    (re.compile(r"thesis|dissertation|research|publication|journal", re.I), "research"),
    (re.compile(r"note|diary|journal|memo", re.I), "notes"),
]

EXT_ROLES: dict[str, str] = {
    ".py": "code", ".js": "code", ".ts": "code", ".go": "code",
    ".rs": "code", ".cpp": "code", ".c": "code", ".java": "code",
    ".swift": "code", ".kt": "code", ".rb": "code", ".sh": "code",
    ".pdf": "document", ".docx": "document", ".doc": "document",
    ".pages": "document", ".rtf": "document",
    ".md": "notes", ".txt": "notes", ".rst": "notes",
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".heic": "image", ".tiff": "image", ".webp": "image",
    ".csv": "spreadsheet", ".tsv": "spreadsheet",
    ".xlsx": "spreadsheet", ".xls": "spreadsheet",
    ".json": "config", ".yaml": "config", ".yml": "config",
    ".toml": "config", ".xml": "config", ".ini": "config", ".conf": "config",
    ".pem": "credential", ".key": "credential", ".p12": "credential",
}


def detect_role(item: dict) -> str:
    combined = f"{item.get('path', '')} {(item.get('text') or '')[:600]}".lower()
    for pattern, role in ROLE_PATTERNS:
        if pattern.search(combined):
            return role
    ext = (item.get("ext") or "").lower()
    return EXT_ROLES.get(ext, "file")


# ---------------------------------------------------------------------------
# Heuristic entity extraction
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_RE = re.compile(r"https?://[^\s<>\"']{6,}")
_PHONE_RE = re.compile(r"\b\+?\d[\d\- ()]{7,}\d\b")
_DATE_RE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b"
    r"|\b\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b"
    r"|\b\d{4}[/\-]\d{2}[/\-]\d{2}\b", re.I
)
_NAME_RE = re.compile(r"\b([A-Z][a-z]{2,})\s+([A-Z][a-z]{2,})(?:\s+([A-Z][a-z]{2,}))?\b")
_ORG_SUFFIX_RE = re.compile(
    r"\b[\w\s]{2,30}?\s+(?:Inc|LLC|Ltd|Corp|Co\.|GmbH|SA|PLC|Foundation|"
    r"University|College|Institute|Agency|Bureau|Department|Ministry)\b"
)

_STOP_NAMES = frozenset({
    "January", "February", "March", "April", "June", "July", "August",
    "September", "October", "November", "December", "Monday", "Tuesday",
    "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "The", "This", "That", "These", "Those", "With", "From", "Your",
})

_PATH_STOPS = frozenset({
    "Users", "Library", "Documents", "Desktop", "Downloads",
    "Developer", "Projects", "Code", "ahmedm", "home", "usr",
    "Applications", "Movies", "Music", "Pictures", "Public",
})


def heuristic_extract(item: dict) -> dict:
    text = (item.get("text") or "")[:8000]
    path = item.get("path") or ""
    combined = f"{path}\n{text}"

    emails = list(dict.fromkeys(_EMAIL_RE.findall(combined)))[:6]
    phones = list(dict.fromkeys(_PHONE_RE.findall(combined)))[:4]
    dates = list(dict.fromkeys(_DATE_RE.findall(combined)))[:8]
    urls = list(dict.fromkeys(_URL_RE.findall(combined)))[:6]

    people: list[str] = []
    for m in _NAME_RE.finditer(text):
        first = m.group(1)
        if first not in _STOP_NAMES:
            people.append(m.group(0).strip())
    people = list(dict.fromkeys(people))[:8]

    orgs: list[str] = []
    for m in _ORG_SUFFIX_RE.finditer(text):
        org = m.group(0).strip()
        if 4 < len(org) < 60:
            orgs.append(org)
    orgs = list(dict.fromkeys(orgs))[:6]

    topics = [t for t, _ in terms.top_toks(text, 20)][:10]

    projects: list[str] = []
    for part in Path(path).parts:
        if (len(part) > 3 and not part.startswith(".")
                and part not in _PATH_STOPS and part != part.lower()):
            projects.append(part)
    projects = projects[:4]

    return {
        "emails": emails,
        "phones": phones,
        "dates": dates,
        "urls": urls,
        "people": people,
        "organizations": orgs,
        "topics": topics,
        "projects": projects,
    }


# ---------------------------------------------------------------------------
# Risk & signal detection
# ---------------------------------------------------------------------------

_SEC_HINTS = frozenset({
    "access_token", "refresh_token", "private_key", "secret", "apikey",
    "api_key", "ssh", "pem", "credential", "password", "token",
})
_PII_HINTS = frozenset({
    "passport", "ssn", "social security", "routing", "iban", "swift", "tax id",
    "invoice", "bank", "credit card", "debit", "date of birth", "dob",
})
_LIFE_HINTS = frozenset({
    "health", "therapy", "medical", "legal", "court", "family",
    "mortgage", "debt", "layoff", "fired", "interview", "stress",
})

_ROLE_SEVERITY: dict[str, str] = {
    "credential": "critical",
    "identity_document": "high",
    "bank_statement": "high",
    "tax_document": "high",
    "medical_document": "high",
    "legal_document": "medium",
    "financial_document": "medium",
    "resume": "low",
    "professional_profile": "low",
}


def detect_risks(item: dict, extracted: dict, role: str) -> list[dict]:
    text = f"{item.get('path', '')} {(item.get('text') or '')[:4000]}".lower()
    risks: list[dict] = []

    if role == "credential" or any(h in text for h in _SEC_HINTS):
        risks.append({
            "type": "credential_exposure",
            "severity": "critical" if role == "credential" else "high",
            "description": "File may contain API keys, tokens, or private credentials",
            "confidence": 0.9 if role == "credential" else 0.65,
        })

    if extracted.get("emails"):
        risks.append({
            "type": "contact_exposure",
            "severity": "medium",
            "description": f"Reveals {len(extracted['emails'])} email contact(s)",
            "confidence": 0.9,
        })

    if any(h in text for h in _PII_HINTS) or role in (
        "bank_statement", "tax_document", "identity_document", "medical_document"
    ):
        risks.append({
            "type": "pii_exposure",
            "severity": _ROLE_SEVERITY.get(role, "medium"),
            "description": "Contains personally identifiable or sensitive financial information",
            "confidence": 0.8,
        })

    if any(h in text for h in _LIFE_HINTS):
        risks.append({
            "type": "sensitive_life_context",
            "severity": "medium",
            "description": "References sensitive personal life events or circumstances",
            "confidence": 0.6,
        })

    if role == "resume":
        risks.append({
            "type": "professional_exposure",
            "severity": "low",
            "description": "Resume discloses employment history, skills, and contact info",
            "confidence": 0.85,
        })

    if extracted.get("urls"):
        risks.append({
            "type": "url_disclosure",
            "severity": "low",
            "description": f"Contains {len(extracted['urls'])} URL(s) that may reveal services or identity",
            "confidence": 0.75,
        })

    return risks


_LANG_MAP: dict[str, str] = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".go": "Go", ".rs": "Rust", ".swift": "Swift", ".kt": "Kotlin",
    ".cpp": "C++", ".c": "C", ".java": "Java", ".rb": "Ruby",
}


def detect_signals(item: dict, extracted: dict, role: str) -> list[dict]:
    signals: list[dict] = []

    if role in ("resume", "cover_letter", "professional_profile"):
        signals.append({
            "signal_type": "professional_identity",
            "description": "Signals professional role, skills, and employment history",
            "confidence": 0.85,
            "audience_visibility": ["recruiter", "employer", "investor", "algorithm"],
        })

    if role in ("bank_statement", "tax_document", "financial_document"):
        signals.append({
            "signal_type": "financial_profile",
            "description": "Signals financial status, transaction patterns, or income level",
            "confidence": 0.80,
            "audience_visibility": ["investor", "adversarial"],
        })

    if role == "code":
        ext = (item.get("ext") or "").lower()
        lang = _LANG_MAP.get(ext, "code")
        signals.append({
            "signal_type": "technical_skill",
            "description": f"Demonstrates {lang} programming competency",
            "confidence": 0.9,
            "audience_visibility": ["recruiter", "peers", "technical_reviewer", "investor"],
        })

    if extracted.get("emails"):
        signals.append({
            "signal_type": "network_connections",
            "description": f"References {len(extracted['emails'])} contact(s) — partial relationship graph",
            "confidence": 0.7,
            "audience_visibility": ["adversarial", "investigator"],
        })

    if role == "academic":
        signals.append({
            "signal_type": "academic_credential",
            "description": "Signals academic achievement, research focus, or institutional affiliation",
            "confidence": 0.85,
            "audience_visibility": ["employer", "institution", "professor", "recruiter"],
        })

    if role == "medical_document":
        signals.append({
            "signal_type": "health_profile",
            "description": "Signals health conditions, treatments, or medical history",
            "confidence": 0.9,
            "audience_visibility": ["insurer", "employer", "adversarial"],
        })

    if role == "notes":
        signals.append({
            "signal_type": "cognitive_style",
            "description": "Reveals thinking patterns, interests, and private reflection",
            "confidence": 0.55,
            "audience_visibility": ["adversarial", "profiler"],
        })

    return signals


# ---------------------------------------------------------------------------
# LLM deep extraction (optional — degrades gracefully)
# ---------------------------------------------------------------------------

def _llm_extract(cfg: dict, item: dict, role: str) -> dict:
    """Attempt LLM-based structured extraction. Returns {} on any failure."""
    try:
        from . import ollama as ollama_mod
        text = (item.get("text") or "")[:3000]
        name = Path(item.get("path") or "").name
        prompt = (
            f'Analyze this file for identity inference. Return ONLY valid JSON, no other text.\n'
            f'File: {name} | Role: {role}\n'
            f'Text:\n{text}\n\n'
            f'JSON schema:\n'
            f'{{"summary":"one sentence","people":[],"organizations":[],"locations":[],'
            f'"projects":[],"key_skills":[],"direct_claims":[],"inferred_claims":[],'
            f'"open_questions":[]}}'
        )
        raw = ollama_mod.gen(cfg, prompt, feature="identity")
        if isinstance(raw, dict):
            keys = {"summary", "people", "organizations", "locations",
                    "projects", "key_skills", "direct_claims",
                    "inferred_claims", "open_questions"}
            if keys & set(raw.keys()):
                return raw
            resp = str(raw.get("response") or raw.get("content") or "")
            start = resp.find("{")
            end = resp.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(resp[start:end])
                if isinstance(parsed, dict):
                    return parsed
    except Exception:
        pass
    return {}


# ---------------------------------------------------------------------------
# Profile builder
# ---------------------------------------------------------------------------

_profile_cache: dict[str, dict] = {}
_MAX_CACHE = 500


def get_profile(conn, cfg: dict, item_id: str, refresh: bool = False) -> dict | None:
    """Get or generate an EntityProfile for a DB item. Cached in memory + DB."""
    if not refresh and item_id in _profile_cache:
        return _profile_cache[item_id]

    if not refresh:
        cached = db.get_entity_profile(conn, item_id)
        if cached is not None:
            _profile_cache[item_id] = cached
            return cached

    rows = db.rows(conn, "SELECT * FROM items WHERE id=? LIMIT 1", (item_id,))
    if not rows:
        return None

    profile = _build_profile(cfg, rows[0])
    db.set_entity_profile(conn, item_id, json.dumps(profile))

    if len(_profile_cache) >= _MAX_CACHE:
        _profile_cache.pop(next(iter(_profile_cache)))
    _profile_cache[item_id] = profile
    return profile


def get_profiles(conn, cfg: dict, item_ids: list[str]) -> list[dict]:
    return [p for iid in item_ids if (p := get_profile(conn, cfg, iid)) is not None]


def invalidate(item_id: str) -> None:
    _profile_cache.pop(item_id, None)


def _build_profile(cfg: dict, item: dict) -> dict:
    t0 = time.time()
    item_id = item["id"]
    path = item.get("path") or ""
    name = Path(path).name

    role = detect_role(item)
    heuristic = heuristic_extract(item)
    llm = _llm_extract(cfg, item, role)

    def _merge(hkey: str, lkey: str | None = None) -> list[str]:
        lk = lkey or hkey
        combined = list(dict.fromkeys(
            str(v) for v in (llm.get(lk) or []) + (heuristic.get(hkey) or []) if v
        ))
        return combined[:8]

    people = _merge("people")
    organizations = _merge("organizations")
    locations = _merge("locations")
    projects = _merge("projects")
    topics = _merge("topics")
    dates = _merge("dates", "dates_mentioned") or heuristic.get("dates") or []
    skills = [str(s) for s in (llm.get("key_skills") or [])[:6]]

    direct_claims = [str(c) for c in (llm.get("direct_claims") or [])[:5]]
    inferred_claims = [str(c) for c in (llm.get("inferred_claims") or [])[:5]]
    open_questions = [str(q) for q in (llm.get("open_questions") or [])[:3]]
    summary = str(llm.get("summary") or "").strip()
    if not summary:
        size_kb = int(item.get("size", 0) / 1024)
        top_topics = ", ".join(topics[:3]) if topics else "unknown topics"
        summary = f"{role.replace('_', ' ').title()} ({size_kb} KB) covering {top_topics}."

    risks = detect_risks(item, heuristic, role)
    signals = detect_signals(item, heuristic, role)

    text_len = len(item.get("text") or "")
    role_known = role != "file"
    confidence = round(min(0.95, 0.25 + min(text_len / 12000, 0.5) + (0.15 if role_known else 0) + (0.05 if llm else 0)), 3)

    return {
        "entity_id": item_id,
        "entity_type": "asset",
        "asset_type": role,
        "name": name,
        "path": path,
        "path_hash": hashlib.sha256(path.encode()).hexdigest()[:16],
        "created_at": float(item.get("mtime", 0)),
        "modified_at": float(item.get("mtime", 0)),
        "ingested_at": time.time(),
        "summary": summary,
        "role": role,
        "extracted_people": people,
        "extracted_organizations": organizations,
        "extracted_locations": locations,
        "extracted_topics": topics,
        "extracted_projects": projects,
        "extracted_dates": dates,
        "extracted_emails": heuristic.get("emails") or [],
        "extracted_urls": heuristic.get("urls") or [],
        "extracted_skills": skills,
        "direct_claims": direct_claims,
        "inferred_claims": inferred_claims,
        "identity_signals": signals,
        "risks": risks,
        "open_questions": open_questions,
        "confidence": confidence,
        "evidence_chunk_ids": [item_id],
        "llm_enriched": bool(llm),
        "generated_ms": int((time.time() - t0) * 1000),
    }


# ---------------------------------------------------------------------------
# Iris formatting helpers
# ---------------------------------------------------------------------------

_SEV_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def format_for_iris(profile: dict) -> str:
    """Render an EntityProfile as a concise text block for Iris prompt injection."""
    p = profile
    lines: list[str] = [
        f"**{p['name']}** | role: {p['role']} | confidence: {p['confidence']:.0%}",
        f"Summary: {p['summary']}",
    ]
    if p.get("extracted_people"):
        lines.append(f"People: {', '.join(p['extracted_people'][:5])}")
    if p.get("extracted_organizations"):
        lines.append(f"Organizations: {', '.join(p['extracted_organizations'][:4])}")
    if p.get("extracted_locations"):
        lines.append(f"Locations: {', '.join(p['extracted_locations'][:4])}")
    if p.get("extracted_skills"):
        lines.append(f"Skills: {', '.join(p['extracted_skills'][:5])}")
    if p.get("extracted_topics"):
        lines.append(f"Topics: {', '.join(p['extracted_topics'][:6])}")
    if p.get("extracted_projects"):
        lines.append(f"Projects: {', '.join(p['extracted_projects'][:4])}")
    if p.get("extracted_dates"):
        lines.append(f"Dates: {', '.join(p['extracted_dates'][:4])}")
    if p.get("extracted_emails"):
        lines.append(f"Contacts: {', '.join(p['extracted_emails'][:3])}")
    if p.get("direct_claims"):
        claims = "\n".join(f"  • {c}" for c in p["direct_claims"][:3])
        lines.append(f"Direct claims:\n{claims}")
    if p.get("inferred_claims"):
        claims = "\n".join(f"  ~ {c}" for c in p["inferred_claims"][:3])
        lines.append(f"Inferred claims (weak):\n{claims}")
    if p.get("identity_signals"):
        sigs = "; ".join(s["description"] for s in p["identity_signals"][:3])
        lines.append(f"Signals: {sigs}")
    if p.get("risks"):
        sorted_risks = sorted(p["risks"], key=lambda r: -_SEV_ORDER.get(r.get("severity", "low"), 0))
        rlines = [f"  ⚠ [{r['severity']}] {r['description']}" for r in sorted_risks[:3]]
        lines.append("Risks:\n" + "\n".join(rlines))
    if p.get("open_questions"):
        lines.append(f"Open questions: {'; '.join(p['open_questions'][:2])}")
    return "\n".join(lines)


def format_claim_card(profile: dict) -> str:
    """Compact claim card format for multi-entity council mode."""
    p = profile
    risks_str = "; ".join(
        f"[{r['severity']}] {r['description']}"
        for r in sorted(p.get("risks", []), key=lambda r: -_SEV_ORDER.get(r.get("severity", "low"), 0))[:2]
    ) or "none detected"
    sigs_str = "; ".join(
        s["description"] for s in p.get("identity_signals", [])[:2]
    ) or "none detected"
    claims_str = "\n".join(f"    • {c}" for c in p.get("direct_claims", [])[:3]) or "    (no direct claims extracted)"
    inferred_str = "\n".join(f"    ~ {c}" for c in p.get("inferred_claims", [])[:2]) or "    (none)"

    return (
        f"[ENTITY] {p['name']} (role={p['role']}, confidence={p['confidence']:.0%})\n"
        f"  Summary: {p['summary']}\n"
        f"  Signals: {sigs_str}\n"
        f"  Top risks: {risks_str}\n"
        f"  Direct claims:\n{claims_str}\n"
        f"  Inferred:\n{inferred_str}"
    )


# ---------------------------------------------------------------------------
# Audience profiles
# ---------------------------------------------------------------------------

AUDIENCE_PROFILES: dict[str, dict] = {
    "recruiter": {
        "audience_id": "recruiter",
        "name": "Recruiter / Hiring Manager",
        "cares_about": ["skills", "employment history", "tenure", "project scope", "measurable impact"],
        "penalizes": ["employment gaps", "inconsistency", "vague contributions", "credential inflation"],
        "interpretation_style": "professional screening with keyword and pattern matching",
        "default_questions": ["What is this person's strongest signal?", "Are there gaps or red flags?"],
        "risk_sensitivity": "medium",
        "likely_false_positives": ["career transitions misread as instability"],
    },
    "investor": {
        "audience_id": "investor",
        "name": "Investor / VC",
        "cares_about": ["execution history", "technical depth", "market insight", "network quality", "shipping track record"],
        "penalizes": ["vaporware", "no shipping evidence", "credential inflation", "weak network"],
        "interpretation_style": "thesis validation — looking for founder-market fit and execution evidence",
        "default_questions": ["Can this person build?", "Do they understand the market?", "Have they shipped?"],
        "risk_sensitivity": "low",
        "likely_false_positives": ["research phase misread as inaction"],
    },
    "collaborator": {
        "audience_id": "collaborator",
        "name": "Collaborator / Cofounder",
        "cares_about": ["execution style", "complementary skills", "trust signals", "communication", "reliability"],
        "penalizes": ["chaos signals", "inconsistent output", "poor communication traces", "unilateral patterns"],
        "interpretation_style": "partnership fit assessment — looking for complementary skills and reliable collaboration patterns",
        "default_questions": ["Can I work with this person?", "Do their skills complement mine?", "Are they reliable?"],
        "risk_sensitivity": "medium",
        "likely_false_positives": ["solo work misread as poor team player"],
    },
    "creator": {
        "audience_id": "creator",
        "name": "Creator / Public Figure",
        "cares_about": ["brand clarity", "audience trust", "content consistency", "platform presence", "controversy surface"],
        "penalizes": ["brand confusion", "audience alienation", "inconsistent messaging", "unaddressed controversy"],
        "interpretation_style": "brand and audience trust assessment — evaluating public persona coherence",
        "default_questions": ["Is the brand clear?", "Are there reputational risks?", "Is the audience engaged?"],
        "risk_sensitivity": "high",
        "likely_false_positives": ["edgy content misread as reputational risk"],
    },
    "privacy": {
        "audience_id": "privacy",
        "name": "Privacy Auditor / Data Broker",
        "cares_about": ["exposed credentials", "identity anchors", "location signals", "behavioral patterns", "tracking surface", "metadata trails"],
        "penalizes": ["nothing — every exposed signal is a finding"],
        "interpretation_style": "maximum exposure assessment — treats every signal as a potential privacy leak",
        "default_questions": ["What is exposed?", "What can be linked?", "What tracking surfaces exist?"],
        "risk_sensitivity": "high",
        "likely_false_positives": ["routine metadata misread as fingerprinting risk"],
    },
    "platform": {
        "audience_id": "platform",
        "name": "Ad Platform / Algorithm",
        "cares_about": ["interest categories", "consumer intent", "demographic proxies", "behavioral signals", "engagement patterns"],
        "penalizes": ["ad blindness", "low engagement", "ad-blocker usage"],
        "interpretation_style": "algorithmic profiling — categorizing users for targeting and recommendations",
        "default_questions": ["What interests can be inferred?", "What is the consumer profile?", "What segments apply?"],
        "risk_sensitivity": "low",
        "likely_false_positives": ["research queries misread as consumer interest"],
    },
    "search": {
        "audience_id": "search",
        "name": "Search Engine / Web Crawler",
        "cares_about": ["search appearance", "result freshness", "relevance signals", "content quality", "structured data"],
        "penalizes": ["stale content", "thin content", "missing metadata", "duplicate signals"],
        "interpretation_style": "information retrieval — indexing and ranking public content for query matching",
        "default_questions": ["What appears in search results?", "Is the information current?", "Are there name collisions?"],
        "risk_sensitivity": "medium",
        "likely_false_positives": ["stale results misread as current profile", "name collisions between different people"],
    },
    "institution": {
        "audience_id": "institution",
        "name": "Institution / Gatekeeper",
        "cares_about": ["credential verification", "stability indicators", "formal records", "compliance surface", "background consistency"],
        "penalizes": ["unverifiable claims", "timeline gaps", "informal experience", "international complexity"],
        "interpretation_style": "formal due diligence — verifying credentials and assessing institutional fit",
        "default_questions": ["Can credentials be verified?", "Are there gaps or inconsistencies?", "Does the record support the application?"],
        "risk_sensitivity": "medium",
        "likely_false_positives": ["creative careers misread as lack of rigour"],
    },
    "stranger": {
        "audience_id": "stranger",
        "name": "Stranger / Outside Observer",
        "cares_about": ["first impression", "public fragments", "search appearance", "professional baseline", "legibility"],
        "penalizes": ["incoherent public presence", "outdated information", "conflicting signals"],
        "interpretation_style": "snap judgment from limited public fragments — rapid pattern matching with no deep context",
        "default_questions": ["What is immediately visible?", "What first impression does this create?", "What seems contradictory?"],
        "risk_sensitivity": "high",
        "likely_false_positives": ["outdated search results misread as current", "name twins misattributed"],
    },
}


def list_audiences() -> list[dict]:
    return [{"id": v["audience_id"], "name": v["name"]} for v in AUDIENCE_PROFILES.values()]


def get_audience(audience_id: str) -> dict | None:
    return AUDIENCE_PROFILES.get(audience_id)


def format_audience_for_iris(audience: dict) -> str:
    a = audience
    cares = ", ".join(a.get("cares_about", [])[:5])
    penalises = ", ".join(a.get("penalizes", [])[:4])
    fps = ", ".join(a.get("likely_false_positives", [])[:2]) or "unknown"
    return (
        f"**Audience: {a['name']}**\n"
        f"Interpretation style: {a['interpretation_style']}\n"
        f"Cares about: {cares}\n"
        f"Penalises: {penalises}\n"
        f"Likely false positives: {fps}\n"
        f"Default questions: {'; '.join(a.get('default_questions', []))}"
    )
