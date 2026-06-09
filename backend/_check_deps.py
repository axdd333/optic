import sys
sys.path.insert(0, 'src')
try:
    import fastapi
    print("fastapi available:", fastapi.__version__)
except ImportError as e:
    print("fastapi NOT available:", e)
    sys.exit(1)
