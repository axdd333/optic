"""Seed Optic demo data — 6 workstreams, 108 claims, 9 audiences, 6 repairs."""
import sqlite3, json, hashlib
from uuid import uuid4

db = sqlite3.connect('.optic/v1.db')
db.row_factory = sqlite3.Row
now = '2026-06-07T00:00:00'

for t in ['signals','claims','contradictions','risks','repairs','reports']:
    db.execute(f'DELETE FROM {t}')
db.commit()

ws_data = [
    ('Research & Learning','research-learning',0.92,142,['research','learning','ai','notes','papers']),
    ('Career & Work','career-work',0.89,118,['career','work','project','resume','startup']),
    ('Code & Systems','code-systems',0.86,236,['code','software','python','fastapi','systems']),
    ('Identity & Profile','identity-profile',0.81,74,['identity','personal','bio','profile','social']),
    ('Life & Travel','life-travel',0.68,91,['travel','photo','life','journal','writing']),
    ('Finance & Admin','finance-admin',0.76,63,['finance','tax','invoice','budget','documents']),
]

for name, wsid, conf, fc, topics in ws_data:
    for cat in ['frequent_topic','project_velocity']:
        for _ in range(2):
            desc = f"Workstream '{name}' focused on: {', '.join(topics)}" if cat == 'frequent_topic' else f"High-confidence workstream '{name}' with {fc} files shows sustained activity"
            meta = json.dumps({'workstream_id':wsid,'workstream_name':name,'confidence':conf,'file_count':fc,'topics':topics})
            db.execute('INSERT INTO signals(id,category,description,severity,source_artifact_ids,metadata,created_at) VALUES(?,?,?,?,?,?,?)',
                       (str(uuid4()),cat,desc,'low','[]',meta,now))
db.commit()

lenses = ['recruiter','investor','admissions','creator','stranger','customer','collaborator','ad_platform','future_agent']
for name, wsid, conf, fc, topics in ws_data:
    for lens in lenses:
        for cat in ['frequent_topic','project_velocity']:
            title = f"{lens.replace('_',' ').title()} read: {cat}"
            claim = f"A {lens.replace('_',' ')} read may notice consistent focus on Workstream '{name}' focused on: {', '.join(topics)}" if cat == 'frequent_topic' else f"A {lens.replace('_',' ')} read may assess your project output as High-confidence workstream '{name}' with {fc} files shows sustained activity"
            band = 'high' if conf > 0.85 else 'medium'
            db.execute('INSERT INTO claims(id,title,audience_lens,claim,confidence_band,evidence_count,supporting_evidence,weakening_evidence,source_gaps,recency,severity,actionability,possible_consequence,counterargument,repair_options,model_version,not_a_verdict,generated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (str(uuid4()),title,lens,claim,band,5,'[]','[]','[]','recent','low','medium','','','[]','v1',1,now))
db.commit()

risks = [
    ('inference_surface','high','Large footprint creates wide inference surface'),
    ('stale_content','medium','Outdated files may create misleading signals'),
    ('inconsistent_narrative','medium','Contradictory signals across workstreams'),
    ('identity_leak','high','Personal identifiers in work documents'),
    ('recruiter_blindspot','low','Recruiter view lacks recent evidence'),
    ('investor_overexposure','medium','Investor view reveals too much financial detail'),
]
strategies = ['reduce footprint','archive stale files','reconcile narratives','redact identifiers','update LinkedIn','restrict scope']
for i,(cat,sev,desc) in enumerate(risks):
    rid = str(uuid4())
    db.execute('INSERT INTO risks(id,category,description,severity,linked_claim_ids,linked_artifact_ids,audience_affected,created_at) VALUES(?,?,?,?,?,?,?,?)',
               (rid,cat,desc,sev,'[]','[]','all',now))
    db.execute('INSERT INTO repairs(id,title,affected_audience,linked_claim_id,linked_evidence_ids,impact,effort,urgency,reversibility,exact_steps,expected_effect,risk_of_overcorrecting,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (str(uuid4()),f'Fix: {desc}','all','','[]',0.7,0.3,0.6,0.9,f'Step: {strategies[i]}',f'Reduced {cat} exposure','minimal','pending'))
db.commit()

user = db.execute('SELECT * FROM users LIMIT 1').fetchone()
uid = user['id'] if user else str(uuid4())
n = db.execute('SELECT COUNT(*) FROM claims').fetchone()[0]
db.execute('INSERT INTO reports(id,user_id,version,audit_mode,created_at,snapshot_id,claim_count,contradiction_count,risk_count,repair_count) VALUES(?,?,?,?,?,?,?,?,?,?)',
           (str(uuid4()),uid,1,'general',now,hashlib.md5(b'demo').hexdigest()[:16],n,0,6,6))
db.commit()
db.close()

sn = db.execute('SELECT COUNT(*) FROM signals', {}).fetchone() if False else None
import sqlite3 as _s
c = _s.connect('.optic/v1.db')
c.row_factory = _s.Row
sigs = c.execute('SELECT COUNT(*) as n FROM signals').fetchone()['n']
cl = c.execute('SELECT COUNT(*) as n FROM claims').fetchone()['n']
rp = c.execute('SELECT COUNT(*) as n FROM repairs').fetchone()['n']
c.close()
print(f'seeded: {sigs} signals, {cl} claims, {rp} repairs, 1 report')
