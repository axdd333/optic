from __future__ import annotations

import json
import random
import re
import time
import urllib.request
from collections.abc import Generator

from . import mirofish


def gen(cfg: dict, prompt: str, *, feature: str = "default",
        model: str = "", schema: dict | None = None) -> dict:
    err = None
    tm = timeout_sec(cfg, feature, None)
    for mdl in model_chain(cfg, feature, model):
        opts = options(cfg, feature, temp=0.1, model=mdl)
        think = pick_think(cfg, feature, mdl)
        for prov in providers(cfg, feature):
            try:
                if prov == "mirofish":
                    return mirofish.gen_json(cfg, prompt, mdl, feature, tm, opts)
                return ollama_json(cfg, prompt, mdl, think, opts, tm, schema)
            except Exception as exc:  # pragma: no cover - fallback path
                err = exc
    if err:
        raise err
    raise RuntimeError("llm_provider_unavailable")


def text(cfg: dict, prompt: str, *, feature: str = "default",
         model: str = "", temp: float = 0.2, num_ctx: int | None = None,
         timeout: int | None = None) -> str:
    tm = timeout_sec(cfg, feature, timeout)
    err = None
    for mdl in model_chain(cfg, feature, model):
        opts = options(cfg, feature, temp=temp, num_ctx=num_ctx, model=mdl)
        think = pick_think(cfg, feature, mdl)
        for prov in providers(cfg, feature):
            try:
                if prov == "mirofish":
                    return mirofish.gen_text(cfg, prompt, mdl, feature, tm, opts)
                return ollama_text(cfg, prompt, mdl, think, opts, tm)
            except Exception as exc:  # pragma: no cover - fallback path
                err = exc
    if err:
        raise err
    raise RuntimeError("llm_provider_unavailable")


def gen_text(cfg: dict, prompt: str, *, feature: str = "default",
             model: str = "", temp: float = 0.2) -> str:
    return text(cfg, prompt, feature=feature, model=model, temp=temp)


def chat_once(cfg: dict, messages: list[dict], *, feature: str = "chat",
              model: str = "", tools: list[dict] | None = None,
              fmt: dict | str | None = None, temp: float = 0.1,
              num_ctx: int | None = None,
              timeout: int | None = None) -> dict:
    tm = timeout_sec(cfg, feature, timeout)
    err = None
    for mdl in model_chain(cfg, feature, model):
        opts = options(cfg, feature, temp=temp, num_ctx=num_ctx, model=mdl)
        think = pick_think(cfg, feature, mdl)
        for prov in providers(cfg, feature):
            try:
                if prov == "mirofish":
                    if tools:
                        continue
                    txt = mirofish.gen_text(
                        cfg, chat_prompt(messages), mdl, feature, tm, opts
                    )
                    return {"message": {"role": "assistant", "content": txt}}
                raw = ollama_chat(cfg, messages, mdl, think, opts, tm, tools,
                                  fmt)
                msg = chat_msg(raw)
                if msg:
                    return {"message": msg}
                txt = answer(raw)
                if txt and txt != "{}":
                    return {"message": {"role": "assistant", "content": txt}}
                err = RuntimeError("chat_once_empty_message")
            except Exception as exc:  # pragma: no cover - fallback path
                err = exc
    if err:
        raise err
    raise RuntimeError("llm_provider_unavailable")


def stream_chat(cfg: dict, messages: list[dict], *,
                feature: str = "iris", model: str = "",
                temp: float = 0.3, num_ctx: int | None = None,
                timeout: int | None = None) -> Generator[dict, None, None]:
    tm = timeout_sec(cfg, feature, timeout)
    err = None
    for mdl in model_chain(cfg, feature, model):
        opts = options(cfg, feature, temp=temp, num_ctx=num_ctx, model=mdl)
        think = pick_think(cfg, feature, mdl)
        for prov in providers(cfg, feature):
            try:
                if prov == "mirofish":
                    yield from mirofish.stream_chat(cfg, messages, mdl,
                                                    feature, tm, opts)
                    return
                yield from ollama_stream(cfg, messages, mdl, think, opts, tm)
                return
            except Exception as exc:  # pragma: no cover - fallback path
                err = exc
    if err:
        raise err
    raise RuntimeError("llm_provider_unavailable")


def chat_stream(cfg: dict, messages: list[dict], *,
                feature: str = "iris") -> Generator[dict, None, None]:
    yield from stream_chat(cfg, messages, feature=feature)


def providers(cfg: dict, feature: str) -> list[str]:
    p0 = provider_name(cfg.get(f"{feature}_provider")
                       or cfg.get("llm_provider")
                       or cfg.get("provider_mode")
                       or cfg.get("provider")
                       or cfg.get("infer_engine")
                       or "ollama")
    out = [p0]
    if bool(cfg.get("provider_fallback_ollama", True)):
        if "ollama" not in out:
            out.append("ollama")
    else:
        p1 = provider_name(cfg.get("llm_fallback_provider")
                           or cfg.get("provider_fallback")
                           or "ollama")
        if p1 not in out:
            out.append(p1)
    if p0 == "mirofish" and not str(cfg.get("mirofish_url", "")).strip():
        return ["ollama"] if "ollama" in out else out
    return out


def provider_name(name: object) -> str:
    val = str(name or "ollama").strip().lower()
    return "mirofish" if val == "mirofish" else "ollama"


def pick_model(cfg: dict, feature: str, model: str) -> str:
    if model:
        return model_norm(model)
    key = f"{feature}_model"
    if cfg.get(key):
        return model_norm(str(cfg[key]))
    if feature in {"chat", "iris", "home"} and cfg.get("fast_model"):
        return model_norm(str(cfg["fast_model"]))
    if cfg.get("model"):
        return model_norm(str(cfg["model"]))
    return "qwen3:1.7b"


def model_chain(cfg: dict, feature: str, model: str) -> list[str]:
    out = [pick_model(cfg, feature, model)]
    fb = cfg.get(f"{feature}_fallback_model") or cfg.get("fallback_model")
    if fb:
        sval = model_norm(str(fb))
        if sval and sval not in out:
            out.append(sval)
    for key in ("fast_model", "model"):
        val = model_norm(str(cfg.get(key, "")))
        if val and val not in out:
            out.append(val)
    return out[:4]


def pick_think(cfg: dict, feature: str, model: str) -> bool | None:
    raw = cfg.get(f"{feature}_think")
    if raw is None:
        raw = cfg.get("llm_think")
    if raw is None:
        lower = model.lower()
        if "qwen3" in lower or "phi4" in lower:
            return False
        return None
    if isinstance(raw, bool):
        return raw
    txt = str(raw).strip().lower()
    if txt in {"1", "true", "yes", "on"}:
        return True
    if txt in {"0", "false", "no", "off"}:
        return False
    return None


def options(cfg: dict, feature: str, temp: float, num_ctx: int | None = None,
            model: str = "") -> dict:
    small = small_model(model)
    if num_ctx is None:
        nctx = int(cfg.get(f"{feature}_num_ctx", cfg.get("num_ctx", 4096)))
    else:
        nctx = int(num_ctx)
    if num_ctx is None and small:
        nctx = min(nctx, small_ctx(cfg, feature))
    out = {"temperature": float(temp), "num_ctx": max(256, nctx)}
    top_p = _opt_float(cfg, feature, "top_p", 0.9 if small else 0.95)
    if top_p > 0:
        out["top_p"] = clamp(top_p, 0.05, 1.0)
    top_k = _opt_int(cfg, feature, "top_k", 32 if small else 40)
    if top_k > 0:
        out["top_k"] = max(1, top_k)
    rep = _opt_float(cfg, feature, "repeat_penalty", 1.12 if small else 1.08)
    if rep > 0:
        out["repeat_penalty"] = clamp(rep, 0.5, 2.0)
    max_tok = cfg.get(f"{feature}_max_tokens", cfg.get("max_tokens", 0))
    try:
        num_predict = int(max_tok or 0)
    except Exception:
        num_predict = 0
    if num_predict <= 0 and small:
        num_predict = small_tokens(cfg, feature)
    if num_predict > 0:
        out["num_predict"] = max(32, num_predict)
    return out


def small_model(model: str) -> bool:
    raw = model_norm(model).lower()
    if not raw:
        return False
    if "mini" in raw:
        return True
    return any(tag in raw for tag in ("1.5b", "1.7b", "2b", "3b", "4b"))


def small_ctx(cfg: dict, feature: str) -> int:
    val = _opt_int(cfg, feature, "small_model_num_ctx",
                   int(cfg.get("small_model_num_ctx", 3072)))
    return max(512, val)


def small_tokens(cfg: dict, feature: str) -> int:
    val = _opt_int(cfg, feature, "small_model_max_tokens",
                   int(cfg.get("small_model_max_tokens", 384)))
    return max(64, val)


def _opt_float(cfg: dict, feature: str, key: str, default: float) -> float:
    val = cfg.get(f"{feature}_{key}", cfg.get(key, default))
    try:
        return float(val)
    except Exception:
        return float(default)


def _opt_int(cfg: dict, feature: str, key: str, default: int) -> int:
    val = cfg.get(f"{feature}_{key}", cfg.get(key, default))
    try:
        return int(val)
    except Exception:
        return int(default)


def clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def timeout_sec(cfg: dict, feature: str, timeout: int | None) -> int:
    if timeout is not None:
        return max(2, int(timeout))
    raw = cfg.get(f"{feature}_timeout_sec", cfg.get("llm_timeout_sec", 120))
    return max(2, int(raw))


def ollama_json(cfg: dict, prompt: str, model: str, think: bool | None,
                opts: dict, tm: int, schema: dict | None = None) -> dict:
    raw = ollama_call(
        cfg,
        payload_json(cfg, prompt, model, think, opts, schema),
        tm,
    )
    return parse(answer(raw))


def ollama_text(cfg: dict, prompt: str, model: str, think: bool | None,
                opts: dict, tm: int) -> str:
    raw = ollama_call(cfg, payload_text(cfg, prompt, model, think, opts), tm)
    return answer(raw)


def ollama_chat(cfg: dict, messages: list[dict], model: str,
                think: bool | None, opts: dict, tm: int,
                tools: list[dict] | None = None,
                fmt: dict | str | None = None) -> dict:
    raw = ollama_chat_call(cfg, payload_chat(messages, model, think, opts,
                         tools, fmt), tm)
    return raw if isinstance(raw, dict) else {}


def ollama_stream(cfg: dict, messages: list[dict], model: str,
                  think: bool | None, opts: dict,
                  tm: int) -> Generator[dict, None, None]:
    data: dict = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": opts,
    }
    if think is not None:
        data["think"] = bool(think)
    tries, base = stream_retry(cfg)
    err = None
    for idx in range(tries):
        seen = False
        req = urllib.request.Request(
            chat_url(cfg),
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=tm) as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line:
                        continue
                    seen = True
                    yield json.loads(line.decode("utf-8"))
            return
        except Exception as exc:
            err = exc
            if seen or idx + 1 >= tries:
                break
            sleep_s = base * (2 ** idx) + random.random() * 0.08
            time.sleep(sleep_s)
    if err:
        raise err
    raise RuntimeError("ollama_stream_failed")


def ollama_call(cfg: dict, body: bytes, tm: int) -> dict:
    req = urllib.request.Request(url(cfg), data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=tm) as fh:
        return json.loads(fh.read().decode())


def ollama_chat_call(cfg: dict, body: bytes, tm: int) -> dict:
    req = urllib.request.Request(chat_url(cfg), data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=tm) as fh:
        return json.loads(fh.read().decode())


def payload_json(cfg: dict, prompt: str, model: str, think: bool | None,
                 opts: dict, schema: dict | None = None) -> bytes:
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": schema if isinstance(schema, dict) else "json",
        "keep_alive": cfg.get("keep_alive", "30s"),
        "options": opts,
    }
    if think is not None:
        data["think"] = bool(think)
    return json.dumps(data).encode()


def payload_text(cfg: dict, prompt: str, model: str, think: bool | None,
                 opts: dict) -> bytes:
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": cfg.get("keep_alive", "30s"),
        "options": opts,
    }
    if think is not None:
        data["think"] = bool(think)
    return json.dumps(data).encode()


def payload_chat(messages: list[dict], model: str, think: bool | None,
                 opts: dict, tools: list[dict] | None = None,
                 fmt: dict | str | None = None) -> bytes:
    data: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": opts,
    }
    if think is not None:
        data["think"] = bool(think)
    if isinstance(tools, list) and tools:
        data["tools"] = tools
    if fmt:
        data["format"] = fmt
    return json.dumps(data).encode()


def chat_prompt(messages: list[dict]) -> str:
    rows = []
    for row in messages[-10:]:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role", "")).strip() or "user"
        txt = str(row.get("content", "")).strip()
        if txt:
            rows.append(f"{role}: {txt}")
    return "\n".join(rows)


def url(cfg: dict) -> str:
    return str(cfg.get("ollama_url", "http://127.0.0.1:11434")).rstrip("/") \
        + "/api/generate"


def chat_url(cfg: dict) -> str:
    return str(cfg.get("ollama_url", "http://127.0.0.1:11434")).rstrip("/") \
        + "/api/chat"


def chat_msg(raw: object) -> dict:
    if not isinstance(raw, dict):
        return {}
    msg = raw.get("message")
    if isinstance(msg, dict):
        return msg
    if isinstance(raw.get("choices"), list) and raw["choices"]:
        row = raw["choices"][0]
        if isinstance(row, dict) and isinstance(row.get("message"), dict):
            return row["message"]
    return {}


def answer(raw: dict) -> str:
    vals = [raw.get("response"), raw.get("thinking"), raw.get("output"),
            raw.get("content"), raw.get("text")]
    for val in vals:
        if isinstance(val, str) and val.strip():
            return val.strip()
    if isinstance(raw.get("message"), dict):
        msg = raw["message"].get("content") or raw["message"].get("text")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
    if isinstance(raw.get("choices"), list) and raw["choices"]:
        msg = raw["choices"][0].get("message", {})
        txt = msg.get("content") if isinstance(msg, dict) else ""
        if isinstance(txt, str) and txt.strip():
            return txt.strip()
    return "{}"


def parse(txt: str) -> dict:
    err = None
    for raw in parse_candidates(txt):
        try:
            out = json.loads(raw)
        except json.JSONDecodeError as exc:
            err = exc
            continue
        if isinstance(out, dict):
            return out
        err = RuntimeError("bad model json: root_not_object")
    if err:
        raise RuntimeError(str(err)) from err
    raise RuntimeError("bad model json: empty")


def parse_candidates(txt: str) -> list[str]:
    raw = str(txt or "").strip()
    vals = [raw, json_text(raw), strip_fence(raw), trail_fix(raw)]
    vals.append(trail_fix(json_text(raw)))
    vals.append(trail_fix(strip_fence(raw)))
    vals.append(key_quote(raw))
    vals.append(key_quote(strip_fence(raw)))
    vals.append(single_quote(raw))
    vals.append(single_quote(key_quote(raw)))
    vals.append(trail_fix(single_quote(key_quote(raw))))
    pairs = kv_json(raw)
    if pairs:
        vals.append(pairs)
    out: list[str] = []
    for val in vals:
        if val and val not in out:
            out.append(val)
    return out


def key_quote(txt: str) -> str:
    raw = str(txt or "").strip()
    pat = r'([{\s,])([A-Za-z_][A-Za-z0-9_-]{0,63})\s*:'
    return re.sub(pat, r'\1"\2":', raw)


def single_quote(txt: str) -> str:
    raw = str(txt or "").strip()
    if raw.count("'") < 2:
        return raw
    return raw.replace("'", "\"")


def kv_json(txt: str) -> str:
    out = {}
    for line in str(txt or "").splitlines()[:24]:
        row = line.strip().strip(",")
        if ":" not in row:
            continue
        key, val = row.split(":", 1)
        key = key.strip().strip("-*").strip("\"'")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", key):
            continue
        sval = val.strip().strip(",").strip("\"'")
        if not sval:
            continue
        out[key] = sval
    return json.dumps(out) if out else ""


def json_text(txt: str) -> str:
    raw = strip_fence(str(txt or "").strip())
    if raw.startswith("{"):
        return raw
    out = json_slice(raw)
    return out if out else raw


def strip_fence(txt: str) -> str:
    raw = str(txt or "").strip()
    if not raw.startswith("```"):
        return raw
    rows = [line for line in raw.splitlines() if line.strip() != "```"]
    if rows and rows[0].startswith("```"):
        rows = rows[1:]
    return "\n".join(rows).strip()


def trail_fix(txt: str) -> str:
    raw = str(txt or "").strip()
    if not raw:
        return raw
    return re.sub(r",\s*([}\]])", r"\1", raw)


def json_slice(txt: str) -> str:
    raw = str(txt or "")
    start = raw.find("{")
    if start < 0:
        return ""
    dep = 0
    esc = False
    ins = False
    for idx, ch in enumerate(raw[start:], start):
        if ins:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == "\"":
                ins = False
            continue
        if ch == "\"":
            ins = True
            continue
        if ch == "{":
            dep += 1
            continue
        if ch == "}":
            dep -= 1
            if dep == 0:
                return raw[start:idx + 1]
    return ""


def stream_retry(cfg: dict) -> tuple[int, float]:
    retry = cfg.get("retry", {})
    tries = int(cfg.get("stream_retry_attempts",
                   retry.get("attempts", 2)) or 2)
    base = float(cfg.get("stream_retry_base_sec",
                   retry.get("base_sec", 0.3)) or 0.3)
    return max(1, tries), max(0.05, base)


def model_norm(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""
    key = raw.lower().replace(" ", "").replace("_", "-")
    alias = {
        "phi-4": "phi4",
        "phi4": "phi4",
        "phi-4-mini": "phi4-mini",
        "phi4-mini": "phi4-mini",
        "phi-4-mini-instruct": "phi4-mini",
        "phi4-mini-instruct": "phi4-mini",
        "phi-4-reasoning": "phi4-reasoning",
        "phi4-reasoning": "phi4-reasoning",
        "phi-4-mini-reasoning": "phi4-mini-reasoning",
        "phi4-mini-reasoning": "phi4-mini-reasoning",
    }
    if key in alias:
        return alias[key]
    return raw


def prompt(cluster: str, rows: list[dict], cfg: dict) -> str:
    ctx = "\n".join(item_line(r) for r in rows)
    cats = ", ".join(cfg["categories"])
    return PROMPT.format(cluster=cluster, cats=cats, ctx=ctx)


def item_line(rec: dict) -> str:
    txt = rec.get("text", "").replace("\n", " ")
    return f"id={rec['id']} path={rec['path']} text={txt[:900]}"


PROMPT = """
You name and organize a personal filesystem from contextual evidence.
Use nearby unrelated documents as evidence when they share entities, tasks,
dates, projects, people, screenshots, notes, or invoices.

Return strict JSON:
{{
  "title": "short semantic cluster name",
  "folder": "relative destination folder under one listed category",
  "reason": "one sentence evidence-based reason",
  "items": [
    {{"id": "item id", "name": "semantic file or folder name"}}
  ]
}}

Rules:
- folder must be relative and start with one of: {cats}
- names must be concise, stable, and filesystem safe
- do not invent entities not supported by the context
- preserve useful extensions in item names
- if evidence is weak, put the cluster under Temporary/NeedsReview

cluster={cluster}
context:
{ctx}
""".strip()
