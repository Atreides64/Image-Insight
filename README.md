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

Image Insight v0.2.0 extracts EXIF metadata when it is available and stores
camera make/model, lens model, focal length, ISO, aperture, shutter speed, and
capture date. Missing or unreadable EXIF data is ignored so scans can continue.

`/scan-folder` returns a concise scan summary by default. To include the full
file list in the response, pass `include_files=true`.

Scans stream directly over `Path.rglob("*")`, commit database changes every 500
matched image files, and treat unchanged existing rows as `skipped_files`
instead of `updated_files`.

Use `resume=true` to resume the latest failed or interrupted scan session for
the same folder without redoing already committed file work unnecessarily.

Default `/scan-folder` summary fields:

- `scan_id`
- `status`
- `total_files`
- `files_seen`
- `image_files_matched`
- `new_files`
- `updated_files`
- `skipped_files`
- `failed_files`
- `elapsed_seconds`
- `folder_path`

Scan session endpoints:

- `GET /scan-sessions`
- `GET /scan-sessions?folder_path=/path/to/folder`
- `GET /scan-sessions/{scan_id}`

Stats are available from `GET /stats` and include:

- Library totals and file type counts
- Top cameras, lenses, and focal lengths
- Photos by year and month
- Busiest capture date when EXIF dates are available

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

v0.2.0 adds EXIF analytics for camera, lens, focal length, and capture timeline
insights. Search, duplicates, maps, and background jobs remain future work.
