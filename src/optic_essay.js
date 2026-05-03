export const intro = [
  "We do not tell you who you are. Other systems already try. Optic shows "
    + "the trail: what was visible, what it signaled, who might read it, "
    + "where the reading breaks, and what can be repaired without "
    + "surrendering the evidence to another bureau.",
  "The premise is narrower than the headline and larger than a privacy "
    + "tool. The audit is about the surface around the subject, not the "
    + "interior truth of the subject. It is a mirror with receipts.",
  "The strategic question is whether this is a feature, a service, or a "
    + "category. Optic's answer is category-level: privacy settings, data "
    + "removal, reputation cleanup, credit awareness, and public profile "
    + "polish all orbit the same missing object, which is the user's inferred "
    + "identity.",
  "The first commercial motion is intentionally narrow. Start with people "
    + "entering moments where being misread is expensive: fundraising, "
    + "hiring, publishing, applying, selling, or becoming newly public. In "
    + "those moments, the user does not want a dashboard. They want a "
    + "credible audit, a clear mirror, and a repair plan.",
  "The operating contract is source -> signal -> inference -> confidence "
    + "-> counterargument -> repair. It appears here as the spine of the "
    + "paper; later sections refer back to the same chain instead of "
    + "reprinting it.",
  "This document is not a claim that Optic already has the final model, "
    + "the final market, or the final legal architecture. It is a "
    + "formation-stage doctrine and build spec: what Optic is, what it "
    + "refuses to become, what can be built now, and what would need to be "
    + "proven before the 2030 version exists.",
];

export const essaySections = [
  section("Thesis: What Optic Is", [
    "Optic is a user-side audit layer for inferred identity. The core "
      + "object is not a score, a personality profile, or a compliance badge. "
      + "The core object is a repairable inference: a claim about how some "
      + "audience might read the user from evidence currently available to "
      + "that audience or supplied by the user.",
    "The product exists because identity is no longer only "
      + "self-presentation. It is assembled from trace families the user "
      + "rarely sees in one place:",
    list([
      "public surfaces: search results, posts, bios, profiles, images",
      "commercial surfaces: broker files, ad categories, price signals",
      "institutional surfaces: records, forms, financial metadata",
      "machine surfaces: exports, tags, embeddings, agent-readable context",
    ]),
    "Optic gives the subject a way to inspect that assembly without "
      + "turning them into another productized dossier. It does not hand the "
      + "reader a new identity. It hands them the receipt for a possible "
      + "reading.",
    "The important distinction: Optic never says, \"this is who you "
      + "are.\" It says, \"under this evidence and this lens, this reading is "
      + "plausible, limited, and repairable.\" That difference is the "
      + "company.",
  ]),
  section("One-Sentence Definition", [
    "Optic turns user-authorized data into evidence-backed inference "
      + "cards that show what a person's digital traces may signal, to whom, "
      + "with what confidence, and what can be repaired.",
    "The sentence matters because it prevents category drift. It points "
      + "to a mirror with receipts, not another bureau, therapist, ranker, or "
      + "social graph.",
    "A card is valid only if its evidence, audience, confidence, caveat, "
      + "and repair path are visible. If a field is missing, the system "
      + "should mark the result incomplete rather than hiding the uncertainty "
      + "behind fluent language.",
  ]),
  section("The World Optic Assumes", [
    "Optic assumes that people are increasingly read through fragments. A "
      + "professional audience, a stranger, a commercial system, and an "
      + "eligibility system may each turn the same thin record into a "
      + "different operational story.",
    "The point is not that every system knows everything. The point is "
      + "worse and more practical: many systems know partial things, and "
      + "partial things can still affect price, trust, access, visibility, "
      + "and opportunity.",
    "Optic treats modern identity as an evidence environment. The user "
      + "lives inside it but rarely sees the environment as a system. Optic's "
      + "first job is to render the environment visible without exaggerating "
      + "its completeness.",
  ]),
  section("Algorithmic Identity Already Exists", [
    "Algorithmic identity is the operational model others form from a "
      + "person's traces. It does not need to be metaphysically true to "
      + "matter. A low-confidence category can still shape an ad, a search "
      + "result, a fraud flag, an underwriting question, or a human first "
      + "impression.",
    "Optic should be careful with language here. Platforms may infer; "
      + "advertisers may classify; institutions may screen; people may judge. "
      + "Optic should not claim secret access to proprietary models it cannot "
      + "inspect.",
    "The product's useful claim is narrower: from the evidence available, "
      + "Optic can estimate plausible readings, compare them across "
      + "audiences, and show the user where those readings are strong, weak, "
      + "stale, misleading, or repairable.",
  ]),
  section("The Invisible Data-Shadow", [
    "A data-shadow is the external shape cast by a person's traces. It is "
      + "not the person. It is the paper outline left after a life gets "
      + "compressed into records, posts, metadata, accounts, photos, "
      + "payments, forms, and searchable fragments.",
    "The danger of the metaphor is mysticism. Optic should not imply that "
      + "the shadow is total, hidden, or omniscient. A better product version "
      + "is brutally specific: this source exists, this signal is visible, "
      + "this audience may read it this way, and this source gap limits the "
      + "conclusion.",
    "The user value is immediate. People already clean resumes, curate "
      + "public profiles, remove broker listings, manage credit, and worry "
      + "about screenshots. Optic turns that scattered self-defense into one "
      + "audit loop.",
  ]),
  section("Why Users Cannot Inspect or Repair It", [
    "Most privacy tools answer the wrong layer. They help users download "
      + "data, delete accounts, block trackers, freeze credit, or remove "
      + "listings. Those are useful, but they do not show the inference "
      + "chain.",
    "A user can know that a platform has their activity history without "
      + "knowing what that activity implies. They can remove a broker listing "
      + "without seeing what other surfaces still support the same reading. "
      + "They can edit a profile without knowing whether the ambiguity was "
      + "solved or merely moved.",
    "Repair requires three things: visibility into the source, "
      + "translation into audience-specific meaning, and a concrete next "
      + "action. Optic is built around that triad.",
  ]),
  section("Existing Tools Are Fragmented", [
    "The adjacent tools are useful, but narrow:",
    list([
      "credit monitoring tracks credit files",
      "data removal services chase broker listings",
      "search cleanup tools manage discoverability",
      "password managers secure accounts",
      "privacy browsers limit collection",
      "reputation tools polish public surfaces",
    ]),
    "That fragmentation is the opening. Each category owns a task, but "
      + "none owns the interpretation layer across tasks. A user can buy "
      + "removal, monitoring, protection, or cleanup and still not know what "
      + "the combined surface says.",
    "The wedge is not \"privacy dashboard.\" That category is too broad "
      + "and too passive. The wedge is inference legibility: what am I "
      + "currently signaling, who might read it, what is wrong, and what "
      + "should I do first?",
  ]),
  section("What Optic Does", [
    "Optic ingests consented sources, preserves provenance, extracts "
      + "signals, maps them into candidate readings, and renders an audit "
      + "report.",
    "The report does not just say \"risk.\" It separates the finding into "
      + "visible parts:",
    list([
      "what source created the signal",
      "which audience lens might care",
      "what context weakens the reading",
      "what source is too sensitive for cloud processing",
      "what should be removed, clarified, separated, or left alone",
    ]),
    "The product loop is import, parse, classify, explain, repair, and "
      + "audit again. The first version can be assisted and human-reviewed, "
      + "but the product contract should be software-native from day one: "
      + "structured sources, structured findings, structured refusal, and "
      + "structured repair.",
  ]),
  section("Refusal Doctrine", [
    "Optic does not generate public scores, employer dashboards, dating "
      + "rankings, credit judgments, tenant screens, insurance eligibility "
      + "predictions, school admissions predictions, criminality labels, or "
      + "dossiers on non-consenting people.",
    "That doctrine is not fear. It is confidence about the category. "
      + "Optic is valuable because the subject is the customer, the evidence "
      + "is consented, and the output exists to help the subject understand "
      + "and repair a reading.",
    "The product must hard-code the boundary once and then stop "
      + "performing anxiety about it. No batch lookup. No hidden buyer "
      + "dashboard. No non-user identity graph. After that line is drawn, the "
      + "paper returns to the useful question: what can the user see and fix?",
  ]),
  section("User Doctrine: Ownership, Consent, Revocation", [
    "Optic starts with the subject. The user chooses what sources to "
      + "include, what purpose the audit serves, what stays local, what can "
      + "be temporarily processed, what can be deleted, and what can be "
      + "exported.",
    "Consent must be operational, not decorative. A checkbox is not "
      + "enough. Each source needs a scope, sensitivity level, retention "
      + "rule, processing boundary, deletion path, and export warning.",
    "Revocation must be visible. If the user deletes a source, Optic "
      + "should show what findings depended on it, what cached outputs "
      + "remain, and what can no longer be supported. The audit should "
      + "degrade honestly when evidence disappears.",
  ]),
  section("Primary Users and First Wedge", [
    "The first users are not everyone with data anxiety. They are people "
      + "whose opportunities depend on being read correctly: founders, "
      + "creators, job seekers, students, public-facing professionals, and "
      + "anyone entering a high-stakes evaluation moment.",
    "This wedge is emotionally obvious and commercially testable. The "
      + "buyer has an urgent before/after question, a finite source surface, "
      + "and a concrete audience in mind. A founder wants to know what "
      + "investors see. A job seeker wants to know what recruiters infer. A "
      + "creator wants to know whether their public surface signals "
      + "credibility, chaos, expertise, risk, or inconsistency.",
    "The first paid product should be an assisted audit, not a fully "
      + "automated app. Trust will come from a sharp report, a narrow source "
      + "set, human review where needed, and a repair loop the user can feel "
      + "after one session.",
  ]),
  section("Primary Use Cases", [
    "The core use case is a question: \"What would this audience infer "
      + "from my current evidence?\"",
    "The first lenses should be practical: recruiter, investor, stranger, "
      + "search, advertiser, and institution-adjacent. This is the canonical "
      + "audience set for v0.6; later sections use broader human, commercial, "
      + "and institutional language instead of relisting it.",
    "The product becomes powerful when it separates audience logic "
      + "instead of collapsing everything into one universal score.",
  ]),
  section("The Optic Audit", [
    "An Optic audit is a bounded procedure. The user states a goal, "
      + "selects sources, approves processing, reviews extracted signals, "
      + "receives inference cards, and chooses repair actions.",
    "The audit should begin narrow: public web, profile links, "
      + "user-uploaded files, screenshots, and manually supplied context. "
      + "Later versions can support platform exports, email, browser data, "
      + "financial records, device metadata, and deeper local parsing only "
      + "after the safety model is proven.",
    "A good audit is not maximal. A good audit is proportionate. More "
      + "data is not always more truth; sometimes it is just more liability.",
  ]),
  section("The Optic Report", [
    "The report is the visible artifact. It should read less like a "
      + "personality test and more like a forensic interface.",
    "Each finding should include: claim, audience, source, evidence span, "
      + "confidence band, counterargument, sensitivity, repair action, and "
      + "status. The report should also include source gaps: what Optic did "
      + "not see, what it cannot know, and what would change the conclusion.",
    "Export is dangerous. A report can become coercive evidence if a "
      + "school, employer, partner, parent, or institution demands to see it. "
      + "Optic should support selective export, watermarking, and warnings by "
      + "default.",
  ]),
  section("Human / Audience Mirrors", [
    "Human mirrors estimate high-context human readings of the user. They "
      + "inherit the audience set named in Primary Use Cases rather than "
      + "expanding it into a new taxonomy.",
    "The model should not pretend people are rational. Human reading is "
      + "noisy, status-sensitive, context-dependent, and often unfair. That "
      + "is why Optic should frame these findings as \"possible audience "
      + "readings,\" not truth claims.",
    "The repair layer matters most here. The answer is not always "
      + "deletion. Sometimes it is adding context, separating audiences, "
      + "making a stronger public anchor, clarifying a timeline, or doing "
      + "nothing because the supposed risk is not worth self-erasure.",
  ]),
  section("Platform and Advertiser Mirrors", [
    "Platform and advertiser mirrors estimate how commercial systems may "
      + "classify the user from behavior, profile data, interests, purchases, "
      + "clicks, follows, exports, and visible activity.",
    "This must be written with precision. Optic can compare user-supplied "
      + "platform exports, ad preference dashboards, public signals, and "
      + "known industry practices. It cannot claim to know TikTok's, Meta's, "
      + "Google's, or any other platform's internal model unless the user "
      + "provides actual records or the platform exposes them.",
    "The product value is still real. Even a plausible advertiser mirror "
      + "can show the user which signals are shaping their machine-readable "
      + "persona, which categories are sensitive, and which assumptions are "
      + "unsupported.",
  ]),
  section("Institutional Mirror Boundaries", [
    "Institutional mirrors are the most legally radioactive part of Optic "
      + "because eligibility contexts can trigger duties far beyond ordinary "
      + "self-audit. Optic must not become a consumer reporting agency by "
      + "accident.",
    "The safe version is educational and user-side. Optic can say: this "
      + "source may be relevant in an employment context, this discrepancy "
      + "may create confusion, this public record should be checked, this "
      + "document is sensitive, this claim should not be exported.",
    "The unsafe version predicts whether a landlord, lender, employer, or "
      + "insurer will accept the user. That version should be refused unless "
      + "the company deliberately enters that regulated domain with counsel, "
      + "licensing, compliance, and a different product architecture.",
  ]),
  section("Contradiction Layer", [
    "Contradiction is where the user's evidence points in different "
      + "directions. A resume says one thing, LinkedIn says another. A "
      + "founder bio signals discipline, public posts signal volatility. A "
      + "bank statement shows stability, search results suggest chaos.",
    "Contradiction is not moral failure. It is an interpretation problem. "
      + "Optic should show which audience might care, what source creates the "
      + "conflict, how severe it is, and whether the conflict is truthful "
      + "complexity or accidental confusion.",
    "This layer is one of Optic's best product differentiators. Most "
      + "tools clean surfaces. Optic can explain when surfaces disagree.",
  ]),
  section("Risk Layer", [
    "Risk is a plausible negative reading that conflicts with the user's "
      + "goals. It depends on audience, visibility, sensitivity, recency, "
      + "confidence, and repairability.",
    "Optic should not maximize fear. It should triage. A high-visibility, "
      + "high-confidence, easily repairable issue should come before a "
      + "speculative, low-visibility, emotionally charged issue. The product "
      + "should reduce panic by sorting action.",
    "Risk language must stay bounded: possible, plausible, unsupported, "
      + "sensitive, stale, contradicted, repairable, not repairable, not "
      + "worth acting on. The worst version of Optic makes users neurotic. "
      + "The good version gives them control.",
  ]),
  section("Coherence Layer", [
    "Coherence means the evidence can be understood in context. It does "
      + "not mean blandness, obedience, professionalism cosplay, or "
      + "algorithmic conformity.",
    "A coherent surface lets the right audience understand the user's "
      + "intent. A chaotic surface leaves important claims to be "
      + "reconstructed from fragments. Optic's job is not to flatten the "
      + "user; it is to show where the available evidence fails to carry the "
      + "intended meaning.",
    "This distinction should be explicit in the product. \"Clarify\" is "
      + "different from \"sanitize.\" \"Separate audiences\" is different "
      + "from \"hide yourself.\" \"Add context\" is different from \"perform "
      + "acceptability.\"",
  ]),
  section("Repair Layer", [
    "Repair is source-aware action. It can mean deleting, redacting, "
      + "clarifying, separating, opting out, freezing, contesting, publishing "
      + "context, changing privacy settings, updating profiles, or leaving "
      + "the record alone.",
    "Every repair action should have effort, risk, reversibility, "
      + "verification, and expected impact. \"Delete this\" is not always "
      + "safe. \"Clarify this\" may be better. \"Do nothing\" should be a "
      + "first-class outcome.",
    "The repair layer is where Optic becomes more than a mirror. The user "
      + "does not just learn what their data says. They learn which parts can "
      + "be changed, which should be left alone, and which require outside "
      + "process.",
  ]),
  section("Data Source Philosophy", [
    "Optic should not collect everything by default. A source is worth "
      + "ingesting only when its inference value justifies its sensitivity, "
      + "storage risk, legal risk, and user burden.",
    "The source ladder should move from readable and low-risk to intimate "
      + "and high-risk:",
    list([
      "start: public profiles, user links, uploaded resumes, screenshots",
      "next: platform exports, ad dashboards, people-search listings",
      "later: email, financial files, browser history, device metadata",
      "only with proof: deep local logs and high-sensitivity archives",
    ]),
    "The governing rule: source hunger is surveillance in disguise. Optic "
      + "should win by extracting more meaning from fewer sources before "
      + "asking for the intimate stuff.",
  ]),
  section("Data Source Matrix", [
    "Every source should be classified before ingestion. The matrix "
      + "should include source type, access method, sensitivity, retention, "
      + "local/cloud boundary, parsing method, inference value, failure mode, "
      + "deletion path, and legal review status.",
    "Example: a LinkedIn URL is low sensitivity, public, easy to parse, "
      + "useful for recruiter/investor mirrors, and easy to re-scan. A bank "
      + "export is high sensitivity, local-only, useful for stability or "
      + "financial-context audits, and dangerous to retain. Email is "
      + "extremely rich but high-risk because it contains third-party data "
      + "and private communications.",
    "This matrix should drive the product roadmap. Sources should not be "
      + "added because they sound powerful. They should be added because they "
      + "pass a value-to-risk gate.",
  ]),
  section("Consent and Permission Model", [
    "Consent should be attached to purpose. \"Analyze my public founder "
      + "surface for investor perception\" is different from \"analyze my "
      + "emails for relationship coherence\" or \"analyze my bank "
      + "transactions for institutional risk.\"",
    "The permission model should include source-level consent, "
      + "purpose-level consent, retention period, local/cloud boundary, "
      + "export permissions, and revocation. The user should be able to see a "
      + "consent receipt for each source.",
    "This matters because Optic's trust architecture is not just "
      + "encryption. It is legibility. The user should always know what was "
      + "processed, why it was processed, what it produced, and how to "
      + "destroy it.",
  ]),
  section("Local-First Architecture", [
    "The default architecture is local-first. Raw personal data should "
      + "live on the user's device whenever possible. Cloud assistance should "
      + "be treated as an exception requiring minimization, redaction, and "
      + "explicit purpose.",
    "The local app should maintain a vault, parser, source ledger, "
      + "identity graph, inference cache, report renderer, and deletion "
      + "ledger. Sensitive sources should never leave the device unless the "
      + "user explicitly chooses a cloud-assisted mode.",
    "Local-first is not just a privacy claim. It is product positioning. "
      + "Optic can only ask for intimate sources if the user believes the "
      + "company is structurally prevented from exploiting them.",
  ]),
  section("Cloud Assist Boundary", [
    "Cloud assist exists for tasks that are too heavy, too fresh, or too "
      + "connected for the device alone: public web search, source discovery, "
      + "large model reasoning, deduplication, or report drafting.",
    "The boundary must be visible. The app should show when a task is "
      + "local, when it is cloud-assisted, what data is sent, whether it is "
      + "redacted, how long it persists, and whether the output can be "
      + "reproduced locally.",
    "The safest pattern is ephemeral orchestration: send the minimum "
      + "needed, avoid raw vault upload, return structured results, and "
      + "delete transient state. Cloud should enhance the audit, not become "
      + "the real vault.",
  ]),
  section("Inference Engine", [
    "The inference engine turns traces into structured readings without "
      + "pretending those readings are final truth.",
    "The pipeline is: raw source -> artifact -> extracted signal -> "
      + "normalized feature -> candidate inference -> audience lens -> "
      + "confidence band -> counterargument -> repair action. The engine "
      + "should preserve provenance at every step.",
    "It should not begin as a giant model. It should begin as a schema "
      + "plus rules plus small models plus human review. The moat is not \"we "
      + "ran an LLM on your life.\" The moat is an auditable map of identity "
      + "signals, audience readings, source sensitivity, and repair logic.",
  ]),
  section("Identity Graph", [
    "The identity graph is the internal map connecting users, accounts, "
      + "platforms, artifacts, signals, inferences, audiences, risks, and "
      + "repairs.",
    "A good graph keeps evidence and interpretation separate. A post is "
      + "not a trait. A purchase is not a personality. A missing profile "
      + "field is not a defect. Each edge should state what it connects, why "
      + "it exists, how confident it is, and which audience lens uses it.",
    "This graph enables re-audits. When the user deletes a source, adds "
      + "context, updates a profile, or removes a broker listing, Optic can "
      + "show which findings changed and which remained.",
  ]),
  section("Signal and Inference Taxonomy", [
    "Signals are observable traces. Inferences are claims derived from "
      + "signals under context. The taxonomy should keep them separate.",
    "Signals may include recency, frequency, inconsistency, omission, "
      + "visibility, sentiment, affiliation, credential, transaction "
      + "category, public association, search prominence, profile "
      + "completeness, and source reliability. Inferences may include "
      + "credibility risk, expertise signal, volatility signal, financial "
      + "stability signal, audience mismatch, privacy exposure, or "
      + "contradiction.",
    "Sensitive inferences need gates. Health, sexuality, religion, "
      + "politics, race, disability, minors, finances, criminality, "
      + "immigration, and intimate relationships should be blocked, "
      + "minimized, or handled only under explicit safe contexts.",
  ]),
  section("Evidence, Confidence, Explainability", [
    "Every inference should be explainable without asking the user to "
      + "trust the model. The user should see the evidence span, the "
      + "reasoning path, the confidence band, and the counterargument.",
    "Confidence should not be a fake percentage. Better bands: weak, "
      + "plausible, strong, contradicted, stale, unsupported, sensitive, "
      + "disallowed. These labels are easier to understand and harder to "
      + "overinterpret.",
    "Explainability is also a safety feature. If the model cannot explain "
      + "why it made a finding, the user cannot repair it, and Optic should "
      + "not ship it as a finding.",
  ]),
  section("Report Schema", [
    "A report should have scope, source ledger, audience lenses, "
      + "findings, assumptions, source gaps, refusals, repair queue, export "
      + "policy, and deletion controls.",
    "Each finding should include: title, claim, audience, source IDs, "
      + "evidence spans, signal class, confidence band, caveat, "
      + "counterargument, sensitivity class, repair action, and verification "
      + "state.",
    "The schema matters because it keeps the product from becoming prose "
      + "sludge. Optic should produce structured objects first and narrative "
      + "explanation second.",
  ]),
  section("Repair Action Schema", [
    "A repair action should include target, action type, reason, expected "
      + "effect, effort, risk, reversibility, verification method, and "
      + "follow-up date.",
    "Action types include clarify, redact, separate, update, delete, opt "
      + "out, freeze, contest, publish context, change permissions, monitor, "
      + "or do nothing. \"Do nothing\" matters because not every "
      + "uncomfortable reading deserves action.",
    "The schema should also flag destructive actions. Deleting a source, "
      + "changing a public claim, or contesting a record may create "
      + "consequences. Optic should make the tradeoff visible before the user "
      + "acts.",
  ]),
  section("MVP Scope", [
    "The MVP should prove the loop, not the whole vision. The first "
      + "product can be a concierge audit wrapped in a local web app or "
      + "iPhone prototype, where a user imports a small bundle of sources and "
      + "receives evidence-backed inference cards.",
    "Minimum source set: public profile links, one uploaded resume or "
      + "bio, screenshots or copied text, public search snippets, and manual "
      + "context. Minimum output: source ledger, three audience lenses, ten "
      + "inference cards, confidence bands, counterarguments, and repair "
      + "actions.",
    "The MVP is successful if a user says, \"I did not realize this is "
      + "what I was signaling, and now I know exactly what to change.\" The "
      + "measurable version of that signal is paid demand, referral behavior, "
      + "visible repair, and repeat audit intent.",
  ]),
  section("Technical Stack and Model Strategy", [
    "The first stack should be boring: encrypted local storage, "
      + "structured JSON schemas, deterministic parsers where possible, and "
      + "small local models for classification or summarization.",
    "For mobile, the long-term direction is Swift, Core ML, "
      + "Keychain/Secure Enclave-backed storage, and a small on-device model. "
      + "For the weekend, a web prototype with local storage, file import, "
      + "manual source entry, and an LLM-assisted report generator is enough.",
    "The model strategy should be layered: rules for safety, embeddings "
      + "for retrieval, small local models for classification, larger models "
      + "for optional cloud assist, and human review for early paid audits.",
  ]),
  section("Threat Model", [
    "Optic handles dangerous data. Threats include stolen devices, cloud "
      + "leakage, prompt injection, malicious uploaded files, screenshots, "
      + "coerced exports, abusive partners, employers demanding reports, "
      + "future acquirer incentives, and the company itself drifting toward "
      + "buyer-side scoring.",
    "The safety design should assume that the report may be misused. It "
      + "should include local encryption, source minimization, export "
      + "warnings, selected sharing, watermarking, sensitive inference gates, "
      + "refusal modes, and deletion receipts.",
    "The hardest threat is not a hacker. It is incentives. If Optic's "
      + "best monetization path becomes selling judgment tools to "
      + "institutions, the product has failed its founding premise.",
  ]),
  section("Abuse Controls", [
    "Abuse controls are the implementation layer behind the Refusal "
      + "Doctrine. They should be quiet, automatic, and testable rather than "
      + "rhetorically loud.",
    "The app should reject prompts that violate consent, protected-trait "
      + "rules, eligibility boundaries, coercive export rules, or deception "
      + "rules. Those checks belong in prompt filters, schema validators, "
      + "export gates, and review tooling.",
    "The distinction is consent plus control. The subject can inspect "
      + "their own surface; the product should not become a weapon against "
      + "someone else.",
  ]),
  section("Regulatory Surface", [
    "Optic touches privacy, consumer protection, data portability, "
      + "biometrics, financial data, minors, employment screening, credit "
      + "reporting, and AI governance. The exact legal exposure depends on "
      + "sources, users, outputs, exports, and customers.",
    "The safest early posture is user-side, educational, non-eligibility, "
      + "non-decisioning, and narrow-scope. Anything involving employment, "
      + "credit, housing, insurance, or education requires counsel before "
      + "productization.",
    "The regulatory thesis should be humble: Optic can be built safely "
      + "only if it refuses certain markets, treats sensitive data carefully, "
      + "and separates self-understanding from institutional judgment.",
  ]),
  section("Competitive Landscape and Business Model", [
    "Optic competes across fragments: data removal, reputation "
      + "management, credit monitoring, privacy tools, personal AI, search "
      + "cleanup, and identity protection. Those markets are useful proof "
      + "that people already pay around the problem. Optic's differentiated "
      + "category is inference audit plus repair.",
    "Near-term monetization should be user-paid audits: founder audit, "
      + "career surface audit, creator audit, public profile audit, and "
      + "premium re-audit. The company should charge for clarity, not sell "
      + "access to the subject.",
    "The compounding asset is not a hidden dossier database. It is the "
      + "user-side ontology: source schemas, inference classes, audience "
      + "lenses, repair playbooks, safety refusals, and calibration from "
      + "consenting audits. Later revenue can include local app subscription, "
      + "paid repair workflows, privacy partner referrals, verified consent "
      + "receipts, or user-controlled data licensing, but data resale should "
      + "not be the default pitch. The trust cost is enormous.",
  ]),
  section("Roadmap and Validation Agenda", [
    "The validation agenda should be concrete and kill-gated. First, "
      + "prove that users care after seeing an audit. Second, prove that they "
      + "will pay before automation is perfect. Third, prove that repair "
      + "actions change the surface. Fourth, prove that the source set can "
      + "expand without destroying trust. Fifth, prove that the architecture "
      + "can handle enough data to be useful.",
    "Milestones: weekend MVP, five manual audits, ten paid audits, source "
      + "matrix, safety policy, local vault prototype, mobile proof, repeat "
      + "audit loop, and a small validation study comparing audience readings "
      + "before and after repair.",
    "The company story is not \"we built social credit for yourself.\" It "
      + "is: inferred identity already affects people, existing tools are "
      + "fragmented, and Optic is the private user-side control panel for "
      + "seeing and repairing that layer. If paid audits do not create "
      + "urgency, the category is too early. If repairs do not create visible "
      + "change, the product is only interesting. If trust fails, the company "
      + "should stop before scale.",
  ]),
  section("2030 Thesis", [
    "By 2030, more of life will be mediated by AI agents, automated "
      + "screening, personalized feeds, generated search, identity graphs, "
      + "and machine-readable context. The question changes from \"what do "
      + "humans think of me?\" to \"what do systems think I am?\"",
    "Optic's long-term version is a personal glass box for algorithmic "
      + "identity. Inspect the reading. Contest the reading. Repair the "
      + "reading. Keep the evidence yours.",
    "The future is not inevitable. Optic only deserves to exist if the "
      + "early product proves the trust loop: consented sources, local "
      + "control, evidence-backed inferences, refusal boundaries, and real "
      + "repair. The 2030 vision is earned by refusing the easy evil version "
      + "now.",
  ]),
];

export const essayAppendices = [
  appendix("A", "Glossary", [
    "Source: Any user-authorized artifact, record, profile, export, link, "
      + "screenshot, file, or data stream used in the audit.",
    "Signal: An observable trace extracted from a source.",
    "Inference: A claim derived from signals under an audience and context.",
    "Audience lens: A declared reader model. The v0.6 lens set is defined "
      + "once in Primary Use Cases.",
    "Repair action: A source-aware step that can clarify, remove, "
      + "separate, contest, or monitor a finding.",
  ]),
  appendix("B", "Source Matrix Fields", [
    "Source type, access method, owner, sensitivity, retention rule, "
      + "local/cloud boundary, parser, inference value, failure mode, "
      + "deletion path, legal review status, MVP status.",
  ]),
  appendix("C", "Identity Graph Objects", [
    "Canonical objects live in the Inference Engine and Report Schema "
      + "sections. The appendix exists only to point implementers back to "
      + "those definitions.",
  ]),
  appendix("D", "Inference Classes", [
    "Defined in Evidence, Confidence, Explainability. Do not duplicate "
      + "the class list in UI copy; reference the source enum.",
  ]),
  appendix("E", "Report Sections", [
    "Defined in Report Schema. Treat the appendix as an implementation "
      + "index, not a second schema.",
  ]),
  appendix("F", "Repair Actions", [
    "Defined in Repair Action Schema. Product copy should name only the "
      + "action relevant to the current finding.",
  ]),
  appendix("G", "Threat Model", [
    "Threat Model is canonical. This appendix tracks review status, "
      + "owners, and controls rather than repeating the threat list.",
  ]),
  appendix("H", "Safety Policy", [
    "Safety Policy points to Refusal Doctrine, Institutional Mirror "
      + "Boundaries, and Abuse Controls as the canonical refusal text.",
  ]),
  appendix("I", "MVP Screens", [
    "Consent screen, source import, source ledger, audience selector, "
      + "inference cards, evidence drawer, repair queue, export warning, "
      + "delete vault.",
  ]),
  appendix("J", "Open Questions", [
    "Which first wedge pays fastest? Which source mix creates the "
      + "strongest moment of recognition? What repairs are measurable? What "
      + "can run locally on iPhone? Which source types are too dangerous for "
      + "v1? What legal lines require hard refusal?",
  ]),
];

function section(title, essay) {
  return { essay, title };
}

function appendix(letter, title, entries) {
  return { entries, id: `APP-${letter}`, title };
}

function list(items) {
  return { items, type: "list" };
}
