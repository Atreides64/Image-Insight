import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = REPO_ROOT / "image_insight.db"
DATABASE_URL = os.getenv(
    "IMAGE_INSIGHT_DATABASE_URL",
    f"sqlite:///{DEFAULT_DATABASE_PATH}",
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
