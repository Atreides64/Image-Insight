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

Scans stream directly over `Path.rglob("*")`, store a resolved folder path for
the scan session, commit visible progress every 500 files seen or 500 matched
image files, and treat unchanged existing rows as `skipped_files` instead of
`updated_files`.

Scan counters use these terms:

- `files_seen`: all files inspected while walking the folder.
- `image_files_matched`: files recognized as supported image types.
- `new_files`: newly indexed images.
- `updated_files`: existing images with changed file metadata or newly
  backfilled EXIF metadata.
- `skipped_files`: matched image files that were unchanged or already handled
  while resuming a scan. ZIP/archive files are included in `files_seen` but are
  not counted as skipped images and are not scanned inside yet.
- `failed_files`: files that could not be read or processed.
- `scan_speed_files_per_second`: current processing rate based on files seen and
  elapsed scan time. Network drives may scan slower than local drives.

Use `force_metadata=true` to refresh EXIF metadata for unchanged files. Normal
scans skip unchanged files; refresh metadata re-checks EXIF for already indexed
files. This is useful after enabling ExifTool or improving metadata extraction.
It only fills missing EXIF fields with newly extracted values, counts those rows
as `updated_files`, and may take longer, especially on network drives.

Use `POST /scan-sessions/{scan_id}/cancel` to request cancellation for a running
scan. Cancellation is tracked in memory, so the active scan loop stops early,
commits the latest counters, and stores the terminal status as `cancelled`.

If the backend restarts while a scan is marked `running`, startup cleanup marks
that session `interrupted`, sets `completed_at`, and records
`Scan interrupted because the application restarted.` in `last_error`. Interrupted
sessions are terminal for elapsed-time display and can be resumed.

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
- `started_at`
- `completed_at`
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
- Average file size, storage by file type, RAW/JPEG split, and capture-date
  coverage
- Average file size by file type for the compact file-type chart
- Top cameras, lenses, and focal lengths
- Most common ISO, aperture, and shutter speed
- Average file size by camera
- Phone/camera/unknown counts from simple camera make/model heuristics
- Photos by year and month
- Busiest capture date when EXIF dates are available

Camera type classification is derived from make/model text without changing the
stored camera fields. Apple/iPhone, Pixel/Google, Samsung/SM-, LG, and Nexus are
classified as `phone`; Nikon, Canon, Fujifilm, Sony, Ricoh, Olympus, Panasonic,
and Leica are classified as `camera`; everything else is `unknown`.

Search indexed photo metadata with `GET /photos/search`. Filters are optional
and can be combined:

- `camera_model`
- `lens_model`
- `min_focal_length`
- `max_focal_length`
- `iso`
- `aperture`
- `shutter_speed`
- `date_from`
- `date_to`
- `extension`
- `device_type`
- `sort_by`
- `sort_order`
- `limit`
- `offset`

Example:

```bash
curl "http://127.0.0.1:8000/photos/search?camera_model=EOS&min_focal_length=24&max_focal_length=85"
```

The response includes `total_count`, `limit`, `offset`, `sort_by`,
`sort_order`, and `results` for simple pagination. Search defaults to
`limit=50`, `offset=0`, `sort_by=date_taken`, and `sort_order=desc`;
requested limits above 500 are capped at 500, and invalid pagination or sort
values return clean `400` responses. Results include file size, extension,
capture date, camera/lens, exposure fields, focal length, and derived
`device_type`.

Metadata search options are available from `GET /photos/search-options`, which
returns capped distinct camera, lens, extension, ISO, aperture, shutter speed,
and device-type values for dropdowns/autocomplete.

Custom analytics are available from `GET /analytics`. Supported dimensions
include capture month/date, camera, lens, extension, device type, ISO, aperture,
shutter speed bucket, and focal length bucket. Supported metrics are
`photo_count`, `avg_file_size`, and `total_file_size`, with optional series
grouping by camera, lens, extension, or device type. Capture-date-heavy
analytics can use safe `limit`, `offset`, `date_from`, and `date_to` parameters
for larger libraries.

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

The dashboard is organized around a branded header, top-level Scan Library,
Metadata Search, and Analytics Explorer tool cards, plus a colorful Insights
section. Insight modules use a compact responsive grid on desktop, with varied
card gradients for charts, file-type summaries, and stat cards. Default charts
include compact camera/lens usage timelines when dated metadata exists, a donut
file type distribution, and top capture dates. Scan Library combines new scans, metadata
refreshes, cancellation, resume/rerun actions, collapsible scan history, and one
concise info popover for scan terminology. Metadata Search stays as a separate
tool with sortable/paginated results and configurable visible columns. Analytics
Explorer uses friendly Compare by, Measure, and Group by controls, quick-build
presets, scrollable dense date charts, and broader chart series colors for
camera/lens comparisons. If a folder has
already been scanned, the dashboard asks the user to choose Refresh metadata,
Scan anyway, or Cancel before starting another scan.

The local "Customize Dashboard" panel lives under Settings. Users can toggle
individual cards, charts, and search/history sections, and those preferences are
saved in browser `localStorage` on that device. The
Capture Timeline only includes files with EXIF capture dates (`date_taken`) and
at least one credible capture metadata value such as camera make/model, ISO,
aperture, shutter speed, or focal length. Files without that supporting capture
metadata are excluded instead of falling back to modified or directory dates.

## Status

v1.3.0 focuses on stronger Metadata Search, sortable/paginated result tables,
custom analytics charts, and more useful default analytics while preserving scan
behavior. Duplicates, maps, open-in-folder, previews, and external job services
remain future work.
