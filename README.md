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

`POST /scan-folder` starts a lightweight background scan job and returns a
`scan_id` quickly. The scan continues in a Python thread and writes progress to
the existing SQLite scan session record.

Scans stream directly over `Path.rglob("*")`, commit database changes every 500
matched image files, and treat unchanged existing rows as `skipped_files`
instead of `updated_files`.

Use `resume=true` to resume the latest failed or interrupted scan session for
the same folder without redoing already committed file work unnecessarily.
Starting a second scan for the same folder while one is already running returns
a conflict instead of creating duplicate work.

Start a scan:

```bash
curl -X POST "http://127.0.0.1:8000/scan-folder?folder_path=/path/to/photos"
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
- `last_error`

Scan session endpoints:

- `GET /scan-sessions`
- `GET /scan-sessions?folder_path=/path/to/folder`
- `GET /scan-sessions/{scan_id}`
- `GET /scan-status/{scan_id}`

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
simple pagination.

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

## Status

v0.4.0 adds metadata search and filtering for indexed photos. Duplicates, maps,
and external job services remain future work.
