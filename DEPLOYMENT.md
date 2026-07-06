# Deployment Guide

How to get Valorant AI Companion live: **backend on Render** (FastAPI) and **frontend on Vercel** (React/Vite), then wire the two together with CORS.

```
Browser ──> Vercel (frontend/)  ──HTTP──>  Render (backend/, FastAPI)
                                              ├── Anthropic Claude API
                                              └── HenrikDev API (match data)
```

## Prerequisites

- The repo pushed to GitHub
- An [Anthropic API key](https://console.anthropic.com)
- A HenrikDev API key (used as `RIOT_API_KEY` while the production Riot key is pending)
- Free accounts on [Render](https://render.com) and [Vercel](https://vercel.com)

---

## 1. Backend → Render (Blueprint)

The repo root contains `render.yaml`, so Render can set everything up from the file:

1. In the Render dashboard: **New → Blueprint** and connect this GitHub repo.
2. Render reads `render.yaml` and proposes one web service (`valorant-ai-companion-api`, root dir `backend`, free plan).
3. Fill in the environment variables it prompts for:

   | Variable | Value |
   |---|---|
   | `ANTHROPIC_API_KEY` | your Anthropic key |
   | `RIOT_API_KEY` | your HenrikDev key |
   | `CORS_ORIGINS` | `http://localhost:5173` for now — you'll replace this with the Vercel URL in step 3 |
   | `ADMIN_TOKEN` | optional — a long random secret that unlocks `GET /analytics/summary` (sent as the `X-Admin-Token` header). Leave it empty to keep the summary endpoint disabled (403). |

   `CLAUDE_MODEL` is preset to `claude-opus-4-8` by the blueprint.
4. Click **Apply** and wait for the build.
5. Sanity check: open `https://<your-service>.onrender.com/` — you should see the "API is running" message — and `https://<your-service>.onrender.com/docs` for the interactive Swagger UI.

> The blueprint declares `runtime: python` and pins the interpreter with a `PYTHON_VERSION` env var set to `3.12.5`, so the build won't pick a Python version that fights with `requirements.txt`.

### Free tier gotchas (read this)

- **The disk is ephemeral.** Everything under `backend/data/` — the SQLite database (`companion.sqlite3`, which holds both mental profiles and analytics events) and the ChromaDB vector index (`chroma_db/`) — is wiped on **every deploy AND every cold start** after an idle spin-down (see below). SQLite history (including analytics) and the Chroma index rebuild from scratch each time, and ChromaDB re-downloads its embedding model (~80 MB) too. Totally fine for a demo; for real persistence you'd attach a Render persistent disk or move to a hosted database.
- **The RAG index warms in the background at startup.** The app kicks off the index build (embedding-model download + embedding the knowledge corpus) when the server boots, so the first `POST /meta/ask` isn't doing the full build in-request. Still, expect the first few minutes after a deploy or cold start to be slow while that warm-up finishes.
- **Free services spin down when idle.** After ~15 minutes without traffic, the next request pays a cold start of up to a minute — and, per the first point, the instance comes back with a fresh disk.

### Known limitations

- `POST /claude/ask` is an **unauthenticated** endpoint that costs Anthropic credits on every call. It's rate-limited to 5 requests/minute per client IP (the other Claude-backed endpoints have their own per-IP limits too), which caps the burn rate but doesn't eliminate it — still, don't publish the backend URL widely, or remove that route before deploying publicly.

---

## 2. Frontend → Vercel

1. In Vercel: **Add New → Project** and import the same GitHub repo.
2. Set **Root Directory** to `frontend`. Vercel auto-detects Vite (`frontend/vercel.json` handles the SPA rewrites).
3. Add one environment variable:

   | Variable | Value |
   |---|---|
   | `VITE_API_URL` | `https://<your-service>.onrender.com` (no trailing slash) |

4. **Deploy.** You'll get a URL like `https://valorant-ai-companion.vercel.app`.

> `VITE_API_URL` is baked in at build time. If you ever change it, trigger a redeploy on Vercel.

---

## 3. Connect the two (CORS)

1. Back in Render: your service → **Environment** → set `CORS_ORIGINS` to your Vercel URL, e.g.

   ```
   https://valorant-ai-companion.vercel.app
   ```

   Multiple origins are comma-separated. No trailing slashes.
2. Save — Render redeploys automatically.

---

## 4. Verify

- Open the Vercel URL, search for a player (`name` + `#tag`), and confirm the dashboard fills in.
- Run a tilt check and ask the Mental Coach something.
- Ask a meta question — the first one may still be slow if the background index warm-up hasn't finished.
- If the browser console shows CORS errors, the `CORS_ORIGINS` value doesn't exactly match the frontend origin (check for `https://` and a missing/extra trailing slash).
- `GET /meta/status` on the backend tells you whether the RAG index is ready; a `503` from `/meta/ask` means ChromaDB isn't available on the instance.
- If you set `ADMIN_TOKEN`, check the analytics pipeline:

  ```bash
  curl -H "X-Admin-Token: <your-token>" https://<your-service>.onrender.com/analytics/summary
  ```

  You should get a JSON summary (totals, daily counts, funnel, latencies). Without the header — or with `ADMIN_TOKEN` unset on the service — it returns 403. Remember the free-tier caveat above: analytics live in the ephemeral SQLite file, so counts reset on every deploy/cold start.
