import subprocess, sys
# Try to install fastapi + deps
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "fastapi", "uvicorn", "pydantic", "httpx", "--quiet"],
    capture_output=True, text=True, timeout=120,
    env={**__import__('os').environ, "PIP_REQUIRE_VIRTUALENV": "false"}
)
print("STDOUT:", result.stdout[-300:])
print("STDERR:", result.stderr[-300:])
print("EXIT:", result.returncode)
