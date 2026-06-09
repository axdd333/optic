import sys
sys.path.insert(0, 'src')
import uvicorn
from optic.v1.server import app
uvicorn.run(app, host='127.0.0.1', port=3004, log_level='info', access_log=False)
