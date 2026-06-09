"""
# DEPRECATED — never imported by the running ctxorg/server.py
# Only referenced in optic/v1/server.py (not the active server).
# Stage 13 (Iris context indexing) is pending — this will be wired when
# indexing during audit is implemented.
# DO NOT DELETE — keep as reference implementation for pipeline Stage 13.

Optic V1 — Iris Audit Chat
===========================
Conversational audit interface. Answers questions about a user's
signal profile drawing from the V1 database (claims, signals,
contradictions, sources, workstreams). Tries Ollama first via direct
HTTP call (no ctxorg config needed), falls back to deterministic
DB-driven responses.
"""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.request
from pathlib import Path
from typing import Any


_OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
_OLLAMA_TIMEOUT = 30

_IRIS_SYSTEM_PROMPT = """You are Iris, the audit intelligence inside Optic V1.
You help users understand what their digital footprint reveals about them.
Answer the user's question using the provided audit context.

Context from the user's self-audit:
{context}

Rules:
- Be direct and specific. No filler openers ("Certainly!", "Great question!").
- Cite counts and categories from the context when relevant.
- If evidence is thin, say so. Don't invent.
- Keep responses 2-4 paragraphs. Use bullet lists for 3+ items.
- Frame inferences as possibilities, not facts.
- Never output raw JSON or database internals."""


def _clean_iris_name(raw: str) -> str:
    """Strip URL fragments, hex noise from workstream names."""
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


class IrisAuditChat:
    """Answers audit questions using V1 database context."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = str(db_path) if db_path else ""

    # ── public API ────────────────────────────────────────────

    def ask(self, question: str, db_path: str | Path = "") -> str:
        """Answer an audit question. Returns the answer text."""
        path = str(db_path or self.db_path)
        ctx = self._gather_context(path)
        return (self._try_deepseek(question, ctx) or
                self._try_ollama(question, ctx) or
                self._fallback(question, ctx))

    def iris_chat(
        self,
        q: str,
        db_path: str | Path = "",
        *,
        mode: str = "report",
        history: list[dict] | None = None,
        audience: str = "recruiter",
    ) -> str:
        """Handle the full Iris chat protocol (matching the frontend's /api/iris call).

        Returns the assistant's text response.
        """
        path = str(db_path or self.db_path)
        ctx = self._gather_context(path)
        mode_text = self._mode_addendum(mode.title())
        system = (
            f"You are Iris, an intelligent assistant inside Optic — a personal file intelligence app.\n\n"
            f"Audit context:\n{ctx}\n\n"
            f"Current mode: {mode_text}\n"
            f"Audience lens: {audience}\n\n"
            f"Rules: Be direct, specific, concise. No filler openers. "
            f"Cite real data when available. Frame inferences as possibilities."
        )
        messages = self._build_messages(system, q, history or [])
        return (self._try_deepseek_messages(messages) or
                self._try_ollama_messages(messages) or
                self._fallback(q, ctx))

    # ── context gathering ─────────────────────────────────────

    def _gather_context(self, db_path: str) -> str:
        if not db_path or not Path(db_path).exists():
            return "No audit database available."

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            parts: list[str] = []

            # Claims
            claims = conn.execute(
                "SELECT COUNT(*) as c FROM claims"
            ).fetchone()
            parts.append(f"Total inference claims: {claims['c']}")

            # Claims by audience
            aud = conn.execute(
                "SELECT audience_lens, COUNT(*) as c FROM claims "
                "GROUP BY audience_lens ORDER BY c DESC"
            ).fetchall()
            if aud:
                parts.append(
                    "Claims by audience: "
                    + ", ".join(
                        f"{r['audience_lens'] or 'general'}={r['c']}"
                        for r in aud[:8]
                    )
                )

            # Top claim titles
            titles = conn.execute(
                "SELECT DISTINCT title FROM claims LIMIT 10"
            ).fetchall()
            if titles:
                parts.append(
                    "Claim topics: "
                    + ", ".join((r["title"] or "?") for r in titles)
                )

            # Confidence bands
            conf = conn.execute(
                "SELECT confidence_band, COUNT(*) as c FROM claims "
                "GROUP BY confidence_band ORDER BY c DESC"
            ).fetchall()
            if conf:
                parts.append(
                    "Confidence: "
                    + ", ".join(
                        f"{r['confidence_band'] or 'unknown'}={r['c']}"
                        for r in conf
                    )
                )

            # Signals
            sigs = conn.execute(
                "SELECT category, COUNT(*) as c FROM signals "
                "GROUP BY category ORDER BY c DESC"
            ).fetchall()
            if sigs:
                parts.append(
                    "Signals: "
                    + ", ".join(
                        f"{s['category']}={s['c']}" for s in sigs[:8]
                    )
                )

            # Contradictions
            cons = conn.execute(
                "SELECT COUNT(*) as c FROM contradictions"
            ).fetchone()
            parts.append(f"Contradictions detected: {cons['c']}")

            # Risks
            risks = conn.execute(
                "SELECT category, description, severity FROM risks "
                "ORDER BY severity DESC LIMIT 5"
            ).fetchall()
            if risks:
                parts.append(
                    "Top risks: "
                    + "; ".join(
                        f"[{r['severity']}] {r['description'][:100]}"
                        for r in risks
                    )
                )

            # Pending repairs
            repairs = conn.execute(
                "SELECT COUNT(*) as c FROM repairs WHERE status='pending'"
            ).fetchone()
            parts.append(f"Pending repairs: {repairs['c']}")

            # Workstreams (derived from signals)
            ws = self._derive_workstream_summaries(conn)
            if ws:
                parts.append("Workstreams:\n" + ws)

            # Sources
            sources = conn.execute(
                "SELECT COUNT(*) as c FROM sources WHERE status='ready'"
            ).fetchone()
            parts.append(f"Verified sources: {sources['c']}")

            # Key claims detail
            top = conn.execute(
                "SELECT title, claim, audience_lens, confidence_band, severity "
                "FROM claims ORDER BY severity DESC LIMIT 6"
            ).fetchall()
            if top:
                parts.append(
                    "Key claims:\n"
                    + "\n".join(
                        f"  [{t['audience_lens'] or 'general'}] {t['title']}"
                        f" ({t['confidence_band'] or '?'} confidence)"
                        f" — {t['claim'][:120] if t['claim'] else 'no detail'}"
                        for t in top
                    )
                )

            conn.close()
            return "\n".join(parts)

        except Exception:
            return "Could not read audit database."

    def _derive_workstream_summaries(self, conn: sqlite3.Connection) -> str:
        """Summarize top workstreams from signals metadata."""
        import json as _json

        rows = conn.execute(
            "SELECT * FROM signals WHERE category='frequent_topic'"
        ).fetchall()
        if not rows:
            return ""

        groups: dict[str, dict] = {}
        for row in rows:
            try:
                meta = _json.loads(row["metadata"] or "{}")
            except Exception:
                meta = {}
            name = _clean_iris_name(meta.get("workstream_name", "Unknown"))
            if name not in groups:
                groups[name] = {
                    "name": name,
                    "confidence": float(meta.get("confidence", 0.5)),
                    "file_count": int(meta.get("file_count", 0)),
                    "topics": meta.get("topics", []),
                }

        lines = []
        for name, data in sorted(
            groups.items(),
            key=lambda x: x[1]["confidence"],
            reverse=True,
        )[:8]:
            conf_pct = int(data["confidence"] * 100)
            topics = ", ".join(data["topics"][:3]) if data["topics"] else "general"
            lines.append(
                f"  {name}: {data['file_count']} files, "
                f"{conf_pct}% confidence — topics: {topics}"
            )

        return "\n".join(lines) if lines else ""

    # ── Ollama integration ────────────────────────────────────

    @staticmethod
    def _ollama_available() -> bool:
        """Check if Ollama is running and has models loaded."""
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/tags",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                return bool(data.get("models"))
        except Exception:
            return False

    def _try_deepseek(self, question: str, context: str) -> str | None:
        """Try DeepSeek API; return None if unavailable."""
        import os
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            return None
        system = _IRIS_SYSTEM_PROMPT.format(context=context)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ]
        payload = json.dumps({
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "messages": messages,
            "stream": False,
            "temperature": 0.3,
            "max_tokens": 500,
        }).encode()
        try:
            base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
            req = urllib.request.Request(
                f"{base}/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                },
            )
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode())
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            return content or None
        except Exception:
            return None

    def _try_deepseek_messages(self, messages: list[dict]) -> str | None:
        """Send messages to DeepSeek API; return content or None."""
        import os
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            return None
        payload = json.dumps({
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "messages": messages,
            "stream": False,
            "temperature": 0.3,
            "max_tokens": 500,
        }).encode()
        try:
            base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
            req = urllib.request.Request(
                f"{base}/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                },
            )
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode())
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            return content or None
        except Exception:
            return None

    def _try_ollama(self, question: str, context: str) -> str | None:
        """Try Ollama chat; return None if unavailable."""
        system = _IRIS_SYSTEM_PROMPT.format(context=context)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ]
        return self._try_ollama_messages(messages)

    def _try_ollama_messages(self, messages: list[dict]) -> str | None:
        """Send messages to Ollama /api/chat; return content or None."""
        if not self._ollama_available():
            return None

        payload = json.dumps(
            {
                "model": self._pick_model(),
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.3, "num_ctx": 4096},
            }
        ).encode()

        try:
            req = urllib.request.Request(
                _OLLAMA_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=_OLLAMA_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
        except Exception:
            return None

        # Extract response from Ollama chat format
        if isinstance(data.get("message"), dict):
            content = data["message"].get("content", "").strip()
            if content:
                return content
        return None

    def _pick_model(self) -> str:
        """Try to discover which model Ollama has available."""
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/tags",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                models = [m.get("name", "") for m in data.get("models", [])]
                if models:
                    # Prefer phi4 / gemma / qwen / llama
                    for pref in ("phi4", "gemma", "qwen", "llama", "mistral"):
                        for m in models:
                            if m.startswith(pref):
                                return m
                    return models[0]
        except Exception:
            pass
        return "phi4-mini"  # default

    # ── mode descriptions ─────────────────────────────────────

    @staticmethod
    def _mode_addendum(mode: str) -> str:
        modes = {
            "Report": (
                "Analyze the user's audit data and surface what matters. "
                "Cover: what the data reveals about their work and interests, "
                "what stands out, and one concrete recommendation. "
                "Write 2-4 paragraphs. No numbered list of statistics."
            ),
            "Archive": (
                "Help organize and structure files. Suggest clear naming conventions "
                "and folder structures. Never execute operations — only propose them."
            ),
            "Entity": (
                "Interrogate a single piece of evidence. Say 'this suggests' rather "
                "than 'you are'. Separate direct evidence from inference."
            ),
            "Explore": (
                "Explore the user's data landscape. Highlight surprising patterns, "
                "connections between workstreams, and untapped opportunities."
            ),
        }
        return modes.get(mode, modes["Report"])

    # ── message building ──────────────────────────────────────

    @staticmethod
    def _build_messages(
        system: str, q: str, history: list[dict]
    ) -> list[dict]:
        """Build chat messages with system prompt and history."""
        msgs = [{"role": "system", "content": system}]
        # Include last few history turns
        for h in history[-6:]:
            role = h.get("role", "user")
            content = h.get("content", "")
            if role in ("user", "assistant") and content:
                msgs.append({"role": role, "content": content})
        msgs.append({"role": "user", "content": q})
        return msgs

    # ── fallback ─────────────────────────────────────────────

    def _fallback(self, question: str, context: str) -> str:
        """Deterministic, DB-driven answer when no LLM is available."""
        q = question.lower()
        lines = context.split("\n")

        # ── risks ── (check first: specific, unambiguous)
        if any(w in q for w in ("risk", "danger", "threat", "exposure", "vulnerab")):
            risk_lines = [l for l in lines if "risk" in l.lower()]
            return (
                "Based on your audit database, "
                + (risk_lines[0].strip() if risk_lines else "no risks are currently flagged")
                + ". Each risk is audience-specific — check the full risk register for "
                "detailed descriptions and severity levels."
            )

        # ── contradictions ── (check before general profile — "contradiction" is specific)
        if any(w in q for w in ("contradict", "inconsistent", "conflict", "disagree")):
            cons = [l for l in lines if l.lower().startswith("contradictions")]
            return (
                f"Your audit found: {cons[0] if cons else 'No contradictions detected'}. "
                "Contradictions are flagged when claims conflict across audience lenses. "
                "Each contradiction includes a resolution suggestion."
            )

        # ── repairs ── (check before general profile)
        if any(w in q for w in ("fix", "repair", "improve", "action")):
            repairs = [l for l in lines if "repair" in l.lower()]
            risks = [l for l in lines if "risk" in l.lower()]
            parts = [
                repairs[0].strip() if repairs else "No pending repairs.",
                risks[0].strip() if risks else "No active risks.",
                "\nRecommendation: Run a full audit to generate repair actions "
                "ranked by impact × urgency ÷ effort. Focus on high-severity claims first."
            ]
            return "\n".join(parts)

        # ── workstreams ── (specific topic)
        if any(w in q for w in ("workstream", "cluster", "organize", "folder", "structure")):
            ws_section = []
            in_ws = False
            for l in lines:
                if l.startswith("Workstreams:"):
                    in_ws = True
                    continue
                if in_ws and l.startswith("  "):
                    ws_section.append(l)
                elif in_ws and not l.startswith("  "):
                    break

            if ws_section:
                return (
                    "Your files are organized into these workstreams:\n\n"
                    + "\n".join(ws_section)
                    + "\n\nEach workstream clusters files by semantic meaning, not folder location."
                )

            return (
                "No workstreams have been clustered yet. Run a scan to organize "
                "your files by semantic meaning rather than folder location."
            )

        # ── general ──
        return (
            f"Here's a summary of your Optic V1 audit:\n\n{context}\n\n"
            "Optic surfaces what your digital footprint implies — these are probabilistic "
            "inferences, not identity truths. Every claim includes counterarguments and "
            "confidence bands. Ask about risks, repairs, contradictions, or specific "
            "workstreams for targeted answers."
        )
