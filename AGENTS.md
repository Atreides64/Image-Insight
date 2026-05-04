# Image Insight Agent Notes

## Project

Image Insight is a local-first media metadata analytics app for scanning photo folders, storing image metadata, and showing library stats.

## Current Stack

- Backend: Python, FastAPI, SQLAlchemy
- Database: SQLite, created locally at the repo root as `image_insight.db`
- Frontend: React, TypeScript, Vite, Recharts
- Tooling: `pip` for backend dependencies, `pytest` for backend tests, `npm` for frontend dependencies
- CI: GitHub Actions runs backend tests and frontend build on pushes and pull requests

## Coding Standards

- Keep code simple and readable; avoid abstractions until repeated behavior needs them.
- Prefer `pathlib` for filesystem work.
- Keep API responses clean JSON with predictable keys.
- Use UTC timestamps for scan metadata.
- Keep frontend components compact until the dashboard grows enough to split.
- Preserve the dark dashboard style unless the user asks for a redesign.

## Workflow Rules

- Do not commit local databases, virtual environments, `node_modules`, build output, or Python bytecode.
- Tracked legacy bytecode files should stay removed; `__pycache__/` is ignored and should not be re-added.
- Frontend TypeScript/Vite generated files are not source and should stay ignored (`*.tsbuildinfo`, generated `vite.config.js`, generated `vite.config.d.ts`).
- Update `docs/progress.md` every session before finishing.
- Keep `AGENTS.md` current when stack, architecture, commands, or workflow rules change.
- Do not invent implemented features in docs; describe only what exists.
- If dependencies are unavailable locally, state that verification was limited.

## Architecture Decisions

- The backend creates tables at startup with `Base.metadata.create_all(bind=engine)` for now.
- The default SQLite database path is always the repo-root `image_insight.db`; tests override it with `IMAGE_INSIGHT_DATABASE_URL`.
- `/scan-folder` scans local paths provided by the user and upserts photos by unique `path`.
- `/scan-folder` returns a concise summary by default and only includes the full `files` payload when `include_files=true`.
- Scan progress is printed with `print(..., flush=True)` so terminal output appears during long scans.
- Scan counters distinguish `files_seen`, `image_files_matched`, `new_files`, `updated_files`, `skipped_files`, and `failed_files`.
- Existing rows only count as `updated_files` when file metadata actually changed; unchanged rescans count as `skipped_files`.
- Long scans commit database writes every 500 matched image files so progress is visible before the full run completes.
- The frontend fetches the backend from `VITE_API_BASE_URL`, defaulting to `http://127.0.0.1:8000`.
- CORS is enabled for the Vite dev server on `localhost:5173` and `127.0.0.1:5173`.
- Tests set `IMAGE_INSIGHT_DATABASE_URL` before importing the app so they use a temporary SQLite database.
- CI lives in `.github/workflows/ci.yml` with separate backend and frontend jobs for faster feedback.
- The backend CI job installs Ubuntu `libjpeg-dev` and `zlib1g-dev` before Python dependencies so Pillow can build if a wheel is unavailable.
- Frontend TypeScript uses `moduleResolution: "bundler"` and routes build cache/output noise into ignored paths so `npm run build` stays CI-safe.

## Common Run Commands

Backend:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend tests:

```bash
pip install -r requirements-dev.txt
pytest
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Useful URLs:

- Backend health: `http://127.0.0.1:8000/health`
- API docs: `http://127.0.0.1:8000/docs`
- Frontend dashboard: `http://127.0.0.1:5173`

## Continuing Work

Start by reading `docs/progress.md`, then inspect `git status --short`. Preserve existing user changes. The next practical work should improve the smallest useful slice, verify it locally when dependencies are available, and update this file plus `docs/progress.md` before ending.
