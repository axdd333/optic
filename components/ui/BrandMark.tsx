type Dot = readonly [number, number, number];

type BrandMarkProps = {
  className?: string;
  title?: string;
};

const dots: readonly Dot[] = [
  [28, 10, 1.2],
  [34, 10, 1.3],
  [22, 14, 1.3],
  [28, 14, 1.8],
  [34, 14, 1.9],
  [40, 14, 1.4],
  [18, 20, 1.4],
  [24, 20, 2.2],
  [30, 20, 2.7],
  [36, 20, 2.4],
  [42, 20, 1.7],
  [14, 26, 1.3],
  [20, 26, 2.3],
  [26, 26, 3],
  [32, 26, 3.6],
  [38, 26, 3],
  [44, 26, 2.2],
  [50, 26, 1.3],
  [12, 32, 1.5],
  [18, 32, 2.6],
  [24, 32, 3.5],
  [30, 32, 4.4],
  [36, 32, 4.1],
  [42, 32, 3.1],
  [48, 32, 2.1],
  [54, 32, 1.1],
  [14, 38, 1.4],
  [20, 38, 2.4],
  [26, 38, 3.4],
  [32, 38, 4.5],
  [38, 38, 3.6],
  [44, 38, 2.5],
  [50, 38, 1.5],
  [18, 44, 1.4],
  [24, 44, 2.3],
  [30, 44, 3],
  [36, 44, 2.9],
  [42, 44, 2],
  [48, 44, 1.2],
  [22, 50, 1.1],
  [28, 50, 1.7],
  [34, 50, 1.8],
  [40, 50, 1.2],
  [28, 55, 1],
  [34, 55, 1],
];

export default function BrandMark({ className, title }: BrandMarkProps) {
  const label = title ? undefined : true;

  return (
    <svg
      aria-hidden={label}
      className={className}
      role={title ? 'img' : undefined}
      viewBox="0 0 64 64"
    >
      {title ? <title>{title}</title> : null}
      <g fill="currentColor">
        {dots.map(([cx, cy, r]) => (
          <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={r} />
        ))}
      </g>
    </svg>
  );
}
