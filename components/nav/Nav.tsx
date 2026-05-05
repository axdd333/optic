'use client';

import Link from 'next/link';
import { useState, useEffect } from 'react';
import Button from '@/components/ui/Button';
import BrandMark from '@/components/ui/BrandMark';

const navLinks = [
  { label: 'How it works', href: '/#how-it-works' },
  { label: 'Audit output', href: '/#audit-output' },
  { label: 'Use cases', href: '/#use-cases' },
  { label: 'Privacy', href: '/#moat' },
  { label: 'FAQ', href: '/#faq' },
  { label: 'Investors', href: '/investors' },
];

export default function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const auditUrl = process.env.NEXT_PUBLIC_AUDIT_FORM_URL
    ?? 'https://app.tryoptic.app';

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 10);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header
      className="sticky top-0 z-[100] w-full"
      style={{
        background: 'rgba(245,243,239,0.92)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        borderBottom: scrolled ? '1px solid var(--color-border)' : '1px solid transparent',
        transition: 'border-color 200ms ease',
      }}
    >
      <div className="mx-auto max-w-[1200px] px-6 h-16 flex items-center justify-between gap-6">
        <Link
          href="/"
          className="flex items-center gap-3 flex-shrink-0"
          aria-label="Optic home"
        >
          <BrandMark className="h-9 w-9 text-[var(--color-ink)]" />
          <span
            className="font-medium text-2xl leading-none
              text-[var(--color-ink)] tracking-tight"
          >
            Optic
          </span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-6" aria-label="Main navigation">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-sm text-[var(--color-muted)] hover:text-[var(--color-ink)] transition-colors"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        {/* Desktop CTAs */}
        <div className="hidden md:flex items-center gap-3 flex-shrink-0">
          <Button variant="ghost" href="/investors">
            Read the thesis
          </Button>
          <Button
            variant="primary"
            href={auditUrl ?? undefined}
            disabled={!auditUrl}
            title={!auditUrl ? 'Coming soon' : undefined}
          >
            Get your audit →
          </Button>
        </div>

        {/* Mobile hamburger */}
        <button
          className="md:hidden flex flex-col gap-1.5 p-2 -mr-2"
          onClick={() => setMenuOpen((prev) => !prev)}
          aria-expanded={menuOpen}
          aria-label="Toggle navigation menu"
        >
          <span
            className="block w-5 h-px bg-[var(--color-ink)] transition-transform duration-200"
            style={{ transform: menuOpen ? 'translateY(4px) rotate(45deg)' : 'none' }}
          />
          <span
            className="block w-5 h-px bg-[var(--color-ink)] transition-opacity duration-200"
            style={{ opacity: menuOpen ? 0 : 1 }}
          />
          <span
            className="block w-5 h-px bg-[var(--color-ink)] transition-transform duration-200"
            style={{ transform: menuOpen ? 'translateY(-4px) rotate(-45deg)' : 'none' }}
          />
        </button>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="md:hidden border-t border-[var(--color-border)] bg-[rgba(245,243,239,0.98)]">
          <nav className="flex flex-col px-6 py-4 gap-4">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="text-base text-[var(--color-ink)] py-1"
                onClick={() => setMenuOpen(false)}
              >
                {link.label}
              </Link>
            ))}
            <div className="flex flex-col gap-3 pt-4 border-t border-[var(--color-border)]">
              <Button variant="ghost" href="/investors">
                Read the thesis
              </Button>
              <Button
                variant="primary"
                href={auditUrl ?? undefined}
                disabled={!auditUrl}
                title={!auditUrl ? 'Coming soon' : undefined}
              >
                Get your audit →
              </Button>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
