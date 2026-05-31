from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import PurePath

from . import cfg as cfgmod
from . import db, terms

Pair = tuple[str, str, float]
PROJ_SKIP = {
    "app", "build", "dist", "lib", "node_modules", "packages", "src",
    "test", "tests", "vendor",
}


class Dsu:
    def __init__(self) -> None:
        self.p = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        if self.p[x] != x:
            self.p[x] = self.find(self.p[x])
        return self.p[x]

    def union(self, a: str, b: str) -> None:
        self.p[self.find(b)] = self.find(a)


def run(conn, cfg: dict, run_id: str) -> dict[str, list[dict]]:
    rows = scoped_rows(conn, cfg)
    data = build(rows, cfg)
    save_links(conn, run_id, data["links"])
    save_clusters(conn, data["clusters"])
    write_graph(cfg, run_id, data)
    return data["clusters"]


def scoped_rows(conn, cfg: dict) -> list[dict]:
    roots = src_roots(cfg)
    if not roots:
        return db.rows(conn, "SELECT * FROM items")
    expr = " OR ".join(["(path=? OR path LIKE ?)"] * len(roots))
    sql = f"SELECT * FROM items WHERE {expr}"
    args = []
    for root in roots:
        args.extend([root, root + "/%"])
    return db.rows(conn, sql, tuple(args))


def src_roots(cfg: dict) -> list[str]:
    out = []
    seen = set()
    for raw in cfg.get("sources", []):
        root = src_root(raw)
        if root and root not in seen:
            seen.add(root)
            out.append(root)
    return out


def src_root(raw: object) -> str:
    val = str(raw or "").strip()
    if not val:
        return ""
    if len(val) > 1:
        val = val.rstrip("/")
    return val or "/"


def build(rows: list[dict], cfg: dict) -> dict:
    vecs = {r["id"]: vector(r, dim(cfg)) for r in rows}
    links = links_for(rows, vecs, cfg)
    cl = clusters(rows, links)
    xy = project(vecs)
    return {"nodes": nodes(rows, cl, xy, vecs), "links": links,
            "clusters": cl}


def dim(cfg: dict) -> int:
    return max(8, int(cfg.get("latent_dim", 96)))


def vector(rec: dict, sz: int = 96) -> list[float]:
    vec = [0.0] * sz
    for tok, wt in features(rec):
        add(vec, tok, wt)
    return norm(vec)


def features(rec: dict) -> list[tuple[str, float]]:
    out = path_features(rec)
    out.extend(type_features(rec))
    out.extend((f"size:{size_bucket(rec)}", 1.0) for _ in [0])
    out.extend(date_features(rec))
    out.extend(text_features(rec))
    out.extend(code_features(rec))
    return out


def path_features(rec: dict) -> list[tuple[str, float]]:
    path = str(rec.get("path", ""))
    parts = [p for p in PurePath(path).parts if p not in ("/", "")]
    vals = [(f"path:{p.lower()}", 0.55) for p in parts[-10:]]
    vals.extend(folder_features(parts))
    vals.extend((f"name:{t}", 2.3) for t in terms.toks(PurePath(path).name))
    return vals


def folder_features(parts: list[str]) -> list[tuple[str, float]]:
    dirs = [p.lower() for p in parts[:-1]][-5:]
    vals = [(f"folder:{p}", 1.6) for p in dirs[-2:]]
    vals.extend((f"ancestor:{p}", 0.8) for p in dirs[:-2])
    return vals


def type_features(rec: dict) -> list[tuple[str, float]]:
    ext = str(rec.get("ext", "")).lower()
    typ = terms.ext_type(ext)
    return [(f"ext:{ext}", 1.1), (f"type:{typ}", 1.4)]


def date_features(rec: dict) -> list[tuple[str, float]]:
    day = mtime_day(rec)
    if day <= 0:
        return []
    dt = datetime.fromtimestamp(day * 86400, timezone.utc)
    return [(f"year:{dt:%Y}", 0.35), (f"month:{dt:%Y-%m}", 0.7),
            (f"week:{dt:%G-%V}", 0.9)]


def text_features(rec: dict) -> list[tuple[str, float]]:
    wt = 1.8 if terms.is_ocr(rec) else 1.45
    return [(f"text:{t}", wt * text_weight(n)) for t, n in text_terms(rec)]


def text_weight(n: int) -> float:
    return 1.0 + min(2.0, math.log2(max(1, n)))


def code_features(rec: dict) -> list[tuple[str, float]]:
    if not terms.is_code(rec):
        return []
    vals = [(f"code:{t}", 1.9) for t in code_terms(rec)]
    vals.extend((f"project:{t}", 1.35) for t in project_terms(rec))
    return vals


def code_terms(rec: dict) -> list[str]:
    path = PurePath(str(rec.get("path", "")))
    return sorted(terms.toks(" ".join(path.parts[-5:])))[:16]


def project_terms(rec: dict) -> list[str]:
    path = PurePath(str(rec.get("path", "")))
    parts = [p for p in path.parts if p not in ("/", "")]
    toks = terms.toks(" ".join(parts[-7:-1]))
    return sorted(t for t in toks if t not in PROJ_SKIP)[:12]


def text_terms(rec: dict) -> list[tuple[str, int]]:
    txt = str(rec.get("text", ""))[:12000]
    return terms.top_toks(txt, 512)


def size_bucket(rec: dict) -> str:
    val = max(0, int(rec.get("size", 0)))
    return str(int(math.log2(max(1, val))))


def mtime_bucket(rec: dict) -> str:
    return str(mtime_day(rec))


def mtime_day(rec: dict) -> int:
    val = max(0, int(float(rec.get("mtime", 0))))
    return val // 86400


def add(vec: list[float], tok: str, wt: float) -> None:
    idx, sign = slot(tok, len(vec))
    vec[idx] += sign * wt


def slot(tok: str, sz: int) -> tuple[int, int]:
    raw = hashlib.blake2b(tok.encode(), digest_size=8).digest()
    val = int.from_bytes(raw, "big")
    return val % sz, 1 if val & (1 << 63) else -1


def norm(vec: list[float]) -> list[float]:
    mag = math.sqrt(sum(v * v for v in vec))
    return [v / mag for v in vec] if mag else vec


def links_for(rows: list[dict], vecs: dict[str, list[float]],
              cfg: dict) -> list[dict]:
    pairs = candidate_pairs(rows, cfg)
    by_id = {r["id"]: r for r in rows}
    top = top_pairs(vecs, int(cfg.get("latent_k", 8)), pairs, by_id)
    lim = float(cfg.get("latent_min_score", cfg.get("link_min_score", 0.18)))
    return [link(a, b, s) for a, b, s in top if s >= lim]


def candidate_pairs(rows: list[dict], cfg: dict) -> set[tuple[str, str]]:
    cap = int(cfg.get("latent_bucket_cap", 96))
    buckets = defaultdict(list)
    for rec in rows:
        for key in bucket_keys(rec):
            if len(buckets[key]) < cap:
                buckets[key].append(rec["id"])
    return pairs_from(buckets)


def bucket_keys(rec: dict) -> list[str]:
    path = PurePath(str(rec.get("path", "")))
    typ = terms.ext_type(str(rec.get("ext", "")))
    keys = [f"ext:{rec.get('ext', '')}", f"type:{typ}",
            f"parent:{path.parent.name}", f"month:{month_bucket(rec)}"]
    keys.extend(f"name:{t}" for t in sorted(terms.toks(path.name))[:10])
    keys.extend(f"text:{t}" for t, _ in terms.top_toks(rec.get("text", ""), 16))
    keys.extend(code_bucket_keys(rec))
    return [k.lower() for k in keys if len(k) > 5]


def code_bucket_keys(rec: dict) -> list[str]:
    if not terms.is_code(rec):
        return []
    vals = [f"code:{t}" for t in code_terms(rec)[:8]]
    vals.extend(f"project:{t}" for t in project_terms(rec)[:6])
    return vals


def month_bucket(rec: dict) -> str:
    day = mtime_day(rec)
    if day <= 0:
        return "unknown"
    return datetime.fromtimestamp(day * 86400, timezone.utc).strftime("%Y-%m")


def pairs_from(buckets: dict) -> set[tuple[str, str]]:
    out = set()
    for ids in buckets.values():
        ids = sorted(set(ids))
        for idx, a in enumerate(ids):
            for b in ids[idx + 1:]:
                out.add((a, b))
    return out


def top_pairs(vecs: dict[str, list[float]], k: int,
              pairs: set[tuple[str, str]], rows: dict) -> list[Pair]:
    near = defaultdict(list)
    for a, b in sorted(pairs):
        if a in vecs and b in vecs:
            base = cosine(vecs[a], vecs[b])
            push(near, a, b, pair_score(rows[a], rows[b], base), k)
    return dedupe(near)


def pair_score(a: dict, b: dict, base: float) -> float:
    if base <= 0:
        return 0.0
    anchor = anchor_score(a, b)
    if anchor <= 0:
        return min(0.12, base * 0.35)
    ctx = min(0.35, context_score(a, b))
    return min(1.0, base * (0.68 + min(0.45, anchor + ctx)))


def anchor_score(a: dict, b: dict) -> float:
    vals = [folder_score(a, b), name_score(a, b), text_score(a, b)]
    vals.append(0.22 if code_adjacent(a, b) else 0.0)
    return min(0.7, sum(vals))


def context_score(a: dict, b: dict) -> float:
    month = month_bucket(a)
    val = 0.0
    val += 0.1 if terms.ext_type(a.get("ext", "")) == type_of(b) else 0.0
    val += 0.08 if month != "unknown" and month == month_bucket(b) else 0.0
    return val


def type_of(rec: dict) -> str:
    return terms.ext_type(str(rec.get("ext", "")))


def folder_score(a: dict, b: dict) -> float:
    ap = PurePath(str(a.get("path", "")))
    bp = PurePath(str(b.get("path", "")))
    if ap.parent == bp.parent:
        return 0.24
    return 0.12 if useful_parent(ap, bp) else 0.0


def useful_parent(ap: PurePath, bp: PurePath) -> bool:
    par = ap.parent.parent
    return par == bp.parent.parent and str(par) not in ("", ".", "/")


def name_score(a: dict, b: dict) -> float:
    at = terms.toks(PurePath(str(a.get("path", ""))).name)
    bt = terms.toks(PurePath(str(b.get("path", ""))).name)
    return min(0.3, 0.1 * len(at & bt))


def text_score(a: dict, b: dict) -> float:
    at = {t for t, _ in terms.top_toks(a.get("text", ""), 64)}
    bt = {t for t, _ in terms.top_toks(b.get("text", ""), 64)}
    return min(0.32, 0.035 * len(at & bt))


def code_adjacent(a: dict, b: dict) -> bool:
    if not (terms.is_code(a) and terms.is_code(b)):
        return False
    return len(set(project_terms(a)) & set(project_terms(b))) >= 2


def push(near: dict, a: str, b: str, score: float, k: int) -> None:
    if score <= 0:
        return
    near[a] = best([*near[a], (b, score)], k)
    near[b] = best([*near[b], (a, score)], k)


def best(rows: list[tuple[str, float]], k: int) -> list[tuple[str, float]]:
    return sorted(rows, key=lambda r: (-r[1], r[0]))[: max(1, k)]


def dedupe(near: dict) -> list[tuple[str, str, float]]:
    out = {}
    for a, rows in near.items():
        for b, score in rows:
            key = tuple(sorted((a, b)))
            out[key] = max(score, out.get(key, 0.0))
    return [(a, b, s) for (a, b), s in sorted(out.items())]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def link(a: str, b: str, score: float) -> dict:
    return {"a": a, "b": b, "score": round(score, 4), "why": "latent_nn"}


def clusters(rows: list[dict], links: list[dict]) -> dict[str, list[dict]]:
    dsu = Dsu()
    for rec in rows:
        dsu.find(rec["id"])
    for rec in links:
        dsu.union(rec["a"], rec["b"])
    return groups(rows, dsu)


def groups(rows: list[dict], dsu: Dsu) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for rec in rows:
        out[dsu.find(rec["id"])].append(rec)
    return dict(out)


def project(vecs: dict[str, list[float]]) -> dict[str, tuple[float, ...]]:
    axes = principal_axes(vecs, 4)
    vals = [scale(axis_values(vecs, axis)) for axis in axes]
    return {iid: tuple(round(vals[d][iid] * 320, 3) for d in range(4))
            for iid in vecs}


def principal_axes(vecs: dict[str, list[float]], n: int) -> list[list[float]]:
    axes: list[list[float]] = []
    for idx in range(n):
        axes.append(principal_axis(vecs, axes, idx))
    return axes


def principal_axis(vecs: dict[str, list[float]], prev: list, idx: int):
    axis_ = orth(seed_axis(dim_from(vecs), idx), prev)
    for _ in range(10):
        axis_ = orth(power(vecs, axis_), prev)
    return axis_


def dim_from(vecs: dict[str, list[float]]) -> int:
    return len(next(iter(vecs.values()))) if vecs else 4


def seed_axis(sz: int, idx: int) -> list[float]:
    vals = [rand_float(idx, pos) for pos in range(sz)]
    return norm(vals)


def rand_float(idx: int, pos: int) -> float:
    raw = hashlib.blake2b(f"pca:{idx}:{pos}".encode(), digest_size=2).digest()
    return int.from_bytes(raw, "big") / 32768 - 1


def power(vecs: dict[str, list[float]], axis_: list[float]) -> list[float]:
    out = [0.0] * len(axis_)
    for vec in vecs.values():
        add_scaled(out, vec, dot(vec, axis_))
    return out


def add_scaled(out: list[float], vec: list[float], wt: float) -> None:
    for idx, val in enumerate(vec):
        out[idx] += val * wt


def orth(axis_: list[float], prev: list[list[float]]) -> list[float]:
    out = axis_[:]
    for old in prev:
        add_scaled(out, old, -dot(out, old))
    return norm(out)


def axis_values(vecs: dict[str, list[float]], axis_: list[float]):
    return {iid: dot(vec, axis_) for iid, vec in vecs.items()}


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def scale(vals: dict[str, float]) -> dict[str, float]:
    if not vals:
        return {}
    mid = sum(vals.values()) / len(vals)
    span = max(1e-9, max(abs(v - mid) for v in vals.values()))
    return {k: (v - mid) / span for k, v in vals.items()}


def nodes(rows: list[dict], cl: dict, xy: dict, vecs: dict) -> list[dict]:
    cids = {r["id"]: cid for cid, rs in cl.items() for r in rs}
    return [node(r, cids, xy, vecs) for r in rows]


def node(rec: dict, cids: dict, xy: dict, vecs: dict) -> dict:
    coords = xy.get(rec["id"], (0.0, 0.0, 0.0, 0.0))
    x, y, z, w = coords
    return {"id": rec["id"], "path": rec["path"], "cluster": cids[rec["id"]],
            "x": x, "y": y, "z": z, "w": w,
            "latent": {"dim": len(vecs[rec["id"]]), "method": "pca4"}}


def save_links(conn, run_id: str, links: list[dict]) -> None:
    for rec in links:
        db.add_link(conn, run_id, rec)
    conn.commit()


def save_clusters(conn, cl: dict) -> None:
    for cid, rows in cl.items():
        for rec in rows:
            db.set_item(conn, rec["id"], cluster=cid)
    conn.commit()


def write_graph(cfg: dict, run_id: str, data: dict) -> None:
    out = {"nodes": data["nodes"], "links": data["links"]}
    path = cfgmod.state_dir(cfg, "graphs") / f"{run_id}.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
