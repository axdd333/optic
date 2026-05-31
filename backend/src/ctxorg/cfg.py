from __future__ import annotations

import json
import os
from pathlib import Path


def load(path: str) -> dict:
    p = Path(path).expanduser()
    with p.open("r", encoding="utf-8") as fh:
        cfg = json.load(fh, object_pairs_hook=unique_obj)
    cfg["_cfg_path"] = str(p.resolve())
    return expand(cfg)


def expand(cfg: dict) -> dict:
    for key in ("home", "target", "state_dir"):
        cfg[key] = env_path(key, cfg[key])
    cfg["sources"] = [norm(p) for p in cfg["sources"]]
    cfg["protected"] = [norm(p) for p in cfg.get("protected", [])]

    cfg["model"] = env_str("MODEL", cfg.get("model", ""))
    cfg["fast_model"] = env_str("FAST_MODEL", cfg.get("fast_model",
                              cfg["model"]))

    llm_cfg(cfg)
    rate_cfg(cfg)
    return cfg


def rate_cfg(cfg: dict) -> None:
    defaults = {
        "rate_api_per_min": 480,
        "rate_chat_per_min": 40,
        "rate_iris_per_min": 50,
        "rate_scan_per_min": 8,
        "rate_signup_per_min": 24,
        "rate_jobs_per_min": 50,
        "rate_secrets_per_min": 20,
        "rate_ops_per_min": 18,
        "rate_heavy_per_min": 90,
    }
    for key, dflt in defaults.items():
        cfg[key] = env_int(key.upper(), cfg.get(key, dflt))


def llm_cfg(cfg: dict) -> None:
    base = cfg.get("provider_mode", cfg.get("provider", "ollama"))
    cfg["provider_mode"] = env_multi(
        ["CTXORG_PROVIDER_MODE", "CTXORG_PROVIDER"],
        str(base),
    )
    cfg["provider_fallback_ollama"] = env_bool(
        "PROVIDER_FALLBACK_OLLAMA",
        cfg.get("provider_fallback_ollama", True),
    )
    cfg["provider"] = cfg["provider_mode"]

    for feat in ("chat", "infer", "workstreams", "home", "iris",
                 "planner", "deep", "docedit", "identity"):
        p_key = f"{feat}_provider"
        m_key = f"{feat}_model"
        f_key = f"{feat}_fallback_model"
        t_key = f"{feat}_think"
        c_key = f"{feat}_num_ctx"
        s_key = f"{feat}_timeout_sec"
        cfg[p_key] = env_str(p_key.upper(), str(cfg.get(p_key, "")))
        cfg[m_key] = env_str(m_key.upper(), str(cfg.get(m_key, "")))
        cfg[f_key] = env_str(f_key.upper(), str(cfg.get(f_key, "")))
        cfg[t_key] = env_str(t_key.upper(), str(cfg.get(t_key, "")))
        cfg[c_key] = env_int(c_key.upper(), cfg.get(c_key, cfg.get("num_ctx", 4096)))
        cfg[s_key] = env_int(s_key.upper(), cfg.get(s_key, cfg.get("llm_timeout_sec", 120)))

    cfg["llm_profile"] = env_str("LLM_PROFILE",
                                 str(cfg.get("llm_profile", "phi4")))
    cfg["phi4_fast_model"] = env_str(
        "PHI4_FAST_MODEL",
        str(cfg.get("phi4_fast_model", "phi4-mini")),
    )
    cfg["phi4_deep_model"] = env_str(
        "PHI4_DEEP_MODEL",
        str(cfg.get("phi4_deep_model", "phi4-mini-reasoning")),
    )
    cfg["small_model_num_ctx"] = env_int(
        "SMALL_MODEL_NUM_CTX",
        cfg.get("small_model_num_ctx", 3072),
    )
    cfg["small_model_max_tokens"] = env_int(
        "SMALL_MODEL_MAX_TOKENS",
        cfg.get("small_model_max_tokens", 384),
    )
    cfg["chat_fallback_num_ctx"] = env_int(
        "CHAT_FALLBACK_NUM_CTX",
        cfg.get("chat_fallback_num_ctx", 3072),
    )
    cfg["chat_fallback_temp"] = env_float(
        "CHAT_FALLBACK_TEMP",
        cfg.get("chat_fallback_temp", 0.12),
    )
    cfg["chat_trace"] = env_bool(
        "CHAT_TRACE",
        cfg.get("chat_trace", True),
    )
    llm_defaults(cfg)

    cfg["mirofish_url"] = env_multi(
        ["CTXORG_MIROFISH_URL", "MIROFISH_URL"],
        str(cfg.get("mirofish_url", "")),
    )
    cfg["mirofish_api_key"] = env_multi(
        ["CTXORG_MIROFISH_API_KEY", "MIROFISH_API_KEY"],
        str(cfg.get("mirofish_api_key", "")),
    )
    cfg["mirofish_generate_path"] = env_str(
        "MIROFISH_GENERATE_PATH",
        str(cfg.get("mirofish_generate_path", "/v1/generate")),
    )
    cfg["mirofish_chat_path"] = env_str(
        "MIROFISH_CHAT_PATH",
        str(cfg.get("mirofish_chat_path", "/v1/chat")),
    )
    cfg["mirofish_auth_header"] = env_str(
        "MIROFISH_AUTH_HEADER",
        str(cfg.get("mirofish_auth_header", "Authorization")),
    )
    cfg["mirofish_auth_prefix"] = env_str(
        "MIROFISH_AUTH_PREFIX",
        str(cfg.get("mirofish_auth_prefix", "Bearer")),
    )
    cfg["mirofish_retries"] = env_int(
        "MIROFISH_RETRIES",
        cfg.get("mirofish_retries", cfg.get("retry", {}).get("attempts", 2)),
    )
    cfg["mirofish_backoff_sec"] = env_float(
        "MIROFISH_BACKOFF_SEC",
        cfg.get("mirofish_backoff_sec", cfg.get("retry", {}).get("base_sec", 0.3)),
    )
    cfg["mirofish_field_map"] = env_multi(
        ["CTXORG_MIROFISH_FIELD_MAP", "MIROFISH_FIELD_MAP"],
        cfg.get("mirofish_field_map", {}),
    )
    cfg["llm_think"] = env_str("LLM_THINK", str(cfg.get("llm_think", "")))
    cfg["fallback_model"] = env_str("FALLBACK_MODEL",
                                    str(cfg.get("fallback_model", "")))


def llm_defaults(cfg: dict) -> None:
    if str(cfg.get("llm_profile", "")).strip().lower() != "phi4":
        return
    fast = str(cfg.get("phi4_fast_model", "phi4-mini")).strip()
    deep = str(cfg.get("phi4_deep_model", "phi4-mini-reasoning")).strip()
    if not str(cfg.get("model", "")).strip():
        cfg["model"] = fast
    if not str(cfg.get("fast_model", "")).strip():
        cfg["fast_model"] = fast
    deep_feats = {"infer", "workstreams", "planner", "deep",
                  "docedit", "identity"}
    for feat in ("chat", "infer", "workstreams", "home", "iris",
                 "planner", "deep", "docedit", "identity"):
        m_key = f"{feat}_model"
        f_key = f"{feat}_fallback_model"
        if not str(cfg.get(m_key, "")).strip():
            cfg[m_key] = deep if feat in deep_feats else fast
        if not str(cfg.get(f_key, "")).strip():
            cfg[f_key] = str(cfg.get("fast_model") or cfg.get("model") or "")


def unique_obj(pairs: list[tuple[str, object]]) -> dict:
    out: dict = {}
    dup: list[str] = []
    for key, val in pairs:
        if key in out:
            dup.append(key)
        out[key] = val
    if dup:
        uniq = ", ".join(sorted(set(dup))[:10])
        raise ValueError(f"duplicate_config_keys: {uniq}")
    return out


def env_path(key: str, val: str) -> str:
    raw = os.environ.get(f"CTXORG_{key.upper()}", val)
    return norm(raw)


def env_str(key: str, val: str) -> str:
    return str(os.environ.get(f"CTXORG_{key}", val)).strip()


def env_multi(keys: list[str], val):
    for key in keys:
        if key in os.environ:
            return os.environ[key].strip()
    return val


def env_bool(key: str, val: bool) -> bool:
    raw = os.environ.get(f"CTXORG_{key}")
    if raw is None:
        return bool(val)
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def env_int(key: str, val) -> int:
    raw = os.environ.get(f"CTXORG_{key}")
    if raw is None:
        return int(val)
    return int(raw)


def env_float(key: str, val) -> float:
    raw = os.environ.get(f"CTXORG_{key}")
    if raw is None:
        return float(val)
    return float(raw)


def norm(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def state_dir(cfg: dict, name: str = "") -> Path:
    base = Path(cfg["state_dir"])
    return base / name if name else base


def ensure(cfg: dict) -> None:
    names = [
        "extracts", "graphs", "plans", "applied", "dead", "atlas",
        "edits", "backups", "labels",
    ]
    for name in names:
        state_dir(cfg, name).mkdir(parents=True, exist_ok=True)


def retry(cfg: dict) -> tuple[int, float]:
    data = cfg.get("retry", {})
    return int(data.get("attempts", 3)), float(data.get("base_sec", 0.4))
