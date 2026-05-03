# Current Project State

Image Insight has a FastAPI backend with `/health`, `/scan-folder`, `/photos`, and `/stats`. `/scan-folder` returns a concise summary by default with totals, counts, elapsed time, and folder path, and only includes the full file list when `include_files=true`. Scans recursively find supported image files, upsert records into SQLite, and print progress to the terminal. A lightweight pytest suite covers `/health`, `/stats`, and `/scan-folder` against a temporary SQLite database, tracked Python bytecode has been removed from git while `__pycache__/` remains ignored, and GitHub Actions now runs backend tests plus a frontend build on push and pull request. The React/Vite dashboard fetches `/stats`, shows summary cards, displays a Recharts file-type bar chart, and includes a scan form that calls `/scan-folder`, shows a long-running scan spinner/message, and refreshes stats when scanning completes.

# Files Changed This Session

- Modified `app/main.py` to print scan progress with `print(..., flush=True)`.
- Modified `app/database.py` to support `IMAGE_INSIGHT_DATABASE_URL`.
- Modified `frontend/src/App.tsx` to add the scan form, scan state, stats refresh, GB formatting, and Recharts chart.
- Modified `frontend/src/styles.css` to support the dark dashboard, chart, scan form, and scan spinner state.
- Modified `README.md` with backend test instructions and scan response behavior.
- Modified `AGENTS.md` and `docs/progress.md`.
- Added `.github/workflows/ci.yml`.
- Added `requirements-dev.txt`.
- Added `tests/test_api.py`.
- Deleted tracked `app/__pycache__/__init__.cpython-313.pyc`.
- Deleted tracked `app/__pycache__/main.cpython-313.pyc`.
- Added/updated frontend dependency metadata including `frontend/package-lock.json`.

# Decisions Made

- Use plain terminal prints for scan progress instead of the logging module.
- Keep the frontend as a single dashboard component for now.
- Use Recharts for file type visualization.
- Keep SQLite and automatic table creation for the early MVP.
- Use `IMAGE_INSIGHT_DATABASE_URL` so tests can run without touching the local development database.
- Remove tracked bytecode from git and rely on `.gitignore` for regenerated local `.pyc` files.
- Return concise scan summaries by default and keep full file payloads optional.
- Use separate backend and frontend CI jobs so failures are isolated and caching stays simple.
- Show clear long-running scan feedback in the frontend instead of leaving the form visually idle.

# Known Issues / Risks

- The frontend build still has not been verified in this Codex environment because `npm` was not available on PATH during earlier checks, though CI now runs `npm run build`.
- Local folder scanning from a browser-triggered request assumes the backend can access the same filesystem path.

# Next Best Task

Push the branch and confirm the new GitHub Actions workflow passes for both backend and frontend jobs.

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
- 2026-05-03: Added backend pytest suite with temporary SQLite coverage for health, stats, and folder scanning.
- 2026-05-03: Added GitHub Actions CI for backend pytest and frontend Vite build on push and pull request.
- 2026-05-03: Added agent/project documentation and captured current backend/frontend progress.
