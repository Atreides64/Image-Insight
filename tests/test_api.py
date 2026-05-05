import atexit
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

test_db_dir = tempfile.TemporaryDirectory()
test_db_path = Path(test_db_dir.name) / "image_insight_test.db"
os.environ["IMAGE_INSIGHT_DATABASE_URL"] = f"sqlite:///{test_db_path}"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import main as main_module  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Photo, ScanSession, ScanSessionFile  # noqa: E402

client = TestClient(app)
atexit.register(engine.dispose)


TERMINAL_SCAN_STATUSES = {"completed", "failed", "interrupted", "cancelled"}


class FakeExifImage:
    def __init__(self, exif_data: dict[int, object]) -> None:
        self.exif_data = exif_data

    def __enter__(self) -> "FakeExifImage":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def getexif(self) -> dict[int, object]:
        return self.exif_data


def wait_for_scan(scan_id: int, *, expected_status: str = "completed") -> dict[str, object]:
    deadline = time.monotonic() + 5
    last_status: dict[str, object] | None = None

    while time.monotonic() < deadline:
        response = client.get(f"/scan-status/{scan_id}")
        assert response.status_code == 200
        last_status = response.json()

        if last_status["status"] in TERMINAL_SCAN_STATUSES:
            assert last_status["status"] == expected_status
            return last_status

        time.sleep(0.05)

    raise AssertionError(f"Scan {scan_id} did not finish. Last status: {last_status}")


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_system_info_returns_runtime_visibility(monkeypatch) -> None:
    monkeypatch.setattr(main_module.shutil, "which", lambda name: "exiftool")

    response = client.get("/system-info")
    data = response.json()

    assert response.status_code == 200
    assert data["app_version"] == "1.3.0"
    assert data["database_path"].endswith("image_insight_test.db")
    assert isinstance(data["photo_count"], int)
    assert isinstance(data["scan_session_count"], int)
    assert data["exiftool_available"] is True


def test_stats_returns_valid_json_structure() -> None:
    response = client.get("/stats")

    assert response.status_code == 200
    data = response.json()

    assert set(data) == {
        "total_photos",
        "total_size_bytes",
        "average_file_size_bytes",
        "file_type_counts",
        "storage_by_file_type",
        "average_file_size_by_file_type",
        "raw_vs_jpeg_counts",
        "phone_vs_camera_counts",
        "top_cameras",
        "top_lenses",
        "top_focal_lengths",
        "most_common_iso",
        "most_common_aperture",
        "most_common_shutter_speed",
        "average_file_size_by_camera",
        "top_capture_dates",
        "iso_distribution",
        "aperture_distribution",
        "shutter_speed_buckets",
        "focal_length_usage_over_time",
        "photos_with_capture_date",
        "photos_missing_capture_date",
        "photos_by_year",
        "photos_by_month",
        "photo_timeline",
        "camera_usage_timeline",
        "lens_usage_timeline",
        "busiest_date",
        "newest_modified_at",
        "oldest_modified_at",
    }
    assert isinstance(data["total_photos"], int)
    assert isinstance(data["total_size_bytes"], int)
    assert isinstance(data["average_file_size_bytes"], (int, float))
    assert isinstance(data["file_type_counts"], dict)
    assert isinstance(data["storage_by_file_type"], list)
    assert isinstance(data["average_file_size_by_file_type"], list)
    assert set(data["raw_vs_jpeg_counts"]) == {"raw", "jpeg", "other"}
    assert set(data["phone_vs_camera_counts"]) == {"phone", "camera", "unknown"}
    assert isinstance(data["top_cameras"], list)
    assert isinstance(data["top_lenses"], list)
    assert isinstance(data["top_focal_lengths"], list)
    assert isinstance(data["average_file_size_by_camera"], list)
    assert isinstance(data["top_capture_dates"], list)
    assert isinstance(data["iso_distribution"], list)
    assert isinstance(data["aperture_distribution"], list)
    assert isinstance(data["shutter_speed_buckets"], list)
    assert isinstance(data["focal_length_usage_over_time"], list)
    assert isinstance(data["photos_with_capture_date"], int)
    assert isinstance(data["photos_missing_capture_date"], int)
    assert isinstance(data["photos_by_year"], list)
    assert isinstance(data["photos_by_month"], list)
    assert isinstance(data["photo_timeline"], list)
    assert isinstance(data["camera_usage_timeline"], list)
    assert isinstance(data["lens_usage_timeline"], list)


def test_camera_type_classification_uses_make_model_heuristics() -> None:
    assert main_module.classify_camera_type("Apple", "iPhone 15 Pro") == "phone"
    assert main_module.classify_camera_type("Google", "Pixel 8") == "phone"
    assert main_module.classify_camera_type("Samsung", "SM-S918U") == "phone"
    assert main_module.classify_camera_type("Canon", "EOS R5") == "camera"
    assert main_module.classify_camera_type("Fujifilm", "X-T5") == "camera"
    assert main_module.classify_camera_type("Mystery", "Box") == "unknown"
    assert main_module.classify_camera_type(None, None) == "unknown"


def test_usage_timeline_omits_missing_series_instead_of_zero_drops() -> None:
    rows = [
        ("2024-01", "Canon EOS R5", 2),
        ("2024-03", "Canon EOS R5", 1),
        ("2024-02", "Sony ILCE-7M4", 3),
    ]

    timeline = main_module.build_usage_timeline(
        rows,
        ["Canon EOS R5", "Sony ILCE-7M4"],
    )
    february = next(row for row in timeline if row["label"] == "2024-02")

    assert february == {"label": "2024-02", "Sony ILCE-7M4": 3}
    assert "Canon EOS R5" not in february


def test_stats_returns_default_insight_fields_and_device_counts(tmp_path: Path) -> None:
    photos = [
        Photo(
            filename="phone.zzp",
            path=str(tmp_path / "phone.zzp"),
            extension="zzp",
            size_bytes=100,
            modified_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            scanned_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            camera_make="Apple",
            camera_model="iPhone 15",
            lens_model=None,
            focal_length=None,
            iso=100,
            aperture=1.8,
            shutter_speed="1/120s",
            date_taken=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ),
        Photo(
            filename="camera.zzc",
            path=str(tmp_path / "camera.zzc"),
            extension="zzc",
            size_bytes=300,
            modified_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
            scanned_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
            camera_make="Canon",
            camera_model="EOS R5",
            lens_model=None,
            focal_length=None,
            iso=100,
            aperture=2.8,
            shutter_speed="1/250s",
            date_taken=None,
        ),
    ]

    with SessionLocal() as session:
        session.add_all(photos)
        session.commit()

    response = client.get("/stats")
    data = response.json()
    storage_by_file_type = {
        row["label"]: row["size_bytes"] for row in data["storage_by_file_type"]
    }
    average_by_camera = {
        row["label"]: row for row in data["average_file_size_by_camera"]
    }

    assert response.status_code == 200
    assert storage_by_file_type["zzp"] == 100
    assert storage_by_file_type["zzc"] == 300
    assert data["phone_vs_camera_counts"]["phone"] >= 1
    assert data["phone_vs_camera_counts"]["camera"] >= 1
    assert data["most_common_iso"] == {"label": "100", "count": 2}
    assert data["most_common_aperture"] is not None
    assert data["most_common_shutter_speed"] is not None
    assert average_by_camera["Apple iPhone 15"]["average_file_size_bytes"] == 100
    assert average_by_camera["Canon EOS R5"]["average_file_size_bytes"] == 300
    assert data["photos_with_capture_date"] >= 1
    assert data["photos_missing_capture_date"] >= 1


def test_stats_timeline_excludes_photos_without_capture_dates(tmp_path: Path) -> None:
    with SessionLocal() as session:
        session.add(
            Photo(
                filename="no-capture-date.jpg",
                path=str(tmp_path / "no-capture-date.jpg"),
                extension="jpg",
                size_bytes=100,
                modified_at=datetime(2099, 5, 1, tzinfo=timezone.utc),
                scanned_at=datetime(2099, 5, 1, tzinfo=timezone.utc),
                camera_make="Future",
                camera_model="Archive",
                lens_model=None,
                focal_length=None,
                iso=None,
                aperture=None,
                shutter_speed=None,
                date_taken=None,
            )
        )
        session.commit()

    response = client.get("/stats")
    data = response.json()

    assert response.status_code == 200
    assert all(row["label"] != "2099-05" for row in data["photo_timeline"])
    assert all(row["label"] != "2099-05" for row in data["photos_by_month"])
    assert data["busiest_date"] is None or data["busiest_date"]["label"] != "2099-05-01"


def test_stats_timeline_excludes_date_only_rows_without_capture_metadata(
    tmp_path: Path,
) -> None:
    with SessionLocal() as session:
        session.add(
            Photo(
                filename="date-only.jpg",
                path=str(tmp_path / "date-only.jpg"),
                extension="jpg",
                size_bytes=100,
                modified_at=datetime(2088, 1, 1, tzinfo=timezone.utc),
                scanned_at=datetime(2088, 1, 1, tzinfo=timezone.utc),
                camera_make=None,
                camera_model=None,
                lens_model=None,
                focal_length=None,
                iso=None,
                aperture=None,
                shutter_speed=None,
                date_taken=datetime(2088, 1, 1, tzinfo=timezone.utc),
            )
        )
        session.commit()

    response = client.get("/stats")
    data = response.json()

    assert response.status_code == 200
    assert all(row["label"] != "2088-01" for row in data["photo_timeline"])


def test_scan_folder_starts_background_job_and_status_completes(tmp_path: Path) -> None:
    nested_folder = tmp_path / "nested"
    nested_folder.mkdir()

    image_files = [
        tmp_path / "first.jpg",
        tmp_path / "second.PNG",
        nested_folder / "third.raf",
    ]
    ignored_file = tmp_path / "notes.txt"

    for image_file in image_files:
        image_file.write_text("fake image content")
    ignored_file.write_text("not an image")

    response = client.post("/scan-folder", params={"folder_path": str(tmp_path)})

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "running"
    assert data["folder_path"] == str(tmp_path)
    assert isinstance(data["scan_id"], int)
    assert "files" not in data

    scan_status = wait_for_scan(data["scan_id"])

    assert scan_status["scan_id"] == data["scan_id"]
    assert scan_status["status"] == "completed"
    assert scan_status["started_at"] is not None
    assert scan_status["completed_at"] is not None
    assert scan_status["files_seen"] == 4
    assert scan_status["image_files_matched"] == 3
    assert scan_status["new_files"] == 3
    assert scan_status["updated_files"] == 0
    assert scan_status["skipped_files"] == 0
    assert scan_status["failed_files"] == 0
    assert scan_status["elapsed_seconds"] >= 0
    assert scan_status["last_error"] is None

    sessions_response = client.get(
        "/scan-sessions",
        params={"folder_path": str(tmp_path)},
    )
    session_list = sessions_response.json()["scan_sessions"]

    assert sessions_response.status_code == 200
    assert len(session_list) == 1
    assert session_list[0]["scan_id"] == data["scan_id"]
    assert session_list[0]["status"] == "completed"

    session_detail_response = client.get(f"/scan-sessions/{data['scan_id']}")
    session_detail = session_detail_response.json()

    assert session_detail_response.status_code == 200
    assert session_detail["folder_path"] == str(tmp_path)
    assert session_detail["completed_at"] is not None

    second_response = client.post("/scan-folder", params={"folder_path": str(tmp_path)})

    assert second_response.status_code == 200
    second_data = second_response.json()
    second_scan_status = wait_for_scan(second_data["scan_id"])

    assert second_scan_status["image_files_matched"] == 3
    assert second_scan_status["new_files"] == 0
    assert second_scan_status["updated_files"] == 0
    assert second_scan_status["skipped_files"] == 3
    assert second_scan_status["failed_files"] == 0


def test_scan_folder_counts_mixed_jpg_raf_files_without_non_image_skips(
    tmp_path: Path,
) -> None:
    nested_folder = tmp_path / "nested"
    nested_folder.mkdir()

    image_files = [
        *(tmp_path / f"photo-{index}.JPG" for index in range(4)),
        *(nested_folder / f"raw-{index}.RAF" for index in range(5)),
    ]
    non_image_files = [
        tmp_path / "archive.zip",
        nested_folder / "notes.txt",
    ]

    for image_file in image_files:
        image_file.write_text("image bytes")

    for non_image_file in non_image_files:
        non_image_file.write_text("not indexed as an image")

    first_response = client.post("/scan-folder", params={"folder_path": str(tmp_path)})
    first_status = wait_for_scan(first_response.json()["scan_id"])

    assert first_response.status_code == 200
    assert first_status["files_seen"] == len(image_files) + len(non_image_files)
    assert first_status["image_files_matched"] == len(image_files)
    assert first_status["new_files"] == len(image_files)
    assert first_status["updated_files"] == 0
    assert first_status["skipped_files"] == 0
    assert first_status["failed_files"] == 0

    second_response = client.post("/scan-folder", params={"folder_path": str(tmp_path)})
    second_status = wait_for_scan(second_response.json()["scan_id"])

    assert second_response.status_code == 200
    assert second_status["files_seen"] == len(image_files) + len(non_image_files)
    assert second_status["image_files_matched"] == len(image_files)
    assert second_status["new_files"] == 0
    assert second_status["updated_files"] == 0
    assert second_status["skipped_files"] == len(image_files)
    assert second_status["failed_files"] == 0


def test_startup_cleanup_marks_stale_running_sessions_interrupted(tmp_path: Path) -> None:
    started_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

    with SessionLocal() as session:
        scan_session = ScanSession(
            folder_path=str(tmp_path),
            status="running",
            started_at=started_at,
            completed_at=None,
            files_seen=12,
            image_files_matched=10,
            new_files=8,
            updated_files=0,
            skipped_files=2,
            failed_files=0,
            last_error=None,
        )
        session.add(scan_session)
        session.commit()
        scan_id = scan_session.id

    interrupted_count = main_module.mark_stale_running_scan_sessions_interrupted()

    assert interrupted_count >= 1

    response = client.get(f"/scan-sessions/{scan_id}")
    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "interrupted"
    assert data["completed_at"] is not None
    assert data["elapsed_seconds"] >= 0
    assert data["last_error"] == main_module.RESTART_INTERRUPTED_SCAN_ERROR


def test_scan_sessions_history_response_and_limit_behavior(tmp_path: Path) -> None:
    scan_sessions = [
        ScanSession(
            folder_path=str(tmp_path / f"folder-{index}"),
            status="completed",
            started_at=datetime(2024, 1, index + 1, tzinfo=timezone.utc),
            completed_at=datetime(2024, 1, index + 1, 0, 0, index, tzinfo=timezone.utc),
            files_seen=index,
            image_files_matched=index,
            new_files=index,
            updated_files=0,
            skipped_files=0,
            failed_files=0,
            last_error=None,
        )
        for index in range(3)
    ]

    with SessionLocal() as session:
        session.add_all(scan_sessions)
        session.commit()

    response = client.get("/scan-sessions", params={"limit": 2})
    data = response.json()

    assert response.status_code == 200
    assert data["limit"] == 2
    assert len(data["scan_sessions"]) == 2

    first_scan = data["scan_sessions"][0]

    assert {
        "scan_id",
        "folder_path",
        "status",
        "started_at",
        "completed_at",
        "files_seen",
        "image_files_matched",
        "new_files",
        "updated_files",
        "skipped_files",
        "failed_files",
        "elapsed_seconds",
        "scan_speed_files_per_second",
        "force_metadata",
        "exiftool_available",
        "last_error",
    } == set(first_scan)
    assert first_scan["elapsed_seconds"] >= 0

    capped_response = client.get("/scan-sessions", params={"limit": 500})
    invalid_response = client.get("/scan-sessions", params={"limit": 0})

    assert capped_response.status_code == 200
    assert capped_response.json()["limit"] == 100
    assert invalid_response.status_code == 400
    assert invalid_response.json()["detail"] == "limit must be 1 or greater"


def test_scan_folder_counts_changed_files_as_updated(tmp_path: Path) -> None:
    image_file = tmp_path / "photo.jpg"
    image_file.write_text("first version")

    first_response = client.post("/scan-folder", params={"folder_path": str(tmp_path)})
    first_data = wait_for_scan(first_response.json()["scan_id"])

    assert first_response.status_code == 200
    assert first_data["new_files"] == 1
    assert first_data["updated_files"] == 0
    assert first_data["skipped_files"] == 0

    image_file.write_text("second version with changes")

    second_response = client.post("/scan-folder", params={"folder_path": str(tmp_path)})
    second_data = wait_for_scan(second_response.json()["scan_id"])

    assert second_response.status_code == 200
    assert second_data["new_files"] == 0
    assert second_data["updated_files"] == 1
    assert second_data["skipped_files"] == 0


def test_scan_folder_force_metadata_backfills_null_exif_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_file = tmp_path / "metadata-backfill.jpg"
    image_file.write_text("image bytes")
    extract_calls = 0

    def fake_extract_exif_metadata(path: Path) -> dict[str, object]:
        nonlocal extract_calls
        extract_calls += 1

        if extract_calls == 1:
            return main_module.EMPTY_EXIF_METADATA.copy()

        if extract_calls == 2:
            return {
                **main_module.EMPTY_EXIF_METADATA,
                "lens_model": "XF35mmF1.4 R",
                "focal_length": 35.0,
            }

        return {
            **main_module.EMPTY_EXIF_METADATA,
            "lens_model": "Different Lens",
            "focal_length": 50.0,
        }

    monkeypatch.setattr(
        main_module,
        "extract_exif_metadata",
        fake_extract_exif_metadata,
    )

    first_response = client.post("/scan-folder", params={"folder_path": str(tmp_path)})
    first_data = wait_for_scan(first_response.json()["scan_id"])

    assert first_response.status_code == 200
    assert first_data["new_files"] == 1
    assert first_data["updated_files"] == 0
    assert extract_calls == 1

    second_response = client.post("/scan-folder", params={"folder_path": str(tmp_path)})
    second_data = wait_for_scan(second_response.json()["scan_id"])

    assert second_response.status_code == 200
    assert second_data["new_files"] == 0
    assert second_data["updated_files"] == 0
    assert second_data["skipped_files"] == 1
    assert extract_calls == 1

    with SessionLocal() as session:
        photo = session.query(Photo).filter(Photo.path == str(image_file)).one()
        assert photo.lens_model is None
        assert photo.focal_length is None

    force_response = client.post(
        "/scan-folder",
        params={"folder_path": str(tmp_path), "force_metadata": True},
    )
    force_data = wait_for_scan(force_response.json()["scan_id"])

    assert force_response.status_code == 200
    assert force_data["new_files"] == 0
    assert force_data["updated_files"] == 1
    assert force_data["skipped_files"] == 0
    assert extract_calls == 2

    with SessionLocal() as session:
        photo = session.query(Photo).filter(Photo.path == str(image_file)).one()
        assert photo.lens_model == "XF35mmF1.4 R"
        assert photo.focal_length == 35.0

    second_force_response = client.post(
        "/scan-folder",
        params={"folder_path": str(tmp_path), "force_metadata": True},
    )
    second_force_data = wait_for_scan(second_force_response.json()["scan_id"])

    assert second_force_response.status_code == 200
    assert second_force_data["updated_files"] == 0
    assert second_force_data["skipped_files"] == 1
    assert extract_calls == 3

    with SessionLocal() as session:
        photo = session.query(Photo).filter(Photo.path == str(image_file)).one()
        assert photo.lens_model == "XF35mmF1.4 R"
        assert photo.focal_length == 35.0


def test_running_scan_can_be_cancelled(tmp_path: Path, monkeypatch) -> None:
    image_files = [tmp_path / f"photo-{index}.jpg" for index in range(5)]

    for image_file in image_files:
        image_file.write_text("image bytes")

    original_build_file_metadata = main_module.build_file_metadata
    metadata_started = Event()

    def slow_build_file_metadata(path: Path) -> dict[str, object]:
        metadata_started.set()
        time.sleep(0.15)
        return original_build_file_metadata(path)

    monkeypatch.setattr(
        main_module,
        "build_file_metadata",
        slow_build_file_metadata,
    )

    start_response = client.post("/scan-folder", params={"folder_path": str(tmp_path)})
    scan_id = start_response.json()["scan_id"]

    assert start_response.status_code == 200
    assert metadata_started.wait(timeout=2)

    cancel_response = client.post(f"/scan-sessions/{scan_id}/cancel")
    cancel_data = cancel_response.json()

    assert cancel_response.status_code == 200
    assert cancel_data["scan_id"] == scan_id
    assert cancel_data["message"] == "Scan cancellation requested."

    cancelled_status = wait_for_scan(scan_id, expected_status="cancelled")

    assert cancelled_status["status"] == "cancelled"
    assert cancelled_status["image_files_matched"] < len(image_files)
    assert cancelled_status["last_error"] is None

    session_detail_response = client.get(f"/scan-sessions/{scan_id}")
    session_detail = session_detail_response.json()

    assert session_detail_response.status_code == 200
    assert session_detail["status"] == "cancelled"
    assert session_detail["completed_at"] is not None


def test_scan_folder_extracts_exif_and_stats(tmp_path: Path) -> None:
    image_file = tmp_path / "exif-photo.jpg"
    image = Image.new("RGB", (1, 1), "white")
    exif = Image.Exif()
    exif[271] = "Canon"
    exif[272] = "EOS R5"
    exif[42036] = "RF50mm F1.8 STM"
    exif[37386] = 50
    exif[33437] = 1.8
    exif[33434] = 0.008
    exif[34855] = 400
    exif[36867] = "2024:07:14 09:30:00"
    image.save(image_file, exif=exif)

    scan_response = client.post(
        "/scan-folder",
        params={"folder_path": str(tmp_path)},
    )
    scan_data = scan_response.json()
    scan_status = wait_for_scan(scan_data["scan_id"])

    assert scan_response.status_code == 200
    assert scan_status["new_files"] == 1
    assert scan_status["failed_files"] == 0

    photos_response = client.get("/photos")
    photos = photos_response.json()["files"]
    photo = next(file for file in photos if file["path"] == str(image_file))

    assert photo["camera_make"] == "Canon"
    assert photo["camera_model"] == "EOS R5"
    assert photo["lens_model"] == "RF50mm F1.8 STM"
    assert photo["focal_length"] == 50.0
    assert photo["iso"] == 400
    assert photo["aperture"] == 1.8
    assert photo["shutter_speed"] == "1/125s"
    assert photo["date_taken"].startswith("2024-07-14T09:30:00")

    stats_response = client.get("/stats")
    stats_data = stats_response.json()

    assert stats_response.status_code == 200
    top_camera_counts = {
        row["label"]: row["count"] for row in stats_data["top_cameras"]
    }

    assert top_camera_counts["Canon EOS R5"] >= 1
    assert {"label": "RF50mm F1.8 STM", "count": 1} in stats_data["top_lenses"]
    assert {"label": "50mm", "count": 1} in stats_data["top_focal_lengths"]
    year_counts = {row["label"]: row["count"] for row in stats_data["photos_by_year"]}
    month_counts = {row["label"]: row["count"] for row in stats_data["photos_by_month"]}
    timeline_rows = {
        row["label"]: row for row in stats_data["photo_timeline"]
    }

    assert year_counts["2024"] >= 1
    assert month_counts["2024-07"] >= 1
    assert timeline_rows["2024-07"]["count"] >= 1
    assert timeline_rows["2024-07"]["top_camera"] == "Canon EOS R5"
    assert timeline_rows["2024-07"]["top_lens"] == "RF50mm F1.8 STM"
    assert any(
        row["label"] == "2024-07" and row["Canon EOS R5"] >= 1
        for row in stats_data["camera_usage_timeline"]
    )
    assert any(
        row["label"] == "2024-07" and row["RF50mm F1.8 STM"] >= 1
        for row in stats_data["lens_usage_timeline"]
    )
    assert stats_data["busiest_date"] is not None


def test_extract_exif_metadata_uses_lens_fallbacks_and_tuple_focal_length(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_file = tmp_path / "mock-exif.jpg"
    exif_data = {
        271: "Nikon",
        272: "Z 8",
        37386: (105, 2),
        42036: "0",
        42035: "Nikkor",
        42034: (24, 70, (28, 10), 4),
        36867: "2024:08:20 14:15:00",
    }

    monkeypatch.setattr(
        main_module.Image,
        "open",
        lambda path: FakeExifImage(exif_data),
    )

    metadata = main_module.extract_exif_metadata(image_file)

    assert metadata["camera_model"] == "Z 8"
    assert metadata["lens_model"] == "Nikkor 24-70mm f/2.8-4"
    assert metadata["focal_length"] == 52.5
    assert metadata["date_taken"].isoformat().startswith("2024-08-20T14:15:00")


def test_extract_exif_metadata_uses_exiftool_when_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_file = tmp_path / "raw-photo.dng"
    exiftool_output = (
        '[{"Make":"Fujifilm","Model":"X-T5","LensModel":"XF35mmF1.4 R",'
        '"FocalLength":"35 mm","ISO":800,"FNumber":1.4,'
        '"ExposureTime":"1/250","DateTimeOriginal":"2024:09:01 10:11:12"}]'
    )

    monkeypatch.setattr(main_module.shutil, "which", lambda name: "exiftool")
    monkeypatch.setattr(
        main_module.subprocess,
        "run",
        lambda *args, **kwargs: main_module.subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=exiftool_output,
            stderr="",
        ),
    )
    monkeypatch.setattr(
        main_module,
        "extract_pillow_exif_metadata",
        lambda path: main_module.EMPTY_EXIF_METADATA.copy(),
    )

    metadata = main_module.extract_exif_metadata(image_file)

    assert metadata["camera_make"] == "Fujifilm"
    assert metadata["camera_model"] == "X-T5"
    assert metadata["lens_model"] == "XF35mmF1.4 R"
    assert metadata["focal_length"] == 35
    assert metadata["iso"] == 800
    assert metadata["aperture"] == 1.4
    assert metadata["shutter_speed"] == "1/250s"
    assert metadata["date_taken"].isoformat().startswith("2024-09-01T10:11:12")


def test_extract_exif_metadata_merges_exiftool_with_pillow_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_file = tmp_path / "partial-exif.jpg"
    exiftool_output = (
        '[{"Make":"Sony","Model":"ILCE-7M4","LensMake":"Sony",'
        '"LensSpecification":[24,70,2.8,2.8]}]'
    )
    pillow_metadata = {
        **main_module.EMPTY_EXIF_METADATA,
        "focal_length": 50.0,
        "iso": 400,
    }

    monkeypatch.setattr(main_module.shutil, "which", lambda name: "exiftool")
    monkeypatch.setattr(
        main_module.subprocess,
        "run",
        lambda *args, **kwargs: main_module.subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=exiftool_output,
            stderr="",
        ),
    )
    monkeypatch.setattr(
        main_module,
        "extract_pillow_exif_metadata",
        lambda path: pillow_metadata,
    )

    metadata = main_module.extract_exif_metadata(image_file)

    assert metadata["camera_make"] == "Sony"
    assert metadata["camera_model"] == "ILCE-7M4"
    assert metadata["lens_model"] == "Sony 24-70mm f/2.8"
    assert metadata["focal_length"] == 50.0
    assert metadata["iso"] == 400


def test_extract_exif_metadata_falls_back_when_exiftool_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_file = tmp_path / "no-exiftool.jpg"
    pillow_metadata = {
        **main_module.EMPTY_EXIF_METADATA,
        "camera_model": "EOS R6",
        "focal_length": 85.0,
    }

    monkeypatch.setattr(main_module.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        main_module,
        "extract_pillow_exif_metadata",
        lambda path: pillow_metadata,
    )

    metadata = main_module.extract_exif_metadata(image_file)

    assert metadata["camera_model"] == "EOS R6"
    assert metadata["focal_length"] == 85.0


def test_parse_focal_length_handles_common_exif_value_shapes() -> None:
    assert main_module.parse_focal_length(50) == 50
    assert main_module.parse_focal_length(35.5) == 35.5
    assert main_module.parse_focal_length((85, 2)) == 42.5
    assert main_module.parse_focal_length("50/1") == 50
    assert main_module.parse_focal_length("35 mm") == 35
    assert main_module.parse_focal_length("0") is None


def test_search_photos_filters_metadata(tmp_path: Path) -> None:
    with SessionLocal() as session:
        photos = [
            Photo(
                filename="canon-wide.jpg",
                path=str(tmp_path / "canon-wide.jpg"),
                extension="jpg",
                size_bytes=100,
                modified_at=datetime(2024, 1, 10, tzinfo=timezone.utc),
                scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                camera_make="Canon",
                camera_model="EOS R5",
                lens_model="RF24-70mm F2.8",
                focal_length=24.0,
                iso=100,
                aperture=2.8,
                shutter_speed="1/250s",
                date_taken=datetime(2024, 1, 10, 9, 0, tzinfo=timezone.utc),
            ),
            Photo(
                filename="canon-portrait.jpg",
                path=str(tmp_path / "canon-portrait.jpg"),
                extension="jpg",
                size_bytes=120,
                modified_at=datetime(2024, 2, 15, tzinfo=timezone.utc),
                scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                camera_make="Canon",
                camera_model="EOS R5",
                lens_model="RF85mm F2",
                focal_length=85.0,
                iso=200,
                aperture=2.0,
                shutter_speed="1/125s",
                date_taken=datetime(2024, 2, 15, 11, 30, tzinfo=timezone.utc),
            ),
            Photo(
                filename="fuji-street.png",
                path=str(tmp_path / "fuji-street.png"),
                extension="png",
                size_bytes=140,
                modified_at=datetime(2023, 8, 1, tzinfo=timezone.utc),
                scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                camera_make="Fujifilm",
                camera_model="X-T5",
                lens_model=None,
                focal_length=None,
                iso=None,
                aperture=None,
                shutter_speed=None,
                date_taken=None,
            ),
        ]
        session.add_all(photos)
        session.commit()

    response = client.get(
        "/photos/search",
        params={
            "camera_model": "eos",
            "lens_model": "rf",
            "min_focal_length": 20,
            "max_focal_length": 50,
            "date_from": "2024-01-01",
            "date_to": "2024-01-31",
            "extension": ".jpg",
        },
    )
    data = response.json()

    assert response.status_code == 200
    assert data["total_count"] == 1
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert data["sort_by"] == "date_taken"
    assert data["sort_order"] == "desc"
    assert [photo["filename"] for photo in data["results"]] == ["canon-wide.jpg"]
    result = data["results"][0]
    assert {
        "filename",
        "path",
        "extension",
        "size_bytes",
        "date_taken",
        "camera_model",
        "lens_model",
        "focal_length",
        "iso",
        "aperture",
        "shutter_speed",
        "device_type",
    }.issubset(result)

    lens_response = client.get(
        "/photos/search",
        params={"lens_model": "rf", "limit": 1, "offset": 1},
    )
    lens_data = lens_response.json()

    assert lens_response.status_code == 200
    assert lens_data["total_count"] >= 2
    assert lens_data["limit"] == 1
    assert lens_data["offset"] == 1
    assert len(lens_data["results"]) == 1

    null_safe_response = client.get(
        "/photos/search",
        params={"min_focal_length": 20, "max_focal_length": 90},
    )
    null_safe_data = null_safe_response.json()
    returned_paths = {photo["path"] for photo in null_safe_data["results"]}

    assert null_safe_response.status_code == 200
    assert str(tmp_path / "fuji-street.png") not in returned_paths


def test_search_photos_supports_sorting_and_paginated_fields(tmp_path: Path) -> None:
    with SessionLocal() as session:
        photos = [
            Photo(
                filename="sort-small.jpg",
                path=str(tmp_path / "sort-small.jpg"),
                extension="jpg",
                size_bytes=50,
                modified_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
                scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                camera_make="Canon",
                camera_model="EOS R6",
                lens_model="RF35",
                focal_length=35.0,
                iso=100,
                aperture=1.8,
                shutter_speed="1/500s",
                date_taken=datetime(2024, 5, 1, tzinfo=timezone.utc),
            ),
            Photo(
                filename="sort-large.raf",
                path=str(tmp_path / "sort-large.raf"),
                extension="raf",
                size_bytes=500,
                modified_at=datetime(2024, 5, 2, tzinfo=timezone.utc),
                scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                camera_make="Fujifilm",
                camera_model="X-H2",
                lens_model="XF16",
                focal_length=16.0,
                iso=800,
                aperture=4.0,
                shutter_speed="1/125s",
                date_taken=datetime(2024, 5, 2, tzinfo=timezone.utc),
            ),
        ]
        session.add_all(photos)
        session.commit()

    response = client.get(
        "/photos/search",
        params={
            "date_from": "2024-05-01",
            "date_to": "2024-05-31",
            "sort_by": "size_bytes",
            "sort_order": "desc",
            "limit": 1,
            "offset": 0,
        },
    )
    data = response.json()

    assert response.status_code == 200
    assert data["total_count"] == 2
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert data["sort_by"] == "size_bytes"
    assert data["sort_order"] == "desc"
    assert data["results"][0]["filename"] == "sort-large.raf"
    assert data["results"][0]["device_type"] == "camera"

    invalid_sort_response = client.get(
        "/photos/search",
        params={"sort_by": "rating"},
    )

    assert invalid_sort_response.status_code == 400


def test_search_photos_sorts_common_metadata_fields(tmp_path: Path) -> None:
    with SessionLocal() as session:
        session.add_all(
            [
                Photo(
                    filename="sort-alpha.jpg",
                    path=str(tmp_path / "sort-alpha.jpg"),
                    extension="jpg",
                    size_bytes=100,
                    modified_at=datetime(2024, 8, 1, tzinfo=timezone.utc),
                    scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    camera_make="Canon",
                    camera_model="Alpha",
                    lens_model="Wide",
                    focal_length=24.0,
                    iso=100,
                    aperture=2.8,
                    shutter_speed="1/250s",
                    date_taken=datetime(2024, 8, 1, tzinfo=timezone.utc),
                ),
                Photo(
                    filename="sort-beta.jpg",
                    path=str(tmp_path / "sort-beta.jpg"),
                    extension="jpg",
                    size_bytes=300,
                    modified_at=datetime(2024, 8, 3, tzinfo=timezone.utc),
                    scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    camera_make="Nikon",
                    camera_model="Beta",
                    lens_model="Tele",
                    focal_length=85.0,
                    iso=200,
                    aperture=4.0,
                    shutter_speed="1/125s",
                    date_taken=datetime(2024, 8, 3, tzinfo=timezone.utc),
                ),
            ]
        )
        session.commit()

    params = {"date_from": "2024-08-01", "date_to": "2024-08-31", "limit": 2}
    expectations = [
        ("date_taken", "desc", ["sort-beta.jpg", "sort-alpha.jpg"]),
        ("camera_model", "asc", ["sort-alpha.jpg", "sort-beta.jpg"]),
        ("lens_model", "asc", ["sort-beta.jpg", "sort-alpha.jpg"]),
        ("focal_length", "desc", ["sort-beta.jpg", "sort-alpha.jpg"]),
        ("size_bytes", "asc", ["sort-alpha.jpg", "sort-beta.jpg"]),
    ]

    for sort_by, sort_order, filenames in expectations:
        response = client.get(
            "/photos/search",
            params={**params, "sort_by": sort_by, "sort_order": sort_order},
        )
        data = response.json()

        assert response.status_code == 200
        assert [photo["filename"] for photo in data["results"]] == filenames


def test_search_photos_filters_exposure_file_type_and_device_type(
    tmp_path: Path,
) -> None:
    with SessionLocal() as session:
        phone_photo = Photo(
            filename="phone-extra.jpg",
            path=str(tmp_path / "phone-extra.jpg"),
            extension="jpg",
            size_bytes=100,
            modified_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
            scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            camera_make="Apple",
            camera_model="iPhone 15",
            lens_model="Phone Wide",
            focal_length=24.0,
            iso=64,
            aperture=1.8,
            shutter_speed="1/120s",
            date_taken=datetime(2024, 3, 1, tzinfo=timezone.utc),
        )
        camera_photo = Photo(
            filename="camera-extra.raf",
            path=str(tmp_path / "camera-extra.raf"),
            extension="raf",
            size_bytes=200,
            modified_at=datetime(2024, 3, 2, tzinfo=timezone.utc),
            scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            camera_make="Fujifilm",
            camera_model="X-T5",
            lens_model="XF35mmF1.4 R",
            focal_length=35.0,
            iso=400,
            aperture=1.4,
            shutter_speed="1/250s",
            date_taken=datetime(2024, 3, 2, tzinfo=timezone.utc),
        )
        session.add_all([phone_photo, camera_photo])
        session.commit()

    response = client.get(
        "/photos/search",
        params={
            "extension": "raf",
            "iso": 400,
            "aperture": 1.4,
            "shutter_speed": "1/250s",
            "device_type": "camera",
            "date_from": "2024-03-01",
            "date_to": "2024-03-31",
        },
    )
    data = response.json()

    assert response.status_code == 200
    assert str(tmp_path / "camera-extra.raf") in {
        photo["path"] for photo in data["results"]
    }
    assert str(tmp_path / "phone-extra.jpg") not in {
        photo["path"] for photo in data["results"]
    }

    invalid_response = client.get("/photos/search", params={"device_type": "tablet"})

    assert invalid_response.status_code == 400
    assert invalid_response.json()["detail"] == "device_type must be phone, camera, or unknown"


def test_photo_search_options_returns_distinct_values(tmp_path: Path) -> None:
    with SessionLocal() as session:
        session.add(
            Photo(
                filename="options-photo.jpg",
                path=str(tmp_path / "options-photo.jpg"),
                extension="jpg",
                size_bytes=100,
                modified_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
                scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                camera_make="Sony",
                camera_model="ILCE-7M4",
                lens_model="FE 35mm F1.8",
                focal_length=35.0,
                iso=800,
                aperture=1.8,
                shutter_speed="1/500s",
                date_taken=datetime(2024, 4, 1, tzinfo=timezone.utc),
            )
        )
        session.commit()

    response = client.get("/photos/search-options")
    data = response.json()

    assert response.status_code == 200
    assert "Sony ILCE-7M4" in data["cameras"]
    assert "Sony ILCE-7M4" in data["camera_models"]
    assert "FE 35mm F1.8" in data["lenses"]
    assert "FE 35mm F1.8" in data["lens_models"]
    assert "jpg" in data["extensions"]
    assert 800 in data["iso_values"]
    assert 1.8 in data["aperture_values"]
    assert "1/500s" in data["shutter_speed_values"]
    assert data["device_types"] == ["phone", "camera", "unknown"]


def test_analytics_returns_chart_friendly_rows_and_validates_combinations(
    tmp_path: Path,
) -> None:
    with SessionLocal() as session:
        session.add_all(
            [
                Photo(
                    filename="analytics-canon.jpg",
                    path=str(tmp_path / "analytics-canon.jpg"),
                    extension="jpg",
                    size_bytes=100,
                    modified_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
                    scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    camera_make="Canon",
                    camera_model="EOS R5",
                    lens_model="RF50",
                    focal_length=50.0,
                    iso=400,
                    aperture=2.8,
                    shutter_speed="1/250s",
                    date_taken=datetime(2024, 6, 1, tzinfo=timezone.utc),
                ),
                Photo(
                    filename="analytics-sony.v13raf",
                    path=str(tmp_path / "analytics-sony.v13raf"),
                    extension="v13raf",
                    size_bytes=300,
                    modified_at=datetime(2024, 7, 1, tzinfo=timezone.utc),
                    scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    camera_make="Sony",
                    camera_model="ILCE-7M4",
                    lens_model="FE35",
                    focal_length=35.0,
                    iso=800,
                    aperture=1.8,
                    shutter_speed="1/1000s",
                    date_taken=datetime(2024, 7, 1, tzinfo=timezone.utc),
                ),
            ]
        )
        session.commit()

    grouped_response = client.get(
        "/analytics",
        params={
            "x_axis": "capture_month",
            "metric": "photo_count",
            "group_by": "camera_model",
        },
    )
    grouped_data = grouped_response.json()

    assert grouped_response.status_code == 200
    assert grouped_data["x_axis"] == "capture_month"
    assert grouped_data["metric"] == "photo_count"
    assert grouped_data["group_by"] == "camera_model"
    assert grouped_data["offset"] == 0
    assert grouped_data["total_count"] >= 2
    assert "Canon EOS R5" in grouped_data["series"]
    assert any(row["label"] == "2024-06" for row in grouped_data["rows"])

    avg_response = client.get(
        "/analytics",
        params={"x_axis": "extension", "metric": "avg_file_size"},
    )
    avg_data = avg_response.json()

    assert avg_response.status_code == 200
    assert any(row["label"] == "V13RAF" and row["value"] == 300 for row in avg_data["rows"])

    duplicate_response = client.get(
        "/analytics",
        params={"x_axis": "camera_model", "group_by": "camera_model"},
    )
    invalid_metric_response = client.get(
        "/analytics",
        params={"metric": "median_file_size"},
    )
    paginated_response = client.get(
        "/analytics",
        params={
            "x_axis": "capture_date",
            "metric": "photo_count",
            "date_from": "2024-06-01",
            "date_to": "2024-07-31",
            "limit": 1,
            "offset": 1,
        },
    )
    paginated_data = paginated_response.json()

    assert duplicate_response.status_code == 400
    assert duplicate_response.json()["detail"] == "x_axis and group_by must differ"
    assert invalid_metric_response.status_code == 400
    assert paginated_response.status_code == 200
    assert paginated_data["limit"] == 1
    assert paginated_data["offset"] == 1
    assert paginated_data["total_count"] >= 2
    assert len(paginated_data["rows"]) == 1


def test_search_photos_pagination_defaults_and_caps() -> None:
    default_response = client.get("/photos/search")
    capped_response = client.get(
        "/photos/search",
        params={"limit": 999},
    )

    default_data = default_response.json()
    capped_data = capped_response.json()

    assert default_response.status_code == 200
    assert set(default_data) == {
        "total_count",
        "limit",
        "offset",
        "sort_by",
        "sort_order",
        "results",
    }
    assert default_data["limit"] == 50
    assert default_data["offset"] == 0
    assert isinstance(default_data["total_count"], int)
    assert len(default_data["results"]) <= 50
    assert capped_response.status_code == 200
    assert capped_data["limit"] == 500
    assert capped_data["offset"] == 0
    assert len(capped_data["results"]) <= 500


def test_search_photos_rejects_invalid_ranges_and_negative_pagination() -> None:
    focal_response = client.get(
        "/photos/search",
        params={"min_focal_length": 100, "max_focal_length": 50},
    )
    date_response = client.get(
        "/photos/search",
        params={"date_from": "2024-02-01", "date_to": "2024-01-01"},
    )
    invalid_date_response = client.get(
        "/photos/search",
        params={"date_from": "not-a-date"},
    )
    negative_limit_response = client.get(
        "/photos/search",
        params={"limit": -1},
    )
    negative_offset_response = client.get(
        "/photos/search",
        params={"offset": -1},
    )

    assert focal_response.status_code == 400
    assert date_response.status_code == 400
    assert invalid_date_response.status_code == 400
    assert invalid_date_response.json()["detail"] == "Invalid date value: not-a-date"
    assert negative_limit_response.status_code == 400
    assert negative_limit_response.json()["detail"] == "limit must be 1 or greater"
    assert negative_offset_response.status_code == 400
    assert negative_offset_response.json()["detail"] == "offset must be 0 or greater"


def test_failed_scan_session_can_be_resumed(tmp_path: Path, monkeypatch) -> None:
    first_image = tmp_path / "first.jpg"
    second_image = tmp_path / "second.jpg"
    first_image.write_text("first image")
    second_image.write_text("second image")

    original_build_file_metadata = main_module.build_file_metadata
    metadata_calls = 0

    def flaky_build_file_metadata(path: Path) -> dict[str, object]:
        nonlocal metadata_calls

        metadata_calls += 1

        if metadata_calls == 2:
            raise RuntimeError("simulated scan failure")

        return original_build_file_metadata(path)

    monkeypatch.setattr(
        main_module,
        "build_file_metadata",
        flaky_build_file_metadata,
    )

    failed_response = client.post("/scan-folder", params={"folder_path": str(tmp_path)})
    failed_data = failed_response.json()
    failed_status = wait_for_scan(failed_data["scan_id"], expected_status="failed")

    assert failed_response.status_code == 200
    assert failed_status["status"] == "failed"
    assert failed_status["last_error"] == "simulated scan failure"

    sessions_response = client.get(
        "/scan-sessions",
        params={"folder_path": str(tmp_path)},
    )
    failed_session = sessions_response.json()["scan_sessions"][0]

    assert failed_session["status"] == "failed"
    assert failed_session["last_error"] == "simulated scan failure"

    monkeypatch.setattr(
        main_module,
        "build_file_metadata",
        original_build_file_metadata,
    )

    resumed_response = client.post(
        "/scan-folder",
        params={"folder_path": str(tmp_path), "resume": "true"},
    )
    resumed_data = resumed_response.json()
    resumed_status = wait_for_scan(resumed_data["scan_id"])

    assert resumed_response.status_code == 200
    assert resumed_data["scan_id"] == failed_session["scan_id"]
    assert resumed_status["status"] == "completed"
    assert resumed_status["new_files"] == 1
    assert resumed_status["updated_files"] == 0
    assert resumed_status["skipped_files"] == 1
    assert resumed_status["failed_files"] == 0


def test_interrupted_scan_session_can_be_resumed(tmp_path: Path) -> None:
    first_image = tmp_path / "first.jpg"
    second_image = tmp_path / "second.jpg"
    first_image.write_text("first image")
    second_image.write_text("second image")

    metadata = main_module.build_file_metadata(first_image)
    scanned_at = datetime.now(timezone.utc)

    with SessionLocal() as session:
        photo = Photo(**metadata, scanned_at=scanned_at)
        scan_session = ScanSession(
            folder_path=str(tmp_path),
            status="interrupted",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            files_seen=1,
            image_files_matched=1,
            new_files=1,
            updated_files=0,
            skipped_files=0,
            failed_files=0,
            last_error="Stopped before completion.",
        )
        session.add(photo)
        session.add(scan_session)
        session.commit()
        session.refresh(scan_session)
        session.add(
            ScanSessionFile(
                scan_session_id=scan_session.id,
                path=str(first_image),
            )
        )
        session.commit()
        scan_id = scan_session.id

    resumed_response = client.post(
        "/scan-folder",
        params={"folder_path": str(tmp_path), "resume": "true"},
    )
    resumed_data = resumed_response.json()
    resumed_status = wait_for_scan(resumed_data["scan_id"])

    assert resumed_response.status_code == 200
    assert resumed_data["scan_id"] == scan_id
    assert resumed_status["status"] == "completed"
    assert resumed_status["new_files"] == 1
    assert resumed_status["updated_files"] == 0
    assert resumed_status["skipped_files"] == 1
    assert resumed_status["failed_files"] == 0


def test_running_scan_blocks_duplicate_start(tmp_path: Path, monkeypatch) -> None:
    image_file = tmp_path / "photo.jpg"
    image_file.write_text("image")

    original_build_file_metadata = main_module.build_file_metadata

    def slow_build_file_metadata(path: Path) -> dict[str, object]:
        time.sleep(0.2)
        return original_build_file_metadata(path)

    monkeypatch.setattr(
        main_module,
        "build_file_metadata",
        slow_build_file_metadata,
    )

    first_response = client.post("/scan-folder", params={"folder_path": str(tmp_path)})
    first_data = first_response.json()

    assert first_response.status_code == 200

    duplicate_response = client.post("/scan-folder", params={"folder_path": str(tmp_path)})

    assert duplicate_response.status_code == 409
    assert "already running" in duplicate_response.json()["detail"]

    monkeypatch.setattr(
        main_module,
        "build_file_metadata",
        original_build_file_metadata,
    )
    wait_for_scan(first_data["scan_id"])
