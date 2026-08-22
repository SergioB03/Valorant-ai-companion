import { useEffect, useRef, useState } from "react";
import { tweenNumber } from "../anim.js";

/**
 * A number that counts up to `value` with GSAP.
 *
 * Replaces the hand-rolled rAF counter: GSAP gives a real easing curve, and
 * re-targeting mid-flight (a new player searched while the last count is still
 * running) is handled by killing the previous tween rather than racing it.
 *
 * Decimal precision is taken from the incoming value — `"1.23"` counts to two
 * decimals, `42` to none — so callers can pass pre-formatted stats unchanged.
 */
export default function AnimatedNumber({ value, duration = 0.9 }) {
  const num = Number(value);
  const decimals = (String(value).split(".")[1] || "").length;
  const [shown, setShown] = useState(num);
  const tweenRef = useRef(null);
  const fromRef = useRef(0);

  useEffect(() => {
    if (!Number.isFinite(num)) return undefined;
    tweenRef.current?.kill();
    tweenRef.current = tweenNumber(fromRef.current, num, setShown, {
      duration,
      decimals,
    });
    fromRef.current = num;
    return () => tweenRef.current?.kill();
  }, [num, decimals, duration]);

  // Non-numeric values (e.g. "?") pass straight through.
  if (!Number.isFinite(num)) return <>{value}</>;
  return <>{shown.toFixed(decimals)}</>;
}
