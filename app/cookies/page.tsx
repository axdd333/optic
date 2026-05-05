import type { Metadata } from 'next';
import LegalPage from '@/components/legal/LegalPage';
import { cookiesDoc } from '@/data/legal';

export const metadata: Metadata = {
  title: 'Cookie Policy - Optic',
  description: cookiesDoc.summary,
};

export default function CookiesPage() {
  return <LegalPage doc={cookiesDoc} />;
}
