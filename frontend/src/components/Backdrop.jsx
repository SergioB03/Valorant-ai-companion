import { useEffect, useState } from "react";
import { prefersReducedMotion } from "../utils.js";

// Valorant home-screen style animated backdrop: slowly zooming map splashes
// that crossfade on a timer. Map UUIDs verified 2026-07 against
// https://valorant-api.com/v1/maps
const MAPS = [
  { name: "Ascent", uuid: "7eaecc1b-4337-bbf6-6ab9-04b8f06b3319" },
  { name: "Haven", uuid: "2bee0dc9-4ffe-519b-1cbd-7fbe763a6047" },
  { name: "Bind", uuid: "2c9d57ec-4431-9c5e-2939-8f9ef6dd5cba" },
  { name: "Icebox", uuid: "e2ad5c54-4114-a870-9641-8ea21279579a" },
  { name: "Lotus", uuid: "2fe4ed3a-450a-948b-6d6b-e89a78e680a9" },
  { name: "Split", uuid: "d960549e-485c-e861-8d71-aa9d1aed12a2" },
];

const splash = (uuid) =>
  `https://media.valorant-api.com/maps/${uuid}/splash.png`;

const CYCLE_MS = 12000;

export default function Backdrop() {
  const [idx, setIdx] = useState(0);
  // Only mount layers we have actually shown, so first paint fetches one
  // splash instead of six; the upcoming one is preloaded ahead of time.
  const [shown, setShown] = useState([0]);

  useEffect(() => {
    // Under reduced motion: keep a single static splash, no cycling.
    if (prefersReducedMotion()) return undefined;
    const timer = setInterval(() => {
      setIdx((i) => (i + 1) % MAPS.length);
    }, CYCLE_MS);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    setShown((s) => (s.includes(idx) ? s : [...s, idx]));
    // Preload the next splash so the crossfade never pops in blank.
    if (prefersReducedMotion()) return;
    const img = new Image();
    img.src = splash(MAPS[(idx + 1) % MAPS.length].uuid);
  }, [idx]);

  return (
    <div className="backdrop" aria-hidden="true">
      {MAPS.map((m, i) =>
        shown.includes(i) ? (
          <div
            key={m.uuid}
            className={`backdrop-layer${i === idx ? " on" : ""}`}
            style={{ backgroundImage: `url(${splash(m.uuid)})` }}
          />
        ) : null
      )}
      <div className="backdrop-shade" />
      <span className="backdrop-map">{`// ${MAPS[idx].name}`}</span>
    </div>
  );
}
