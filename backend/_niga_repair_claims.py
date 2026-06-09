import sqlite3, json

conn = sqlite3.connect('.optic/v1.db')
conn.row_factory = sqlite3.Row

rows = conn.execute('SELECT id, title, audience_lens, claim, confidence_band, severity, evidence_count, source_gaps, repair_options FROM claims LIMIT 108').fetchall()
print(f'Total: {len(rows)} claims')

# Group by audience_lens
lenses = {}
for r in rows:
    l = r['audience_lens'] or 'unknown'
    if l not in lenses: lenses[l] = 0
    lenses[l] += 1
print('By lens:', json.dumps(lenses))

# Show all claims with their IDs for linking
print('\nFull claim index:')
for i, r in enumerate(rows):
    gaps = (r['source_gaps'] or '').replace('\n',' ')
    conf = r['confidence_band'] or 'medium'
    print(f'{i}: id={r["id"][:12]}... lens={r["audience_lens"]} conf={conf} sev={r["severity"]} title={r["title"][:45]} gaps={gaps[:60]}')

# Also check workstreams
ws = conn.execute('SELECT * FROM workstreams').fetchall()
if ws:
    print(f'\nWorkstreams: {len(ws)}')
    for w in ws[:5]:
        print(f'  {dict(w)}')

# contradictions  
con = conn.execute('SELECT COUNT(*) as c FROM contradictions').fetchone()['c']
print(f'\nContradictions: {con}')

conn.close()
