import sys
sys.path.insert(0, "src")
try:
    import ctxorg.server
    print("server.py imports OK")
except Exception as e:
    print(f"ERROR: {e}")
