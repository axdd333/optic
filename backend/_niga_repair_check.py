import sqlite3, json

conn = sqlite3.connect('.optic/v1.db')
conn.row_factory = sqlite3.Row

total = conn.execute('SELECT COUNT(*) as c FROM repairs').fetchone()['c']
print(f'Total repairs: {total}')

rows = conn.execute('SELECT id, title, impact, effort, urgency, reversibility, linked_claim_id, exact_steps, expected_effect, status FROM repairs ORDER BY impact DESC LIMIT 15').fetchall()
for r in rows:
    imp = float(r['impact'] or 0.5)
    eff = max(float(r['effort'] or 0.5), 0.01)
    urg = float(r['urgency'] or 0.5)
    rev = float(r['reversibility'] or 0.5)
    pri = round((imp * urg * rev) / eff, 3)
    cid = r['linked_claim_id'] or '(empty)'
    steps = (r['exact_steps'] or '')[:80]
    print(f'[{pri:.3f}] {r["title"][:60]} | linked_claim={cid} | steps={steps} | status={r["status"]}')

distinct = conn.execute('SELECT impact, effort, urgency, reversibility, COUNT(*) as cnt FROM repairs GROUP BY impact, effort, urgency, reversibility ORDER BY cnt DESC').fetchall()
print(f'\nDistinct metric combos: {len(distinct)}')
for d in distinct:
    imp = float(d['impact']); eff = float(d['effort']); urg = float(d['urgency']); rev = float(d['reversibility'])
    pri = round((imp * urg * rev) / max(eff, 0.01), 3)
    print(f'impact={imp} effort={eff} urgency={urg} reversibility={rev} -> priority={pri} count={d["cnt"]}')

claims = conn.execute('SELECT COUNT(*) as c FROM claims').fetchone()['c']
print(f'\nTotal claims: {claims}')

claim_rows = conn.execute('SELECT id, title, audience_lens, claim, severity FROM claims LIMIT 10').fetchall()
print(f'\nSample claims for linking:')
for c in claim_rows:
    print(f'  id={c["id"][:8]}... title={c["title"][:40]} lens={c["audience_lens"]} severity={c["severity"]}')

conn.close()
