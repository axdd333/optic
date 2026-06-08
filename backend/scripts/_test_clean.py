"""Test the current _clean_workstream_name function."""
import sys
sys.path.insert(0, 'src')

# Copy the function directly
def _clean_workstream_name(raw):
    if not raw:
        return 'Other'
    name = raw.strip()
    for prefix in ['set-up-', 'setup-', 'config-']:
        if name.lower().startswith(prefix):
            name = name[len(prefix):]
    name = name.replace('-', ' ').replace('_', ' ')
    words = name.split()
    cleaned = []
    for w in words:
        if w.upper() in ('AI', 'API', 'HTTPS', 'SSL', 'DNS', 'PDF', 'CSS', 'JS', 'ML', 'ABX', 'XTCFTW'):
            cleaned.append(w.upper())
        elif len(w) <= 2:
            cleaned.append(w.upper())
        else:
            cleaned.append(w[0].upper() + w[1:].lower() if len(w) > 1 else w.upper())
    name = ' '.join(cleaned)
    if len(name) < 2:
        name = raw[:30]
    return name.strip() or 'Other'


ugly_names = [
    'HTTPS ABX XTCFTW Com',
    'Rspace XTCFTW Com Very Very Simple',
    'Live V49',
    'V1',
    'Pyasn1 Modules',
    'Round 1',
    'Beta',
    'Tests',
    'Examples',
    'Docs',
    'Trading',
    'Data',
    'Work',
    'Screenshots',
    'Downloads',
    'Generated',
]

for n in ugly_names:
    cleaned = _clean_workstream_name(n)
    print(f'{n!r:45s} -> {cleaned!r}')
