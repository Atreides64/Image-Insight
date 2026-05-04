# Image Insight

A local-first media metadata analytics platform for analyzing and organizing existing file libraries.

## Goals

- Scan local media folders
- Extract metadata from images
- Visualize trends
- Support fragmented archives

## Planned Stack

- Python
- FastAPI
- SQLite
- React + TypeScript
- Recharts

## Quick Start

1. Start the FastAPI backend.
2. Start the Vite dashboard.
3. Scan a local photo folder from the dashboard.
4. Watch scan progress, then use stats, charts, history, and metadata search.

The dashboard expects the backend at `http://127.0.0.1:8000` unless
`VITE_API_BASE_URL` is set.

## Backend Setup

Create and activate a Python virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install backend dependencies:

```bash
pip install -r requirements.txt
```

For backend tests, install development dependencies:

```bash
pip install -r requirements-dev.txt
```

Run the API:

```bash
uvicorn app.main:app --reload
```

The backend creates a local SQLite database at the repo root as `image_insight.db` automatically.

Image Insight extracts EXIF metadata when it is available and stores
camera make/model, lens model, focal length, ISO, aperture, shutter speed, and
capture date. Missing or unreadable EXIF data is ignored so scans can continue.
If the `exiftool` command is available on your PATH, Image Insight uses it first
for stronger metadata support across RAW/DNG/RAF files, then falls back to
Pillow for any missing fields or when ExifTool is not installed.

Optional ExifTool install:

- Windows: download the Windows executable archive from the official ExifTool
  site, unzip it, rename `exiftool(-k).exe` to `exiftool.exe`, and put it and
  its `exiftool_files` folder somewhere on your PATH.
- macOS with Homebrew: run `brew install exiftool`.
- macOS package installer: download the official macOS package from ExifTool;
  it installs the command-line tool into `/usr/local/bin`.

Verify installation:

```bash
exiftool -ver
```

`POST /scan-folder` starts a lightweight background scan job and returns a
`scan_id` quickly. The scan continues in a Python thread and writes progress to
the existing SQLite scan session record.

Scans stream directly over `Path.rglob("*")`, commit database changes every 500
matched image files, and treat unchanged existing rows as `skipped_files`
instead of `updated_files`.

Use `force_metadata=true` to refresh EXIF metadata for unchanged files. This is
intended for backfilling older rows after metadata extraction improves; it only
fills missing EXIF fields with newly extracted values and counts those rows as
`updated_files`.

Use `POST /scan-sessions/{scan_id}/cancel` to request cancellation for a running
scan. Cancellation is tracked in memory, so the active scan loop stops early,
commits the latest counters, and stores the terminal status as `cancelled`.

Use `resume=true` to resume the latest failed or interrupted scan session for
the same folder without redoing already committed file work unnecessarily.
Starting a second scan for the same folder while one is already running returns
a conflict instead of creating duplicate work.

Start a scan:

```bash
curl -X POST "http://127.0.0.1:8000/scan-folder?folder_path=/path/to/photos"
```

Refresh missing EXIF metadata on unchanged files:

```bash
curl -X POST "http://127.0.0.1:8000/scan-folder?folder_path=/path/to/photos&force_metadata=true"
```

Cancel a running scan:

```bash
curl -X POST "http://127.0.0.1:8000/scan-sessions/1/cancel"
```

Poll scan progress:

```bash
curl "http://127.0.0.1:8000/scan-status/1"
```

`GET /scan-status/{scan_id}` returns:

- `scan_id`
- `status`
- `folder_path`
- `files_seen`
- `image_files_matched`
- `new_files`
- `updated_files`
- `skipped_files`
- `failed_files`
- `elapsed_seconds`
- `scan_speed_files_per_second`
- `force_metadata`
- `exiftool_available`
- `last_error`

Scan session endpoints:

- `GET /scan-sessions`
- `GET /scan-sessions?folder_path=/path/to/folder`
- `GET /scan-sessions?limit=25`
- `GET /scan-sessions/{scan_id}`
- `GET /scan-status/{scan_id}`

`GET /scan-sessions` returns recent scan history with folder path, status,
start/completion timestamps, elapsed seconds, counters, and any last error.
The optional `limit` parameter defaults to 25 and is capped at 100.

System visibility is available from `GET /system-info` and includes app
version, SQLite database path, indexed photo count, scan session count, and
ExifTool detection.

Stats are available from `GET /stats` and include:

- Library totals and file type counts
- Top cameras, lenses, and focal lengths
- Photos by year and month
- Busiest capture date when EXIF dates are available

Search indexed photo metadata with `GET /photos/search`. Filters are optional
and can be combined:

- `camera_model`
- `lens_model`
- `min_focal_length`
- `max_focal_length`
- `date_from`
- `date_to`
- `extension`
- `limit`
- `offset`

Example:

```bash
curl "http://127.0.0.1:8000/photos/search?camera_model=EOS&min_focal_length=24&max_focal_length=85"
```

The response includes `total_count`, `limit`, `offset`, and `results` for
simple pagination. Search defaults to `limit=50` and `offset=0`; requested
limits above 500 are capped at 500, and negative pagination values return a
clean `400` response.

Then open:

- API health check: `http://127.0.0.1:8000/health`
- Interactive API docs: `http://127.0.0.1:8000/docs`

Run backend tests:

```bash
pytest
```

## Frontend Setup

The React dashboard lives in `frontend/` and uses Vite.

Install frontend dependencies:

```bash
cd frontend
npm install
```

Run the frontend:

```bash
npm run dev
```

Then open:

- Dashboard: `http://127.0.0.1:5173`

By default, the frontend fetches the FastAPI backend at `http://127.0.0.1:8000`.
To point it somewhere else, create `frontend/.env.local`:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

The dashboard includes a local "Customize Dashboard" panel. Users can toggle
individual cards, charts, search/history sections, and the file type table, and
those preferences are saved in browser `localStorage` on that device.
The dashboard also includes a System Info panel, clearer empty states before
data exists, scan-state messages for running/completed/failed/cancelled/
interrupted scans, and copy actions for the database path and search result
file paths.

## Status

v0.9.0 focuses on stability and UX polish on top of the v0.8 scan,
ExifTool, metadata backfill, cancellation, and system-info work. Duplicates,
maps, open-in-folder, previews, scan groups, archive scanning, desktop
packaging, cloud integrations, and external job services remain future work.
