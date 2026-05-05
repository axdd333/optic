'use client';

import { motion } from 'framer-motion';
import SectionEyebrow from '@/components/ui/SectionEyebrow';
import { wedgeCards } from '@/data/wedge';

export default function Wedge() {
  return (
    <section
      id="use-cases"
      className="w-full py-24 md:py-32"
      style={{ background: 'var(--color-cream)', scrollMarginTop: '80px' }}
    >
      <div className="mx-auto max-w-[1200px] px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.4 }}
          className="mb-12"
        >
          <SectionEyebrow className="mb-4">Who it&apos;s for</SectionEyebrow>
          <h2 className="text-3xl md:text-4xl font-serif font-semibold text-[var(--color-ink)] leading-tight max-w-lg">
            Start where being misread is expensive.
          </h2>
        </motion.div>

        <div className="grid sm:grid-cols-2 gap-px bg-[var(--color-border)] rounded-2xl overflow-hidden">
          {wedgeCards.map((card, i) => (
            <motion.div
              key={card.number}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-80px' }}
              transition={{ duration: 0.35, delay: i * 0.08 }}
              className="group bg-[var(--color-cream)] hover:bg-white transition-colors duration-200 p-8 flex flex-col gap-4 cursor-default"
            >
              <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)]">
                {card.number}
              </p>
              <h3 className="text-xl font-serif font-semibold text-[var(--color-ink)]">
                {card.title}
              </h3>
              <p className="text-sm text-[var(--color-muted)] leading-relaxed">
                {card.description}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
