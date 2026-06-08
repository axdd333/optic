#!/usr/bin/env python3
"""Seed the V1 database from a real filesystem scan."""
import sys, json
sys.path.insert(0, '/Users/ahmedm/Developer/Projects/optic/backend/src')
from optic.v1.startup import ensure_data, get_db_path
result = ensure_data(get_db_path())
print(json.dumps(result, default=str, indent=2))
