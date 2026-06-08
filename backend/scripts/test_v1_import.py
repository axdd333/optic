import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from optic.v1.server import app
route_paths = [getattr(r, 'path', '') for r in app.routes]
route_paths = [p for p in route_paths if p]
print(str(len(route_paths)) + ' routes registered:')
for p in sorted(route_paths):
    print('  ' + p)
print('OK')
