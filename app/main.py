import time
from collections import Counter
from datetime import datetime, time as datetime_time, timezone
from pathlib import Path
from threading import Thread

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import ExifTags, Image, UnidentifiedImageError
from sqlalchemy import func, text

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
    version="0.4.0",
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


EXIF_COLUMNS = {
    "camera_make": "VARCHAR",
    "camera_model": "VARCHAR",
    "lens_model": "VARCHAR",
    "focal_length": "FLOAT",
    "iso": "INTEGER",
    "aperture": "FLOAT",
    "shutter_speed": "VARCHAR",
    "date_taken": "DATETIME",
}
EXIF_TAGS = {value: key for key, value in ExifTags.TAGS.items()}


def ensure_photo_exif_columns() -> None:
    with engine.begin() as connection:
        existing_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(photos)"))
        }

        for column_name, column_type in EXIF_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE photos ADD COLUMN {column_name} {column_type}")
                )


ensure_photo_exif_columns()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def clean_exif_text(value: object) -> str | None:
    if value is None:
        return None

    cleaned = str(value).strip().strip("\x00")
    return cleaned or None


def rational_to_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None

    return round(number, 2)


def format_shutter_speed(value: object) -> str | None:
    speed = rational_to_float(value)

    if speed is None or speed <= 0:
        return None

    if speed < 1:
        denominator = round(1 / speed)
        return f"1/{denominator}s"

    return f"{speed:g}s"


def parse_exif_datetime(value: object) -> datetime | None:
    text_value = clean_exif_text(value)

    if not text_value:
        return None

    for date_format in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text_value, date_format).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue

    return None


def parse_search_datetime(value: str | None, *, end_of_day: bool) -> datetime | None:
    if not value:
        return None

    stripped_value = value.strip()

    if not stripped_value:
        return None

    try:
        if "T" not in stripped_value and len(stripped_value) == 10:
            parsed_date = datetime.fromisoformat(stripped_value).date()
            parsed_datetime = datetime.combine(
                parsed_date,
                datetime_time.max if end_of_day else datetime_time.min,
            )
        else:
            parsed_datetime = datetime.fromisoformat(stripped_value)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date value: {value}",
        ) from error

    return normalize_datetime(parsed_datetime)


def exif_value(exif, tag_name: str) -> object:
    tag_id = EXIF_TAGS.get(tag_name)

    if tag_id is None:
        return None

    return exif.get(tag_id)


def extract_exif_metadata(path: Path) -> dict[str, object]:
    empty_metadata = {
        "camera_make": None,
        "camera_model": None,
        "lens_model": None,
        "focal_length": None,
        "iso": None,
        "aperture": None,
        "shutter_speed": None,
        "date_taken": None,
    }

    try:
        with Image.open(path) as image:
            exif = image.getexif()
    except (OSError, UnidentifiedImageError, ValueError):
        return empty_metadata

    if not exif:
        return empty_metadata

    iso = exif_value(exif, "ISOSpeedRatings") or exif_value(
        exif,
        "PhotographicSensitivity",
    )

    try:
        iso_value = int(iso) if iso is not None else None
    except (TypeError, ValueError):
        iso_value = None

    return {
        "camera_make": clean_exif_text(exif_value(exif, "Make")),
        "camera_model": clean_exif_text(exif_value(exif, "Model")),
        "lens_model": clean_exif_text(exif_value(exif, "LensModel")),
        "focal_length": rational_to_float(exif_value(exif, "FocalLength")),
        "iso": iso_value,
        "aperture": rational_to_float(exif_value(exif, "FNumber")),
        "shutter_speed": format_shutter_speed(exif_value(exif, "ExposureTime")),
        "date_taken": parse_exif_datetime(
            exif_value(exif, "DateTimeOriginal") or exif_value(exif, "DateTime")
        ),
    }


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
        **extract_exif_metadata(path),
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
        "camera_make": photo.camera_make,
        "camera_model": photo.camera_model,
        "lens_model": photo.lens_model,
        "focal_length": photo.focal_length,
        "iso": photo.iso,
        "aperture": photo.aperture,
        "shutter_speed": photo.shutter_speed,
        "date_taken": photo.date_taken.isoformat() if photo.date_taken else None,
    }


def format_count_rows(rows: list[tuple[object, int]]) -> list[dict[str, object]]:
    return [
        {
            "label": str(label),
            "count": count,
        }
        for label, count in rows
        if label
    ]


def format_focal_length(value: float | None) -> str | None:
    if value is None:
        return None

    if float(value).is_integer():
        return f"{int(value)}mm"

    return f"{value:g}mm"


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def calculate_elapsed_seconds(scan_session: ScanSession) -> float:
    end_time = scan_session.completed_at or datetime.now(timezone.utc)

    return round(
        (
            normalize_datetime(end_time)
            - normalize_datetime(scan_session.started_at)
        ).total_seconds(),
        2,
    )


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


def format_scan_status(scan_session: ScanSession) -> dict[str, object]:
    return {
        "scan_id": scan_session.id,
        "status": scan_session.status,
        "folder_path": scan_session.folder_path,
        "files_seen": scan_session.files_seen,
        "image_files_matched": scan_session.image_files_matched,
        "new_files": scan_session.new_files,
        "updated_files": scan_session.updated_files,
        "skipped_files": scan_session.skipped_files,
        "failed_files": scan_session.failed_files,
        "elapsed_seconds": calculate_elapsed_seconds(scan_session),
        "last_error": scan_session.last_error,
    }


def metadata_values_changed(photo: Photo, metadata: dict[str, object]) -> bool:
    date_taken = metadata["date_taken"]
    stored_date_taken = photo.date_taken

    if isinstance(date_taken, datetime) and stored_date_taken is not None:
        date_taken_changed = normalize_datetime(stored_date_taken) != normalize_datetime(
            date_taken
        )
    else:
        date_taken_changed = stored_date_taken != date_taken

    return any(
        (
            photo.filename != metadata["filename"],
            photo.extension != metadata["extension"],
            photo.size_bytes != metadata["size_bytes"],
            normalize_datetime(photo.modified_at)
            != normalize_datetime(metadata["modified_at"]),
            photo.camera_make != metadata["camera_make"],
            photo.camera_model != metadata["camera_model"],
            photo.lens_model != metadata["lens_model"],
            photo.focal_length != metadata["focal_length"],
            photo.iso != metadata["iso"],
            photo.aperture != metadata["aperture"],
            photo.shutter_speed != metadata["shutter_speed"],
            date_taken_changed,
        )
    )


def apply_photo_metadata(
    photo: Photo,
    metadata: dict[str, object],
    *,
    scanned_at: datetime,
) -> None:
    photo.filename = metadata["filename"]
    photo.extension = metadata["extension"]
    photo.size_bytes = metadata["size_bytes"]
    photo.modified_at = metadata["modified_at"]
    photo.scanned_at = scanned_at
    photo.camera_make = metadata["camera_make"]
    photo.camera_model = metadata["camera_model"]
    photo.lens_model = metadata["lens_model"]
    photo.focal_length = metadata["focal_length"]
    photo.iso = metadata["iso"]
    photo.aperture = metadata["aperture"]
    photo.shutter_speed = metadata["shutter_speed"]
    photo.date_taken = metadata["date_taken"]


def format_scan_file_metadata(
    metadata: dict[str, object],
    *,
    scanned_at: datetime,
) -> dict[str, object]:
    date_taken = metadata["date_taken"]

    return {
        **metadata,
        "modified_at": metadata["modified_at"].isoformat(),
        "scanned_at": scanned_at.isoformat(),
        "date_taken": date_taken.isoformat()
        if isinstance(date_taken, datetime)
        else None,
    }


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


def get_or_create_scan_session(session, *, folder_path: str, resume: bool) -> tuple[int, bool, bool]:
    latest_session = get_latest_scan_session(session, folder_path)
    resumed = False

    if latest_session and latest_session.status == "running":
        return latest_session.id, False, True

    if (
        resume
        and latest_session
        and latest_session.status in RESUMABLE_SCAN_STATUSES
    ):
        scan_session = latest_session
        scan_session.status = "running"
        scan_session.started_at = datetime.now(timezone.utc)
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

    return scan_session.id, resumed, False


def run_scan_job(scan_id: int, *, resumed: bool) -> None:
    start_time = time.monotonic()
    scanned_at = datetime.now(timezone.utc)
    files_seen = 0
    image_files_matched = 0
    new_files = 0
    updated_files = 0
    skipped_files = 0
    failed_files = 0

    with SessionLocal() as session:
        scan_session = session.get(ScanSession, scan_id)

        if scan_session is None:
            print(f"Scan session not found: {scan_id}", flush=True)
            return

        folder = Path(scan_session.folder_path)
        processed_paths = set()

        if resumed:
            processed_paths = {
                row.path
                for row in session.query(ScanSessionFile.path)
                .filter(ScanSessionFile.scan_session_id == scan_session.id)
                .all()
            }

        print(f"Scan started: {folder}", flush=True)

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
                    if metadata_values_changed(photo, metadata):
                        apply_photo_metadata(
                            photo,
                            metadata,
                            scanned_at=scanned_at,
                        )
                        updated_files += 1
                    else:
                        skipped_files += 1

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
            print(f"Scan failed: {error}", flush=True)
            return

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


def start_scan_thread(scan_id: int, *, resumed: bool) -> None:
    thread = Thread(
        target=run_scan_job,
        kwargs={"scan_id": scan_id, "resumed": resumed},
        daemon=True,
    )
    thread.start()


@app.post("/scan-folder")
def scan_folder(
    folder_path: str,
    resume: bool = False,
) -> dict[str, object]:
    folder = Path(folder_path).expanduser()

    if not folder.exists() or not folder.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"Folder not found: {folder_path}",
        )

    with SessionLocal() as session:
        scan_id, resumed, already_running = get_or_create_scan_session(
            session,
            folder_path=str(folder),
            resume=resume,
        )

    if already_running:
        if resume:
            return {
                "scan_id": scan_id,
                "status": "running",
                "folder_path": str(folder),
                "message": "A scan is already running for this folder.",
            }

        raise HTTPException(
            status_code=409,
            detail="A scan is already running for this folder.",
        )

    start_scan_thread(scan_id, resumed=resumed)

    return {
        "scan_id": scan_id,
        "status": "running",
        "folder_path": str(folder),
    }


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


@app.get("/scan-status/{scan_id}")
def get_scan_status(scan_id: int) -> dict[str, object]:
    with SessionLocal() as session:
        scan_session = session.get(ScanSession, scan_id)

    if scan_session is None:
        raise HTTPException(status_code=404, detail=f"Scan session not found: {scan_id}")

    return format_scan_status(scan_session)


@app.get("/photos/search")
def search_photos(
    camera_model: str | None = None,
    lens_model: str | None = None,
    min_focal_length: float | None = None,
    max_focal_length: float | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    extension: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, object]:
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be 1 or greater")

    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be 0 or greater")

    limit = min(limit, 500)

    parsed_date_from = parse_search_datetime(date_from, end_of_day=False)
    parsed_date_to = parse_search_datetime(date_to, end_of_day=True)
    normalized_camera_model = camera_model.strip() if camera_model else None
    normalized_lens_model = lens_model.strip() if lens_model else None
    normalized_extension = extension.strip().lower().lstrip(".") if extension else None

    if parsed_date_from and parsed_date_to and parsed_date_from > parsed_date_to:
        raise HTTPException(status_code=400, detail="date_from must be before date_to")

    if (
        min_focal_length is not None
        and max_focal_length is not None
        and min_focal_length > max_focal_length
    ):
        raise HTTPException(
            status_code=400,
            detail="min_focal_length must be less than or equal to max_focal_length",
        )

    with SessionLocal() as session:
        query = session.query(Photo)

        if normalized_camera_model:
            query = query.filter(Photo.camera_model.ilike(f"%{normalized_camera_model}%"))

        if normalized_lens_model:
            query = query.filter(Photo.lens_model.ilike(f"%{normalized_lens_model}%"))

        if min_focal_length is not None:
            query = query.filter(Photo.focal_length >= min_focal_length)

        if max_focal_length is not None:
            query = query.filter(Photo.focal_length <= max_focal_length)

        if parsed_date_from:
            query = query.filter(Photo.date_taken >= parsed_date_from)

        if parsed_date_to:
            query = query.filter(Photo.date_taken <= parsed_date_to)

        if normalized_extension:
            query = query.filter(Photo.extension == normalized_extension)

        total_count = query.count()
        photos = (
            query.order_by(Photo.date_taken.desc(), Photo.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    return {
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "results": [format_photo(photo) for photo in photos],
    }


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
        camera_photos = (
            session.query(Photo.camera_make, Photo.camera_model)
            .filter((Photo.camera_make.is_not(None)) | (Photo.camera_model.is_not(None)))
            .all()
        )
        lens_rows = (
            session.query(Photo.lens_model, func.count(Photo.id))
            .filter(Photo.lens_model.is_not(None))
            .group_by(Photo.lens_model)
            .order_by(func.count(Photo.id).desc(), Photo.lens_model)
            .limit(10)
            .all()
        )
        focal_length_rows = (
            session.query(Photo.focal_length, func.count(Photo.id))
            .filter(Photo.focal_length.is_not(None))
            .group_by(Photo.focal_length)
            .order_by(func.count(Photo.id).desc(), Photo.focal_length)
            .limit(10)
            .all()
        )
        year_rows = (
            session.query(
                func.strftime("%Y", Photo.date_taken).label("year"),
                func.count(Photo.id),
            )
            .filter(Photo.date_taken.is_not(None))
            .group_by("year")
            .order_by("year")
            .all()
        )
        month_rows = (
            session.query(
                func.strftime("%Y-%m", Photo.date_taken).label("month"),
                func.count(Photo.id),
            )
            .filter(Photo.date_taken.is_not(None))
            .group_by("month")
            .order_by("month")
            .all()
        )
        busiest_date_row = (
            session.query(
                func.strftime("%Y-%m-%d", Photo.date_taken).label("date"),
                func.count(Photo.id),
            )
            .filter(Photo.date_taken.is_not(None))
            .group_by("date")
            .order_by(func.count(Photo.id).desc(), "date")
            .first()
        )

    camera_counts = Counter(
        " ".join(part for part in (make, model) if part)
        for make, model in camera_photos
    )
    top_cameras = [
        {"label": label, "count": count}
        for label, count in camera_counts.most_common(10)
        if label
    ]
    top_focal_lengths = [
        {"label": format_focal_length(value), "count": count}
        for value, count in focal_length_rows
        if format_focal_length(value)
    ]

    return {
        "total_photos": total_photos,
        "total_size_bytes": total_size_bytes,
        "file_type_counts": {
            extension: count for extension, count in file_type_rows
        },
        "top_cameras": top_cameras,
        "top_lenses": format_count_rows(lens_rows),
        "top_focal_lengths": top_focal_lengths,
        "photos_by_year": format_count_rows(year_rows),
        "photos_by_month": format_count_rows(month_rows),
        "busiest_date": (
            {"label": busiest_date_row[0], "count": busiest_date_row[1]}
            if busiest_date_row
            else None
        ),
        "newest_modified_at": (
            newest_modified_at.isoformat() if newest_modified_at else None
        ),
        "oldest_modified_at": (
            oldest_modified_at.isoformat() if oldest_modified_at else None
        ),
    }
