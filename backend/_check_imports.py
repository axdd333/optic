import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from optic.v1.contradiction import ContradictionEngine

# Check which methods exist
methods = [m for m in dir(ContradictionEngine) if m.startswith('_extract') or m.startswith('_semantic') or m.startswith('_severity_from') or m.startswith('find_claim')]
print("Methods:", methods)

# Check the actual source of find_claim_contradictions
import inspect
sig = inspect.signature(ContradictionEngine.find_claim_contradictions)
print("Signature:", sig)
