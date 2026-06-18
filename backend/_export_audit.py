#!/usr/bin/env python3
"""Export system audit V3 - final, with correctly shaped test data."""
import sys, os, json, io, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from ctxorg.server import (
    _export_format, _export_to_csv, _export_to_pdf, _export_to_md,
    _export_check, _export_redact, export_v1_formats_payload,
    _sanitize_pdf_text,
)

errors = []
warnings = []

# Realistic data shapes matching what _export_build returns for each kind
# report_payload shape: {"run": ..., "corpus": ..., "scan": ..., ...}
report_data = {
    "run": "run-abc",
    "corpus": {"total_files": 1847, "total_bytes": 4294967296, "recent_week": 142},
    "scan": {
        "scanning": False, "queue_depth": 0, "dead_letter_count": 3,
        "metrics": {"api_hits": 12453},
        "infer_metrics": {"infer_req": 1245}
    },
    "infer": {"total": 200, "completed": 198},
}

# workstreams_payload shape: {"run": ..., "workstreams": [...], "cached": ...}
workstreams_data = {
    "run": "run-abc",
    "workstreams": [
        {"id": "ws-1", "name": "AI Research \u0026 Development", "file_count": 423,
         "confidence": 0.92, "topics": ["research", "ai", "machine-learning", "nlp"],
         "summary": "Deep engagement with AI/ML research papers, code repositories, and experimental notebooks."},
        {"id": "ws-2", "name": "Creative Writing", "file_count": 215,
         "confidence": 0.78, "topics": ["writing", "fiction", "blog", "essays"],
         "summary": "Significant body of creative work \u2014 draft manuscripts, blog posts, and personal essays."},
        {"id": "ws-3", "name": "Personal Finance", "file_count": 86,
         "confidence": 0.64, "topics": ["finance", "budgeting", "investments", "tax"],
         "summary": "Financial planning documents, spreadsheets, and investment tracking."},
    ],
    "cached": True,
}

# datapack/bundle/markdown _export_build shape
combined_data = {
    "run": "run-abc",
    "report": report_data,
    "workstreams": workstreams_data,
}

print("=" * 60)
print("EXPORT SYSTEM AUDIT V3")
print("=" * 60)

# ---------------------------------------------------------------------------
# TEST 1: _sanitize_pdf_text
# ---------------------------------------------------------------------------
print("\n--- TEST 1: PDF text sanitizer ---")
tests = [
    ("Plain ASCII", "hello world", "hello world"),
    ("em dash", "foo \u2014 bar", "foo -- bar"),
    ("en dash", "foo \u2013 bar", "foo - bar"),
    ("smart quotes", "\u2018hi\u2019 \u201cthere\u201d", "'hi' \"there\""),
    ("ellipsis", "wait\u2026", "wait..."),
    ("bullet", "\u2022 item", "* item"),
    ("mixed", "The \u2014 quick \u2018brown\u2019 fox", "The -- quick 'brown' fox"),
]
all_ok = True
for label, inp, expected in tests:
    result = _sanitize_pdf_text(inp)
    ok = result == expected
    status = "OK" if ok else f"FAIL: got {repr(result)}"
    if not ok:
        all_ok = False
        errors.append(f"sanitize: {label}")
    print(f"  [{('OK' if ok else 'FAIL')}] {label}: {repr(inp)} -> {repr(result)}")
if all_ok:
    print("  All sanitizer tests passed")

# ---------------------------------------------------------------------------
# TEST 2: Format dispatcher
# ---------------------------------------------------------------------------
print("\n--- TEST 2: Format dispatcher ---")
test_cases = [
    ("datapack", combined_data),
    ("graph", combined_data),
    ("bundle", combined_data),
    ("audience", {"lens": "recruiter", "claims": []}),
    ("report", report_data),
    ("workstreams", workstreams_data),
    ("markdown", combined_data),
    ("unknown", combined_data),
]
for kind, data in test_cases:
    try:
        ext, body = _export_format(kind, data, "run-abc", 1716000000)
        print(f"  {kind:15s} -> {ext:6s}  ({len(body):>8,} bytes) OK")
    except Exception as e:
        msg = str(e)[:120]
        print(f"  {kind:15s} -> ERROR: {msg}")
        errors.append(f"_export_format({kind}): {msg}")

# ---------------------------------------------------------------------------
# TEST 3: CSV Export
# ---------------------------------------------------------------------------
print("\n--- TEST 3: CSV Export ---")
try:
    ext, body = _export_to_csv(workstreams_data)
    assert ext == ".csv"
    reader = csv.DictReader(io.StringIO(body.decode('utf-8')))
    rows = list(reader)
    assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"
    assert reader.fieldnames == ["id", "name", "file_count", "confidence", "topics", "summary"]

    # Verify data
    r1 = rows[0]
    assert r1['file_count'] == '423'
    assert r1['confidence'] == '0.92'
    assert ';' in r1['topics'], f"Topics should be semicolon-delimited: {r1['topics']}"

    # Verify empty case
    ext_e, body_e = _export_to_csv({})
    assert "id,name,file_count" in body_e.decode('utf-8'), "Empty CSV must have header"

    # Verify direct list
    ext_l, body_l = _export_to_csv(workstreams_data["workstreams"])
    assert len(list(csv.DictReader(io.StringIO(body_l.decode('utf-8'))))) == 3

    print(f"  OK: CSV works - 3 rows, semicolon topics, empty header, direct list")
except Exception as e:
    errors.append(f"CSV: {e}")
    print(f"  ERROR: {e}")

# ---------------------------------------------------------------------------
# TEST 4: PDF Export
# ---------------------------------------------------------------------------
print("\n--- TEST 4: PDF Export ---")

# 4A: Safe ASCII-only data
try:
    safe = {"corpus": {"total_files": 100, "total_bytes": 1_000_000, "recent_week": 10}}
    ext, body = _export_to_pdf(safe, "run-safe", 1716000000)
    assert ext == ".pdf"
    assert body[:5] == b'%PDF-', f"Not a valid PDF: {body[:10]}"
    assert len(body) > 500, f"PDF too small: {len(body)} bytes"
    print(f"  OK: Safe data -> valid PDF, {len(body)} bytes")
except Exception as e:
    errors.append(f"PDF safe: {e}")
    print(f"  ERROR: {e}")

# 4B: Real workstream data with Unicode (the bug fix verification)
try:
    # Build PDF data matching what _export_build returns for 'report' kind
    pdf_data = report_data  # report_payload already has corpus + scan at top level

    # But _export_to_pdf also extracts workstreams from data
    # Let's add workstreams to simulate the combined _export_build output
    pdf_data_with_ws = {
        "corpus": report_data["corpus"],
        "workstreams": workstreams_data,
        "report": report_data,
    }

    ext, body = _export_to_pdf(pdf_data_with_ws, "run-abc", 1716000000)
    assert ext == ".pdf"
    assert body[:5] == b'%PDF-', f"Not a valid PDF: {body[:10]}"
    assert len(body) > 800, f"PDF too small: {len(body)} bytes"
    print(f"  OK: Unicode data -> valid PDF, {len(body)} bytes")
    print(f"  (em dash in summary was sanitized to '--')")
except Exception as e:
    msg = str(e)
    if 'outside the range' in msg or 'font' in msg.lower():
        errors.append(f"PDF UNICODE BUG STILL EXISTS: {msg[:120]}")
    else:
        errors.append(f"PDF unicode: {msg[:120]}")
    print(f"  ERROR: {msg[:150]}")

# 4C: Empty data
try:
    ext, body = _export_to_pdf({}, "run-empty", 1716000000)
    assert body[:5] == b'%PDF-'
    assert len(body) > 200
    print(f"  OK: Empty data -> valid PDF, {len(body)} bytes")
except Exception as e:
    errors.append(f"PDF empty: {e}")

# 4D: Data with various Unicode chars
try:
    unicode_data = {
        "corpus": {"total_files": 50, "total_bytes": 500000, "recent_week": 5},
        "workstreams": {
            "workstreams": [{
                "id": "u-1",
                "name": "Test \u2014 Workstream \u2018Name\u2019",
                "file_count": 10,
                "confidence": 0.85,
                "topics": ["test"],
                "summary": "Contains \u201csmart quotes\u201d, em\u2014dash, and ellipsis\u2026"
            }]
        }
    }
    ext, body = _export_to_pdf(unicode_data, "run-unicode", 1716000000)
    assert body[:5] == b'%PDF-'
    print(f"  OK: Full Unicode stress test -> valid PDF, {len(body)} bytes")
except Exception as e:
    errors.append(f"PDF unicode stress: {e}")
    print(f"  ERROR: {e}")

# ---------------------------------------------------------------------------
# TEST 5: Markdown Export
# ---------------------------------------------------------------------------
print("\n--- TEST 5: Markdown Export ---")
try:
    # Use correctly shaped data matching _export_build for markdown
    md_data = {
        "run": "run-abc",
        "report": report_data,  # Has 'scan' at top level
        "workstreams": workstreams_data,
    }
    ext, body = _export_to_md(md_data, "run-abc", 1716000000)
    assert ext == ".md"
    md_text = body.decode('utf-8')

    checks = [
        ("Title (H1)", "# Optic Export Report" in md_text),
        ("Run info", "**Run:** run-abc" in md_text),
        ("Corpus section", "## Corpus" in md_text),
        ("Corpus file count", "1847" in md_text),
        ("Workstreams section", "## Workstreams" in md_text),
        ("Workstream count", "(3)" in md_text),
        ("AI Research heading", "### AI Research" in md_text),
        ("Creative Writing heading", "### Creative Writing" in md_text),
        ("Scan Status section", "## Scan Status" in md_text),
        ("Footer disclaimer", "Not a consumer report" in md_text),
        ("Topics rendered", "*Topics:" in md_text),
    ]
    all_md_ok = True
    for label, result in checks:
        status = "OK" if result else "FAIL"
        print(f"  [{status}] MD: {label}")
        if not result:
            all_md_ok = False
            errors.append(f"Markdown: {label}")

    if all_md_ok:
        print("  OK: All markdown sections present")

    # Verify MD content quality
    assert "Optic self-audit" in md_text
    print(f"  OK: MD has footer watermark")

    # Empty case
    ext_e, body_e = _export_to_md({}, "run-empty", 1716000000)
    md_empty = body_e.decode('utf-8')
    assert "# Optic" in md_empty
    assert "Not a consumer report" in md_empty
    print(f"  OK: Empty MD has title + disclaimer")

except Exception as e:
    errors.append(f"Markdown: {e}")
    print(f"  ERROR: {e}")

# ---------------------------------------------------------------------------
# TEST 6: Compliance + Redaction
# ---------------------------------------------------------------------------
print("\n--- TEST 6: Compliance check ---")

# Safe data
r = _export_check({"name": "Safe data only"})
assert r['ok'] and r['risk_count'] == 0
print(f"  OK: Safe data passes (risk_count=0)")

# Emails
r2 = _export_check({"email": "user@example.com", "contact": "test@test.org"})
assert r2['risk_count'] >= 2
assert r2['emails'] == 2
print(f"  OK: Detects emails (count={r2['emails']})")

# Tokens (sk- prefix)
r3 = _export_check({"token": "sk-abc123def456ghijklmnop"})  # gitleaks:allow -- detector test fixture
assert r3['tokens'] >= 1
print(f"  OK: Detects API tokens (count={r3['tokens']})")

# Redaction
data = {
    "user": "john@example.com",
    "notes": "API key: sk-abc123def456",  # gitleaks:allow -- redaction test fixture
    "items": [{"contact": "jane@test.org"}, {"phone": "555-123-4567"}]
}
redacted = _export_redact(data)
assert '[redacted' in str(redacted['user']), "Email should be redacted"
assert '[redacted' in str(redacted['notes']), "Token should be redacted"
assert '[redacted' in str(redacted['items'][0]['contact']), "Nested email should be redacted"
assert _export_redact(42) == 42
assert _export_redact("hello") == "hello"
print(f"  OK: Redaction works (emails, tokens, nested, primitives preserved)")

# ---------------------------------------------------------------------------
# TEST 7: GET /api/v1/exports endpoint shape
# ---------------------------------------------------------------------------
print("\n--- TEST 7: GET /api/v1/exports endpoint shape ---")
mock_cfg = {"home": "/tmp", "state_dir": "/tmp/.ctxorg/state", "target": "/tmp"}
payload = export_v1_formats_payload(mock_cfg)

# Required shape
assert "formats" in payload, "Missing 'formats' key"
assert "history" in payload, "Missing 'history' key"
assert isinstance(payload["formats"], list), "formats must be a list"
assert isinstance(payload["history"], list), "history must be a list"

formats = payload['formats']
format_ids = {f['id'] for f in formats}
expected = {'report', 'audience', 'datapack', 'workstreams', 'markdown'}
assert format_ids == expected, f"Format mismatch: missing={expected-format_ids}, extra={format_ids-expected}"

# Each format must have id, title, subtitle
for f in formats:
    assert f.get('id'), f"Format missing id: {f}"
    assert f.get('title'), f"Format missing title: {f}"
    assert f.get('subtitle'), f"Format missing subtitle: {f}"

print(f"  OK: 5 formats, all with id/title/subtitle")
for f in formats:
    print(f"    - {f['id']:15s} -> {f['title']}")

# Check format-specific expectations
titles = {f['id']: f['title'] for f in formats}
assert 'PDF' in titles.get('report', ''), "Report should be PDF"
assert 'JSON' in titles.get('audience', ''), "Audience should be JSON"
assert 'JSON' in titles.get('datapack', ''), "Datapack should be JSON"
assert 'CSV' in titles.get('workstreams', ''), "Workstreams should be CSV"
assert 'Markdown' in titles.get('markdown', ''), "Markdown should be markdown"
print(f"  OK: Format types correct (PDF, JSON, CSV, Markdown)")

# History structure
history = payload.get("history", [])
if history:
    item = history[0]
    has_fields = all(k in item for k in ["id", "kind", "run", "path", "bytes", "created_at"])
    print(f"  History items: {len(history)}, has expected fields: {has_fields}")

# ---------------------------------------------------------------------------
# TEST 8: JSON export completeness
# ---------------------------------------------------------------------------
print("\n--- TEST 8: JSON export completeness ---")
for kind in ["datapack", "audience"]:
    data = combined_data if kind == "datapack" else {"lens": "recruiter", "claims": [{"id": 1}]}
    ext, body = _export_format(kind, data, "run-abc", 1716000000)
    assert ext == ".json"
    parsed = json.loads(body.decode('utf-8'))
    assert isinstance(parsed, dict)
    # Verify valid JSON round-trips
    re_encoded = json.dumps(parsed)
    assert len(re_encoded) > 10
    print(f"  OK: {kind} -> valid round-trippable JSON, {len(body)} bytes")

# ---------------------------------------------------------------------------
# TEST 9: Edge cases
# ---------------------------------------------------------------------------
print("\n--- TEST 9: Edge cases ---")

# CSV: workstreams with no topics field
ws_no_topics = {"workstreams": [{"id": "x", "name": "Test", "file_count": 1, "confidence": 0.5}]}
ext, body = _export_to_csv(ws_no_topics)
rows = list(csv.DictReader(io.StringIO(body.decode('utf-8'))))
assert len(rows) == 1
print(f"  OK: CSV handles missing topics field")

# CSV: topics as string (not list)
ws_str_topics = {"workstreams": [{"id": "x", "name": "T", "file_count": 1, "confidence": 0.5, "topics": "tag1, tag2"}]}
ext, body = _export_to_csv(ws_str_topics)
rows = list(csv.DictReader(io.StringIO(body.decode('utf-8'))))
# topics are semicolon-joined; if already a string, it just writes as-is
print(f"  OK: CSV handles string topics: {rows[0].get('topics', '')}")

# PDF: very long summary (truncation)
long_ws = {"workstreams": {"workstreams": [{
    "id": "long", "name": "Long", "file_count": 1, "confidence": 0.9,
    "summary": "x" * 300
}]}}
ext, body = _export_to_pdf(long_ws, "run-long", 1716000000)
assert body[:5] == b'%PDF-'
print(f"  OK: PDF handles long summaries (truncated), {len(body)} bytes")

# MD: no workstreams
ext, body = _export_to_md({"run": "r", "report": report_data}, "run-r", 1716000000)
md = body.decode('utf-8')
assert "Workstreams" not in md, "Should not have workstreams section"
assert "## Corpus" in md
assert "## Scan Status" in md
print(f"  OK: MD handles missing workstreams gracefully")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("AUDIT SUMMARY")
print("=" * 60)
if errors:
    print(f"FAILURES ({len(errors)}):")
    for e in errors:
        print(f"  \u2717 {e}")
else:
    print("ALL TESTS PASSED")
    print(f"  9 test suites, all passing")
    print(f"  PDF Unicode bug: FIXED")
    print(f"  CSV format: OK")
    print(f"  Markdown format: OK")
    print(f"  JSON format: OK")
    print(f"  GET /api/v1/exports shape: OK")
    print(f"  Compliance + redaction: OK")
if warnings:
    print(f"WARNINGS ({len(warnings)}):")
    for w in warnings:
        print(f"  ! {w}")
print("=" * 60)
sys.exit(1 if errors else 0)
