"""
Iris — Optic's intelligent file agent, powered by Neurontology.

Neurontology: a proprietary semantic graph engine that models every file as
a node in 4-dimensional neural embedding space. Files cluster by meaning,
not by filesystem hierarchy.

Architecture: context-first streaming.
  1. Pre-gather relevant DB context synchronously (milliseconds).
  2. Inject into system prompt alongside mode instructions.
  3. Stream the LLM response token-by-token to the browser.
  No blocking tool-call round-trips — every query responds in < 2 s to first token.
"""
from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Generator

from . import cfg as cfgmod
from . import db, ollama


# ─── Neurontology System Prompt ──────────────────────────────────────────────

BASE_SYSTEM = """You are Iris, an intelligent assistant inside Optic — a personal file intelligence app.

You have access to a semantic map of the user's entire local file system. Files are \
grouped by meaning into clusters (called workstreams), not just by folder. You can see \
what topics, themes, and file types dominate each cluster.

Corpus snapshot: {corpus}

Rules:
- Be direct and specific. No filler openers ("Certainly!", "Great question!", "Of course!").
- Never reveal technical internals (embedding dimensions, PCA, vector counts, model names).
- Write in plain, clear prose first. Use bullet lists only when listing 3+ items.
- Use **bold** for the single most important insight per paragraph — not for every noun.
- Keep responses concise: 2–4 paragraphs for general questions, shorter for specific ones.
- Cite real file names or workstream names when they support a claim.
- Be honest about what you cannot infer."""

MODE_ADDENDUM = {
    "report": """
You are in Report mode. Analyse the user's file collection and surface what matters.
Write 2–4 tight paragraphs covering: what the collection reveals about their work and \
interests, what stands out or is surprising, and one concrete recommendation.
Do NOT produce a numbered list of statistics. Do NOT repeat file counts verbatim. \
End with a one-line **Signal Score: NN / 100** rating of how well-organised the corpus is.
""",
    "archive": """
## Mode: ARCHIVE
Help organize, rename, and structure files.
Format every rename/move suggestion as:
```
CURRENT  ~/Downloads/IMG_4521.jpg
→ TARGET  ~/Pictures/2026-05/dashboard-screenshot.jpg
   WHY    Date-prefixed, descriptive, categorized
```
Never execute operations — only propose them.
""",
    "entity": """
## Mode: ENTITY — Single Evidence Entity Interrogation

You are interrogating a single local file as a structured evidence entity.
The entity profile and raw text are provided as context.

VOICE RULES:
- Say "this file suggests" or "this asset implies" — never "you are"
- Identity inference is probabilistic: say "this weakly implies" for uncertain claims
- Separate DIRECT EVIDENCE (from quoted text / metadata) from INFERENCE
- If the evidence doesn't support the question, say so explicitly
- Never invent facts not grounded in the evidence

ANSWER STRUCTURE:
1. **Direct Answer** — what the evidence actually supports
2. **Strongest Signals** — top 2-3 signals this entity emits
3. **Weak Signals** — what this entity only hints at
4. **Risks** — what exposure this file creates
5. **Confidence** — your overall confidence (0–100%) and why
6. **Evidence References** — cite filename + text excerpt for each claim
7. **What's Missing** — what would strengthen or change the inference
""",
    "compare": """
## Mode: COMPARE — Multi-Entity Council

Multiple evidence entities have contributed claim cards. You must weigh and
synthesise them into a grounded answer.

COUNCIL RULES:
- State which entity each claim comes from
- Weight entities by: relevance to question, evidence confidence, recency
- Note where entities agree vs contradict each other
- Penalise weak evidence, unclear source, irrelevant jurisdiction
- Never average entities blindly — domain relevance matters
  (resume dominates career questions; bank statement dominates financial questions)

ANSWER STRUCTURE:
1. **Council Answer** — synthesised conclusion, grounded in evidence
2. **Dominant Entities** — which mattered most and why (with weights)
3. **Points of Agreement** — where multiple entities reinforce the same claim
4. **Contradictions** — where entities conflict (flag severity)
5. **Audience Implications** — what different readers would conclude
6. **Confidence** — overall confidence and evidence gaps
7. **Evidence References** — entity name + excerpt for each key claim
""",
    "audience": """
## Mode: AUDIENCE LENS — Modelled Perception Analysis

Apply the specified audience lens to the provided evidence entities.
This is NOT truth — it is modelled perception: what would this audience
actually see, think, and decide based on this evidence?

AUDIENCE RULES:
- Describe what this audience notices FIRST (attention priorities)
- What do they REWARD? (positive signals from their perspective)
- What do they PENALISE? (negative signals or red flags)
- What might they MISUNDERSTAND? (false positives / misreadings)
- What REPAIR ACTIONS would improve this person's signal for this audience?
- State your CONFIDENCE in the model (audiences vary individually)

Be specific about which file/entity drives each observation.
Never claim this is objective truth — always frame as modelled perception.
""",
    "contradiction": """
## Mode: CONTRADICTION SCAN

Scan the selected evidence entities for internal and cross-entity contradictions.

CONTRADICTION TYPES TO CHECK:
- Timeline conflicts (claimed dates that don't add up)
- Affiliation conflicts (different employers or roles in the same period)
- Skill level conflicts (claims expertise but evidence shows beginner work)
- Location conflicts (different places at the same time)
- Content conflicts (one file's claims undermine another's)
- Tone/register conflicts (formal credential vs informal behaviour)

FORMAT each finding as:
`[ENTITY A] ↔ [ENTITY B or INTERNAL] — [what conflicts] — severity: low/med/high — [which to trust and why]`

If no contradictions are found, say so explicitly and explain why the evidence is consistent.
End with a **Coherence Score** (0–100) where 100 = fully consistent.
""",
    "audit": """
## Mode: IDENTITY AUDIT — Structured Full Report

Generate a complete identity audit from the selected evidence.
Every claim must cite a source entity or be marked as unknown/inferred.

Required sections in this exact order:

### Executive Read
4–6 sentences. What does this evidence, taken together, cause others to infer?
Write as if briefing a smart stranger. State overall confidence.

### Dominant Signals
Top 5 signals. Each as: `SIGNAL — source entity — confidence%`

### Strongest Evidence
Top 3 most solid findings. Each must cite filename + excerpt.

### Weakest Evidence
Claims that are possible but poorly supported. Flag confidence < 40%.

### Contradictions
Conflicts across entities, or "None found — evidence is coherent."

### Audience Interpretations
**Recruiter:** one paragraph — what they would notice, reward, penalise.
**Investor:** one paragraph — same lens.
**Adversarial reader:** one paragraph — what they could exploit.

### Risk Map
Ranked list: `[severity] risk — source entity — mitigation action`

### Repair Map
Numbered action list, highest-ROI first:
`N. [~Xmin] specific action → what it improves`

### Follow-up Questions
3–5 questions this evidence raises but cannot answer.
""",
    "mirror": """
## Mode: MIRROR — Adversarial Footprint Analysis

You are acting as a red-team analyst. The context below contains the raw output of a \
5-layer adversarial analysis of the user's local file corpus. \
Your job: synthesize it into a structured threat intelligence brief.

Write EXACTLY this structure (all sections required):

### ⚡ EXECUTIVE SUMMARY
One tight paragraph (4–6 sentences). Write as if briefing an adversary: what they know, \
what they can infer, what they can do with it. Include confidence level (low/medium/high). \
Specific, not generic. No filler.

### 👤 INFERRED PROFILE
List each inference as `INFERENCE — confidence% — evidence`. Cover: identity anchors \
(real name / email / handles), location signals, employer/client signals, technical level, \
project domain, work schedule. Only list what the evidence actually supports.

### 🔓 TOP EXPOSED ASSETS
Numbered list, ranked by harm potential. Each entry:
`N. [CATEGORY] filename-or-pattern — Risk: why this matters to an adversary`
Categories: CREDENTIAL, IDENTITY, IP, BEHAVIORAL, COMPETITIVE. Max 10 items.

### 🗺️ ATTACK PATHS
Five specific attack scenarios. Format each as:
`**Attack**: [name]`
`**Who benefits**: [actor type]`
`**How**: [2-sentence mechanical description]`
`**Requires**: [what the attacker needs beyond what's already exposed]`

### 📊 FOOTPRINT RISK SCORE
Reproduce the score from the context: `**Overall Risk: NN / 100**`
Then one line each for the 5 sub-scores: Credential / Identity / IP / Behavioral / Competitive.

### 🔧 1-HOUR FIX PLAN
Numbered action list, highest-ROI first. Each item:
`N. [TIME ~Xmin] specific action → what it closes`
Realistic. Specific file names or patterns where known. No platitudes.

Tone: direct, analytical, zero hedging. You are not trying to scare — you are trying to \
give the user the exact same picture an adversary would have. Be honest about gaps in the data.
""",
    "retune": """
## Mode: SIGNAL RETUNE
Diagnose and fix noise. Output a numbered action list:
```
N. [NOISE TYPE] problem
   → Fix: specific action
   → Impact: X MB / Y files
```
Noise types: duplicates, stale downloads, naming entropy, orphaned files, bloat.
""",
}

_TERM_RE = re.compile(r"[a-z0-9][a-z0-9._/-]{2,}")
_STOP_TERMS = {
    "with", "from", "that", "this", "what", "where", "when", "which",
    "about", "into", "just", "have", "your", "mine", "show", "give",
    "find", "scan", "file", "files", "mode", "run", "then", "than",
}


# ─── Context Gatherers ────────────────────────────────────────────────────────

def _corpus_stats(conn, scope: set[str] | None = None) -> dict:
    rows = _scope_rows(conn,
        "SELECT id, kind, size, mtime, ext FROM items", (), scope)
    week_ago = time.time() - 7 * 86400
    files = [r for r in rows if r.get("kind") == "file"]
    dirs = [r for r in rows if r.get("kind") == "dir"]
    ext_map: dict[str, dict] = {}
    for row in files:
        ext = str(row.get("ext") or "")
        if not ext:
            continue
        rec = ext_map.setdefault(ext, {"ext": ext, "count": 0, "size_bytes": 0})
        rec["count"] += 1
        rec["size_bytes"] += int(row.get("size") or 0)
    top_ext = sorted(ext_map.values(), key=lambda x: -x["count"])[:12]
    return {
        "total_files": len(files),
        "total_size_bytes": sum(int(r.get("size") or 0) for r in files),
        "total_dirs": len(dirs),
        "modified_last_week": sum(
            1 for r in files if float(r.get("mtime") or 0) > week_ago),
        "top_extensions": top_ext,
    }


def _list_largest(conn, limit: int = 12,
                  scope: set[str] | None = None) -> list[dict]:
    rows = _scope_rows(conn,
        "SELECT id, path, size FROM items WHERE kind='file' AND size > 0",
        (), scope)
    rows.sort(key=lambda x: -int(x.get("size") or 0))
    return [{"name": Path(r["path"]).name, "size_bytes": r["size"]}
            for r in rows[:limit]]


def _find_duplicates_summary(conn, limit: int = 10,
                             scope: set[str] | None = None) -> dict:
    rows = _scope_rows(conn, "SELECT id, path, size FROM items WHERE kind='file'",
                       (), scope)
    by_name: dict = defaultdict(list)
    for r in rows:
        name = Path(r["path"]).name.lower()
        if len(name) > 3:
            by_name[name].append(r["size"])
    groups = [
        {"name": name, "count": len(sizes), "wasted": sum(sizes) - min(sizes)}
        for name, sizes in by_name.items() if len(sizes) > 1
    ]
    groups.sort(key=lambda g: -g["wasted"])
    total_wasted = sum(g["wasted"] for g in groups)
    return {
        "group_count": len(groups),
        "total_wasted_bytes": total_wasted,
        "top_groups": groups[:limit],
    }


def _stale_downloads(conn, older_than_days: int = 30, limit: int = 15,
                     scope: set[str] | None = None) -> list[dict]:
    cutoff = time.time() - older_than_days * 86400
    rows = _scope_rows(conn,
        "SELECT id, path, size, mtime FROM items "
        "WHERE kind='file' AND mtime < ? AND size >= 102400 "
        "AND (path LIKE '%/Downloads/%' OR path LIKE '%/Desktop/%')",
        (cutoff,), scope)
    rows.sort(key=lambda x: float(x.get("mtime") or 0))
    now = time.time()
    return [
        {"name": Path(r["path"]).name, "size_bytes": r["size"],
         "age_days": int((now - r["mtime"]) / 86400)}
        for r in rows[:limit]
    ]


def _get_workstreams(conn, limit: int = 12,
                     scope: set[str] | None = None) -> list[dict]:
    rows = _scope_rows(conn,
        "SELECT id, cluster, path, size FROM items "
        "WHERE cluster != '' AND kind='file'",
        (), scope)
    grp: dict[str, dict] = {}
    for row in rows:
        cid = str(row.get("cluster") or "")
        if not cid:
            continue
        cur = grp.setdefault(cid, {"cluster": cid, "cnt": 0, "sz": 0, "rows": []})
        cur["cnt"] += 1
        cur["sz"] += int(row.get("size") or 0)
        cur["rows"].append(row)
    rows2 = sorted(grp.values(), key=lambda x: -x["cnt"])[:limit]
    result = []
    for r in rows2:
        names = [Path(s["path"]).name for s in
                 sorted(r["rows"], key=lambda x: -int(x.get("size") or 0))[:3]]
        result.append({
            "id": r["cluster"][:16],
            "files": r["cnt"],
            "size_bytes": r["sz"],
            "samples": names,
        })
    return result


def _read_file_text(conn, path: str) -> str:
    rows = db.rows(conn, "SELECT text FROM items WHERE path=? LIMIT 1", (path,))
    if rows:
        return (rows[0]["text"] or "").strip()[:3000]
    return ""


def _recent_files(conn, days: int = 7, limit: int = 15,
                  scope: set[str] | None = None) -> list[dict]:
    cutoff = time.time() - days * 86400
    rows = _scope_rows(conn,
        "SELECT id, path, size, mtime FROM items "
        "WHERE kind='file' AND mtime > ?",
        (cutoff,), scope)
    rows.sort(key=lambda x: -float(x.get("mtime") or 0))
    now = time.time()
    return [
        {"name": Path(r["path"]).name, "size_bytes": r["size"],
         "hours_ago": int((now - r["mtime"]) / 3600)}
        for r in rows[:limit]
    ]


def _scope_rows(conn, sql: str, args: tuple,
                scope: set[str] | None) -> list[dict]:
    rows = db.rows(conn, sql, args)
    if not scope:
        return rows
    return [r for r in rows if str(r.get("id") or "") in scope]


def _q_terms(q: str, cap: int = 8) -> list[str]:
    out: list[str] = []
    for raw in _TERM_RE.findall(q.lower()):
        tok = raw.strip("._/-")
        if len(tok) < 3 or tok in _STOP_TERMS:
            continue
        if tok in out:
            continue
        out.append(tok)
        if len(out) >= cap:
            break
    return out


def _hit_score(row: dict, terms: list[str]) -> int:
    path = str(row.get("path") or "").lower()
    text = str(row.get("text") or "").lower()
    score = 0
    for tok in terms:
        if tok in path:
            score += 5
        if tok in text:
            score += 2
    return score


def _hit_excerpt(text: str, terms: list[str], cap: int = 180) -> str:
    raw = " ".join(str(text or "").split())
    if not raw:
        return ""
    low = raw.lower()
    pos = -1
    for tok in terms:
        idx = low.find(tok)
        if idx >= 0 and (pos < 0 or idx < pos):
            pos = idx
    if pos < 0:
        return raw[:cap]
    start = max(0, pos - 44)
    end = min(len(raw), pos + cap)
    return raw[start:end]


def _evidence_sql(terms: list[str], limit: int) -> tuple[str, tuple]:
    picks = terms[:6]
    if not picks:
        return "", ()
    like = []
    args: list[object] = []
    for tok in picks:
        pat = f"%{tok}%"
        like.append("(lower(path) LIKE ? OR lower(text) LIKE ?)")
        args.extend([pat, pat])
    sql = (
        "SELECT id, path, text, mtime, size FROM items "
        "WHERE kind='file' AND text != '' AND (" + " OR ".join(like) + ") "
        "ORDER BY mtime DESC LIMIT ?"
    )
    args.append(max(40, limit * 22))
    return sql, tuple(args)


def _query_hits(conn, q: str, scope: set[str] | None,
                limit: int = 6) -> list[dict]:
    terms = _q_terms(q)
    sql, args = _evidence_sql(terms, limit)
    if not sql:
        return []
    rows = _scope_rows(conn, sql, args, scope)
    scored = []
    for row in rows:
        score = _hit_score(row, terms)
        if score <= 0:
            continue
        scored.append((score, row))
    scored.sort(key=lambda x: (
        -x[0],
        -float(x[1].get("mtime") or 0),
        -int(x[1].get("size") or 0),
    ))
    out = []
    for score, row in scored[:limit]:
        path = str(row.get("path") or "")
        out.append({
            "id": str(row.get("id") or ""),
            "path": path,
            "name": Path(path).name,
            "score": score,
            "text": _hit_excerpt(str(row.get("text") or ""), terms),
        })
    return out


def _query_context(conn, q: str, scope: set[str] | None,
                   limit: int = 6) -> str:
    hits = _query_hits(conn, q, scope=scope, limit=limit)
    if not hits:
        return ""
    rows = []
    for row in hits:
        rows.append(
            f"  - {row['name']} ({row['score']}): {row['text']}"
        )
    return "Query-matched evidence:\n" + "\n".join(rows)


def _run_scope_ids(cfg: dict, run: str) -> set[str] | None:
    if not cfg or not run:
        return None
    path = cfgmod.state_dir(cfg, "graphs") / f"{run}.json"
    if not path.exists():
        return None
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    nodes = graph.get("nodes", [])
    out = {str(n.get("id") or "") for n in nodes}
    out.discard("")
    return out or None


# ─── Smart context routing ────────────────────────────────────────────────────

# ─── Identity-mode context gatherers ─────────────────────────────────────────

def _entity_context(conn, cfg: dict, selected_ids: list[str]) -> tuple[str, list[dict]]:
    """Gather entity profiles for single-entity or comparison interrogation."""
    from . import identity as id_mod
    if not selected_ids:
        return "No entity selected. Select a file in the graph, then ask.", []

    ctx_parts: list[str] = []
    tools_used: list[dict] = []

    for item_id in selected_ids[:3]:
        t0 = time.time()
        try:
            profile = id_mod.get_profile(conn, cfg, item_id)
        except Exception as exc:
            profile = None
        elapsed = int((time.time() - t0) * 1000)

        if not profile:
            ctx_parts.append(f"Entity {item_id}: profile unavailable.")
            continue

        tools_used.append({
            "name": "entity_profile",
            "preview": f"profiling {profile['name']} ({profile['role']})",
            "ms": elapsed,
        })
        ctx_parts.append(f"## Entity: {profile['name']}")
        ctx_parts.append(id_mod.format_for_iris(profile))

        # Include raw text excerpt for deeper evidence grounding
        rows = db.rows(conn, "SELECT text FROM items WHERE id=? LIMIT 1", (item_id,))
        if rows:
            excerpt = (rows[0]["text"] or "")[:2000].strip()
            if excerpt:
                ctx_parts.append(f"\n### Raw text excerpt:\n```\n{excerpt}\n```")

    return "\n\n".join(ctx_parts), tools_used


def _compare_context(conn, cfg: dict, selected_ids: list[str]) -> tuple[str, list[dict]]:
    """Gather claim cards for multi-entity council comparison."""
    from . import identity as id_mod
    if len(selected_ids) < 2:
        return "Select 2 or more files (Ctrl+click in the graph) to compare.", []

    ctx_parts: list[str] = [f"## Council of {min(len(selected_ids), 5)} Evidence Entities\n"]
    tools_used: list[dict] = []

    for item_id in selected_ids[:5]:
        t0 = time.time()
        try:
            profile = id_mod.get_profile(conn, cfg, item_id)
        except Exception:
            profile = None
        elapsed = int((time.time() - t0) * 1000)
        if not profile:
            continue
        tools_used.append({
            "name": "claim_card",
            "preview": f"{profile['name']} → {len(profile.get('direct_claims', []))} claims",
            "ms": elapsed,
        })
        ctx_parts.append(id_mod.format_claim_card(profile))

    return "\n\n".join(ctx_parts), tools_used


def _audience_context(conn, cfg: dict, selected_ids: list[str], audience_id: str) -> tuple[str, list[dict]]:
    """Apply an audience lens to entity profiles."""
    from . import identity as id_mod
    audience = id_mod.get_audience(audience_id) or id_mod.get_audience("recruiter")
    ctx_parts: list[str] = [
        "## Audience Lens\n",
        id_mod.format_audience_for_iris(audience),
        "\n## Evidence Entities Under Review\n",
    ]
    tools_used: list[dict] = []

    ids_to_use = selected_ids[:3] if selected_ids else []
    if not ids_to_use:
        # Fall back to most-recently-modified files if nothing selected
        recent = db.rows(conn,
            "SELECT id FROM items WHERE kind='file' AND text != '' "
            "ORDER BY mtime DESC LIMIT 3")
        ids_to_use = [r["id"] for r in recent]

    for item_id in ids_to_use:
        t0 = time.time()
        try:
            profile = id_mod.get_profile(conn, cfg, item_id)
        except Exception:
            profile = None
        elapsed = int((time.time() - t0) * 1000)
        if not profile:
            continue
        tools_used.append({
            "name": "audience_lens",
            "preview": f"{audience['name']} ← {profile['name']}",
            "ms": elapsed,
        })
        ctx_parts.append(id_mod.format_for_iris(profile))

    return "\n\n".join(ctx_parts), tools_used


def _contradiction_context(conn, cfg: dict, selected_ids: list[str]) -> tuple[str, list[dict]]:
    """Gather entity profiles for contradiction scanning."""
    from . import identity as id_mod
    ids_to_use = selected_ids[:5] if selected_ids else []
    if not ids_to_use:
        recent = db.rows(conn,
            "SELECT id FROM items WHERE kind='file' AND text != '' "
            "ORDER BY mtime DESC LIMIT 4")
        ids_to_use = [r["id"] for r in recent]

    if len(ids_to_use) < 2:
        return "Need at least 2 files to scan for contradictions. Select more files.", []

    ctx_parts: list[str] = [f"## Contradiction Scan — {len(ids_to_use)} entities\n"]
    tools_used: list[dict] = []

    for item_id in ids_to_use:
        t0 = time.time()
        try:
            profile = id_mod.get_profile(conn, cfg, item_id)
        except Exception:
            profile = None
        elapsed = int((time.time() - t0) * 1000)
        if not profile:
            continue
        tools_used.append({
            "name": "contradiction_scan",
            "preview": f"scanning {profile['name']}",
            "ms": elapsed,
        })
        ctx_parts.append(id_mod.format_claim_card(profile))

    return "\n\n".join(ctx_parts), tools_used


def _audit_context(conn, cfg: dict, selected_ids: list[str]) -> tuple[str, list[dict]]:
    """Compile full entity profiles for identity audit."""
    from . import identity as id_mod
    ids_to_use = selected_ids[:6] if selected_ids else []
    if not ids_to_use:
        recent = db.rows(conn,
            "SELECT id FROM items WHERE kind='file' AND text != '' "
            "ORDER BY mtime DESC LIMIT 5")
        ids_to_use = [r["id"] for r in recent]

    ctx_parts: list[str] = [f"## Identity Audit — {len(ids_to_use)} evidence entit{'y' if len(ids_to_use)==1 else 'ies'}\n"]
    tools_used: list[dict] = []

    for item_id in ids_to_use:
        t0 = time.time()
        try:
            profile = id_mod.get_profile(conn, cfg, item_id)
        except Exception:
            profile = None
        elapsed = int((time.time() - t0) * 1000)
        if not profile:
            continue
        tools_used.append({
            "name": "audit_entity",
            "preview": f"{profile['name']} | {len(profile.get('risks',[]))} risks",
            "ms": elapsed,
        })
        ctx_parts.append(f"### {profile['name']}")
        ctx_parts.append(id_mod.format_for_iris(profile))

    # Append audience scaffolding for the audit
    ctx_parts.append(
        "\n### Audience reference profiles\n"
        + "\n---\n".join(
            id_mod.format_audience_for_iris(a)
            for a in [
                id_mod.get_audience("recruiter"),
                id_mod.get_audience("investor"),
                id_mod.get_audience("adversarial"),
            ]
            if a
        )
    )

    return "\n\n".join(ctx_parts), tools_used


# ─── Smart context routing ────────────────────────────────────────────────────

def _gather_context(conn, q: str, mode: str, cfg: dict | None = None,
                    run: str = "",
                    selected_ids: list[str] | None = None,
                    audience_id: str | None = None) -> tuple[str, list[dict]]:
    """
    Decide what DB context to gather based on the query and mode.
    Returns (context_text, tool_events) where tool_events are shown in the UI.
    """
    q_lower = q.lower()
    ctx_parts: list[str] = []
    tools_used: list[dict] = []
    _cfg = cfg or {}
    scope = _run_scope_ids(_cfg, run)

    # ── Identity modes (bypass standard corpus routing) ───────────────────
    if mode == "entity":
        return _entity_context(conn, _cfg, selected_ids or [])

    if mode == "compare":
        return _compare_context(conn, _cfg, selected_ids or [])

    if mode == "audience":
        return _audience_context(conn, _cfg, selected_ids or [], audience_id or "recruiter")

    if mode == "contradiction":
        return _contradiction_context(conn, _cfg, selected_ids or [])

    if mode == "audit":
        return _audit_context(conn, _cfg, selected_ids or [])

    # ── Mirror mode: full adversarial analysis (bypasses standard routing) ──
    if mode == "mirror":
        from . import mirror as mirror_mod
        t0 = time.time()
        try:
            mirror_data = mirror_mod.full_analysis(conn)
        except Exception as exc:
            return f"Mirror analysis failed: {exc}", []
        elapsed = int((time.time() - t0) * 1000)
        score = mirror_data.get("overall_score", 0)
        tools_used.append({
            "name": "adversarial_analysis",
            "preview": f"5-layer footprint analysis · risk score {score}/100",
            "ms": elapsed,
        })
        return mirror_data["llm_context"], tools_used

    def _tool(name: str, preview: str, fn):
        t0 = time.time()
        result = fn()
        elapsed_ms = int((time.time() - t0) * 1000)
        tools_used.append({
            "name": name,
            "preview": preview,
            "ms": elapsed_ms,
        })
        return result

    # Always get corpus stats (fast, always relevant)
    stats = _tool("corpus_stats", "indexing corpus stats",
                  lambda: _corpus_stats(conn, scope=scope))
    ext_str = ", ".join(
        f"{e['ext']}({e['count']})" for e in stats["top_extensions"][:7]
    )
    ctx_parts.append(
        f"Corpus: {stats['total_files']:,} files · "
        f"{stats['total_size_bytes']/1e9:.1f} GB · "
        f"{stats['modified_last_week']:,} modified this week · "
        f"top types: {ext_str}"
    )
    qctx = _query_context(conn, q, scope=scope, limit=6)
    if qctx:
        ctx_parts.append(qctx)

    # Route additional context based on query intent
    wants_largest = any(w in q_lower for w in [
        "large", "biggest", "heaviest", "space", "size", "gb", "mb",
        "most space", "big files"])
    wants_dupes = any(w in q_lower for w in [
        "duplicate", "copy", "copies", "same file", "dupe"])
    wants_stale = any(w in q_lower for w in [
        "delete", "clean", "old", "stale", "unused", "download", "desktop"])
    wants_workstreams = any(w in q_lower for w in [
        "workstream", "project", "cluster", "topic", "category",
        "what do i work on", "about my files", "overview", "corpus"])
    wants_recent = any(w in q_lower for w in [
        "recent", "new", "today", "this week", "modified", "changed"])

    # Mode overrides: retune → always gather stale + dupes
    if mode == "retune":
        wants_dupes = True
        wants_stale = True
    if mode == "report":
        wants_workstreams = True
    if mode == "archive":
        wants_largest = True

    if wants_largest:
        files = _tool("list_largest", "scanning for large files",
                      lambda: _list_largest(conn, limit=15, scope=scope))
        if files:
            lines = [f"  - {f['name']}: {f['size_bytes']/1e6:.0f} MB" for f in files[:12]]
            ctx_parts.append("Largest files:\n" + "\n".join(lines))

    if wants_dupes:
        d = _tool("find_duplicates", "scanning for duplicates",
                  lambda: _find_duplicates_summary(conn, limit=12,
                                                   scope=scope))
        ctx_parts.append(
            f"Duplicates: {d['group_count']} groups · "
            f"~{d['total_wasted_bytes']/1e6:.0f} MB potentially wasted"
        )
        if d["top_groups"]:
            lines = [f"  - {g['name']} ×{g['count']} ({g['wasted']/1e6:.1f} MB wasted)"
                     for g in d["top_groups"][:8]]
            ctx_parts.append("Top duplicate groups:\n" + "\n".join(lines))

    if wants_stale:
        stale = _tool("stale_downloads", "finding stale files",
                      lambda: _stale_downloads(conn, older_than_days=30,
                                               limit=15, scope=scope))
        total_stale_mb = sum(f["size_bytes"] for f in stale) / 1e6
        ctx_parts.append(
            f"Stale downloads/desktop (>30 days): {len(stale)} files · {total_stale_mb:.0f} MB"
        )
        if stale:
            lines = [f"  - {f['name']} ({f['age_days']}d old, {f['size_bytes']/1e6:.0f} MB)"
                     for f in stale[:8]]
            ctx_parts.append("\n".join(lines))

    if wants_workstreams:
        ws = _tool("get_workstreams", "loading semantic workstreams",
                   lambda: _get_workstreams(conn, limit=12, scope=scope))
        if ws:
            lines = [
                f"  - [{w['id']}] {w['files']} files · {w['size_bytes']/1e6:.0f} MB · "
                f"e.g. {', '.join(w['samples'][:2])}"
                for w in ws[:10]
            ]
            ctx_parts.append("Semantic workstreams:\n" + "\n".join(lines))

    if wants_recent:
        recent = _tool("recent_files", "loading recent activity",
                       lambda: _recent_files(conn, days=7, limit=12,
                                             scope=scope))
        if recent:
            lines = [f"  - {f['name']} ({f['hours_ago']}h ago)" for f in recent[:10]]
            ctx_parts.append("Recently modified:\n" + "\n".join(lines))

    return "\n\n".join(ctx_parts), tools_used


# ─── Ollama Streaming Interface ───────────────────────────────────────────────

def _ollama_stream(cfg: dict, messages: list, temp: float = 0.24,
                   model: str = "") -> Generator[dict, None, None]:
    """Streaming provider router output, normalized to Ollama chunk shape."""
    ctx = int(cfg.get("iris_num_ctx", cfg.get("num_ctx", 4096)))
    sec = int(cfg.get("llm_timeout_sec", 120))
    yield from ollama.stream_chat(
        cfg,
        messages,
        feature="iris",
        model=model,
        temp=float(temp),
        num_ctx=ctx,
        timeout=sec,
    )


def _mode_temp(mode: str, q: str) -> float:
    if mode in {"audit", "mirror", "compare"}:
        return 0.35
    if len(q) < 44:
        return 0.18
    return 0.24


def _q_hard(q: str) -> bool:
    txt = str(q or "").lower()
    score = 0
    if len(txt) > 320:
        score += 1
    if txt.count("?") > 1:
        score += 1
    keys = (
        "compare", "tradeoff", "risk", "audit", "contradiction", "timeline",
        "root cause", "evidence", "simulate", "strategy", "hypothesis",
        "step-by-step", "analyze", "analyse", "why",
    )
    if any(k in txt for k in keys):
        score += 1
    if len(_TERM_RE.findall(txt)) > 45:
        score += 1
    return score >= 2


def _mode_model(cfg: dict, mode: str, q: str) -> str:
    fast = str(cfg.get("phi4_fast_model")
               or cfg.get("fast_model")
               or cfg.get("model", "")).strip()
    deep = str(cfg.get("phi4_deep_model")
               or cfg.get("infer_model")
               or cfg.get("model", "")).strip()
    if mode in {"audit", "compare", "contradiction", "mirror"}:
        return deep or fast
    if _q_hard(q):
        return deep or fast
    return fast or deep


def _context_cap(mode: str) -> int:
    if mode in {"mirror", "audit"}:
        return 60000
    if mode in {"compare", "contradiction", "audience"}:
        return 38000
    return 26000


def _fallback_prompt(messages: list[dict]) -> str:
    lines: list[str] = []
    for row in messages[-6:]:
        role = str(row.get("role", "")).strip().lower()
        txt = str(row.get("content", "")).strip()
        if role not in {"system", "user", "assistant"} or not txt:
            continue
        cap = 520 if role == "system" else 720
        lines.append(f"{role.upper()}:\n{txt[:cap]}")
    return "\n\n".join(lines)


def _fallback_text(cfg: dict, messages: list[dict], model: str = "") -> str:
    prompt = _fallback_prompt(messages)
    if not prompt:
        return ""
    try:
        return ollama.text(cfg, prompt, feature="iris", temp=0.16,
                           model=model, num_ctx=3072, timeout=70)
    except Exception:
        return ""


def _emit_text_chunks(txt: str, width: int = 120) -> Generator[str, None, None]:
    raw = str(txt or "").strip()
    if not raw:
        return
    for i in range(0, len(raw), width):
        yield _chunk("token", content=raw[i:i + width]) + "\n"


# ─── Streaming Response Generator ────────────────────────────────────────────

def stream_response(cfg: dict, conn,
                    body: dict) -> Generator[str, None, None]:
    """
    Generator yielding newline-terminated JSON chunks for the browser.

    Chunk types emitted:
      {"type":"tool_start", "name":"...", "preview":"..."}
      {"type":"tool_end",   "name":"...", "ms":N}
      {"type":"token",      "content":"..."}
      {"type":"done",       "tok_per_sec":N, "total_tokens":N}
      {"type":"error",      "message":"..."}
    """
    mode = str(body.get("mode", "report"))
    q = str(body.get("q", "")).strip()[:2400]
    run = str(body.get("run", "")).strip()
    history = _history_pack(list(body.get("history", [])))
    # Identity-mode extras
    selected_ids: list[str] = [str(i) for i in body.get("selected_ids", []) if i]
    audience_id: str = str(body.get("audience", "recruiter"))

    if not q:
        yield _chunk("error", message="Empty query") + "\n"
        return

    # Larger context window for modes that produce long structured output
    if mode in ("mirror", "audit", "compare"):
        base_ctx = int(cfg.get("iris_num_ctx", cfg.get("num_ctx", 4096)))
        cfg = {**cfg, "iris_num_ctx": max(base_ctx, 8192)}

    # ── Step 1: Gather DB context ─────────────────────────────────────────
    try:
        context_text, tools_used = _gather_context(
            conn, q, mode,
            cfg=cfg,
            run=run,
            selected_ids=selected_ids or None,
            audience_id=audience_id or None,
        )
    except Exception as exc:
        context_text = "context unavailable"
        tools_used = []
        yield _chunk("error", message=f"Context error: {exc}") + "\n"

    ctx_cap = _context_cap(mode)
    if len(context_text) > ctx_cap:
        context_text = context_text[:ctx_cap] + "\n\n[context clipped]"

    # Emit tool events to the UI.
    for idx, t in enumerate(tools_used, start=1):
        tid = f"tool-{idx}"
        yield _chunk("tool_start", id=tid, name=t["name"],
                     preview=t["preview"]) + "\n"
        yield _chunk("tool_end", id=tid, name=t["name"], ms=t["ms"]) + "\n"

    # ── Step 2: Build prompt ──────────────────────────────────────────────
    system_content = (
        BASE_SYSTEM.format(corpus="(see context below)")
        + "\n"
        + MODE_ADDENDUM.get(mode, MODE_ADDENDUM["report"])
        + "\n## Context\n"
        + context_text
    )

    messages: list = [{"role": "system", "content": system_content}]
    for h in history[-10:]:
        if isinstance(h, dict) and h.get("role") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])[:2000]})
    messages.append({"role": "user", "content": q})

    # ── Step 3: Stream LLM response ───────────────────────────────────────
    t_start = time.time()
    total_tokens = 0
    emitted = 0
    in_think = False  # skip leaked reasoning blocks
    temp = _mode_temp(mode, q)
    model = _mode_model(cfg, mode, q)

    try:
        for chunk in _ollama_stream(cfg, messages, temp=temp, model=model):
            tok = chunk.get("message", {}).get("content", "")

            # Filter out leaked reasoning blocks for compact models.
            if tok:
                if "<think>" in tok or "<reasoning>" in tok:
                    in_think = True
                if in_think:
                    if "</think>" in tok or "</reasoning>" in tok:
                        in_think = False
                        after = tok
                        if "</think>" in after:
                            after = after.split("</think>", 1)[1]
                        if "</reasoning>" in after:
                            after = after.split("</reasoning>", 1)[1]
                        if after:
                            emitted += len(after)
                            yield _chunk("token", content=after) + "\n"
                    continue
                emitted += len(tok)
                yield _chunk("token", content=tok) + "\n"

            if chunk.get("done"):
                total_tokens = (
                    chunk.get("eval_count", 0) +
                    chunk.get("prompt_eval_count", 0)
                )

    except Exception as exc:
        if emitted <= 0:
            fb = _fallback_text(cfg, messages, model=model)
            if fb:
                for line in _emit_text_chunks(fb):
                    yield line
                elapsed = max(0.01, time.time() - t_start)
                yield _chunk("done",
                             tok_per_sec=round(len(fb) / elapsed, 1),
                             total_tokens=len(fb),
                             fallback=True) + "\n"
                return
        yield _chunk("error", message=f"Ollama error: {exc}") + "\n"
        return

    elapsed = max(0.01, time.time() - t_start)
    yield _chunk("done",
                 tok_per_sec=round(total_tokens / elapsed, 1),
                 total_tokens=total_tokens) + "\n"


def _history_line(txt: str, cap: int) -> str:
    return " ".join(str(txt or "").split())[:cap]


def _history_pack(history: list[dict], max_msgs: int = 12,
                  max_chars: int = 12000) -> list[dict]:
    out: list[dict] = []
    used = 0
    for row in reversed(history[-max_msgs * 2:]):
        if not isinstance(row, dict):
            continue
        role = str(row.get("role", "")).strip().lower()
        if role not in {"user", "assistant"}:
            continue
        txt = str(row.get("content", "")).strip()
        if not txt:
            continue
        cap = 1200 if role == "user" else 900
        txt = _history_line(txt, cap=cap)
        if used + len(txt) > max_chars:
            continue
        out.append({"role": role, "content": txt})
        used += len(txt)
        if len(out) >= max_msgs:
            break
    out.reverse()
    return out


def _chunk(type_: str, **kwargs) -> str:
    return json.dumps({"type": type_, **kwargs})
