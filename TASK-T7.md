# TASK-T7: Populate EvidenceGraph During Audit
**Priority:** HIGH (graph visualization)
**Agent:** @optic-pipe
**Files:** backend/src/optic/v1/server.py + backend/src/ctxorg/server.py
**Estimated:** 30 minutes

## Problem
`_build_evidence_graph()` (server.py:936) builds user/sources/artifacts nodes with edges when called from the API endpoint. But it's never called during `run_audit()` or `_v1_audit_bg()`. The graph remains empty after an audit: the live endpoint returns 1 node (user), 0 edges.

## Fix

### In V1 server's run_audit() — After Stage 10 (repairs), before Stage 11 (report):
```python
# Stage 12: Populate evidence graph
eg = graph.EvidenceGraph()
# Add user node
eg.add_node("user", user["id"], label=user.get("email", "Optic user"), data={"local_mode": True})

# Add source nodes
for source in sources:
    sid = f"source:{source['id']}"
    eg.add_node("document", sid, label=source.get("user_label", source.get("provider", "")),
                data=dict(source))

# Add artifact nodes
for artifact in real_artifacts:
    eg.add_node("artifact", str(artifact.id), label=artifact.type,
                data={"type": artifact.type, "content_preview": artifact.content_preview[:100]})
    eg.add_edge("derived_from", str(artifact.id), f"source:{artifact.source_id}")

# Add claim nodes
for claim in all_claims:
    eg.add_node("claim", str(claim.id), label=claim.title[:60],
                data={"audience_lens": claim.audience_lens, "confidence_band": claim.confidence_band.value})
    for aid in claim.supporting_evidence[:3]:
        eg.add_edge("supports", str(aid), str(claim.id))

# Add contradiction nodes
for c in contradictions:
    eg.add_node("contradiction", str(c.id), label=c.category,
                data={"severity": c.severity.value, "description": c.description[:100]})

# Add risk nodes
for r in risks:
    eg.add_node("risk", str(r.id), label=r.category.value,
                data={"severity": r.severity.value, "description": r.description[:100]})

# Add repair nodes
for r in repairs:
    eg.add_node("repair", str(r.id), label=r.title[:60],
                data={"impact": r.impact, "effort": r.effort, "status": r.status.value})

# Persist graph
eg.conn.commit()
eg.close()
```

### In ctxorg bridge _v1_audit_bg()
Same pattern, targeting the shared DB.

## Verification
After fix, `/api/v1/graph/evidence` should return nodes > 1 and edges > 0.

## References
- QA report: QA-VERIFICATION-HAWK.md, Section Stage 12, T7
- Code: optic/v1/graph.py (EvidenceGraph, NODE_TYPES, EDGE_TYPES)
- Live data: graph endpoint returns node_count=1, edge_count=0
