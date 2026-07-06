// Mini trend of tilt snapshots (single series, fixed 0–100 domain).
export default function Sparkline({ points, width = 280, height = 64 }) {
  if (!points || points.length === 0) return null;

  const pad = 8;
  const x = (i) =>
    points.length === 1
      ? width / 2
      : pad + (i * (width - pad * 2)) / (points.length - 1);
  const y = (v) =>
    pad + (1 - Math.max(0, Math.min(100, v)) / 100) * (height - pad * 2);

  const path = points
    .map(
      (p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`
    )
    .join(" ");

  return (
    <svg
      className="sparkline"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Tilt score history, ${points.length} snapshots, oldest to newest`}
    >
      <line
        x1={pad}
        y1={y(50)}
        x2={width - pad}
        y2={y(50)}
        stroke="currentColor"
        strokeOpacity="0.15"
        strokeDasharray="3 4"
      />
      <path
        d={path}
        fill="none"
        stroke="#9aa7b3"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {points.map((p, i) => (
        <circle
          key={i}
          cx={x(i)}
          cy={y(p.value)}
          r="3.5"
          fill={p.color || "#9aa7b3"}
          stroke="#1f2933"
          strokeWidth="1.5"
        >
          <title>{p.label}</title>
        </circle>
      ))}
    </svg>
  );
}
