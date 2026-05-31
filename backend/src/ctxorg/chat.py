from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import cfg as cfgmod
from . import db, ollama, retry

_RUN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_HARD_KEYS = {
    "compare", "contradiction", "timeline", "root cause", "evidence",
    "risk", "strategy", "hypothesis", "step-by-step", "analyze",
    "analyse", "why",
}


def reply(cfg: dict, req: dict) -> dict:
    try:
        run = run_clean(req.get("run") or latest(cfg))
    except ValueError:
        return err("", "invalid_run_id")
    if not run:
        return err(run, "run_not_found")
    try:
        graph = graph_data(cfg, run)
    except FileNotFoundError:
        return err(run, "run_not_found")
    node = graph_node(graph, str(req.get("id") or "")) or \
        graph_path(graph, str(req.get("path") or ""))
    if not node:
        return err(run, "unknown node")
    ctx = context(cfg, run, graph, node, req)
    return ask(cfg, run, ctx)


def latest(cfg: dict) -> str:
    root = cfgmod.state_dir(cfg, "graphs")
    vals = sorted(root.glob("*.json"), reverse=True)
    return vals[0].stem if vals else ""


def graph_data(cfg: dict, run: str) -> dict:
    run = run_clean(run)
    path = cfgmod.state_dir(cfg, "graphs") / f"{run}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def run_clean(raw: object) -> str:
    val = str(raw or "").strip()
    if not val:
        return ""
    if _RUN_RE.fullmatch(val):
        return val
    raise ValueError("invalid_run_id")


def graph_node(graph: dict, iid: str) -> dict | None:
    return next((n for n in graph.get("nodes", []) if n.get("id") == iid), None)


def graph_path(graph: dict, path: str) -> dict | None:
    return next((n for n in graph.get("nodes", [])
                 if n.get("path") == path), None)


def context(cfg: dict, run: str, graph: dict, node: dict, req: dict) -> dict:
    conn = db.open_db(cfg)
    item = item_row(conn, node["id"]) or node
    near = neighbors(conn, graph, node["id"])
    max_msgs = max(2, int(cfg.get("chat_history_max_msgs", 6) or 6))
    max_chars = max(400, int(cfg.get("chat_history_max_chars", 2400) or 2400))
    hist = history_pack(req.get("history"), max_msgs=max_msgs,
                        max_chars=max_chars)
    t_mode = req.get("tool_mode", cfg.get("chat_tool_loop", False))
    return {"run": run, "q": str(req.get("q") or ""), "kind": kind(req),
            "item": item, "near": near, "history": hist,
            "tool_mode": bool(t_mode)}


def history_pack(raw: object, max_msgs: int = 6,
                 max_chars: int = 2400) -> list[dict]:
    rows = raw if isinstance(raw, list) else []
    out, used = [], 0
    for row in reversed(rows[-max_msgs * 2:]):
        rec = history_row(row, used, max_chars)
        if not rec:
            continue
        out.append(rec)
        used += len(rec["content"])
        if len(out) >= max_msgs:
            break
    out.reverse()
    return out


def history_row(row: object, used: int, max_chars: int) -> dict | None:
    if not isinstance(row, dict):
        return None
    role = str(row.get("role", "")).strip().lower()
    if role not in {"user", "assistant"}:
        return None
    txt = " ".join(str(row.get("content", "")).split())[:420]
    if not txt or used + len(txt) > max_chars:
        return None
    return {"role": role, "content": txt}


def kind(req: dict) -> str:
    val = str(req.get("kind") or "question")
    vals = {"question", "similar", "rename", "tasks"}
    return val if val in vals else "question"


def item_row(conn, iid: str) -> dict | None:
    rows = db.rows(conn, "SELECT * FROM items WHERE id=?", (iid,))
    return rows[0] if rows else None


def neighbors(conn, graph: dict, iid: str) -> list[dict]:
    rows = sorted(near_links(graph, iid), key=lambda r: -r["score"])[:8]
    return [near_row(conn, r, iid) for r in rows]


def near_links(graph: dict, iid: str) -> list[dict]:
    links = graph.get("links", [])
    return [l for l in links if iid in (l.get("a"), l.get("b"))]


def near_row(conn, link: dict, iid: str) -> dict:
    nid = link["b"] if link["a"] == iid else link["a"]
    item = item_row(conn, nid) or {"id": nid, "path": nid, "text": ""}
    return {"id": nid, "path": item["path"], "score": link["score"],
            "text": str(item.get("text") or "")[:900]}


def ask(cfg: dict, run: str, ctx: dict) -> dict:
    mods = pick_chat_models(cfg, ctx)
    last = RuntimeError("chat_failed")
    for model in mods:
        try:
            return ask_struct(cfg, run, ctx, model)
        except Exception as exc:
            last = exc
            note = f"model={model} err={str(exc)[:200]}"
            trace(cfg, run, ctx, "structured_failed", note)
    for model in mods:
        out = fallback(cfg, run, ctx, model=model)
        if out:
            return out
    dead(cfg, run, ctx, last)
    trace(cfg, run, ctx, "dead_letter", str(last))
    return err(run, "Iris unavailable")


def ask_struct(cfg: dict, run: str, ctx: dict, model: str) -> dict:
    sctx = fit_ctx(cfg, ctx, model, "structured")
    note = tool_brief(cfg, run, sctx, model) if tool_loop_on(cfg, sctx) else ""
    try:
        data = retry.run(
            lambda: ollama.gen(
                cfg,
                prompt(sctx, note),
                feature="chat",
                model=model,
                schema=CHAT_SCHEMA,
            ),
            attempts(cfg),
            base(cfg),
        )
    except Exception as exc:
        out = repair_struct(cfg, run, sctx, model, note, exc)
        if out:
            return out
        raise
    out = valid(sctx, data)
    trace(cfg, run, ctx, "structured_ready", f"model={model}")
    return out


def pick_chat_model(cfg: dict, ctx: dict) -> str:
    fast = str(cfg.get("chat_model") or cfg.get("fast_model")
               or cfg.get("model", "")).strip()
    deep = str(cfg.get("phi4_deep_model") or cfg.get("infer_model")
               or cfg.get("model", "")).strip()
    return (deep or fast) if hard_query(ctx) else (fast or deep)


def pick_chat_models(cfg: dict, ctx: dict) -> list[str]:
    pri = pick_chat_model(cfg, ctx)
    deep = str(cfg.get("phi4_deep_model") or cfg.get("infer_model")
               or cfg.get("model", "")).strip()
    fast = str(cfg.get("chat_model") or cfg.get("fast_model")
               or cfg.get("model", "")).strip()
    cands = [pri, deep, fast, str(cfg.get("chat_fallback_model", "")).strip()]
    out = []
    for row in cands:
        txt = str(row or "").strip()
        if txt and txt not in out:
            out.append(txt)
    return out[:4]


def hard_query(ctx: dict) -> bool:
    q = str(ctx.get("q", "")).lower()
    if any(k in q for k in _HARD_KEYS):
        return True
    score = 0
    if len(q) > 240:
        score += 1
    if q.count("?") > 1:
        score += 1
    if str(ctx.get("kind", "")) in {"tasks", "rename"}:
        score += 1
    return score >= 2


def tool_loop_on(cfg: dict, ctx: dict) -> bool:
    if not bool(ctx.get("tool_mode", False)):
        return False
    if str(ctx.get("kind", "")) in {"tasks", "rename"}:
        return True
    return hard_query(ctx) or bool(cfg.get("chat_tool_force", False))


def attempts(cfg: dict) -> int:
    return int(cfg.get("retry", {}).get("attempts", 2))


def base(cfg: dict) -> float:
    return float(cfg.get("retry", {}).get("base_sec", 0.25))


def fit_ctx(cfg: dict, ctx: dict, model: str, stage: str) -> dict:
    lim = ctx_limits(cfg, ctx, model, stage)
    out = dict(ctx)
    out["q"] = clip(ctx.get("q"), lim["q"])
    out["item"] = fit_item(ctx.get("item"), lim["item"])
    out["near"] = fit_near(ctx.get("near"), lim["near_rows"], lim["near"])
    out["history"] = fit_history(ctx.get("history"), lim["hist_rows"],
                                 lim["hist"])
    return out


def ctx_limits(cfg: dict, ctx: dict, model: str, stage: str) -> dict:
    small = ollama.small_model(model)
    base = int(cfg.get("chat_ctx_chars_small" if small else "chat_ctx_chars",
               2200 if small else 4200) or 2200)
    if hard_query(ctx) and not small:
        base += 400
    if stage == "fallback":
        base = min(base + 600, 5600)
    return {
        "q": min(1200, max(220, base // 4)),
        "item": min(1800 if not small else 900, max(380, base // 3)),
        "near": min(1100 if not small else 620, max(220, base // 5)),
        "near_rows": 6 if not small else 4,
        "hist": min(1400 if not small else 820, max(320, base // 4)),
        "hist_rows": 6 if not small else 4,
    }


def fit_item(row: object, max_txt: int) -> dict:
    src = row if isinstance(row, dict) else {}
    out = dict(src)
    out["id"] = str(src.get("id", ""))
    out["path"] = str(src.get("path", ""))
    out["text"] = clip(src.get("text"), max_txt)
    out["ext"] = str(src.get("ext", ""))
    out["size"] = int(src.get("size") or 0)
    return out


def fit_near(rows: object, max_rows: int, max_txt: int) -> list[dict]:
    vals = rows if isinstance(rows, list) else []
    out = []
    for row in vals[:max_rows]:
        if not isinstance(row, dict):
            continue
        rec = dict(row)
        rec["text"] = clip(row.get("text"), max_txt)
        out.append(rec)
    return out


def fit_history(rows: object, max_rows: int, max_chars: int) -> list[dict]:
    vals = rows if isinstance(rows, list) else []
    out, used = [], 0
    for row in reversed(vals[-max_rows * 2:]):
        if not isinstance(row, dict):
            continue
        role = str(row.get("role", "")).strip().lower()
        if role not in {"user", "assistant"}:
            continue
        txt = clip(row.get("content"), min(420, max_chars))
        if not txt or used + len(txt) > max_chars:
            continue
        out.append({"role": role, "content": txt})
        used += len(txt)
        if len(out) >= max_rows:
            break
    out.reverse()
    return out


def clip(raw: object, max_len: int) -> str:
    txt = " ".join(str(raw or "").split())
    return txt[:max(0, int(max_len or 0))]


def valid(ctx: dict, data: dict) -> dict:
    data = as_obj(data)
    return {"state": "READY", "answer": answer(data),
            "related": related(ctx), "rename_proposals": names(data, ctx),
            "tasks": tasks(data)}


def as_obj(data: object) -> dict:
    if isinstance(data, dict):
        return {
            "answer": str(data.get("answer", "")),
            "rename_proposals": list_or_empty(data.get("rename_proposals")),
            "tasks": list_or_empty(data.get("tasks")),
        }
    txt = str(data or "").strip()
    obj = parse_obj(txt)
    if obj:
        return obj
    return {"answer": txt[:1600]}


def list_or_empty(raw: object) -> list:
    return raw if isinstance(raw, list) else []


def parse_obj(txt: str) -> dict | None:
    raw = str(txt or "").strip()
    if not raw or ("{" not in raw and "```" not in raw):
        return None
    try:
        data = ollama.parse(raw)
    except Exception:
        return None
    return {
        "answer": str(data.get("answer", "")),
        "rename_proposals": list_or_empty(data.get("rename_proposals")),
        "tasks": list_or_empty(data.get("tasks")),
    }


def repair_struct(cfg: dict, run: str, ctx: dict, model: str, note: str,
                  exc: Exception) -> dict | None:
    if not json_fail(exc):
        return None
    trace(cfg, run, ctx, "structured_parse_fail", str(exc))
    try:
        txt = retry.run(
            lambda: ollama.text(
                cfg,
                repair_prompt(ctx, note),
                feature="chat",
                model=model,
                temp=float(cfg.get("chat_repair_temp", 0.0) or 0.0),
                num_ctx=int(cfg.get("chat_repair_num_ctx", 2048) or 2048),
                timeout=max(2, int(cfg.get("chat_timeout_sec",
                           cfg.get("llm_timeout_sec", 60)) or 60)),
            ),
            min(2, attempts(cfg)),
            base(cfg),
        )
    except Exception as sub:
        trace(cfg, run, ctx, "structured_repair_error", str(sub))
        return None
    obj = parse_obj(txt) or parse_obj(ollama.json_text(txt))
    if not obj:
        trace(cfg, run, ctx, "structured_repair_parse_fail", "")
        return None
    out = valid(ctx, obj)
    trace(cfg, run, ctx, "structured_repair_ready", f"model={model}")
    return out


def json_fail(exc: Exception) -> bool:
    txt = str(exc).lower()
    keys = ("json", "root_not_object", "unterminated", "delimiter", "expect")
    return any(k in txt for k in keys)


def fallback(cfg: dict, run: str, ctx: dict, model: str = "") -> dict | None:
    f_model = model or pick_chat_model(cfg, ctx)
    fctx = fit_ctx(cfg, ctx, f_model, "fallback")
    try:
        txt = retry.run(
            lambda: ollama.text(
                cfg,
                fallback_prompt(fctx),
                feature="chat",
                model=f_model,
                temp=float(cfg.get("chat_fallback_temp", 0.12) or 0.12),
                num_ctx=int(cfg.get("chat_fallback_num_ctx", 3072) or 3072),
                timeout=max(2, int(cfg.get("chat_timeout_sec",
                           cfg.get("llm_timeout_sec", 60)) or 60)),
            ),
            attempts(cfg),
            base(cfg),
        )
    except Exception as exc:
        note = f"model={model or 'default'} err={str(exc)[:200]}"
        trace(cfg, run, ctx, "fallback_error", note)
        return None
    ans = str(txt or "").strip()
    if not ans:
        trace(cfg, run, ctx, "fallback_empty", "")
        return None
    note = f"model={f_model or 'default'} answer_len={len(ans)}"
    trace(cfg, run, ctx, "fallback_ready", note)
    return {
        "state": "READY",
        "answer": ans[:1600],
        "related": related(fctx),
        "rename_proposals": [],
        "tasks": [],
    }


def answer(data: dict) -> str:
    txt = str(data.get("answer") or "").strip()
    return txt[:1600] or "No grounded answer returned."


def related(ctx: dict) -> list[dict]:
    return [{"id": r["id"], "path": r["path"], "why": score(r)}
            for r in ctx["near"][:5]]


def score(row: dict) -> str:
    val = float(row.get("score") or 0)
    return "strong match" if val >= 0.72 else "related file"


def names(data: dict, ctx: dict) -> list[dict]:
    ext = Path(ctx["item"]["path"]).suffix
    vals = data.get("rename_proposals") or []
    return [n for n in (clean_name(v, ext) for v in vals) if n][:5]


def clean_name(row: dict, ext: str) -> dict | None:
    if not isinstance(row, dict):
        return None
    name = str(row.get("name") or "").strip()
    if bad_name(name, ext):
        return None
    return {"name": name, "why": str(row.get("why") or "")[:240]}


def bad_name(name: str, ext: str) -> bool:
    return not name or "/" in name or "\\" in name or len(name) > 96 or \
        (ext and not name.endswith(ext))


def tasks(data: dict) -> list[dict]:
    vals = data.get("tasks") or []
    out = []
    for row in vals[:8]:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()[:120]
        why = str(row.get("why") or "").strip()[:240]
        if title:
            out.append({"title": title, "why": why})
        if len(out) >= 5:
            break
    return out


def dead(cfg: dict, run: str, ctx: dict, exc: Exception) -> None:
    path = cfgmod.state_dir(cfg, "dead") / f"{run}.chat.ndjson"
    rec = {"ts": time.time(), "id": ctx["item"]["id"], "err": str(exc)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


def trace(cfg: dict, run: str, ctx: dict, event: str, note: str) -> None:
    if not bool(cfg.get("chat_trace", True)):
        return
    path = cfgmod.state_dir(cfg, "dead") / f"{run}.chat.trace.ndjson"
    rec = {"ts": time.time(), "id": ctx["item"]["id"], "event": event}
    if note:
        rec["note"] = str(note)[:300]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


def err(run: str, msg: str) -> dict:
    return {"state": "DEAD_LETTER", "run": run, "answer": msg,
            "related": [], "rename_proposals": [], "tasks": []}


def prompt(ctx: dict, tool_note: str = "") -> str:
    near = "\n".join(near_line(r) for r in ctx["near"])
    hist = history_text(ctx.get("history") or [])
    note = tool_note.strip()[:2400] if tool_note else "none"
    return PROMPT.format(kind=ctx["kind"], q=ctx["q"][:800],
                         item=item_line(ctx["item"]), history=hist,
                         near=near or "none", tool_note=note)


def fallback_prompt(ctx: dict) -> str:
    near = "\n".join(near_line(r) for r in ctx["near"])
    hist = history_text(ctx.get("history") or [])
    return FALLBACK_PROMPT.format(
        kind=ctx["kind"],
        q=ctx["q"][:800],
        item=item_line(ctx["item"]),
        history=hist,
        near=near or "none",
    )


def repair_prompt(ctx: dict, tool_note: str = "") -> str:
    near = "\n".join(near_line(r) for r in ctx["near"])
    hist = history_text(ctx.get("history") or [])
    note = tool_note.strip()[:1200] if tool_note else "none"
    return REPAIR_PROMPT.format(
        kind=ctx["kind"],
        q=ctx["q"][:700],
        item=item_line(ctx["item"]),
        history=hist,
        near=near or "none",
        tool_note=note,
    )


def item_line(row: dict) -> str:
    txt = str(row.get("text") or "").replace("\n", " ")[:1600]
    ext = str(row.get("ext") or "")
    size = int(row.get("size") or 0)
    return f"id={row['id']} path={row['path']} ext={ext} size={size} text={txt}"


def near_line(row: dict) -> str:
    txt = str(row.get("text") or "").replace("\n", " ")[:500]
    return f"path={row['path']} score={row['score']} text={txt}"


def history_text(rows: list[dict]) -> str:
    if not rows:
        return "none"
    out = [f"{r['role']}: {r['content']}" for r in rows[:6]]
    return "\n".join(out)


def tool_brief(cfg: dict, run: str, ctx: dict, model: str) -> str:
    steps = max(1, int(cfg.get("chat_tool_max_steps", 3) or 3))
    calls = max(1, int(cfg.get("chat_tool_max_calls", 4) or 4))
    msgs = tool_seed(ctx)
    for _ in range(steps):
        try:
            raw = retry.run(
                lambda: ollama.chat_once(
                    cfg, msgs, feature="chat", model=model,
                    tools=TOOL_DEFS, temp=0.0,
                ),
                attempts(cfg),
                base(cfg),
            )
        except Exception as exc:
            trace(cfg, run, ctx, "tool_loop_error", str(exc))
            return ""
        msg = tool_msg(raw)
        t_calls = tool_calls(msg)
        if not t_calls:
            txt = str(msg.get("content", "")).strip()
            if txt:
                trace(cfg, run, ctx, "tool_loop_ready", f"len={len(txt)}")
                return txt[:1800]
            return ""
        rows = tool_results(ctx, t_calls[:calls])
        if not rows:
            return ""
        msgs.append({
            "role": "assistant",
            "content": str(msg.get("content", ""))[:200],
            "tool_calls": t_calls[:calls],
        })
        msgs.extend(rows)
    return ""


def tool_seed(ctx: dict) -> list[dict]:
    return [
        {"role": "system", "content": TOOL_SYSTEM},
        {"role": "user", "content": TOOL_USER.format(
            q=ctx["q"][:800], item=item_line(ctx["item"]),
            near="\n".join(near_line(r) for r in ctx["near"]) or "none",
        )},
    ]


def tool_msg(raw: object) -> dict:
    if isinstance(raw, dict):
        msg = raw.get("message")
        if isinstance(msg, dict):
            return msg
    return {}


def tool_calls(msg: dict) -> list[dict]:
    rows = msg.get("tool_calls")
    vals = rows if isinstance(rows, list) else []
    out = []
    for row in vals:
        if isinstance(row, dict):
            out.append(row)
    return out


def tool_results(ctx: dict, calls: list[dict]) -> list[dict]:
    out = []
    for row in calls:
        rec = tool_call(ctx, row)
        if rec:
            out.append({
                "role": "tool",
                "tool_name": rec["name"],
                "content": json.dumps(rec["data"], separators=(",", ":")),
            })
    return out


def tool_call(ctx: dict, row: dict) -> dict | None:
    fn = row.get("function", {}) if isinstance(row, dict) else {}
    name = str(fn.get("name", "")).strip().lower()
    args = tool_args(fn.get("arguments", {}))
    if name == "get_selected":
        lim = max(120, min(2000, int(args.get("max_chars", 900) or 900)))
        item = dict(ctx["item"])
        item["text"] = str(item.get("text", ""))[:lim]
        return {"name": name, "data": item}
    if name == "get_related":
        lim = max(1, min(8, int(args.get("limit", 5) or 5)))
        rows = [dict(v) for v in ctx["near"][:lim]]
        return {"name": name, "data": rows}
    if name == "search_related":
        qry = str(args.get("query", "")).strip().lower()
        lim = max(1, min(6, int(args.get("limit", 4) or 4)))
        rows = [dict(v) for v in ctx["near"] if qry in str(v).lower()]
        return {"name": name, "data": rows[:lim]}
    return None


def tool_args(raw: object) -> dict:
    if isinstance(raw, dict):
        return raw
    txt = str(raw or "").strip()
    if not txt:
        return {}
    try:
        out = json.loads(txt)
    except Exception:
        return {}
    return out if isinstance(out, dict) else {}


PROMPT = """
You are Iris, a local filesystem analyst.
Answer only from the selected file and nearby file evidence.
Do not claim that any rename or move has been applied.
If evidence is weak, say "insufficient evidence" and ask one precise follow-up.

Return strict JSON:
{{
  "answer": "short grounded answer",
  "rename_proposals": [{{"name": "safe-name.ext", "why": "evidence"}}],
  "tasks": [{{"title": "small task", "why": "evidence"}}]
}}

mode={kind}
question={q}
selected:
{item}
history:
{history}
nearby:
{near}
tool_notes:
{tool_note}
""".strip()


FALLBACK_PROMPT = """
You are Iris, a local filesystem analyst.
Answer only from selected and nearby file evidence.
Be concise, specific, and explicit about uncertainty.
Do not output JSON.

mode={kind}
question={q}
selected:
{item}
history:
{history}
nearby:
{near}
""".strip()


REPAIR_PROMPT = """
You are Iris.
Fix model output into strict JSON only.
Do not use markdown fences.
Return this exact object shape:
{{
  "answer": "short grounded answer",
  "rename_proposals": [{{"name": "safe-name.ext", "why": "evidence"}}],
  "tasks": [{{"title": "small task", "why": "evidence"}}]
}}
If uncertain, keep arrays empty and explain uncertainty in answer.

mode={kind}
question={q}
selected:
{item}
history:
{history}
nearby:
{near}
tool_notes:
{tool_note}
""".strip()


TOOL_SYSTEM = """
You are Iris.
Use tools when needed, then return a concise grounded answer.
Never invent files not present in tool outputs.
""".strip()


TOOL_USER = """
question={q}
selected:
{item}
nearby:
{near}
""".strip()


TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "get_selected",
            "description": "Get selected file metadata and excerpt.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_chars": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_related",
            "description": "Get related files with scores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_related",
            "description": "Search related files by query text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
]


CHAT_SCHEMA = {
    "type": "object",
    "required": ["answer", "rename_proposals", "tasks"],
    "properties": {
        "answer": {"type": "string"},
        "rename_proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "why"],
                "properties": {
                    "name": {"type": "string"},
                    "why": {"type": "string"},
                },
            },
        },
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "why"],
                "properties": {
                    "title": {"type": "string"},
                    "why": {"type": "string"},
                },
            },
        },
    },
}
