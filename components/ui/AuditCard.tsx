type Severity = 'high' | 'medium' | 'low' | 'positive';

type AuditRow = {
  label: string;
  value: string;
  severity: Severity;
  subLabel: string;
  meta: string;
};

const severityDot: Record<Severity, string> = {
  high: 'bg-red-500',
  medium: 'bg-amber-400',
  low: 'bg-slate-400',
  positive: 'bg-emerald-500',
};

const rows: AuditRow[] = [
  {
    label: 'Signals',
    value: 'Strong proof of work',
    severity: 'positive',
    subLabel: '14 sources indexed',
    meta: 'Coverage · High',
  },
  {
    label: 'Implication',
    value: 'Capable. Hard to place.',
    severity: 'medium',
    subLabel: 'Uneven recency, scattered context',
    meta: 'Confidence · Medium',
  },
  {
    label: 'Risk',
    value: '2 contradictions found',
    severity: 'high',
    subLabel: 'Gap between narrative and record',
    meta: 'Clarity · Low',
  },
  {
    label: 'Repair',
    value: '4 actions available',
    severity: 'low',
    subLabel: '1 high-impact, 3 moderate',
    meta: 'Effort · Low–Med',
  },
];

export default function AuditCard() {
  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-white overflow-hidden shadow-[0_4px_32px_rgba(14,14,12,0.06)]">
      <div className="px-5 pt-5 pb-3 border-b border-[var(--color-border)]">
        <p className="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)]">
          Sample report
        </p>
        <p className="mt-1 text-sm font-medium text-[var(--color-ink)]">Only you see this.</p>
      </div>

      <ul className="divide-y divide-[var(--color-border)]">
        {rows.map((row) => (
          <li key={row.label} className="flex items-start justify-between gap-4 px-5 py-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <span
                  className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${severityDot[row.severity]}`}
                  aria-hidden="true"
                />
                <span className="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)]">
                  {row.label}
                </span>
              </div>
              <p className="text-sm font-medium text-[var(--color-ink)] leading-snug">{row.value}</p>
              <p className="text-xs text-[var(--color-muted)] mt-0.5">{row.subLabel}</p>
            </div>
            <span className="text-[10px] font-mono text-[var(--color-muted)] whitespace-nowrap pt-0.5 flex-shrink-0">
              {row.meta}
            </span>
          </li>
        ))}
      </ul>

      <div className="px-5 py-3 bg-[var(--color-tag-bg)] border-t border-[var(--color-border)]">
        <p className="text-[11px] text-[var(--color-muted)]">
          Not shared. Not stored. Not scored.
        </p>
      </div>
    </div>
  );
}
