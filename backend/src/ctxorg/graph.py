from __future__ import annotations

import itertools
import json
from collections import defaultdict

from . import cfg as cfgmod
from . import db, terms


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
    rows = db.rows(conn, "SELECT * FROM items WHERE state='EXTRACTED'")
    sigs = {r["id"]: terms.sig(r) for r in rows}
    links = score_links(sigs, cfg)
    save_links(conn, run_id, links)
    clusters = cluster(rows, links, cfg)
    save_clusters(conn, clusters)
    write_graph(cfg, run_id, rows, links, clusters)
    return clusters


def score_links(sigs: dict[str, set[str]], cfg: dict) -> list[dict]:
    pairs = pair_scores(index(sigs, int(cfg["max_token_docs"])), sigs)
    lim = float(cfg["link_min_score"])
    return [link(a, b, s) for (a, b), s in pairs.items() if s >= lim]


def index(sigs: dict[str, set[str]], cap: int) -> dict[str, list[str]]:
    idx = defaultdict(list)
    for iid, toks in sigs.items():
        for tok in toks:
            if len(idx[tok]) < cap:
                idx[tok].append(iid)
    return idx


def pair_scores(idx: dict[str, list[str]], sigs: dict[str, set[str]]) -> dict:
    hits = defaultdict(int)
    for ids in idx.values():
        for a, b in itertools.combinations(sorted(ids), 2):
            hits[(a, b)] += 1
    return {k: score(k, v, sigs) for k, v in hits.items()}


def score(
    pair: tuple[str, str],
    inter: int,
    sigs: dict[str, set[str]],
) -> float:
    a, b = pair
    den = max(1, len(sigs[a] | sigs[b]))
    return inter / den


def link(a: str, b: str, score_: float) -> dict:
    return {"a": a, "b": b, "score": round(score_, 4), "why": "term_overlap"}


def save_links(conn, run_id: str, links: list[dict]) -> None:
    for rec in links:
        db.add_link(conn, run_id, rec)
    conn.commit()


def save_clusters(conn, clusters: dict) -> None:
    for cid, rows in clusters.items():
        for rec in rows:
            db.set_item(conn, rec["id"], cluster=cid)
    conn.commit()


def cluster(rows: list[dict], links: list[dict], cfg: dict) -> dict:
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


def write_graph(
    cfg: dict,
    run_id: str,
    rows: list,
    links: list,
    cl: dict,
) -> None:
    data = {"nodes": nodes(rows, cl), "links": links}
    path = cfgmod.state_dir(cfg, "graphs") / f"{run_id}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def nodes(rows: list[dict], cl: dict) -> list[dict]:
    cids = {r["id"]: cid for cid, rs in cl.items() for r in rs}
    return [{"id": r["id"], "path": r["path"], "cluster": cids[r["id"]]}
            for r in rows]
