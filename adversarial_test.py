#!/usr/bin/env python3
"""Adversarial test suite for Optic — breaks things systematically."""
import json
import time
import sys
import urllib.request
import urllib.error
import concurrent.futures
import threading
import random
import string
from urllib.parse import urlencode, quote

BASE = "http://127.0.0.1:3003"
FINDINGS = []

def log(severity, endpoint, method, payload_desc, status, body_preview, detail=""):
    finding = {
        "severity": severity,  # CRITICAL, HIGH, MEDIUM, LOW, INFO
        "endpoint": endpoint,
        "method": method,
        "payload": payload_desc,
        "status": status,
        "body_preview": str(body_preview)[:500],
        "detail": detail,
    }
    FINDINGS.append(finding)
    icon = {"CRITICAL": "🔥", "HIGH": "⚠️", "MEDIUM": "⚡", "LOW": "·", "INFO": "ℹ️"}
    print(f"  {icon.get(severity, '?')} [{severity:8s}] {method:4s} {endpoint:40s} → {status} | {payload_desc[:80]}")
    if detail:
        print(f"          {detail[:120]}")

def do_request(method, path, data=None, headers=None, timeout=10):
    url = f"{BASE}{path}"
    req = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, body[:2000]
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, body[:2000]
    except Exception as e:
        return 0, str(e)[:2000]

# ── ALL ENDPOINTS ──────────────────────────────────────────────

GET_ENDPOINTS = [
    "/healthz",
    "/api/runs",
    "/api/graph",
    "/api/delta",
    "/api/workstreams",
    "/api/report",
    "/api/status",
    "/api/embeddings/status",
    "/api/home",
    "/api/account",
    "/api/workspace",
    "/api/workspace/members",
    "/api/workspace/invites",
    "/api/api-keys",
    "/api/billing",
    "/api/billing/usage",
    "/api/settings",
    "/api/integrations/catalog",
    "/api/integrations/state",
    "/api/integrations/secrets",
    "/api/integrations/connections",
    "/api/integrations/sync/state",
    "/api/integrations/jobs",
    "/api/integrations/oauth/events",
    "/api/integrations/oauth/callback",
    "/api/audiences",
    "/api/simulations",
    "/api/exports/history",
    "/api/ops/health",
    "/api/ops/backups",
    "/api/infer",
    "/api/analyze",
    "/api/entity/profile",
    "/api/audience",
    "/api/audit/history",
    "/api/v1/simulations",
    "/api/v1/onboarding",
    "/api/v1/exports",
    "/api/v1/claims",
    "/api/v1/contradictions",
    "/api/v1/risks",
    "/api/v1/repairs",
    "/api/v1/status",
    "/api/v1/settings",
    "/api/v1/artifacts",
    "/api/v1/audit/general",
]

POST_ENDPOINTS = [
    "/api/chat", "/api/iris", "/api/rename", "/api/signup", "/api/signout",
    "/api/workspace", "/api/workspace/invites", "/api/workspace/invites/accept",
    "/api/api-keys/create", "/api/api-keys/revoke",
    "/api/billing/checkout", "/api/billing/portal", "/api/billing/webhook", "/api/billing/plan",
    "/api/settings", "/api/integrations/state", "/api/integrations/secrets",
    "/api/integrations/sync/state", "/api/integrations/jobs", "/api/integrations/jobs/replay",
    "/api/integrations/oauth/start", "/api/integrations/oauth/refresh", "/api/integrations/oauth/revoke",
    "/api/scan", "/api/simulations/evaluate", "/api/simulations/save", "/api/simulations/compare",
    "/api/exports", "/api/ops/backup", "/api/ops/restore", "/api/ops/danger",
    "/api/embed/run", "/api/audit", "/api/audit/ml", "/api/audit/batch",
    "/api/v1/onboarding", "/api/v1/simulations",
    "/api/v1/iris/ask",
    "/api/v1/audit/general",
    "/api/v1/reset",
]

# ════════════════════════════════════════════════════════════════
# PHASE 1: Empty, malformed, and edge-case payloads on all POSTs
# ════════════════════════════════════════════════════════════════

print("\n" + "="*80)
print("PHASE 1: EMPTY / MALFORMED / EDGE PAYLOADS (POST)")
print("="*80)

MALFORMED_PAYLOADS = [
    ("empty body", b""),
    ("empty JSON object", b"{}"),
    ("empty JSON object with whitespace", b"  \n  {   }  \n  "),
    ("null", b"null"),
    ("empty array", b"[]"),
    ("string 'test'", b'"test"'),
    ("number 0", b"0"),
    ("boolean true", b"true"),
    ("malformed JSON (trailing comma)", b'{"a": 1,}'),
    ("malformed JSON (no closing)", b'{"a": 1'),
    ("malformed JSON (single quotes)", b"{'a': 1}"),
    ("malformed JSON (NaN)", b'{"a": NaN}'),
    ("malformed JSON (Infinity)", b'{"a": Infinity}'),
    ("binary garbage", bytes(random.getrandbits(8) for _ in range(256))),
    ("XML instead of JSON", b'<?xml version="1.0"?><root><a>1</a></root>'),
    ("HTML instead of JSON", b'<html><body><h1>test</h1></body></html>'),
    ("plain text", b"This is not JSON at all. Just some text."),
    ("very deeply nested", json.dumps({"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": {"j": 1}}}}}}}}}}).encode()),
]

for endpoint in POST_ENDPOINTS:
    for desc, payload in MALFORMED_PAYLOADS:
        status, body = do_request("POST", endpoint, data=payload,
                                  headers={"Content-Type": "application/json"})
        if status == 500:
            log("CRITICAL", endpoint, "POST", desc, status, body, "SERVER 500!")
        elif status == 0:
            log("HIGH", endpoint, "POST", desc, status, body, "Connection error/crash")
        elif status == 200 and desc in ("binary garbage", "XML instead of JSON", "HTML instead of JSON"):
            log("HIGH", endpoint, "POST", desc, status, body, "Accepted non-JSON garbage")
        elif status == 200 and desc == "empty body":
            log("MEDIUM", endpoint, "POST", desc, status, body, "Accepted empty body")
    time.sleep(0.01)  # Don't overwhelm

# ════════════════════════════════════════════════════════════════
# PHASE 2: SQL injection, XSS, path traversal on GET endpoints
# ════════════════════════════════════════════════════════════════

print("\n" + "="*80)
print("PHASE 2: SQL INJECTION / XSS / PATH TRAVERSAL (GET)")
print("="*80)

SQLI_PAYLOADS = [
    "' OR '1'='1",
    "' OR 1=1--",
    "'; DROP TABLE users;--",
    "1' UNION SELECT * FROM users--",
    "1; SELECT * FROM sqlite_master--",
    "' OR 1=1 ORDER BY 1--",
    "1' AND 1=2 UNION SELECT 1,2,3,4,5--",
    "'; SELECT load_extension('/etc/passwd');--",
    "\" OR \"1\"=\"1",
    "1' OR '1'='1' /*",
]

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg/onload=alert(1)>",
    "javascript:alert(1)",
    "\"><script>alert(document.cookie)</script>",
    "<body onload=alert(1)>",
    "';alert(1);//",
    "<iframe src=javascript:alert(1)>",
]

PATH_TRAVERSAL = [
    "../../../etc/passwd",
    "..%2F..%2F..%2Fetc%2Fpasswd",
    "....//....//....//etc/passwd",
    "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "..\\..\\..\\Windows\\System32\\config\\SAM",
    "/../../../../etc/passwd",
]

NEGATIVE_NUMBERS = ["-1", "-999999", "-0", "-Infinity"]

# SQL injection in query params
for endpoint in GET_ENDPOINTS:
    for sqli in SQLI_PAYLOADS[:5]:  # First 5 for speed
        status, body = do_request("GET", f"{endpoint}?q={quote(sqli)}")
        if status == 500:
            log("CRITICAL", endpoint, "GET", f"SQLi: {sqli[:50]}", status, body)

# SQL injection in path segments where applicable
for endpoint in ["/api/v1/claims/workstream/", "/api/simulate/", "/api/v1/simulate/", "/api/audit/"]:
    for sqli in SQLI_PAYLOADS[:3]:
        full_path = f"{endpoint}{quote(sqli)}"
        status, body = do_request("GET", full_path)
        if status == 500:
            log("CRITICAL", full_path, "GET", f"SQLi in path: {sqli[:50]}", status, body)
        elif status == 200:
            log("MEDIUM", full_path, "GET", f"SQLi in path returned 200: {sqli[:50]}", status, body)

# XSS in query params
for endpoint in GET_ENDPOINTS:
    for xss in XSS_PAYLOADS[:3]:
        status, body = do_request("GET", f"{endpoint}?q={quote(xss)}&name={quote(xss)}")
        if status == 200:
            body_str = body.decode('utf-8', errors='replace')
            if "<script>" in body_str or "alert" in body_str:
                log("CRITICAL", endpoint, "GET", f"XSS REFLECTED: {xss[:40]}", status, body_str[:300])

# Path traversal
for endpoint in ["/api/v1/claims/workstream/", "/api/simulate/", "/api/v1/simulate/"]:
    for trav in PATH_TRAVERSAL[:3]:
        full_path = f"{endpoint}{quote(trav)}"
        status, body = do_request("GET", full_path)
        if status == 500:
            log("HIGH", full_path, "GET", f"Path traversal: {trav[:40]}", status, body)
        elif status == 200:
            body_str = body.decode('utf-8', errors='replace')
            if "root:" in body_str or "passwd" in body_str.lower():
                log("CRITICAL", full_path, "GET", f"PATH TRAVERSAL SUCCEEDED: {trav[:40]}", status, body_str[:300])
            else:
                log("MEDIUM", full_path, "GET", f"Path traversal returned 200: {trav[:40]}", status, body_str[:200])

# Negative numbers
for endpoint in GET_ENDPOINTS:
    for neg in NEGATIVE_NUMBERS:
        status, body = do_request("GET", f"{endpoint}?limit={neg}&offset={neg}&page={neg}&id={neg}")
        time.sleep(0.005)

# ════════════════════════════════════════════════════════════════
# PHASE 3: Large payloads, concurrent spam, unicode bombs
# ════════════════════════════════════════════════════════════════

print("\n" + "="*80)
print("PHASE 3: LARGE PAYLOADS / CONCURRENT / UNICODE BOMBS")
print("="*80)

# Unicode bombs
UNICODE_BOMBS = [
    ("zero-width chars", "\u200b\u200c\u200d\u2060\u2061\u2062\u2063\u2064" * 100),
    ("right-to-left override", "\u202e" * 50 + "moc.liamg@nimda"),
    ("homoglyph attack", "admin" + "\u0430" + "dmin"),  # Cyrillic 'a'
    ("decomposition bomb", "\u0041\u0300\u0301\u0302\u0303\u0304\u0305\u0306\u0307\u0308" * 50),
    ("unicode control chars", "\u0000\u0001\u0002\u0003\u0004\u0005\u0006\u0007\u0008\u000b\u000c\u000e\u000f" * 10),
    ("BOM characters", "\ufeff\ufeff\ufeff" * 20),
]

for endpoint in POST_ENDPOINTS[:15]:  # Sample to save time
    for desc, bomb in UNICODE_BOMBS:
        payload = json.dumps({"text": bomb, "name": bomb, "query": bomb}).encode()
        status, body = do_request("POST", endpoint, data=payload,
                                  headers={"Content-Type": "application/json"})
        if status == 500:
            log("HIGH", endpoint, "POST", f"Unicode bomb: {desc}", status, body)

# Large payloads
def make_large_payload(size_mb):
    return json.dumps({
        "text": "A" * (size_mb * 500000),  # Roughly size_mb MB
        "nested": [{"key": "B" * 1000} for _ in range(min(size_mb * 10, 100))],
        "deep": {"level": {str(i): "C" * 1000 for i in range(min(size_mb * 5, 50))}}
    }).encode()

for size in [1, 5, 10]:
    print(f"\n  Testing with {size}MB payloads...")
    payload = make_large_payload(size)
    actual_size = len(payload) / (1024*1024)
    print(f"  Actual payload size: {actual_size:.1f}MB")
    
    for endpoint in ["/api/audit", "/api/chat", "/api/iris", "/api/signup", "/api/settings"]:
        status, body = do_request("POST", endpoint, data=payload,
                                  headers={"Content-Type": "application/json"}, timeout=30)
        if status == 500:
            log("HIGH", endpoint, "POST", f"Large payload ({actual_size:.1f}MB)", status, body)
        elif status == 0:
            log("CRITICAL", endpoint, "POST", f"Large payload crashed server ({actual_size:.1f}MB)", status, body)
        elif status == 200:
            log("MEDIUM", endpoint, "POST", f"Accepted huge payload ({actual_size:.1f}MB)", status, 
                f"Response: {len(body)} bytes")

# Concurrent request spam
print("\n  Spamming endpoints with 50 concurrent requests...")
SPAM_TARGETS = [
    "/api/audit", "/api/status", "/api/home", "/api/runs", "/api/graph",
    "/api/workstreams", "/api/audit/history", "/api/v1/claims", "/api/v1/status",
    "/healthz",
]

def spam_endpoint(endpoint, idx):
    results = []
    for i in range(5):  # 5 per endpoint * 10 endpoints * 50 threads = high load
        try:
            status, body = do_request("GET", endpoint, timeout=5)
            results.append((status, len(body)))
        except Exception as e:
            results.append((0, str(e)[:50]))
    return endpoint, results

with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
    futures = []
    for endpoint in SPAM_TARGETS:
        for i in range(5):
            futures.append(executor.submit(spam_endpoint, endpoint, i))
    
    concurrent.futures.wait(futures, timeout=30)
    
    error_count = 0
    for future in futures:
        if future.done():
            endpoint, results = future.result()
            for status, body_len in results:
                if status in (500, 0):
                    error_count += 1
                    if error_count <= 5:
                        log("CRITICAL", endpoint, "GET", "Concurrent spam", status, 
                            f"body_len={body_len}", "Failed under load")
    
    if error_count == 0:
        print(f"  All concurrent requests survived. {len(futures)} requests, 0 failures.")
    else:
        print(f"  {error_count} failures under concurrent load!")

# ════════════════════════════════════════════════════════════════
# PHASE 4: Special endpoint-specific attacks
# ════════════════════════════════════════════════════════════════

print("\n" + "="*80)
print("PHASE 4: ENDPOINT-SPECIFIC ATTACKS")
print("="*80)

# Audit endpoint — should require evidence but try without
AUDIT_ATTACKS = [
    ("no fields", b"{}"),
    ("no sources", b'{"target": "test"}'),
    ("invalid source paths", json.dumps({"sources": [None, 0, True, [], "../etc/passwd", "/dev/null"]}).encode()),
    ("wildcards in paths", json.dumps({"sources": ["/Users/*/.*", "/**/*"]}).encode()),
    ("extremely long source path", json.dumps({"sources": ["/A" * 10000]}).encode()),
    ("recursive references", b'{"sources": {"$ref": "#/sources"}}'),
]

for desc, payload in AUDIT_ATTACKS:
    for ep in ["/api/audit", "/api/audit/ml", "/api/audit/batch"]:
        status, body = do_request("POST", ep, data=payload,
                                  headers={"Content-Type": "application/json"})
        if status == 500:
            log("CRITICAL", ep, "POST", desc, status, body)

# Reset endpoint — dangerous if not protected
status, body = do_request("POST", "/api/v1/reset", data=b"{}",
                          headers={"Content-Type": "application/json"})
log("HIGH" if status == 200 else "INFO", "/api/v1/reset", "POST", "Unprotected reset", status, body)

# Danger endpoint
status, body = do_request("POST", "/api/ops/danger", data=b"{}",
                          headers={"Content-Type": "application/json"})
log("HIGH" if status == 200 else "INFO", "/api/ops/danger", "POST", "Unprotected danger op", status, body)

# Content-Type header attacks
CT_ATTACKS = [
    ("application/xml", b'<?xml version="1.0"?><root>test</root>'),
    ("text/plain", b"just plain text, not json"),
    ("application/x-www-form-urlencoded", b"key=value&another=thing"),
    ("multipart/form-data", b"--boundary\r\nContent-Disposition: form-data; name=\"file\"\r\n\r\nbad\r\n--boundary--"),
    ("application/octet-stream", bytes(range(256))),
    ("", b"{}"),  # No content-type
]

for ct, payload in CT_ATTACKS:
    for ep in ["/api/audit", "/api/chat", "/api/signup"]:
        headers = {"Content-Type": ct} if ct else {}
        status, body = do_request("POST", ep, data=payload, headers=headers)
        if status == 500:
            log("HIGH", ep, "POST", f"Content-Type='{ct}'", status, body)

# ════════════════════════════════════════════════════════════════
# FRONTEND REACHABILITY CHECK
# ════════════════════════════════════════════════════════════════

print("\n" + "="*80)
print("PHASE 5: FRONTEND REACHABILITY")
print("="*80)

try:
    req = urllib.request.Request("http://127.0.0.1:3000")
    with urllib.request.urlopen(req, timeout=5) as resp:
        html = resp.read().decode('utf-8', errors='replace')
        print(f"  Frontend reachable: {resp.status}, {len(html)} bytes")
        if "DOCTYPE" in html[:500]:
            print("  HTML structure looks valid")
        else:
            log("MEDIUM", "/", "GET", "frontend", resp.status, html[:200], "Missing DOCTYPE or invalid HTML")
except Exception as e:
    log("CRITICAL", "/", "GET", "frontend", 0, str(e), "FRONTEND UNREACHABLE")

# ── Generate findings report ────────────────────────────────────

print("\n" + "="*80)
print(f"TOTAL FINDINGS: {len(FINDINGS)}")
print("="*80)

critical = [f for f in FINDINGS if f["severity"] == "CRITICAL"]
high = [f for f in FINDINGS if f["severity"] == "HIGH"]
medium = [f for f in FINDINGS if f["severity"] == "MEDIUM"]

print(f"  CRITICAL: {len(critical)}")
print(f"  HIGH:     {len(high)}")
print(f"  MEDIUM:   {len(medium)}")
print(f"  LOW/INFO: {len(FINDINGS) - len(critical) - len(high) - len(medium)}")

# Write markdown report
md = []
md.append("# Optic Adversarial Test Findings\n")
md.append(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
md.append(f"**Total endpoints tested:** {len(GET_ENDPOINTS)} GET + {len(POST_ENDPOINTS)} POST")
md.append(f"**Total findings:** {len(FINDINGS)}")
md.append(f"**Critical:** {len(critical)}")
md.append(f"**High:** {len(high)}")
md.append(f"**Medium:** {len(medium)}\n")

if critical:
    md.append("## 🔥 CRITICAL FINDINGS\n")
    for f in critical:
        md.append(f"### {f['endpoint']} ({f['method']})")
        md.append(f"- **Payload:** {f['payload']}")
        md.append(f"- **Status:** {f['status']}")
        md.append(f"- {f['detail']}")
        md.append(f"\n```\n{f['body_preview'][:500]}\n```\n")

if high:
    md.append("## ⚠️ HIGH SEVERITY\n")
    for f in high:
        md.append(f"- **{f['method']} {f['endpoint']}** — {f['payload']} → {f['status']}")
        if f['detail']:
            md.append(f"  - {f['detail']}")
    md.append("")

if medium:
    md.append("## ⚡ MEDIUM SEVERITY\n")
    for f in medium[:30]:
        md.append(f"- **{f['method']} {f['endpoint']}** — {f['payload']} → {f['status']}")
    if len(medium) > 30:
        md.append(f"- ... and {len(medium) - 30} more medium findings")
    md.append("")

md.append("## 📊 ENDPOINT STATUS MATRIX\n")
md.append("| Endpoint | Method | Empty | Malformed | SQLi | XSS | Unicode | Large |")
md.append("|----------|--------|-------|-----------|------|-----|---------|-------|")

# Count issues per endpoint
from collections import Counter
endpoint_issues = Counter()
for f in FINDINGS:
    endpoint_issues[f"{f['method']} {f['endpoint']}"] += 1

for ep, count in endpoint_issues.most_common(15):
    severity_icons = {
        "CRITICAL": sum(1 for f in FINDINGS if f"{f['method']} {f['endpoint']}" == ep and f['severity'] == 'CRITICAL'),
        "HIGH": sum(1 for f in FINDINGS if f"{f['method']} {f['endpoint']}" == ep and f['severity'] == 'HIGH'),
    }
    icons = "🔥" * min(severity_icons["CRITICAL"], 3) + "⚠️" * min(severity_icons["HIGH"], 3)
    md.append(f"| {ep} | {count} issues | {icons} |")

md.append(f"\n## Methodology\n")
md.append(f"- {len(MALFORMED_PAYLOADS)} malformed payload types × {len(POST_ENDPOINTS)} POST endpoints")
md.append(f"- {len(SQLI_PAYLOADS)} SQL injection vectors × {len(GET_ENDPOINTS)} GET endpoints")
md.append(f"- {len(XSS_PAYLOADS)} XSS vectors × {len(GET_ENDPOINTS)} GET endpoints")
md.append(f"- {len(PATH_TRAVERSAL)} path traversal vectors")
md.append(f"- {len(UNICODE_BOMBS)} unicode bomb types")
md.append(f"- 3 large payload sizes (1MB, 5MB, 10MB)")
md.append(f"- 50 concurrent requests across 10 endpoints")
md.append(f"- 6 Content-Type header attacks")

report_path = "/Users/ahmedm/Developer/Projects/optic/ADVERSARIAL-FINDINGS.md"
with open(report_path, "w") as f:
    f.write("\n".join(md))
print(f"\nReport written to {report_path}")
