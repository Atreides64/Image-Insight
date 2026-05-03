import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

test_db_dir = tempfile.TemporaryDirectory()
test_db_path = Path(test_db_dir.name) / "image_insight_test.db"
os.environ["IMAGE_INSIGHT_DATABASE_URL"] = f"sqlite:///{test_db_path}"

from fastapi.testclient import TestClient  # noqa: E402

from app import main as main_module  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Photo, ScanSession, ScanSessionFile  # noqa: E402

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_stats_returns_valid_json_structure() -> None:
    response = client.get("/stats")

    assert response.status_code == 200
    data = response.json()

    assert set(data) == {
        "total_photos",
        "total_size_bytes",
        "file_type_counts",
        "newest_modified_at",
        "oldest_modified_at",
    }
    assert isinstance(data["total_photos"], int)
    assert isinstance(data["total_size_bytes"], int)
    assert isinstance(data["file_type_counts"], dict)


def test_scan_folder_creates_completed_scan_session(tmp_path: Path) -> None:
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

    response = client.get("/scan-folder", params={"folder_path": str(tmp_path)})

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "completed"
    assert data["total_files"] == 3
    assert data["files_seen"] == 4
    assert data["image_files_matched"] == 3
    assert data["new_files"] == 3
    assert data["updated_files"] == 0
    assert data["skipped_files"] == 1
    assert data["failed_files"] == 0
    assert data["folder_path"] == str(tmp_path)
    assert data["elapsed_seconds"] >= 0
    assert "files" not in data

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

    response_with_files = client.get(
        "/scan-folder",
        params={"folder_path": str(tmp_path), "include_files": "true"},
    )

    assert response_with_files.status_code == 200
    data_with_files = response_with_files.json()
    returned_paths = {file["path"] for file in data_with_files["files"]}

    assert data_with_files["total_files"] == 3
    assert data_with_files["files_seen"] == 4
    assert data_with_files["image_files_matched"] == 3
    assert data_with_files["new_files"] == 0
    assert data_with_files["updated_files"] == 0
    assert data_with_files["skipped_files"] == 4
    assert data_with_files["failed_files"] == 0
    assert returned_paths == {str(path) for path in image_files}


def test_scan_folder_counts_changed_files_as_updated(tmp_path: Path) -> None:
    image_file = tmp_path / "photo.jpg"
    image_file.write_text("first version")

    first_response = client.get("/scan-folder", params={"folder_path": str(tmp_path)})
    first_data = first_response.json()

    assert first_response.status_code == 200
    assert first_data["new_files"] == 1
    assert first_data["updated_files"] == 0
    assert first_data["skipped_files"] == 0

    image_file.write_text("second version with changes")

    second_response = client.get("/scan-folder", params={"folder_path": str(tmp_path)})
    second_data = second_response.json()

    assert second_response.status_code == 200
    assert second_data["new_files"] == 0
    assert second_data["updated_files"] == 1
    assert second_data["skipped_files"] == 0


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

    failed_response = client.get("/scan-folder", params={"folder_path": str(tmp_path)})

    assert failed_response.status_code == 500
    assert "Scan failed" in failed_response.json()["detail"]

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

    resumed_response = client.get(
        "/scan-folder",
        params={"folder_path": str(tmp_path), "resume": "true"},
    )
    resumed_data = resumed_response.json()

    assert resumed_response.status_code == 200
    assert resumed_data["scan_id"] == failed_session["scan_id"]
    assert resumed_data["status"] == "completed"
    assert resumed_data["new_files"] == 1
    assert resumed_data["updated_files"] == 0
    assert resumed_data["skipped_files"] == 1
    assert resumed_data["failed_files"] == 0


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

    resumed_response = client.get(
        "/scan-folder",
        params={"folder_path": str(tmp_path), "resume": "true"},
    )
    resumed_data = resumed_response.json()

    assert resumed_response.status_code == 200
    assert resumed_data["scan_id"] == scan_id
    assert resumed_data["status"] == "completed"
    assert resumed_data["new_files"] == 1
    assert resumed_data["updated_files"] == 0
    assert resumed_data["skipped_files"] == 1
    assert resumed_data["failed_files"] == 0
