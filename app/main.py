import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func

from app.database import Base, SessionLocal, engine
from app.models import Photo

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


@app.get("/scan-folder")
def scan_folder(folder_path: str, include_files: bool = False) -> dict[str, object]:
    folder = Path(folder_path).expanduser()
    start_time = time.monotonic()
    print(f"Scan started: {folder}", flush=True)

    if not folder.exists() or not folder.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"Folder not found: {folder_path}",
        )

    scanned_at = datetime.now(timezone.utc)
    files = []
    files_seen = 0
    image_files_matched = 0
    new_files = 0
    updated_files = 0
    skipped_files = 0
    failed_files = 0

    with SessionLocal() as session:
        for path in folder.rglob("*"):
            if not path.is_file():
                continue

            files_seen += 1

            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                skipped_files += 1
                continue

            image_files_matched += 1

            try:
                metadata = build_file_metadata(path)
            except OSError as error:
                print(f"Could not read file {path}: {error}", flush=True)
                failed_files += 1
                continue

            photo = session.query(Photo).filter(Photo.path == metadata["path"]).one_or_none()

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

            if include_files:
                files.append(
                    {
                        **metadata,
                        "modified_at": metadata["modified_at"].isoformat(),
                        "scanned_at": scanned_at.isoformat(),
                    }
                )

            if image_files_matched % BATCH_COMMIT_SIZE == 0:
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

        session.commit()

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

    response = {
        "total_files": image_files_matched,
        "files_seen": files_seen,
        "image_files_matched": image_files_matched,
        "new_files": new_files,
        "updated_files": updated_files,
        "skipped_files": skipped_files,
        "failed_files": failed_files,
        "elapsed_seconds": round(elapsed_time, 2),
        "folder_path": str(folder),
    }

    if include_files:
        response["files"] = files

    return response


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
