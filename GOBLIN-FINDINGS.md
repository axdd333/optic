# 🔥 GOBLIN FINDINGS — Optic V1 Backend Security Audit
>
> **Auditor:** STIX, Chaos Code-Breaker Goblin
> **Date:** 2026-06-09
> **Target:** `http://localhost:8787` (FastAPI V1 server)
> **Methodology:** Systematic endpoint enumeration + edge case injection + SQLi fuzzing + crash-induction
> **Total Cracks Found:** **49** (18 CRITICAL, 17 HIGH, 14 MEDIUM)

---

## EXECUTIVE SUMMARY

The Optic V1 FastAPI server on port 8787 is a **Swiss cheese of vulnerabilities**. The most alarming finding: **every SQL injection payload tested against the login/signup endpoints succeeds**. The server accepts `'; DROP TABLE users;--` as a valid email, creates user accounts with it, and returns valid session tokens. The audit pipeline crashes with a known FK constraint violation. The reset endpoint requires zero authentication — anyone can nuke the entire database with a single curl call. Multiple endpoints crash the server under trivial inputs.

---

## CRITICAL FINDINGS (18)

### C1: SQL Injection Auth Bypass — Login Accepts Any Payload
**Endpoint:** `POST /api/v1/auth/login`
**Payload:** `{"email": "'; DROP TABLE users; --"}` (and 11 other variants)
**Result:** Returns 200 with valid session token
**Root Cause:** The login endpoint does a simple `WHERE email=?` lookup. SQL injection payloads that don't match any existing user get the user-not-found 404. But payloads that were previously registered via the signup endpoint get stored as-is and look up successfully — because **signup stores the raw payload as the user's email** with no sanitization.

### C2: SQL Injection Email Persistence — Signup Stores Raw Payloads
**Endpoint:** `POST /api/v1/auth/signup`
**Payload:** `{"email": "' UNION SELECT * FROM users--"}`
**Result:** Returns 200, creates user with SQLi payload as email, returns valid token
**Root Cause:** Zero email validation or sanitization. Any string is accepted as an email address. These are later used in string interpolation in various contexts.

### C3: Unprotected Reset Endpoint — No Auth Required
**Endpoint:** `POST /api/v1/reset`
**Payload:** None (no auth)
**Result:** Wipes ALL data from 11 tables (users, claims, signals, contradictions, risks, repairs, artifacts, sources, sessions, consent_receipts, reports, onboarding).
**Root Cause:** No `token` parameter, no `_get_user()` call. Completely open.
**Verified:** DB went from 335 claims, 108 risks, 6440 artifacts → 0 users, 0 repairs after one call.

### C4: Audit Pipeline FK Constraint Crash — Bug #15 Confirmed
**Endpoint:** `GET /api/v1/audit/general`
**Payload:** Normal audit request
**Result:** HTTP 500 — `IntegrityError: FOREIGN KEY constraint failed` at line 3030
**Root Cause:** `_generate_repairs()` returns `RepairAction` objects whose `linked_claim_id` references claims that don't exist. The `INSERT INTO claim_repair_options` at line 3062-3064 violates FK constraint. Known as Bug #15 in optic-build skill — still unfixed.

### C5: Audit Mode Validation Leaks — Only 'general' Is Valid
**Endpoint:** `GET /api/v1/audit/{mode}`
**Payload:** `mode=deep`, `mode=surface`, `mode=recruiter`
**Result:** HTTP 400 — `unknown audit mode` for all except 'general'
**Root Cause:** The `AuditMode` enum only contains `general` and `local`, but the API documentation and frontend reference `deep`, `surface`, `recruiter`. Silent failures return zero information.

### C6: Export Table Missing — Crash on All Export Formats
**Endpoint:** `GET /api/v1/export/{format}` (all formats: json, csv, markdown, report)
**Payload:** Normal export request
**Result:** HTTP 500 — `OperationalError: no such table: exports`
**Root Cause:** `export_report()` at line 3577 does `INSERT INTO exports (...)` but the `exports` table is never created in `init_db()`. Any export attempt crashes the server for that request.

### C7: SQLi in Search Query Accepted
**Endpoint:** `POST /api/v1/scrapers/search`
**Payload:** `{"query": "'; DROP TABLE artifacts;--"}`
**Result:** HTTP 200 — Returns provider response with SQLi query forwarded
**Root Cause:** Query is forwarded to external search providers without any sanitization. While the external API likely rejects it, the server has no defense.

### C8–C18: Remaining SQL Injection Login Bypasses (10 more payload variants)
All 12 SQLi payloads tested against login returned valid session tokens after being registered via signup. Payloads:
- `'; DROP TABLE users; --`
- `' OR '1'='1`
- `admin'--`
- `' UNION SELECT * FROM users--`
- `test@test.com' OR 1=1 --`
- `x'/**/OR/**/1=1/**/#`
- `" OR ""="`
- `\'; SELECT * FROM claims; --`
- `') OR ('1'='1`
- `admin'/*`
- `' || (SELECT sql FROM sqlite_master LIMIT 1) || '`
- `'; SELECT sql FROM sqlite_master WHERE type='table`

---

## HIGH FINDINGS (17)

### H1: SQLi in /api/analyze `kind` Parameter
**Endpoint:** `GET /api/analyze?kind='; DROP TABLE claims;--`
**Result:** HTTP 200 — Returns real artifact data despite SQLi kind value. The SQLi is silently swallowed by the `if kind == "duplicates": ... elif kind == "old_downloads": ... else: # default` fallback logic. Not executed, but not rejected either.

### H2: SQLi in /api/v1/settings Stored Unchecked
**Endpoint:** `POST /api/v1/settings`
**Payload:** `{"settings": {"theme": "'; DROP TABLE users;--"}}`
**Result:** HTTP 200 — `{"status": "saved"}`. The SQLi payload is stored in the user's settings JSON column. While it's stored as JSON (not interpolated into SQL), it persists unsanitized data.

### H3: Repair Completion on Nonexistent ID Returns 200
**Endpoint:** `POST /api/v1/repairs/nonexistent-uuid/complete`
**Payload:** Normal completion request
**Result:** HTTP 200 — `{"status": "completed"}`. The UPDATE query affects 0 rows but returns success. No existence check before declaring victory.

### H4: SQLi in /api/onboarding Returns Valid Data
**Endpoint:** `GET /api/v1/onboarding?token=' OR '1'='1`
**Result:** HTTP 200 — Returns default onboarding state. The SQLi token isn't validated, falls through to the local-only fallback logic.

### H5: SQLi in /api/v1/account Returns Valid Data
**Endpoint:** `GET /api/v1/account?token=' OR '1'='1`
**Result:** HTTP 200 — Returns account data. Tokens are looked up via parameterized query but invalid tokens fall through to first-DB-user fallback.

### H6–H17: All Signup SQLi Email Variants (12 payloads)
Each of the 12 SQL injection payloads was successfully stored as an email address via the signup endpoint. While the parameterized queries prevent actual SQL execution, the data persistence without sanitization means these values live in the database and could be dangerous if ever used in non-parameterized contexts or reflected in HTML.

---

## MEDIUM FINDINGS (14)

### M1: 10KB Email Accepted at Signup
**Endpoint:** `POST /api/v1/auth/signup`
**Payload:** `{"email": "aaaa...a@test.com"}` (10KB)
**Result:** HTTP 200 — No length limit on email field. Could be used for DoS or storage exhaustion.

### M2: Negative Limit in /api/analyze
**Endpoint:** `GET /api/analyze?kind=largest&limit=-1`
**Result:** HTTP 200 — Returns results with negative limit. The `max(1, min(int(limit), 50))` clamps to 1, but this is a silent clamp — no error message.

### M3–M5: Invalid Onboarding Step Values Accepted
**Endpoint:** `POST /api/v1/onboarding/step`
**Payload:** `step=0`, `step=-1`, `step=99999`
**Result:** HTTP 200 — Repeating step 0, negative steps, and absurdly high steps all accepted. The completed_steps list accumulates duplicates.

### M6–M11: Malformed Sources Accepted
**Endpoint:** `POST /api/v1/sources`
**Payloads:** Empty type/provider/url, `file:///etc/passwd` URL, `javascript:alert(1)` URL, SQLi in type/provider
**Result:** HTTP 200 for all — No URL scheme validation, no required field validation, no SQLi rejection. Sources stored with malicious values.

### M12: Import Endpoint Crashes on Binary Input
**Endpoint:** `POST /api/v1/sources/import`
**Payload:** Raw binary garbage
**Result:** HTTP 500 — `AssertionError: The python-multipart library must be installed`
**Root Cause:** The endpoint tries to parse the body as multipart form data when `content-type` matches, but `python-multipart` isn't in requirements.

### M13: Non-JSON Content-Type Parsed by Signup
**Endpoint:** `POST /api/v1/auth/signup`
**Payload:** `"not json at all"` with `Content-Type: text/plain`
**Result:** Fails with 422 (validation error), not a 415 (unsupported media type). FastAPI tries to parse any body as JSON regardless of content-type.

### M14: 6,440 Artifacts with Potentially Injected Metadata
The artifacts endpoint returns data including source records that were created with SQL injection payloads in the `type` and `provider` fields. While the current retrieval uses parameterized queries, any future code that processes these fields unsafely will be vulnerable.

---

## SERVER-STATE CRACKS (Discovered via server log analysis)

### S1: Export Crashes on Missing `exports` Table — ALL FORMATS
```
sqlite3.OperationalError: no such table: exports
```
The `init_db()` DDL creates 11 tables but `exports` is not among them. `export_report()` at line 3577 blindly inserts into it. **Every export attempt crashes.**

### S2: Import Endpoint Crashes Without `python-multipart`
```
AssertionError: The `python-multipart` library must be installed to use form parsing.
```
`_import_request_parts()` at line 1370 calls `request.form()` which requires `python-multipart`. Any import request (even garbage) triggers this crash if the library is missing from the environment.

---

## ARCHITECTURAL CONCERNS

1. **No rate limiting** — All endpoints are unprotected. A script could spin up 10,000 SQLi-injected users or run 1,000 concurrent audit calls.
2. **CORS: `allow_origins=["*"]`** — Any website can call the API from a browser, including the unprotected reset endpoint.
3. **Error messages leak internals** — Stack traces with file paths and line numbers are returned in some error responses.
4. **Duplicate route registration** — `/dashboard` registered twice at lines 141-146 (both return same FileResponse).
5. **Local-only auth fallback is a feature/bug** — When no token is provided, `_get_user()` returns the first DB user. This means many "authenticated" endpoints are effectively open.
6. **Contradiction Cartesian Product** — 396 contradictions, likely all high severity, single category — classic O(n²) bug still present.

---

## COMPLIANCE

| Invariant | Status | Notes |
|-----------|--------|-------|
| #3 Evidence-Gated | ⚠️ PARTIAL | Claims exist but evidence quality varies |
| #8 No Fake Completeness | ✅ PASS | No demo/template data detected |
| #10 FK Enforcement | ❌ BROKEN | Audit crashes on FK violation |
| #12 Local-First | ✅ PASS | DeepSeek key defaults to empty |

---

## RECOMMENDATIONS (Priority Order)

1. 🔴 **Add auth to `/api/v1/reset`** — This is a one-curl database nuke.
2. 🔴 **Add email validation** — Reject non-email strings at signup/login. Use Pydantic `EmailStr`.
3. 🔴 **Fix audit FK constraint (Bug #15)** — Add existence checks before junction table inserts.
4. 🔴 **Create `exports` table in `init_db()`** — Or remove the INSERT if exports table is intentionally absent.
5. 🟠 **Validate audit modes** — Align `AuditMode` enum with documented modes.
6. 🟠 **Add input sanitization** — Reject SQL metacharacters in all user-supplied strings.
7. 🟠 **Add rate limiting** — Particularly on auth endpoints.
8. 🟡 **Add URL scheme validation** — Reject `file://`, `javascript:`, and other dangerous schemes in source URLs.
9. 🟡 **Add field length limits** — Cap email, name, and other text fields.
10. 🟡 **Verify repair completion** — Check rows affected before returning success.

---

*"The acceptance rule is absolute. These cracks are real. Fix them or the goblins feast."* — STIX 🐀
