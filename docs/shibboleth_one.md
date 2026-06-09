# shibboleth_one — Engineering Quality Doctrine

> Recovered from WAVE1-PRODUCT-DOCTRINE.md and optichyperdoc.rtf
> Original RTF: 204 bytes · Agent-built artifact · June 2026

## The 8 Quality Gates

Every subagent, PR, and feature must pass ALL gates. No exceptions.

### Gate 1: Architecture Integrity
- Who can access this data, and where is that enforced?
- Can changing an object ID let someone read or mutate someone else's data?
- What fields are explicitly allowlisted for this actor on this operation?
- Which invariant is enforced even if app code is buggy?

### Gate 2: Mutation Safety
- What happens if this request is sent twice?
- What happens if two users, two tabs, or two workers do this at the same millisecond?
- What happens if the network times out after the operation already succeeded?

### Gate 3: AI-Native Safety
- Is model output treated as untrusted at every boundary?
- Can a prompt injection cause tool calls, memory writes, file changes, SQL, shell, or HTML execution?
- What prevents retrieved context from overriding system rules?
- Can malformed, adversarial, or semantically wrong model output corrupt state?

### Gate 4: UI Honesty
- Does every screen handle: loading, empty, error (specific), disabled, and unavailable?
- Is there any hardcoded, placeholder, or demo content rendering as product truth?
- Does every count, status, and readiness signal derive from real state?
- Can the user complete this flow with keyboard only?

### Gate 5: Operational Readiness
- Can a fresh machine boot this from the README alone?
- Do `.env.example`, code, deploy config, and docs agree?
- Are there any unused, fake, or hallucinated dependencies?

### Gate 6: Cost & Abuse Surface
- What can one abusive user loop until it costs money?
- Are there rate limits, quotas, file size limits, or usage tracking?
- Does every expensive operation have cleanup behavior for abandoned/incomplete work?

### Gate 7: Testing
- Does the test prove something that could actually break in production?
- Does the test hit the real boundary or only a mock?
- Does the test cover: bad input, wrong user, duplicate execution, race, timeout, provider failure?

### Gate 8: Self-Audit
- What did you deliberately not build yet, and is it documented?
- Did you catch yourself building a shiny surface while the core loop is brittle?
- Did you add files, abstractions, or ceremony to make the repo feel mature?

## The Acceptance Rule

> A feature is **not complete** until every applicable quality gate is satisfied.
> "It works on my machine" is not passing. "The demo looks good" is not passing.
> Complete means: wired, traceable, recoverable, honest, and survivable under real conditions.

## Engineering Invariants

### Model Output Is Untrusted Input
Every byte from a model must be validated, structured, and policy-checked before it mutates state.

### Client Input Is Untrusted Input
Every request body, query param, header, cookie, and form field must be validated server-side. Client-side validation is UX, not security.

### No Fake Completeness
The interface must never pretend the system knows something it does not know. No hardcoded counts. No demo screens shipped as product.

### Traceable State Changes
Every important state mutation must be authorized, logged with provenance, and recoverable if it fails.

### Database Enforces Invariants
Invariants live in the database — unique constraints, foreign keys, ownership scoping, non-null fields. The ORM is a convenience, not a data model.

### Idempotent Mutations
Every paid, irreversible, or state-changing operation must survive double-clicks, webhook retries, network timeouts, and concurrent execution.

### Explicit Over Elegant
Prefer working, inspectable, debuggable code over abstractions that hide uncertainty. Every abstraction must reduce risk, not decorate confusion.
