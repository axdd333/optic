import type { Metadata } from 'next';
import LegalPage from '@/components/legal/LegalPage';
import { privacyDoc } from '@/data/legal';

export const metadata: Metadata = {
  title: 'Privacy Policy - Optic',
  description: privacyDoc.summary,
};

export default function PrivacyPage() {
  return <LegalPage doc={privacyDoc} />;
}
