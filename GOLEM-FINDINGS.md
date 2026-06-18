# GOLEM FINDINGS — BRICK SCAN REPORT
> Target: `/Users/ahmedm/Developer/Projects/optic/backend`
> Scan time: 2026-06-09
> Scanner: BRICK (file scanner golem)

---

## 1. .ENV FILES

| File | Status | Risk |
|---|---|---|
| `backend/.env.example` | Template only — no secrets | ✅ SAFE |
| `backend/.env` | **DOES NOT EXIST** | N/A |

No live `.env` files found. The `.env.example` is clean: template host/port settings and commented-out `DEEPSEEK_API_KEY=sk-your-key-here` placeholder.

---

## 2. API KEY PATTERNS

### 2a. Hardcoded Keys in Source — NONE FOUND ✅

All API keys are sourced from environment variables. No hardcoded live keys anywhere. The only hardcoded "key-like" value is a test key in the heresy test suite that the tests themselves assert must NOT appear in production source:

```
tests/test_heresy7_deepseek_optin.py — sk-ef42d79c0ff64ba9bd21c011638397f6 (test-only, NOT in server source)
```

### 2b. Environment Variables Referenced (all safe — env-sourced)

| Env Var | Used In | Purpose |
|---|---|---|
| `DEEPSEEK_API_KEY` | `server.py`, `iris_audit.py` | LLM API key |
| `DEEPSEEK_MODEL` | `server.py`, `iris_audit.py` | Model selection |
| `DEEPSEEK_BASE_URL` | `server.py`, `iris_audit.py` | API endpoint |
| `CTXORG_STRIPE_SECRET_KEY` / `STRIPE_SECRET_KEY` | `server.py` | Billing |
| `CTXORG_BILLING_WEBHOOK_SECRET` / `STRIPE_WEBHOOK_SECRET` | `server.py` | Billing webhooks |
| `CTXORG_GOOGLE_CLIENT_ID` | `server.py` | Google OAuth |
| `CTXORG_GOOGLE_CLIENT_SECRET` | `server.py` | Google OAuth |
| `CTXORG_MS_CLIENT_ID` | `server.py` | Microsoft OAuth |
| `CTXORG_MS_CLIENT_SECRET` | `server.py` | Microsoft OAuth |
| `GITHUB_TOKEN` | `scrapers.py` | GitHub integration |
| `OPTIC_INTERNAL_PROXY_TOKEN` | `server.py` | Internal proxy auth |

### 2c. ⚠️ WEAK DEFAULT — Internal Proxy Token

`src/ctxorg/server.py:782`:
```python
_INTERNAL_PROXY_TOKEN = os.environ.get("OPTIC_INTERNAL_PROXY_TOKEN", "optic-proxy-v1")
```
The hardcoded fallback `"optic-proxy-v1"` is a static, guessable string. If the env var is not set and the proxy header `x-internal-proxy` is spoofed from localhost, CSRF protection is bypassed. **Set `OPTIC_INTERNAL_PROXY_TOKEN` to a random value in production.**

### 2d. ⚠️ CORS WIDE OPEN in V1 FastAPI Server

`src/optic/v1/server.py:119`:
```python
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
```
All origins, all methods, all headers permitted. Acceptable for local-only dev; a risk if ever exposed on a network interface.

---

## 3. EXPOSED PATHS

### 3a. User Home Path in Live Config

`backend/config.json` contains the real user home path:
```json
{
  "home": "/Users/ahmedm",
  "target": "/Users/ahmedm",
  "sources": ["/Users/ahmedm/Developer/Projects"],
  "categories": [
    "Developer/Projects", "Developer/Code",
    "Documents/Work", "Documents/Learning",
    "Documents/Notes", "Documents/Finance"
  ]
}
```
This file is gitignored (root `.gitignore` line 13) ✅, but it exists on disk and reveals:
- Full home directory path
- Scan targets (what this user works on)
- Category structure (what the user organizes)

### 3b. Hardcoded User Paths in Python Source ⚠️

Multiple files contain hardcoded `/Users/ahmedm/` paths — these WOULD be committed if not careful:

| File | Hardcoded Path |
|---|---|
| `src/ctxorg/server.py:93` | `/Users/ahmedm/.optic/v1.db` |
| `src/ctxorg/server.py:9216` | `/Users/ahmedm/.optic/v1.db` |
| `src/ctxorg/server.py:9319` | `/Users/ahmedm/.optic/v1.db` |
| `pipe_audit_loop.py:36` | `/Users/ahmedm/.optic/v1.db` |
| `_reseed.py:13` | `/Users/ahmedm/Developer/Projects/optic/backend/.optic/v1.db` |
| `_check_all_dbs.py:5-6` | `/Users/ahmedm/.optic/v1.db` + `.../backend/.optic/v1.db` |
| `scripts/_check_db2.py:2` | `/Users/ahmedm/Developer/Projects/optic/backend/.optic/v1.db` |
| `test_contra_fix.py:12` | `/Users/ahmedm/Developer/Projects/optic/backend/.optic/v1.db` |
| `test_contra_fix2.py:12` | Same |
| `test_contra_fix3.py:12` | Same |
| `test_debug_load.py:9` | Same |

These should use `os.environ.get("OPTIC_DB_PATH", ...)` or `Path.home() / ".optic" / "v1.db"` instead.

### 3c. Database Files on Disk (CONTAINS REAL DATA) 🔴

| Path | Exists | Content |
|---|---|---|
| `backend/.optic/v1.db` | ✅ YES | Production V1 SQLite database |
| `backend/.ctxorg/state/ctx.db` | ✅ YES | Production ctxorg SQLite database |

Both are gitignored ✅, but are live databases with real scan data on disk.

### 3d. No Private Keys or Certificates Found ✅

No `.pem`, `.key`, `.pfx`, `.p12`, or `.jks` files outside `venv/`. The only `.pem` files are in `venv/lib/python3.9/site-packages/certifi/cacert.pem` (bundled CA certs — safe).

---

## 4. GITIGNORE AUDIT

| Check | Status |
|---|---|
| `backend/.env` ignored? | `backend/` has no `.gitignore` but root covers `.env*.local` — `.env` would NOT be gitignored ⚠️ |
| `backend/config.json` ignored? | ✅ Root `.gitignore` line 13 |
| `backend/.optic/` ignored? | ✅ Root `.gitignore` line 11 |
| `backend/.ctxorg/` ignored? | ✅ Root `.gitignore` line 12 |
| `backend/venv/` ignored? | ✅ Root `.gitignore` line 17 |

### ⚠️ Gap: If someone creates `backend/.env`, it would NOT be gitignored
The root `.gitignore` only ignores `.env*.local` (glob). A plain `backend/.env` file would be tracked by git. No `backend/.gitignore` exists to add backend-specific rules.

---

## 5. SUMMARY

| Severity | Count | Details |
|---|---|---|
| 🔴 HIGH | 0 | No hardcoded secrets, no private keys |
| 🟡 MEDIUM | 3 | Hardcoded user paths in 9+ source files; wide-open CORS; weak default proxy token |
| 🟢 LOW | 2 | Missing `backend/.env` gitignore coverage; `.env.example` is safe template |
| ✅ SAFE | — | All API keys env-sourced; database files gitignored; no credential files on disk |

**THE ACCEPTANCE RULE IS ABSOLUTE.** BRICK has scanned. BRICK has reported.
