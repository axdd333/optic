'use client';

import { useMemo, useState } from 'react';
import {
  AXES,
  ROUNDS,
  TAG_LABELS,
  axisVerdict,
  emptyPicks,
  optionLabel,
  rankFor,
  scoreWorld,
  seededRun,
  type AxisId,
  type InstrumentId,
  type Picks,
  type Worldseed,
  type WorldScore,
} from '@/data/xenoguesser';

type Difficulty = 'cadet' | 'field' | 'coroner' | 'coldcase';

// Harder clearances take instruments offline — you infer the seed from fewer
// readings, the way real paleontology works from partial remains.
const DIFFICULTY: Record<
  Difficulty,
  { label: string; blurb: string; offline: InstrumentId[] }
> = {
  cadet: { label: 'Cadet', blurb: 'All six instruments online.', offline: [] },
  field: { label: 'Field', blurb: 'All six instruments online.', offline: [] },
  coroner: { label: 'Coroner', blurb: 'Planetary shadow offline.', offline: ['shadow'] },
  coldcase: {
    label: 'Cold Case',
    blurb: 'Shadow & singularity instruments offline.',
    offline: ['shadow', 'singularity'],
  },
};

const VERDICT_MARK = { exact: '✓', partial: '~', off: '✗', blank: '·' } as const;

export default function Xenoguesser() {
  const [difficulty, setDifficulty] = useState<Difficulty>('field');
  const [started, setStarted] = useState(false);
  const [seed, setSeed] = useState(() => Math.floor(Math.random() * 1e9));
  const run = useMemo(() => seededRun(seed), [seed]);

  const [roundIdx, setRoundIdx] = useState(0);
  const [picks, setPicks] = useState<Picks>(emptyPicks());
  const [locked, setLocked] = useState(false);
  const [scores, setScores] = useState<WorldScore[]>([]);
  const [activeInstrument, setActiveInstrument] = useState<InstrumentId>('morphology');

  const world = run[roundIdx];
  const offline = new Set(DIFFICULTY[difficulty].offline);
  const runTotal = scores.reduce((a, s) => a + s.points, 0);
  const lastScore = scores[roundIdx];

  function toggle(axisId: AxisId, key: string, multi: boolean) {
    if (locked) return;
    setPicks((p) => {
      const cur = p[axisId];
      if (multi) {
        return {
          ...p,
          [axisId]: cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key],
        };
      }
      return { ...p, [axisId]: cur[0] === key ? [] : [key] };
    });
  }

  function lockIn() {
    const result = scoreWorld(world, picks);
    setScores((s) => {
      const next = [...s];
      next[roundIdx] = result;
      return next;
    });
    setLocked(true);
  }

  function nextRound() {
    if (roundIdx + 1 >= ROUNDS) {
      setRoundIdx(ROUNDS);
      return;
    }
    setRoundIdx((i) => i + 1);
    setPicks(emptyPicks());
    setLocked(false);
    setActiveInstrument('morphology');
  }

  function restart() {
    setSeed(Math.floor(Math.random() * 1e9));
    setRoundIdx(0);
    setPicks(emptyPicks());
    setLocked(false);
    setScores([]);
    setActiveInstrument('morphology');
    setStarted(false);
  }

  const answeredAxes = AXES.filter((a) => picks[a.id].length > 0).length;
  const allAnswered = answeredAxes === AXES.length;

  // ---- Intro -----------------------------------------------------------
  if (!started) {
    return (
      <Shell>
        <div className="mx-auto max-w-2xl py-20 text-center">
          <p className="font-sans text-xs uppercase tracking-[0.3em] text-[var(--color-muted)]">
            Hyperspace Inference Engine
          </p>
          <h1 className="mt-4 font-editorial text-6xl font-semibold tracking-tight">
            Xenoguesser
          </h1>
          <p className="mx-auto mt-6 max-w-xl font-sans text-lg leading-relaxed text-[var(--color-muted)]">
            The engine seeds a hidden world — gravity, star, chemistry, catastrophe —
            and simulates life forward across deep time. You see only the final form,
            read through six instruments. Reconstruct the{' '}
            <span className="text-[var(--color-ink)]">Worldseed</span> from the body it
            left behind.
          </p>
          <p className="mx-auto mt-4 max-w-xl font-editorial text-lg italic text-[var(--color-ink)]">
            Every alien is a theorem with skin. The final form cannot lie.
          </p>

          <div className="mt-10 text-left">
            <p className="font-sans text-xs uppercase tracking-[0.2em] text-[var(--color-muted)]">
              Choose your clearance
            </p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {(Object.keys(DIFFICULTY) as Difficulty[]).map((d) => (
                <button
                  key={d}
                  onClick={() => setDifficulty(d)}
                  className={`rounded-lg border p-4 text-left transition ${
                    difficulty === d
                      ? 'border-[var(--color-ink)] bg-[var(--color-ink)] text-[var(--color-cream)]'
                      : 'border-[var(--color-border)] hover:border-[var(--color-ink)]'
                  }`}
                >
                  <div className="font-editorial text-xl">{DIFFICULTY[d].label}</div>
                  <div
                    className={`mt-1 font-sans text-sm ${
                      difficulty === d
                        ? 'text-[var(--color-cream)]/70'
                        : 'text-[var(--color-muted)]'
                    }`}
                  >
                    {DIFFICULTY[d].blurb}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={() => setStarted(true)}
            className="mt-10 rounded-full bg-[var(--color-ink)] px-10 py-4 font-sans text-base font-medium text-[var(--color-cream)] transition hover:opacity-90"
          >
            Peer into hyperspace →
          </button>
          <p className="mt-4 font-sans text-xs text-[var(--color-muted)]">
            {ROUNDS} worlds · 6 instruments · 9 axes · causal scoring · seed #{seed}
          </p>
        </div>
      </Shell>
    );
  }

  // ---- Report card -----------------------------------------------------
  if (roundIdx >= ROUNDS) {
    const maxTotal = ROUNDS * 1000;
    return (
      <Shell>
        <div className="mx-auto max-w-2xl py-16">
          <p className="font-sans text-xs uppercase tracking-[0.3em] text-[var(--color-muted)]">
            Engine session complete
          </p>
          <h1 className="mt-3 font-editorial text-5xl font-semibold">{rankFor(runTotal)}</h1>
          <p className="mt-4 font-sans text-2xl">
            {runTotal.toLocaleString()}{' '}
            <span className="text-[var(--color-muted)]">/ {maxTotal.toLocaleString()}</span>
            <span className="ml-3 text-[var(--color-muted)]">
              ({Math.round((runTotal / maxTotal) * 100)}% seed recovery)
            </span>
          </p>

          <div className="mt-10 space-y-3">
            {run.map((w, i) => (
              <div
                key={w.id}
                className="flex items-center justify-between border-b border-[var(--color-border)] pb-3"
              >
                <div>
                  <span className="font-editorial text-lg">{w.codename}</span>
                  <span className="ml-2 font-sans text-xs text-[var(--color-muted)]">
                    {w.id.toUpperCase()}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="h-2 w-32 overflow-hidden rounded-full bg-[var(--color-border)]">
                    <div
                      className="h-full bg-[var(--color-ink)]"
                      style={{ width: `${scores[i]?.matchPct ?? 0}%` }}
                    />
                  </div>
                  <span className="w-12 text-right font-sans text-sm text-[var(--color-muted)]">
                    {scores[i]?.matchPct ?? 0}%
                  </span>
                </div>
              </div>
            ))}
          </div>

          <button
            onClick={restart}
            className="mt-12 rounded-full bg-[var(--color-ink)] px-8 py-3 font-sans text-base font-medium text-[var(--color-cream)] transition hover:opacity-90"
          >
            Seed a new run →
          </button>
        </div>
      </Shell>
    );
  }

  // ---- Round -----------------------------------------------------------
  const activeReading = world.instruments.find((i) => i.id === activeInstrument);
  const isOffline = offline.has(activeInstrument);

  return (
    <Shell>
      <div className="flex items-center justify-between border-b border-[var(--color-border)] py-4">
        <span className="font-sans text-xs uppercase tracking-[0.2em] text-[var(--color-muted)]">
          World {roundIdx + 1} / {ROUNDS} · {DIFFICULTY[difficulty].label}
        </span>
        <span className="font-sans text-sm">
          Run total: <span className="font-medium">{runTotal.toLocaleString()}</span>
        </span>
      </div>

      <div className="grid gap-10 py-8 lg:grid-cols-[1fr_1fr]">
        {/* Instruments */}
        <div className="lg:sticky lg:top-6 lg:self-start">
          <p className="font-sans text-xs uppercase tracking-[0.3em] text-[var(--color-muted)]">
            Specimen {world.id.toUpperCase()}
          </p>
          <h2 className="mt-2 font-editorial text-3xl font-semibold">
            {locked ? world.codename : 'unresolved final form'}
          </h2>

          <div className="mt-5 flex flex-wrap gap-2">
            {world.instruments.map((inst) => {
              const dim = offline.has(inst.id) && !locked;
              return (
                <button
                  key={inst.id}
                  onClick={() => setActiveInstrument(inst.id)}
                  className={`rounded-full border px-3 py-1.5 font-sans text-[13px] transition ${
                    activeInstrument === inst.id
                      ? 'border-[var(--color-ink)] bg-[var(--color-ink)] text-[var(--color-cream)]'
                      : 'border-[var(--color-border)] hover:border-[var(--color-ink)]'
                  } ${dim ? 'opacity-50' : ''}`}
                >
                  {inst.label}
                  {dim ? ' ⃠' : ''}
                </button>
              );
            })}
          </div>

          <div className="mt-5 min-h-[160px] rounded-xl border border-[var(--color-border)] bg-[var(--color-white)] p-5">
            <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">
              {activeReading?.label}
            </p>
            <p className="mt-2 font-sans text-[15px] leading-relaxed">
              {isOffline && !locked
                ? '— instrument offline at this clearance. No reading available. Infer this dimension from the others. —'
                : activeReading?.reading}
            </p>
          </div>

          {locked && (
            <div className="mt-6">
              <p className="font-sans text-xs uppercase tracking-[0.2em] text-[var(--color-muted)]">
                The simulation, unsealed
              </p>
              <ol className="mt-3 space-y-3">
                {world.chain.map((stage) => (
                  <li key={stage.stage} className="border-l-2 border-[var(--color-ink)] pl-4">
                    <p className="font-sans text-xs font-semibold uppercase tracking-wider">
                      {stage.stage}
                    </p>
                    <p className="mt-0.5 font-sans text-[14px] leading-relaxed text-[var(--color-ink)]">
                      {stage.text}
                    </p>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>

        {/* Axes / reveal */}
        <div>
          {!locked && (
            <p className="mb-5 font-sans text-sm text-[var(--color-muted)]">
              Reconstruct the Worldseed. You score on the causal{' '}
              <em>tags</em> your answers imply — name the right pressure and you score
              even if the exact label is wrong.
            </p>
          )}

          {locked && lastScore && <CausalLedger world={world} score={lastScore} />}

          {AXES.map((axis) => {
            const verdict = locked ? axisVerdict(world, axis.id, picks[axis.id]) : null;
            return (
              <div key={axis.id} className="mb-6">
                <div className="flex items-baseline justify-between">
                  <p className="font-sans text-xs font-semibold uppercase tracking-wider">
                    {axis.title}
                    <span className="ml-2 font-normal text-[var(--color-muted)]">
                      {axis.multi ? '· choose all' : '· choose one'}
                    </span>
                  </p>
                  {verdict && verdict !== 'blank' && (
                    <span
                      className={`font-sans text-sm ${
                        verdict === 'exact'
                          ? 'text-[var(--color-ink)]'
                          : verdict === 'partial'
                            ? 'text-[var(--color-ink)]'
                            : 'text-[var(--color-muted)]'
                      }`}
                    >
                      {VERDICT_MARK[verdict]}{' '}
                      {verdict === 'exact' ? 'exact' : verdict === 'partial' ? 'close' : 'off'}
                    </span>
                  )}
                </div>
                {!locked && (
                  <p className="mt-0.5 font-sans text-sm text-[var(--color-muted)]">
                    {axis.prompt}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap gap-2">
                  {axis.options.map((opt) => {
                    const selected = picks[axis.id].includes(opt.key);
                    const isTruth = (world.truth[axis.id] ?? []).includes(opt.key);
                    let cls = 'border-[var(--color-border)] hover:border-[var(--color-ink)]';
                    if (locked) {
                      if (isTruth)
                        cls =
                          'border-[var(--color-ink)] bg-[var(--color-ink)] text-[var(--color-cream)]';
                      else if (selected)
                        cls =
                          'border-[var(--color-border)] line-through text-[var(--color-muted)]';
                      else cls = 'border-[var(--color-border)] text-[var(--color-muted)] opacity-50';
                    } else if (selected) {
                      cls =
                        'border-[var(--color-ink)] bg-[var(--color-ink)] text-[var(--color-cream)]';
                    }
                    return (
                      <button
                        key={opt.key}
                        disabled={locked}
                        onClick={() => toggle(axis.id, opt.key, axis.multi)}
                        className={`rounded-full border px-3 py-1.5 text-left font-sans text-[13px] leading-snug transition ${cls}`}
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
                {locked && (world.truth[axis.id] ?? []).length > 0 && (
                  <p className="mt-1.5 font-sans text-[13px] text-[var(--color-muted)]">
                    Truth:{' '}
                    {(world.truth[axis.id] ?? [])
                      .map((k) => optionLabel(axis.id, k))
                      .join(', ')}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Action bar */}
      <div className="sticky bottom-0 border-t border-[var(--color-border)] bg-[var(--color-cream)] py-4">
        {!locked ? (
          <div className="flex items-center justify-between">
            <span className="font-sans text-sm text-[var(--color-muted)]">
              {answeredAxes}/{AXES.length} axes answered
              {allAnswered ? ' — ready to resolve.' : '.'}
            </span>
            <button
              onClick={lockIn}
              disabled={!allAnswered}
              className="rounded-full bg-[var(--color-ink)] px-8 py-3 font-sans text-base font-medium text-[var(--color-cream)] transition enabled:hover:opacity-90 disabled:opacity-30"
            >
              Resolve the Worldseed →
            </button>
          </div>
        ) : (
          <div>
            <div className="flex items-center justify-between">
              <div className="font-sans text-sm">
                <span className="font-medium">{lastScore?.matchPct}% seed match</span>
                <span className="ml-2 text-[var(--color-muted)]">
                  +{lastScore?.points.toLocaleString()} pts
                </span>
              </div>
              <button
                onClick={nextRound}
                className="rounded-full bg-[var(--color-ink)] px-8 py-3 font-sans text-base font-medium text-[var(--color-cream)] transition hover:opacity-90"
              >
                {roundIdx + 1 >= ROUNDS ? 'See session report →' : 'Next world →'}
              </button>
            </div>
            <p className="mt-3 font-editorial text-[15px] italic leading-relaxed text-[var(--color-ink)]">
              {world.verdict}
            </p>
          </div>
        )}
      </div>
    </Shell>
  );
}

function CausalLedger({ world, score }: { world: Worldseed; score: WorldScore }) {
  return (
    <div className="mb-7 rounded-xl border border-[var(--color-border)] bg-[var(--color-white)] p-5">
      <div className="flex items-baseline justify-between">
        <p className="font-sans text-xs font-semibold uppercase tracking-wider">
          Causal ledger — {world.codename}
        </p>
        <span className="font-editorial text-2xl">{score.matchPct}%</span>
      </div>
      <p className="mt-1 font-sans text-[13px] text-[var(--color-muted)]">
        You reconstructed {score.hitTags.length} of {world.trueTags.length} causal tags
        {score.falseTags.length > 0 ? ` · ${score.falseTags.length} false leads` : ''}.
      </p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {score.hitTags.map((t) => (
          <span
            key={t}
            className="rounded-full bg-[var(--color-ink)] px-2.5 py-1 font-sans text-[12px] text-[var(--color-cream)]"
          >
            ✓ {TAG_LABELS[t] ?? t}
          </span>
        ))}
        {score.missedTags.map((t) => (
          <span
            key={t}
            className="rounded-full border border-[var(--color-border)] px-2.5 py-1 font-sans text-[12px] text-[var(--color-muted)]"
          >
            ✗ {TAG_LABELS[t] ?? t}
          </span>
        ))}
        {score.falseTags.map((t) => (
          <span
            key={t}
            className="rounded-full border border-dashed border-[var(--color-muted)] px-2.5 py-1 font-sans text-[12px] text-[var(--color-muted)] line-through"
          >
            {TAG_LABELS[t] ?? t}
          </span>
        ))}
      </div>
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-[var(--color-cream)] text-[var(--color-ink)]">
      <div className="mx-auto max-w-5xl px-6">{children}</div>
    </main>
  );
}
