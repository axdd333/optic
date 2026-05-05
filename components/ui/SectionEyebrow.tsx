import type { ReactNode } from 'react';

type SectionEyebrowProps = {
  children: ReactNode;
  light?: boolean;
  className?: string;
};

export default function SectionEyebrow({ children, light = false, className = '' }: SectionEyebrowProps) {
  return (
    <p
      className={`font-mono text-xs tracking-widest uppercase ${
        light ? 'text-[rgba(245,243,239,0.5)]' : 'text-[var(--color-muted)]'
      } ${className}`}
    >
      {children}
    </p>
  );
}
