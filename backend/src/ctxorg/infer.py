from __future__ import annotations

import json
import math
import re
import threading
import time
from pathlib import Path

from . import cfg as cfgmod
from . import db, ollama, retry, terms

_lock = threading.Lock()
_lite: dict[str, dict[str, dict]] = {}
_full: dict[tuple[str, str, str], dict] = {}
_warm: set[str] = set()
_met = {
    "infer_req": 0,
    "infer_hit": 0,
    "infer_miss": 0,
    "infer_fail": 0,
    "infer_fallback": 0,
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
LONG_NUM_RE = re.compile(r"\b\d{6,}\b")
TOKEN_RE = re.compile(r"\b(?:sk|pk|rk|tok|token|key)[-_A-Za-z0-9]{6,}\b",
                      re.IGNORECASE)
PHONE_RE = re.compile(r"\b\+?\d[\d\- ]{8,}\d\b")
RUN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")

PII_HINTS = {
    "passport", "ssn", "social", "routing", "iban", "swift", "tax",
    "invoice", "bank", "credit", "debit", "address", "dob", "license",
}

SEC_HINTS = {
    "access_token", "refresh_token", "private_key", "secret", "apikey",
    "api_key", "ssh", "pem", "credential", "password", "token",
}

LIFE_HINTS = {
    "health", "therapy", "medical", "legal", "court", "family", "kids",
    "mortgage", "debt", "layoff", "resume", "interview", "stress",
}


def warm_async(cfg: dict, run: str) -> None:
    run = _run_clean(run)
    if not run:
        return
    with _lock:
        if run in _warm:
            return
        _warm.add(run)
    th = threading.Thread(target=_warm_run, args=(cfg, run), daemon=True)
    th.start()


def _warm_run(cfg: dict, run: str) -> None:
    try:
        _precompute(cfg, run)
    except Exception:
        with _lock:
            _warm.discard(run)


def status() -> dict:
    with _lock:
        return dict(_met)


def get(cfg: dict, run: str, cluster: str, refresh: bool = False) -> dict:
    run = _run_clean(run)
    cluster = str(cluster or "").strip()
    if not run:
        raise RuntimeError("run_not_found")
    if not cluster:
        raise RuntimeError("cluster_not_found")
    t0 = time.time()
    _inc("infer_req")
    pre = _cluster_pack(cfg, run, cluster)
    key = (run, cluster, pre["sig"])
    if not refresh:
        hit = _cache_get(key)
        if hit:
            _inc("infer_hit")
            return _done(hit, "cache", t0)
    _inc("infer_miss")
    data = _build(cfg, pre)
    _cache_put(key, data)
    return _done(data, "fresh", t0)


def _done(data: dict, source: str, t0: float) -> dict:
    out = dict(data)
    out["source"] = source
    out["generated_at"] = int(time.time())
    out["stats"] = {
        "claim_count": len(out.get("claims", [])),
        "evidence_count": sum(len(c.get("evidence", []))
                              for c in out.get("claims", [])),
        "latency_ms": int((time.time() - t0) * 1000),
    }
    return out


def _build(cfg: dict, pre: dict) -> dict:
    claims = _claims(pre)
    model = cfg.get("infer_model") or cfg.get("model", "")
    try:
        claims = _deep(cfg, pre, claims)
    except Exception:
        _inc("infer_fallback")
        model = "fallback"
    return {
        "run": pre["run"],
        "cluster": pre["cluster"],
        "model": model,
        "claims": claims,
    }


def _deep(cfg: dict, pre: dict, claims: list[dict]) -> list[dict]:
    raw = retry.run(
        lambda: ollama.gen(cfg, _prompt(pre, claims), feature="infer"),
        llm_attempts(cfg),
        llm_base(cfg),
    )
    rows = raw.get("claims") or []
    by_id = {c["id"]: c for c in claims}
    for row in rows:
        iid = str(row.get("id") or "")
        txt = str(row.get("summary") or "").strip()
        if iid in by_id and txt:
            by_id[iid]["summary"] = txt[:280]
    return [by_id[k] for k in by_id]


def _prompt(pre: dict, claims: list[dict]) -> str:
    sig = json.dumps(pre["signals"], sort_keys=True)
    ev = []
    for row in pre["evidence"][:6]:
        ev.append(f"path={row['path']} score={row['score']} txt={row['snippet']}")
    cl = json.dumps([{"id": c["id"], "summary": c["summary"]}
                     for c in claims], sort_keys=True)
    return (
        "You are Iris. Rewrite claim summaries only. Keep evidence-grounded. "
        "No new facts. Return strict JSON: {\"claims\":[{\"id\":\"...\","
        "\"summary\":\"...\"}]}.\n"
        f"signals={sig}\nclaims={cl}\nevidence=\n" + "\n".join(ev)
    )


def _claims(pre: dict) -> list[dict]:
    sig = pre["signals"]
    out = []
    out.append(_behavior_claim(pre, sig))
    out.append(_project_claim(pre, sig))
    out.extend(_risk_claims(pre, sig))
    return out


def _behavior_claim(pre: dict, sig: dict) -> dict:
    sup = sig["doc_density"]
    rec = sig["recency"]
    con = sig["folder_focus"]
    crs = sig["cross_evidence"]
    conf = _score(sup, rec, con, crs)
    ev = _pick(pre, "behavior", 3)
    sum_ = "Routine activity appears concentrated in recurring contexts."
    return _claim("behavior-routine", "behavior", "routine", conf, sum_, ev)


def _project_claim(pre: dict, sig: dict) -> dict:
    sup = sig["code_mix"]
    rec = sig["recency"]
    con = sig["ext_focus"]
    crs = sig["cross_evidence"]
    conf = _score(sup, rec, con, crs)
    ev = _pick(pre, "projects", 3)
    sum_ = "Project momentum is visible via code and artifact co-movement."
    return _claim("projects-momentum", "projects", "momentum", conf, sum_, ev)


def _risk_claims(pre: dict, sig: dict) -> list[dict]:
    out = []
    out.append(_risk_one(pre, sig, "pii_financial", sig["pii_hits"]))
    out.append(_risk_one(pre, sig, "security_secrets", sig["sec_hits"]))
    out.append(_risk_one(pre, sig, "broad_life", sig["life_hits"]))
    return out


def _risk_one(pre: dict, sig: dict, cat: str, hit: float) -> dict:
    conf = _score(hit, sig["recency"], sig["folder_focus"], sig["cross_evidence"])
    sev = _sev(conf)
    ev = _pick(pre, "risk", 3)
    sum_ = f"Potential {cat.replace('_', ' ')} sensitivity detected in cluster."
    row = _claim(f"risk-{cat}", "risk", cat, conf, sum_, ev)
    row["severity"] = sev
    return row


def _claim(iid: str, fam: str, cat: str, conf: float,
           sum_: str, ev: list[dict]) -> dict:
    t = conf < 0.35
    out = {
        "id": iid,
        "family": fam,
        "category": cat,
        "title": _title(fam, cat, t),
        "summary": sum_[:280],
        "confidence": round(conf, 4),
        "tentative": t,
        "evidence": ev or [_empty_ev()],
    }
    return out


def _title(fam: str, cat: str, t: bool) -> str:
    base = f"{fam}: {cat}".replace("_", " ")
    return (base + " (tentative)") if t else base


def _empty_ev() -> dict:
    return {"id": "", "path": "", "snippet": "no direct snippet", "score": 0.0}


def _sev(conf: float) -> str:
    if conf < 0.35:
        return "low"
    if conf <= 0.7:
        return "med"
    return "high"


def llm_attempts(cfg: dict) -> int:
    data = cfg.get("retry", {})
    return max(1, int(data.get("attempts", 2) or 2))


def llm_base(cfg: dict) -> float:
    data = cfg.get("retry", {})
    return max(0.05, float(data.get("base_sec", 0.3) or 0.3))


def _score(sup: float, rec: float, con: float, crs: float) -> float:
    val = 0.35 * sup + 0.25 * rec + 0.2 * con + 0.2 * crs
    return max(0.0, min(1.0, val))


def _pick(pre: dict, fam: str, lim: int) -> list[dict]:
    rows = sorted(pre["evidence"], key=lambda r: -r.get("score", 0.0))
    return rows[:lim]


def _cluster_pack(cfg: dict, run: str, cluster: str) -> dict:
    pre = _precompute(cfg, run)
    row = pre.get(cluster)
    if row:
        return row
    raise RuntimeError("cluster_not_found")


def _precompute(cfg: dict, run: str) -> dict[str, dict]:
    with _lock:
        cur = _lite.get(run)
        if cur:
            return cur
    rows = _cluster_rows(cfg, run)
    out = {}
    for cid, vals in rows.items():
        out[cid] = _pre_one(run, cid, vals)
    with _lock:
        _lite[run] = out
        _warm.discard(run)
    return out


def _cluster_rows(cfg: dict, run: str) -> dict[str, list[dict]]:
    g = _graph(cfg, run)
    conn = db.open_db(cfg)
    out: dict[str, list[dict]] = {}
    for n in g.get("nodes", []):
        row = _item(conn, str(n.get("id") or ""), n)
        cid = str(row.get("cluster") or n.get("cluster") or "")
        if not cid:
            continue
        out.setdefault(cid, []).append(row)
    return out


def _graph(cfg: dict, run: str) -> dict:
    run = _run_clean(run)
    if not run:
        raise RuntimeError("run_not_found")
    path = cfgmod.state_dir(cfg, "graphs") / f"{run}.json"
    if not path.exists():
        raise RuntimeError("run_not_found")
    return json.loads(path.read_text(encoding="utf-8"))


def _run_clean(raw: object) -> str:
    val = str(raw or "").strip()
    if not val:
        return ""
    if RUN_RE.fullmatch(val):
        return val
    raise RuntimeError("run_not_found")


def _item(conn, iid: str, node: dict) -> dict:
    vals = db.rows(conn, "SELECT * FROM items WHERE id=?", (iid,))
    if vals:
        return vals[0]
    return {
        "id": iid,
        "path": str(node.get("path") or ""),
        "text": "",
        "size": 0,
        "mtime": 0,
        "ext": "",
    }


def _pre_one(run: str, cid: str, rows: list[dict]) -> dict:
    sig = _sig(rows)
    ev = _evidence(rows)
    return {
        "run": run,
        "cluster": cid,
        "sig": sig,
        "signals": _signals(rows),
        "evidence": ev,
    }


def _sig(rows: list[dict]) -> str:
    vals = [f"{r.get('id','')}:{int(float(r.get('mtime',0)))}" for r in rows]
    return str(abs(hash("|".join(sorted(vals)))))


def _signals(rows: list[dict]) -> dict:
    n = max(1, len(rows))
    dens = _doc_density(rows)
    rec = _recency(rows)
    ext = _ext_focus(rows)
    fld = _folder_focus(rows)
    crs = min(1.0, math.sqrt(n) / 6)
    code = _code_mix(rows)
    pii = _hit(rows, PII_HINTS)
    sec = _hit(rows, SEC_HINTS)
    life = _hit(rows, LIFE_HINTS)
    return {
        "doc_density": dens,
        "recency": rec,
        "ext_focus": ext,
        "folder_focus": fld,
        "cross_evidence": crs,
        "code_mix": code,
        "pii_hits": pii,
        "sec_hits": sec,
        "life_hits": life,
    }


def _doc_density(rows: list[dict]) -> float:
    words = []
    for r in rows:
        words.extend([t for t, _ in terms.top_toks(r.get("text", ""), 24)])
    uniq = len(set(words))
    return max(0.0, min(1.0, uniq / max(12.0, len(rows) * 10.0)))


def _recency(rows: list[dict]) -> float:
    now = time.time()
    vals = []
    for r in rows:
        age = max(0.0, (now - float(r.get("mtime", 0.0))) / 86400.0)
        vals.append(math.exp(-age / 45.0))
    return sum(vals) / max(1, len(vals))


def _ext_focus(rows: list[dict]) -> float:
    cnt: dict[str, int] = {}
    for r in rows:
        ext = str(r.get("ext") or "").lower() or "none"
        cnt[ext] = cnt.get(ext, 0) + 1
    top = max(cnt.values()) if cnt else 0
    return top / max(1, len(rows))


def _folder_focus(rows: list[dict]) -> float:
    cnt: dict[str, int] = {}
    for r in rows:
        par = str(Path(str(r.get("path", ""))).parent)
        cnt[par] = cnt.get(par, 0) + 1
    top = max(cnt.values()) if cnt else 0
    return top / max(1, len(rows))


def _code_mix(rows: list[dict]) -> float:
    hit = 0
    for r in rows:
        ext = str(r.get("ext") or "").lower()
        if terms.ext_type(ext) == "code":
            hit += 1
    return hit / max(1, len(rows))


def _hit(rows: list[dict], hints: set[str]) -> float:
    hit = 0
    for r in rows:
        txt = _text(r)
        if any(h in txt for h in hints):
            hit += 1
    return hit / max(1, len(rows))


def _text(row: dict) -> str:
    return f"{row.get('path','')} {row.get('text','')}".lower()


def _evidence(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        score = _ev_score(r)
        out.append({
            "id": str(r.get("id") or ""),
            "path": str(r.get("path") or ""),
            "snippet": _mask(str(r.get("text") or "")[:260]),
            "score": round(score, 4),
        })
    out.sort(key=lambda x: (-x["score"], x["path"]))
    return out


def _ev_score(row: dict) -> float:
    txt = _text(row)
    hit = 0.0
    hit += 0.22 if EMAIL_RE.search(txt) else 0.0
    hit += 0.22 if LONG_NUM_RE.search(txt) else 0.0
    hit += 0.28 if TOKEN_RE.search(txt) else 0.0
    hit += 0.18 if PHONE_RE.search(txt) else 0.0
    return max(0.05, min(1.0, hit + 0.12))


def _mask(txt: str) -> str:
    out = EMAIL_RE.sub("[email]", txt)
    out = PHONE_RE.sub("[phone]", out)
    out = LONG_NUM_RE.sub("[number]", out)
    out = TOKEN_RE.sub("[token]", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out[:260] or "(no text excerpt)"


def _inc(key: str) -> None:
    with _lock:
        _met[key] = int(_met.get(key, 0)) + 1


def _cache_get(key: tuple[str, str, str]) -> dict | None:
    with _lock:
        row = _full.get(key)
    return dict(row) if row else None


def _cache_put(key: tuple[str, str, str], data: dict) -> None:
    with _lock:
        _full[key] = dict(data)
        if len(_full) > 400:
            old = next(iter(_full.keys()))
            _full.pop(old, None)
