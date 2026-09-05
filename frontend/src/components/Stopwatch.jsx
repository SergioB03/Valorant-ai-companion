import { memo, useEffect, useState } from "react";

/**
 * Bruno-style elapsed-time counter for the long Claude waits: ticks every
 * 100ms while `running`, rendered as "4.7s". Fixed width via CSS
 * (.stopwatch — tabular-nums + min-width) so the ticking digits never nudge
 * the layout, and aria-hidden so it can sit next to the Spinner's polite
 * live region without announcing ten times a second.
 */
function Stopwatch({ running }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!running) return undefined;
    const start = performance.now();
    setElapsed(0);
    const id = setInterval(() => {
      setElapsed(performance.now() - start);
    }, 100);
    return () => clearInterval(id);
  }, [running]);

  if (!running) return null;
  return (
    <span className="stopwatch" aria-hidden="true">
      {(elapsed / 1000).toFixed(1)}s
    </span>
  );
}

export default memo(Stopwatch);
