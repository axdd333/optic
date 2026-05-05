import type { LegalDoc } from '@/data/legal';

type LegalPageProps = {
  doc: LegalDoc;
};

export default function LegalPage({ doc }: LegalPageProps) {
  return (
    <main className="w-full bg-[var(--color-cream)]">
      <section className="mx-auto max-w-[900px] px-6 py-20 md:py-28">
        <p className="mb-4 font-mono text-xs uppercase tracking-widest
          text-[var(--color-muted)]">
          Legal
        </p>
        <h1 className="mb-5 font-serif text-4xl font-semibold leading-tight
          text-[var(--color-ink)] md:text-5xl">
          {doc.title}
        </h1>
        <p className="max-w-2xl text-lg leading-relaxed
          text-[var(--color-muted)]">
          {doc.summary}
        </p>
        <p className="mt-6 text-sm text-[var(--color-muted)]">
          Effective {doc.updated}
        </p>
      </section>

      <section className="mx-auto max-w-[900px] px-6 pb-24">
        <article className="divide-y divide-[var(--color-border)]
          border-y border-[var(--color-border)]">
          {doc.sections.map((section) => (
            <section key={section.heading} className="py-9">
              <h2 className="mb-4 font-serif text-2xl font-semibold
                text-[var(--color-ink)]">
                {section.heading}
              </h2>
              <div className="space-y-4 text-base leading-relaxed
                text-[var(--color-muted)]">
                {section.body.map((copy) => (
                  <p key={copy}>{copy}</p>
                ))}
              </div>
            </section>
          ))}
        </article>
      </section>
    </main>
  );
}
