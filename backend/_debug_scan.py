#!/usr/bin/env python3
"""Debug scan_all."""
import sys
sys.path.insert(0, 'src')
from optic.v1.startup import scan_all, quick_scan

# Test individual dirs
for d in ['/Users/ahmedm/Desktop', '/Users/ahmedm/Documents', '/Users/ahmedm/Downloads', '/Users/ahmedm/Developer']:
    files = quick_scan(d)
    print(f'{d}: {len(files)} files')

total = scan_all()
print(f'\nTotal from scan_all(): {len(total)} files')
