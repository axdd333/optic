#!/usr/bin/env python3
"""Clear DB and reseed with real filesystem scan using improved _clean_name."""
import sys, os, hashlib, sqlite3
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, '/Users/ahmedm/Developer/Projects/optic/backend/src')

from optic.v1.startup import scan_all, build_workstreams, generate_narratives, _seed_from_scan

v1_db = Path('/Users/ahmedm/Developer/Projects/optic/backend/.optic/v1.db')

conn = sqlite3.connect(str(v1_db))
conn.row_factory = sqlite3.Row

# Clear existing data
for t in ['signals','claims','contradictions','risks','repairs','reports']:
    conn.execute(f'DELETE FROM {t}')
conn.commit()
print("DB cleared")

# Scan filesystem and build workstreams
print("Scanning filesystem...")
files = scan_all()
workstreams = build_workstreams(files)

# Show workstream names
print(f"\nScanned {len(files)} files → {len(workstreams)} workstreams:\n")
for ws in workstreams:
    print(f"  {ws['name']!r:40s}  ({ws['file_count']} files, conf={ws['confidence']})")

# Seed database
if len(workstreams) >= 2 and len(files) >= 20:
    n = _seed_from_scan(conn, workstreams, files)
    conn.close()
    
    # Verify
    conn2 = sqlite3.connect(str(v1_db))
    conn2.row_factory = sqlite3.Row
    sigs = conn2.execute("SELECT COUNT(*) as n FROM signals").fetchone()['n']
    claims = conn2.execute("SELECT COUNT(*) as n FROM claims").fetchone()['n']
    repairs = conn2.execute("SELECT COUNT(*) as n FROM repairs").fetchone()['n']
    reports = conn2.execute("SELECT COUNT(*) as n FROM reports").fetchone()['n']
    conn2.close()
    
    print(f"\nSeeded: {sigs} signals, {claims} claims, {repairs} repairs, {reports} reports")
    
    # Show sample workstream names from claims
    conn3 = sqlite3.connect(str(v1_db))
    conn3.row_factory = sqlite3.Row
    print("\nSample workstream names from claims:")
    for row in conn3.execute("SELECT DISTINCT claim FROM claims LIMIT 5").fetchall():
        print(f"  {row['claim'][:120]}")
    conn3.close()
else:
    conn.close()
    print(f"\nNot enough data: {len(workstreams)} workstreams, {len(files)} files")
