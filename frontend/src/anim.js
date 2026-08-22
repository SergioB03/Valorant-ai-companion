// GSAP animation layer.
//
// One place to register plugins and to define what "motion" means for this app,
// so components never re-implement the reduced-motion check. Everything here is
// a no-op (final state applied instantly) when the visitor asks for reduced
// motion, matching the existing CSS @media (prefers-reduced-motion) rules.

import { gsap } from "gsap";
import { useGSAP } from "@gsap/react";
import { prefersReducedMotion } from "./utils.js";

gsap.registerPlugin(useGSAP);

// Valorant's UI moves with a hard, decisive snap rather than a soft ease —
// these two curves keep every animation in the app on the same character.
export const EASE = "power3.out";
export const EASE_SNAP = "power4.out";

export const motionOK = () => !prefersReducedMotion();

/** Tween a number for display. Returns the tween so callers can kill it. */
export function tweenNumber(from, to, onUpdate, opts = {}) {
  const { duration = 0.9, ease = EASE, decimals = 0 } = opts;
  const state = { n: from };
  if (!motionOK()) {
    onUpdate(Number(to.toFixed(decimals)));
    return null;
  }
  return gsap.to(state, {
    n: to,
    duration,
    ease,
    onUpdate: () => onUpdate(Number(state.n.toFixed(decimals))),
  });
}

/**
 * Staggered entrance for a set of children. `scope` is the container element;
 * `selector` picks the items. Safe to call with nothing matching.
 */
export function revealStagger(scope, selector, opts = {}) {
  if (!scope) return null;
  const items = scope.querySelectorAll(selector);
  if (!items.length) return null;
  if (!motionOK()) {
    gsap.set(items, { clearProps: "all" });
    return null;
  }
  const { y = 14, duration = 0.5, stagger = 0.055, delay = 0 } = opts;
  return gsap.fromTo(
    items,
    { opacity: 0, y },
    { opacity: 1, y: 0, duration, stagger, delay, ease: EASE, clearProps: "transform" },
  );
}

/** Single-element entrance. */
export function revealIn(el, opts = {}) {
  if (!el) return null;
  if (!motionOK()) {
    gsap.set(el, { clearProps: "all" });
    return null;
  }
  const { y = 10, duration = 0.45, delay = 0, from = {} } = opts;
  return gsap.fromTo(
    el,
    { opacity: 0, y, ...from },
    { opacity: 1, y: 0, duration, delay, ease: EASE, clearProps: "transform" },
  );
}

export { gsap, useGSAP };
