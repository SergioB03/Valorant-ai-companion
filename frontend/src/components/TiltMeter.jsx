import { LEVEL_COLORS } from "../utils.js";

const SCALE = ["calm", "warming", "heated", "tilted"];

export default function TiltMeter({ score, level }) {
  const pct = Math.max(0, Math.min(100, Number(score) || 0));
  const color = LEVEL_COLORS[level] || "#9aa7b3";

  return (
    <div className="tilt-meter">
      <div className="tilt-meter-head">
        <span className="tilt-score" style={{ color }}>
          {pct}
        </span>
        <span className="tilt-level" style={{ color, borderColor: color }}>
          {level || "unknown"}
        </span>
      </div>
      <div
        className="meter-track"
        role="img"
        aria-label={`Tilt score ${pct} out of 100 — ${level}`}
      >
        <div
          className="meter-fill"
          style={{ width: `${pct}%`, background: color }}
        />
        {[25, 50, 75].map((t) => (
          <span key={t} className="meter-tick" style={{ left: `${t}%` }} />
        ))}
      </div>
      <div className="meter-scale">
        {SCALE.map((s) => (
          <span
            key={s}
            className={s === level ? "current" : ""}
            style={s === level ? { color: LEVEL_COLORS[s] } : undefined}
          >
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}
