"""Neural embeddings via nomic-embed-text (Ollama /api/embed)."""
from __future__ import annotations

import json
import struct
import urllib.request
from pathlib import Path

EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
_BATCH_SIZE = 20  # items per request to /api/embed


# ---------------------------------------------------------------------------
# Public API: single + batch embedding
# ---------------------------------------------------------------------------

def embed_text(text: str, cfg: dict) -> list[float] | None:
    """Get a 768-dim embedding for a text string. Returns None on failure."""
    results = embed_batch([text], cfg)
    return results[0] if results else None


def embed_batch(texts: list[str], cfg: dict) -> list[list[float] | None]:
    """Embed multiple texts in one HTTP call. Falls back item-by-item on error."""
    if not texts:
        return []
    try:
        return _batch_request(texts, cfg)
    except Exception:
        # Fall back to one-by-one so partial results are preserved
        out: list[list[float] | None] = []
        for t in texts:
            try:
                result = _batch_request([t], cfg)
                out.append(result[0] if result else None)
            except Exception:
                out.append(None)
        return out


def _batch_request(texts: list[str], cfg: dict) -> list[list[float] | None]:
    """POST to Ollama /api/embed and return one vector per input text."""
    ollama_url = cfg.get("ollama_url", "http://127.0.0.1:11434")
    url = ollama_url.rstrip("/") + "/api/embed"
    payload = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as fh:
        raw = json.loads(fh.read().decode())
    # Ollama returns {"embeddings": [[float, ...], ...]}
    embeddings = raw.get("embeddings") or []
    # Pad with None if fewer vectors than inputs were returned
    result: list[list[float] | None] = []
    for i, t in enumerate(texts):
        vec = embeddings[i] if i < len(embeddings) else None
        result.append(vec if vec else None)
    return result


# ---------------------------------------------------------------------------
# SQLite cache helpers
# ---------------------------------------------------------------------------

def ensure_embed_table(conn) -> None:
    """Create embeddings table if it doesn't exist."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS embeddings "
        "(id TEXT PRIMARY KEY, vec BLOB)"
    )
    conn.commit()


def get_cached(conn, item_id: str) -> list[float] | None:
    """Return cached embedding or None."""
    row = conn.execute(
        "SELECT vec FROM embeddings WHERE id=?", (item_id,)
    ).fetchone()
    if row is None:
        return None
    blob = row[0] if not hasattr(row, "keys") else row["vec"]
    if not blob:
        return None
    return load_embed(blob)


def store_embed(conn, item_id: str, vec: list[float]) -> None:
    """Store embedding as packed float32 blob."""
    blob = struct.pack(f"{len(vec)}f", *vec)
    conn.execute(
        "INSERT OR REPLACE INTO embeddings VALUES (?, ?)", (item_id, blob)
    )
    conn.commit()


def load_embed(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


# ---------------------------------------------------------------------------
# High-level: embed a list of DB item rows with caching
# ---------------------------------------------------------------------------

def embed_items(
    conn, cfg: dict, rows: list[dict], verbose: bool = False
) -> dict[str, list[float]]:
    """
    Embed a list of DB item rows. Uses cache. Builds text from item text + path.
    Returns {item_id: vector}.
    """
    ensure_embed_table(conn)
    result: dict[str, list[float]] = {}
    to_embed: list[dict] = []

    for row in rows:
        cached = get_cached(conn, row["id"])
        if cached is not None:
            result[row["id"]] = cached
        else:
            to_embed.append(row)

    if verbose:
        print(
            f"  Embedding {len(to_embed)} new items "
            f"({len(result)} cached)..."
        )

    # Process in batches
    for i in range(0, len(to_embed), _BATCH_SIZE):
        batch = to_embed[i : i + _BATCH_SIZE]
        texts = [_item_text(r) for r in batch]
        vecs = embed_batch(texts, cfg)
        for row, vec in zip(batch, vecs):
            if vec:
                store_embed(conn, row["id"], vec)
                result[row["id"]] = vec

    return result


def _item_text(row: dict) -> str:
    """Build embedding text from item metadata."""
    path = row.get("path", "")
    stem = Path(path).stem.replace("-", " ").replace("_", " ")
    parent = Path(path).parent.name
    text = (row.get("text") or "")[:800]
    return f"{parent} {stem} {text}".strip()[:1200]


# ---------------------------------------------------------------------------
# TF-IDF fallback: produce a latent vector if Ollama is unavailable
# ---------------------------------------------------------------------------

def tfidf_fallback(row: dict, cfg: dict) -> list[float] | None:
    """Return a TF-IDF vector from latent.py as a fallback."""
    try:
        from . import latent
        dim = latent.dim(cfg)
        return latent.vector(row, dim)
    except Exception:
        return None
