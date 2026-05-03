import os
import tempfile
from pathlib import Path

test_db_dir = tempfile.TemporaryDirectory()
test_db_path = Path(test_db_dir.name) / "image_insight_test.db"
os.environ["IMAGE_INSIGHT_DATABASE_URL"] = f"sqlite:///{test_db_path}"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

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


def test_scan_folder_with_temporary_image_files(tmp_path: Path) -> None:
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

    assert data["total_files"] == 3
    assert data["new_files"] == 3
    assert data["updated_files"] == 0
    assert data["skipped_files"] == 0
    assert data["folder_path"] == str(tmp_path)
    assert data["elapsed_seconds"] >= 0
    assert "files" not in data

    response_with_files = client.get(
        "/scan-folder",
        params={"folder_path": str(tmp_path), "include_files": "true"},
    )

    assert response_with_files.status_code == 200
    data_with_files = response_with_files.json()
    returned_paths = {file["path"] for file in data_with_files["files"]}

    assert data_with_files["total_files"] == 3
    assert data_with_files["new_files"] == 0
    assert data_with_files["updated_files"] == 3
    assert data_with_files["skipped_files"] == 0
    assert returned_paths == {str(path) for path in image_files}

    stats_response = client.get("/stats")
    stats = stats_response.json()

    assert stats_response.status_code == 200
    assert stats["total_photos"] >= 3
    assert stats["file_type_counts"]["jpg"] >= 1
    assert stats["file_type_counts"]["png"] >= 1
    assert stats["file_type_counts"]["raf"] >= 1
