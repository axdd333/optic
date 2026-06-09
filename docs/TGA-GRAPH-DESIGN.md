# TGA Evidence Graph — 3-Level Visualization Design

> **Status**: Design Document — not yet implemented
> **Author**: Nova (Agent 4 • Graph) — Agent 16 (View) consult
> **Date**: 2026-06-08
> **Target**: Wave 2 integration milestone

---

## 0. Executive Summary

The TGA (Triple Graph Architecture) evidence graph is a **3-level, expandable, hierarchical visualization** that shows the full inference pipeline in a single navigable canvas:

```
L1: SIGNALS   →  detected patterns in the user's filesystem
L2: CLAIMS    →  audience-specific readings generated from signals  
L3: EVIDENCE  →  the concrete files, artifacts, and metadata that support or weaken each claim
```

Each level **expands from the one above**. A user clicks a Signal node (L1) to reveal its child Claims (L2). Clicking a Claim reveals its supporting/weakening Evidence (L3). Clicking an Evidence node opens the actual file or shows the raw artifact.

This replaces the file-centric TopologyMap (which shows all files indiscriminately) with an **audit-centric evidence map** that answers: *"What does Optic infer about me, from what evidence, and how strong is it?"*

---

## 1. Data Architecture

### 1.1 Three-Level Node Hierarchy

```
LEVEL 1 — SIGNAL NODES
├── Type: "signal"
├── Source: v1.db → signals table
├── Fields: id, category, description, severity, source_artifact_ids
├── Visual: Large circles (r=12–18px), colored by category
│
│   ── EDGE: "generates" (signal → claim) ──
│
├── LEVEL 2 — CLAIM NODES  
│   ├── Type: "claim"
│   ├── Source: v1.db → claims table
│   ├── Fields: id, title, audience_lens, claim, confidence_band,
│   │           supporting_evidence[], weakening_evidence[], counterargument
│   ├── Visual: Medium hexagons (r=8–12px), colored by audience lens
│   │
│   │   ── EDGE: "supported_by" / "weakened_by" (claim → evidence) ──
│   │
│   └── LEVEL 3 — EVIDENCE NODES
│       ├── Type: "artifact" / "document" / "file"
│       ├── Source: v1.db → artifacts + ctx.db → items
│       ├── Fields: id, path, type, content_preview, metadata
│       ├── Visual: Small squares/dots (r=3–6px), colored by file category
│       └── EDGE: "located_at" (evidence → file on disk)
```

### 1.2 Edge Types for TGA

| Edge Type | From | To | Meaning |
|-----------|------|----|---------|
| `generates` | signal | claim | This signal produced this claim |
| `supported_by` | claim | evidence | This artifact supports the claim |
| `weakened_by` | claim | evidence | This artifact weakens the claim |
| `contradicts` | claim | claim | Two claims conflict |
| `context_for` | evidence | evidence | Related evidence items |
| `derived_from` | evidence | file | Evidence came from this file |

### 1.3 Graph Population — What Must Be Built

**The EvidenceGraph (`optic/v1/graph.py`) is the canonical store.** Currently `_build_evidence_graph()` only populates user + sources + artifacts. The TGA graph requires extending it to include signals, claims, contradictions, and their relationships.

**New population function required in V1 server or pipeline:**

```python
def build_tga_evidence_graph() -> graph.EvidenceGraph:
    """Populate EvidenceGraph with signals→claims→evidence hierarchy."""
    eg = graph.EvidenceGraph()
    
    # L1: Add all signals as nodes
    for signal_row in db.signals:
        eg.add_node("signal", signal_row.id, 
                    label=signal_row.category,
                    data={"severity": signal_row.severity, 
                          "description": signal_row.description})
    
    # L2: Add all claims as nodes
    for claim_row in db.claims:
        eg.add_node("claim", claim_row.id,
                    label=claim_row.title,
                    data={"audience_lens": claim_row.audience_lens,
                          "confidence_band": claim_row.confidence_band,
                          "claim_text": claim_row.claim,
                          "counterargument": claim_row.counterargument})
    
    # L2→L1: Link claims to their source signals
    for signal in signals:
        for claim in claims_from_signal(signal):
            eg.add_edge("generates", signal.id, claim.id,
                       weight=claim.confidence_score)
    
    # L2→L3: Link claims to supporting/weakening evidence
    for claim in claims:
        for artifact_id in claim.supporting_evidence:
            eg.add_edge("supported_by", claim.id, artifact_id, 
                       weight=1.0, data={"polarity": "supporting"})
        for artifact_id in claim.weakening_evidence:
            eg.add_edge("weakened_by", claim.id, artifact_id,
                       weight=1.0, data={"polarity": "weakening"})
    
    # L3: Add artifact/file nodes
    for artifact in artifacts:
        eg.add_node("artifact", artifact.id,
                   label=artifact.type,
                   data={"path": artifact.metadata.get("path"),
                         "preview": artifact.content_preview})
    
    # L3: Link artifacts to files on disk (if available)
    for file_row in ctxorg_items:
        eg.add_node("file", file_row.id,
                   label=Path(file_row.path).name,
                   data={"path": file_row.path, "size": file_row.size})
        eg.add_edge("located_at", artifact.id, file_row.id)
    
    return eg
```

### 1.4 API Contract

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/v1/graph/tga` | Full TGA graph: signals + claims + evidence + edges |
| GET | `/api/v1/graph/tga?expand=signal:{id}` | Subgraph under a specific signal |
| GET | `/api/v1/graph/tga?expand=claim:{id}` | Subgraph under a specific claim |
| GET | `/api/v1/graph/tga?lens=recruiter` | Filter to one audience lens |
| GET | `/api/v1/graph/tga?depth=2` | Control expansion depth (default: 1) |

**Response shape:**

```json
{
  "run": "20260608-tga-v1",
  "tga_version": 1,
  "levels": {
    "signals": 33,
    "claims": 198,
    "evidence": 1423
  },
  "nodes": [
    {
      "id": "signal-uuid-1",
      "type": "signal",
      "label": "frequent_topic",
      "level": 1,
      "data": {
        "category": "frequent_topic",
        "severity": "medium",
        "description": "Consistent focus on AI/ML topics across 142 files"
      },
      "x": 0, "y": 0, "z": 0
    },
    {
      "id": "claim-uuid-1",
      "type": "claim",
      "label": "Recruiter: frequent_topic",
      "level": 2,
      "data": {
        "audience_lens": "recruiter",
        "confidence_band": "high",
        "claim_text": "A recruiter may notice consistent focus on AI/ML",
        "counterargument": "No direct contradictory evidence found...",
        "severity": "medium"
      },
      "x": 120, "y": 80, "z": 0
    },
    {
      "id": "artifact-uuid-1",
      "type": "artifact",
      "label": "workstream_file",
      "level": 3,
      "data": {
        "path": "/Users/ahmedm/Research/papers/transformer-notes.md",
        "preview": "Notes on attention mechanisms...",
        "polarity": "supporting"
      },
      "x": 240, "y": 160, "z": 0
    }
  ],
  "edges": [
    {
      "id": "edge-uuid-1",
      "type": "generates",
      "from_id": "signal-uuid-1",
      "to_id": "claim-uuid-1",
      "weight": 0.87,
      "data": {}
    },
    {
      "id": "edge-uuid-2",
      "type": "supported_by",
      "from_id": "claim-uuid-1",
      "to_id": "artifact-uuid-1",
      "weight": 1.0,
      "data": {"polarity": "supporting"}
    }
  ],
  "audience_lenses": ["recruiter", "investor", "collaborator", "creator",
                       "privacy", "platform", "search", "institution", "stranger"]
}
```

---

## 2. Visualization Design

### 2.1 TGA Mode — New Canvas Mode

A new mode class: `TGAMode` in `app.js`, sibling to `TopologyMode` and `UniverseMode`. Registered as mode `"tga"`.

**Layout Strategy: Layered Radial / Tree**

```
                    ┌─────────────┐
                    │  SIGNALS     │  ← L1: Outer ring, 33 signal nodes
                    │  (radial)    │     arranged by category
                    └──────┬──────┘
                           │ edges: "generates"
                    ┌──────┴──────┐
                    │  CLAIMS      │  ← L2: Middle ring, 198 claim nodes
                    │  (force)     │     arranged by audience lens + force
                    └──────┬──────┘
                           │ edges: "supported_by" / "weakened_by"
                    ┌──────┴──────┐
                    │  EVIDENCE    │  ← L3: Inner cluster, evidence dots
                    │  (cluster)   │     grouped by file category
                    └─────────────┘
```

**Alternative Layout (for "focus" mode):** When a signal or claim is selected, the graph transitions to a **tree layout** with the selected node as root, 1 level of children radially arranged, and evidence as leaves.

### 2.2 Level 1 — Signal Nodes

**Placement**: Radial layout. 33 signals arranged in a circle (or partial circle) at radius R1 from center. Categorized by signal category:

```
           stale_bio  
       ○               ○  timeline_gap
    ○                       ○
  ○     frequent_topic        ○  project_velocity
    ○                       ○  
       ○               ○
           ○       ○
       controversial  unclear_credential
```

**Visual encoding**:
- **Shape**: Circle
- **Size**: r = 12–18px, scaled by `severity × evidence_count`
- **Color**: By signal category:
  - `frequent_topic` = blue (#4A90D9)
  - `timeline_gap` = amber (#D9A44A)
  - `stale_bio` = coral (#D94A4A)
  - `project_velocity` = green (#4AD97A)
  - `controversial_phrase` = red (#D94A6A)
  - `unclear_credential` = purple (#8A4AD9)
  - `inconsistent_title` = orange (#D97A4A)
- **Label**: Signal category name, shown on hover or when zoomed > 0.6

**Interaction**:
- **Hover**: Shows tooltip with signal description + severity + evidence count
- **Click**: Expands to L2 — Claims generated from this signal. Camera zooms in, radial children appear.
- **Double-click**: Opens signal detail in right panel

### 2.3 Level 2 — Claim Nodes

**Placement**: Force-directed within a band (radius R1 + Δ to R2). Each claim starts positioned near its parent signal, then D3 force simulation spreads them to avoid overlap. Claims from the same audience lens cluster together.

**Visual encoding**:
- **Shape**: Hexagon (six-sided, distinctly different from circles)
- **Size**: r = 8–12px, scaled by `confidence_band` (HIGH=12, MEDIUM=9, LOW=7)
- **Color**: By audience lens:
  - `recruiter` = navy (#1B3A5C)
  - `investor` = teal (#1B5C4A)
  - `collaborator` = indigo (#3A1B5C)
  - `creator` = forest (#2D5C1B)
  - `privacy` = slate (#4A4A5C)
  - `platform` = steel (#3A4A5C)
  - `search` = cobalt (#1B3A8C)
  - `institution` = maroon (#5C1B2D)
  - `stranger` = charcoal (#2D2D3A)
- **Border/glow**: 
  - HIGH confidence = bright glow (opacity 0.8)
  - MEDIUM = subtle glow (opacity 0.4)
  - LOW = no glow, dashed border
- **Label**: First 20 chars of claim title, shown when zoomed or hovered

**Interaction**:
- **Hover**: Shows claim text + confidence band + counterargument preview
- **Click**: Expands to L3 — Evidence supporting/weakening this claim. Evidence nodes appear radially around the claim.
- **Double-click**: Opens claim detail modal with full text + counterargument + repair options

### 2.4 Level 3 — Evidence Nodes

**Placement**: Radial around parent claim. Supporting evidence on the right side, weakening evidence on the left side. Distance from claim proportional to contribution weight.

```
              weakening                supporting
                 ○ ○ ○              ○ ○ ○ ○
                    \    claim    /
        ○ ○ ──────── (⬡) ──────── ○ ○
                    /              \
                 ○ ○              ○ ○ ○
```

**Visual encoding**:
- **Shape**: Small circle or file-icon-glyph
- **Size**: r = 3–6px, scaled by `contribution_weight`
- **Color**: 
  - `supporting` = warm green (#4AD97A at 0.7 opacity)
  - `weakening` = warm red (#D94A6A at 0.7 opacity)
  - `neutral` = gray (#8A8A9A at 0.5 opacity)
- **Label**: Filename or artifact type, shown on hover

**Interaction**:
- **Hover**: Shows file path + preview text (first 80 chars) + polarity
- **Click**: Selects the evidence, shows full metadata in right panel
- **Double-click or "Open" button**: Opens the actual file in Finder/editor (via `file://` or backend file-open route)

### 2.5 Edge Rendering

Edges are drawn as curved lines (quadratic bezier) between parent and child levels.

**Edge styling**:
- `generates` (signal→claim): Solid line, thickness = weight × 2, color = parent signal color at 0.3 opacity. Always visible.
- `supported_by` (claim→evidence): Solid line, thickness = 1px, color = green (#4AD97A at 0.25 opacity). Only visible when claim is expanded.
- `weakened_by` (claim→evidence): Dashed line, thickness = 1px, color = red (#D94A6A at 0.25 opacity). Only visible when claim is expanded.
- `contradicts` (claim↔claim): Red dotted line, thickness = 1.5px. Always visible between expanded claims.

**Edge visibility rules** (inspired by TopologyMode's edge-on-select pattern):
- L1→L2 edges: Show only for the **selected signal** + its immediate neighbors
- L2→L3 edges: Show only for the **selected claim** + any claims sharing the selected signal
- L3→L3 edges: Show only when two evidence items are both selected
- Maximum edges rendered at once: 300 (match TopologyMode cap)

### 2.6 Background & Atmosphere

Following the white frost-glass aesthetic and UniverseMode patterns:

- **Background**: Dark gradient (#05060f → #03050b) with subtle frost-glass grid
- **L1 ring**: Subtle concentric ring at the signal radius, drawn in `rgba(176,196,255,0.06)`
- **L2 band**: Slightly lighter band for claim region
- **L3 area**: Dust particles (like UniverseMode) in the evidence zone
- **Audience lens labels**: Semi-transparent text labels at the edges showing each audience lens name (like UniverseMode category labels)

---

## 3. Interaction Model

### 3.1 Navigation Controls

| Input | Action |
|-------|--------|
| Scroll | Zoom in/out (clamp: 0.3–3.0) |
| Drag (empty space) | Pan the viewport |
| Drag (node) | Move node within its level (forces update layout) |
| Click (empty space) | Deselect all, collapse to L1-only view |
| Click (L1 signal) | Select signal, expand to show its L2 claims |
| Click (L2 claim) | Select claim, expand to show its L3 evidence |
| Click (L3 evidence) | Select evidence, show metadata in panel |
| Double-click (any) | Open detail modal or file |
| Key "0" | Reset viewport (center, zoom 1.0) |
| Key "Z" | Zoom to selection |
| Key "Escape" | Collapse all, return to L1-only view |

### 3.2 Expansion Animation

When a signal is clicked and its claims appear:
1. Camera smoothly pans to center on the signal
2. Claim nodes animate outward from the signal node position (300ms ease-out)
3. Edges fade in (200ms delay, 200ms duration)
4. Labels appear at the end of animation

When a claim is clicked and evidence appears:
1. Evidence dots animate outward radially from the claim (200ms spring)
2. Supporting evidence slides right, weakening slides left
3. Edge lines draw in with a "stroke-dashoffset" reveal animation

### 3.3 Collapse Behavior

- Clicking an already-selected node **collapses** its children
- Children animate back to parent position and fade out before being removed
- Edges retract
- Sibling nodes adjust positions via force simulation

### 3.4 Right Panel Integration

When a node is selected, the right inspector panel (`#inspector`) shows:

**Signal selected**:
```
┌─────────────────────────────┐
│ SIGNAL: frequent_topic       │
│ Severity: MEDIUM             │
│ Evidence count: 142 files    │
│                             │
│ "Consistent focus on AI/ML  │
│  topics across research     │
│  notes, papers, and code."  │
│                             │
│ → Generated 18 claims       │
│   across 9 audience lenses  │
│                             │
│ [Expand all claims]         │
└─────────────────────────────┘
```

**Claim selected**:
```
┌─────────────────────────────┐
│ CLAIM: Recruiter read       │
│ Confidence: HIGH ●          │
│                             │
│ "A recruiter may notice    │
│  consistent focus on AI/ML  │
│  and value your technical   │
│  depth."                    │
│                             │
│ COUNTERARGUMENT:            │
│ "No direct contradictory   │
│  evidence found. This is    │
│  a hypothesis, not a        │
│  verdict."                  │
│                             │
│ SUPPORTING: 12 files        │
│ WEAKENING: 2 files          │
│                             │
│ → [Inspect evidence]        │
│ → [View repair actions]     │
│ → [Simulate this audience]  │
└─────────────────────────────┘
```

**Evidence selected**:
```
┌─────────────────────────────┐
│ EVIDENCE: transformer-notes │
│ Polarity: SUPPORTING        │
│ Weight: 0.87                │
│                             │
│ Path:                       │
│ /Users/ahmedm/Research/     │
│ papers/transformer-notes.md │
│                             │
│ Preview:                    │
│ "Notes on attention         │
│  mechanisms and multi-head  │
│  architectures..."          │
│                             │
│ → [Open file]               │
│ → [View in context]         │
└─────────────────────────────┘
```

---

## 4. Implementation Plan

### 4.1 Backend Changes

#### File: `backend/src/optic/v1/graph.py`
**Changes**: None to the core class — it's already well-designed. Only add a helper method:

```python
def populate_from_audit(self, signals, claims, artifacts):
    """Bulk-populate the evidence graph from audit pipeline results."""
    # Add signal nodes + signal→claim edges + claim→evidence edges
```

#### File: `backend/src/optic/v1/server.py`
**Changes**: 
1. Add `build_tga_evidence_graph()` function (as described in §1.3 above)
2. Add route `GET /api/v1/graph/tga` that calls `build_tga_evidence_graph()`, then `export_subgraph()` with appropriate depth
3. Support query params: `?expand=signal:{id}`, `?expand=claim:{id}`, `?lens={id}`, `?depth={1|2|3}`
4. Add `GET /api/v1/graph/tga/subgraph?root={id}&depth={n}` for focused views

#### File: `backend/src/ctxorg/server.py`
**Changes**:
1. Add route `GET /api/v1/graph/tga` → proxies to V1 intelligence or imports V1 modules directly
2. Bridge ctxorg items (from ctx.db) into the evidence graph so file paths resolve correctly
3. Add route `GET /api/file/open?path={path}` — opens a file in the OS default app (macOS: `open {path}`)

### 4.2 Frontend Changes

#### File: `backend/src/ctxorg/static/app.js`

**New class: `TGAMode`** (~800-1200 lines)

Structure:
```javascript
class TGAMode extends CanvasMode {
  constructor() {
    // State: expansion depth, selected node, visible levels
    this.expandedSignals = new Set();
    this.expandedClaims = new Set();
    this.selectedNode = null;
    this.level = 1;  // 1, 2, or 3
  }
  
  mount(canvas)     // Initialize canvas, load TGA data, setup controls
  loadTGAData()     // Fetch /api/v1/graph/tga, cache in state
  layout()          // Position nodes by level: L1 radial, L2 force, L3 radial
  draw()            // Main render loop
  drawSignals()     // L1 rendering
  drawClaims()      // L2 rendering  
  drawEvidence()    // L3 rendering
  drawEdges()       // Edge rendering with level-aware visibility
  expandSignal(id)  // Animate claims appearing from signal
  collapseSignal()  // Reverse animation
  expandClaim(id)   // Animate evidence appearing from claim
  collapseClaim()   // Reverse animation
  pick(ev)          // Hit detection: L1 > L2 > L3 priority
  move(ev)          // Hover detection
  drawPanel()       // Right panel rendering per selected node type
  animate()         // requestAnimationFrame loop
}
```

**Registration** — Add to mode registry (line ~743):
```javascript
tga: new TGAMode(),
```

**Leftnav** — Add "Evidence Graph" mode to the leftnav items list (line ~269):
```javascript
{ mode: "tga", label: "Evidence Graph", icon: "⊞", section: 1 }
```

**Loading screen** — Like TopologyMode, show a dark gradient loading screen with:
- "Evidence Graph" title (48px Sora)
- Animated orbiting signal/claim/evidence dots at 3 radial distances
- "Loading inference data…" status text
- Node/edge count shown in statusbar

**Honest UI states** (per Quality Gate 4):
- **Loading**: Pulsing dots at three radii, "Building evidence graph…"
- **Empty**: "No audit data yet. Run an audit to populate the evidence graph." with [Run Audit] button
- **Error**: Error message + [Retry] button + "Click to retry" (matching UniverseMode pattern)
- **Disabled**: Grayed-out canvas, "Evidence graph is not available in this mode"

### 4.3 CSS Changes

#### File: `backend/src/ctxorg/static/app.css`

Add TGA-specific styles:
```css
/* TGA mode — no additional CSS needed beyond existing canvas styles */
/* Node selection glow reuses existing .selected-glow pattern */
/* Tooltip reuses existing #tooltip */
/* Inspector panel reuses existing #inspector with new TGA-specific content */
```

### 4.4 Integration Order

```
Phase 1: Backend data pipeline
  1. ✓ EvidenceGraph class exists (optic/v1/graph.py)
  2. 🔲 build_tga_evidence_graph() — populates graph from audit pipeline
  3. 🔲 /api/v1/graph/tga endpoint in V1 server
  4. 🔲 Bridge route in ctxorg server (or proxy)
  5. 🔲 /api/file/open endpoint for file access

Phase 2: Frontend canvas
  6. 🔲 TGAMode class with loading/getData/layout/draw skeleton
  7. 🔲 L1 signal rendering (radial circles)
  8. 🔲 L1→L2 expansion animation
  9. 🔲 L2 claim rendering (force-laid hexagons)
  10. 🔲 L2→L3 expansion animation
  11. 🔲 L3 evidence rendering (radial dots)
  12. 🔲 Edge rendering with level-aware visibility
  13. 🔲 Hit detection (pick/move/hover)

Phase 3: Interaction polish
  14. 🔲 Expand/collapse transitions
  15. 🔲 Right panel per-node-type
  16. 🔲 Tooltip with node details
  17. 🔲 Keyboard navigation (0, Z, Escape)
  18. 🔲 Mode registration + leftnav entry
  19. 🔲 Loading/empty/error states
```

---

## 5. Force Layout Details

### 5.1 L1 — Signal Radial Layout

```javascript
layoutSignals() {
  const signals = this.tgaNodes.filter(n => n.type === "signal");
  const count = signals.length;
  const radius = Math.min(this.canvas.width, this.canvas.height) * 0.35;
  const cx = this.canvas.width / 2;
  const cy = this.canvas.height / 2;
  
  signals.forEach((s, i) => {
    const angle = (i / count) * Math.PI * 2 - Math.PI / 2;
    s.x = cx + Math.cos(angle) * radius;
    s.y = cy + Math.sin(angle) * radius;
  });
}
```

### 5.2 L2 — Claim Force Layout

Uses D3 force simulation with:
- **Centering force** toward parent signal position (strength 0.3)
- **Collision force** to prevent overlap (radius + 4px)
- **Many-body repulsion** between claims (strength -30, limited to same audience lens)
- **Link force** for claim↔claim "contradicts" edges (distance 60, strength 0.1)
- **alphaDecay**: 0.05 (fast settle)

### 5.3 L3 — Evidence Radial Layout

```javascript
layoutEvidence(claim) {
  const evidence = this.tgaNodes.filter(n => 
    n.type === "artifact" && this.isChildOf(n, claim));
  const supporting = evidence.filter(e => e.data.polarity === "supporting");
  const weakening = evidence.filter(e => e.data.polarity === "weakening");
  
  // Supporting: radial from claim, right side (angle -π/2 to π/2)
  const supRadius = 80;
  supporting.forEach((e, i) => {
    const angle = -Math.PI/2 + (i / (supporting.length || 1)) * Math.PI;
    e.x = claim.x + Math.cos(angle) * supRadius;
    e.y = claim.y + Math.sin(angle) * supRadius;
  });
  
  // Weakening: radial from claim, left side (angle π/2 to 3π/2)
  const weakRadius = 80;
  weakening.forEach((e, i) => {
    const angle = Math.PI/2 + (i / (weakening.length || 1)) * Math.PI;
    e.x = claim.x + Math.cos(angle) * weakRadius;
    e.y = claim.y + Math.sin(angle) * weakRadius;
  });
}
```

---

## 6. Performance Budget

- **Max nodes in view**: 500 (L1=33 + L2=198 + L3=269)
- **Max edges in view**: 300 (capped, same as TopologyMode)
- **Target FPS**: 60fps on M1 Mac
- **Animation budget**: 16ms per frame (requestAnimationFrame)
- **Canvas resolution**: devicePixelRatio × bounding rect (standard)
- **Force simulation**: Only run when L2 claims are visible; stop when settled
- **Hit testing**: Spatial hash grid (if nodes > 300) or linear scan (below that)

---

## 7. Doctrinal Compliance

### Invariants Satisfied

| # | Invariant | How TGA Complies |
|---|-----------|-----------------|
| 3 | Evidence-Gated | Every claim node cites evidence nodes; edges are typed |
| 4 | Confidence-Banded | L2 nodes visually encode HIGH/MEDIUM/LOW |
| 5 | Repair-Oriented | Claim panel links to repair actions |
| 8 | No Fake Completeness | Empty/null states handled honestly |
| 14 | Honest UI States | Loading/empty/error/disabled all handled |
| 15 | Explicit Over Elegant | All nodes are inspectable; data is citeable |

### What TGA REFUSES To Do (matching Optic refusals)
- No universal scores or rankings — claims are audience-specific readings
- No black-box results — every claim has inspectable evidence
- No fake product truth — empty graph shows "Run audit first"
- No silent data egress — all computation is local

---

## 8. Appendix: Visual Reference

### 8.1 Color Palette for Signal Categories

| Category | Hex | Meaning |
|----------|-----|---------|
| frequent_topic | #4A90D9 | Blue — informational |
| timeline_gap | #D9A44A | Amber — caution |
| stale_bio | #D94A4A | Coral — attention needed |
| project_velocity | #4AD97A | Green — positive signal |
| controversial_phrase | #D94A6A | Red — risk flag |
| unclear_credential | #8A4AD9 | Purple — ambiguity |
| inconsistent_title | #D97A4A | Orange — inconsistency |

### 8.2 Color Palette for Audience Lenses

| Lens | Hex | Tone |
|------|-----|------|
| recruiter | #1B3A5C | Navy |
| investor | #1B5C4A | Teal |
| collaborator | #3A1B5C | Indigo |
| creator | #2D5C1B | Forest |
| privacy | #4A4A5C | Slate |
| platform | #3A4A5C | Steel |
| search | #1B3A8C | Cobalt |
| institution | #5C1B2D | Maroon |
| stranger | #2D2D3A | Charcoal |

### 8.3 Mock Layout (ASCII)

```
                          L1: SIGNALS (outer ring)
                    ○timeline    ○frequent_topic
                 ○stale                    ○project
               ○                                   ○
              ○      ┌─────────────────┐            ○
             ○       │  L2: CLAIMS      │             ○
            ○        │  (selected       │              ○
     ○──────○────────│   signal         │───────○──────○
            ○        │   expanded)      │              ○
             ○       │                 │             ○
              ○      │    ⬡ ⬡ ⬡      │            ○
               ○     │   ⬡  ⬡  ⬡    │           ○
                ○    │  ⬡   ⬡   ⬡  │          ○
                 ○   └──────┬─────────┘         ○
                  ○         │                   ○
                   ○   L3: EVIDENCE            ○
                    ○  (claim expanded)      ○
                      ○  ○ ○ ○ ○ ○ ○ ○    ○
```

---

*End of TGA Evidence Graph Design Document*
*Next step: Implementation per §4.4 Integration Order*
