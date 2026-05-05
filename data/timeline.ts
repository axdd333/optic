import type { TimelineItem, BusinessModelRow } from './types';

export const timelineItems: TimelineItem[] = [
  {
    phase: 'Now',
    heading: 'Private audit product',
    body: 'Local-first audit for founders, professionals, and creators navigating high-stakes transitions.',
    active: true,
  },
  {
    phase: 'Next',
    heading: 'Monitoring and re-audit',
    body: 'Track footprint changes over time. Alert on new public signals. Measure repair actions before and after.',
    active: true,
  },
  {
    phase: 'Later',
    heading: 'Team and organizational lens',
    body: 'Private audit tooling for companies preparing for due diligence, media cycles, or regulatory review.',
    active: false,
  },
  {
    phase: 'Vision',
    heading: 'User-owned data economy',
    body: 'Voluntary, anonymized contribution improves the system. Users benefit from the network they build rather than extracting it.',
    active: false,
  },
];

export const businessModelRows: BusinessModelRow[] = [
  {
    phase: 'Initial',
    heading: 'Audit subscription',
    body: 'Individual audits and monthly monitoring subscriptions for high-stakes professionals.',
  },
  {
    phase: 'Expansion',
    heading: 'Team and enterprise',
    body: 'Bulk audit tooling for companies, agencies, and advisors managing multiple subjects.',
  },
  {
    phase: 'Network',
    heading: 'Calibration marketplace',
    body: 'Opt-in data contribution layer where users share anonymized signals to improve inference and receive value from the network.',
  },
];
