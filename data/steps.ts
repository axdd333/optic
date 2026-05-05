import type { Step } from './types';

export const steps: Step[] = [
  {
    number: '01',
    title: 'Collect',
    description: 'Authorize a limited set of sources and define scope.',
    icon: 'collect',
  },
  {
    number: '02',
    title: 'Analyze',
    description: 'Map signals locally on device. Raw personal data never leaves your machine.',
    icon: 'analyze',
  },
  {
    number: '03',
    title: 'Reveal',
    description: 'See likely readings, contradictions, and gaps between intent and signal.',
    icon: 'reveal',
  },
  {
    number: '04',
    title: 'Repair',
    description: 'Clarify the story with evidence. Ranked actions by impact and effort.',
    icon: 'repair',
  },
  {
    number: '05',
    title: 'Re-audit',
    description: 'Track whether the footprint improved. Measure before and after.',
    icon: 'reaudit',
  },
];
