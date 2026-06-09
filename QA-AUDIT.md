# QA Audit Report — Optic Frontend (app.js + app.css)

**Date:** 2026-06-06  
**Files audited:**
- `/backend/src/ctxorg/static/app.js` (8834 lines)
- `/backend/src/ctxorg/static/app.css` (4470 lines)

---

## 1. Hardcoded Values

### 1.1 Fake / hardcoded fallback data
| # | File | Line(s) | Description |
|---|------|---------|-------------|
| 1 | app.js | 6532–6563 | `defaultAudiences()` returns 4 hardcoded audience objects with fixed scores (80, 76, 72, 68) and placeholder summaries. Used as fallback in 11 call sites when the real `/api/audiences` endpoint returns empty. |
| 2 | app.js | 6255–6263 | `renderUniverseRail()` — hardcoded fake metrics: "Estimated reach 68%", "Top strength Technical depth", "Watchouts Low bias". Also "Breadth of interests 87 · High", "Network influence 74 · Moderate", "Privacy posture 68 · Moderate". All fake. |
| 3 | app.js | 6221–6227 | `renderUniverseRail()` — hardcoded fake category breakdown for hero/empty state: Documents 68%, Images 3%, etc. |
| 4 | app.js | 6278–6284 | `renderTopologySummary()` — same pattern: hardcoded fake category breakdown for hero state (Documents 98% etc.). |
| 5 | app.js | 6426 | `renderSimulationRail()` — fake projection math: `now + 6 + (r.id === "recruiter" ? 4 : 0)`. Computes "projected after" scores client-side instead of fetching from backend. |
| 6 | app.js | 6413–6415 | `renderAudienceRail()` — hardcoded "What to improve next" items: "Add recent metrics", "Increase leadership visibility", "Share public content". |
| 7 | app.js | 6383–6385 | `renderVaultRail()` — hardcoded sync statuses: "iCloud Drive Up to date", "Google Drive Up to date". |
| 8 | app.js | 6481–6492 | `renderSettingsRail()` — hardcoded system statuses: "Running", "Up to date", "Today", "Daily", "Ready". |
| 9 | app.js | 6513 | `renderIrisRail()` — hardcoded "Last 90 days" time range label. |
| 10 | app.js | 6521–6523 | `renderIrisRail()` — hardcoded "Quick tools" items: "Summarize this context", "Risk check", "Cleanup suggestions". |
| 11 | app.js | 5072–5084 | `TimelineMode.ghostLabel()` — hardcoded fake file labels for hero/empty timeline: "Executive summary", "Project plan", "Q2 deck", "Roadmap review", etc. |
| 12 | app.js | 1996 | `AudiencesMode.render()` — hardcoded signal type chips: `idx % 2 ? "Execution" : "Technical"`. |

### 1.2 Hardcoded UI strings
| # | File | Line(s) | Description |
|---|------|---------|-------------|
| 13 | app.js | 525–535 | `chooseIrisMode()` — all 9 placeholder strings are hardcoded. |
| 14 | app.js | 603–648 | `updateIrisChips()` — all 27 suggestion chips and prompts are hardcoded. |
| 15 | app.js | 2242–2251 | `ExportsMode.render()` — export type cards (PDF Report, Audience Snapshot, etc.) with hardcoded titles/descriptions. |
| 16 | app.js | 353–355 | `syncTopbarPresence()` — hardcoded dot colors: `#d97706`, `#2563eb`, `#16a34a`. |

### 1.3 Hardcoded color maps
| # | File | Line(s) | Description |
|---|------|---------|-------------|
| 17 | app.js | 34–41 | `palette` — category colors (`Documents: "#5aa7ff"`, etc.) hardcoded, not synchronized with CSS variables. |
| 18 | app.js | 1361–1369 | `catColor()` — returns hardcoded RGBA values for 5 categories. |
| 19 | app.js | 1371–1391 | `emoji()` — hardcoded keyword-to-emoji mapping. |
| 20 | app.js | 6731–6732 | `renderFile()` — `colorMap` object is declared but `ws.color` is never populated, making the lookup a no-op. |

---

## 2. Dead Code

| # | File | Line(s) | Description |
|---|------|---------|-------------|
| 1 | app.js | 3606–3872 | **Entire `OnboardMode` class is dead.** `ModeManager` (line 742) instantiates `new OnboardingMode()` — the newer 7-step class at line 8340. The old `OnboardMode` (no "ing") is never instantiated. |
| 2 | app.js | 7233–7243 | **`sendPrompt()` is dead.** Legacy non-streaming chat function. `streamIris()` (line 7054) is the active chat engine. `sendPrompt()` is never called. |
| 3 | app.js | 7298–7302 | **`kindFrom()` is dead.** Only called by `sendPrompt()`. |
| 4 | app.js | 6814–6828 | `renderInference()` — called from nowhere (only `renderPanel` → `renderFile` path commented out at line 6771: "renderInference() removed"). |
| 5 | app.js | 6830–6878 | `drawInference()` and `renderClaims()` — only called by `renderInference()`. |
| 6 | app.js | 6880–6891 | `bindInferEvidence()` — only called by `drawInference()`. |
| 7 | app.css | 559 | `.cluster-label::before` — applies an invisible border overlay; `opacity` is never set (defaults to 1 but border color is `rgba(...,0.10)` making it barely visible). Possibly intentional but adds no visible effect at zoom levels < 1. |
| 8 | app.css | 2743 | `.ada` — legacy class alias, no JS references found. |

---

## 3. Inconsistent Styles

### 3.1 Naming inconsistencies
| # | File | Line(s) | Description |
|---|------|---------|-------------|
| 1 | app.css | 262–263 | `.leftnav` (no hyphen) vs `.mobile-nav` (with hyphen) — inconsistent naming convention. |
| 2 | app.css | 1670 vs 1662 | `.ws-sort-wrap` is what JS generates (line 945), but CSS also defines `.home-sort-wrap` (unused duplicate). |
| 3 | app.css | 1641, 1648 | `.home-controls-main` and `.home-controls-end` defined but never referenced in JS. |
| 4 | app.css | 1698, 1654 | `.home-view-toggle` and `.ws-view` — duplicate style blocks for view toggle. `.home-view-btn` and `.ws-view-btn` are identical with different class names. JS uses `.ws-view-btn`. |
| 5 | app.css | 1776–1788 | `.cards-grid` list view selector chain: `.view-list`, `.is-list`, `.list`, `[data-view="list"]` — three different class names for the same behavior. JS only sets `.view-list`. |

### 3.2 Dual class patterns
| # | File | Line(s) | Description |
|---|------|---------|-------------|
| 6 | app.js | 1155 | Cards use BOTH `ws-card` and `ws-card2` classes simultaneously. CSS defines both blocks (lines 1849 and 2010) causing confusion about which styles apply — `ws-card2` overrides many properties. |
| 7 | app.css | 1849–2007 | `.ws-card` block — old card styling. Still present but overridden by `.ws-card2` (line 2010). Consider removing. |

### 3.3 CSS duplicate blocks
| # | File | Line(s) | Description |
|---|------|---------|-------------|
| 8 | app.css | 1678–1686, 1688–1696 | `.home-sort` and `.ws-sort` — identical styles. `.home-sort` is unused; JS generates `#wsSort.ws-sort`. |
| 9 | app.css | 1710–1728 | `.home-view-btn` and `.ws-view-btn` — identical styles. `.home-view-btn` is unused. |
| 10 | app.css | 1730–1750 | `.home-view-btn:hover`, `.home-view-btn.active` and their `.ws-view-btn` counterparts — duplicate hover/active rules. |

### 3.4 Overriding styles at bottom of CSS
| # | File | Line(s) | Description |
|---|------|---------|-------------|
| 11 | app.css | 3291–4471 | Large "Ultra Route + Rail polish" and "Native Proprietary Brand Pass" sections (lines 3291–4470) override styles defined earlier in the file. This creates a maintenance burden — any earlier changes may be silently overridden. e.g., `.app` grid columns defined at line 77, overridden at line 3292. `.topbar` styles at line 151, overridden at lines 3295, 4295, 4412. |
| 12 | app.css | 4437 | `#run { display: none; }` — hides the run selector, contradicting early styling (line 248). If this is intentional, the element shouldn't be rendered at all. |

---

## 4. Missing Error States

| # | File | Line(s) | Description |
|---|------|---------|-------------|
| 1 | app.js | 315–326 | `refreshSimulations()` — catches all errors silently, returns `[]`. No visual feedback if simulations fail to load. |
| 2 | app.js | 252–263 | `refreshAudiences()` — catches all errors silently, returns `[]`. No feedback. |
| 3 | app.js | 1838–1851 | `VaultMode.loadAnalytics()` — catches errors silently, sets empty arrays. The Vault view shows "No files in view" with no explanation. |
| 4 | app.js | 6272–6361 | `renderTopologySummary()` — while audiences are loading, shows a pulse-dot "Loading audiences…" that never transitions to an error state if the fetch fails (the `Promise.all` catch isn't connected to the UI). |
| 5 | app.js | 2231–2238 | `ExportsMode.refreshHistory()` — catches errors silently, sets `this.history = []`. No "failed to load history" state. |
| 6 | app.js | 7054–7207 | `streamIris()` — when streaming fails, shows a static error message with no "retry" or "try again" UI affordance. |
| 7 | app.js | 2327–2353 | `ExportsMode.click()` export action — shows failure text inline but provides no retry mechanism. |
| 8 | app.js | 2167–2171 | `SimulationsMode.showEval()` — accesses `rec.confidence_interval.low` / `.high` without null-safety. If API returns a scenario without confidence_interval, this throws. |
| 9 | app.js | 301–313 | `refreshSettings()` — when fetch fails, returns `state.settings` which could be `null`. The `render()` method in `SettingsMode` (line 2502) destructures `state.settings || {}` so this is safe, but other consumers might not. |

---

## 5. Fake / Placeholder Data Summary

The following functions contain entirely fabricated data used as display content when real API data is unavailable:

| Function | Lines | Fake Data |
|----------|-------|-----------|
| `defaultAudiences()` | 6532–6563 | 4 audiences with hardcoded scores (80/76/72/68) |
| `renderUniverseRail()` | 6255–6263 | Iris insight metrics (87/74/68), reach/strength/watchouts |
| `renderUniverseRail()` | 6221–6227 | Category breakdown (68%/3%/2%/1%/0.5%) |
| `renderTopologySummary()` | 6278–6284 | Category breakdown (98%/1%/0.8%/0.4%/0.2%) |
| `renderSimulationRail()` | 6426 | Projected scores calculated as `now + 6 + condition` |
| `renderAudienceRail()` | 6413–6415 | "What to improve next" suggestions |
| `renderVaultRail()` | 6383–6385 | Sync statuses (iCloud, Google Drive, Local) |
| `renderSettingsRail()` | 6481–6492 | System health statuses |
| `renderIrisRail()` | 6513, 6521–6523 | Time range + quick tool labels |
| `TimelineMode.ghostLabel()` | 5072–5084 | Fake file names for hero timeline |
| `AudiencesMode.render()` | 1996 | Signal type chips ("Execution"/"Technical") |

**Impact:** Users see fabricated data when the backend returns empty results, creating a false impression that analysis is complete.

---

## 6. Code Quality / Structural Issues

| # | File | Line(s) | Description |
|---|------|---------|-------------|
| 1 | app.js | 101 | Top-level `boot()` call with `.catch()` — errors in boot only set `el.inspector.innerHTML`. No retry mechanism, no "reload" button. |
| 2 | app.js | 5876–5878 | `visibleNodes()` simply returns `state.nodes` — no actual filtering. The function name is misleading. |
| 3 | app.js | 928–966 | `WorkstreamsMode.renderShell()` — event listeners removed and re-added on every re-render. Could use a single delegated listener. |
| 4 | app.js | 1083–1094 | Duplicate click handler — `renderInspector()` adds two separate `click` listeners for `[data-mode-jump]` selectors, one general and one specific to `[data-mode-jump='iris']`, causing double-firing. |
| 5 | app.js | 1902–1909 | `VaultMode.render()` — toolbar buttons ("All folders", "Type: All", "Size: Any", "Modified: Any time", "Source: All", "More filters") are non-functional; click does nothing. |
| 6 | app.js | 2016–2017 | `AudiencesMode.render()` — "Manage audiences" and "Export audience brief" buttons are non-functional. |
| 7 | app.js | 2121–2123 | `SimulationsMode.render()` — "Save scenario", "History", "Saved scenarios" buttons are non-functional placeholders. |
| 8 | app.css | 210 | Comment: "Legacy top modebar retired in favor of .iris-modebar" — but no legacy modebar CSS exists for cleanup. |
| 9 | app.js | 1987–1988 | `AudiencesMode.render()` — `AudienceModal` uses `data-aud` for both cards AND buttons, causing the click handler to have complex disambiguation logic (line 2041–2049). |
| 10 | app.js | 1669 | `WorkstreamsMode.stopMiniGlobe()` — disposes Three.js resources but the `this.globeTick` variable is never reset to 0, which could cause a jump if `startMiniGlobe` is called again. |

---

## 7. CSS-Specific Issues

| # | Line(s) | Description |
|---|---------|-------------|
| 1 | 57 | Universal selector reset removes all margin/padding including from form elements that need native spacing. |
| 2 | 80 | `100vw` / `100vh` on `.app` — causes horizontal scrollbar on macOS with overlay scrollbars when vertical scrollbar appears. Should use `100dvh`. |
| 3 | 86–98, 100–110 | Pseudo-elements `body::before` and `body::after` are fixed decorative gradients that add visual noise and performance cost. Consider making them opt-in. |
| 4 | 121, 131 | `backdrop-filter` with `blur(0px)` on `.glass` — zero blur is a no-op that still triggers compositing. Remove the blur function call entirely. |
| 5 | 190, 207 | `[hidden] { display: none; }` — duplicates native UA stylesheet behavior but may conflict with flex/grid display when `hidden` is removed dynamically. |
| 6 | 4437 | `#run { display: none; }` — conflicts with the element being styled for visibility earlier. If this is permanent, the run selector should be removed from HTML. |
| 7 | 3291–4470 | "Brand Pass" section at file bottom re-overrides many styles (border-radius, shadows, backgrounds, transitions) — should be merged into the original declarations. |

---

## 8. Findings Tally

| Category | Count |
|----------|-------|
| Hardcoded values (data + UI) | 20 |
| Dead code blocks | 8 |
| Inconsistent styles | 12 |
| Missing error states | 9 |
| Fake/placeholder data functions | 11 |
| Code quality issues | 10 |
| CSS-specific issues | 7 |
| **Total findings** | **77** |

---

## 9. Recommendations

1. **P0 — Remove dead `OnboardMode` class** (lines 3606–3872). It shadows the active `OnboardingMode` and wastes ~267 lines.
2. **P0 — Move `defaultAudiences()` data to backend.** 11 call sites fall back to hardcoded data. Add a server-side default or improve the `/api/audiences` endpoint to always return complete data.
3. **P1 — Replace all fake rail data** (Universe, Topology, Simulation, Audience, Vault, Settings, Iris rails) with either real API-sourced data or honest empty states ("No data yet — run a scan").
4. **P1 — Remove dead `sendPrompt()` / `kindFrom()` / inference functions** (lines 6814–6891, 7233–7243, 7298–7302).
5. **P1 — Merge CSS overrides.** Move the "Brand Pass" section (lines 3291–4470) into the original style declarations rather than re-overriding at the bottom.
6. **P2 — Add error states** for `refreshSimulations()`, `refreshAudiences()`, `VaultMode.loadAnalytics()`, and the topology audience loader.
7. **P2 — Clean up CSS duplicates**: `.home-sort`/`.ws-sort`, `.home-view-btn`/`.ws-view-btn`, the 3 redundant list-view class names on `.cards-grid`.
8. **P2 — Remove non-functional UI buttons** or wire them to real actions (Vault toolbar, Audience "Manage"/"Export", Simulation "Save"/"History").
9. **P3 — Remove `ws-card` styles** now that `ws-card2` is the primary card class.
10. **P3 — Resolve dual event listener** in `renderInspector()` (lines 1083–1094).
