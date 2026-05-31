from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Generator


def gen_json(cfg: dict, prompt: str, model: str, feature: str,
             timeout: int, opts: dict) -> dict:
    data = {
        field(cfg, "model"): model,
        field(cfg, "prompt"): prompt,
        field(cfg, "feature"): feature,
        field(cfg, "stream"): False,
        field(cfg, "options"): opts,
    }
    raw = post_retry(cfg, gen_path(cfg), data, timeout)
    return strict_json(raw)


def gen_text(cfg: dict, prompt: str, model: str, feature: str,
             timeout: int, opts: dict) -> str:
    data = {
        field(cfg, "model"): model,
        field(cfg, "prompt"): prompt,
        field(cfg, "feature"): feature,
        field(cfg, "stream"): False,
        field(cfg, "options"): opts,
    }
    raw = post_retry(cfg, gen_path(cfg), data, timeout)
    return text(raw)


def stream_chat(cfg: dict, messages: list[dict], model: str, feature: str,
                timeout: int, opts: dict) -> Generator[dict, None, None]:
    data = {
        field(cfg, "model"): model,
        field(cfg, "messages"): messages,
        field(cfg, "feature"): feature,
        field(cfg, "stream"): True,
        field(cfg, "options"): opts,
    }
    tries, base = retry_cfg(cfg)
    last: Exception | None = None
    for idx in range(tries):
        seen = False
        try:
            for row in stream_once(cfg, chat_path(cfg), data, timeout):
                seen = True
                yield row
            return
        except Exception as exc:
            if seen:
                raise
            last = exc
            if idx + 1 >= tries:
                break
            time.sleep(base * (2 ** idx))
    raise RuntimeError(f"mirofish_stream_failed: {last}") from last


def stream_once(cfg: dict, path: str, data: dict,
                timeout: int) -> Generator[dict, None, None]:
    req = request(cfg, path, data)
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        for raw in fh:
            row = parse_line(raw)
            if row is None:
                continue
            yield norm_chunk(row)


def parse_line(raw: bytes) -> dict | None:
    line = raw.strip()
    if not line:
        return None
    if line.startswith(b"data:"):
        line = line[5:].strip()
    if line in {b"[DONE]", b"done"}:
        return {"done": True}
    return json.loads(line.decode("utf-8"))


def norm_chunk(row: dict) -> dict:
    if row.get("done"):
        return {"done": True}
    msg = row.get("message") if isinstance(row.get("message"), dict) else {}
    tok = msg.get("content") or row.get("delta") or row.get("token")
    tok = tok or row.get("content") or row.get("text") or ""
    out = {"message": {"content": str(tok)}}
    if row.get("done") or row.get("finish_reason"):
        out["done"] = True
    if "eval_count" in row:
        out["eval_count"] = int(row.get("eval_count") or 0)
    if "prompt_eval_count" in row:
        out["prompt_eval_count"] = int(row.get("prompt_eval_count") or 0)
    return out


def post_retry(cfg: dict, path: str, data: dict, timeout: int) -> dict:
    tries, base = retry_cfg(cfg)
    last: Exception | None = None
    for idx in range(tries):
        try:
            return post(cfg, path, data, timeout)
        except Exception as exc:
            last = exc
            if idx + 1 >= tries:
                break
            time.sleep(base * (2 ** idx))
    raise RuntimeError(f"mirofish_request_failed: {last}") from last


def post(cfg: dict, path: str, data: dict, timeout: int) -> dict:
    req = request(cfg, path, data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            body = fh.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"http_{exc.code}:{body[:180]}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"bad_mirofish_json: {exc}") from exc


def request(cfg: dict, path: str, data: dict) -> urllib.request.Request:
    raw = json.dumps(data).encode("utf-8")
    return urllib.request.Request(url(cfg, path), data=raw, headers=headers(cfg))


def headers(cfg: dict) -> dict[str, str]:
    out = {"Content-Type": "application/json"}
    key = api_key(cfg)
    if key:
        pref = str(cfg.get("mirofish_auth_prefix", "Bearer")).strip() or "Bearer"
        hdr = str(cfg.get("mirofish_auth_header", "Authorization")).strip()
        out[hdr] = f"{pref} {key}"
    return out


def strict_json(raw: dict) -> dict:
    if isinstance(raw.get("json"), dict):
        return dict(raw["json"])
    if isinstance(raw.get("response_json"), dict):
        return dict(raw["response_json"])
    txt = text(raw)
    val = parse_json(txt)
    if not isinstance(val, dict):
        raise RuntimeError("mirofish_non_object_json")
    return val


def text(raw: dict) -> str:
    keys = ["response", "output", "content", "text", "message"]
    for key in keys:
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if key == "message" and isinstance(val, dict):
            out = val.get("content") or val.get("text")
            if isinstance(out, str) and out.strip():
                return out.strip()
    if isinstance(raw.get("data"), dict):
        return text(raw["data"])
    raise RuntimeError("mirofish_missing_text")


def parse_json(txt: str) -> object:
    raw = json_text(txt)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"bad_model_json: {exc}") from exc


def json_text(txt: str) -> str:
    raw = txt.strip()
    if raw.startswith("{") or raw.startswith("["):
        return raw
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return raw[start:end + 1]
    return raw


def url(cfg: dict, path: str) -> str:
    base = str(cfg.get("mirofish_url", "")).strip()
    if not base:
        raise RuntimeError("mirofish_url_missing")
    return base.rstrip("/") + path


def gen_path(cfg: dict) -> str:
    return str(cfg.get("mirofish_generate_path", "/v1/generate"))


def chat_path(cfg: dict) -> str:
    return str(cfg.get("mirofish_chat_path", "/v1/chat"))


def field(cfg: dict, name: str) -> str:
    raw_map = cfg.get("mirofish_field_map", "")
    if isinstance(raw_map, dict):
        val = raw_map.get(name)
        if isinstance(val, str) and val.strip():
            return val
    map_key = str(raw_map).strip()
    if map_key and not isinstance(raw_map, dict):
        try:
            val = json.loads(map_key).get(name)
            if isinstance(val, str) and val.strip():
                return val
        except Exception:
            pass
    flat_key = f"mirofish_field_{name}"
    val = cfg.get(flat_key)
    if isinstance(val, str) and val.strip():
        return val
    return name


def retry_cfg(cfg: dict) -> tuple[int, float]:
    base_retry = cfg.get("retry", {})
    tries = int(cfg.get("mirofish_retries", base_retry.get("attempts", 2)) or 2)
    base = float(cfg.get("mirofish_backoff_sec", base_retry.get("base_sec", 0.3)) or 0.3)
    return max(1, tries), max(0.05, base)


def api_key(cfg: dict) -> str:
    val = str(cfg.get("mirofish_api_key", "")).strip()
    return val
