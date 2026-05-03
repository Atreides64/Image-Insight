# Current Project State

Image Insight has a FastAPI backend with `/health`, `/scan-folder`, `/photos`, and `/stats`. `/scan-folder` now returns a concise summary by default with `total_files`, `files_seen`, `image_files_matched`, `new_files`, `updated_files`, `skipped_files`, `failed_files`, `elapsed_seconds`, and `folder_path`, and only includes the full file list when `include_files=true`. Scans recursively find supported image files, upsert records into SQLite at the repo-root `image_insight.db`, commit writes every 500 matched image files, and print progress counters to the terminal during long runs. A lightweight pytest suite covers `/health`, `/stats`, and `/scan-folder` against a temporary SQLite database, tracked Python bytecode has been removed from git while `__pycache__/` remains ignored, and GitHub Actions runs backend tests plus a frontend build on push and pull request. The frontend TypeScript build now passes with modern Vite-compatible `bundler` resolution, and generated frontend build artifacts are no longer tracked. The React/Vite dashboard fetches `/stats`, shows summary cards, displays a Recharts file-type bar chart, and includes a scan form that calls `/scan-folder`, shows a long-running scan spinner/message, and refreshes stats when scanning completes.

# Files Changed This Session

- Modified `app/main.py` to track scan counters, print richer scan progress with `print(..., flush=True)`, and commit database updates every 500 matched image files.
- Modified `app/database.py` to use a clear repo-root SQLite path by default while still supporting `IMAGE_INSIGHT_DATABASE_URL` for tests.
- Modified `tests/test_api.py` to cover the new `/scan-folder` counter semantics.
- Modified `frontend/src/App.tsx` to add the scan form, scan state, stats refresh, GB formatting, and Recharts chart.
- Modified `frontend/src/styles.css` to support the dark dashboard, chart, scan form, and scan spinner state.
- Modified frontend TypeScript config and dependency ranges so `npm run build` passes reliably.
- Modified `README.md` with backend test instructions and scan response behavior.
- Modified `AGENTS.md` and `docs/progress.md`.
- Added `.github/workflows/ci.yml`.
- Added `requirements-dev.txt`.
- Added `tests/test_api.py`.
- Deleted tracked `app/__pycache__/__init__.cpython-313.pyc`.
- Deleted tracked `app/__pycache__/main.cpython-313.pyc`.
- Deleted tracked frontend generated artifacts: `vite.config.js`, `vite.config.d.ts`, and root-level `.tsbuildinfo` files.
- Added/updated frontend dependency metadata including `frontend/package-lock.json`.

# Decisions Made

- Use plain terminal prints for scan progress instead of the logging module.
- Distinguish scan counters between all files seen, matched image files, created rows, updated rows, skipped non-image files, and failed image reads.
- Commit scan database writes every 500 matched image files so long scans expose durable progress before the full run finishes.
- Keep the frontend as a single dashboard component for now.
- Use Recharts for file type visualization.
- Keep SQLite and automatic table creation for the early MVP.
- Use the repo-root `image_insight.db` as the one clear local database path, with `IMAGE_INSIGHT_DATABASE_URL` reserved for tests.
- Remove tracked bytecode from git and rely on `.gitignore` for regenerated local `.pyc` files.
- Return concise scan summaries by default and keep full file payloads optional.
- Use separate backend and frontend CI jobs so failures are isolated and caching stays simple.
- Show clear long-running scan feedback in the frontend instead of leaving the form visually idle.
- Pin frontend package ranges to stable semver versions taken from the current lockfile instead of `latest`.

# Known Issues / Risks

- Local folder scanning from a browser-triggered request assumes the backend can access the same filesystem path.
- `/scan-folder` is still a single request/response flow, so very large archives can still run into browser or proxy timeout limits even though commits now happen in batches.
- The frontend production bundle still triggers Vite's 500 kB chunk-size warning because the dashboard ships Recharts in a single main bundle.

# Next Best Task

Convert scan progress into a lightweight background job/status flow so the frontend can show live processed counts without holding one request open for the full archive scan.

# Quick Start

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

Open:

- API docs: `http://127.0.0.1:8000/docs`
- Dashboard: `http://127.0.0.1:5173`

# Changelog

- 2026-05-03: Removed tracked Python bytecode files from git and confirmed `.gitignore` keeps regenerated `__pycache__` files out of status.
- 2026-05-03: Changed `/scan-folder` to return a concise summary by default and made the full file list optional via `include_files=true`.
- 2026-05-03: Improved long-running scan UX with a spinner, clearer wait message, and disabled scan action during requests.
- 2026-05-03: Fixed the frontend TypeScript build, pinned frontend dependency ranges, and removed generated frontend build artifacts from git.
- 2026-05-03: Added backend pytest suite with temporary SQLite coverage for health, stats, and folder scanning.
- 2026-05-03: Added GitHub Actions CI for backend pytest and frontend Vite build on push and pull request.
- 2026-05-03: Added agent/project documentation and captured current backend/frontend progress.
- 2026-05-03: Improved `/scan-folder` scan semantics with explicit counters, repo-root SQLite visibility, and batch commits every 500 matched image files.
