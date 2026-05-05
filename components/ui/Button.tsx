import type { ReactNode } from 'react';

type Variant = 'primary' | 'ghost' | 'outline-light' | 'light';

type ButtonProps = {
  variant?: Variant;
  href?: string;
  onClick?: () => void;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
  title?: string;
};

const variantClasses: Record<Variant, string> = {
  primary:
    'bg-black text-[var(--color-cream)] hover:bg-[var(--color-ink)] border border-black',
  ghost:
    'bg-transparent text-[var(--color-ink)] border border-[var(--color-border)] hover:border-[var(--color-ink)] hover:bg-[var(--color-tag-bg)]',
  'outline-light':
    'bg-transparent text-[var(--color-cream)] border border-[rgba(245,243,239,0.3)] hover:border-[var(--color-cream)] hover:bg-[rgba(245,243,239,0.08)]',
  light:
    'bg-[var(--color-cream)] text-[var(--color-black)] border border-[var(--color-cream)] hover:bg-white',
};

export default function Button({
  variant = 'primary',
  href,
  onClick,
  children,
  className = '',
  disabled = false,
  title,
}: ButtonProps) {
  const base =
    'inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-full transition-all duration-150 cursor-pointer select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-current disabled:opacity-40 disabled:cursor-not-allowed';

  const classes = `${base} ${variantClasses[variant]} ${className}`;

  if (href) {
    return (
      <a href={href} className={classes} title={title}>
        {children}
      </a>
    );
  }

  return (
    <button onClick={onClick} className={classes} disabled={disabled} title={title}>
      {children}
    </button>
  );
}
