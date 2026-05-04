# Current Project State

Image Insight has a FastAPI backend with `/health`, `POST /scan-folder`, `/scan-status/{scan_id}`, `/scan-sessions`, `/scan-sessions/{scan_id}`, `/photos`, `/photos/search`, and `/stats`. `POST /scan-folder` starts a lightweight Python-thread background scan job and returns `scan_id` quickly while `/scan-status/{scan_id}` exposes live persisted counters and elapsed time for polling. `GET /scan-sessions` serves recent scan history with folder path, status, timestamps, elapsed seconds, counters, last error, optional folder filtering, and a safe `limit` parameter. Scan jobs still create durable scan session records in SQLite and support `resume=true` for the latest failed or interrupted scan on the same folder. Resumed scans reuse the same `scan_id`, preserve committed session-file state, skip already committed file work when possible, and still count unchanged files as `skipped_files` rather than `updated_files`. Duplicate running scans for the same folder are rejected unless `resume=true` is attaching to the existing running session. Scans extract best-effort EXIF metadata for camera make/model, lens model, focal length, ISO, aperture, shutter speed, and capture date while allowing missing or unreadable EXIF to scan cleanly. `/photos/search` filters the existing SQLite `photos` table by camera model, lens model, focal length range, capture date range, extension, limit, and offset, and returns `total_count` plus paginated results. Scans stream directly over the recursive folder walk, upsert records into SQLite at the repo-root `image_insight.db`, commit writes every 500 matched image files, and print progress counters to the terminal during long runs. A lightweight pytest suite covers health, stats, EXIF extraction, scan history response/limit behavior, metadata search filtering, invalid search ranges, background scan start/status polling, duplicate running scan prevention, failed/interrupted resume flows, and unchanged-after-resume skip behavior against a temporary SQLite database. The React/Vite dashboard fetches `/stats`, includes a localStorage-backed Customize Dashboard panel for summary cards, EXIF cards, and charts, shows summary and EXIF insight cards when enabled, displays Recharts charts when enabled, includes a compact metadata search/filter panel with a results table, shows a recent scan history table with rerun/resume actions, starts scans without holding the request open, polls `/scan-status/{scan_id}` every 2 seconds while running, shows live counters, refreshes stats after completion, and offers a calm resume action when the last scan did not complete cleanly.

# Files Changed This Session

- Modified `frontend/src/App.tsx` to add localStorage-backed dashboard preferences for summary cards, EXIF cards, and charts.
- Modified `frontend/src/styles.css` to style the Customize Dashboard panel and toggles.
- Modified `README.md` and `docs/progress.md`.

# Decisions Made

- Keep SQLite and the current scan session tables; use a simple daemon `threading.Thread` per started scan job.
- Make `POST /scan-folder` return quickly with `scan_id`; expose live progress through `/scan-status/{scan_id}`.
- Keep v0.6.0 dashboard customization frontend-only; preferences are stored in browser `localStorage` and default all configurable dashboard sections to visible.
- Keep `/scan-sessions` as the scan history source; default history limit is 25 and requested limits above 100 are capped at 100.
- Keep metadata search as a read-only query over the existing `photos` table; do not add new storage or change scan behavior.
- Use optional query params for `/photos/search` and return `total_count`, `limit`, `offset`, and `results` for simple pagination.
- Default `/photos/search` to `limit=50` and `offset=0`; cap requested limits above 500 to 500 so the endpoint cannot accidentally return an entire large library in one response.
- Return clean HTTP 400 errors for invalid date values, reversed date ranges, reversed focal-length ranges, negative offsets, and non-positive limits.
- Use Pillow for best-effort EXIF extraction during scans; EXIF parse failures return null metadata instead of failing the file or scan.
- Store capture date as UTC because EXIF dates often lack timezone information.
- Add a small startup SQLite column check for the new nullable `photos` EXIF columns because the project does not have migrations yet.
- Keep `/stats` as the dashboard data source for EXIF analytics instead of adding a separate analytics endpoint.
- Use `pytest.ini` with `pythonpath = .` plus backend CI `PYTHONPATH=.` instead of editable package installation because the project does not yet have Python packaging metadata.
- Pin backend CI to Python 3.12 instead of floating `3.x` so CI does not jump to the newest interpreter before dependencies publish wheels.
- Reuse the same `scan_id` when resuming the latest failed or interrupted scan for a folder.
- Track processed file paths per scan session so resumed scans can skip already committed file work.
- Reset per-run counters when resuming, while preserving the session record and previous stop reason.
- Keep batch commits at every 500 matched image files so both photo data and scan-session progress become visible during long scans.
- Reject duplicate running scans for the same folder with HTTP 409; `resume=true` on a running session returns the existing `scan_id`.
- Keep the frontend as a single dashboard component for now and surface resume controls inline with the scan form.

# Known Issues / Risks

- Local folder scanning from a browser-triggered request assumes the backend can access the same filesystem path.
- Background scan jobs run in-process, so they are intentionally lightweight and will not survive a backend process restart.
- Resume currently reuses the latest resumable session for a folder rather than supporting multiple parallel in-flight scans for the same path.
- The frontend production bundle still triggers Vite's 500 kB chunk-size warning because the dashboard ships Recharts in a single main bundle.
- EXIF capture dates are interpreted as UTC when the image does not provide timezone data.

# Next Best Task

Add filtering or pagination controls to scan history if recent scans grow beyond the compact table.

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
- 2026-05-04: Added v0.2.0 EXIF analytics with camera/lens/focal length metadata, capture timeline stats, dashboard insight cards, and camera/lens/timeline charts.
- 2026-05-04: Updated backend CI to install Ubuntu JPEG/zlib development libraries before Python dependencies so Pillow can build when wheels are unavailable.
- 2026-05-04: Added pytest repo-root import configuration, backend CI `PYTHONPATH=.`, and Python 3.12 pin to fix `ModuleNotFoundError: No module named 'app'` and avoid latest-Python dependency churn.
- 2026-05-04: Ran branch stability checks: backend pytest passes locally, frontend production build passes, and `git diff --check` reports no whitespace errors.
- 2026-05-04: Added v0.3.0 background scan jobs with `POST /scan-folder`, `/scan-status/{scan_id}`, frontend polling, live counters, and duplicate running scan prevention.
- 2026-05-04: Added v0.4.0 metadata search with `/photos/search`, backend filter tests, dashboard filter controls, and a simple results table.
- 2026-05-04: Tightened `/photos/search` pagination safety with default `limit=50`, max cap 500, default `offset=0`, negative pagination errors, total-count response checks, and frontend requests capped below 500.
- 2026-05-04: Re-ran local CI-equivalent checks for backend tests, frontend build, diff hygiene, generated-file status, search defaults, no-results UI, and docs alignment.
- 2026-05-04: Added v0.5.0 scan history with `/scan-sessions` elapsed-time and limit support plus a dashboard history table with rerun/resume actions.
- 2026-05-04: Tightened scan history resume actions so the frontend only shows Resume for failed or interrupted scans.
- 2026-05-04: Added v0.6.0 custom dashboard controls with localStorage persistence for summary cards, EXIF cards, and charts.
