#!/usr/bin/env python3
"""Quick test of signal imports."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

try:
    from optic.signal import SignalAuditor, PatternDetector
    print('SUCCESS: signal imports work')
except ImportError as e:
    print(f'FAILED: {e}')
    signal_dir = os.path.join(os.path.dirname(__file__), 'backend', 'src', 'optic', 'signal')
    print(f'signal dir exists: {os.path.exists(signal_dir)}')
    if os.path.exists(signal_dir):
        print(f'files: {os.listdir(signal_dir)}')
    
    # Try different import path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
    try:
        from src.optic.signal import SignalAuditor
        print('SUCCESS with src.optic.signal')
    except ImportError as e2:
        print(f'Also failed: {e2}')

# Check from within the optic package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))
from optic.v1.server import SIGNAL_AUDIT_AVAILABLE
print(f'SIGNAL_AUDIT_AVAILABLE from server: {SIGNAL_AUDIT_AVAILABLE}')
