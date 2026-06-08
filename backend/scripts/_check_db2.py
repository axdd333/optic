import sqlite3, json
db = sqlite3.connect('/Users/ahmedm/Developer/Projects/optic/backend/.optic/v1.db')
db.row_factory = sqlite3.Row

print("=== Reports (last 5) ===")
for r in db.execute("SELECT * FROM reports ORDER BY created_at DESC LIMIT 5").fetchall():
    print(f"  id={r['id'][:16]}... mode={r['audit_mode']} claims={r['claim_count']} contradictions={r['contradiction_count']} risks={r['risk_count']} repairs={r['repair_count']} created={str(r['created_at'])[:19] if r['created_at'] else 'N/A'}")

print("\n=== Counts ===")
for t in ['signals','claims','contradictions','risks','repairs','reports']:
    cnt = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {cnt}")

print("\n=== Claims by audience lens ===")
for r in db.execute("SELECT audience_lens, COUNT(*) as cnt FROM claims GROUP BY audience_lens ORDER BY cnt DESC").fetchall():
    print(f"  {r['audience_lens']}: {r['cnt']}")

print("\n=== Latest claims (3) ===")
for r in db.execute("SELECT * FROM claims ORDER BY generated_at DESC LIMIT 3").fetchall():
    print(f"  [{r['audience_lens']}] {r['title'][:60]}... band={r['confidence_band']}")

db.close()
