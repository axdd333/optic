import sqlite3, json
from pathlib import Path

db_path = Path.home() / ".optic" / "v1.db"
print(f"DB path: {db_path} (exists: {db_path.exists()})")

db = sqlite3.connect(str(db_path))
db.row_factory = sqlite3.Row

print("\n=== Reports ===")
for r in db.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall():
    print(f"  id={r['id'][:12]}... mode={r['audit_mode']} claims={r['claim_count']} contradictions={r['contradiction_count']} risks={r['risk_count']} repairs={r['repair_count']} created={r['created_at'][:19] if r['created_at'] else 'N/A'}")

print("\n=== Counts ===")
for t in ['signals','claims','contradictions','risks','repairs','reports']:
    cnt = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {cnt}")

db.close()
