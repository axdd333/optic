# Optic — Agent Goal Document

## 0. Mission
Transform the existing Optic prototype into a **production-quality, fully-functional local SaaS** that feels like a real product. Every element visible in the UI must be wired to live data. The app analyzes a user's local file system to surface what humans and algorithms can infer about them — their identity, work, relationships, behavior. All analysis is private and on-device.

---

## 1. Stack Reference

| Layer | Technology |
|---|---|
| Backend | Python (`src/ctxorg/`), stdlib HTTPServer, SQLite via `db.py` |
| LLM | Gemma 4 via Ollama (`ollama.py`) |
| Frontend | Vanilla JS SPA (`src/ctxorg/static/app.js` ~2900 lines) |
| Styles | Single CSS file (`src/ctxorg/static/app.css` ~1400 lines) |
| Server | `python -m ctxorg serve --cfg config.json --host 127.0.0.1 --port 8765` |

**Do not add npm, React, or build tools. Keep vanilla JS + plain CSS.**

---

## 2. Existing API Routes (server.py)

```
GET  /api/health
GET  /api/runs
GET  /api/graph          → { nodes[], edges[], run }
GET  /api/workstreams    → { workstreams[] }
GET  /api/report         → workstream report
GET  /api/status         → scan status
GET  /api/home           → home panel data
GET  /api/infer          → node inference
GET  /api/analyze
POST /api/scan           → { folders[] }
POST /api/iris           → streaming LLM chat (chunked)
POST /api/rename
POST /api/embed/run
```

**New routes to add** (see Section 6).

---

## 3. Existing Workstream Card Shape

Each card from `/api/workstreams` currently returns:
```json
{
  "id": "cluster-42",
  "name": "Research & Learning",
  "confidence": 0.87,
  "file_count": 142,
  "size": 48234567,
  "topics": ["research", "notes", "papers"],
  "summary": "A collection of research notes...",
  "key_files": [
    { "path": "/Users/.../Research.txt", "ext": ".txt", "size": 14200 }
  ],
  "folders": ["Research", "Documents"],
  "category_breakdown": { "Documents": 0.7, "Code": 0.2, "Other": 0.1 }
}
```

---

## 4. Goal State — Home View

### 4a. Layout Changes
The Home view canvas area (`#workspace-cards`) must be completely redesigned:

```
┌─────────────────────────────────────────────────────┐
│  Home                                               │
│  Optic analyzes your digital footprint to surface   │
│  what humans and algorithms infer about you.        │
├─────────────────────────────────────────────────────┤
│ [All clusters] [Identity] [Work & skills] [Life]    │
│ [Relations] [Behavior]          Sort: Relevance ▾  │
│                                       [⊞] [☰]       │
├─────────────────────────────────────────────────────┤
│  ┌──────────────────────┐  ┌─────────────────────┐  │
│  │ 📚 Research & Learning│  │ 💼 Career & Work     │  │
│  │ High · 92%           │  │ High · 89%          │  │
│  │                      │  │                     │  │
│  │ You invest heavily in│  │ You work in AI/ML   │  │
│  │ technical depth...   │  │ and value impact... │  │
│  │                      │  │                     │  │
│  │ TOP EVIDENCE         │  │ TOP EVIDENCE        │  │
│  │ 📄 Research.txt  Docs│  │ 📄 Resume.pdf  Docs │  │
│  │ 📄 Exec Summary  Docs│  │ 🔗 LinkedIn profile │  │
│  │ 📝 ai-safety-notes   │  │ 📊 company-roadmap  │  │
│  │                      │  │                     │  │
│  │ →View in map         │  │ →View in map        │  │
│  │ Inspect evidence     │  │ Inspect evidence    │  │
│  │ Simulate audience    │  │ Simulate audience   │  │
│  └──────────────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 4b. Cluster Category Tabs
Filter workstream cards. Map workstream names to categories:
- **Identity**: clusters whose topics include "identity", "personal", "bio", "profile", "resume", "cv", "social"
- **Work & skills**: topics include "work", "code", "project", "career", "job", "research", "skill", "learning"
- **Life**: topics include "photo", "travel", "health", "fitness", "journal", "diary", "life"
- **Relations**: topics include "contact", "email", "message", "social", "people", "friend", "family"
- **Behavior**: topics include "habit", "finance", "purchase", "browse", "download", "activity"
- **All clusters**: show everything

Tabs are pill-style buttons. Active tab is `var(--accent)` filled. Filter client-side — no extra API call needed.

### 4c. Sort & View Controls
- **Sort dropdown**: "Relevance" (default, by confidence desc), "Recent" (by mtime of newest file), "Size" (by total bytes), "A–Z"
- **View toggles**: grid view (default, 2-3 cols) and list view (1 col, more compact)
- All client-side only.

### 4d. Redesigned Card
Replace the current `.ws-card` entirely. New structure:

```html
<div class="ws-card2">
  <div class="ws-card2-head">
    <div class="ws-icon2" style="background: {color}">
      <span class="ws-emoji">{emoji}</span>
    </div>
    <div class="ws-title-block">
      <div class="ws-name2">{name}</div>
      <div class="ws-conf2">
        <span class="ws-conf-dot {high|medium|low}"></span>
        {High|Medium|Low} · {confidence}%
      </div>
    </div>
  </div>
  <p class="ws-desc2">{summary}</p>
  <div class="ws-evidence-block">
    <div class="ws-evidence-label">TOP EVIDENCE</div>
    <div class="ws-evidence-row">
      <span class="ws-ev-icon">{file_icon}</span>
      <span class="ws-ev-name">{filename}</span>
      <span class="ws-ev-loc">{folder}</span>
    </div>
    <!-- up to 3 evidence rows -->
  </div>
  <div class="ws-actions2">
    <button class="ws-action-primary" data-ws-id="{id}" data-action="map">→ View in map</button>
    <button class="ws-action-ghost" data-ws-id="{id}" data-action="inspect">Inspect evidence</button>
    <button class="ws-action-ghost" data-ws-id="{id}" data-action="simulate">Simulate audience</button>
  </div>
</div>
```

**Emoji mapping** (by dominant category or topics):
- Research/Learning: 📚, Career/Work: 💼, Social: 💬, Finance: 💳, Writing: ✍️, Photos: 📷, Travel: ✈️, Health: 🏃, Code: 💻, Config/System: ⚙️, Other: 📁

**Confidence dot colors**: High (≥80%) = green `#22c55e`, Medium (50–79%) = amber `#f59e0b`, Low (<50%) = coral `#ef4444`

**Icon background**: derive from category color at 15% opacity.

### 4e. Card Actions Wiring
- **→ View in map**: call `state.manager.switch("topology")`, then highlight/select that cluster's nodes
- **Inspect evidence**: expand the card in-place (toggle `.ws-expanded` class) to show all key_files, not just top 3
- **Simulate audience**: open an audience simulation modal (Section 7)

### 4f. Right Panel — "Your digital self"
Replace the `inspector` content on Home mode with a rich "digital self" panel. **Backend must supply this via `/api/home`** (already exists — expand its response).

```
YOUR DIGITAL SELF
Private. Local. Computed on-device.

[Animated particle globe — Three.js sphere, same as Universe but smaller,
 ~180px diameter, using canvas inside .panel-globe, colorful dots orbit]

SIGNALS INDEXED     NARRATIVES    CONTRADICTIONS
128,473             32            7

AUDIENCES           EXPOSURES     LAST ANALYZED
8                   12            2h ago

TOP INFERRED NARRATIVES
[AI builder] [Independent thinker] [Global explorer]
[Privacy conscious] [High agency]

─────────────────────────────
◆ Iris                          ⋮
Insight summary

You are a technically sophisticated builder
with a strong track record of independent
research and execution.

You value autonomy, privacy, and long-term
impact over short-term validation.

Key strengths
✓ Deep technical curiosity
✓ Consistent execution
✓ Strong writing & communication

● On-device analysis    Local vault ●
```

The globe is a miniature Three.js sphere (same renderer pattern as UniverseMode). It auto-rotates. Node count = min(200, total files). Colors from palette.

The "Iris Insight summary" is a persisted LLM-generated summary of the user's corpus. Fetch once from `/api/home`, cache in `state.homeSummary`. If not yet generated, show a pulsing skeleton.

**Narratives** are short strings inferred from topic clusters (e.g., "AI builder" if Code+Research clusters are dominant). Generate these client-side from workstream data — no extra API call needed.

---

## 5. Goal State — Map View

### 5a. Cluster Nebulae
The topology canvas currently draws dots with `ctx.arc`. **Extend** (do not replace) the drawing pipeline to also render cluster blobs behind the nodes.

In `TopologyMode.draw()`, after `clearRect` and before `drawEdges()`, add a new `drawClusterNebulae(r)` call:

```javascript
drawClusterNebulae(r) {
  const ctx = this.ctx;
  // Group nodes by cluster
  const clusterGroups = new Map();
  for (const n of visibleNodes()) {
    const cid = n.cluster || n.category;
    if (!clusterGroups.has(cid)) clusterGroups.set(cid, []);
    clusterGroups.get(cid).push(n);
  }
  for (const [cid, nodes] of clusterGroups) {
    if (nodes.length < 3) continue;
    // Compute centroid in screen coords
    const pts = nodes.map(n => this.screen(n));
    const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
    const r2 = Math.max(40, Math.sqrt(pts.reduce((s, p) =>
      s + (p.x - cx) ** 2 + (p.y - cy) ** 2, 0) / pts.length) * 1.8);
    const color = palette[nodes[0].category] || "#7c8291";
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r2);
    grad.addColorStop(0, color + "28");
    grad.addColorStop(0.6, color + "10");
    grad.addColorStop(1, color + "00");
    ctx.beginPath();
    ctx.arc(cx, cy, r2, 0, Math.PI * 2);
    ctx.fillStyle = grad;
    ctx.fill();
  }
}
```

### 5b. Cluster Label Overlays (HTML, not canvas)
For each cluster centroid, render an HTML label div inside `.viewport` (positioned absolutely in screen space, updated on every draw/pan/zoom). These are `<div class="cluster-label">` elements with:
```html
<div class="cluster-label" style="left: {sx}px; top: {sy}px">
  <span class="cluster-label-icon">{emoji}</span>
  <div>
    <div class="cluster-label-name">{name}</div>
    <div class="cluster-label-desc">{shortDesc}</div>
  </div>
</div>
```
Cluster name and emoji come from matching by dominant topics against the workstream cards (same data already fetched). Short desc is the first 4–5 words of the workstream summary.

Create a `<div id="cluster-labels" class="cluster-labels-layer">` inside `.viewport` (sibling to `#scene`), cleared and re-populated on each render call. At low zoom (`cam.k < 0.4`), hide labels.

### 5c. Map Bottom Toolbar
Add a `.map-toolbar` div inside `.viewport`, absolutely positioned at the bottom center:
```html
<div id="mapToolbar" class="map-toolbar" hidden>
  <button class="map-tool active" data-tool="pan" title="Pan">✥</button>
  <button class="map-tool" data-tool="select" title="Box select">⬚</button>
  <button class="map-tool" data-tool="focus" title="Focus selection">◎</button>
  <div class="map-toolbar-sep"></div>
  <button class="map-zoom-out" title="Zoom out">−</button>
  <span class="map-zoom-val">100%</span>
  <button class="map-zoom-in" title="Zoom in">+</button>
</div>
```
Show on topology mount, hide on unmount. Zoom buttons adjust `cam.k`. Zoom % updates on every draw. Tool buttons toggle active tool (pan is default — existing behavior; select will implement box select in a future iteration, for now just highlight the button).

### 5d. Map Right Panel — Audience Views + Iris Summary
When in topology mode and nothing is selected, the inspector panel shows:

```
Map
────────────────────────
SIGNALS SHOWN   CLUSTERS
12,486          87

MODIFIED TODAY  AUDIENCE VIEWS
1,073           4

AUDIENCE VIEWS
What different people & systems infer

[👤] Recruiter read           87%  ›
     Most likely a strong fit...

[💰] Investor read            82%  ›
     High builder signal...

[🏛] Lender read              78%  ›
     Low credit risk...

[👁] Stranger read            61%  ›
     Creative, thoughtful...

─────────────────────────────
IRIS SUMMARY
Your digital footprint shows a coherent,
high-signal identity...

Coherence        ████████████ High
Anomaly risk     ███          Low
```

Audience data comes from `/api/audiences` (new route, Section 6). Clicking an audience row opens the Audience Simulation modal (Section 7).

Add drag/scroll/click hint line at the very bottom-right of the canvas: `"Drag to rotate · Scroll to zoom · Click to focus"` — shown as a `<div class="canvas-hint">` inside `.viewport`.

---

## 6. New Backend Routes (server.py)

### 6a. GET /api/audiences
Returns synthetic audience read profiles derived from the user's workstream data. These are computed heuristically (no LLM call needed — use existing cluster data).

```python
def audiences_payload(req, cfg):
    """GET /api/audiences — heuristic audience read profiles."""
    ws = _load_workstreams(cfg)  # reuse existing workstream loader
    # Derive audience scores from topic overlap
    profiles = [
        {
            "id": "recruiter",
            "name": "Recruiter read",
            "icon": "👤",
            "score": _audience_score(ws, ["career", "code", "project", "research", "work"]),
            "summary": "Most likely a strong fit for technical leadership roles.",
        },
        {
            "id": "investor",
            "name": "Investor read",
            "icon": "💰",
            "score": _audience_score(ws, ["finance", "startup", "research", "code", "project"]),
            "summary": "High builder signal with long-term owner mindset.",
        },
        {
            "id": "lender",
            "name": "Lender read",
            "icon": "🏛",
            "score": _audience_score(ws, ["finance", "documents", "tax", "income"]),
            "summary": "Low credit risk with stable financial behavior.",
        },
        {
            "id": "stranger",
            "name": "Stranger read",
            "icon": "👁",
            "score": _audience_score(ws, ["photo", "travel", "social", "writing", "life"]),
            "summary": "Creative, thoughtful, and globally curious.",
        },
    ]
    profiles.sort(key=lambda p: -p["score"])
    send_json(req, {"audiences": profiles})

def _audience_score(ws, keywords):
    """Score 0–100 based on topic overlap with audience keywords."""
    if not ws:
        return 50
    hits = 0
    total_weight = 0
    for card in ws:
        conf = card.get("confidence", 0.5)
        topics = [t.lower() for t in card.get("topics", [])]
        name = card.get("name", "").lower()
        text = " ".join(topics) + " " + name
        overlap = sum(1 for kw in keywords if kw in text)
        hits += overlap * conf
        total_weight += len(keywords) * conf
    raw = hits / max(total_weight, 1)
    # Scale to 55–95 range so scores feel realistic
    return round(55 + raw * 40)
```

Add to `route()`:
```python
if path == "/api/audiences":
    return send_json(req, audiences_payload(req, cfg))
```

### 6b. GET /api/home (extend existing)
The existing `/api/home` should be extended to return:
```json
{
  "file_count": 3574,
  "total_size": 3700000000,
  "workstreams_count": 30,
  "coherence_avg": 0.50,
  "signal_count": 128473,
  "source_count": 1236,
  "last_analyzed_ago": "2h ago",
  "narratives": ["AI builder", "Independent thinker", "Privacy conscious"],
  "exposures": 12,
  "iris_summary": "You are a technically sophisticated builder..."
}
```
The `iris_summary` should be generated once by Ollama (fire-and-forget on first load, cache in the SQLite db or a sidecar `.json` file). If not available, return `null`. The client shows a skeleton loader when null.

`signal_count` = total item count in current run. `source_count` = count of unique parent folders. `narratives` = top 3–5 topic strings from the highest-confidence workstreams. `last_analyzed_ago` = human-readable delta from run timestamp.

### 6c. GET /api/simulate/{audience_id}
```python
def simulate_payload(req, cfg, audience_id):
    """Simulate how a specific audience reads the user's footprint."""
    ws = _load_workstreams(cfg)
    audience_map = {
        "recruiter": {"perspective": "hiring manager at a tech company", ...},
        "investor":  {"perspective": "early-stage VC", ...},
        ...
    }
    profile = audience_map.get(audience_id)
    if not profile:
        return send_err(req, "Unknown audience", 404)
    # Build a structured report without LLM (heuristic)
    highlights = [w["name"] for w in ws[:5] if w.get("confidence", 0) > 0.7]
    risks = [w["name"] for w in ws if w.get("confidence", 0) < 0.5]
    send_json(req, {
        "audience_id": audience_id,
        "score": _audience_score(ws, profile.get("keywords", [])),
        "highlights": highlights,
        "risks": risks,
        "narrative": f"From a {profile['perspective']}'s view: ...",
    })
```

---

## 7. Audience Simulation Modal

When the user clicks "Simulate audience" on a card OR an audience row in the Map panel, show a full-screen modal overlay (separate from settings overlay):

```html
<div id="audienceModal" class="audience-modal-overlay" hidden>
  <div class="audience-modal glass">
    <div class="audience-modal-head">
      <div class="audience-modal-who">
        <span class="audience-modal-icon">{icon}</span>
        <div>
          <div class="audience-modal-name">{name}</div>
          <div class="audience-modal-sub">How they read your footprint</div>
        </div>
      </div>
      <div class="audience-modal-score">
        <span class="audience-score-num">{score}%</span>
        <span class="audience-score-lbl">match</span>
      </div>
      <button class="audience-modal-close">✕</button>
    </div>
    <div class="audience-modal-body">
      <div class="audience-section">
        <div class="audience-section-title">WHAT THEY SEE</div>
        <div class="audience-narrative">{narrative}</div>
      </div>
      <div class="audience-section">
        <div class="audience-section-title">YOUR STRONGEST SIGNALS</div>
        <div class="audience-highlights">
          <!-- chip for each highlight -->
        </div>
      </div>
      <div class="audience-section">
        <div class="audience-section-title">GAPS & RISKS</div>
        <div class="audience-risks">
          <!-- chip for each risk -->
        </div>
      </div>
    </div>
  </div>
</div>
```

---

## 8. Leftnav Additions

Add below "Audiences" in the secondary nav:

```html
<button class="leftnav-item leftnav-item--dim">
  <svg class="nav-ico" viewBox="0 0 16 16" ...><!-- beaker/flask icon --></svg>
  <span>Simulations</span>
</button>
<div class="leftnav-divider"></div>
<button class="leftnav-item leftnav-item--dim">
  <svg class="nav-ico" viewBox="0 0 16 16" ...><!-- arrow-up-from-bracket --></svg>
  <span>Exports</span>
</button>
<button class="leftnav-item" data-mode="settings" id="settingsNavBtn">
  <svg class="nav-ico" viewBox="0 0 16 16" ...><!-- gear --></svg>
  <span>Settings</span>
</button>
```

The "Settings" item in the leftnav should open the existing settings overlay (same as the account button). Wire it to call `document.querySelector('#settingsBtn').click()`.

---

## 9. Status Bar Enhancement

Update the statusbar HTML to:
```html
<footer class="statusbar">
  <span class="statusbar-privacy">
    <svg ...><!-- shield --></svg>
    All analysis is private and local
  </span>
  <span class="statusbar-index" id="statusbarIndex">
    Indexed: — · — signals from — sources
  </span>
  <span class="statusbar-version">Optic v0.1.0</span>
</footer>
```

JS: after loading graph, update `#statusbarIndex` with live data from `/api/home`:
```javascript
const d = await getJson("/api/home");
document.querySelector("#statusbarIndex").textContent =
  `Indexed: ${fmt(d.last_analyzed_ago)} · ${d.signal_count.toLocaleString()} signals from ${d.source_count.toLocaleString()} sources`;
```

---

## 10. CSS Design Rules to Follow

- Use existing CSS variables — do not introduce new ones unless genuinely needed
- All new components must follow the light glass aesthetic: `rgba(255,255,255,0.85)` backgrounds, `var(--line)` borders, `var(--text)`/`var(--muted)`/`var(--subtle)` text hierarchy
- Animations: `animation: cardIn .28s var(--ease) both` for card entrances; never use `animation: none` unless `prefers-reduced-motion`
- Never use `!important` except to override the `.glass` base class when needed
- `[hidden] { display: none }` pattern already established — always add `selector[hidden] { display: none }` before the selector's display rule if display is explicitly set
- Z-index layers: canvas=1, cluster-labels=5, map-toolbar=10, tooltip=30, settings-overlay=200, audience-modal=210
- Glass panels: always combine `backdrop-filter: blur(28px) saturate(180%)`, border `rgba(255,255,255,0.42)`, and `box-shadow: var(--glass-shadow)`

---

## 11. JS Patterns to Follow

- All `fetch` uses `getJson(url)` / `postJson(url, data)` helpers at bottom of app.js
- DOM queries at startup go in the `const el = { ... }` block at top
- Mode-specific logic goes inside the mode class (`class WorkstreamsMode`, `class TopologyMode`, etc.)
- State lives in `state.*` object — add new keys there, never use global variables directly
- Animation loops use `requestAnimationFrame` — always cancel in `unmount()`
- New overlays follow the settings overlay pattern: hidden by default (`hidden` attribute), opened by toggling `.hidden`, dismissed by Escape key + backdrop click
- Workstream data is cached in `state.workstreams` after first fetch — re-use it, don't re-fetch on every render

---

## 12. Quality Gates — MUST Pass Before Done

- [ ] Home cards show emoji icons, top evidence files, all 3 action buttons
- [ ] Category tabs filter cards client-side without page reload
- [ ] Sort dropdown works (relevance, recent, size, A–Z)
- [ ] "→ View in map" switches to topology and highlights the cluster
- [ ] "Simulate audience" opens the audience modal with real data from `/api/simulate/{id}`
- [ ] Right panel on Home shows globe, stats, narratives, Iris summary (skeleton if not ready)
- [ ] Map shows cluster nebula blobs behind nodes
- [ ] Cluster label divs appear at centroids, update on pan/zoom
- [ ] Map toolbar shows and zoom +/- works
- [ ] Map right panel shows audience scores from `/api/audiences`
- [ ] `/api/audiences` responds with valid JSON in < 200ms
- [ ] `/api/home` returns `signal_count`, `source_count`, `narratives`, `last_analyzed_ago`
- [ ] Status bar shows live indexed count
- [ ] Settings nav item in leftnav opens settings overlay
- [ ] No JS errors in console on any mode switch
- [ ] Timeline HUD correctly hidden outside Timeline mode (existing fix — do not regress)
- [ ] Universe canvas correctly hidden on mode switch (existing fix — do not regress)
- [ ] All `[hidden]` elements respect the pattern (`selector[hidden] { display: none }` in CSS)
- [ ] CSS version bumped to `-v22` in index.html when CSS changes, JS version to `-v22` when JS changes

---

## 13. File Edit Constraints

**Only edit these files** (do not add new files unless absolutely necessary):
- `src/ctxorg/static/index.html`
- `src/ctxorg/static/app.css`
- `src/ctxorg/static/app.js`
- `src/ctxorg/server.py`
- `src/ctxorg/workstreams.py` (only if adding a helper used by server.py)

**Do not touch**: `db.py`, `graph.py`, `ingest.py`, `scan.py`, `embed.py`, `ollama.py`, any test file, `config.json`, `pyproject.toml`.

---

## 14. Implementation Order (Recommended)

1. Backend: extend `/api/home`, add `/api/audiences`, add `/api/simulate/{id}`  
2. Status bar HTML + JS wiring  
3. Home card redesign (HTML template in JS + CSS)  
4. Category tabs + sort controls (client-side filtering)  
5. Home right panel "Your digital self" (globe + stats + narratives)  
6. Audience simulation modal (HTML + CSS + JS)  
7. Map: cluster nebula blobs (canvas drawing)  
8. Map: cluster label divs (HTML overlay layer)  
9. Map: toolbar (HTML + CSS + JS)  
10. Map: right panel audience views  
11. Leftnav: Simulations / Exports / Settings items  
12. Wire "→ View in map" to switch mode + highlight  
13. Final pass: CSS polish, version bumps, console error check  
