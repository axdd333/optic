export const opticCfg = {
  canonicalUrl: "https://optic.xtcftw.com/",
  ctaEmail: "hello@tryoptic.app",
  ctaSubject: "Optic pilot audit",
  description: "Optic is a private feedback layer for how people are "
    + "perceived, starting with high-stakes professional contexts, with "
    + "user-owned data and optional calibration over time.",
  docUrl: "/docs/optic-whitepaper.md",
  title: "Optic | Private perception intelligence",
  version: "v1.0",
};

export const hero = {
  body: "Optic is building a private identity feedback system for a world "
    + "where people are increasingly judged through fragments of digital "
    + "information.",
  lede: "Private perception intelligence for high-stakes professional life.",
  primaryCta: "Request pilot audit",
  secondaryCta: "Read the thesis",
  title: "Optic",
};

export const publicSections = [
  nav("why", "Why now"),
  nav("product", "Product"),
  nav("wedge", "Wedge"),
  nav("calibration", "Calibration"),
  nav("trust", "Boundary"),
  nav("brief", "Brief"),
];

export const sections = [
  sec("why", "Digital life now produces a second self.", [
    "Today, a person's reputation is shaped by scattered signals: emails, "
      + "calendar patterns, public profiles, search results, documents, "
      + "metadata, social history, and institutional traces.",
    "These signals influence how people are perceived by employers, "
      + "investors, institutions, partners, and peers, but individuals rarely "
      + "have a clear way to understand what their own data is signaling.",
    "We live inside digital systems that constantly interpret us, yet we "
      + "have almost no tools to inspect or improve those interpretations.",
  ]),
  sec("product", "Optic is the private feedback layer.", [
    "Optic gives users a private way to understand how they may be "
      + "perceived across personal, professional, and social contexts.",
    "The product analyzes user-authorized data and turns it into a clear, "
      + "actionable profile: what signals exist, what they may imply, where "
      + "the risks or contradictions are, and how the user can improve the "
      + "way they are understood.",
    "The goal is not to punish users, expose them, or create a public "
      + "ranking system. The goal is to give people the feedback loop that "
      + "modern digital life has removed.",
  ]),
  sec("audit", "The first version", [
    "The first version of Optic is a local, opt-in audit tool.",
    "Users connect a limited set of personal data sources, such as email, "
      + "calendar metadata, documents, public profiles, and local files.",
    "Optic processes this information privately on-device and produces an "
      + "initial baseline: a structured view of the user's digital footprint, "
      + "the patterns it reveals, and the specific areas where clarification, "
      + "repair, or improvement may be useful.",
    "This gives users immediate value without requiring them to surrender "
      + "control of their data.",
  ]),
  sec("calibration", "Continuous calibration", [
    "Over time, Optic can become a continuous calibration layer.",
    "Users may choose to contribute anonymized or privacy-preserving data to "
      + "improve the system and, in return, participate in a user-owned data "
      + "economy.",
    "Instead of platforms extracting behavioral data without meaningful "
      + "compensation, Optic creates a model where users understand the value "
      + "of their data, control what is shared, and can benefit from "
      + "contributing to the network.",
  ]),
  sec("vision", "Personal AI feedback", [
    "The long-term vision is a personal AI feedback system that helps people "
      + "navigate an increasingly complex social and professional world.",
    "As AI systems become more involved in hiring, fundraising, lending, "
      + "reputation, dating, education, and daily communication, people will "
      + "need their own tools to understand how they are being read.",
    "Optic becomes that layer: a private, user-controlled system for "
      + "self-understanding, reputation repair, and social calibration.",
  ]),
  sec("trust", "What Optic is not", [
    "Optic is not a surveillance product. It is not a government social "
      + "credit system. It is not a public score for institutions to use "
      + "against people.",
    "It is a user-side product that helps individuals see themselves more "
      + "clearly, understand how their behavior and data may be interpreted, "
      + "and make better decisions about how they present, communicate, and "
      + "operate.",
  ]),
  sec("wedge", "The starting wedge", [
    "We are starting with a narrow, useful wedge: private audits for people "
      + "in high-stakes moments, such as founders preparing to fundraise, "
      + "professionals preparing for hiring, creators managing public "
      + "reputation, and individuals who want to understand their digital "
      + "footprint.",
    "From there, Optic can expand into a broader personal intelligence layer "
      + "for identity, reputation, and behavioral feedback.",
  ]),
  sec("thesis", "The core thesis", [
    "Modern life produces more signals than humans can interpret.",
    "Optic turns those signals into private, actionable feedback.",
    "It gives people a way to understand how they are seen, correct what is "
      + "wrong, and regain agency over their digital identity.",
  ]),
];

export const signals = [
  "Emails",
  "Calendar patterns",
  "Public profiles",
  "Search results",
  "Documents",
  "Metadata",
  "Social history",
  "Institutional traces",
];

export const audiences = [
  row("Founders", "Preparing to fundraise."),
  row("Professionals", "Preparing for hiring."),
  row("Creators", "Managing public reputation."),
  row("Individuals", "Understanding a digital footprint."),
];

export const auditSteps = [
  step("Authorize", "Connect a limited set of personal data sources."),
  step("Process", "Analyze the information privately on device."),
  step("Baseline", "Produce a structured view of the digital footprint."),
  step("Interpret", "Show patterns, implications, risks, and contradictions."),
  step("Improve", "Identify clarification, repair, or improvement paths."),
  step("Calibrate", "Optionally contribute privacy-preserving data over time."),
];

export const profileParts = [
  row("Signals", "What exists across authorized sources."),
  row("Implications", "What those signals may imply."),
  row("Contradictions", "Where perception may diverge from intent."),
  row("Actions", "How the user can improve the way they are understood."),
];

export const principles = [
  row("Private", "User-authorized data and opt-in access."),
  row("Local first", "The first audit processes personal data on device."),
  row("User owned", "People control what is shared and when."),
  row("Actionable", "Feedback is tied to clarification, repair, or change."),
];

export const brief = {
  heading: "Optic turns signals into private, actionable feedback.",
  path: opticCfg.docUrl,
};

export const intro = [hero.body, hero.lede];
export const bodySections = sections.map(toBody);
export const appendices = [];
export const claims = [];
export const sources = [];
export const sourceGaps = [];
export const validationAgenda = sourceGaps;
export const zinePlates = [];
export const sampleReport = { findings: [], lenses: [] };
export const trustCards = principles;

function nav(id, label) {
  return { id, label };
}

function sec(id, title, body) {
  return { body, id, title };
}

function row(title, body) {
  return { body, title };
}

function step(title, body) {
  return { body, title };
}

function toBody(item, idx) {
  return {
    atomic: [`OPTIC-${String(idx + 1).padStart(3, "0")}`],
    essay: item.body,
    id: item.id,
    title: item.title,
  };
}
