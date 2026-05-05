import type { ReactNode } from 'react';
import type { Metadata } from 'next';
import { editorialFont, sansFont } from '@/lib/fonts';
import Nav from '@/components/nav/Nav';
import Footer from '@/components/Footer';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL('https://tryoptic.app'),
  title: 'Optic — Know how the internet sees you',
  description:
    'A private, local-first mirror for reputation in an AI-gated world. Optic shows what your public traces may imply before someone else acts on them.',
  openGraph: {
    title: 'Optic — Know how the internet sees you',
    description: 'A private, local-first mirror for reputation in an AI-gated world.',
    images: [{ url: '/optic-og.png', width: 1200, height: 630 }],
  },
  twitter: {
    card: 'summary_large_image',
    images: ['/optic-og.png'],
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${editorialFont.variable} ${sansFont.variable}`}>
      <head>
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
      </head>
      <body className="antialiased">
        <Nav />
        {children}
        <Footer />
      </body>
    </html>
  );
}
