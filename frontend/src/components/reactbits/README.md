# React Bits components (vendored)

Files in this directory come from [React Bits](https://reactbits.dev)
([DavidHDev/react-bits](https://github.com/DavidHDev/react-bits)) and are **not**
covered by this repository's Apache-2.0 licence. They are licensed under
**MIT + Commons Clause v1.0** — see [LICENSE.md](./LICENSE.md) in this folder.

What that licence means here:

- Using these components as part of this application is expressly permitted,
  including commercially.
- Selling, sublicensing, or redistributing **the components themselves** —
  alone, bundled, or ported — is not. So don't lift this folder out and publish
  it as a component library.
- The copyright and permission notice has to travel with the code, which is why
  `LICENSE.md` sits next to the components rather than only at the repo root.

React Bits is a copy-in library (shadcn/jsrepo style), not an npm dependency, so
the source lives in the repo. **Keep these files verbatim.** Project-specific
styling is applied by overriding their classes from `src/index.css` instead of
editing their CSS, so a component can be re-fetched from upstream without
re-applying local edits.

> Note: the `react-bits` package on npm is **unrelated** — an abandoned 2017
> project by a different author. Don't install it.

Currently vendored:

| Component | Used by | Needs |
|---|---|---|
| `ScrambledText` | the site footer (`App.jsx`) | `gsap` + the free `SplitText` / `ScrambleTextPlugin` |
