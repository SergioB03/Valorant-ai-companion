# 2026-09-05 — Growth Wave 1

Implements the five Wave-1 quick wins from [docs/GROWTH-FEATURES.md](../../GROWTH-FEATURES.md)
(the council's staff-SWE-vetted specs, including all security mitigations as requirements):

1. Tappable starter prompts in coach chat (Meta-tab chip pattern, same send path)
2. Mental-game positioning: static hero in `index.html` + real empty state (demo CTA lands here in Wave 2)
3. Persist paid AI reports per player + "generated Xh ago" stamp (saves Claude spend; never chat messages)
4. GitHub footer link + "Open source · privacy-first" badge
5. Recent-players quick switcher (localStorage, capped, clearable)

## Before

- `before-landing.png` — live rebuy.gg landing: the "No player selected" dead end both
  analysts independently flagged as the #1 activation leak
- `before-mental-tab.png` — Mental Coach tab via deep link: inert example-question hint,
  no starter prompts, reports lost on every reload

After screenshots will be appended when the wave lands.
