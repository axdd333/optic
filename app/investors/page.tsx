import type { Metadata } from 'next';
import Image from 'next/image';
import type { InvestorSection } from '@/data/types';
import { investorSections, investorCta } from '@/data/investor';
import SectionEyebrow from '@/components/ui/SectionEyebrow';
import Button from '@/components/ui/Button';

const logos = [
  ['LinkedIn', 'linkedin.svg'],
  ['X', 'x.svg'],
  ['GitHub', 'github.svg'],
  ['Reddit', 'reddit.svg'],
  ['Google', 'google.svg'],
  ['YouTube', 'youtube.svg'],
  ['Instagram', 'instagram.svg'],
  ['TikTok', 'tiktok.svg'],
  ['Substack', 'substack.svg'],
] as const;

const facts = [
  ['Input', 'User-authorized sources only'],
  ['Output', 'Signals, implications, contradictions, repair'],
  ['Boundary', 'No public score or third-party dossier'],
];

const generated = [
  {
    alt: 'Optic source-to-inference workflow',
    body: 'User-authorized sources become signals, implications, and repair.',
    src: '/investors/generated/source-workflow.png',
    title: 'How signals become a private reading',
  },
  {
    alt: 'Optic trust architecture workflow',
    body: 'Founder, hiring, and creator audits share one private boundary.',
    src: '/investors/generated/trust-architecture.png',
    title: 'Where the wedge expands',
  },
];

export const metadata: Metadata = {
  title: 'Investor Brief - Optic',
  description:
    'The private mirror for reputation in an AI-gated world. The investor '
    + 'case for user-owned perception intelligence.',
};

export default function InvestorsPage() {
  return (
    <main>
      <Hero />
      <SourceStrip />
      <InvestorFacts />
      <GeneratedAssets />
      {investorSections.map((section, idx) => (
        <MemoSection key={section.id} idx={idx} section={section} />
      ))}
      <Cta />
    </main>
  );
}

function Hero() {
  return (
    <section className="w-full bg-[var(--color-section-dark)] py-20 md:py-32">
      <div className="mx-auto grid max-w-[1200px] gap-10 px-6
        md:grid-cols-[0.78fr_1fr] md:items-center">
        <div>
          <SectionEyebrow light className="mb-6">
            Investor field guide · v1.0
          </SectionEyebrow>
          <h1 className="mb-6 font-serif text-4xl font-semibold leading-[1.1]
            tracking-tight text-[var(--color-section-dark-text)] md:text-5xl
            lg:text-6xl">
            The private mirror for reputation in an AI-gated world.
          </h1>
          <p className="max-w-xl text-lg leading-relaxed
            text-[rgba(245,243,239,0.56)]">
            A local-first perception intelligence layer for high-stakes
            professional identity audits.
          </p>
        </div>
        <ReportVisual />
      </div>
    </section>
  );
}

function ReportVisual() {
  return (
    <figure className="overflow-hidden rounded-[18px] border border-white/15
      bg-black shadow-[0_24px_80px_rgba(0,0,0,0.38)]">
      <Image
        alt="Optic sample report with sources, confidence, and next steps"
        className="aspect-[16/9] w-full object-cover"
        height={941}
        priority
        src="/investors/generated/audit-interface.png"
        width={1672}
      />
    </figure>
  );
}

function SourceStrip() {
  return (
    <section className="w-full border-b border-[var(--color-border)]
      bg-white py-8">
      <div className="mx-auto max-w-[1200px] px-6">
        <p className="mb-5 font-mono text-[10px] uppercase tracking-widest
          text-[var(--color-muted)]">
          Source surfaces in the first audit
        </p>
        <ul className="grid grid-cols-3 gap-px overflow-hidden rounded-2xl
          border border-[var(--color-border)] bg-[var(--color-border)]
          sm:grid-cols-5 md:grid-cols-9">
          {logos.map(([name, file]) => (
            <li
              key={name}
              className="flex min-h-28 flex-col items-center justify-center
                gap-3 bg-[var(--color-cream)] p-4"
            >
              <Image
                alt=""
                aria-hidden="true"
                height={28}
                src={`/investors/logos/${file}`}
                width={28}
              />
              <span className="text-xs text-[var(--color-muted)]">
                {name}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function InvestorFacts() {
  return (
    <section className="w-full bg-[var(--color-cream)] py-10">
      <div className="mx-auto grid max-w-[1200px] gap-px px-6 md:grid-cols-3">
        {facts.map(([label, copy]) => (
          <div
            key={label}
            className="border border-[var(--color-border)] bg-white p-6"
          >
            <p className="mb-3 font-mono text-[10px] uppercase tracking-widest
              text-[var(--color-muted)]">
              {label}
            </p>
            <p className="text-base font-medium text-[var(--color-ink)]">
              {copy}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

function GeneratedAssets() {
  return (
    <section className="w-full bg-white py-16 md:py-20">
      <div className="mx-auto max-w-[1200px] px-6">
        <div className="mb-8 max-w-2xl">
          <SectionEyebrow className="mb-4">Product system</SectionEyebrow>
          <h2 className="font-serif text-3xl font-semibold leading-tight
            text-[var(--color-ink)] md:text-4xl">
            A private audit stack investors can understand at a glance.
          </h2>
        </div>
        <div className="grid gap-6 md:grid-cols-2">
          {generated.map((asset) => (
            <figure
              key={asset.src}
              className="overflow-hidden rounded-[16px] border
                border-[var(--color-border)] bg-[var(--color-cream)]"
            >
              <Image
                alt={asset.alt}
                className="aspect-[16/9] w-full object-cover"
                height={941}
                src={asset.src}
                width={1672}
              />
              <figcaption className="border-t border-[var(--color-border)]
                bg-white p-5">
                <strong className="block text-base text-[var(--color-ink)]">
                  {asset.title}
                </strong>
                <span className="mt-1 block text-sm leading-relaxed
                  text-[var(--color-muted)]">
                  {asset.body}
                </span>
              </figcaption>
            </figure>
          ))}
        </div>
      </div>
    </section>
  );
}

function MemoSection({ idx, section }: {
  idx: number;
  section: InvestorSection;
}) {
  const dark = section.dark;
  const flip = idx % 2 === 1;

  return (
    <section
      id={section.id}
      className="w-full py-20 md:py-28"
      style={{
        background: dark ? 'var(--color-section-dark)' : 'var(--color-cream)',
        scrollMarginTop: '80px',
      }}
    >
      <div className={`mx-auto grid max-w-[1200px] gap-10 px-6
        md:grid-cols-[0.52fr_0.48fr] md:items-center ${flip
          ? 'md:[&>*:first-child]:order-2'
          : ''}`}>
        <div>
          <SectionCopy section={section} />
          <SectionIndex dark={dark} idx={idx} section={section} />
        </div>
        <MemoVisual dark={dark} section={section} />
      </div>
    </section>
  );
}

function SectionCopy({ section }: { section: InvestorSection }) {
  const dark = section.dark;

  return (
    <div className="max-w-3xl">
      <SectionEyebrow light={dark} className="mb-5">
        {section.eyebrow}
      </SectionEyebrow>
      <h2 className={`mb-5 font-serif text-3xl font-semibold leading-tight
        md:text-4xl ${dark
          ? 'text-[var(--color-section-dark-text)]'
          : 'text-[var(--color-ink)]'}`}>
        {section.heading}
      </h2>
      <p className={`text-lg leading-relaxed ${dark
        ? 'text-[rgba(245,243,239,0.56)]'
        : 'text-[var(--color-muted)]'}`}>
        {section.body}
      </p>
    </div>
  );
}

function MemoVisual({ dark, section }: {
  dark: boolean;
  section: InvestorSection;
}) {
  return (
    <figure
      className={`overflow-hidden rounded-[18px] border shadow-sm ${dark
        ? 'border-white/15 bg-white/5 shadow-black/20'
        : 'border-[var(--color-border)] bg-white shadow-black/5'}`}
    >
      <Image
        alt={section.visual.alt}
        className="aspect-[16/9] w-full object-cover"
        height={941}
        src={section.visual.src}
        width={1672}
      />
    </figure>
  );
}

function SectionIndex({ dark, idx, section }: {
  dark: boolean;
  idx: number;
  section: InvestorSection;
}) {
  const num = String(idx + 1).padStart(2, '0');

  return (
    <aside
      className={`mt-8 border p-5 ${dark
        ? 'border-white/15 text-[rgba(245,243,239,0.62)]'
        : 'border-[var(--color-border)] text-[var(--color-muted)]'}`}
    >
      <p className="mb-8 font-mono text-[10px] uppercase tracking-widest">
        Memo {num}
      </p>
      <p className="text-sm leading-relaxed">
        {section.eyebrow}
      </p>
    </aside>
  );
}

function Cta() {
  return (
    <section className="w-full border-t border-[var(--color-border)]
      bg-[var(--color-cream)] py-24 md:py-32">
      <div className="mx-auto max-w-[1200px] px-6">
        <div className="max-w-2xl">
          <h2 className="mb-5 font-serif text-3xl font-semibold leading-tight
            text-[var(--color-ink)] md:text-4xl">
            {investorCta.heading}
          </h2>
          <p className="mb-8 text-lg leading-relaxed text-[var(--color-muted)]">
            {investorCta.subtext}
          </p>
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" href={investorCta.contactHref}>
              {investorCta.contactLabel} →
            </Button>
            <Button variant="ghost" href="/">
              Public page
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
