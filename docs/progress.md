# Current Project State

Image Insight has a FastAPI backend with `/health`, `/system-info`, `POST /scan-folder`, `/scan-status/{scan_id}`, `/scan-sessions`, `/scan-sessions/{scan_id}`, `POST /scan-sessions/{scan_id}/cancel`, `/photos`, `/photos/search`, `/photos/search-options`, and `/stats`. `/system-info` returns app version, SQLite database path, indexed photo count, scan session count, and ExifTool detection for lightweight runtime visibility. `POST /scan-folder` starts a lightweight Python-thread background scan job and returns `scan_id` quickly while `/scan-status/{scan_id}` exposes live persisted timestamps, counters, scan speed, force-metadata flag, ExifTool availability, and elapsed time for polling. Startup cleanup marks stale persisted `running` scan sessions as `interrupted`, sets `completed_at`, and records a restart interruption message so history durations stop after backend restarts. `GET /scan-sessions` serves recent scan history with folder path, status, timestamps, elapsed seconds, counters, last error, optional folder filtering, force-metadata flag, ExifTool availability, scan speed, and a safe `limit` parameter. Scan jobs still create durable scan session records in SQLite and support `resume=true` for the latest failed or interrupted scan on the same resolved folder path. Resumed scans reuse the same `scan_id`, preserve committed session-file state, skip already committed image work when possible, and still count unchanged matched images as `skipped_files` rather than `updated_files`. Duplicate running scans for the same folder are rejected unless `resume=true` is attaching to the existing running session. Running scans can be cancelled with an in-memory `POST /scan-sessions/{scan_id}/cancel` request; the scan loop exits early, commits progress, and stores `cancelled` as a terminal status. Scans extract best-effort EXIF metadata for camera make/model, lens model, focal length, ISO, aperture, shutter speed, and capture date while allowing missing or unreadable EXIF to scan cleanly. If `exiftool` is available on PATH, scans use ExifTool JSON metadata first for stronger RAW/DNG/RAF support, then fall back to Pillow for unavailable fields or when ExifTool is not installed. `POST /scan-folder?force_metadata=true` re-runs EXIF extraction for unchanged files and only backfills missing EXIF fields with newly populated values. EXIF focal-length parsing handles Pillow rationals, tuple fractions, numbers, and common string forms, and lens labels fall back from LensModel to LensMake plus LensSpecification when available. `/photos/search` filters the existing SQLite `photos` table by camera/make model text, lens model, focal length range, capture date range, extension, ISO, aperture, shutter speed, device type, limit, and offset, and returns `total_count` plus paginated results. `/photos/search-options` returns capped distinct metadata values for search autocomplete/dropdowns. `/stats` includes v1.2 default insight fields for average file size, storage by file type, average file size by file type, RAW/JPEG split, phone/camera/unknown counts, most common ISO/aperture/shutter speed, average file size by camera, camera/lens usage timelines, capture-date coverage, and `photo_timeline`, a monthly capture-date insight series that only uses `date_taken` rows with at least one credible capture metadata field and includes top camera/lens labels for tooltips. Camera type classification is derived from make/model heuristics and does not overwrite stored EXIF camera fields. Scans stream directly over the recursive folder walk, upsert records into SQLite at the repo-root `image_insight.db`, count non-image files in `files_seen` but not `skipped_files`, commit visible progress every 500 files seen or 500 matched image files, and print progress counters and folder diagnostics to the terminal during long runs. A lightweight pytest suite covers health, system info, stats, EXIF extraction, mocked ExifTool availability/output, mocked EXIF focal/lens parsing, forced metadata backfill, scan cancellation, scan history response/limit behavior, metadata search filtering, metadata search options, invalid search ranges, background scan start/status polling, duplicate running scan prevention, startup cleanup of stale running sessions, mixed JPG/RAF scan counts, failed/interrupted resume flows, unchanged-after-resume skip behavior, credible capture metadata timeline stats, v1.2 default stats, device classification, and timeline insight stats against a temporary SQLite database. The React/Vite dashboard uses a colorful v1.2 visual system with varied insight gradients, top-level Scan Library and Metadata Search cards, a two-column desktop insight module grid, compact file-type cards, compact default insight cards, blue/cyan Scan Library theming, and purple Metadata Search theming. Metadata Search remains a focused tool card with autocomplete/dropdowns for scanned metadata values, Settings contains System Info and Customize Dashboard, and Insights shows stats/charts when indexed data exists. Capture Timeline only includes files with EXIF capture dates plus credible capture metadata and is hidden when there is no capture-date timeline data.

# Files Changed This Session

- Modified `app/main.py` to add `force_metadata=true` scan backfills for missing EXIF fields on unchanged files while preserving normal skip behavior.
- Modified `app/main.py` to add in-memory scan cancellation with `POST /scan-sessions/{scan_id}/cancel` and persisted `cancelled` terminal status.
- Modified `app/main.py` and `app/models.py` to add v0.8.0 system visibility, scan speed, ExifTool availability, and persisted scan `force_metadata` flag.
- Modified `frontend/src/App.tsx` and `frontend/src/styles.css` to add a System Info panel, Refresh metadata checkbox, ExifTool/backfill scan indicators, scan speed, active scan errors, and active scan cancellation button.
- Modified `frontend/src/App.tsx` and `frontend/src/styles.css` to refactor the dashboard into Header, Insights, and Tools sections, with scan/search/history opened from clickable tool cards.
- Modified `frontend/src/App.tsx` to make the Scan Folder, Metadata Search, and Scan History tool cards toggle their corresponding panels while collapsing inactive tools.
- Modified `frontend/src/App.tsx` and `frontend/src/styles.css` to polish the v1.0 tool-card UI with feature-specific gradients, CSS visual accents, stronger hover/focus states, a more prominent IMAGE INSIGHT header, and a first-run scan onboarding state.
- Modified `frontend/src/App.tsx` and `frontend/src/styles.css` to refine v1.0 branding to blue/cyan/violet, consolidate Scan Folder and Scan History into Scan Library, add rescan safety choices, add quick shortcuts, and clarify the capture timeline.
- Modified `frontend/src/App.tsx` to restore the Metadata Search Copy Path action with clipboard copied-state handling.
- Modified `app/main.py`, `frontend/src/App.tsx`, and `frontend/src/styles.css` to prepare v1.1 Scan Library UX with clearer New Scan hierarchy, local scan timestamps, Start/Cancel primary action behavior, compact metric boxes, info tooltips, and fresher live polling counters.
- Modified `app/main.py` and `tests/test_api.py` to mark stale running sessions interrupted on startup, correct skip-count semantics for non-image files, add scan diagnostics, and cover mixed JPG/RAF counts.
- Modified `frontend/src/App.tsx` and `frontend/src/styles.css` to move Scan Library and Metadata Search cards to the top of the dashboard, remove the shortcut row, replace CSS-shape icons with SVG scan/search icons, and consolidate scan help into one info popover.
- Modified `frontend/src/App.tsx` and `frontend/src/styles.css` for v1.2 dashboard visual polish with a two-column insight module grid, compact file-type cards, varied gradients, chart margin fixes, colored expanded tool themes, and clearer capture-date-only timeline copy.
- Modified `tests/test_api.py` to assert timeline stats exclude photos without `date_taken` instead of falling back to modified dates.
- Modified `app/main.py`, `frontend/src/App.tsx`, and `frontend/src/styles.css` to add v1.2 default insight stats/cards for file size, storage, RAW/JPEG, device type, common exposure settings, camera average file size, and capture-date coverage.
- Modified `tests/test_api.py` to cover v1.2 stats fields and phone/camera/unknown classification heuristics.
- Modified `app/main.py`, `frontend/src/App.tsx`, and `frontend/src/styles.css` to tighten Capture Timeline validity, expand metadata search filters, add search options, add the average file size by type chart, improve search dropdown/autocomplete usability, remove the duplicate File Type Counts module, and reduce camera/lens chart label clutter.
- Modified `tests/test_api.py` to cover credible capture metadata timeline filtering, expanded metadata search filters, and search option values.
- Modified `tests/test_api.py` to cover system info, forced backfill of previously null lens/focal-length metadata, cancellation of a running scan, and expanded scan session fields.
- Modified `AGENTS.md` to fix stale scan-status wording, the `photo_timeline` endpoint reference, and pytest capitalization.
- Modified `README.md`, `AGENTS.md`, and `docs/progress.md`.

# Decisions Made

- Keep SQLite and the current scan session tables; use a simple daemon `threading.Thread` per started scan job.
- Make `POST /scan-folder` return quickly with `scan_id`; expose live progress through `/scan-status/{scan_id}`.
- Keep v0.6.0 dashboard customization frontend-only; preferences are stored in browser `localStorage` and default all configurable dashboard sections to visible.
- For v0.7.0, keep scan behavior unchanged and add only a focused `/stats.photo_timeline` field because the timeline tooltip needs top camera/lens context that the existing monthly counts did not include.
- Keep dashboard preferences local to the browser and default every individual card, chart, and optional section to visible.
- Keep `/scan-sessions` as the scan history source; default history limit is 25 and requested limits above 100 are capped at 100.
- Keep metadata search as a read-only query over the existing `photos` table; do not add new storage or change scan behavior.
- Use optional query params for `/photos/search` and return `total_count`, `limit`, `offset`, and `results` for simple pagination.
- Default `/photos/search` to `limit=50` and `offset=0`; cap requested limits above 500 to 500 so the endpoint cannot accidentally return an entire large library in one response.
- Return clean HTTP 400 errors for invalid date values, reversed date ranges, reversed focal-length ranges, negative offsets, and non-positive limits.
- Use Pillow for best-effort EXIF extraction during scans; EXIF parse failures return null metadata instead of failing the file or scan.
- Treat EXIF text value `"0"` as unavailable for user-facing metadata, because some camera/lens tags surface missing values that way.
- Parse focal length through a shared rational parser so IFDRational, tuple fractions, numbers, and strings all normalize to positive floats.
- Build fallback lens labels from LensMake plus LensSpecification when LensModel is missing or unusable.
- Keep ExifTool optional; detect it with `shutil.which("exiftool")`, parse `exiftool -json -n` safely, and never require it in CI.
- Preserve Pillow as the fallback metadata extractor so scans still work without external tools.
- Keep forced metadata refresh conservative: unchanged files only count as updated when a missing EXIF field is filled with a newly extracted value.
- Keep cancellation state in memory only; the worker persists final scan progress and `cancelled` status when it observes the request.
- Keep v0.8.0 polish minimal: expose runtime visibility and scan context without changing scan behavior or adding persistent cancellation state.
- Keep the scan, search, and history components in the dashboard, but expose Scan Library and Metadata Search through top-level tool cards directly below the header.
- Tool cards are always visible and act as expand/collapse controls; selecting one tool unmounts the inactive tool panels.
- Use lightweight CSS gradients and shape accents for v1.0 tool-card polish rather than adding icon libraries or changing frontend architecture.
- Keep light mode out of the v1.0 polish pass so the brand/color refactor and rescan safety work stay focused.
- Treat rerun/resume buttons as explicit scan actions, while normal folder-form submissions warn before rescanning a previously scanned directory.
- Store capture date as UTC because EXIF dates often lack timezone information.
- Add a small startup SQLite column check for the new nullable `photos` EXIF columns because the project does not have migrations yet.
- Keep `/stats` as the dashboard data source for EXIF analytics instead of adding a separate analytics endpoint.
- Use `pytest.ini` with `pythonpath = .` plus backend CI `PYTHONPATH=.` instead of editable package installation because the project does not yet have Python packaging metadata.
- Pin backend CI to Python 3.12 instead of floating `3.x` so CI does not jump to the newest interpreter before dependencies publish wheels.
- Reuse the same `scan_id` when resuming the latest failed or interrupted scan for a folder.
- Track processed file paths per scan session so resumed scans can skip already committed file work.
- Reset per-run counters when resuming, while preserving the session record and previous stop reason.
- Keep batch commits at every 500 matched image files and visible progress commits every 500 files seen so folders with many non-image/archive files do not appear stuck while polling.
- On backend startup, stale `running` sessions are marked `interrupted` with `completed_at` set so elapsed time stops and the frontend can offer Resume.
- `skipped_files` means matched images that were unchanged or already processed during resume; non-image files count in `files_seen` only.
- Capture Timeline and `photo_timeline` use only `date_taken` plus at least one credible capture metadata field; files without capture metadata are excluded rather than falling back to modified or folder dates.
- Camera type stats classify make/model text as `phone`, `camera`, or `unknown` without changing stored EXIF fields.
- Reject duplicate running scans for the same folder with HTTP 409; `resume=true` on a running session returns the existing `scan_id`.
- Keep the frontend as a single dashboard component for now and surface resume controls inline with the scan form.

# Known Issues / Risks

- Local folder scanning from a browser-triggered request assumes the backend can access the same filesystem path.
- Background scan jobs run in-process, so they are intentionally lightweight and will not survive a backend process restart.
- Resume currently reuses the latest resumable session for a folder rather than supporting multiple parallel in-flight scans for the same path.
- The frontend production bundle still triggers Vite's 500 kB chunk-size warning because the dashboard ships Recharts in a single main bundle.
- EXIF capture dates are interpreted as UTC when the image does not provide timezone data.
- ZIP/archive files are counted in `files_seen` but not `skipped_files`, and are not scanned inside yet.
- Network drives may scan slower than local drives, especially when Refresh metadata re-reads EXIF for already indexed files.

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
- 2026-05-04: Added v0.7.0 dashboard UX cleanup with compact stat cards, per-card/per-section localStorage preferences, and a richer photo timeline insight chart.
- 2026-05-04: Fixed EXIF lens and focal-length extraction with robust rational/string parsing, LensMake/LensSpecification fallbacks, and mocked EXIF tests.
- 2026-05-04: Added optional ExifTool metadata extraction ahead of the Pillow fallback, with mocked ExifTool tests and README install notes.
- 2026-05-04: Added forced metadata backfill scans with `force_metadata=true`, a frontend Refresh metadata checkbox, and regression coverage for filling previously null lens/focal-length fields.
- 2026-05-04: Added v0.7.2 scan cancellation with an in-memory cancel request endpoint, persisted `cancelled` terminal status, dashboard Cancel Scan action, and regression coverage.
- 2026-05-04: Added v0.8.0 polish with `/system-info`, dashboard System Info, scan speed, ExifTool/backfill indicators, active scan error visibility, and persisted scan `force_metadata` flag.
- 2026-05-04: Corrected `AGENTS.md` wording for `/scan-status`, `/stats.photo_timeline`, and pytest.
- 2026-05-04: Refactored the frontend layout into Header, Insights, and Tools sections, with existing scan/search/history UI conditionally shown from tool-card selections.
- 2026-05-04: Tightened tool-card behavior so Scan Folder, Metadata Search, and Scan History each expand/collapse their panel and collapse inactive tools.
- 2026-05-04: Polished the v1.0 tool-card UI with scan/search/history gradient accents, CSS-drawn card icons, stronger header treatment, improved focus/hover states, and first-run scan onboarding.
- 2026-05-04: Refined the v1.0 dashboard redesign with blue/cyan/violet branding, Scan Library consolidation, rescan warning choices, quick shortcut navigation, and clearer capture timeline labeling.
- 2026-05-05: Reviewed `docs/progress.md`, fixed the frontend Metadata Search Copy Path TypeScript error, and confirmed backend pytest, frontend build, and diff whitespace checks pass.
- 2026-05-05: Prepared v1.1 Scan Library UX with a clearer New Scan panel, single Start/Cancel action, local running-scan timestamps, compact explained counters, collapsed history details, refresh metadata help, and polling/status updates for folders with many non-image files.
- 2026-05-05: Fixed scan count accuracy by excluding non-image files from `skipped_files`, added mixed JPG/RAF count coverage, added scan diagnostics, and marked stale `running` sessions `interrupted` on startup.
- 2026-05-05: Moved the primary Scan Library and Metadata Search cards to the top of the dashboard, removed shortcut buttons and auto-scroll behavior, added explicit SVG icons, and consolidated scan help into one concise info popover.
- 2026-05-05: Added v1.2 dashboard visual polish with a colorful two-column insight grid, compact file-type modules, chart clipping fixes, blue Scan Library theming, purple Metadata Search theming, and capture-date-only timeline wording and coverage.
- 2026-05-05: Added v1.2 default insight cards and `/stats` fields for file size, storage mix, RAW/JPEG mix, device type, common exposure settings, camera average file size, and capture-date coverage.
- 2026-05-05: Added v1.2 analytics cleanup with credible capture metadata timeline filtering, expanded metadata search filters/options, compact search dropdowns/autocomplete, the average file size by type chart, camera/lens chart label cleanup, and removal of duplicate File Type Counts.
