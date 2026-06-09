"""
# DEPRECATED — never imported by the running ctxorg/server.py
# Only referenced in optic/v1/server.py which is NOT the active server.
# Stage 12 (Graph projection) is scheduled for remediation — this module
# will be wired into ctxorg/server.py when that stage is complete.
# DO NOT DELETE — keep as reference implementation for pipeline Stage 12.

Optic V1 evidence graph storage.

Typed SQLite graph for identity audit evidence. Edges are directed, but read
helpers can traverse incoming, outgoing, or both directions.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Literal
from uuid import UUID, uuid4

Direction = Literal["in", "out", "both"]


NODE_TYPES = frozenset({
    "user", "account", "handle", "email", "domain", "organization", "school",
    "employer", "project", "repository", "post", "article", "resume_item",
    "calendar_event", "email_thread", "search_result", "image", "document",
    "artifact", "parsed_span", "topic", "skill", "credential", "location",
    "timeline_period", "signal", "claim", "audience", "risk",
    "contradiction", "repair", "source_gap", "consent_receipt",
    "report_snapshot",
})

EDGE_TYPES = frozenset({
    "authored", "owned", "mentions", "supports", "weakens", "contradicts",
    "outdated_by", "context_for", "associated_with", "same_as",
    "maybe_same_as", "located_at", "worked_at", "studied_at",
    "contributed_to", "inferred_from", "visible_to", "risky_for",
    "repaired_by", "missing_context_for", "derived_from", "imported_under",
    "revoked_by", "included_in_report",
})


class EvidenceGraph:
    """SQLite-backed typed evidence graph."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "EvidenceGraph":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def add_node(
        self,
        node_type: str,
        node_id: str | UUID | None = None,
        *,
        label: str = "",
        data: dict[str, Any] | Any | None = None,
        **attrs: Any,
    ) -> dict[str, Any]:
        """Insert or update a node and return it."""
        self._require_type(node_type, NODE_TYPES, "node")
        nid = str(node_id or uuid4())
        payload = self._merge_data(data, attrs)
        now = self._now()
        self.conn.execute(
            """
            INSERT INTO nodes(id, type, label, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                type = excluded.type,
                label = excluded.label,
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (nid, node_type, label, self._dumps(payload), now, now),
        )
        self.conn.commit()
        node = self.get_node(nid)
        if node is None:
            raise RuntimeError(f"node was not persisted: {nid}")
        return node

    def merge_node(
        self,
        node_type: str,
        node_id: str | UUID,
        *,
        label: str = "",
        data: dict[str, Any] | None = None,
        provenance: str | None = None,
        **attrs: Any,
    ) -> dict[str, Any]:
        """Insert a node or merge provenance data into an existing one.

        Unlike add_node (which overwrites data on conflict), this method
        merges new data fields into the existing node and accumulates
        provenance records so a node that appears in multiple contexts
        tracks all of its source categories.

        The ``provenance`` parameter is a category label (e.g. audience
        lens name, workstream name) that is appended to the node's
        ``data.source_provenance`` list — deduplicating entries so each
        category appears exactly once.
        """
        self._require_type(node_type, NODE_TYPES, "node")
        nid = str(node_id)

        existing = self.get_node(nid)
        if existing is None:
            # First time — insert fresh.
            payload = dict(data or {})
            if provenance:
                payload.setdefault("source_provenance", []).append(provenance)
            payload.update(attrs)
            now = self._now()
            self.conn.execute(
                """
                INSERT INTO nodes(id, type, label, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (nid, node_type, label, self._dumps(payload), now, now),
            )
            self.conn.commit()
            node = self.get_node(nid)
            if node is None:
                raise RuntimeError(f"node was not persisted: {nid}")
            return node

        # Node exists — merge provenance and new data fields.
        merged_data = dict(existing.get("data", {}) or {})
        if data:
            for key, value in data.items():
                if key == "source_provenance":
                    # Accumulate provenance entries — no duplicates.
                    existing_prov = set(merged_data.get("source_provenance", []))
                    new_entries = value if isinstance(value, list) else [value]
                    for entry in new_entries:
                        if entry not in existing_prov:
                            merged_data.setdefault("source_provenance", []).append(entry)
                            existing_prov.add(entry)
                elif key in merged_data:
                    # For scalar fields, keep the existing value (first-write wins)
                    # unless the existing value is a placeholder.
                    if merged_data[key] in (None, "", "unknown"):
                        merged_data[key] = value
                else:
                    merged_data[key] = value

        if provenance:
            existing_prov = set(merged_data.get("source_provenance", []))
            if provenance not in existing_prov:
                merged_data.setdefault("source_provenance", []).append(provenance)
                existing_prov.add(provenance)

        merged_data.update(attrs)
        now = self._now()
        self.conn.execute(
            """
            UPDATE nodes SET data = ?, updated_at = ? WHERE id = ?
            """,
            (self._dumps(merged_data), now, nid),
        )
        self.conn.commit()
        node = self.get_node(nid)
        if node is None:
            raise RuntimeError(f"node was not persisted: {nid}")
        return node

    def add_edge(
        self,
        edge_type: str,
        from_id: str | UUID,
        to_id: str | UUID,
        *,
        edge_id: str | UUID | None = None,
        weight: float = 1.0,
        data: dict[str, Any] | Any | None = None,
        **attrs: Any,
    ) -> dict[str, Any]:
        """Insert or update a typed edge between existing nodes."""
        self._require_type(edge_type, EDGE_TYPES, "edge")
        fid, tid = str(from_id), str(to_id)
        self._require_node(fid)
        self._require_node(tid)
        eid = str(edge_id or uuid4())
        payload = self._merge_data(data, attrs)
        now = self._now()
        self.conn.execute(
            """
            INSERT INTO edges(id, type, from_id, to_id, weight, data, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                type = excluded.type,
                from_id = excluded.from_id,
                to_id = excluded.to_id,
                weight = excluded.weight,
                data = excluded.data
            """,
            (eid, edge_type, fid, tid, float(weight), self._dumps(payload), now),
        )
        self.conn.commit()
        edge = self._get_edge(eid)
        if edge is None:
            raise RuntimeError(f"edge was not persisted: {eid}")
        return edge

    def get_node(self, node_id: str | UUID) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM nodes WHERE id = ?", (str(node_id),)
        ).fetchone()
        return self._node(row) if row else None

    def get_neighbors(
        self,
        node_id: str | UUID,
        *,
        edge_type: str | None = None,
        node_type: str | None = None,
        direction: Direction = "both",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return adjacent nodes with the connecting edge."""
        nid = str(node_id)
        self._require_direction(direction)
        if edge_type is not None:
            self._require_type(edge_type, EDGE_TYPES, "edge")
        if node_type is not None:
            self._require_type(node_type, NODE_TYPES, "node")

        clauses: list[str] = []
        params: list[Any] = []
        if direction in ("out", "both"):
            clauses.append("e.from_id = ?")
            params.append(nid)
        if direction in ("in", "both"):
            clauses.append("e.to_id = ?")
            params.append(nid)
        sql = (
            "SELECT e.*, n.id AS n_id, n.type AS n_type, n.label AS n_label, "
            "n.data AS n_data, n.created_at AS n_created_at, "
            "n.updated_at AS n_updated_at "
            "FROM edges e JOIN nodes n ON n.id = CASE "
            "WHEN e.from_id = ? THEN e.to_id ELSE e.from_id END "
            f"WHERE ({' OR '.join(clauses)})"
        )
        query_params = [nid, *params]
        if edge_type:
            sql += " AND e.type = ?"
            query_params.append(edge_type)
        if node_type:
            sql += " AND n.type = ?"
            query_params.append(node_type)
        sql += " ORDER BY e.created_at, e.id"
        if limit is not None:
            sql += " LIMIT ?"
            query_params.append(int(limit))

        rows = self.conn.execute(sql, query_params).fetchall()
        return [
            {
                "edge": self._edge(row),
                "node": self._node_from_prefix(row, "n_"),
                "direction": "out" if row["from_id"] == nid else "in",
            }
            for row in rows
        ]

    def get_path(
        self,
        start_id: str | UUID,
        end_id: str | UUID,
        *,
        max_depth: int = 6,
        edge_types: Iterable[str] | None = None,
        direction: Direction = "both",
    ) -> dict[str, list[dict[str, Any]]] | None:
        """Find the shortest bounded path between two nodes."""
        start, end = str(start_id), str(end_id)
        self._require_node(start)
        self._require_node(end)
        allowed = self._validate_edge_filter(edge_types)
        self._require_direction(direction)
        if start == end:
            node = self.get_node(start)
            return {"nodes": [node] if node else [], "edges": []}

        queue: list[tuple[str, list[str], list[str]]] = [(start, [start], [])]
        seen = {start}
        while queue:
            current, node_path, edge_path = queue.pop(0)
            if len(edge_path) >= max_depth:
                continue
            for item in self.get_neighbors(current, direction=direction):
                edge = item["edge"]
                if allowed and edge["type"] not in allowed:
                    continue
                nxt = item["node"]["id"]
                if nxt in seen:
                    continue
                nodes = [*node_path, nxt]
                edges = [*edge_path, edge["id"]]
                if nxt == end:
                    return {
                        "nodes": [self.get_node(n) for n in nodes],
                        "edges": [self._get_edge(e) for e in edges],
                    }
                seen.add(nxt)
                queue.append((nxt, nodes, edges))
        return None

    def export_subgraph(
        self,
        node_ids: Iterable[str | UUID],
        *,
        depth: int = 1,
        edge_types: Iterable[str] | None = None,
        direction: Direction = "both",
    ) -> dict[str, list[dict[str, Any]]]:
        """Export a bounded subgraph rooted at node_ids."""
        self._require_direction(direction)
        allowed = self._validate_edge_filter(edge_types)
        roots = {str(n) for n in node_ids}
        for nid in roots:
            self._require_node(nid)

        visited_nodes = set(roots)
        visited_edges: set[str] = set()
        frontier = set(roots)
        for _ in range(max(0, depth)):
            next_frontier: set[str] = set()
            for nid in frontier:
                for item in self.get_neighbors(nid, direction=direction):
                    edge = item["edge"]
                    if allowed and edge["type"] not in allowed:
                        continue
                    visited_edges.add(edge["id"])
                    adjacent = item["node"]["id"]
                    if adjacent not in visited_nodes:
                        visited_nodes.add(adjacent)
                        next_frontier.add(adjacent)
            frontier = next_frontier
            if not frontier:
                break

        return {
            "nodes": self._nodes_by_id(visited_nodes),
            "edges": self._edges_by_id(visited_edges),
        }

    def find_contradictions(
        self,
        node_id: str | UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Return contradiction nodes and direct contradicts edges."""
        params: list[Any] = []
        edge_where = "type = 'contradicts'"
        node_where = "type = 'contradiction'"
        if node_id is not None:
            nid = str(node_id)
            self._require_node(nid)
            edge_where += " AND (from_id = ? OR to_id = ?)"
            node_where += (
                " AND id IN (SELECT from_id FROM edges WHERE to_id = ? "
                "UNION SELECT to_id FROM edges WHERE from_id = ?)"
            )
            params.extend([nid, nid])
            node_params = [nid, nid]
        else:
            node_params = []

        edge_rows = self.conn.execute(
            f"SELECT * FROM edges WHERE {edge_where} ORDER BY created_at, id",
            params,
        ).fetchall()
        node_rows = self.conn.execute(
            f"SELECT * FROM nodes WHERE {node_where} ORDER BY created_at, id",
            node_params,
        ).fetchall()
        return [
            {
                "type": "edge",
                "edge": self._edge(row),
                "from": self.get_node(row["from_id"]),
                "to": self.get_node(row["to_id"]),
            }
            for row in edge_rows
        ] + [{"type": "node", "node": self._node(row)} for row in node_rows]

    def find_evidence_chain(
        self,
        claim_id: str | UUID,
        *,
        max_depth: int = 4,
    ) -> dict[str, list[dict[str, Any]]]:
        """Export evidence that supports, weakens, or derives a claim."""
        cid = str(claim_id)
        node = self.get_node(cid)
        if node is None:
            raise KeyError(f"unknown node: {cid}")
        if node["type"] != "claim":
            raise ValueError(f"evidence chain target must be a claim, got {node['type']}")
        evidence_edges = {
            "supports", "weakens", "contradicts", "inferred_from",
            "derived_from", "missing_context_for", "context_for",
        }
        return self.export_subgraph(
            [cid],
            depth=max_depth,
            edge_types=evidence_edges,
            direction="both",
        )

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                data TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                from_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                to_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                weight REAL NOT NULL DEFAULT 1.0,
                data TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
            CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
            CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id);
            CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id);
            """
        )
        self.conn.commit()

    def _require_node(self, node_id: str) -> None:
        exists = self.conn.execute(
            "SELECT 1 FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if not exists:
            raise KeyError(f"unknown node: {node_id}")

    def _get_edge(self, edge_id: str | UUID) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM edges WHERE id = ?", (str(edge_id),)
        ).fetchone()
        return self._edge(row) if row else None

    def _nodes_by_id(self, node_ids: Iterable[str]) -> list[dict[str, Any]]:
        ids = sorted(set(node_ids))
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"SELECT * FROM nodes WHERE id IN ({marks}) ORDER BY type, label, id",
            ids,
        ).fetchall()
        return [self._node(row) for row in rows]

    def _edges_by_id(self, edge_ids: Iterable[str]) -> list[dict[str, Any]]:
        ids = sorted(set(edge_ids))
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"SELECT * FROM edges WHERE id IN ({marks}) ORDER BY type, id",
            ids,
        ).fetchall()
        return [self._edge(row) for row in rows]

    @staticmethod
    def _require_type(value: str, allowed: frozenset[str], kind: str) -> None:
        if value not in allowed:
            choices = ", ".join(sorted(allowed))
            raise ValueError(f"unknown {kind} type '{value}'. Allowed: {choices}")

    @staticmethod
    def _require_direction(direction: str) -> None:
        if direction not in {"in", "out", "both"}:
            raise ValueError("direction must be 'in', 'out', or 'both'")

    @classmethod
    def _validate_edge_filter(
        cls,
        edge_types: Iterable[str] | None,
    ) -> set[str]:
        allowed = set(edge_types or [])
        for edge_type in allowed:
            cls._require_type(edge_type, EDGE_TYPES, "edge")
        return allowed

    @staticmethod
    def _merge_data(data: dict[str, Any] | Any | None, attrs: dict[str, Any]) -> dict[str, Any]:
        if data is None:
            base: dict[str, Any] = {}
        elif isinstance(data, dict):
            base = dict(data)
        elif is_dataclass(data):
            base = asdict(data)
        elif hasattr(data, "to_dict"):
            base = dict(data.to_dict())
        else:
            raise TypeError("data must be a dict, dataclass, or object with to_dict()")
        base.update(attrs)
        return base

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _dumps(cls, value: dict[str, Any]) -> str:
        return json.dumps(value, default=cls._json_default, sort_keys=True)

    @staticmethod
    def _loads(value: str) -> dict[str, Any]:
        loaded = json.loads(value or "{}")
        return loaded if isinstance(loaded, dict) else {"value": loaded}

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if is_dataclass(value):
            return asdict(value)
        raise TypeError(f"{type(value).__name__} is not JSON serializable")

    def _node(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "type": row["type"],
            "label": row["label"],
            "data": self._loads(row["data"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _edge(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "type": row["type"],
            "from_id": row["from_id"],
            "to_id": row["to_id"],
            "weight": row["weight"],
            "data": self._loads(row["data"]),
            "created_at": row["created_at"],
        }

    def _node_from_prefix(self, row: sqlite3.Row, prefix: str) -> dict[str, Any]:
        return {
            "id": row[f"{prefix}id"],
            "type": row[f"{prefix}type"],
            "label": row[f"{prefix}label"],
            "data": self._loads(row[f"{prefix}data"]),
            "created_at": row[f"{prefix}created_at"],
            "updated_at": row[f"{prefix}updated_at"],
        }


__all__ = ["EDGE_TYPES", "NODE_TYPES", "EvidenceGraph"]
