# refrence_two — Aesthetic & Design Doctrine

> Recovered from WAVE1-PRODUCT-DOCTRINE.md, CLAUDE.md, and optichyperdoc.rtf
> Original RTF: 770 bytes · Agent-built artifact · June 2026

## The White Frost-Glass Visual System

Optic's canonical visual language: off-white root, translucent panels, cool-gray borders, soft blur, clear hierarchy.

### Design Tokens

```
--color-cream: off-white root background
--color-ink: dark text primary
--color-muted: secondary/muted text
--color-border: cool-gray borders
--color-section-dark: darker section backgrounds
```

### Typography

- **Editorial/Display:** Playfair Display (`font-editorial`) — hero, section headings
- **Body/UI:** DM Sans (`font-sans`) — body text, UI labels, controls
- **Mono (debug/tech):** JetBrains Mono — code, stats, technical displays

### Frost-Glass Principles

- Translucent panels layered over the cream root
- Soft backdrop blur for depth
- Cool-gray borders (not harsh black)
- Clear visual hierarchy through weight and spacing
- No aggressive shadows, no neon, no dark-mode-only
- Cream base conveys warmth; glass panels convey intelligence

## Honest UI States (Invariant 14)

Every screen and every component MUST handle:

| State | Requirement |
|-------|-------------|
| **Loading** | Skeleton or spinner, not blank screen |
| **Empty** | Explicit empty state with guidance |
| **Error** | Specific: 401, 403, 404, 409, 500, timeout, provider failure |
| **Disabled** | Visually distinct, with reason tooltip |
| **Unavailable** | Missing API key, missing model, offline |

A single `loading` boolean and a single `error` string are not sufficient for critical flows.

## Honest Product Truth (Invariant 8)

- No placeholder content rendered as truth
- No hardcoded counts pretending to be real data
- No demo screens shipped as product
- No fake readiness signals
- No simulated progress bars that don't reflect actual work
- Every count, status, and readiness signal must derive from real state

## UI Screen Requirements

Required screens (from optichyperdoc §20):
- Onboarding (state machine, not slideshow)
- Dashboard/Home (state-aware CTA)
- Sources and Consent
- Workstreams
- Scan Status
- Audience Selection
- Run Audit / Audit Progress
- Inference Cards + Card Detail with Evidence Drawer
- Contradictions
- Risks/Exposures
- Repair Queue
- Report View + Report History
- Graph/Topology
- Iris Chat
- Settings
- Export Center

## The White Frost-Glass Dashboard

- 8 dashboard modes
- 198 claims displayed
- 42 repairs surfaced
- 33 signal detectors feeding the view
- Frost-glass panels with evidence drawers
- Confidence bands visible on every claim
- No dead buttons. No fake data.

## Design Anti-Patterns

- No gamification (no points, XP, badges, streaks)
- No dark patterns (no hidden dismissals, no confusing CTAs)
- No fake product truth (no Lorem Ipsum as data)
- No black-box results (evidence must be inspectable)
- No "shiny surface while the core loop is brittle" (Gate 8)
