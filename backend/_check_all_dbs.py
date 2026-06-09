import sqlite3, json, os

# Check all v1.db files
paths_to_check = [
    '/Users/ahmedm/.optic/v1.db',
    '/Users/ahmedm/Developer/Projects/optic/backend/.optic/v1.db',
]

for path in paths_to_check:
    real = os.path.realpath(path)
    print(f"Path: {path}")
    print(f"  Real: {real}")
    print(f"  Exists: {os.path.exists(path)}")
    if os.path.exists(path):
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        for t in ['reports','claims','signals','risks','repairs','contradictions']:
            cnt = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {cnt}")
        db.close()
    print()
