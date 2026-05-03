from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    extension: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScanSession(Base):
    __tablename__ = "scan_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    folder_path: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    files_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_files_matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScanSessionFile(Base):
    __tablename__ = "scan_session_files"
    __table_args__ = (
        UniqueConstraint("scan_session_id", "path", name="uq_scan_session_file_path"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scan_session_id: Mapped[int] = mapped_column(
        ForeignKey("scan_sessions.id"),
        nullable=False,
        index=True,
    )
    path: Mapped[str] = mapped_column(String, nullable=False)
