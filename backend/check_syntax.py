import py_compile, sys
for f in [
    "src/ctxorg/server.py",
    "src/optic/v1/contradiction.py",
    "src/optic/v1/models.py",
]:
    try:
        py_compile.compile(f, doraise=True)
        print(f"{f}: OK")
    except py_compile.PyCompileError as e:
        print(f"{f}: ERROR - {e}")
        sys.exit(1)
print("All files compile clean")
