import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func

from app.database import Base, SessionLocal, engine
from app.models import Photo, ScanSession, ScanSessionFile

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".heic",
    ".dng",
    ".raf",
}
BATCH_COMMIT_SIZE = 500
RESUMABLE_SCAN_STATUSES = {"running", "interrupted", "failed"}

app = FastAPI(
    title="Image Insight API",
    description="Backend API for local-first media metadata analytics.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def build_file_metadata(path: Path) -> dict[str, object]:
    file_stat = path.stat()

    return {
        "filename": path.name,
        "path": str(path),
        "extension": path.suffix.lower().lstrip("."),
        "size_bytes": file_stat.st_size,
        "modified_at": datetime.fromtimestamp(
            file_stat.st_mtime,
            tz=timezone.utc,
        ),
    }


def format_photo(photo: Photo) -> dict[str, object]:
    return {
        "id": photo.id,
        "filename": photo.filename,
        "path": photo.path,
        "extension": photo.extension,
        "size_bytes": photo.size_bytes,
        "modified_at": photo.modified_at.isoformat(),
        "scanned_at": photo.scanned_at.isoformat(),
    }


def format_scan_session(scan_session: ScanSession) -> dict[str, object]:
    return {
        "scan_id": scan_session.id,
        "folder_path": scan_session.folder_path,
        "status": scan_session.status,
        "started_at": scan_session.started_at.isoformat(),
        "completed_at": (
            scan_session.completed_at.isoformat()
            if scan_session.completed_at
            else None
        ),
        "files_seen": scan_session.files_seen,
        "image_files_matched": scan_session.image_files_matched,
        "new_files": scan_session.new_files,
        "updated_files": scan_session.updated_files,
        "skipped_files": scan_session.skipped_files,
        "failed_files": scan_session.failed_files,
        "last_error": scan_session.last_error,
    }


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def print_scan_counters(
    label: str,
    *,
    files_seen: int,
    image_files_matched: int,
    new_files: int,
    updated_files: int,
    skipped_files: int,
    failed_files: int,
) -> None:
    print(
        (
            f"{label}: files_seen={files_seen}, "
            f"image_files_matched={image_files_matched}, "
            f"new_files={new_files}, updated_files={updated_files}, "
            f"skipped_files={skipped_files}, failed_files={failed_files}"
        ),
        flush=True,
    )


def apply_scan_counters(
    scan_session: ScanSession,
    *,
    files_seen: int,
    image_files_matched: int,
    new_files: int,
    updated_files: int,
    skipped_files: int,
    failed_files: int,
) -> None:
    scan_session.files_seen = files_seen
    scan_session.image_files_matched = image_files_matched
    scan_session.new_files = new_files
    scan_session.updated_files = updated_files
    scan_session.skipped_files = skipped_files
    scan_session.failed_files = failed_files


def reset_scan_session_progress(scan_session: ScanSession) -> None:
    apply_scan_counters(
        scan_session,
        files_seen=0,
        image_files_matched=0,
        new_files=0,
        updated_files=0,
        skipped_files=0,
        failed_files=0,
    )


def get_latest_scan_session(session, folder_path: str) -> ScanSession | None:
    return (
        session.query(ScanSession)
        .filter(ScanSession.folder_path == folder_path)
        .order_by(ScanSession.started_at.desc(), ScanSession.id.desc())
        .first()
    )


def get_or_create_scan_session(session, *, folder_path: str, resume: bool) -> tuple[ScanSession, set[str], bool]:
    latest_session = get_latest_scan_session(session, folder_path)
    processed_paths: set[str] = set()
    resumed = False

    if latest_session and latest_session.status == "running":
        latest_session.status = "interrupted"
        latest_session.completed_at = datetime.now(timezone.utc)
        latest_session.last_error = (
            latest_session.last_error or "Scan stopped before completion."
        )
        session.commit()

    if (
        resume
        and latest_session
        and latest_session.status in RESUMABLE_SCAN_STATUSES
    ):
        scan_session = latest_session
        processed_paths = {
            row.path
            for row in session.query(ScanSessionFile.path)
            .filter(ScanSessionFile.scan_session_id == scan_session.id)
            .all()
        }
        scan_session.status = "running"
        scan_session.completed_at = None
        scan_session.last_error = None
        reset_scan_session_progress(scan_session)
        session.commit()
        resumed = True
    else:
        scan_session = ScanSession(
            folder_path=folder_path,
            status="running",
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            files_seen=0,
            image_files_matched=0,
            new_files=0,
            updated_files=0,
            skipped_files=0,
            failed_files=0,
            last_error=None,
        )
        session.add(scan_session)
        session.commit()
        session.refresh(scan_session)

    return scan_session, processed_paths, resumed


def build_scan_response(
    *,
    scan_session: ScanSession,
    files_seen: int,
    image_files_matched: int,
    new_files: int,
    updated_files: int,
    skipped_files: int,
    failed_files: int,
    elapsed_time: float,
    folder_path: str,
    files: list[dict[str, object]] | None,
) -> dict[str, object]:
    response = {
        "scan_id": scan_session.id,
        "status": scan_session.status,
        "total_files": image_files_matched,
        "files_seen": files_seen,
        "image_files_matched": image_files_matched,
        "new_files": new_files,
        "updated_files": updated_files,
        "skipped_files": skipped_files,
        "failed_files": failed_files,
        "elapsed_seconds": round(elapsed_time, 2),
        "folder_path": folder_path,
        "last_error": scan_session.last_error,
    }

    if files is not None:
        response["files"] = files

    return response


@app.get("/scan-folder")
def scan_folder(
    folder_path: str,
    include_files: bool = False,
    resume: bool = False,
) -> dict[str, object]:
    folder = Path(folder_path).expanduser()
    start_time = time.monotonic()
    print(f"Scan started: {folder}", flush=True)

    if not folder.exists() or not folder.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"Folder not found: {folder_path}",
        )

    scanned_at = datetime.now(timezone.utc)
    files = [] if include_files else None
    files_seen = 0
    image_files_matched = 0
    new_files = 0
    updated_files = 0
    skipped_files = 0
    failed_files = 0

    with SessionLocal() as session:
        scan_session, processed_paths, resumed = get_or_create_scan_session(
            session,
            folder_path=str(folder),
            resume=resume,
        )

        try:
            for path in folder.rglob("*"):
                if not path.is_file():
                    continue

                path_string = str(path)
                files_seen += 1

                if path.suffix.lower() not in IMAGE_EXTENSIONS:
                    skipped_files += 1

                    if resumed and path_string in processed_paths:
                        continue

                    session.add(
                        ScanSessionFile(
                            scan_session_id=scan_session.id,
                            path=path_string,
                        )
                    )
                    continue

                image_files_matched += 1

                if resumed and path_string in processed_paths:
                    skipped_files += 1
                    continue

                try:
                    metadata = build_file_metadata(path)
                except OSError as error:
                    print(f"Could not read file {path}: {error}", flush=True)
                    failed_files += 1
                    continue

                photo = (
                    session.query(Photo)
                    .filter(Photo.path == metadata["path"])
                    .one_or_none()
                )

                if photo is None:
                    photo = Photo(**metadata, scanned_at=scanned_at)
                    session.add(photo)
                    new_files += 1
                else:
                    has_changes = any(
                        (
                            photo.filename != metadata["filename"],
                            photo.extension != metadata["extension"],
                            photo.size_bytes != metadata["size_bytes"],
                            normalize_datetime(photo.modified_at)
                            != normalize_datetime(metadata["modified_at"]),
                        )
                    )

                    if has_changes:
                        photo.filename = metadata["filename"]
                        photo.extension = metadata["extension"]
                        photo.size_bytes = metadata["size_bytes"]
                        photo.modified_at = metadata["modified_at"]
                        photo.scanned_at = scanned_at
                        updated_files += 1
                    else:
                        skipped_files += 1

                if files is not None:
                    files.append(
                        {
                            **metadata,
                            "modified_at": metadata["modified_at"].isoformat(),
                            "scanned_at": scanned_at.isoformat(),
                        }
                    )

                session.add(
                    ScanSessionFile(
                        scan_session_id=scan_session.id,
                        path=path_string,
                    )
                )

                if image_files_matched % BATCH_COMMIT_SIZE == 0:
                    apply_scan_counters(
                        scan_session,
                        files_seen=files_seen,
                        image_files_matched=image_files_matched,
                        new_files=new_files,
                        updated_files=updated_files,
                        skipped_files=skipped_files,
                        failed_files=failed_files,
                    )
                    session.commit()
                    print_scan_counters(
                        "Scan progress",
                        files_seen=files_seen,
                        image_files_matched=image_files_matched,
                        new_files=new_files,
                        updated_files=updated_files,
                        skipped_files=skipped_files,
                        failed_files=failed_files,
                    )

        except Exception as error:
            apply_scan_counters(
                scan_session,
                files_seen=files_seen,
                image_files_matched=image_files_matched,
                new_files=new_files,
                updated_files=updated_files,
                skipped_files=skipped_files,
                failed_files=failed_files,
            )
            scan_session.status = "failed"
            scan_session.completed_at = datetime.now(timezone.utc)
            scan_session.last_error = str(error)
            session.commit()
            raise HTTPException(status_code=500, detail=f"Scan failed: {error}") from error

        apply_scan_counters(
            scan_session,
            files_seen=files_seen,
            image_files_matched=image_files_matched,
            new_files=new_files,
            updated_files=updated_files,
            skipped_files=skipped_files,
            failed_files=failed_files,
        )
        scan_session.status = "completed"
        scan_session.completed_at = datetime.now(timezone.utc)
        scan_session.last_error = None
        session.commit()
        session.refresh(scan_session)

    elapsed_time = time.monotonic() - start_time
    print_scan_counters(
        "Scan complete",
        files_seen=files_seen,
        image_files_matched=image_files_matched,
        new_files=new_files,
        updated_files=updated_files,
        skipped_files=skipped_files,
        failed_files=failed_files,
    )
    print(
        f"Elapsed time: {elapsed_time:.2f} seconds",
        flush=True,
    )

    return build_scan_response(
        scan_session=scan_session,
        files_seen=files_seen,
        image_files_matched=image_files_matched,
        new_files=new_files,
        updated_files=updated_files,
        skipped_files=skipped_files,
        failed_files=failed_files,
        elapsed_time=elapsed_time,
        folder_path=str(folder),
        files=files,
    )


@app.get("/scan-sessions")
def list_scan_sessions(folder_path: str | None = None) -> dict[str, object]:
    with SessionLocal() as session:
        query = session.query(ScanSession)

        if folder_path:
            folder = str(Path(folder_path).expanduser())
            query = query.filter(ScanSession.folder_path == folder)

        scan_sessions = (
            query.order_by(ScanSession.started_at.desc(), ScanSession.id.desc())
            .limit(100)
            .all()
        )

    return {
        "scan_sessions": [format_scan_session(scan_session) for scan_session in scan_sessions],
    }


@app.get("/scan-sessions/{scan_id}")
def get_scan_session(scan_id: int) -> dict[str, object]:
    with SessionLocal() as session:
        scan_session = session.get(ScanSession, scan_id)

    if scan_session is None:
        raise HTTPException(status_code=404, detail=f"Scan session not found: {scan_id}")

    return format_scan_session(scan_session)


@app.get("/photos")
def list_photos() -> dict[str, object]:
    with SessionLocal() as session:
        photos = session.query(Photo).order_by(Photo.id).limit(100).all()

    return {
        "total_files": len(photos),
        "files": [format_photo(photo) for photo in photos],
    }


@app.get("/stats")
def get_stats() -> dict[str, object]:
    with SessionLocal() as session:
        total_photos = session.query(func.count(Photo.id)).scalar() or 0
        total_size_bytes = session.query(func.sum(Photo.size_bytes)).scalar() or 0
        newest_modified_at = session.query(func.max(Photo.modified_at)).scalar()
        oldest_modified_at = session.query(func.min(Photo.modified_at)).scalar()
        file_type_rows = (
            session.query(Photo.extension, func.count(Photo.id))
            .group_by(Photo.extension)
            .order_by(Photo.extension)
            .all()
        )

    return {
        "total_photos": total_photos,
        "total_size_bytes": total_size_bytes,
        "file_type_counts": {
            extension: count for extension, count in file_type_rows
        },
        "newest_modified_at": (
            newest_modified_at.isoformat() if newest_modified_at else None
        ),
        "oldest_modified_at": (
            oldest_modified_at.isoformat() if oldest_modified_at else None
        ),
    }
