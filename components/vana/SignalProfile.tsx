'use client';

/**
 * SignalProfile — renders the aggregated signal profile produced by
 * POST /api/backend/api/vana/ingest (persisted at GET /api/vana/profile).
 * Used by both the onboarding payoff step and /app/profile.
 */

export interface VanaDetection {
  attribute: string;
  severity: string;
  confidence: number;
  description: string;
}

export interface VanaWorstOffender {
  id: string;
  content_summary: string;
  detection_count: number;
  max_severity: string;
  detections: VanaDetection[];
  metadata?: { platform?: string; kind?: string; title?: string };
}

export interface VanaSource {
  platform: string;
  files: number;
  audit_items: number;
  profiled_items: number;
  detections: number;
  kinds: Record<string, number>;
}

export interface VanaProfile {
  exists?: boolean;
  generated_at: number;
  corpus: {
    files_parsed: number;
    audited_items: number;
    flagged_items: number;
    profiled_items: number;
    total_chars: number;
    truncated: boolean;
  };
  sources: VanaSource[];
  audit: {
    score: number;
    total_detections: number;
    severity: Record<string, number>;
    top_attributes: { attribute: string; count: number; avg_confidence: number }[];
    worst_offenders: VanaWorstOffender[];
  };
}

const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low', 'info'];

const SEVERITY_BAR: Record<string, string> = {
  critical: 'bg-red-700',
  high: 'bg-red-500',
  medium: 'bg-amber-500',
  low: 'bg-blue-400',
  info: 'bg-gray-300',
};

const SEVERITY_TEXT: Record<string, string> = {
  critical: 'text-red-700 border-red-200 bg-red-50',
  high: 'text-red-600 border-red-200 bg-red-50',
  medium: 'text-amber-600 border-amber-200 bg-amber-50',
  low: 'text-blue-600 border-blue-200 bg-blue-50',
  info: 'text-gray-500 border-gray-200 bg-gray-50',
};

function prettyAttribute(attr: string): string {
  return attr.replace(/_/g, ' ');
}

export default function SignalProfile({ profile }: { profile: VanaProfile }) {
  const { corpus, sources, audit } = profile;
  const severityTotal =
    SEVERITY_ORDER.reduce((acc, s) => acc + (audit.severity[s] ?? 0), 0) || 1;
  const maxAttr = audit.top_attributes[0]?.count ?? 1;

  return (
    <div className="space-y-10">
      {/* Headline numbers */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Items audited', value: corpus.audited_items.toLocaleString() },
          { label: 'Detections', value: audit.total_detections.toLocaleString() },
          { label: 'Flagged items', value: corpus.flagged_items.toLocaleString() },
          { label: 'Signal score', value: audit.score.toFixed(2) },
        ].map(({ label, value }) => (
          <div
            key={label}
            className="border border-[var(--color-border)] rounded-lg px-4 py-3 bg-white"
          >
            <p className="font-editorial text-2xl text-[var(--color-ink)]">{value}</p>
            <p className="text-xs text-[var(--color-muted)] mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* Severity distribution */}
      {audit.total_detections > 0 && (
        <section>
          <h2 className="text-sm font-medium text-[var(--color-ink)] mb-3">
            Severity distribution
          </h2>
          <div className="flex h-3 w-full rounded-full overflow-hidden border border-[var(--color-border)]">
            {SEVERITY_ORDER.filter(s => (audit.severity[s] ?? 0) > 0).map(s => (
              <div
                key={s}
                className={SEVERITY_BAR[s]}
                style={{ width: `${((audit.severity[s] ?? 0) / severityTotal) * 100}%` }}
                title={`${s}: ${audit.severity[s]}`}
              />
            ))}
          </div>
          <div className="flex flex-wrap gap-3 mt-2">
            {SEVERITY_ORDER.filter(s => (audit.severity[s] ?? 0) > 0).map(s => (
              <span key={s} className="text-xs text-[var(--color-muted)]">
                <span className={`inline-block w-2 h-2 rounded-full mr-1 ${SEVERITY_BAR[s]}`} />
                {s} · {audit.severity[s]}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Top attributes */}
      {audit.top_attributes.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-[var(--color-ink)] mb-3">
            Dominant signal patterns
          </h2>
          <div className="space-y-2">
            {audit.top_attributes.map(a => (
              <div key={a.attribute} className="flex items-center gap-3">
                <span className="text-xs text-[var(--color-ink)] w-40 shrink-0 capitalize">
                  {prettyAttribute(a.attribute)}
                </span>
                <div className="flex-1 h-2 rounded-full bg-[var(--color-cream)] overflow-hidden">
                  <div
                    className="h-full rounded-full bg-black"
                    style={{ width: `${(a.count / maxAttr) * 100}%` }}
                  />
                </div>
                <span className="text-xs text-[var(--color-muted)] w-24 shrink-0 text-right">
                  {a.count} · conf {a.avg_confidence.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Source breakdown */}
      <section>
        <h2 className="text-sm font-medium text-[var(--color-ink)] mb-3">Sources</h2>
        <div className="grid sm:grid-cols-2 gap-3">
          {sources.map(s => (
            <div
              key={s.platform}
              className="border border-[var(--color-border)] rounded-lg px-4 py-3 bg-white"
            >
              <div className="flex items-baseline justify-between">
                <p className="text-sm font-medium text-[var(--color-ink)] capitalize">
                  {s.platform.replace(/_/g, ' ')}
                </p>
                <p className="text-xs text-[var(--color-muted)]">{s.files} export{s.files === 1 ? '' : 's'}</p>
              </div>
              <p className="text-xs text-[var(--color-muted)] mt-1">
                {s.audit_items > 0 && `${s.audit_items} audited`}
                {s.audit_items > 0 && s.detections > 0 && ` · ${s.detections} detections`}
                {s.audit_items === 0 && s.profiled_items > 0 && `${s.profiled_items} items profiled (non-text)`}
                {s.audit_items > 0 && s.profiled_items > 0 && ` · ${s.profiled_items} profiled`}
              </p>
              {Object.keys(s.kinds).length > 0 && (
                <p className="text-[11px] text-[var(--color-muted)] mt-1">
                  {Object.entries(s.kinds)
                    .map(([k, v]) => `${v} ${k}`)
                    .join(' · ')}
                </p>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Worst offenders */}
      {audit.worst_offenders.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-[var(--color-ink)] mb-3">
            Highest-signal items
          </h2>
          <div className="space-y-3">
            {audit.worst_offenders.map(w => (
              <details
                key={w.id}
                className="border border-[var(--color-border)] rounded-lg px-4 py-3 bg-white"
              >
                <summary className="cursor-pointer select-none flex items-center justify-between gap-3">
                  <span className="text-sm text-[var(--color-ink)] truncate">
                    {w.content_summary}
                  </span>
                  <span
                    className={`text-[11px] border rounded-full px-2 py-0.5 shrink-0 ${
                      SEVERITY_TEXT[w.max_severity] ?? SEVERITY_TEXT.info
                    }`}
                  >
                    {w.max_severity} · {w.detection_count}
                  </span>
                </summary>
                <ul className="mt-3 space-y-2">
                  {w.detections.slice(0, 8).map((d, i) => (
                    <li key={i} className="text-xs text-[var(--color-muted)]">
                      <span className="capitalize text-[var(--color-ink)]">
                        {prettyAttribute(d.attribute)}
                      </span>{' '}
                      ({d.severity}, {Math.round(d.confidence * 100)}%) — {d.description}
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          </div>
        </section>
      )}

      {corpus.truncated && (
        <p className="text-xs text-[var(--color-muted)]">
          Corpus was truncated to the audit cap — re-run ingestion with a higher
          limit to cover everything.
        </p>
      )}
    </div>
  );
}
