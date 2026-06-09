# Optic V1 — Product Doctrine

> This document is the acceptance criteria for every agent, PR, feature, and
> screen in Wave 1. Nothing ships that violates it. Nothing is declared
> "complete" that dodges it.

---

## 1. What Optic Does

Optic is a private, local-first intelligence instrument that analyzes your
digital footprint to show what different audiences and algorithms may infer
about you. It indexes your local files, detects workstreams, and runs
structured inference through audience lenses you select — producing
evidence-citing claims, confidence-banded results, and repair-oriented
recommendations. You are the subject. You own the inference. Nothing leaves
your machine without your explicit consent. Every result is traceable,
inspectable, and open to challenge.

---

## 2. What Optic Refuses to Do

Optic's identity is defined as much by what it rejects as by what it builds.

- **Not a background check.** Optic does not evaluate the user for a third
  party. It works for the subject, not the evaluator.
- **Not a third-party evaluator.** Optic does not produce reports for
  employers, landlords, insurers, lenders, platforms, or any external
  decision-maker.
- **No universal identity score.** Optic does not reduce a person to a
  single number, rating, or grade. No credit-score-for-identity.
- **No surveillance.** Optic does not monitor, report on, or profile other
  people. It only analyzes data the subject owns and approves.
- **No cloud-first posture.** Local-first is the default. Cloud sync,
  multi-device, or remote features require explicit opt-in — not opt-out.
- **No fake product truth.** Optic never shows placeholder content, demo
  screens, hardcoded counts, invented claims, fake readiness, or simulated
  progress that pretends the system knows something it does not.
- **No silent data egress.** Nothing leaves the user's machine without
  informed, explicit consent. Every external call is visible and
  interruptible.
- **No black-box results.** Every inference must cite its evidence, expose
  its uncertainty, and show counterarguments. Inscrutable model output with
  no provenance is forbidden.
- **No gamification.** Optic does not award points, XP, badges, levels, or
  streaks. Engagement comes from control, consequence, and precision — not
  compulsion loops.

---

## 3. Core Invariants (The 15 Rules)

These rules are non-negotiable. No feature, refactor, optimization, or
deadline justifies violating them.

### 1. Subject-Owned
The user owns their data and their inferences. Optic works exclusively for
the subject. Every access check proves the user is acting on their own
behalf — or the action is blocked.

### 2. Consent-Scoped
No data is analyzed without explicit user approval. Sources must be
approved. Lenses must be selected. The audit scope is always visible and
always under user control.

### 3. Evidence-Gated
Every inference claim must cite specific evidence drawn from the user's
approved data. Claims without evidence links are invalid output and must
not be rendered.

### 4. Confidence-Banded
Every inference must expose its confidence level as a band, not a binary.
Uncertainty is never presented as certainty. Low-confidence results are
labeled honestly, not hidden.

### 5. Repair-Oriented
Every finding that surfaces a risk, contradiction, or undesirable inference
must be accompanied by actionable repair steps when possible. Optic is not a
diagnosis dispenser — it is an instrument for improvement.

### 6. Model Output Is Untrusted Input
Every byte from a model — text, JSON, structured claims, tool calls,
summaries — must be validated, structured, and policy-checked before it
mutates state, becomes SQL, hits the filesystem, or reaches the UI.

### 7. Client Input Is Untrusted Input
Every request body, query param, header, cookie, and form field must be
validated and authorized server-side. Client-side validation is UX, not
security. Assume the user can bypass the UI and POST raw JSON.

### 8. No Fake Completeness
The interface must never pretend the system knows something it does not
know. No hardcoded counts. No demo screens shipped as product. No
placeholder data rendered as truth. Loading, empty, error, disabled, and
unavailable states are first-class — not afterthoughts.

### 9. Traceable State Changes
Every important state mutation must be authorized before execution, logged
with provenance after execution, and recoverable if it fails. The system
must answer: who did what, with what input, producing what output, changing
what state.

### 10. Database Enforces Invariants
Invariants live in the database — unique constraints, foreign keys,
ownership scoping, non-null fields, check constraints, and transaction
boundaries. The ORM is a convenience, not a data model. The app code can
be buggy; the database still protects correctness.

### 11. Idempotent Mutations
Every paid, irreversible, expensive, or state-changing operation must
survive double-clicks, webhook retries, network timeouts, and concurrent
execution. Assume every request arrives at least once — and possibly twice
at the same millisecond.

### 12. Local-First By Default
The system must run fully on the user's machine with no external
dependencies required for core operation. Any feature that requires network
access must be explicitly opt-in, clearly marked, and fail gracefully when
offline.

### 13. Bootstrappable From README
A fresh machine with only the README, runtime dependencies, and a cloned
repo must be able to run the project. Package scripts, env vars, migrations,
seed data, and local dev commands must agree. No hallucinated packages, no
fake scripts, no undocumented magic.

### 14. Honest UI States
Every screen and every component must handle: loading, empty, error (with
specificity: 401, 403, 404, 409, 500, timeout, provider failure), disabled,
and unavailable. A single `loading` boolean and a single `error` string are
not sufficient for critical flows.

### 15. Explicit Over Elegant
Prefer working, inspectable, debuggable code over abstractions that hide
uncertainty. Do not over-abstract early. No `ManagerFactoryProviderStrategy`
architecture unless repeated pain justifies it. Every abstraction must
reduce risk, not decorate confusion.

---

## 4. User Pain It Solves

- **Algorithmic evaluation without visibility.** People are judged by
  algorithms they cannot see, using data they cannot control. Recruiters,
  insurers, lenders, platforms, and border systems run inference on scattered
  digital footprints — and the subject never knows what was inferred or why.

- **No structured view of your own footprint.** Your data is scattered
  across local files, cloud drives, messaging apps, browsers, and platforms.
  No tool gives you a coherent, structured, queryable map of what you've
  actually produced — or what it implies about you to different audiences.

- **No way to contest or repair algorithmic inference.** When a platform,
  employer, or system draws a wrong conclusion from your data, you have no
  instrument to discover it, understand its evidence chain, challenge it, or
  guide your behavior to change it.

- **Existing tools are either surveillance or decoration.** Background-check
  services work for the evaluator, not the subject. Scoring services produce
  opaque numbers. "Personal analytics" dashboards show vanity metrics with
  no causal model, no uncertainty, and no repair path.

- **No instrument for digital self-understanding.** There is no tool that
  combines local-first privacy, structured inference, evidence traceability,
  confidence calibration, and repair guidance into a single instrument that
  the subject owns and controls.

---

## 5. What V1 Ships vs. What It Defers

### V1 Ships

| Capability | Scope |
|---|---|
| Local file indexing | Scan user-approved directories. Detect file types, sizes, and modification dates. |
| Workstream detection | Group files into coherent workstreams (projects, topics, activities). |
| Source approval flow | User reviews detected workstreams and explicitly includes/excludes each. |
| Audience lens selection | User selects which audience perspectives to run inference through (e.g., recruiter, collaborator, platform). |
| Local inference engine | Runs models locally via Ollama. No cloud inference in the default path. |
| Evidence-citing claims | Every inference product links back to specific files or file regions. |
| Confidence-banded results | Every claim carries an explicit confidence band (high / medium / low / insufficient). |
| Counterargument display | Where evidence is mixed, the UI surfaces competing interpretations. |
| Repair recommendations | Actionable steps generated alongside risks and contradictions. |
| Trace inspection | User can drill into any claim to see: trigger, input, context, model, confidence, and evidence. |
| White frost-glass interface | Canonical visual system: off-white root, translucent panels, cool-gray borders, soft blur, clear hierarchy. |
| Seven-step onboarding | Calibration flow: Welcome → Profile → Data Scope → Source Approval → Lenses → Model Check → Ready to Audit. |
| One product shell | Onboarding, dashboard, audit run, and results all route through the same coherent visual system. |
| Local auth | Salted-hash user accounts stored locally. No third-party auth required. |
| Honest UI states | Every screen handles loading, empty, error, disabled, and unavailable — not just the happy path. |

### V1 Defers

| Capability | Rationale |
|---|---|
| Cloud sync / multi-device | Violates local-first default. Requires explicit opt-in architecture, not bolted-on sync. |
| Team / org features | Optic V1 is a personal instrument. Shared workspaces introduce permission models that are out of scope. |
| Third-party platform integrations | Reading from Gmail, Slack, Twitter, etc., introduces OAuth, rate limits, and data-residency complexity. |
| Real-time file monitoring | Filesystem watchers add OS-specific fragility. V1 uses explicit scan triggers. |
| Mobile applications | V1 is desktop-first. The inference pipeline requires local compute not practical on phones. |
| API for external consumers | Optic is not a platform. No public API, no webhooks, no SDK. |
| Advanced rendering (PixiJS, Rive, Canvas) | DOM-first until real graph/preview data exists and justifies a richer layer. |
| Semantic command search | Useful but not core to the audit loop. Deferred until post-V1. |
| Browser extension for web footprint | Out of scope for the local-filesystem-first V1. |

---

## 6. Quality Gates

Every subagent must satisfy every gate before marking work complete.
"No" is not an acceptable answer to any gate unless accompanied by an
explicit, documented deferral with a tracking issue.

### Gate 1: Architecture Integrity
- [ ] Who can access this data, and where is that enforced?
- [ ] Can changing an object ID let someone read or mutate someone else's data?
- [ ] What fields are explicitly allowlisted for this actor on this operation?
- [ ] Which invariant is enforced even if app code is buggy?

### Gate 2: Mutation Safety
- [ ] What happens if this request is sent twice?
- [ ] What happens if two users, two tabs, or two workers do this at the same millisecond?
- [ ] What happens if the client sends fields the UI never exposes?
- [ ] What happens if the network times out after the operation already succeeded?

### Gate 3: AI-Native Safety
- [ ] Is model output treated as untrusted at every boundary?
- [ ] Can a prompt injection cause tool calls, memory writes, file changes, SQL, shell, or HTML execution?
- [ ] What prevents retrieved context from overriding system rules?
- [ ] Can malformed, adversarial, too-long, partial, or semantically wrong model output corrupt state?
- [ ] What permanent state changes did the model influence, and are they traceable?
- [ ] Can we inspect why the agent did what it did?

### Gate 4: UI Honesty
- [ ] Does every screen handle: loading, empty, error (specific), disabled, and unavailable?
- [ ] Is there any hardcoded, placeholder, or demo content rendering as product truth?
- [ ] Does every count, status, and readiness signal derive from real state?
- [ ] Can the user complete this flow with keyboard only?
- [ ] Are errors surfaced near the thing that failed, not just in console?
- [ ] Does the flow respect `prefers-reduced-motion`?

### Gate 5: Operational Readiness
- [ ] Can a fresh machine boot this from the README alone?
- [ ] Do `.env.example`, code, deploy config, and docs agree?
- [ ] Are there any unused, fake, or hallucinated dependencies?
- [ ] Which endpoints exist, who can call them, and which are deprecated?
- [ ] Are webhooks signature-verified (if applicable)?
- [ ] Can user input make the backend call internal URLs or private IPs?
- [ ] What logs would help debug this in production without leaking secrets?

### Gate 6: Cost & Abuse Surface
- [ ] What can one abusive user loop until it costs money?
- [ ] Are there rate limits, quotas, file size limits, or usage tracking on cost-bearing surfaces?
- [ ] Does every expensive operation have cleanup behavior for abandoned/incomplete work?

### Gate 7: Testing
- [ ] Does the test prove something that could actually break in production?
- [ ] Does the test hit the real boundary or only a mock?
- [ ] Does the test cover: bad input, wrong user, duplicate execution, race, timeout, and provider failure?
- [ ] Does the test prove the core Optic loop is durable (input → perception → reasoning → memory → result → trace → recovery)?

### Gate 8: Self-Audit
- [ ] What did you deliberately not build yet, and is it documented?
- [ ] Did you catch yourself building a shiny surface while the core loop is brittle?
- [ ] Did you add files, abstractions, or ceremony to make the repo feel mature?
- [ ] Did you write code that assumes perfect users, perfect browsers, perfect providers, perfect networks, or perfect model outputs?

---

## Acceptance Rule

> A feature, screen, or subsystem is **not complete** until every applicable
> quality gate is satisfied. Passing 7 of 8 gates is not passing. "It works
> on my machine" is not passing. "The demo looks good" is not passing.
>
> Complete means: wired, traceable, recoverable, honest, and survivable under
> real conditions. Build the intended system with teeth.

---

*Doctrine derived from shibboleth_one, refrence_two, and bible_one.
This document governs all Wave 1 work. Amendments require explicit review.*
