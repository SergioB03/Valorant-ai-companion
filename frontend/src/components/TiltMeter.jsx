import { useRef, useState } from "react";
import { LEVEL_COLORS } from "../utils.js";
import { useGSAP, gsap, motionOK, EASE_SNAP } from "../anim.js";

const SCALE = ["calm", "warming", "heated", "tilted"];

export default function TiltMeter({ score, level }) {
  const pct = Math.max(0, Math.min(100, Number(score) || 0));
  const color = LEVEL_COLORS[level] || "#9aa7b3";

  const scope = useRef(null);
  const fillRef = useRef(null);
  const [shown, setShown] = useState(pct);

  // One timeline so the number and the bar arrive together — the bar sweeps up
  // while the score counts to match it, then the level badge pops in behind.
  // Under reduced motion everything is set to its final state instantly.
  useGSAP(
    () => {
      if (!motionOK()) {
        gsap.set(fillRef.current, { width: `${pct}%` });
        setShown(pct);
        return;
      }
      const counter = { n: 0 };
      setShown(0);
      gsap
        .timeline()
        .fromTo(
          fillRef.current,
          { width: "0%" },
          { width: `${pct}%`, duration: 1.05, ease: EASE_SNAP },
          0,
        )
        .to(
          counter,
          {
            n: pct,
            duration: 1.05,
            ease: EASE_SNAP,
            onUpdate: () => setShown(Math.round(counter.n)),
          },
          0,
        )
        .fromTo(
          scope.current.querySelector(".tilt-level"),
          { opacity: 0, scale: 0.86 },
          { opacity: 1, scale: 1, duration: 0.35, ease: "back.out(2)" },
          0.45,
        );
    },
    { scope, dependencies: [pct, level] },
  );

  return (
    <div className="tilt-meter" ref={scope}>
      <div className="tilt-meter-head">
        <span
          className="tilt-score"
          style={{ color, textShadow: `0 0 22px ${color}55` }}
        >
          {shown}
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
          ref={fillRef}
          className="meter-fill"
          style={{
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
