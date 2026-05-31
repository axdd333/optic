'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || 'Something went wrong.');
      } else {
        router.push('/app');
      }
    } catch {
      setError('Could not reach the server. Try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-6 py-24">
      <div className="w-full max-w-sm">

        <div className="mb-10 text-center">
          <Link href="/" className="inline-block mb-6">
            <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="14" cy="14" r="13" stroke="currentColor" strokeWidth="1.5" />
              <circle cx="14" cy="14" r="5" fill="currentColor" />
            </svg>
          </Link>
          <h1 className="font-editorial text-2xl text-[var(--color-ink)] mb-2">Sign in to Optic</h1>
          <p className="text-sm text-[var(--color-muted)]">Private. Local-first. Subject-owned.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-xs font-medium text-[var(--color-muted)] mb-1.5 uppercase tracking-wide">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full px-4 py-2.5 text-sm rounded-lg border border-[var(--color-border)] bg-white text-[var(--color-ink)] placeholder:text-[var(--color-muted)] focus:outline-none focus:border-[var(--color-ink)] transition-colors"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-xs font-medium text-[var(--color-muted)] mb-1.5 uppercase tracking-wide">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••••••"
              className="w-full px-4 py-2.5 text-sm rounded-lg border border-[var(--color-border)] bg-white text-[var(--color-ink)] placeholder:text-[var(--color-muted)] focus:outline-none focus:border-[var(--color-ink)] transition-colors"
            />
          </div>

          {error && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-4 py-2.5">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full px-5 py-2.5 text-sm font-medium rounded-full bg-black text-[var(--color-cream)] border border-black hover:bg-[var(--color-ink)] transition-colors duration-150 mt-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Signing in…' : 'Sign in →'}
          </button>
        </form>

        <div className="mt-8 pt-6 border-t border-[var(--color-border)] text-center">
          <p className="text-xs text-[var(--color-muted)]">
            No account?{' '}
            <Link href="/signup" className="text-[var(--color-ink)] underline underline-offset-2 hover:opacity-70 transition-opacity">
              Create one
            </Link>
          </p>
        </div>

      </div>
    </main>
  );
}
