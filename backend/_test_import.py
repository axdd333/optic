import sys, traceback
try:
    from src.ctxorg import server
    print("Server module imported successfully")
    print(f"V1_DB path: {server._V1_DB}")
    print(f"V1_AVAILABLE: {server._V1_AVAILABLE}")
except Exception as e:
    traceback.print_exc()
