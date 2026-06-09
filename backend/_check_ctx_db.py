#!/usr/bin/env python3
"""Check ctx.db structure and items."""
import sqlite3

conn = sqlite3.connect('.ctxorg/state/ctx.db')
conn.row_factory = sqlite3.Row

print("ctx.db tables:")
for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
    print(f"  {row['name']}")

# Show item counts
for t in ['items', 'clusters', 'runs']:
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t}: {n}")
    except Exception as e:
        print(f"{t}: error - {e}")

print()
print("Sample item paths:")
for row in conn.execute("SELECT path FROM items LIMIT 10").fetchall():
    print(f"  {row['path']}")

conn.close()
