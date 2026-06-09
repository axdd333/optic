#!/usr/bin/env python3
"""Apply prompt injection guard hardening to server.py and iris.py."""
import re, sys

SERVER = '/Users/ahmedm/Developer/Projects/optic/backend/src/ctxorg/server.py'
IRIS = '/Users/ahmedm/Developer/Projects/optic/backend/src/ctxorg/iris.py'

# Read server.py, find _CHAT_BLOCK_RE block, replace
with open(SERVER, 'r') as f:
    content = f.read()

old = '_CHAT_BLOCK_RE = re.compile(\n    r"(ignore (all )?(previous|prior) instructions|"\n    r"reveal (the )?(system|developer) prompt|"\n    r"print (the )?(system|developer) message)",\n    re.IGNORECASE,\n)'

new = '_CHAT_BLOCK_RE = re.compile(\n    r"(ignore (all )?(previous|prior) instructions|"\n    r"reveal (the )?(system|developer) prompt|"\n    r"print (the )?(system|developer) message)",\n    re.IGNORECASE,\n)\n\n# Despaced variant — catches spaced-letter and carriage-return obfuscation.\n# "i g n o r e a l l ..." -> despaced -> "ignoreall..." matches this pattern.\n_DESPACED_BLOCK_RE = re.compile(\n    r"(ignore(all)?(previous|prior)instructions|"\n    r"reveal(the)?(system|developer)prompt|"\n    r"print(the)?(system|developer)message)",\n    re.IGNORECASE,\n)\n\n\ndef _guard_check(q: str) -> bool:\n    """Return True if *q* contains a blocked prompt-injection pattern.\n\n    Resilient to obfuscation: collapses all whitespace (handles \\\\r, \\\\n,\n    multi-space) and also checks the fully-despaced variant (handles\n    spaced-letter obfuscation like \'i g n o r e a l l ...\').\n    """\n    normalized = re.sub(r"\\s+", " ", q).strip()\n    if _CHAT_BLOCK_RE.search(normalized):\n        return True\n    despaced = re.sub(r"\\s+", "", q)\n    if _DESPACED_BLOCK_RE.search(despaced):\n        return True\n    return False'

if old in content:
    content = content.replace(old, new, 1)
    with open(SERVER, 'w') as f:
        f.write(content)
    print("OK: server.py")
else:
    print("FAIL: server.py - old block not found")

# Read iris.py
with open(IRIS, 'r') as f:
    content = f.read()

old2 = '_IRIS_BLOCK_RE = re.compile(\n    r"(ignore (all )?(previous|prior) instructions|"\n    r"reveal (the )?(system|developer) prompt|"\n    r"print (the )?(system|developer) message)",\n    re.IGNORECASE,\n)'

new2 = '_IRIS_BLOCK_RE = re.compile(\n    r"(ignore (all )?(previous|prior) instructions|"\n    r"reveal (the )?(system|developer) prompt|"\n    r"print (the )?(system|developer) message)",\n    re.IGNORECASE,\n)\n\n# Despaced variant — catches spaced-letter and carriage-return obfuscation.\n_DESPACED_IRIS_BLOCK_RE = re.compile(\n    r"(ignore(all)?(previous|prior)instructions|"\n    r"reveal(the)?(system|developer)prompt|"\n    r"print(the)?(system|developer)message)",\n    re.IGNORECASE,\n)\n\n\ndef _iris_guard_check(q: str) -> bool:\n    """Return True if *q* contains a blocked prompt-injection pattern.\n\n    Resilient to obfuscation: collapses all whitespace (handles \\\\r, \\\\n,\n    multi-space) and also checks the fully-despaced variant (handles\n    spaced-letter obfuscation like \'i g n o r e a l l ...\').\n    """\n    normalized = re.sub(r"\\s+", " ", q).strip()\n    if _IRIS_BLOCK_RE.search(normalized):\n        return True\n    despaced = re.sub(r"\\s+", "", q)\n    if _DESPACED_IRIS_BLOCK_RE.search(despaced):\n        return True\n    return False'

if old2 in content:
    content = content.replace(old2, new2, 1)
    with open(IRIS, 'w') as f:
        f.write(content)
    print("OK: iris.py")
else:
    print("FAIL: iris.py - old block not found")
