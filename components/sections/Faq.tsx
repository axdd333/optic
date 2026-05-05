'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import SectionEyebrow from '@/components/ui/SectionEyebrow';
import FaqItem from '@/components/ui/FaqItem';
import { faqItems } from '@/data/faq';

export default function Faq() {
  const [openId, setOpenId] = useState<string>('q1');

  return (
    <section
      id="faq"
      className="w-full py-24 md:py-32"
      style={{ background: 'var(--color-cream)', scrollMarginTop: '80px' }}
    >
      <div className="mx-auto max-w-[1200px] px-6">
        <div className="grid md:grid-cols-[1fr_2fr] gap-12 md:gap-16 items-start">
          {/* Left header */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.4 }}
            className="md:sticky md:top-24"
          >
            <SectionEyebrow className="mb-4">Questions</SectionEyebrow>
            <h2 className="text-3xl md:text-4xl font-serif font-semibold text-[var(--color-ink)] leading-tight">
              What people ask before they trust us with this.
            </h2>
          </motion.div>

          {/* FAQ list */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.4, delay: 0.1 }}
          >
            {faqItems.map((item) => (
              <FaqItem
                key={item.id}
                question={item.question}
                answer={item.answer}
                isOpen={openId === item.id}
                onToggle={() => setOpenId(openId === item.id ? '' : item.id)}
              />
            ))}
          </motion.div>
        </div>
      </div>
    </section>
  );
}
