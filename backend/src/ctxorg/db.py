from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def open_db(cfg: dict) -> sqlite3.Connection:
    path = Path(cfg["state_dir"]) / "ctx.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init(conn)
    return conn


def init(conn: sqlite3.Connection) -> None:
    for sql in schema():
        conn.execute(sql)
    conn.commit()


def schema() -> list[str]:
    return [ITEMS, LINKS, PLANS, METRICS, DEAD, ENTITY_PROFILES]


ITEMS = """
CREATE TABLE IF NOT EXISTS items(
  id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  kind TEXT NOT NULL,
  size INTEGER NOT NULL,
  mtime REAL NOT NULL,
  ext TEXT NOT NULL,
  state TEXT NOT NULL,
  text TEXT NOT NULL DEFAULT '',
  sig TEXT NOT NULL DEFAULT '',
  cluster TEXT NOT NULL DEFAULT '',
  err TEXT NOT NULL DEFAULT ''
)"""

LINKS = """
CREATE TABLE IF NOT EXISTS links(
  run TEXT NOT NULL,
  a TEXT NOT NULL,
  b TEXT NOT NULL,
  score REAL NOT NULL,
  why TEXT NOT NULL,
  PRIMARY KEY(run, a, b)
)"""

PLANS = """
CREATE TABLE IF NOT EXISTS plans(
  run TEXT NOT NULL,
  id TEXT NOT NULL,
  src TEXT NOT NULL,
  dst TEXT NOT NULL,
  state TEXT NOT NULL,
  why TEXT NOT NULL,
  err TEXT NOT NULL DEFAULT '',
  cluster TEXT NOT NULL,
  PRIMARY KEY(run, id)
)"""

METRICS = """
CREATE TABLE IF NOT EXISTS metrics(
  key TEXT PRIMARY KEY,
  val INTEGER NOT NULL
)"""

DEAD = """
CREATE TABLE IF NOT EXISTS dead(
  run TEXT NOT NULL,
  id TEXT NOT NULL,
  path TEXT NOT NULL,
  err TEXT NOT NULL,
  ts REAL NOT NULL
)"""

ENTITY_PROFILES = """
CREATE TABLE IF NOT EXISTS entity_profiles(
  item_id TEXT PRIMARY KEY,
  profile_json TEXT NOT NULL,
  generated_at REAL NOT NULL
)"""


def get_entity_profile(conn: sqlite3.Connection, item_id: str) -> dict | None:
    row = conn.execute(
        "SELECT profile_json FROM entity_profiles WHERE item_id=?", (item_id,)
    ).fetchone()
    if row is None:
        return None
    try:
        import json as _json
        return _json.loads(row[0] if not hasattr(row, "keys") else row["profile_json"])
    except Exception:
        return None


def set_entity_profile(conn: sqlite3.Connection, item_id: str, profile_json: str) -> None:
    import time as _time
    conn.execute(
        "INSERT OR REPLACE INTO entity_profiles(item_id, profile_json, generated_at) VALUES(?,?,?)",
        (item_id, profile_json, _time.time()),
    )
    conn.commit()


def up_item(conn: sqlite3.Connection, rec: dict) -> None:
    sql = """
    INSERT INTO items(id,path,kind,size,mtime,ext,state)
    VALUES(:id,:path,:kind,:size,:mtime,:ext,:state)
    ON CONFLICT(id) DO UPDATE SET
    path=:path,kind=:kind,size=:size,mtime=:mtime,ext=:ext
    """
    conn.execute(sql, rec)


def rows(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def set_item(conn: sqlite3.Connection, iid: str, **vals: object) -> None:
    pairs = ", ".join(f"{k}=?" for k in vals)
    conn.execute(f"UPDATE items SET {pairs} WHERE id=?", (*vals.values(), iid))


def items(conn: sqlite3.Connection) -> list[dict]:
    return rows(conn, "SELECT * FROM items ORDER BY path")


def item_map(conn: sqlite3.Connection) -> dict[str, dict]:
    return {r["id"]: r for r in items(conn)}


def inc(conn: sqlite3.Connection, key: str, val: int = 1) -> None:
    conn.execute("INSERT OR IGNORE INTO metrics(key,val) VALUES(?,0)", (key,))
    conn.execute("UPDATE metrics SET val=val+? WHERE key=?", (val, key))


def metric_rows(conn: sqlite3.Connection) -> dict[str, int]:
    data = rows(conn, "SELECT key,val FROM metrics")
    return {r["key"]: int(r["val"]) for r in data}


def add_link(conn: sqlite3.Connection, run: str, rec: dict) -> None:
    sql = "INSERT OR REPLACE INTO links(run,a,b,score,why) VALUES(?,?,?,?,?)"
    conn.execute(sql, (run, rec["a"], rec["b"], rec["score"], rec["why"]))


def add_plan(conn: sqlite3.Connection, run: str, rec: dict) -> None:
    sql = """
    INSERT OR REPLACE INTO plans(run,id,src,dst,state,why,cluster)
    VALUES(?,?,?,?,?,?,?)
    """
    args = (run, rec["id"], rec["src"], rec["dst"], rec["state"],
            rec["why"], rec["cluster"])
    conn.execute(sql, args)


def plan_rows(conn: sqlite3.Connection, run: str) -> list[dict]:
    return rows(conn, "SELECT * FROM plans WHERE run=? ORDER BY dst", (run,))


def json_dump(path: Path, rows_: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in rows_:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")

