import sqlite3
db = sqlite3.connect('.optic/v1.db')
db.row_factory = sqlite3.Row
for t in ['signals','claims','contradictions','risks','repairs','reports','users']:
    try:
        cnt = db.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]
        print(t + ': ' + str(cnt) + ' rows')
    except Exception as e:
        print(t + ': ERROR - ' + str(e))
# Sample some data
print()
print('--- Sample signals ---')
for r in db.execute('SELECT category, description FROM signals LIMIT 3').fetchall():
    print(f'  [{r["category"]}] {r["description"][:80]}')
print()
print('--- Sample claims ---')
for r in db.execute('SELECT audience_lens, claim FROM claims LIMIT 3').fetchall():
    print(f'  [{r["audience_lens"]}] {r["claim"][:80]}')
print()
print('--- Sample repairs ---')
for r in db.execute('SELECT title, status FROM repairs LIMIT 3').fetchall():
    print(f'  {r["title"]} ({r["status"]})')
print()
print('--- Sample report ---')
r = db.execute('SELECT * FROM reports LIMIT 1').fetchone()
if r:
    print(f'  id={r["id"]}, mode={r["audit_mode"]}, claims={r["claim_count"]}, risks={r["risk_count"]}, repairs={r["repair_count"]}')
db.close()
