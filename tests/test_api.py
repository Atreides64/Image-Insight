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
    assert data["app_version"] == "0.8.0"
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
        "file_type_counts",
        "top_cameras",
        "top_lenses",
        "top_focal_lengths",
        "photos_by_year",
        "photos_by_month",
        "photo_timeline",
        "busiest_date",
        "newest_modified_at",
        "oldest_modified_at",
    }
    assert isinstance(data["total_photos"], int)
    assert isinstance(data["total_size_bytes"], int)
    assert isinstance(data["file_type_counts"], dict)
    assert isinstance(data["top_cameras"], list)
    assert isinstance(data["top_lenses"], list)
    assert isinstance(data["top_focal_lengths"], list)
    assert isinstance(data["photos_by_year"], list)
    assert isinstance(data["photos_by_month"], list)
    assert isinstance(data["photo_timeline"], list)


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
    assert scan_status["files_seen"] == 4
    assert scan_status["image_files_matched"] == 3
    assert scan_status["new_files"] == 3
    assert scan_status["updated_files"] == 0
    assert scan_status["skipped_files"] == 1
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
    assert second_scan_status["skipped_files"] == 4
    assert second_scan_status["failed_files"] == 0


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
    assert {"label": "Canon EOS R5", "count": 1} in stats_data["top_cameras"]
    assert {"label": "RF50mm F1.8 STM", "count": 1} in stats_data["top_lenses"]
    assert {"label": "50mm", "count": 1} in stats_data["top_focal_lengths"]
    assert {"label": "2024", "count": 1} in stats_data["photos_by_year"]
    assert {"label": "2024-07", "count": 1} in stats_data["photos_by_month"]
    assert {
        "label": "2024-07",
        "count": 1,
        "top_camera": "Canon EOS R5",
        "top_lens": "RF50mm F1.8 STM",
    } in stats_data["photo_timeline"]
    assert stats_data["busiest_date"] == {"label": "2024-07-14", "count": 1}


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
    assert [photo["filename"] for photo in data["results"]] == ["canon-wide.jpg"]

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


def test_search_photos_pagination_defaults_and_caps() -> None:
    default_response = client.get("/photos/search")
    capped_response = client.get(
        "/photos/search",
        params={"limit": 999},
    )

    default_data = default_response.json()
    capped_data = capped_response.json()

    assert default_response.status_code == 200
    assert set(default_data) == {"total_count", "limit", "offset", "results"}
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
