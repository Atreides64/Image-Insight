# Image Insight

A local-first media metadata analytics platform for analyzing and organizing existing file libraries.

## Goals

- Scan local media folders
- Extract metadata from images
- Detect duplicates
- Visualize trends
- Support fragmented archives

## Planned Stack

- Python
- FastAPI
- SQLite
- React + TypeScript

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

Run the API:

```bash
uvicorn app.main:app --reload
```

Then open:

- API health check: `http://127.0.0.1:8000/health`
- Interactive API docs: `http://127.0.0.1:8000/docs`

## Status

In active development.
