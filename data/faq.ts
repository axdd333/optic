import type { FaqItem } from './types';

export const faqItems: FaqItem[] = [
  {
    id: 'q1',
    question: 'What does Optic actually look at?',
    answer:
      'The same surfaces anyone else would look at — social profiles, news mentions, public records, job history, open-web presence. You authorize exactly which sources are in scope. Nothing is collected passively or without your instruction. Optic reads what is already readable.',
  },
  {
    id: 'q2',
    question: 'Does Optic sell or share my data?',
    answer:
      'No. Your report is for you. Optic does not sell your data to employers, data brokers, or any third party. Processing is local-first — raw personal data stays on your device. There is no buyer dashboard, no institutional feed, and no public profile created from your audit. The product only works if you trust it completely.',
  },
  {
    id: 'q3',
    question: 'What does the audit actually produce?',
    answer:
      'A private report with four layers: the signals Optic found, the likely inferences those signals create in a reader, any contradictions or gaps between your intent and your digital record, and a ranked repair list — specific actions ordered by impact and effort. You see the receipts, not just a score.',
  },
  {
    id: 'q4',
    question: 'Can institutions use Optic to evaluate people without their consent?',
    answer:
      'No. Optic is built for subjects, not evaluators. There is no institutional product, no employer license, and no way to run an audit on someone who has not authorized it. This is an architectural constraint, not a policy. The product does not have a mode for uninvited evaluation.',
  },
  {
    id: 'q5',
    question: 'Why now? Is this a new problem?',
    answer:
      "Public digital records have always existed, but AI changed what you can do with them. What once required a specialist to synthesize — a background check firm, an experienced researcher — can now be assembled automatically from fragments at scale. The asymmetry grew quietly: institutions and AI systems can pre-read people before any interaction begins. Individuals still have no equivalent feedback loop. That's the gap Optic closes.",
  },
  {
    id: 'q6',
    question: 'How is this different from a reputation management service?',
    answer:
      "Reputation management services typically focus on suppressing negative search results or generating positive content. Optic does neither. It is a diagnostic tool — it shows you what the current record implies, where the contradictions are, and what the highest-impact repairs would be. You decide what to do with that information. The goal is an accurate reading, not a clean one.",
  },
];
