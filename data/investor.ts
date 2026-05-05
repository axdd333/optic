import type { InvestorSection } from './types';

export const investorSections: InvestorSection[] = [
  {
    id: 'thesis',
    eyebrow: 'Foundation',
    heading: 'The company is a mirror with receipts.',
    body: 'A private perception intelligence layer, starting with high-stakes professional identity audits. Optic gives individuals the feedback loop digital life removed: what their authorized data signals, how it may be interpreted, and what to repair before it affects trust, access, or opportunity.',
    dark: false,
    visual: {
      alt: 'Evidence receipts orbiting an Optic perception mirror',
      src: '/investors/memos/memo-01.png',
    },
  },
  {
    id: 'why-now',
    eyebrow: 'Market timing',
    heading: 'The internet created a second self.',
    body: 'Reputation is shaped by emails, calendar patterns, public profiles, search results, documents, metadata, social history, and institutional traces. AI makes those fragments easier to interpret and harder for individuals to inspect. More signals than people can read. Higher stakes for being misread. No user-side interpretation layer. That gap is the market.',
    dark: true,
    visual: {
      alt: 'Public digital traces forming a second identity map',
      src: '/investors/memos/memo-02.png',
    },
  },
  {
    id: 'asymmetry',
    eyebrow: 'The opportunity',
    heading: 'The asymmetry is the company.',
    body: 'Institutions and AI systems can pre-read people at scale. Individuals cannot see the output. Every recruiter, investor, and background check firm has tools for this. None of those tools face the subject. Optic builds the subject-facing side of that same inference stack.',
    dark: false,
    visual: {
      alt: 'Institutional evaluation panels balanced by a subject mirror',
      src: '/investors/memos/memo-03.png',
    },
  },
  {
    id: 'product',
    eyebrow: 'Product',
    heading: 'The product is a private mirror.',
    body: 'Users connect a limited set of sources. Optic processes privately on device and produces a baseline profile: signals, implications, contradictions, risks, and practical repair actions. The first product is useful before the network exists. No dependency on a data moat or critical mass.',
    dark: false,
    visual: {
      alt: 'Private audit interface with signals and repair actions',
      src: '/investors/memos/memo-04.png',
    },
  },
  {
    id: 'wedge',
    eyebrow: 'Go to market',
    heading: 'The wedge is high-stakes transition.',
    body: 'The first wedge is private audits for founders preparing to raise, professionals preparing for hiring, creators managing public reputation, and individuals entering high-stakes transitions. These are moments when being misread is expensive — and when someone will pay for clarity rather than live with the uncertainty.',
    dark: true,
    visual: {
      alt: 'High-stakes transition lanes converging into an audit checkpoint',
      src: '/investors/memos/memo-05.png',
    },
  },
  {
    id: 'moat',
    eyebrow: 'Trust moat',
    heading: 'The moat is trusted access.',
    body: 'The product only works if users authorize real data. They will only authorize real data if they trust the architecture. Trust is not a feature — it is the entry condition. Subject-owned means no non-user dossiers, no public ranking, and no coercive export. These are architectural commitments, not marketing copy.',
    dark: false,
    visual: {
      alt: 'Subject-owned data protected inside a private access boundary',
      src: '/investors/memos/memo-06.png',
    },
  },
  {
    id: 'arc',
    eyebrow: 'Long arc',
    heading: 'The long arc is a user-owned data economy.',
    body: 'Over time, users may contribute anonymized or privacy-preserving data to improve the inference system and benefit from the network — instead of letting platforms extract behavioral data without compensation. Calibration can become a marketplace where users are participants, not products.',
    dark: true,
    visual: {
      alt: 'Distributed user-owned data vaults feeding a calibration network',
      src: '/investors/memos/memo-07.png',
    },
  },
];

export const investorCta = {
  heading: 'If the world is going to infer you, you should get to see the inference first.',
  subtext:
    'Optic is building the subject-side of the evaluation stack. We are speaking with seed investors who understand that trust infrastructure is not a product feature — it is a category.',
  contactLabel: 'Contact',
  contactHref: 'mailto:hello@tryoptic.app?subject=Optic%20investor%20inquiry',
};
