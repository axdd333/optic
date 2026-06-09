#!/bin/bash
# Kill old server, start new one with updated code
kill $(lsof -ti :3003) 2>/dev/null
sleep 2

# Use the Python that has uvicorn
PY=/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python
cd /Users/ahmedm/Developer/Projects/optic/backend
exec $PY -c "
import sys, uvicorn
sys.path.insert(0, 'src')
from optic.v1.server import app
uvicorn.run(app, host='127.0.0.1', port=3003, log_level='error')
"
