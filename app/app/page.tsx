'use client';

import { useState } from 'react';

interface Detection {
  attribute: string;
  severity: string;
  confidence: number;
  location?: string;
  description: string;
}

interface AuditResult {
  id: string;
  source: string;
  content_summary: string;
  created_at: string;
  detection_count: number;
  max_severity: string;
  detections: Detection[];
}

const SEVERITY_COLOR: Record<string, string> = {
  high: 'text-red-600 border-red-200 bg-red-50',
  medium: 'text-amber-600 border-amber-200 bg-amber-50',
  low: 'text-blue-600 border-blue-200 bg-blue-50',
};

export default function AppPage() {
  const [content, setContent] = useState('');
  const [includeML, setIncludeML] = useState(false);
  const [result, setResult] = useState<AuditResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function runAudit() {
    if (!content.trim()) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await fetch('/api/backend/api/audit', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ content, include_ml: includeML }),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error((e as { error?: string }).error ?? `HTTP ${res.status}`);
      }
      setResult(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen px-6 py-16 max-w-2xl mx-auto">

      <div className="mb-12">
        <h1 className="font-editorial text-3xl text-[var(--color-ink)] mb-2">Signal audit</h1>
        <p className="text-sm text-[var(--color-muted)]">
          Paste any text — Optic maps its signals, loaded language, and implied confidence.
        </p>
      </div>

      <div className="space-y-4">
        <textarea
          className="w-full border border-[var(--color-border)] rounded-lg px-4 py-3 text-sm resize-y min-h-[140px] bg-white text-[var(--color-ink)] placeholder:text-[var(--color-muted)] focus:outline-none focus:border-[var(--color-ink)] transition-colors"
          placeholder="Paste the text you want to audit…"
          value={content}
          onChange={e => setContent(e.target.value)}
        />

        <div className="flex items-center justify-between">
          <label className="text-xs text-[var(--color-muted)] flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={includeML}
              onChange={e => setIncludeML(e.target.checked)}
              className="rounded"
            />
            Include ML detection
          </label>
          <button
            onClick={runAudit}
            disabled={loading || !content.trim()}
            className="px-5 py-2 text-sm font-medium rounded-full bg-black text-[var(--color-cream)] border border-black hover:bg-[var(--color-ink)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? 'Analyzing…' : 'Run audit →'}
          </button>
        </div>
      </div>

      {error && (
        <p className="mt-6 text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-4 py-3">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-12 border-t border-[var(--color-border)] pt-10 space-y-6">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs text-[var(--color-muted)] uppercase tracking-wide mb-1">Result</p>
              <p className="text-sm text-[var(--color-ink)]">
                {result.detection_count === 0
                  ? 'No signals detected.'
                  : `${result.detection_count} signal${result.detection_count !== 1 ? 's' : ''} detected`}
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-[var(--color-muted)]">
                {new Date(result.created_at).toLocaleTimeString()}
              </p>
              {result.max_severity && result.detection_count > 0 && (
                <p className="text-xs mt-0.5 capitalize">{result.max_severity} severity</p>
              )}
            </div>
          </div>

          {result.detections.length === 0 ? (
            <p className="text-sm text-[var(--color-muted)] border border-[var(--color-border)] rounded-lg px-4 py-6 text-center">
              Content appears clean — no loaded language or bias patterns found.
            </p>
          ) : (
            <div className="space-y-3">
              {result.detections.map((d, i) => (
                <div
                  key={i}
                  className={`p-4 border rounded-lg text-sm ${SEVERITY_COLOR[d.severity] ?? 'border-[var(--color-border)] bg-[var(--color-tag-bg)]'}`}
                >
                  <div className="flex justify-between items-start mb-1 gap-4">
                    <span className="font-medium capitalize">{d.attribute.replace(/_/g, ' ')}</span>
                    <span className="text-xs uppercase tracking-wide shrink-0 opacity-70">
                      {d.severity} · {(d.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="opacity-80 leading-relaxed">{d.description}</p>
                  {d.location && (
                    <p className="mt-1.5 text-xs opacity-60 font-mono truncate">
                      &ldquo;{d.location}&rdquo;
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

    </main>
  );
}
