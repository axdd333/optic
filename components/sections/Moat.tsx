'use client';

import { motion } from 'framer-motion';
import SectionEyebrow from '@/components/ui/SectionEyebrow';
import { moatCards, boundaryPills } from '@/data/moat';

export default function Moat() {
  return (
    <section
      id="moat"
      className="w-full py-24 md:py-32"
      style={{ background: 'var(--color-section-dark)', scrollMarginTop: '80px' }}
    >
      <div className="mx-auto max-w-[1200px] px-6">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.4 }}
          className="mb-16 max-w-2xl"
        >
          <SectionEyebrow light className="mb-4">
            Trust moat
          </SectionEyebrow>
          <h2 className="text-3xl md:text-4xl font-serif font-semibold text-[var(--color-section-dark-text)] leading-tight mb-4">
            Private feedback. Not public judgment.
          </h2>
          <p className="text-[rgba(245,243,239,0.5)] leading-relaxed">
            The product only works if you trust it completely. That trust is architectural — not
            a policy.
          </p>
        </motion.div>

        {/* Cards */}
        <div className="grid md:grid-cols-3 gap-px bg-[rgba(245,243,239,0.06)] rounded-2xl overflow-hidden mb-12">
          {moatCards.map((card, i) => (
            <motion.div
              key={card.label}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-80px' }}
              transition={{ duration: 0.35, delay: i * 0.08 }}
              className="p-8 flex flex-col gap-4"
              style={{ background: 'var(--color-section-dark)' }}
            >
              <p className="font-mono text-[10px] tracking-widest uppercase text-[rgba(245,243,239,0.3)]">
                {card.label}
              </p>
              <h3 className="text-lg font-medium text-[var(--color-section-dark-text)]">
                {card.heading}
              </h3>
              <p className="text-sm text-[rgba(245,243,239,0.5)] leading-relaxed">{card.body}</p>
            </motion.div>
          ))}
        </div>

        {/* Boundary pills */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.35, delay: 0.2 }}
          className="flex flex-wrap gap-3"
          role="list"
          aria-label="Architectural boundaries"
        >
          {boundaryPills.map((pill) => (
            <span
              key={pill}
              role="listitem"
              className="px-4 py-2 rounded-full border border-[rgba(245,243,239,0.15)] text-sm text-[rgba(245,243,239,0.6)]"
            >
              {pill}
            </span>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
