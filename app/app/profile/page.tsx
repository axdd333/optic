'use client';

/**
 * /app/profile — persistent signal profile dashboard.
 * Reads the profile produced during onboarding (GET /api/vana/profile)
 * and allows re-ingesting fresh DataConnect exports.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import SignalProfile, { VanaProfile } from '@/components/vana/SignalProfile';

export default function ProfilePage() {
  const [profile, setProfile] = useState<VanaProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/backend/api/vana/profile');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const p = await res.json();
      setProfile(p?.exists ? p : null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load profile.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function reingest() {
    setRefreshing(true);
    setError('');
    try {
      const res = await fetch('/api/backend/api/vana/ingest', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const e = (await res.json().catch(() => ({}))) as { err?: string; error?: string };
        const code = e.err ?? e.error;
        throw new Error(
          code === 'no_exports_found'
            ? 'No exports on this machine — upload fresh files via onboarding.'
            : code ?? `HTTP ${res.status}`,
        );
      }
      setProfile(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Re-ingestion failed.');
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <main className="min-h-screen px-6 py-16 max-w-2xl mx-auto">
      <div className="mb-12 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-editorial text-3xl text-[var(--color-ink)] mb-2">
            Signal profile
          </h1>
          <p className="text-sm text-[var(--color-muted)]">
            Your audited footprint from Vana DataConnect exports — processed locally.
          </p>
        </div>
        {profile && (
          <div className="shrink-0 flex items-center gap-2">
            <Link
              href="/onboarding"
              className="px-4 py-2 text-xs font-medium rounded-full border border-[var(--color-border)] text-[var(--color-ink)] hover:border-[var(--color-ink)] transition-colors"
            >
              Upload new exports
            </Link>
            <button
              onClick={reingest}
              disabled={refreshing}
              className="px-4 py-2 text-xs font-medium rounded-full border border-[var(--color-border)] text-[var(--color-ink)] hover:border-[var(--color-ink)] transition-colors disabled:opacity-40"
              title="Desktop mode: re-scan exports on this machine"
            >
              {refreshing ? 'Re-auditing…' : 'Re-scan this machine'}
            </button>
          </div>
        )}
      </div>

      {error && (
        <p className="mb-6 text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-4 py-3">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-sm text-[var(--color-muted)]">Loading…</p>
      ) : profile ? (
        <>
          <SignalProfile profile={profile} />
          <p className="mt-10 text-[11px] text-[var(--color-muted)]">
            Generated {new Date(profile.generated_at * 1000).toLocaleString()} ·{' '}
            <Link href="/app" className="underline hover:text-[var(--color-ink)]">
              back to audit
            </Link>
          </p>
        </>
      ) : (
        <div className="border border-[var(--color-border)] rounded-lg px-6 py-10 bg-white text-center">
          <p className="text-sm text-[var(--color-ink)] mb-2">No signal profile yet.</p>
          <p className="text-xs text-[var(--color-muted)] mb-6">
            Connect your data through DataConnect to build one.
          </p>
          <Link
            href="/onboarding"
            className="inline-block px-5 py-2 text-sm font-medium rounded-full bg-black text-[var(--color-cream)] border border-black hover:bg-[var(--color-ink)] transition-colors"
          >
            Connect my data →
          </Link>
        </div>
      )}
    </main>
  );
}
