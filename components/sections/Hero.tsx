'use client';

import { motion } from 'framer-motion';
import Button from '@/components/ui/Button';
import AuditCard from '@/components/ui/AuditCard';

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 },
};

const stagger = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.1 } },
};

const trustPills = ['Private. Local-first.', 'No public score.', 'Subject-owned.'];

export default function Hero() {
  const auditUrl = process.env.NEXT_PUBLIC_AUDIT_FORM_URL
    ?? 'https://app.tryoptic.app';

  return (
    <section
      id="top"
      className="relative w-full pt-20 pb-24 md:pt-28 md:pb-32 overflow-hidden"
      style={{ scrollMarginTop: '80px' }}
    >
      <div className="mx-auto max-w-[1200px] px-6">
        <div className="grid md:grid-cols-2 gap-12 md:gap-16 items-center">
          {/* Left: content */}
          <motion.div
            variants={stagger}
            initial="hidden"
            animate="visible"
            className="flex flex-col gap-6"
          >
            {/* Eyebrow badge */}
            <motion.div variants={fadeUp}>
              <span className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-tag-bg)] text-xs font-mono tracking-widest uppercase text-[var(--color-muted)]">
                Private · Local-first · Subject-owned
              </span>
            </motion.div>

            {/* H1 */}
            <motion.h1
              variants={fadeUp}
              className="text-4xl md:text-5xl lg:text-6xl font-serif font-semibold text-[var(--color-ink)] leading-[1.1] tracking-tight"
            >
              Know how the internet{' '}
              <em className="not-italic text-[var(--color-muted)]">sees you.</em>
            </motion.h1>

            {/* Subheading */}
            <motion.p
              variants={fadeUp}
              className="text-lg text-[var(--color-muted)] leading-relaxed max-w-[480px]"
            >
              Optic shows what your public traces may imply — before a recruiter, investor, or
              partner turns them into a story you never agreed to.
            </motion.p>

            {/* CTAs */}
            <motion.div variants={fadeUp} className="flex flex-wrap items-center gap-3">
              <Button
                variant="primary"
                href={auditUrl ?? undefined}
                disabled={!auditUrl}
                title={!auditUrl ? 'Coming soon' : undefined}
              >
                Get your audit →
              </Button>
              <Button variant="ghost" href="#how-it-works">
                See how it works
              </Button>
            </motion.div>

            {/* Trust pills */}
            <motion.ul
              variants={fadeUp}
              className="flex flex-wrap gap-2"
              aria-label="Trust notes"
            >
              {trustPills.map((pill) => (
                <li
                  key={pill}
                  className="px-3 py-1 rounded-full border border-[var(--color-border)] text-xs text-[var(--color-muted)] bg-white"
                >
                  {pill}
                </li>
              ))}
            </motion.ul>
          </motion.div>

          {/* Right: audit card */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.3, ease: [0.4, 0, 0.2, 1] }}
            className="relative"
          >
            <div className="relative z-10">
              <AuditCard />
            </div>
            {/* Decorative background blob */}
            <div
              className="absolute -inset-8 -z-10 rounded-3xl opacity-50"
              style={{
                background:
                  'radial-gradient(ellipse at 60% 40%, rgba(226,223,216,0.6) 0%, transparent 70%)',
              }}
              aria-hidden="true"
            />
          </motion.div>
        </div>
      </div>
    </section>
  );
}
