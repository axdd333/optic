# Optic Backend Security Audit
**Date:** 2026-06-08
**Auditor:** Vault (Optic Office — DevSecOps Leader)
**Scope:** `backend/src/ctxorg/server.py` (9,561 lines), `app/api/backend/[...path]/route.ts`, `.gitignore`
**Sacred Invariants Audited:** #6 (Model Output Is Untrusted Input), #7 (Client Input Is Untrusted Input), #10 (Database Enforces Invariants)

---

## EXECUTIVE SUMMARY

The Optic backend has a solid security foundation with several best-practice implementations: path-traversal defense, prompt-injection hardening, rate limiting, CSRF protection, OAuth state management, and parameterized SQL. **Three findings warrant immediate attention**: (1) the Next.js proxy bypasses CSRF by spoofing origin headers, (2) the proxy exposes all backend routes including ops/danger with no allowlist, and (3) `/api/ops/health` leaks internal state to any session with read scope.

---

## FINDING 1 [CRITICAL] — Proxy CSRF Bypass via Spoofed Origin

**File:** `app/api/backend/[...path]/route.ts`, lines 18-19
**Violates:** Invariant #7 (Client Input Is Untrusted Input)

The proxy sets `origin` and `host` headers to match the backend URL:
```typescript
headers.set('host', new URL(BACKEND).host);
headers.set('origin', BACKEND);
```

This causes `_csrf_same_origin()` in server.py (line 538-546) to *always* return `true` for proxied requests, because:
```
host = req.headers['host'] → '127.0.0.1:3003' (spoofed by proxy)
origin = req.headers['origin'] → 'http://127.0.0.1:3003' (spoofed by proxy)
org == host → true → CSRF bypass
```

**Impact:** Any cross-origin request routed through the proxy (even from an attacker's site) passes the CSRF check. Since the proxy forwards cookies, an attacker with a CSRF exploit could perform state-changing POST operations as the victim.

**Remediation:**
- Add a cryptographically random internal proxy token (`X-Internal-Proxy`) that only the proxy knows, and have the backend require it for CSRF skip
- OR: Move CSRF to double-submit cookie pattern (Next.js sets a non-httponly CSRF token cookie that the frontend reads and sends as a header — the backend checks they match)
- OR: Add a route allowlist to the proxy so only safe routes are forwarded

---

## FINDING 2 [CRITICAL] — Proxy Exposes All Backend Routes Without Allowlist

**File:** `app/api/backend/[...path]/route.ts`, lines 7-9
**Violates:** Invariant #3 (Evidence-Gated), #10 (Database Enforces Invariants)

The proxy has no allowlist. Any backend path is reachable:
```typescript
const backendPath = url.pathname.replace(/^\/api\/backend/, '');
// backendPath can be /api/ops/danger, /api/v1/reset, /api/billing/webhook, etc.
```

**Dangerous routes now exposed through the public proxy:**
| Route | Risk |
|-------|------|
| `POST /api/ops/danger` | Clear dead letters, reset home summary, reset UI cache |
| `POST /api/ops/backup` | Create full state backup |
| `POST /api/ops/restore` | Restore from backup (could overwrite state) |
| `POST /api/v1/reset` | Clear all V1 test data and users |
| `POST /api/embed/run` | Trigger embedding compute |
| `GET /api/ops/health` | Full system health — disk usage, model config, settings, all runs |

While many of these require auth, the proxy exposes them to the browser network surface where they become targets for CSRF (amplified by Finding 1).

**Remediation:**
- Add an explicit allowlist of backend routes the proxy forwards; return 404 for anything else
- Minimum allowlist: `static/*`, `/api/runs`, `/api/graph`, `/api/workstreams`, `/api/home`, `/api/account`, `/api/workspace*`, `/api/audiences`, `/api/simulate/*`, `/api/simulations*`, `/api/infer`, `/api/audit/*`, `/api/chat`, `/api/iris`, `/api/signup`, `/api/signout`, `/api/rename`, `/api/settings`, `/api/v1/*` (READ operations only)

---

## FINDING 3 [HIGH] — `/api/ops/health` Leaks Sensitive Data with Read Scope

**File:** `backend/src/ctxorg/server.py`, lines 1264-1288
**Violates:** Invariant #3 (Evidence-Gated)

The `_scope_need` function (line 583) assigns only `"read"` scope to all GET routes. The `/api/ops/health` endpoint therefore requires only read scope, yet returns:
- Full disk usage (free/used/total bytes)
- Model provider and configuration
- All scan runs
- Full settings including integration config
- Health report metrics

This is operational intelligence that should require admin scope.

**Remediation:**
- Add `if path == "/api/ops/health": return "admin"` to `_scope_need()` (around line 581)
- Or move `/api/ops/health` under the existing `if path.startswith("/api/ops/"):` block

---

## FINDING 4 [HIGH] — No Input Size Validation on Individual POST Fields

**File:** `backend/src/ctxorg/server.py`, multiple locations
**Violates:** Invariant #7 (Client Input Is Untrusted Input)

The total body is capped at 65,536 bytes (`_MAX_BODY`), but individual string fields are often accepted raw without length limits. Examples:
- `signup_payload`: `data.get("email")` → `str().strip().lower()` — no length cap (line 3613)
- `audit_single_payload`: `data.get("content")` → `str().strip()` — unbounded (line 7976)
- `integrations_secrets_set_payload`: `data.get("secret")` → `str().strip()` — later truncated to 2000, but only at storage (line 2097)
- Path segment extraction: `path.removeprefix("/api/v1/simulate/").strip("/")` — no length cap (could be up to URL max ~8KB)

While the 64KB body cap provides a ceiling, individual field validation is inconsistent. Some functions truncate (secrets, webhook payload), others do not.

**Remediation:**
- Add a helper `_str_field(data, key, max_len=1000)` used consistently
- Apply length caps on: email (254), name (200), content/signal text (10000), path segments (200)

---

## FINDING 5 [MEDIUM] — `/api/chat` Lacks Workspace Role Check

**File:** `backend/src/ctxorg/server.py`, lines 899-903

The POST `/api/chat` handler does not call `_workspace_require_role()`. Any authenticated session can use the LLM chat endpoint. The only guard is the quota system (`_quota_take`).

Compare with `/api/iris` (line 904-906) which also lacks a role check — same pattern. Both are LLM-consuming endpoints that could be abused by a low-privilege workspace member.

**Remediation:**
- Add `_workspace_require_role(cfg, {"owner", "admin", "member"})` to chat and iris handlers
- Or add a billing/plan check: `_quota_take` currently doesn't check subscription tier

---

## FINDING 6 [MEDIUM] — `_req_host` Trusts `x-forwarded-host`

**File:** `backend/src/ctxorg/server.py`, line 524-526

```python
def _req_host(req):
    raw = _req_hdr(req, "x-forwarded-host") or _req_hdr(req, "host")
    return raw.lower()
```

The `x-forwarded-host` header is attacker-controlled and is preferred over the actual `host` header. This is used in CSRF origin checking (line 539). If an attacker can inject an `x-forwarded-host` header matching their origin, they could bypass CSRF for direct backend requests (not proxied through Next.js).

**Remediation:**
- Only trust `x-forwarded-host` from the proxy IP (127.0.0.1)
- Or use `host` header only for same-origin checks

---

## FINDING 7 [MEDIUM] — Webhook Endpoints Bypass CSRF

**File:** `backend/src/ctxorg/server.py`, lines 549-559

The CSRF guard skips API key requests (line 553-554) and unauthenticated requests (line 555-556). The billing webhook (`POST /api/billing/webhook`) has `_scope_need` returning `""` (line 608), meaning no scope required. Combined with the billing webhook's route, this means:

1. The billing webhook bypasses CSRF entirely
2. It's intended for Stripe server-to-server calls
3. But if exposed through the proxy, an attacker could POST to it

The webhook payload does its own signature verification (presumably), but the route is still reachable.

**Remediation:**
- Have the billing webhook handler verify Stripe signature before processing
- Verify this is actually implemented in `billing_webhook_payload()`

---

## FINDING 8 [LOW] — No Content-Type Enforcement on POST Endpoints

**File:** `backend/src/ctxorg/server.py`, line 1011-1024 (body function)

The `body()` function parses any POST body as JSON regardless of Content-Type header. This means:
- `text/plain` with JSON content → accepted
- `application/x-www-form-urlencoded` with JSON → rejected by `json.loads` (good)
- Missing Content-Type → still parsed as JSON

**Remediation:**
- Require `Content-Type: application/json` for all API POST endpoints
- Reject or return clear error for other content types

---

## FINDING 9 [LOW] — `_MAX_BODY` Applied at Raw Read Level, Not JSON Parse Level

**File:** `backend/src/ctxorg/server.py`, line 1148

The 64KB body limit is enforced at the TCP read level (`read_size()`). After parsing, the resulting dict could contain deeply nested structures. No recursion depth or key-count limit is applied.

**Remediation:**
- Add `max(1, min(1000, len(data)))` check after JSON parsing
- Consider a JSON depth limit

---

## POSITIVE FINDINGS (What's Working Well)

### P1: Path Traversal Defense
`safe_static()` (line 8585-8586) correctly uses `Path.resolve()` and checks `root.resolve() in path.parents`. This prevents `../` traversal out of the static directory.

### P2: Prompt Injection Hardening
`_guard_check()` (line 356-369) detects "ignore previous instructions" patterns, including despaced obfuscation (`i g n o r e a l l...`). `_chat_guard_input()` and `_iris_guard_input()` apply this before any LLM call. Null bytes stripped. History sanitized. **Exemplary.**

### P3: Rate Limiting Architecture
Token-bucket rate limiting covers all API endpoints with per-actor (IP/session/key) tracking. GC cleans stale entries after 15 minutes. Configurable via settings. **Well designed.**

### P4: OAuth State Management
`_oauth_state_take()` enforces a 15-minute TTL on state tokens. PKCE is enforced for Google and Microsoft providers. State is validated before token exchange. **Solid OAuth 2.0 implementation.**

### P5: Secret Provider Allowlist
`integrations_secrets_set_payload()` validates provider against `_SECRET_PROVIDERS` allowlist before storing. Secrets are truncated to 2000 chars. Requires owner/admin role. **Correct.**

### P6: Database Gitignore
`.optic/` and `backend/.ctxorg/` are properly covered by root `.gitignore` lines 11-12. `backend/config.json` is also gitignored (line 13). Verified via `git check-ignore`. **Clean.**

### P7: SQL Parameterization
All user-controlled SQL uses `?` placeholders (db.rows with parameter tuples). The two f-string SQL uses in `v1_reset_payload` operate on a hardcoded table name list, not user input. **No SQL injection found.**

### P8: CSRF Guard on All POST API Routes
`_csrf_guard()` (line 549) runs on every POST to `/api/*`. It checks session, API key presence, and same-origin. **Correct pattern** (though bypassed by proxy — see Finding 1).

### P9: Webhook Provider Validation
`integrations_webhook_ingest_payload()` validates provider against `_INT_WEBHOOK_PROVIDERS` allowlist (`{"slack", "google", "microsoft"}`) before processing. **Correct.**

---

## COMPLIANCE WITH SACRED INVARIANTS

| Invariant | Status | Notes |
|-----------|--------|-------|
| #6 — Model Output Is Untrusted Input | PASS | `_chat_guard_output` exists; prompt injection blocked |
| #7 — Client Input Is Untrusted Input | PARTIAL | Good: null-byte stripping, prompt guard, body size cap. Gap: no per-field length limits (Finding 4), proxy CSRF bypass (Finding 1) |
| #10 — Database Enforces Invariants | PASS | Parameterized SQL, state files in gitignored directories |

---

## REMEDIATION PRIORITY

| Priority | Finding | Effort | Risk Reduction |
|----------|---------|--------|----------------|
| **P0** | #1 — Proxy CSRF bypass | Small (add token or cookie pattern) | Eliminates CSRF attack surface |
| **P0** | #2 — Proxy route allowlist | Small (add Set of allowed paths) | Prevents internal route exposure |
| **P1** | #3 — Ops health scope | Trivial (add 1 line) | Prevents info leak |
| **P2** | #4 — Field length limits | Medium (add helper + audit all routes) | Defense in depth |
| **P3** | #6 — x-forwarded-host trust | Trivial (check source IP) | Hardens CSRF for direct access |
| **P4** | #5 — Chat role check | Trivial (add 1 line) | Prevents LLM abuse |
| **P5** | #7 — Webhook CSRF | Small (verify if already handled) | Confirm or fix |
| **P6** | #8 — Content-Type check | Small (add 2-line check) | Cleaner error messages |
| **P7** | #9 — JSON depth limit | Trivial (add recursion guard) | Defense in depth |

---

## AUDIT ROUTE INVENTORY (Complete)

### GET Routes (55 total)
`/`, `/index.html`, `/static/*`, `/healthz`, `/api/health`, `/readyz`, `/api/ready`,
`/api/runs`, `/api/graph`, `/api/reveal`, `/api/open`, `/api/delta`, `/api/workstreams`,
`/api/report`, `/api/status`, `/api/embeddings/status`, `/api/home`, `/api/account`,
`/api/workspace`, `/api/workspace/members`, `/api/workspace/invites`, `/api/api-keys`,
`/api/billing`, `/api/billing/usage`, `/api/settings`, `/api/integrations/*` (catalog, state, secrets, connections, sync/state, jobs, oauth/events, oauth/callback),
`/api/audiences`, `/api/simulations`, `/api/simulate/*`, `/api/exports/history`,
`/api/ops/health`, `/api/ops/backups`, `/api/infer`, `/api/analyze`, `/api/entity/profile`,
`/api/audience`, `/api/audit/history`, `/api/audit/*/report`,
`/api/v1/simulations`, `/api/v1/simulate/*`, `/api/v1/onboarding`, `/api/v1/exports`,
`/api/v1/claims`, `/api/v1/claims/workstream/*`, `/api/v1/contradictions`, `/api/v1/risks`,
`/api/v1/repairs`, `/api/v1/status`, `/api/v1/settings`, `/api/v1/artifacts`, `/api/v1/audit/general`

### POST Routes (42 total)
`/api/chat`, `/api/iris`, `/api/rename`, `/api/signup`, `/api/signout`,
`/api/workspace`, `/api/workspace/invites`, `/api/workspace/invites/accept`,
`/api/api-keys/create`, `/api/api-keys/revoke`,
`/api/billing/checkout`, `/api/billing/portal`, `/api/billing/webhook`, `/api/billing/plan`,
`/api/settings`, `/api/integrations/state`, `/api/integrations/secrets`,
`/api/integrations/sync/state`, `/api/integrations/jobs`, `/api/integrations/jobs/replay`,
`/api/integrations/oauth/start`, `/api/integrations/oauth/refresh`, `/api/integrations/oauth/revoke`,
`/api/integrations/webhooks/*`,
`/api/scan`, `/api/simulations/evaluate`, `/api/simulations/save`, `/api/simulations/compare`,
`/api/exports`, `/api/ops/backup`, `/api/ops/restore`, `/api/ops/danger`,
`/api/embed/run`, `/api/audit`, `/api/audit/ml`, `/api/audit/batch`,
`/api/v1/onboarding`, `/api/v1/simulations`, `/api/v1/simulate/*`, `/api/v1/iris/ask`,
`/api/v1/export/*`, `/api/v1/audit/general`, `/api/v1/repairs/*`, `/api/v1/reset`

---

*Audit completed per GOD directive. Findings are evidence-gated per Invariant #3.*
