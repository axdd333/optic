'use client';

import { motion } from 'framer-motion';
import SectionEyebrow from '@/components/ui/SectionEyebrow';
import { featureRows } from '@/data/features';

/* ---- Visual panels ---- */

function SignalsPanel() {
  const sources = [
    { label: 'Social profiles', pct: 88 },
    { label: 'News & media', pct: 62 },
    { label: 'Public records', pct: 45 },
    { label: 'Job history', pct: 79 },
  ];

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-white p-6 flex flex-col gap-4 shadow-[0_2px_16px_rgba(14,14,12,0.04)]">
      <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)]">
        Signal coverage
      </p>
      <ul className="flex flex-col gap-3">
        {sources.map((s) => (
          <li key={s.label} className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[var(--color-ink)]">{s.label}</span>
              <span className="font-mono text-xs text-[var(--color-muted)]">{s.pct}%</span>
            </div>
            <div className="h-1 w-full rounded-full bg-[var(--color-border)]">
              <div
                className="h-full rounded-full bg-[var(--color-ink)]"
                style={{ width: `${s.pct}%`, transition: 'width 0.6s ease' }}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

type ImplicationSeverity = 'neutral' | 'warning' | 'positive';

function ImplicationPanel() {
  const cards: { label: string; text: string; severity: ImplicationSeverity }[] = [
    {
      label: 'Neutral',
      text: 'Track record is visible. Narrative is unclear.',
      severity: 'neutral',
    },
    {
      label: 'Warning',
      text: 'Two-year gap reads as unresolved. No counter-signal.',
      severity: 'warning',
    },
    {
      label: 'Positive',
      text: 'Consistent output pattern. Credible proof of work.',
      severity: 'positive',
    },
  ];

  const severityColors: Record<ImplicationSeverity, string> = {
    neutral: 'border-[var(--color-border)] bg-white',
    warning: 'border-amber-200 bg-amber-50',
    positive: 'border-emerald-200 bg-emerald-50',
  };

  const dotColors: Record<ImplicationSeverity, string> = {
    neutral: 'bg-slate-400',
    warning: 'bg-amber-400',
    positive: 'bg-emerald-500',
  };

  return (
    <div className="flex flex-col gap-3">
      {cards.map((card) => (
        <div
          key={card.label}
          className={`rounded-xl border p-4 flex items-start gap-3 ${severityColors[card.severity]}`}
        >
          <span className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${dotColors[card.severity]}`} />
          <div>
            <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)] mb-1">
              {card.label}
            </p>
            <p className="text-sm text-[var(--color-ink)]">{card.text}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function RepairPanel() {
  const items = [
    { rank: '01', label: 'Update LinkedIn headline', impact: 'High', effort: 'Low', active: true },
    { rank: '02', label: 'Add context to 2021 gap', impact: 'High', effort: 'Med', active: true },
    { rank: '03', label: 'Claim Google Knowledge Panel', impact: 'Med', effort: 'Low', active: true },
    { rank: '04', label: 'Request outdated article removal', impact: 'Med', effort: 'High', active: false },
  ];

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-white overflow-hidden shadow-[0_2px_16px_rgba(14,14,12,0.04)]">
      <div className="px-5 py-4 border-b border-[var(--color-border)]">
        <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)]">
          Repair actions
        </p>
      </div>
      <ul className="divide-y divide-[var(--color-border)]">
        {items.map((item) => (
          <li
            key={item.rank}
            className={`flex items-center justify-between gap-4 px-5 py-3.5 ${!item.active ? 'opacity-40' : ''}`}
          >
            <div className="flex items-center gap-3 min-w-0">
              <span className="font-mono text-[10px] text-[var(--color-muted)] flex-shrink-0">
                {item.rank}
              </span>
              <span className="text-sm text-[var(--color-ink)] truncate">{item.label}</span>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span className="font-mono text-[10px] text-[var(--color-muted)]">{item.impact}</span>
              <span className="text-[var(--color-border)]">·</span>
              <span className="font-mono text-[10px] text-[var(--color-muted)]">{item.effort}</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

const visualPanels = {
  signals: <SignalsPanel />,
  implication: <ImplicationPanel />,
  repair: <RepairPanel />,
};

export default function Features() {
  return (
    <section
      id="audit-output"
      className="w-full py-24 md:py-32 bg-white"
      style={{ scrollMarginTop: '80px' }}
    >
      <div className="mx-auto max-w-[1200px] px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.4 }}
          className="mb-20"
        >
          <SectionEyebrow className="mb-4">The audit</SectionEyebrow>
          <h2 className="text-3xl md:text-4xl font-serif font-semibold text-[var(--color-ink)] leading-tight max-w-xl">
            What the report actually shows you.
          </h2>
        </motion.div>

        <div className="flex flex-col gap-24">
          {featureRows.map((row, i) => (
            <motion.div
              key={row.number}
              initial={{ opacity: 0, x: row.reversed ? -32 : 32 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: '-80px' }}
              transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
              className={`grid md:grid-cols-2 gap-12 md:gap-16 items-center ${row.reversed ? 'md:[&>*:first-child]:order-2' : ''}`}
            >
              {/* Content */}
              <div className="flex flex-col gap-5">
                <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)]">
                  {row.number}
                </p>
                <h3 className="text-2xl md:text-3xl font-serif font-semibold text-[var(--color-ink)] leading-tight">
                  {row.heading}
                </h3>
                <p className="text-[var(--color-muted)] leading-relaxed">{row.body}</p>
              </div>

              {/* Visual */}
              <div>{visualPanels[row.visualType]}</div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
