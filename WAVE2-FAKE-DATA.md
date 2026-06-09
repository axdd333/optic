# Wave 2 — Fake Data & Hardcoded Values Audit

> Generated from: `/Users/ahmedm/Developer/Projects/optic/backend/src/ctxorg/static/app.js` (8218 lines)

---

## A. Hardcoded Color Values

### Palette (lines 34–41)
| Line | Value | Purpose |
|------|-------|---------|
| 35 | `#5aa7ff` | Palette: Documents |
| 36 | `#4bd6c6` | Palette: Images |
| 37 | `#f2bd5a` | Palette: Code |
| 38 | `#ff7f73` | Palette: Video |
| 39 | `#7c8291` | Palette: System |
| 40 | `#b889ff` | Palette: Other |

### Status Dot Colors (line 325)
| Line | Value | Purpose |
|------|-------|---------|
| 325 | `#d97706` | Busy (amber) |
| 325 | `#2563eb` | Signed in (blue) |
| 325 | `#16a34a` | Local-only (green) |

### Category Background Colors (lines 1247–1253)
| Line | Value | Purpose |
|------|-------|---------|
| 1247 | `rgba(99,102,241,.15)` | Identity |
| 1248 | `rgba(59,130,246,.15)` | Work |
| 1249 | `rgba(16,185,129,.15)` | Life |
| 1250 | `rgba(236,72,153,.15)` | Relations |
| 1251 | `rgba(245,158,11,.15)` | Behavior |
| 1253 | `rgba(124,130,145,.15)` | Default fallback |

### Universe Mode Landmark Colors (lines 3979–3990)
| Line | Value | Landmark |
|------|-------|----------|
| 3979 | `#8d63f7` | People |
| 3980 | `#4f86ef` | Projects |
| 3981 | `#25b8b5` | Documents |
| 3983 | `#3dbf79` | (landmark) |
| 3984 | `#e0a53e` | Systems |
| 3985 | `#e95f9f` | Events |
| 3986 | `#9a6cf9` | Outcomes |
| 3988 | `#2fc9d5` | (landmark) |
| 3990 | `#3b6ff0` | Core |

### Identity Universe Label Colors (lines 5698–5712)
| Line | Value | Label |
|------|-------|-------|
| 5698 | `#4f86ef` | Work |
| 5699 | `#34c37b` | Money |
| 5702 | `#f15fa6` | Reputation |
| 5703 | `#e7b04a` | Interests |
| 5704 | `#9a6cf9` | Relationships |
| 5707 | `#5db7ff` | Location |
| 5708 | `#2ac6b4` | Health |
| 5711 | `#f39b4f` | Expression |
| 5712 | `#8493ab` | System |

### Score/Confidence Colors (line 6216)
| Line | Value | Purpose |
|------|-------|---------|
| 6216 | `#22c55e` | High score (≥70) |
| 6216 | `#f59e0b` | Medium score (≥50) |
| 6216 | `#ef4444` | Low score (<50) |

### File Row Color Map (lines 6616–6617)
| Line | Value | Key |
|------|-------|-----|
| 6616 | `#5b9cf6` | blue |
| 6616 | `#2dd4bf` | teal |
| 6616 | `#fbbf24` | amber |
| 6617 | `#f87171` | coral |
| 6617 | `#a78bfa` | purple |
| 6617 | `#6b7280` | gray |

### Canvas Background / Gradient Colors
| Line | Value | Purpose |
|------|-------|---------|
| 4170 | `#1a2444` | Canvas fill |
| 4636 | `#fbfcff` | Gradient start |
| 4637 | `#f5f8ff` | Gradient end |
| 4671 | `#1b2446` | Canvas fill |
| 5603 | `#05060f` | Universe bg gradient start |
| 5604 | `#03050b` | Universe bg gradient end |

### Fallback / Error Colors
| Line | Value | Purpose |
|------|-------|---------|
| 3745 | `#ff7f73` | Error text color |
| 4346 | `#7c8291` | Fallback map color |
| 4369 | `#4f86ef` | Fallback sample color |
| 5057 | `#6b7280` | Fallback palette color |

---

## B. Hardcoded API Endpoint URLs

| Line | Endpoint |
|------|----------|
| 227 | `/api/home` |
| 241 | `/api/audiences` |
| 254 | `/api/status` |
| 279 | `/api/settings` |
| 349 | `/api/runs` |
| 369 | `/api/graph?run=` |
| 814, 992 | `/api/workstreams` |
| 1726 | `/api/analyze?kind=duplicates&limit=8` |
| 1727 | `/api/analyze?kind=old_downloads&limit=10` |
| 1728 | `/api/analyze?kind=largest&limit=10` |
| 2063 | `/api/simulations/evaluate` |
| 2069 | `/api/simulations/save` |
| 2084 | `/api/simulations/compare` |
| 2118 | `/api/exports/history` |
| 2228 | `/api/exports` |
| 2290 | `/api/ops/health` |
| 2298 | `/api/ops/backups` |
| 2307 | `/api/workspace` |
| 2315 | `/api/workspace/members` |
| 2324 | `/api/workspace/invites` |
| 2333 | `/api/integrations/state` |
| 2341 | `/api/integrations/jobs` |
| 2349 | `/api/integrations/oauth/events` |
| 2357 | `/api/integrations/connections` |
| 2365 | `/api/integrations/sync/state` |
| 2373 | `/api/billing` |
| 2381 | `/api/billing/usage` |
| 2818 | `/api/workspace` (POST save) |
| 2830 | `/api/workspace/invites` (POST) |
| 2886 | `/api/integrations/state` (POST) |
| 2974 | `/api/integrations/secrets` (POST X token) |
| 2994 | `/api/integrations/secrets` (POST secrets) |
| 3018 | `/api/integrations/oauth/start` (Calendar) |
| 3044 | `/api/integrations/oauth/start` (Storage) |
| 3066 | `/api/integrations/oauth/start` (ChatOps) |
| 3087 | `/api/integrations/oauth/refresh` |
| 3108 | `/api/integrations/oauth/revoke` |
| 3156, 3170 | `/api/integrations/jobs/replay` |
| 3200, 3235, 3260, 3291, 3322, 3356 | `/api/integrations/jobs` (POST) |
| 3390 | `/api/billing/plan` |
| 3405 | `/api/billing/checkout` |
| 3418 | `/api/billing/portal` |
| 3431 | `/api/settings` (POST) |
| 3440 | `/api/ops/backup` |
| 6562 | `/api/simulate/{audienceId}` |
| 6708 | `/api/infer?run=&cluster=` |
| 6857 | `/api/rename` |
| 6874 | `/api/open?mode=reveal&path=` |
| 6984 | `/api/iris` (POST streaming) |
| 7142 | `/api/chat` (POST legacy) |
| 7313 | `/api/analyze?kind=` |
| 7778 | `/api/account` |
| 7892 | `/api/signup` |
| 7909 | `/api/signout` |
| 7954 | `/api/health` |
| 7984 | `/api/integrations/catalog` |
| 8075 | `/api/integrations/state` (POST digest) |
| 8092 | `/api/integrations/jobs` (POST digest queue) |
| 8116 | `/api/integrations/state` (GET LLM runtime) |
| 8142 | `/api/integrations/state` (POST LLM save) |
| 8182 | `/api/graph?run=` |
| 8183 | `/api/workstreams?run=` |

---

## C. Hardcoded Magic Numbers

### Time-Related
| Line | Value | Meaning |
|------|-------|---------|
| 6924 | `120` | Default Iris timeout (seconds) |
| 6927 | `12000` | Min Iris timeout (ms) |
| 6927 | `240000` | Max Iris timeout (ms) |
| 6927 | `1000` | sec→ms conversion |
| 7078 | `1800` | Max user message chars in history |
| 7081 | `2400` | Max assistant response chars in history |
| 7084 | `24` | Max history entries before trim |
| 7084 | `4` | Trim count when overflowing |
| 7212 | `86400` | Seconds per day |
| 7396 | `86400` | Seconds per day (stale calc) |
| 7443 | `1024` | Bytes per KB (humanSize) |
| 7459 | `3600` | Seconds per hour |
| 7460 | `86400` | Seconds per day |
| 7461 | `2592000` | Seconds per 30 days |
| 989 | `3000` | Polling interval for Gemma names (ms) |
| 989 | `20` | Max polling iterations |
| 8212 | `300` | setTimeout for URL.revokeObjectURL |

### Layout & Sizing
| Line | Value | Meaning |
|------|-------|---------|
| 468 | `110` | Max textarea height (px) |
| 981 | `200` | Max globe points |
| 981 | `120` | Default globe points |
| 1034 | `3` | Default evidence rows |
| 1034 | `99` | Max evidence rows (expanded) |
| 1107 | `480` | Min canvas width |
| 1108 | `320` | Min canvas height |
| 1110 | `220` | Room calc min |
| 1110 | `112` | Room calc padding |
| 1113 | `0.8` | Min cam zoom |
| 1113 | `3.4` | Max cam zoom |
| 1445 | `210` | Default globe canvas W |
| 1446 | `210` | Default globe canvas H |
| 1449 | `170` | Camera Z position |
| 1457 | `40` | Min globe node count |
| 1457 | `200` | Max globe node count |
| 1478 | `3.2` | Point material size |
| 1516 | `40` | Min 2D globe pts |
| 1516 | `220` | Max 2D globe pts |
| 1536 | `rgba(255,255,255,.34)` | Globe shell fill |
| 7226 | `1.8` | PCA scale factor |

### Thresholds & Limits
| Line | Value | Meaning |
|------|-------|---------|
| 80 | `0` | Default Iris req sequence |
| 83 | `0` | Default Iris error streak |
| 1029 | `80` | Confidence "high" threshold |
| 1029 | `50` | Confidence "medium" threshold |
| 564 | `6` | Max entity selection count |
| 698 | `"topology"` | Map tool default |
| 7538 | `12` | Max history messages |
| 7538 | `12000` | Max history chars |
| 1602 | `8` | Min coverage display |
| 1602 | `42` | Base coverage display |
| 1602 | `11` | Coverage decrement |
| 1603 | `56` | Min confidence display |
| 1726 | `8` | Duplicate analysis limit |
| 1727 | `10` | Old downloads limit |
| 1728 | `10` | Largest files limit |
| 1755 | `10` | Vault display rows |
| 1772 | `4` | Duplicate groups shown |
| 1780 | `42` | Dup name truncation |
| 1801 | `6` | Category rows shown |
| 1964 | `16` | Simulation workstream rows |
| 1995 | `4` | Slider min value |
| 1995 | `10` | Slider max value |
| 1995 | `8` | Slider default calc |
| 1990 | `3` | Auto-checked rows |
| 2077 | `2` | Min scenarios for compare |
| 2416 | `8` | Max members shown |
| 2420 | `6` | Max invites shown |
| 2424 | `4` | Recent jobs shown |
| 2428 | `5` | Recent OAuth events |
| 2436 | `8` | Max connections shown |
| 2444 | `6` | Max sync rows shown |
| 6605 | `26` | File label truncation |
| 6650 | `220` | File preview chars |
| 6650 | `30` | Min snippet length |
| 6755 | `24` | Evidence name truncation |
| 6782 | `12` | Similar files shown |
| 6782 | `30` | Similar label truncation |
| 6806 | `22` | Panel title truncation |
| 6820 | `6` | Similar for Iris query |
| 6827 | `20` | Glow connected nodes |
| 6993 | `6` | Max selected entity IDs |
| 7137 | `10` | Workstream context count |
| 7163 | `4` | Related items shown |
| 7163 | `26` | Related path truncation |
| 7328 | `32` | Largest file name truncation |
| 7360 | `28` | Stale file name truncation |
| 7381 | `14` | Duplicate groups shown |
| 7385 | `28` | Duplicate name truncation |

---

## D. Hardcoded Default Values

| Line | Value | Purpose |
|------|-------|---------|
| 78 | `"report"` | Default Iris mode |
| 86 | `"recruiter"` | Default Iris audience |
| 149 | `"workstreams"` | Default mode |
| 140 | `"workstreams"` | Default URL mode fallback |
| 318 | `0` | Default queue depth |
| 390 | `0.1` | Default link score |
| 794 | `"all"` | Default category filter |
| 795 | `"relevance"` | Default sort |
| 796 | `"grid"` | Default view |
| 919 | `4` | Default audience count |
| 921 | `"—"` | Default "ago" display |
| 1347 | `"lender"` | Behavior → audience |
| 1348 | `"stranger"` | Relations/life → audience |
| 1349 | `"recruiter"` | Identity → audience |
| 1352 | `"investor"` | Finance/startup → audience |
| 1353 | `"recruiter"` | Default audience fallback |
| 1749 | `"idle"` | Default scan stage |
| 1750 | `"ready"` | Default stage state |
| 1751 | `"none"` | Default last run |
| 1843 | `"latest"` | Default run for Iris |
| 2039 | `"recruiter"` | Default sim audience |
| 2045 | `"Scenario"` | Default sim name |
| 2126 | `true` | Default redact_exports |
| 2459 | `"Alex Morgan"` | Default display name |
| 2461 | `30` | Default session days |
| 2464 | `6` | Default queue cap |
| 2465 | `2` | Default retry max |
| 2466 | `3` | Default backoff seconds |
| 2467 | `300` | Default timeout seconds |
| 2499 | `"Optic Workspace"` | Default workspace name |
| 6420 | `"recruiter"` | Default audience ID 1 |
| 6423 | `80` | Default recruiter score |
| 6430 | `76` | Default investor score |
| 6437 | `72` | Default lender score |
| 6444 | `68` | Default stranger score |
| 7538 | `12` | Max Iris history messages |
| 7538 | `12000` | Max Iris history chars |
| 7946 | `"ollama"` | Default provider mode |
| 7971 | `"0 9 * * *"` | Default digest cron |
| 7972 | `"UTC"` | Default digest timezone |
| 8072 | `"0 9 * * *"` | Digest cron fallback |
| 8073 | `"UTC"` | Digest TZ fallback |
| 8135 | `"ollama"` | Default LLM provider mode |
| 8169 | `"report"` | Default export kind |
| 8095 | `"team@local"` | Default digest email |
| 8096 | `"Optic digest · manual run"` | Default digest subject |
| 8097 | `"Manual digest run queued from settings."` | Default digest body |
| 8098 | `{ source: "settings_manual_digest" }` | Default digest meta |

---

## E. Hardcoded Category / Topic Mappings

### Workstream Category Keywords (lines 1210–1220)
```
identity:  ["identity", "personal", "bio", "profile", "resume", "cv", "social"]
work:      ["work", "code", "project", "career", "job", "research", "skill", "learning"]
life:      ["photo", "travel", "health", "fitness", "journal", "diary", "life"]
relations: ["contact", "email", "message", "social", "people", "friend", "family"]
behavior:  ["habit", "finance", "purchase", "browse", "download", "activity"]
```

### Emoji Mapping (lines 1258–1275)
```
"research"/"learning"       → 📚
"career"/"work"             → 💼
"social"/"message"          → 💬
"finance"/"purchase"        → 💳
"write"/"journal"           → ✍️
"photo"/"image"             → 📷
"travel"                    → ✈️
"health"/"fitness"          → 🏃
"code"/"project"            → 💻
"config"/"system"           → ⚙️
identity (fallback)         → 📁
work (fallback)             → 💼
life (fallback)             → 📷
relations (fallback)        → 💬
behavior (fallback)         → 💳
default                     → 📁
```

### File Icon Mapping (lines 1309–1318)
```
.pdf/.doc/.docx  → 📄
.md/.txt         → 📝
.json/.yml/.toml → ⚙️
.js/.ts/.py      → 💻
http://          → 🔗
default          → 📄
```

### Narrative Noise Words (lines 1384–1390)
```
"name", "path", "users", "ahmedm", "home", "root", "local", "mobile",
"desktop", "downloads", "documents", "inbox", "library", "folder",
"true", "false", "null", "none", "https", "http", "www", "com", "org",
"json", "html", "default", "used", "found", "size", "type", "date",
"conf", "pio", "bash", "text", "file", "files", "copy", "temp", "misc",
"version", "new", "old", "stinct", "ass", "sch", "pcb"
```

### Narrative Topic → Label Map (lines 1393–1411)
17 regex→label pairs (e.g., `/python|numpy|pandas|.../i` → "Python developer", `/swift|xcode|.../i` → "Apple platform builder", etc.)

---

## F. Hardcoded UI Text / Template Strings

| Line | Text |
|------|------|
| 101 | `"Optic failed"` |
| 306 | `"Up to date · "` |
| 322–324 | `"Status: indexing in progress."` / `"Status: account connected."` / `"Status: local-only mode."` |
| 337–338 | `"Ask anything about your files"` / `"files indexed · everything stays on-device"` |
| 342–343 | `"No files indexed yet"` / `"Scan a folder to get started"` |
| 359 | Month names: `["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]` |
| 498–506 | Iris mode placeholders (report, archive, mirror, retune, entity, compare, audience, contradiction, audit) |
| 508 | `"Ask Iris…"` |
| 543 | `"No file selected — click a node"` |
| 733 | `"Ask Iris about this map"` |
| 740, 746, 808 | `"Ask Iris about your files…"` |
| 836 | `"Could not load workstreams: "` |
| 851 | `"Loading workstreams…"` |
| 859–861 | `"Home"` / `"Optic analyzes your digital footprint to surface what humans and algorithms infer about you."` |
| 865–870 | Tab labels: "All clusters", "Identity", "Work & skills", "Life", "Relations", "Behavior" |
| 873 | `"Sort:"` |
| 875–878 | Sort options: "Relevance", "Recent", "Size", "A–Z" |
| 935–936 | `"Your digital self"` / `"Private · local · on-device"` |
| 940 | `"Files indexed"` |
| 1047 | `"Untitled"` |
| 1056 | `"Top evidence"` |
| 1057 | `"No indexed files yet"` |
| 1061 | `"→ View in map"` |
| 1620–1621 | `"Iris"` / `"Analytical intelligence for your digital universe."` |
| 1653–1655 | `"What changed most?"`, `"What to delete?"`, `"Recruiter summary"` |
| 1783 | `"Vault (Local)"` / `"On-device"` |
| 1784 | `"Your private files and sources. Everything stays on this machine."` |
| 1793 | `"Search in vault…"` |
| 1897–1898 | `"Audiences"` / `"See how different people and systems will perceive you."` |
| 2004 | `"Model how changes to your digital presence influence different audiences."` |
| 2012 | `"Identity uplift"` |
| 2182 | `"Optic · Your Digital Identity Report"` |
| 2219 | More filters text |
| 2454 | `"Control how Optic works on this device."` |
| 6470 | `"mapToolbar"` |
| 6474 | `"Map tools"` |
| 6503 | `"Drag to pan · Scroll to zoom · Click to select"` |
| 6527 | `"How they read your footprint"` |
| 6575 | `"Simulating audience view…"` |
| 6662 | Panel actions: "Identity", "Iris inference", "Rename with AI", "Find Similar", "Open in Finder" |
| 7055 | `"Iris request timed out. Try a shorter question."` |
| 7057 | `"Iris is unavailable: "` / `"Make sure Ollama is running."` |
| 7794–7795 | `"Not signed in"` / `"Sync your vault across devices"` |
| 7803 | `"Local User"` |
| 7857 | `"Create local account"` |
| 7865–7867 | `"Google sign-in"` / `"Apple sign-in"` / `"Email sign-in"` |
| 7886 | `"Email is required."` |
| 7935 | `"files"` / `"—"` |
| 7947 | `"Runtime model · local"` |
| 8036 | `"present"` / `"missing"` |

---

## G. Hardcoded Audience Fallback Data (lines 6417–6448)

Complete fallback audience definitions with fixed scores, names, icons, and summaries:

| Field | Recruiter | Investor | Lender | Stranger |
|-------|-----------|----------|--------|----------|
| id | `"recruiter"` | `"investor"` | `"lender"` | `"stranger"` |
| name | `"Recruiter read"` | `"Investor read"` | `"Lender read"` | `"Stranger read"` |
| icon | 👤 | 💰 | 🏛 | 👁 |
| score | 80 | 76 | 72 | 68 |

---

## H. Hardcoded CSS Selector Strings

| Line | Selector |
|------|----------|
| 2 | `#scene` |
| 3 | `.viewport` |
| 4 | `#workspace-cards` |
| 5 | `#onboard` |
| 6 | `#scanBtn` |
| 7 | `#run` |
| 8 | `#search` |
| 9 | `.leftnav` |
| 10 | `#mobileNav` |
| 11 | `#leftnavSettingsBtn` |
| 12 | `#tooltip` |
| 13 | `#inspector` |
| 14 | `#counts` |
| 15 | `#statusbarIndex` |
| 16 | `#statusSignals` |
| 17 | `#statusRun` |
| 18 | `#modeName` |
| 19 | `#messages` |
| 20 | `#draft` |
| 21 | `#chatForm` |
| 22 | `.chips` |
| 23 | `#irisModebar` |
| 24 | `#irisEntityBar` |
| 25 | `#irisEntityLabel` |
| 26 | `#irisAudienceSelect` |
| 27 | `.topbar-presence` |
| 28 | `.topbar-presence-dot` |
| 29 | `.topbar-avatar` |
| 30 | `#logoLockup` |
| 31 | `#logoFallback` |

---

## I. Hardcoded Mode Names (used as strings throughout)

| Lines | Mode Name |
|-------|-----------|
| 44, 106, etc. | `"workstreams"` |
| 45, 107, etc. | `"topology"` |
| 46, 108, etc. | `"timeline"` |
| 47, 109, etc. | `"universe"` |
| 48, 110, etc. | `"iris"` |
| 49, 111, etc. | `"vault"` |
| 50, 112, etc. | `"audiences"` |
| 51, 113, etc. | `"simulations"` |
| 52, 114, etc. | `"exports"` |
| 53, 115, etc. | `"onboard"` |

These appear in `URL_MODE_ALLOW` (`105–116`), `modeTitle` (`43–54`), `ModeManager` (`704–714`), keyboard bindings (`667–675`), and throughout the codebase.

---

## J. Hardcoded Identity Mode Names

| Line | Value |
|------|-------|
| 530 | `["entity", "compare", "audience", "contradiction", "audit"]` |
| 556 | `IDENTITY_MODES` set with same values |
| 498–506 | Iris mode: `"report"`, `"archive"`, `"mirror"`, `"retune"`, `"entity"`, `"compare"`, `"audience"`, `"contradiction"`, `"audit"` |

---

## K. Other Notable Hardcoded Values

| Line | Value | Context |
|------|-------|---------|
| 213 | `120` | Logo minimum natural width |
| 357 | Regex `^(\\d{4})(\\d{2})(\\d{2})-(.+)$` | Run ID parsing |
| 360 | `"Run: "` | Run label prefix |
| 698 | `"pan"` | Default map tool |
| 1029 | `"high"`/`"medium"`/`"low"` | Confidence level strings |
| 1289 | `{ path: "" }` | Empty file fallback |
| 1429 | `5` | Max narrative labels |
| 1442 | `120` | Default mini-globe count |
| 1456 | `2` | Max pixel ratio |
| 1487 | `60` | Sphere geometry radius |
| 1487 | `22` | Sphere segments |
| 1755 | `10` | Vault table rows |
| 1964 | `16` | Sim workstream rows |
| 1990 | `3` | Sim auto-check count |
| 1995 | `8` | Sim slider max calc |
| 2400 | `"America/Chicago"` | Default timezone |
| 6958 | `16` | Max glow clamp |
| 7271 | `256` | Sprite canvas width |
| 7272 | `64` | Sprite canvas height |
| 7282 | `110` | Sprite scale X |
| 7282 | `28` | Sprite scale Y |
| 7529 | `2166136261` | FNV hash offset |
| 7530 | `16777619` | FNV hash prime |
| 7531 | `4294967295` | Hash normalization |
