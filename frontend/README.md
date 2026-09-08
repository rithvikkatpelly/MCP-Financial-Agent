# Econ Data frontend (`frontend/`)

Minimal React + Vite + TypeScript UI that calls the FastAPI backend
(`backend/app`) over HTTP — one page, a sidebar to switch between the four
FRED tools, a recharts line chart + raw table per result.

```bash
cd frontend
npm install
cp .env.example .env      # VITE_API_BASE_URL, defaults to http://127.0.0.1:8000
npm run dev               # http://localhost:5173
```

The backend must be running (`cd backend && uvicorn app.main:app --reload`)
and its `CORS_ALLOWED_ORIGINS` must include the frontend's origin — the
default already lists `http://localhost:5173`.

```
src/
  api/client.ts   fetch wrapper + one function per endpoint
  api/types.ts     mirrors backend/app/schemas.py
  components/       one panel per tool + shared chart/table/error pieces
  App.tsx          sidebar + active panel + API health check
```

`npm run build` type-checks (`tsc -b`) and bundles to `dist/`.

## Docker

```bash
docker build -f frontend/Dockerfile \
  --build-arg VITE_API_BASE_URL=https://your-api.example.com \
  -t econ-data-frontend ./frontend
```

`VITE_API_BASE_URL` is inlined at build time. Multi-stage: Vite build →
nginx (`nginx.conf`). Or just deploy `dist/` to any static host. Full notes:
[`../DEPLOYMENT.md`](../DEPLOYMENT.md).
