import sys, uvicorn
sys.path.insert(0, 'src')
from optic.v1.server import app
uvicorn.run(app, host='127.0.0.1', port=3003, log_level='error')
