const items = [
  'Source',
  'Signal',
  'Inference',
  'Confidence',
  'Repair',
  'Re-audit',
  'Private by design',
  'Local-first',
  'Subject-owned',
];

export default function MarqueeBar() {
  const track = [...items, ...items];

  return (
    <div
      className="w-full overflow-hidden py-4"
      style={{ background: 'var(--color-section-dark)' }}
      aria-hidden="true"
    >
      <div className="marquee-track flex gap-10 whitespace-nowrap" style={{ width: 'max-content' }}>
        {track.map((item, i) => (
          <span
            key={i}
            className="text-sm font-mono tracking-widest uppercase text-[rgba(245,243,239,0.4)] flex-shrink-0"
          >
            {item}
            {i < track.length - 1 && (
              <span className="ml-10 text-[rgba(245,243,239,0.15)]" aria-hidden="true">
                ·
              </span>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}
