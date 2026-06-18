'use client';

/**
 * Onboarding — connect your data via Vana DataConnect, ingest it into the
 * Optic signal engine, and land on your signal profile.
 *
 * Hosted flow (tryoptic.app): the customer exports with the DataConnect
 * desktop app, then drags the export JSON files into this page. Files are
 * parsed client-side and uploaded in size-capped batches to
 * POST /api/vana/upload; the final batch triggers the audit.
 *
 * Desktop flow (backend on the same machine): exports are auto-detected
 * via GET /api/vana/status and ingested directly from disk — no upload.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import SignalProfile, { VanaProfile } from '@/components/vana/SignalProfile';

const DATACONNECT_RELEASES = 'https://github.com/vana-com/data-connect/releases';
const POLL_MS = 4000;
const BATCH_BYTES = 2_500_000; // stay under serverless request caps
const MAX_FILES = 400;

interface VanaStatus {
  available: boolean;
  total_files: number;
  platforms: { platform: string; files: number; latest_export: number }[];
}

interface UploadDoc {
  name: string;
  data: unknown;
  bytes: number;
}

type Step = 'intro' | 'connect' | 'ingest' | 'profile';

/** Split an oversized export into batchable documents (conversation slices). */
function explodeDoc(name: string, parsed: unknown, json: string): UploadDoc[] {
  if (json.length <= BATCH_BYTES) {
    return [{ name, data: parsed, bytes: json.length }];
  }
  const obj = parsed as {
    company?: string;
    name?: string;
    content?: { conversations?: unknown[] };
  };
  const convs =
    obj?.content?.conversations ??
    (parsed as { conversations?: unknown[] })?.conversations;
  if (!Array.isArray(convs) || convs.length < 2) {
    // Can't split — send as-is and let the server cap handle it
    return [{ name, data: parsed, bytes: json.length }];
  }
  const perSlice = Math.max(1, Math.ceil(convs.length / Math.ceil(json.length / BATCH_BYTES)));
  const docs: UploadDoc[] = [];
  for (let i = 0; i < convs.length; i += perSlice) {
    const slice = convs.slice(i, i + perSlice);
    const data = {
      company: obj?.company ?? '',
      name: obj?.name ?? name,
      content: { conversations: slice },
    };
    docs.push({ name: `${name}#${i}`, data, bytes: JSON.stringify(data).length });
  }
  return docs;
}

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>('intro');
  const [status, setStatus] = useState<VanaStatus | null>(null);
  const [profile, setProfile] = useState<VanaProfile | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/backend/api/vana/status');
      if (res.ok) setStatus(await res.json());
    } catch {
      /* hosted backend without local exports — expected */
    }
  }, []);

  useEffect(() => {
    if (step !== 'connect') return;
    fetchStatus();
    pollRef.current = setInterval(fetchStatus, POLL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [step, fetchStatus]);

  function finishOnboarding(p: VanaProfile) {
    setProfile(p);
    setStep('profile');
    fetch('/api/backend/api/v1/onboarding', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        step: 7,
        profile: { vana_connected: true, vana_sources: p.sources.map(s => s.platform) },
      }),
    }).catch(() => {});
  }

  /** Hosted mode: parse + batch + upload the dropped export files. */
  async function handleFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList)
      .filter(f => f.name.endsWith('.json'))
      .slice(0, MAX_FILES);
    if (files.length === 0) {
      setError('No .json export files found — drag the files DataConnect saved.');
      return;
    }
    setBusy(true);
    setError('');
    setStep('ingest');
    try {
      // Parse client-side; split oversized conversation exports
      setProgress(`Reading ${files.length} file${files.length === 1 ? '' : 's'}…`);
      const docs: UploadDoc[] = [];
      for (const f of files) {
        try {
          const text = await f.text();
          docs.push(...explodeDoc(f.name, JSON.parse(text), text));
        } catch {
          /* skip unparseable file */
        }
      }
      if (docs.length === 0) throw new Error('None of the files contained valid JSON.');

      // Batch under the request-size cap
      const batches: UploadDoc[][] = [];
      let current: UploadDoc[] = [];
      let size = 0;
      for (const doc of docs) {
        if (current.length > 0 && size + doc.bytes > BATCH_BYTES) {
          batches.push(current);
          current = [];
          size = 0;
        }
        current.push(doc);
        size += doc.bytes;
      }
      if (current.length > 0) batches.push(current);

      const session = crypto.randomUUID().replace(/-/g, '');
      for (let i = 0; i < batches.length; i++) {
        setProgress(`Uploading batch ${i + 1} of ${batches.length}…`);
        const res = await fetch('/api/backend/api/vana/upload', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            session,
            files: batches[i].map(d => ({ name: d.name, data: d.data })),
          }),
        });
        if (!res.ok) {
          const e = await res.json().catch(() => ({}));
          throw new Error((e as { err?: string; error?: string }).err ?? (e as { err?: string; error?: string }).error ?? `Upload failed (HTTP ${res.status})`);
        }
      }

      setProgress('Auditing your corpus…');
      const res = await fetch('/api/backend/api/vana/upload', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ session, final: true }),
      });
      if (!res.ok) {
        const e = (await res.json().catch(() => ({}))) as { err?: string; error?: string };
        const code = e.err ?? e.error;
        throw new Error(
          code === 'no_text_found'
            ? 'No auditable text found in those exports — try a ChatGPT or Claude export.'
            : code ?? `Audit failed (HTTP ${res.status})`,
        );
      }
      finishOnboarding(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Upload failed.');
      setStep('connect');
    } finally {
      setBusy(false);
      setProgress('');
    }
  }

  /** Desktop mode: backend reads the export store directly. */
  async function runLocalIngest() {
    setBusy(true);
    setError('');
    setStep('ingest');
    setProgress('Auditing exports from this machine…');
    try {
      const res = await fetch('/api/backend/api/vana/ingest', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error((e as { err?: string; error?: string }).err ?? (e as { err?: string; error?: string }).error ?? `HTTP ${res.status}`);
      }
      finishOnboarding(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ingestion failed.');
      setStep('connect');
    } finally {
      setBusy(false);
      setProgress('');
    }
  }

  return (
    <main className="min-h-screen px-6 py-16 max-w-2xl mx-auto">
      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-12">
        {(['intro', 'connect', 'ingest', 'profile'] as Step[]).map((s, i) => (
          <div
            key={s}
            className={`h-1 flex-1 rounded-full transition-colors ${
              (['intro', 'connect', 'ingest', 'profile'] as Step[]).indexOf(step) >= i
                ? 'bg-black'
                : 'bg-[var(--color-border)]'
            }`}
          />
        ))}
      </div>

      {step === 'intro' && (
        <section>
          <h1 className="font-editorial text-3xl text-[var(--color-ink)] mb-3">
            Bring your real signal footprint
          </h1>
          <p className="text-sm text-[var(--color-muted)] leading-relaxed mb-6">
            Optic audits language for loaded framing, absolutes, and implied
            confidence. It works best on the words you actually produce — your
            ChatGPT conversations, posts, bios, and notes — not pasted samples.
          </p>
          <p className="text-sm text-[var(--color-muted)] leading-relaxed mb-8">
            Export that data with{' '}
            <span className="text-[var(--color-ink)]">Vana DataConnect</span>, an
            open-source desktop app, then drop the files here. Your data is
            processed for your profile and nothing else.
          </p>
          <div className="flex items-center gap-4">
            <button
              onClick={() => setStep('connect')}
              className="px-5 py-2 text-sm font-medium rounded-full bg-black text-[var(--color-cream)] border border-black hover:bg-[var(--color-ink)] transition-colors"
            >
              Connect my data →
            </button>
            <button
              onClick={() => router.push('/app')}
              className="text-xs text-[var(--color-muted)] hover:text-[var(--color-ink)] transition-colors"
            >
              Skip for now
            </button>
          </div>
        </section>
      )}

      {step === 'connect' && (
        <section>
          <h1 className="font-editorial text-3xl text-[var(--color-ink)] mb-3">
            Connect your data
          </h1>
          <ol className="text-sm text-[var(--color-muted)] leading-relaxed space-y-2 mb-8 list-decimal list-inside">
            <li>
              <a
                href={DATACONNECT_RELEASES}
                target="_blank"
                rel="noreferrer"
                className="underline text-[var(--color-ink)]"
              >
                Download DataConnect
              </a>{' '}
              and run the connectors you want — ChatGPT, Claude, LinkedIn,
              Instagram, GitHub, and more.
            </li>
            <li>
              In DataConnect, open an export&apos;s folder (<span className="text-[var(--color-ink)]">⋯ → Open folder</span>).
            </li>
            <li>Drag the JSON files below.</li>
          </ol>

          {/* Dropzone (hosted mode, primary) */}
          <div
            onDragOver={e => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => {
              e.preventDefault();
              setDragOver(false);
              if (!busy) handleFiles(e.dataTransfer.files);
            }}
            onClick={() => !busy && fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl px-6 py-12 text-center cursor-pointer transition-colors mb-4 ${
              dragOver
                ? 'border-[var(--color-ink)] bg-[var(--color-cream)]'
                : 'border-[var(--color-border)] bg-white hover:border-[var(--color-ink)]'
            }`}
          >
            <p className="text-sm text-[var(--color-ink)] mb-1">
              Drop your DataConnect export files here
            </p>
            <p className="text-xs text-[var(--color-muted)]">
              or click to choose .json files — parsed in your browser, audited on upload
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json,application/json"
              multiple
              className="hidden"
              onChange={e => {
                if (e.target.files?.length) handleFiles(e.target.files);
                e.target.value = '';
              }}
            />
          </div>

          {/* Desktop mode: local exports detected */}
          {status?.available && (
            <div className="border border-[var(--color-border)] rounded-lg px-4 py-4 bg-[var(--color-cream)] mb-4">
              <p className="text-sm text-[var(--color-ink)] mb-2">
                Exports detected on this machine ({status.total_files} file
                {status.total_files === 1 ? '' : 's'}):
              </p>
              <div className="flex flex-wrap gap-2 mb-3">
                {status.platforms.map(p => (
                  <span
                    key={p.platform}
                    className="text-xs border border-[var(--color-border)] rounded-full px-3 py-1 bg-white text-[var(--color-ink)] capitalize"
                  >
                    {p.platform.replace(/_/g, ' ')} · {p.files}
                  </span>
                ))}
              </div>
              <button
                onClick={runLocalIngest}
                disabled={busy}
                className="px-4 py-1.5 text-xs font-medium rounded-full bg-black text-[var(--color-cream)] border border-black hover:bg-[var(--color-ink)] transition-colors disabled:opacity-40"
              >
                Audit directly — no upload needed →
              </button>
            </div>
          )}

          {error && (
            <p className="mb-6 text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-4 py-3">
              {error}
            </p>
          )}

          <button
            onClick={() => router.push('/app')}
            className="text-xs text-[var(--color-muted)] hover:text-[var(--color-ink)] transition-colors"
          >
            Skip for now
          </button>
        </section>
      )}

      {step === 'ingest' && (
        <section className="text-center py-24">
          <div className="inline-block w-8 h-8 border-2 border-[var(--color-border)] border-t-black rounded-full animate-spin mb-6" />
          <h1 className="font-editorial text-2xl text-[var(--color-ink)] mb-2">
            Building your signal profile
          </h1>
          <p className="text-sm text-[var(--color-muted)]">
            {progress || 'Normalizing exports, running signal detection…'}
          </p>
        </section>
      )}

      {step === 'profile' && profile && (
        <section>
          <h1 className="font-editorial text-3xl text-[var(--color-ink)] mb-3">
            Your signal profile
          </h1>
          <p className="text-sm text-[var(--color-muted)] mb-10">
            Built from {profile.corpus.audited_items.toLocaleString()} items
            across {profile.sources.length} source
            {profile.sources.length === 1 ? '' : 's'}.
          </p>
          <SignalProfile profile={profile} />
          <div className="mt-12 flex items-center gap-4">
            <button
              onClick={() => router.push('/app')}
              className="px-5 py-2 text-sm font-medium rounded-full bg-black text-[var(--color-cream)] border border-black hover:bg-[var(--color-ink)] transition-colors"
            >
              Enter Optic →
            </button>
            <Link
              href="/app/profile"
              className="text-xs text-[var(--color-muted)] underline hover:text-[var(--color-ink)]"
            >
              Revisit this any time at /app/profile
            </Link>
          </div>
        </section>
      )}
    </main>
  );
}
