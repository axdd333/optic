'use client';

import { motion } from 'framer-motion';
import SectionEyebrow from '@/components/ui/SectionEyebrow';
import { timelineItems, businessModelRows } from '@/data/timeline';

export default function Expansion() {
  return (
    <section
      id="expansion"
      className="w-full py-24 md:py-32 bg-white"
      style={{ scrollMarginTop: '80px' }}
    >
      <div className="mx-auto max-w-[1200px] px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.4 }}
          className="mb-16"
        >
          <SectionEyebrow className="mb-4">The long arc</SectionEyebrow>
          <h2 className="text-3xl md:text-4xl font-serif font-semibold text-[var(--color-ink)] leading-tight max-w-xl">
            Built to expand with trust.
          </h2>
        </motion.div>

        <div className="grid md:grid-cols-2 gap-16">
          {/* Timeline */}
          <div className="relative">
            {/* Vertical line */}
            <div
              className="absolute left-[9px] top-3 bottom-3 w-px"
              style={{ background: 'var(--color-border)' }}
              aria-hidden="true"
            />

            <ul className="flex flex-col gap-10 relative">
              {timelineItems.map((item, i) => (
                <motion.li
                  key={item.phase}
                  initial={{ opacity: 0, x: -16 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true, margin: '-80px' }}
                  transition={{ duration: 0.35, delay: i * 0.1 }}
                  className="pl-8 relative"
                >
                  {/* Dot */}
                  <span
                    className={`absolute left-0 top-1.5 w-[18px] h-[18px] rounded-full border-2 ${
                      item.active
                        ? 'bg-[var(--color-ink)] border-[var(--color-ink)]'
                        : 'bg-white border-[var(--color-border)]'
                    }`}
                    aria-hidden="true"
                  />

                  <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)] mb-1.5">
                    {item.phase}
                  </p>
                  <h3 className="text-base font-medium text-[var(--color-ink)] mb-1.5">
                    {item.heading}
                  </h3>
                  <p className="text-sm text-[var(--color-muted)] leading-relaxed">{item.body}</p>
                </motion.li>
              ))}
            </ul>
          </div>

          {/* Business model card */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.4, delay: 0.15 }}
            className="rounded-2xl border border-[var(--color-border)] overflow-hidden self-start"
          >
            <div className="px-6 py-5 border-b border-[var(--color-border)]">
              <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)]">
                Business model
              </p>
            </div>
            <ul className="divide-y divide-[var(--color-border)]">
              {businessModelRows.map((row) => (
                <li key={row.phase} className="px-6 py-5">
                  <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)] mb-2">
                    {row.phase}
                  </p>
                  <h3 className="text-base font-medium text-[var(--color-ink)] mb-1.5">
                    {row.heading}
                  </h3>
                  <p className="text-sm text-[var(--color-muted)] leading-relaxed">{row.body}</p>
                </li>
              ))}
            </ul>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
