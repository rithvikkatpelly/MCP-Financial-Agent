# Deployment

The repo has three runnable surfaces. Only the **HTTP API + frontend** are
meant to be *hosted*; the MCP server runs on the user's own machine next to
Claude Desktop, and the Streamlit page is a local demo.

```
frontend/ (static)  ──HTTP──▶  backend/app (FastAPI)  ──▶  FRED API
                                     │
src/server.py (MCP, local)  ─────────┘  same src/tools.py, no shared process
```

This document is the checklist for getting `backend/` + `frontend/` onto the
internet. Nothing here is done yet — local dev works (`README.md` → "Run the
API"), production does not.

---

## 1. Backend — containerize + host

Not committed yet:

- **`backend/Dockerfile`** — `python:3.12-slim`, `pip install -r requirements.txt`,
  copy `src/` and `backend/`, `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]`
  with `WORKDIR /app/backend`. Note the image needs **both** `src/` and
  `backend/` because the API imports the shared tool logic from `src/`.
- **`backend/.dockerignore`** — `.venv`, `__pycache__`, `frontend/`, `.git`,
  `*.sqlite`, `*.log`.
- A production ASGI setup: `uvicorn` alone is fine for low traffic; for real
  load put it behind `gunicorn -k uvicorn.workers.UvicornWorker` or run
  multiple `uvicorn --workers N`.

Host options (any works — it's a stateless single container):
Google Cloud Run, Fly.io, Railway, Render, an EC2/Fargate task. Cloud Run is
the closest match to the UAC setup.

**Health check:** point the platform's probe at `GET /health`.

## 2. Backend — environment variables

Set in the hosting platform (never commit real values):

| Var | Needed | Notes |
|---|---|---|
| `FRED_API_KEY` | for live data | Without it the API serves the synthetic fixture — fine for a demo, misleading for a real deployment. |
| `SESSION_TOKEN_BUDGET` | optional | Defaults to 50000. This is a **per-process** budget today (module-level singleton in `cost_tracker.py`), not per-user — see "Known gaps". |
| `CORS_ALLOWED_ORIGINS` | **yes** | Must list the deployed frontend's exact origin, e.g. `https://econ-data.example.com`. Comma-separated, no trailing slash. The default only covers `localhost:5173`. |
| `FRED_OFFLINE` | optional | Set `0` in prod to be explicit that you expect live data (so a missing key fails loudly rather than silently serving fixtures). |
| `AUDIT_LOG_PATH` | optional | Defaults to `audit.log` in the working dir. On a read-only or ephemeral container filesystem, point it at `/tmp/audit.log` or a mounted volume, or it will be lost on restart. |

`CACHE_PATH` is left at `:memory:` — the FRED cache is per-process and resets
on deploy. That's acceptable (FRED data for a closed window is immutable and
re-fetching is cheap); set it to a mounted file only if you want the cache to
survive restarts.

## 3. Frontend — build + host

- **`frontend/Dockerfile`** (multi-stage: `node:20` → `npm ci && npm run build`
  → copy `dist/` into `nginx:alpine`), **or** just deploy `dist/` to any
  static host (Cloudflare Pages, Netlify, Vercel, S3 + CloudFront, Firebase
  Hosting, GitHub Pages).
- **`VITE_API_BASE_URL`** is read at **build time**, not runtime — set it in
  the build environment (e.g. `VITE_API_BASE_URL=https://api.econ-data.example.com npm run build`)
  or the platform's build-env settings. Rebuild to change it.
- If you host the frontend behind nginx, add an SPA fallback
  (`try_files $uri /index.html;`) — not strictly needed now (no client-side
  routing) but standard.
- Consider `build.rollupOptions.output.manualChunks` to split the ~540 KB
  bundle (mostly recharts); cosmetic, not blocking.

## 4. Wiring the two together

1. Deploy the backend, note its URL.
2. Build the frontend with `VITE_API_BASE_URL` = that URL, deploy it, note
   its URL.
3. Set the backend's `CORS_ALLOWED_ORIGINS` to the frontend URL, redeploy the
   backend (or set it before step 1 if you know the domain).
4. Confirm: open the frontend, check the sidebar shows "API up", run a search.

Frontend and backend on **different domains** means the browser sends
cross-origin requests — that's why `CORS_ALLOWED_ORIGINS` matters. The API
uses no cookies (`allow_credentials=False`), so there's no third-party-cookie
problem; a stale/missing CORS origin just makes every call fail in the
browser (curl still works, which is a useful way to tell the two apart).

## 5. Known gaps to close before real traffic

- **No auth / no rate limiting on the HTTP surface.** `src/rate_limit.py`
  guards the *MCP* boundary only; `backend/app` has neither. A public
  deployment needs at least an API key check or a reverse-proxy rate limit,
  or it's an open proxy to your FRED key. (The MCP server's
  `rate_limit.guard` could be lifted into a FastAPI dependency — same
  token-bucket, keyed on client IP or an API key.)
- **The token budget is process-global.** One busy client can exhaust it for
  everyone until the process restarts. For multi-user hosting, key the budget
  by session/API-key instead of the module-level singleton (there's a
  `# TODO`-style note to this effect already in `cost_tracker.py`).
- **`FRED_API_KEY` in error text.** `audit_log.py` already redacts it; spot-
  check that a forced upstream error (e.g. an invalid key) doesn't echo the
  key in a 502 body before going public.
- **Observability.** No structured logging / tracing on the API yet. Add
  request logging middleware and (optionally) something like OpenTelemetry if
  this needs to be operable.
- **CI doesn't deploy.** The `frontend` CI job builds but publishes nothing;
  add a deploy workflow (gated on `main`) once the hosting target is chosen.
