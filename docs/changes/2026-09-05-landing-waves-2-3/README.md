# 2026-09-05 — Landing page + Growth Waves 2–3

Fixes the owner-reported "always lands on my test user's dashboard" behavior (last-player
auto-restore hijacked the homescreen — which also hid the Wave-1 hero from returning
visitors) and finishes the council roadmap: real landing page, ⭐ demo player, friendly
quota state, shareable tilt card, returning-player ritual, patch-digest pages, plus the
tilt_snapshots bounding precondition and the dead RIOT_API_KEY fallback cleanup.

## Before

- `before-homescreen.png` / `before-mobile.png` — live rebuy.gg fresh-visit state
  (Wave-1 hero; returning visitors with a saved player skipped straight past this).
