import Link from 'next/link';
import BrandMark from '@/components/ui/BrandMark';

const footerLinks = [
  {
    heading: 'Product',
    links: [
      { label: 'How it works', href: '/#how-it-works' },
      { label: 'Audit output', href: '/#audit-output' },
      { label: 'Use cases', href: '/#use-cases' },
      { label: 'Privacy', href: '/#moat' },
    ],
  },
  {
    heading: 'Company',
    links: [
      { label: 'Investors', href: '/investors' },
      { label: 'FAQ', href: '/#faq' },
    ],
  },
  {
    heading: 'Legal',
    links: [
      { label: 'Privacy Policy', href: '/privacy' },
      { label: 'Terms', href: '/terms' },
      { label: 'Cookies', href: '/cookies' },
    ],
  },
];

export default function Footer() {
  return (
    <footer
      className="w-full border-t border-[var(--color-border)] py-16"
      style={{ background: 'var(--color-cream)' }}
    >
      <div className="mx-auto max-w-[1200px] px-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-10 mb-12">
          {/* Brand */}
          <div className="col-span-2 md:col-span-1">
            <Link
              href="/"
              className="inline-flex items-center gap-3 mb-4"
              aria-label="Optic home"
            >
              <BrandMark className="h-8 w-8 text-[var(--color-ink)]" />
              <span className="font-medium text-xl text-[var(--color-ink)]">
                Optic
              </span>
            </Link>
            <p className="text-sm text-[var(--color-muted)] leading-relaxed max-w-[200px]">
              A private mirror for reputation in an AI-gated world.
            </p>
          </div>

          {/* Link columns */}
          {footerLinks.map((col) => (
            <div key={col.heading}>
              <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)] mb-4">
                {col.heading}
              </p>
              <ul className="flex flex-col gap-3">
                {col.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-sm text-[var(--color-muted)] hover:text-[var(--color-ink)] transition-colors"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pt-8 border-t border-[var(--color-border)]">
          <p className="text-xs text-[var(--color-muted)]">
            © {new Date().getFullYear()} Optic. All rights reserved.
          </p>
          <p className="text-xs text-[var(--color-muted)]">Private. Local-first. Subject-owned.</p>
        </div>
      </div>
    </footer>
  );
}
