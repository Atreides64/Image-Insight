import json
import re
import shutil
import subprocess
import time
from collections import Counter
from datetime import datetime, time as datetime_time, timezone
from pathlib import Path
from threading import Lock, Thread

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import ExifTags, Image, UnidentifiedImageError
from sqlalchemy import and_, func, not_, or_, text

from app.database import Base, DATABASE_URL, DEFAULT_DATABASE_PATH, SessionLocal, engine
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
PROGRESS_COMMIT_FILE_INTERVAL = 500
RESUMABLE_SCAN_STATUSES = {"running", "interrupted", "failed"}
RESTART_INTERRUPTED_SCAN_ERROR = "Scan interrupted because the application restarted."
CANCELLED_SCAN_IDS: set[int] = set()
CANCELLED_SCAN_IDS_LOCK = Lock()
APP_VERSION = "0.8.0"

app = FastAPI(
    title="Image Insight API",
    description="Backend API for local-first media metadata analytics.",
    version=APP_VERSION,
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
SCAN_SESSION_COLUMNS = {
    "force_metadata": "INTEGER NOT NULL DEFAULT 0",
}
EXIF_TAGS = {value: key for key, value in ExifTags.TAGS.items()}
EMPTY_EXIF_METADATA = {
    "camera_make": None,
    "camera_model": None,
    "lens_model": None,
    "focal_length": None,
    "iso": None,
    "aperture": None,
    "shutter_speed": None,
    "date_taken": None,
}
EXIF_METADATA_KEYS = tuple(EMPTY_EXIF_METADATA)


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


def ensure_scan_session_columns() -> None:
    with engine.begin() as connection:
        existing_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(scan_sessions)"))
        }

        for column_name, column_type in SCAN_SESSION_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE scan_sessions ADD COLUMN {column_name} {column_type}"
                    )
                )


ensure_photo_exif_columns()
ensure_scan_session_columns()


def mark_stale_running_scan_sessions_interrupted() -> int:
    interrupted_at = datetime.now(timezone.utc)

    with SessionLocal() as session:
        running_sessions = (
            session.query(ScanSession)
            .filter(ScanSession.status == "running")
            .all()
        )

        for scan_session in running_sessions:
            scan_session.status = "interrupted"
            scan_session.completed_at = interrupted_at
            scan_session.last_error = RESTART_INTERRUPTED_SCAN_ERROR

        session.commit()
        interrupted_count = len(running_sessions)

    if interrupted_count:
        print(
            f"Marked {interrupted_count} stale running scan session(s) interrupted.",
            flush=True,
        )

    return interrupted_count


mark_stale_running_scan_sessions_interrupted()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/system-info")
def system_info() -> dict[str, object]:
    with SessionLocal() as session:
        photo_count = session.query(func.count(Photo.id)).scalar() or 0
        scan_session_count = session.query(func.count(ScanSession.id)).scalar() or 0

    return {
        "app_version": APP_VERSION,
        "database_path": database_path_label(),
        "photo_count": photo_count,
        "scan_session_count": scan_session_count,
        "exiftool_available": is_exiftool_available(),
    }


def clean_exif_text(value: object) -> str | None:
    if value is None:
        return None

    cleaned = str(value).strip().strip("\x00")
    if cleaned in {"", "0"}:
        return None

    return cleaned


def parse_rational_number(value: object) -> float | None:
    if value is None:
        return None

    if isinstance(value, tuple):
        if len(value) == 2:
            numerator = parse_rational_number(value[0])
            denominator = parse_rational_number(value[1])
            if numerator is None or denominator in (None, 0):
                return None
            return numerator / denominator

        if len(value) == 1:
            return parse_rational_number(value[0])

        return None

    if isinstance(value, str):
        cleaned_value = value.strip().strip("\x00")
        if not cleaned_value or cleaned_value == "0":
            return None

        if "/" in cleaned_value:
            numerator, denominator = cleaned_value.split("/", maxsplit=1)
            parsed_numerator = parse_rational_number(numerator)
            parsed_denominator = parse_rational_number(denominator)
            if parsed_numerator is None or parsed_denominator in (None, 0):
                return None
            return parsed_numerator / parsed_denominator

        number_matches = re.findall(r"-?\d+(?:\.\d+)?", cleaned_value)
        if not number_matches:
            return None

        if "," in cleaned_value and len(number_matches) >= 2:
            denominator = float(number_matches[1])
            if denominator == 0:
                return None
            return float(number_matches[0]) / denominator

        return float(number_matches[0])

    try:
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def rational_to_float(value: object) -> float | None:
    number = parse_rational_number(value)

    if number is None:
        return None

    return round(number, 2)


def parse_focal_length(value: object) -> float | None:
    focal_length = rational_to_float(value)

    if focal_length is None or focal_length <= 0:
        return None

    return focal_length


def format_lens_spec_part(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def lens_specification_text(value: object) -> str | None:
    if not isinstance(value, tuple) or len(value) < 2:
        return None

    min_focal = parse_focal_length(value[0])
    max_focal = parse_focal_length(value[1])
    min_aperture = rational_to_float(value[2]) if len(value) > 2 else None
    max_aperture = rational_to_float(value[3]) if len(value) > 3 else None

    if min_focal is None and max_focal is None:
        return None

    focal_values = [focal for focal in (min_focal, max_focal) if focal is not None]
    if len(focal_values) == 2 and focal_values[0] != focal_values[1]:
        focal_text = (
            f"{format_lens_spec_part(focal_values[0])}-"
            f"{format_lens_spec_part(focal_values[1])}mm"
        )
    else:
        focal_text = f"{format_lens_spec_part(focal_values[0])}mm"

    aperture_values = [
        aperture
        for aperture in (min_aperture, max_aperture)
        if aperture is not None and aperture > 0
    ]
    if not aperture_values:
        return focal_text

    if len(aperture_values) == 2 and aperture_values[0] != aperture_values[1]:
        aperture_text = (
            f"f/{format_lens_spec_part(aperture_values[0])}-"
            f"{format_lens_spec_part(aperture_values[1])}"
        )
    else:
        aperture_text = f"f/{format_lens_spec_part(aperture_values[0])}"

    return f"{focal_text} {aperture_text}"


def parse_lens_model(exif) -> str | None:
    lens_model = clean_exif_text(exif_value(exif, "LensModel"))
    if lens_model:
        return lens_model

    lens_make = clean_exif_text(exif_value(exif, "LensMake"))
    lens_specification = lens_specification_text(exif_value(exif, "LensSpecification"))

    if lens_make and lens_specification:
        return f"{lens_make} {lens_specification}"

    return lens_specification or lens_make


def exiftool_value(metadata: dict[str, object], *keys: str) -> object:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, "", "0"):
            return value

    return None


def exiftool_lens_model(metadata: dict[str, object]) -> str | None:
    lens_model = clean_exif_text(
        exiftool_value(metadata, "LensModel", "LensID", "Lens", "LensType")
    )
    if lens_model:
        return lens_model

    lens_make = clean_exif_text(exiftool_value(metadata, "LensMake"))
    raw_lens_specification = exiftool_value(metadata, "LensSpecification")
    lens_specification = (
        lens_specification_text(tuple(raw_lens_specification))
        if isinstance(raw_lens_specification, list)
        else lens_specification_text(raw_lens_specification)
    )
    lens_specification = lens_specification or clean_exif_text(
        raw_lens_specification
    )

    if lens_make and lens_specification:
        return f"{lens_make} {lens_specification}"

    return lens_specification or lens_make


def parse_iso(value: object) -> int | None:
    iso_value = parse_rational_number(value)

    if iso_value is None or iso_value <= 0:
        return None

    return int(round(iso_value))


def extract_exiftool_metadata(path: Path) -> dict[str, object] | None:
    exiftool_path = shutil.which("exiftool")
    if exiftool_path is None:
        return None

    try:
        result = subprocess.run(
            [exiftool_path, "-json", "-n", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0 or not result.stdout.strip():
        return None

    try:
        parsed_output = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(parsed_output, list) or not parsed_output:
        return None

    metadata = parsed_output[0]
    if not isinstance(metadata, dict):
        return None

    return {
        "camera_make": clean_exif_text(exiftool_value(metadata, "Make")),
        "camera_model": clean_exif_text(exiftool_value(metadata, "Model")),
        "lens_model": exiftool_lens_model(metadata),
        "focal_length": parse_focal_length(exiftool_value(metadata, "FocalLength")),
        "iso": parse_iso(exiftool_value(metadata, "ISO", "BaseISO")),
        "aperture": rational_to_float(
            exiftool_value(metadata, "FNumber", "Aperture", "ApertureValue")
        ),
        "shutter_speed": format_shutter_speed(
            exiftool_value(
                metadata,
                "ExposureTime",
                "ShutterSpeed",
                "ShutterSpeedValue",
            )
        ),
        "date_taken": parse_exif_datetime(
            exiftool_value(metadata, "DateTimeOriginal", "CreateDate", "DateTime")
        ),
    }


def log_unavailable_lens_metadata(
    path: Path,
    exif,
    *,
    lens_model: str | None,
    focal_length: float | None,
) -> None:
    lens_raw_values = [
        exif_value(exif, "LensModel"),
        exif_value(exif, "LensMake"),
        exif_value(exif, "LensSpecification"),
    ]
    focal_raw_value = exif_value(exif, "FocalLength")

    if lens_model is None and any(clean_exif_text(value) for value in lens_raw_values):
        print(f"EXIF lens model unavailable for {path}", flush=True)

    if focal_length is None and focal_raw_value is not None:
        print(f"EXIF focal length unavailable for {path}", flush=True)


def format_shutter_speed(value: object) -> str | None:
    speed = parse_rational_number(value)

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

    text_value = text_value.removesuffix("Z")
    if re.search(r"[+-]\d{2}:\d{2}$", text_value):
        try:
            return normalize_datetime(datetime.fromisoformat(text_value))
        except ValueError:
            pass

    text_value = re.sub(r"([+-]\d{2}):?(\d{2})$", "", text_value).strip()

    for date_format in (
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S.%f",
    ):
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
    exiftool_metadata = extract_exiftool_metadata(path)
    pillow_metadata = extract_pillow_exif_metadata(path)

    if exiftool_metadata is None:
        return pillow_metadata

    return {
        key: exiftool_metadata.get(key) or pillow_metadata.get(key)
        for key in EMPTY_EXIF_METADATA
    }


def extract_pillow_exif_metadata(path: Path) -> dict[str, object]:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
    except (OSError, UnidentifiedImageError, ValueError):
        return EMPTY_EXIF_METADATA.copy()

    if not exif:
        return EMPTY_EXIF_METADATA.copy()

    iso = exif_value(exif, "ISOSpeedRatings") or exif_value(
        exif,
        "PhotographicSensitivity",
    )

    lens_model = parse_lens_model(exif)
    focal_length = parse_focal_length(exif_value(exif, "FocalLength"))
    log_unavailable_lens_metadata(
        path,
        exif,
        lens_model=lens_model,
        focal_length=focal_length,
    )

    return {
        "camera_make": clean_exif_text(exif_value(exif, "Make")),
        "camera_model": clean_exif_text(exif_value(exif, "Model")),
        "lens_model": lens_model,
        "focal_length": focal_length,
        "iso": parse_iso(iso),
        "aperture": rational_to_float(exif_value(exif, "FNumber")),
        "shutter_speed": format_shutter_speed(exif_value(exif, "ExposureTime")),
        "date_taken": parse_exif_datetime(
            exif_value(exif, "DateTimeOriginal") or exif_value(exif, "DateTime")
        ),
    }


def build_basic_file_metadata(path: Path) -> dict[str, object]:
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


def build_file_metadata(path: Path) -> dict[str, object]:
    return {
        **build_basic_file_metadata(path),
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


def format_size_rows(rows: list[tuple[object, int]]) -> list[dict[str, object]]:
    return [
        {
            "label": str(label),
            "size_bytes": size_bytes,
        }
        for label, size_bytes in rows
        if label
    ]


def format_focal_length(value: float | None) -> str | None:
    if value is None:
        return None

    if float(value).is_integer():
        return f"{int(value)}mm"

    return f"{value:g}mm"


def format_aperture(value: float | None) -> str | None:
    if value is None:
        return None

    return f"f/{value:g}"


def build_usage_timeline(
    rows: list[tuple[str, str, int]],
    top_labels: list[str],
) -> list[dict[str, object]]:
    selected_labels = top_labels[:3]
    if not selected_labels:
        return []

    buckets: dict[str, Counter] = {}
    for month, label, count in rows:
        if label not in selected_labels:
            continue

        buckets.setdefault(month, Counter())[label] += count

    return [
        {
            "label": month,
            **{label: buckets[month].get(label, 0) for label in selected_labels},
        }
        for month in sorted(buckets)
    ]


def classify_camera_type(camera_make: str | None, camera_model: str | None) -> str:
    label = " ".join(part for part in (camera_make, camera_model) if part).lower()

    if not label:
        return "unknown"

    phone_terms = (
        "iphone",
        "apple",
        "pixel",
        "samsung",
        "sm-",
        "google",
        "lg",
        "nexus",
    )
    camera_terms = (
        "nikon",
        "canon",
        "fujifilm",
        "sony",
        "ricoh",
        "olympus",
        "panasonic",
        "leica",
    )

    if any(term in label for term in phone_terms):
        return "phone"

    if any(term in label for term in camera_terms):
        return "camera"

    return "unknown"


def camera_type_expression(device_type: str):
    phone_expression = or_(
        Photo.camera_make.ilike("%iPhone%"),
        Photo.camera_model.ilike("%iPhone%"),
        Photo.camera_make.ilike("%Apple%"),
        Photo.camera_model.ilike("%Apple%"),
        Photo.camera_make.ilike("%Pixel%"),
        Photo.camera_model.ilike("%Pixel%"),
        Photo.camera_make.ilike("%Samsung%"),
        Photo.camera_model.ilike("%Samsung%"),
        Photo.camera_make.ilike("%SM-%"),
        Photo.camera_model.ilike("%SM-%"),
        Photo.camera_make.ilike("%Google%"),
        Photo.camera_model.ilike("%Google%"),
        Photo.camera_make.ilike("%LG%"),
        Photo.camera_model.ilike("%LG%"),
        Photo.camera_make.ilike("%Nexus%"),
        Photo.camera_model.ilike("%Nexus%"),
    )
    camera_expression = or_(
        Photo.camera_make.ilike("%Nikon%"),
        Photo.camera_model.ilike("%Nikon%"),
        Photo.camera_make.ilike("%Canon%"),
        Photo.camera_model.ilike("%Canon%"),
        Photo.camera_make.ilike("%Fujifilm%"),
        Photo.camera_model.ilike("%Fujifilm%"),
        Photo.camera_make.ilike("%Sony%"),
        Photo.camera_model.ilike("%Sony%"),
        Photo.camera_make.ilike("%Ricoh%"),
        Photo.camera_model.ilike("%Ricoh%"),
        Photo.camera_make.ilike("%Olympus%"),
        Photo.camera_model.ilike("%Olympus%"),
        Photo.camera_make.ilike("%Panasonic%"),
        Photo.camera_model.ilike("%Panasonic%"),
        Photo.camera_make.ilike("%Leica%"),
        Photo.camera_model.ilike("%Leica%"),
    )

    if device_type == "phone":
        return phone_expression
    if device_type == "camera":
        return camera_expression
    if device_type == "unknown":
        return and_(not_(phone_expression), not_(camera_expression))

    return None


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


def calculate_scan_speed(scan_session: ScanSession) -> float:
    elapsed_seconds = calculate_elapsed_seconds(scan_session)

    if elapsed_seconds <= 0:
        return 0

    return round(scan_session.files_seen / elapsed_seconds, 2)


def is_exiftool_available() -> bool:
    return shutil.which("exiftool") is not None


def database_path_label() -> str:
    if DATABASE_URL.startswith("sqlite:///"):
        return DATABASE_URL.removeprefix("sqlite:///")

    return str(DEFAULT_DATABASE_PATH)


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
        "elapsed_seconds": calculate_elapsed_seconds(scan_session),
        "scan_speed_files_per_second": calculate_scan_speed(scan_session),
        "force_metadata": bool(scan_session.force_metadata),
        "exiftool_available": is_exiftool_available(),
        "last_error": scan_session.last_error,
    }


def format_scan_status(scan_session: ScanSession) -> dict[str, object]:
    return {
        "scan_id": scan_session.id,
        "status": scan_session.status,
        "folder_path": scan_session.folder_path,
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
        "elapsed_seconds": calculate_elapsed_seconds(scan_session),
        "scan_speed_files_per_second": calculate_scan_speed(scan_session),
        "force_metadata": bool(scan_session.force_metadata),
        "exiftool_available": is_exiftool_available(),
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


def file_values_changed(photo: Photo, metadata: dict[str, object]) -> bool:
    return any(
        (
            photo.filename != metadata["filename"],
            photo.extension != metadata["extension"],
            photo.size_bytes != metadata["size_bytes"],
            normalize_datetime(photo.modified_at)
            != normalize_datetime(metadata["modified_at"]),
        )
    )


def is_missing_metadata_value(value: object) -> bool:
    return value is None or value == ""


def exif_backfill_values_changed(photo: Photo, metadata: dict[str, object]) -> bool:
    return any(
        is_missing_metadata_value(getattr(photo, key))
        and not is_missing_metadata_value(metadata[key])
        for key in EXIF_METADATA_KEYS
    )


def apply_exif_backfill_metadata(
    photo: Photo,
    metadata: dict[str, object],
    *,
    scanned_at: datetime,
) -> None:
    for key in EXIF_METADATA_KEYS:
        if is_missing_metadata_value(getattr(photo, key)) and not is_missing_metadata_value(
            metadata[key]
        ):
            setattr(photo, key, metadata[key])

    photo.scanned_at = scanned_at


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


def print_scan_diagnostics(
    label: str,
    *,
    folder_path: Path,
    resolved_folder_path: Path | None,
    directory_entries_inspected: int,
    supported_extension_files_found: int,
    resume_skipped_files: int,
) -> None:
    resolved_label = str(resolved_folder_path) if resolved_folder_path else "unavailable"
    print(
        (
            f"{label}: folder_path={folder_path}, "
            f"resolved_folder_path={resolved_label}, "
            f"directory_entries_inspected={directory_entries_inspected}, "
            f"supported_extension_files_found={supported_extension_files_found}, "
            f"resume_skipped_files={resume_skipped_files}"
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


def commit_scan_progress(
    session,
    scan_session: ScanSession,
    *,
    files_seen: int,
    image_files_matched: int,
    new_files: int,
    updated_files: int,
    skipped_files: int,
    failed_files: int,
) -> None:
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


def request_scan_cancellation(scan_id: int) -> None:
    with CANCELLED_SCAN_IDS_LOCK:
        CANCELLED_SCAN_IDS.add(scan_id)


def is_scan_cancelled(scan_id: int) -> bool:
    with CANCELLED_SCAN_IDS_LOCK:
        return scan_id in CANCELLED_SCAN_IDS


def clear_scan_cancellation(scan_id: int) -> None:
    with CANCELLED_SCAN_IDS_LOCK:
        CANCELLED_SCAN_IDS.discard(scan_id)


def get_latest_scan_session(session, folder_path: str) -> ScanSession | None:
    return (
        session.query(ScanSession)
        .filter(ScanSession.folder_path == folder_path)
        .order_by(ScanSession.started_at.desc(), ScanSession.id.desc())
        .first()
    )


def get_or_create_scan_session(
    session,
    *,
    folder_path: str,
    resume: bool,
    force_metadata: bool,
) -> tuple[int, bool, bool]:
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
        scan_session.force_metadata = force_metadata
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
            force_metadata=force_metadata,
            last_error=None,
        )
        session.add(scan_session)
        session.commit()
        session.refresh(scan_session)

    return scan_session.id, resumed, False


def run_scan_job(scan_id: int, *, resumed: bool, force_metadata: bool) -> None:
    start_time = time.monotonic()
    scanned_at = datetime.now(timezone.utc)
    files_seen = 0
    image_files_matched = 0
    new_files = 0
    updated_files = 0
    skipped_files = 0
    failed_files = 0
    directory_entries_inspected = 0
    resume_skipped_files = 0
    cancelled = False

    with SessionLocal() as session:
        scan_session = session.get(ScanSession, scan_id)

        if scan_session is None:
            print(f"Scan session not found: {scan_id}", flush=True)
            clear_scan_cancellation(scan_id)
            return

        folder = Path(scan_session.folder_path)
        try:
            resolved_folder = folder.resolve(strict=True)
        except OSError:
            resolved_folder = None
        processed_paths = set()

        if resumed:
            processed_paths = {
                row.path
                for row in session.query(ScanSessionFile.path)
                .filter(ScanSessionFile.scan_session_id == scan_session.id)
                .all()
            }

        print_scan_diagnostics(
            "Scan started",
            folder_path=folder,
            resolved_folder_path=resolved_folder,
            directory_entries_inspected=directory_entries_inspected,
            supported_extension_files_found=image_files_matched,
            resume_skipped_files=resume_skipped_files,
        )

        try:
            for path in folder.rglob("*"):
                directory_entries_inspected += 1

                if is_scan_cancelled(scan_id):
                    cancelled = True
                    break

                if not path.is_file():
                    continue

                path_string = str(path)
                files_seen += 1

                if path.suffix.lower() not in IMAGE_EXTENSIONS:
                    if resumed and path_string in processed_paths:
                        resume_skipped_files += 1
                        if files_seen % PROGRESS_COMMIT_FILE_INTERVAL == 0:
                            commit_scan_progress(
                                session,
                                scan_session,
                                files_seen=files_seen,
                                image_files_matched=image_files_matched,
                                new_files=new_files,
                                updated_files=updated_files,
                                skipped_files=skipped_files,
                                failed_files=failed_files,
                            )
                        continue

                    session.add(
                        ScanSessionFile(
                            scan_session_id=scan_session.id,
                            path=path_string,
                        )
                    )
                    if files_seen % PROGRESS_COMMIT_FILE_INTERVAL == 0:
                        commit_scan_progress(
                            session,
                            scan_session,
                            files_seen=files_seen,
                            image_files_matched=image_files_matched,
                            new_files=new_files,
                            updated_files=updated_files,
                            skipped_files=skipped_files,
                            failed_files=failed_files,
                        )
                    continue

                image_files_matched += 1

                if resumed and path_string in processed_paths:
                    skipped_files += 1
                    resume_skipped_files += 1
                    if files_seen % PROGRESS_COMMIT_FILE_INTERVAL == 0:
                        commit_scan_progress(
                            session,
                            scan_session,
                            files_seen=files_seen,
                            image_files_matched=image_files_matched,
                            new_files=new_files,
                            updated_files=updated_files,
                            skipped_files=skipped_files,
                            failed_files=failed_files,
                        )
                    continue

                try:
                    basic_metadata = build_basic_file_metadata(path)
                except OSError as error:
                    print(f"Could not read file {path}: {error}", flush=True)
                    failed_files += 1
                    continue

                photo = (
                    session.query(Photo)
                    .filter(Photo.path == basic_metadata["path"])
                    .one_or_none()
                )

                if photo is not None and not file_values_changed(photo, basic_metadata):
                    if force_metadata:
                        metadata = {
                            **basic_metadata,
                            **extract_exif_metadata(path),
                        }

                        if exif_backfill_values_changed(photo, metadata):
                            apply_exif_backfill_metadata(
                                photo,
                                metadata,
                                scanned_at=scanned_at,
                            )
                            updated_files += 1
                        else:
                            skipped_files += 1
                    else:
                        skipped_files += 1
                else:
                    try:
                        metadata = build_file_metadata(path)
                    except OSError as error:
                        print(f"Could not read file {path}: {error}", flush=True)
                        failed_files += 1
                        continue

                    if photo is None:
                        photo = Photo(**metadata, scanned_at=scanned_at)
                        session.add(photo)
                        new_files += 1
                    elif metadata_values_changed(photo, metadata):
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

                should_commit_progress = (
                    image_files_matched > 0
                    and image_files_matched % BATCH_COMMIT_SIZE == 0
                ) or files_seen % PROGRESS_COMMIT_FILE_INTERVAL == 0

                if should_commit_progress:
                    commit_scan_progress(
                        session,
                        scan_session,
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
            print_scan_diagnostics(
                "Scan failed diagnostics",
                folder_path=folder,
                resolved_folder_path=resolved_folder,
                directory_entries_inspected=directory_entries_inspected,
                supported_extension_files_found=image_files_matched,
                resume_skipped_files=resume_skipped_files,
            )
            clear_scan_cancellation(scan_id)
            return

        if is_scan_cancelled(scan_id):
            cancelled = True

        apply_scan_counters(
            scan_session,
            files_seen=files_seen,
            image_files_matched=image_files_matched,
            new_files=new_files,
            updated_files=updated_files,
            skipped_files=skipped_files,
            failed_files=failed_files,
        )
        scan_session.status = "cancelled" if cancelled else "completed"
        scan_session.completed_at = datetime.now(timezone.utc)
        scan_session.last_error = None
        session.commit()
        session.refresh(scan_session)

    clear_scan_cancellation(scan_id)
    elapsed_time = time.monotonic() - start_time
    print_scan_counters(
        "Scan cancelled" if cancelled else "Scan complete",
        files_seen=files_seen,
        image_files_matched=image_files_matched,
        new_files=new_files,
        updated_files=updated_files,
        skipped_files=skipped_files,
        failed_files=failed_files,
    )
    print_scan_diagnostics(
        "Scan cancelled diagnostics" if cancelled else "Scan complete diagnostics",
        folder_path=folder,
        resolved_folder_path=resolved_folder,
        directory_entries_inspected=directory_entries_inspected,
        supported_extension_files_found=image_files_matched,
        resume_skipped_files=resume_skipped_files,
    )
    print(
        f"Elapsed time: {elapsed_time:.2f} seconds",
        flush=True,
    )


def start_scan_thread(scan_id: int, *, resumed: bool, force_metadata: bool) -> None:
    thread = Thread(
        target=run_scan_job,
        kwargs={
            "scan_id": scan_id,
            "resumed": resumed,
            "force_metadata": force_metadata,
        },
        daemon=True,
    )
    thread.start()


@app.post("/scan-folder")
def scan_folder(
    folder_path: str,
    resume: bool = False,
    force_metadata: bool = False,
) -> dict[str, object]:
    folder = Path(folder_path).expanduser()

    if not folder.exists() or not folder.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"Folder not found: {folder_path}",
        )

    resolved_folder = folder.resolve()

    with SessionLocal() as session:
        scan_id, resumed, already_running = get_or_create_scan_session(
            session,
            folder_path=str(resolved_folder),
            resume=resume,
            force_metadata=force_metadata,
        )

    if already_running:
        if resume:
            return {
                "scan_id": scan_id,
                "status": "running",
                "folder_path": str(resolved_folder),
                "force_metadata": force_metadata,
                "exiftool_available": is_exiftool_available(),
                "message": "A scan is already running for this folder.",
            }

        raise HTTPException(
            status_code=409,
            detail="A scan is already running for this folder.",
        )

    start_scan_thread(scan_id, resumed=resumed, force_metadata=force_metadata)

    return {
        "scan_id": scan_id,
        "status": "running",
        "folder_path": str(resolved_folder),
        "force_metadata": force_metadata,
        "exiftool_available": is_exiftool_available(),
    }


@app.post("/scan-sessions/{scan_id}/cancel")
def cancel_scan_session(scan_id: int) -> dict[str, object]:
    with SessionLocal() as session:
        scan_session = session.get(ScanSession, scan_id)

        if scan_session is None:
            raise HTTPException(status_code=404, detail="Scan session not found")

        if scan_session.status == "running":
            request_scan_cancellation(scan_id)
            response = format_scan_status(scan_session)
            response["message"] = "Scan cancellation requested."
            return response

        response = format_scan_status(scan_session)
        response["message"] = "Scan is not running."
        return response


@app.get("/scan-sessions")
def list_scan_sessions(
    folder_path: str | None = None,
    limit: int = 25,
) -> dict[str, object]:
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be 1 or greater")

    limit = min(limit, 100)

    with SessionLocal() as session:
        query = session.query(ScanSession)

        if folder_path:
            folder = str(Path(folder_path).expanduser().resolve())
            query = query.filter(ScanSession.folder_path == folder)

        scan_sessions = (
            query.order_by(ScanSession.started_at.desc(), ScanSession.id.desc())
            .limit(limit)
            .all()
        )

    return {
        "limit": limit,
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
    iso: int | None = None,
    aperture: float | None = None,
    shutter_speed: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    extension: str | None = None,
    device_type: str | None = None,
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
    normalized_shutter_speed = shutter_speed.strip() if shutter_speed else None
    normalized_device_type = device_type.strip().lower() if device_type else None

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

    if normalized_device_type and normalized_device_type not in {
        "phone",
        "camera",
        "unknown",
    }:
        raise HTTPException(
            status_code=400,
            detail="device_type must be phone, camera, or unknown",
        )

    with SessionLocal() as session:
        query = session.query(Photo)

        if normalized_camera_model:
            query = query.filter(
                or_(
                    Photo.camera_make.ilike(f"%{normalized_camera_model}%"),
                    Photo.camera_model.ilike(f"%{normalized_camera_model}%"),
                    (
                        Photo.camera_make + " " + Photo.camera_model
                    ).ilike(f"%{normalized_camera_model}%"),
                )
            )

        if normalized_lens_model:
            query = query.filter(Photo.lens_model.ilike(f"%{normalized_lens_model}%"))

        if min_focal_length is not None:
            query = query.filter(Photo.focal_length >= min_focal_length)

        if max_focal_length is not None:
            query = query.filter(Photo.focal_length <= max_focal_length)

        if iso is not None:
            query = query.filter(Photo.iso == iso)

        if aperture is not None:
            query = query.filter(Photo.aperture == aperture)

        if normalized_shutter_speed:
            query = query.filter(Photo.shutter_speed == normalized_shutter_speed)

        if parsed_date_from:
            query = query.filter(Photo.date_taken >= parsed_date_from)

        if parsed_date_to:
            query = query.filter(Photo.date_taken <= parsed_date_to)

        if normalized_extension:
            query = query.filter(Photo.extension == normalized_extension)

        if normalized_device_type:
            expression = camera_type_expression(normalized_device_type)
            if expression is not None:
                query = query.filter(expression)

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


@app.get("/photos/search-options")
def photo_search_options(limit: int = 100) -> dict[str, object]:
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be 1 or greater")

    limit = min(limit, 250)

    with SessionLocal() as session:
        camera_rows = (
            session.query(Photo.camera_make, Photo.camera_model)
            .filter((Photo.camera_make.is_not(None)) | (Photo.camera_model.is_not(None)))
            .group_by(Photo.camera_make, Photo.camera_model)
            .order_by(Photo.camera_make, Photo.camera_model)
            .limit(limit)
            .all()
        )
        lens_rows = (
            session.query(Photo.lens_model)
            .filter(Photo.lens_model.is_not(None))
            .group_by(Photo.lens_model)
            .order_by(Photo.lens_model)
            .limit(limit)
            .all()
        )
        extension_rows = (
            session.query(Photo.extension)
            .filter(Photo.extension.is_not(None))
            .group_by(Photo.extension)
            .order_by(Photo.extension)
            .limit(limit)
            .all()
        )
        iso_rows = (
            session.query(Photo.iso)
            .filter(Photo.iso.is_not(None))
            .group_by(Photo.iso)
            .order_by(Photo.iso)
            .limit(limit)
            .all()
        )
        aperture_rows = (
            session.query(Photo.aperture)
            .filter(Photo.aperture.is_not(None))
            .group_by(Photo.aperture)
            .order_by(Photo.aperture)
            .limit(limit)
            .all()
        )
        shutter_speed_rows = (
            session.query(Photo.shutter_speed)
            .filter(Photo.shutter_speed.is_not(None))
            .group_by(Photo.shutter_speed)
            .order_by(Photo.shutter_speed)
            .limit(limit)
            .all()
        )

    cameras = [
        " ".join(part for part in (make, model) if part)
        for make, model in camera_rows
        if " ".join(part for part in (make, model) if part)
    ]

    return {
        "limit": limit,
        "cameras": cameras,
        "lenses": [row[0] for row in lens_rows],
        "extensions": [row[0] for row in extension_rows],
        "iso_values": [row[0] for row in iso_rows],
        "aperture_values": [row[0] for row in aperture_rows],
        "shutter_speed_values": [row[0] for row in shutter_speed_rows],
        "device_types": ["phone", "camera", "unknown"],
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
        storage_by_file_type_rows = (
            session.query(Photo.extension, func.sum(Photo.size_bytes))
            .group_by(Photo.extension)
            .order_by(func.sum(Photo.size_bytes).desc(), Photo.extension)
            .all()
        )
        average_file_size_by_type_rows = (
            session.query(Photo.extension, func.avg(Photo.size_bytes), func.count(Photo.id))
            .group_by(Photo.extension)
            .order_by(func.avg(Photo.size_bytes).desc(), Photo.extension)
            .all()
        )
        raw_extension_count = (
            session.query(func.count(Photo.id))
            .filter(Photo.extension.in_(("dng", "raf")))
            .scalar()
            or 0
        )
        jpeg_extension_count = (
            session.query(func.count(Photo.id))
            .filter(Photo.extension.in_(("jpg", "jpeg")))
            .scalar()
            or 0
        )
        capture_date_count = (
            session.query(func.count(Photo.id))
            .filter(Photo.date_taken.is_not(None))
            .scalar()
            or 0
        )
        most_common_iso_row = (
            session.query(Photo.iso, func.count(Photo.id))
            .filter(Photo.iso.is_not(None))
            .group_by(Photo.iso)
            .order_by(func.count(Photo.id).desc(), Photo.iso)
            .first()
        )
        most_common_aperture_row = (
            session.query(Photo.aperture, func.count(Photo.id))
            .filter(Photo.aperture.is_not(None))
            .group_by(Photo.aperture)
            .order_by(func.count(Photo.id).desc(), Photo.aperture)
            .first()
        )
        most_common_shutter_speed_row = (
            session.query(Photo.shutter_speed, func.count(Photo.id))
            .filter(Photo.shutter_speed.is_not(None))
            .group_by(Photo.shutter_speed)
            .order_by(func.count(Photo.id).desc(), Photo.shutter_speed)
            .first()
        )
        average_file_size_by_camera_rows = (
            session.query(
                Photo.camera_make,
                Photo.camera_model,
                func.avg(Photo.size_bytes),
                func.count(Photo.id),
            )
            .filter((Photo.camera_make.is_not(None)) | (Photo.camera_model.is_not(None)))
            .group_by(Photo.camera_make, Photo.camera_model)
            .order_by(func.avg(Photo.size_bytes).desc())
            .limit(10)
            .all()
        )
        device_camera_rows = session.query(Photo.camera_make, Photo.camera_model).all()
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
        camera_usage_timeline_rows = (
            session.query(
                func.strftime("%Y-%m", Photo.date_taken).label("month"),
                Photo.camera_make,
                Photo.camera_model,
                func.count(Photo.id),
            )
            .filter(Photo.date_taken.is_not(None))
            .filter((Photo.camera_make.is_not(None)) | (Photo.camera_model.is_not(None)))
            .group_by("month", Photo.camera_make, Photo.camera_model)
            .order_by("month")
            .all()
        )
        lens_usage_timeline_rows = (
            session.query(
                func.strftime("%Y-%m", Photo.date_taken).label("month"),
                Photo.lens_model,
                func.count(Photo.id),
            )
            .filter(Photo.date_taken.is_not(None))
            .filter(Photo.lens_model.is_not(None))
            .group_by("month", Photo.lens_model)
            .order_by("month")
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
        timeline_detail_rows = (
            session.query(
                func.strftime("%Y-%m", Photo.date_taken).label("month"),
                Photo.camera_make,
                Photo.camera_model,
                Photo.lens_model,
                func.count(Photo.id),
            )
            .filter(Photo.date_taken.is_not(None))
            .filter(
                (Photo.camera_make.is_not(None))
                | (Photo.camera_model.is_not(None))
                | (Photo.iso.is_not(None))
                | (Photo.aperture.is_not(None))
                | (Photo.shutter_speed.is_not(None))
                | (Photo.focal_length.is_not(None))
            )
            .group_by("month", Photo.camera_make, Photo.camera_model, Photo.lens_model)
            .order_by("month")
            .all()
        )

    raw_vs_jpeg_counts = {
        "raw": raw_extension_count,
        "jpeg": jpeg_extension_count,
        "other": max(total_photos - raw_extension_count - jpeg_extension_count, 0),
    }
    phone_vs_camera_counts = {"phone": 0, "camera": 0, "unknown": 0}
    for camera_make, camera_model in device_camera_rows:
        phone_vs_camera_counts[classify_camera_type(camera_make, camera_model)] += 1

    camera_counts = Counter(
        " ".join(part for part in (make, model) if part)
        for make, model in camera_photos
    )
    top_cameras = [
        {"label": label, "count": count}
        for label, count in camera_counts.most_common(10)
        if label
    ]
    camera_usage_rows = [
        (
            month,
            " ".join(part for part in (make, model) if part),
            count,
        )
        for month, make, model, count in camera_usage_timeline_rows
        if " ".join(part for part in (make, model) if part)
    ]
    camera_usage_timeline = build_usage_timeline(
        camera_usage_rows,
        [str(row["label"]) for row in top_cameras],
    )
    top_lenses = format_count_rows(lens_rows)
    lens_usage_timeline = build_usage_timeline(
        lens_usage_timeline_rows,
        [str(row["label"]) for row in top_lenses],
    )
    top_focal_lengths = [
        {"label": format_focal_length(value), "count": count}
        for value, count in focal_length_rows
        if format_focal_length(value)
    ]
    average_file_size_by_camera = [
        {
            "label": " ".join(part for part in (make, model) if part),
            "average_file_size_bytes": round(float(average_size), 2),
            "count": count,
        }
        for make, model, average_size, count in average_file_size_by_camera_rows
        if " ".join(part for part in (make, model) if part)
    ]
    timeline_buckets: dict[str, dict[str, object]] = {}
    for month, camera_make, camera_model, lens_model, count in timeline_detail_rows:
        bucket = timeline_buckets.setdefault(
            month,
            {
                "label": month,
                "count": 0,
                "camera_counts": Counter(),
                "lens_counts": Counter(),
            },
        )
        bucket["count"] = int(bucket["count"]) + count

        camera_label = " ".join(
            part for part in (camera_make, camera_model) if part
        )
        if camera_label:
            bucket["camera_counts"][camera_label] += count
        if lens_model:
            bucket["lens_counts"][lens_model] += count

    photo_timeline = []
    for month in sorted(timeline_buckets):
        bucket = timeline_buckets[month]
        camera_counts_for_month = bucket["camera_counts"]
        lens_counts_for_month = bucket["lens_counts"]
        top_camera = (
            camera_counts_for_month.most_common(1)[0][0]
            if camera_counts_for_month
            else None
        )
        top_lens = (
            lens_counts_for_month.most_common(1)[0][0]
            if lens_counts_for_month
            else None
        )
        photo_timeline.append(
            {
                "label": bucket["label"],
                "count": bucket["count"],
                "top_camera": top_camera,
                "top_lens": top_lens,
            }
        )

    return {
        "total_photos": total_photos,
        "total_size_bytes": total_size_bytes,
        "average_file_size_bytes": round(total_size_bytes / total_photos, 2)
        if total_photos
        else 0,
        "file_type_counts": {
            extension: count for extension, count in file_type_rows
        },
        "storage_by_file_type": format_size_rows(storage_by_file_type_rows),
        "average_file_size_by_file_type": [
            {
                "label": str(extension),
                "average_file_size_bytes": round(float(average_size), 2),
                "count": count,
            }
            for extension, average_size, count in average_file_size_by_type_rows
            if extension
        ],
        "raw_vs_jpeg_counts": raw_vs_jpeg_counts,
        "phone_vs_camera_counts": phone_vs_camera_counts,
        "top_cameras": top_cameras,
        "top_lenses": top_lenses,
        "camera_usage_timeline": camera_usage_timeline,
        "lens_usage_timeline": lens_usage_timeline,
        "top_focal_lengths": top_focal_lengths,
        "most_common_iso": (
            {"label": str(most_common_iso_row[0]), "count": most_common_iso_row[1]}
            if most_common_iso_row
            else None
        ),
        "most_common_aperture": (
            {
                "label": format_aperture(most_common_aperture_row[0]),
                "count": most_common_aperture_row[1],
            }
            if most_common_aperture_row
            else None
        ),
        "most_common_shutter_speed": (
            {
                "label": str(most_common_shutter_speed_row[0]),
                "count": most_common_shutter_speed_row[1],
            }
            if most_common_shutter_speed_row
            else None
        ),
        "average_file_size_by_camera": average_file_size_by_camera,
        "photos_with_capture_date": capture_date_count,
        "photos_missing_capture_date": total_photos - capture_date_count,
        "photos_by_year": format_count_rows(year_rows),
        "photos_by_month": format_count_rows(month_rows),
        "photo_timeline": photo_timeline,
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
