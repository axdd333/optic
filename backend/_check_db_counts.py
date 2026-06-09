#!/usr/bin/env python3
"""Check DB counts and sample workstream names."""
import sqlite3

p = '.optic/v1.db'
conn = sqlite3.connect(p)
conn.row_factory = sqlite3.Row

for t in ['signals','claims','contradictions','risks','repairs','reports']:
    n = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t}: {n}')

print()
print("Sample workstream names from claims:")
for row in conn.execute('SELECT claim FROM claims LIMIT 10').fetchall():
    txt = row['claim']
    if "workstream '" in txt.lower():
        start = txt.lower().index("workstream '") + len("workstream '")
        end = txt.index("'", start)
        ws_name = txt[start:end]
    else:
        ws_name = txt[:80]
    print(f"  -> {ws_name}")

conn.close()
