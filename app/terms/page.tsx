import type { Metadata } from 'next';
import LegalPage from '@/components/legal/LegalPage';
import { termsDoc } from '@/data/legal';

export const metadata: Metadata = {
  title: 'Terms of Service - Optic',
  description: termsDoc.summary,
};

export default function TermsPage() {
  return <LegalPage doc={termsDoc} />;
}
