'use client';

import { AnimatePresence, motion } from 'framer-motion';

type FaqItemProps = {
  question: string;
  answer: string;
  isOpen: boolean;
  onToggle: () => void;
};

export default function FaqItem({ question, answer, isOpen, onToggle }: FaqItemProps) {
  return (
    <div className="border-b border-[var(--color-border)]">
      <button
        onClick={onToggle}
        className="w-full flex items-start justify-between gap-6 py-5 text-left group"
        aria-expanded={isOpen}
      >
        <span className="text-base font-medium text-[var(--color-ink)] group-hover:text-[var(--color-black)] transition-colors">
          {question}
        </span>
        <span
          className="flex-shrink-0 w-6 h-6 flex items-center justify-center text-[var(--color-muted)] mt-0.5 transition-transform duration-200"
          aria-hidden="true"
          style={{ transform: isOpen ? 'rotate(45deg)' : 'rotate(0deg)' }}
        >
          +
        </span>
      </button>

      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            key="answer"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
            style={{ overflow: 'hidden' }}
          >
            <p className="pb-5 text-[var(--color-muted)] leading-relaxed text-sm">{answer}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
