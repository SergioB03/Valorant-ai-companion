# Third-party licences

This project is Apache-2.0 (see [LICENSE](./LICENSE)), **except** for the
third-party code noted below, which keeps its own licence.

## Vendored source (in this repository)

| Path | Project | Licence |
|---|---|---|
| `frontend/src/components/reactbits/**` | [React Bits](https://github.com/DavidHDev/react-bits) | MIT + Commons Clause v1.0 — full text in [`frontend/src/components/reactbits/LICENSE.md`](./frontend/src/components/reactbits/LICENSE.md) |

React Bits is a copy-in component library, so its source lives in this repo
rather than in `node_modules`. The Commons Clause permits use in an application
(including commercially) but forbids selling, sublicensing, or redistributing
**the components themselves** — alone, bundled, or ported. Apache-2.0 grants
recipients broader redistribution rights than that, so those files are carved
out here rather than silently relicensed.

## Runtime dependencies (not vendored)

| Package | Licence |
|---|---|
| `gsap`, `@gsap/react` | GSAP Standard "No Charge" licence — <https://gsap.com/standard-license> |
| `react`, `react-dom` | MIT |
| `vite`, `@vitejs/plugin-react` | MIT |
| `fastapi`, `starlette`, `uvicorn`, `pydantic`, `httpx`, `anthropic`, `python-dotenv` | MIT / BSD-3-Clause |
| `chromadb` | Apache-2.0 |
| `slowapi` | MIT |
| Caddy (container image) | Apache-2.0 |

As of GSAP 3.13 every GSAP plugin — including the formerly Club-only `SplitText`
and `ScrambleTextPlugin` this project uses — is free on npm under that standard
licence. It permits use in a freely-accessible site like this one; reselling GSAP
itself, or shipping it inside a competing animation product, is what it excludes.
