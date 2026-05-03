# Current Project State

Image Insight has a FastAPI backend with `/health`, `/scan-folder`, `/scan-sessions`, `/scan-sessions/{scan_id}`, `/photos`, and `/stats`. `/scan-folder` still returns a concise summary by default, but now also creates durable scan session records in SQLite and supports `resume=true` for the latest failed or interrupted scan on the same folder. Resumed scans reuse the same `scan_id`, preserve committed session state, skip already committed file work when possible, and still count unchanged files as `skipped_files` rather than `updated_files`. Scans stream directly over the recursive folder walk, upsert records into SQLite at the repo-root `image_insight.db`, commit writes every 500 matched image files, and print progress counters to the terminal during long runs. A lightweight pytest suite now covers health, stats, scan session creation, completed scans, failed/interrupted resume flows, and unchanged-after-resume skip behavior against a temporary SQLite database. The React/Vite dashboard fetches `/stats`, shows summary cards, displays a Recharts file-type bar chart, includes a scan form that calls `/scan-folder`, shows the latest scan session state for the entered folder, and offers a calm resume action when the last scan did not complete cleanly.

# Files Changed This Session

- Modified `app/main.py` to add durable scan session tracking, resume support, and `/scan-sessions` endpoints while keeping `/scan-folder` backward compatible.
- Modified `app/models.py` to add `scan_sessions` and `scan_session_files` tables.
- Modified `tests/test_api.py` to cover scan session creation, completed scans, failed/interrupted resume flows, and unchanged-after-resume skip behavior.
- Modified `frontend/src/App.tsx` to show the latest scan session for the entered folder and offer a resume action when the last scan was interrupted or failed.
- Modified `frontend/src/styles.css` to style the previous scan status panel and resume button.
- Modified `README.md` and `docs/progress.md`.

# Decisions Made

- Keep `/scan-folder` synchronous for now, but persist each scan as a durable session record with resumable states.
- Reuse the same `scan_id` when resuming the latest failed or interrupted scan for a folder.
- Track processed file paths per scan session so resumed scans can skip already committed file work.
- Reset per-run counters when resuming, while preserving the session record and previous stop reason.
- Keep batch commits at every 500 matched image files so both photo data and scan-session progress become visible during long scans.
- Keep the frontend as a single dashboard component for now and surface resume controls inline with the scan form.

# Known Issues / Risks

- Local folder scanning from a browser-triggered request assumes the backend can access the same filesystem path.
- `/scan-folder` is still a single request/response flow, so very large archives can still run into browser or proxy timeout limits even though session progress is committed in batches and resume is available afterward.
- Resume currently reuses the latest resumable session for a folder rather than supporting multiple parallel in-flight scans for the same path.
- The frontend production bundle still triggers Vite's 500 kB chunk-size warning because the dashboard ships Recharts in a single main bundle.

# Next Best Task

Convert scan session progress into a lightweight background job/status flow so the frontend can show live processed counts without holding one request open for the full archive scan.

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
- 2026-05-03: Preserved streaming scan iteration, counted unchanged rescans as skipped, and surfaced failed image reads in the dashboard scan summary.
- 2026-05-03: Added resumable scan sessions, session inspection endpoints, and frontend resume controls for interrupted or failed scans.
