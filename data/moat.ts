import type { MoatCard } from './types';

export const moatCards: MoatCard[] = [
  {
    label: '01 — Access',
    heading: 'Authorized scope only.',
    body: 'Optic processes only what you explicitly authorize. No passive capture, no background scraping, no inference from adjacent accounts.',
  },
  {
    label: '02 — Privacy',
    heading: 'Local-first processing.',
    body: 'Analysis runs on your device. Raw personal data does not transit a server. The report exists for you — not as input into a platform data model.',
  },
  {
    label: '03 — Boundary',
    heading: 'Subject-owned, not buyer-owned.',
    body: 'No employer, lender, or institution can purchase a dashboard view of your report. The product is built for the subject, not the evaluator.',
  },
];

export const boundaryPills = [
  'No non-user dossiers',
  'No public ranking',
  'No coercive export',
] as const;
