#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from optic.v1.lenses import AUDIENCE_LENSES
ids = list(AUDIENCE_LENSES.keys())
print(f"Lens count: {len(ids)}")
print(f"IDs: {ids}")
canonical = ["recruiter","investor","collaborator","creator","privacy","platform","search","institution","stranger"]
missing = [x for x in canonical if x not in ids]
extra = [x for x in ids if x not in canonical]
for lid in ids:
    l = AUDIENCE_LENSES[lid]
    print(f"  {lid}: {l.name} ({l.icon}) risk={l.risk_sensitivity}")
print(f"MISSING: {missing}")
print(f"EXTRA: {extra}")
print("PASS" if not missing and not extra else "FAIL")
