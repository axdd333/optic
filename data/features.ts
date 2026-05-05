import type { FeatureRow } from './types';

export const featureRows: FeatureRow[] = [
  {
    number: '01 — Signals',
    heading: 'The record is already speaking. You just can’t hear it.',
    body: 'Optic maps the surfaces a stranger would read when they look you up — social profiles, news mentions, public records, job history, open-web presence. You see what they see before they decide anything.',
    visualType: 'signals',
    reversed: false,
  },
  {
    number: '02 — Implication',
    heading: 'The opinion formed before you arrived.',
    body: 'Raw signals become inferences. A strong track record with an unclear narrative reads as unreliable. A gap in history reads as risk. A visible contradiction reads as a flag. Optic surfaces the logical chain so you can see the story being told about you.',
    visualType: 'implication',
    reversed: true,
  },
  {
    number: '03 — Repair',
    heading: 'Where to start when the story needs fixing.',
    body: 'Not a list of vague suggestions. A ranked set of actions — highest impact first, lowest effort where possible — each with a source, a reason, and a way to verify it landed.',
    visualType: 'repair',
    reversed: false,
  },
];
