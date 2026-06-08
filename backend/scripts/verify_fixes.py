import py_compile, sys

files = [
    '/Users/ahmedm/Developer/Projects/optic/backend/src/ctxorg/iris.py',
    '/Users/ahmedm/Developer/Projects/optic/backend/src/optic/reporter.py',
    '/Users/ahmedm/Developer/Projects/optic/backend/src/ctxorg/server.py',
    '/Users/ahmedm/Developer/Projects/optic/backend/src/optic/v1/parsers.py',
]
errors = []
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f'OK: {f}')
    except py_compile.PyCompileError as e:
        print(f'FAIL: {f} — {e}')
        errors.append(f)

if errors:
    sys.exit(1)
print()
print('All 4 Python files compile clean.')
