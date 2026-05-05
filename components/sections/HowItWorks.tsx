'use client';

import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import SectionEyebrow from '@/components/ui/SectionEyebrow';
import { steps } from '@/data/steps';
import type { Step } from '@/data/types';

function StepIcon({ icon }: { icon: Step['icon'] }) {
  const icons: Record<Step['icon'], ReactNode> = {
    collect: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 3v4M12 17v4M3 12h4M17 12h4" />
      </svg>
    ),
    analyze: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3v18h18" />
        <path d="M7 16l4-4 4 4 4-6" />
      </svg>
    ),
    reveal: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    ),
    repair: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2L2 7l10 5 10-5-10-5z" />
        <path d="M2 17l10 5 10-5" />
        <path d="M2 12l10 5 10-5" />
      </svg>
    ),
    reaudit: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M1 4v6h6" />
        <path d="M3.51 15a9 9 0 1 0 .49-5.13" />
      </svg>
    ),
  };

  return <>{icons[icon]}</>;
}

export default function HowItWorks() {
  return (
    <section
      id="how-it-works"
      className="w-full py-24 md:py-32 bg-white"
      style={{ scrollMarginTop: '80px' }}
    >
      <div className="mx-auto max-w-[1200px] px-6">
        {/* Header */}
        <div className="grid md:grid-cols-2 gap-8 mb-16">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.4 }}
          >
            <SectionEyebrow className="mb-4">How it works</SectionEyebrow>
            <h2 className="text-3xl md:text-4xl font-serif font-semibold text-[var(--color-ink)] leading-tight">
              A mirror with receipts. Not another score.
            </h2>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="flex items-end"
          >
            <p className="text-[var(--color-muted)] leading-relaxed">
              You cannot erase every surface. You can understand the shape of the reading, where
              it came from, and what is still worth changing.
            </p>
          </motion.div>
        </div>

        {/* Steps grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-px bg-[var(--color-border)] rounded-2xl overflow-hidden">
          {steps.map((step, i) => (
            <motion.div
              key={step.number}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-80px' }}
              transition={{ duration: 0.35, delay: i * 0.07 }}
              className="bg-white p-6 flex flex-col gap-4"
            >
              <div className="text-[var(--color-muted)]">
                <StepIcon icon={step.icon} />
              </div>
              <div>
                <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)] mb-1.5">
                  {step.number}
                </p>
                <h3 className="text-base font-medium text-[var(--color-ink)] mb-2">
                  {step.title}
                </h3>
                <p className="text-sm text-[var(--color-muted)] leading-relaxed">
                  {step.description}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
