# Current Project State

Image Insight has a FastAPI backend with `/health`, `/scan-folder`, `/scan-sessions`, `/scan-sessions/{scan_id}`, `/photos`, and `/stats`. `/scan-folder` still returns a concise summary by default, creates durable scan session records in SQLite, and supports `resume=true` for the latest failed or interrupted scan on the same folder. Scans now extract best-effort EXIF metadata for camera make/model, lens model, focal length, ISO, aperture, shutter speed, and capture date while allowing missing or unreadable EXIF to scan cleanly. Resumed scans reuse the same `scan_id`, preserve committed session state, skip already committed file work when possible, and still count unchanged files as `skipped_files` rather than `updated_files`. Scans stream directly over the recursive folder walk, upsert records into SQLite at the repo-root `image_insight.db`, commit writes every 500 matched image files, and print progress counters to the terminal during long runs. A lightweight pytest suite now covers health, stats, EXIF extraction, scan session creation, completed scans, failed/interrupted resume flows, and unchanged-after-resume skip behavior against a temporary SQLite database. The React/Vite dashboard fetches `/stats`, shows summary and EXIF insight cards, displays Recharts charts for camera usage, lens usage, capture timeline, and file types, includes a scan form that calls `/scan-folder`, shows the latest scan session state for the entered folder, and offers a calm resume action when the last scan did not complete cleanly.

# Files Changed This Session

- Modified `app/models.py` to add nullable EXIF columns on `photos`.
- Modified `app/main.py` to add best-effort Pillow EXIF extraction, lightweight SQLite column backfill for existing local databases, v0.2.0 API metadata, and EXIF analytics in `/stats`.
- Modified `tests/test_api.py` to cover EXIF extraction and the expanded stats payload.
- Modified `frontend/src/App.tsx` to add Favorite Camera, Favorite Lens, Most Used Focal Length, Busiest Date, camera/lens usage charts, and a capture timeline chart.
- Modified `frontend/src/styles.css` to support the expanded chart layout.
- Modified `requirements.txt` to add Pillow.
- Modified `.gitignore` to ignore pytest cache directories created during local test runs.
- Added `pytest.ini`, backend CI `PYTHONPATH=.`, and a Python 3.12 CI pin so CI and local pytest runs can import the repo-root `app` package consistently.
- Modified `README.md` and `docs/progress.md`.

# Decisions Made

- Keep `/scan-folder` synchronous for now, but persist each scan as a durable session record with resumable states.
- Use Pillow for best-effort EXIF extraction during scans; EXIF parse failures return null metadata instead of failing the file or scan.
- Store capture date as UTC because EXIF dates often lack timezone information.
- Add a small startup SQLite column check for the new nullable `photos` EXIF columns because the project does not have migrations yet.
- Keep `/stats` as the dashboard data source for v0.2.0 analytics instead of adding a separate analytics endpoint.
- Use `pytest.ini` with `pythonpath = .` plus backend CI `PYTHONPATH=.` instead of editable package installation because the project does not yet have Python packaging metadata.
- Pin backend CI to Python 3.12 instead of floating `3.x` so CI does not jump to the newest interpreter before dependencies publish wheels.
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
- EXIF capture dates are interpreted as UTC when the image does not provide timezone data.

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
- 2026-05-04: Added v0.2.0 EXIF analytics with camera/lens/focal length metadata, capture timeline stats, dashboard insight cards, and camera/lens/timeline charts.
- 2026-05-04: Updated backend CI to install Ubuntu JPEG/zlib development libraries before Python dependencies so Pillow can build when wheels are unavailable.
- 2026-05-04: Added pytest repo-root import configuration, backend CI `PYTHONPATH=.`, and Python 3.12 pin to fix `ModuleNotFoundError: No module named 'app'` and avoid latest-Python dependency churn.
- 2026-05-04: Ran branch stability checks: backend pytest passes locally, frontend production build passes, and `git diff --check` reports no whitespace errors.
