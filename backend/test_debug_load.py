"""Quick debug of DB loading."""
import sys
sys.path.insert(0, '/Users/ahmedm/Developer/Projects/optic/backend/src')

import json, sqlite3, traceback
from uuid import UUID
from optic.v1.models import InferenceClaim, Artifact, Severity, ConfidenceBand

DB = '/Users/ahmedm/Developer/Projects/optic/backend/.optic/v1.db'

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Check claim count
claim_rows = conn.execute("SELECT * FROM claims LIMIT 3").fetchall()
print(f"Claim rows: {len(claim_rows)}")
if claim_rows:
    cd = dict(claim_rows[0])
    print(f"Claim keys: {list(cd.keys())}")
    print(f"Sample claim: id={cd.get('id')[:20] if cd.get('id') else None}, title={cd.get('title','')[:40]}, claim={cd.get('claim','')[:60]}")

# Try to build one
try:
    se = cd["supporting_evidence"]
    if isinstance(se, str):
        try: se = json.loads(se)
        except Exception: se = []
    we = cd["weakening_evidence"]
    if isinstance(we, str):
        try: we = json.loads(we)
        except Exception: we = []
    c = InferenceClaim(
        id=UUID(cd["id"]),
        title=cd["title"] or "",
        audience_lens=cd["audience_lens"] or "",
        claim=cd["claim"] or "",
        confidence_band=ConfidenceBand(cd["confidence_band"] or "low"),
        evidence_count=int(cd["evidence_count"] or 0),
        supporting_evidence=([UUID(x) for x in se if x] if isinstance(se, list) else []),
        weakening_evidence=([UUID(x) for x in we if x] if isinstance(we, list) else []),
        source_gaps=[],
        recency=cd["recency"] or "",
        severity=Severity(cd["severity"] or "low"),
        counterargument=cd.get("counterargument", ""),
    )
    print(f"Built claim OK: {c.title}")
except Exception as e:
    traceback.print_exc()

# Check artifacts
art_rows = conn.execute("SELECT * FROM artifacts LIMIT 3").fetchall()
print(f"\nArtifact rows: {len(art_rows)}")
if art_rows:
    ad = dict(art_rows[0])
    print(f"Artifact keys: {list(ad.keys())}")
    print(f"created_at: {ad.get('created_at','')}")

conn.close()
