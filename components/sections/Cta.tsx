'use client';

import { motion } from 'framer-motion';
import SectionEyebrow from '@/components/ui/SectionEyebrow';
import Button from '@/components/ui/Button';

export default function Cta() {
  const auditUrl = process.env.NEXT_PUBLIC_AUDIT_FORM_URL
    ?? 'https://app.tryoptic.app';

  return (
    <section
      id="cta"
      className="w-full py-24 md:py-32"
      style={{ background: 'var(--color-section-dark)', scrollMarginTop: '80px' }}
    >
      <div className="mx-auto max-w-[1200px] px-6">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.45 }}
          className="max-w-2xl mx-auto text-center flex flex-col items-center gap-6"
        >
          <SectionEyebrow light>Get started</SectionEyebrow>

          <h2 className="text-3xl md:text-5xl font-serif font-semibold text-[var(--color-section-dark-text)] leading-tight">
            You should get to see the inference first.
          </h2>

          <p className="text-[rgba(245,243,239,0.5)] leading-relaxed max-w-md">
            The reading is already happening. Optic shows you what it says before it affects
            anything that matters.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-3">
            <Button
              variant="light"
              href={auditUrl ?? undefined}
              disabled={!auditUrl}
              title={!auditUrl ? 'Coming soon' : undefined}
            >
              Get your audit →
            </Button>
            <Button variant="outline-light" href="/investors">
              Read the investor brief
            </Button>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
