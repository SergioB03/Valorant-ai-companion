import { useEffect, useState } from "react";
import { LEVEL_COLORS, prefersReducedMotion } from "../utils.js";

const SCALE = ["calm", "warming", "heated", "tilted"];

export default function TiltMeter({ score, level }) {
  const pct = Math.max(0, Math.min(100, Number(score) || 0));
  const color = LEVEL_COLORS[level] || "#9aa7b3";

  // Animate the fill sweeping up from 0 on load (skipped under
  // prefers-reduced-motion, where the CSS transition is also disabled).
  const [fill, setFill] = useState(() => (prefersReducedMotion() ? pct : 0));
  useEffect(() => {
    if (prefersReducedMotion()) {
      setFill(pct);
      return undefined;
    }
    setFill(0);
    const id = setTimeout(() => setFill(pct), 60);
    return () => clearTimeout(id);
  }, [pct]);

  return (
    <div className="tilt-meter">
      <div className="tilt-meter-head">
        <span
          className="tilt-score"
          style={{ color, textShadow: `0 0 22px ${color}55` }}
        >
          {pct}
        </span>
        <span
          className="tilt-level"
          style={{
            color,
            borderColor: color,
            boxShadow: `0 0 14px -4px ${color}`,
          }}
        >
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
          style={{
            width: `${fill}%`,
            background: color,
            boxShadow: `0 0 16px 0 ${color}`,
          }}
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
