export type Step = {
  number: string;
  title: string;
  description: string;
  icon: 'collect' | 'analyze' | 'reveal' | 'repair' | 'reaudit';
};

export type WedgeCard = {
  number: string;
  title: string;
  description: string;
};

export type FeatureRow = {
  number: string;
  heading: string;
  body: string;
  visualType: 'signals' | 'implication' | 'repair';
  reversed: boolean;
};

export type MoatCard = {
  label: string;
  heading: string;
  body: string;
};

export type TimelineItem = {
  phase: 'Now' | 'Next' | 'Later' | 'Vision';
  heading: string;
  body: string;
  active: boolean;
};

export type FaqItem = {
  id: string;
  question: string;
  answer: string;
};

export type InvestorSection = {
  id: string;
  eyebrow: string;
  heading: string;
  body: string;
  dark: boolean;
  visual: {
    alt: string;
    src: string;
  };
};

export type BusinessModelRow = {
  phase: 'Initial' | 'Expansion' | 'Network';
  heading: string;
  body: string;
};
