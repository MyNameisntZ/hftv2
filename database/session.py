import shutil
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import (
    DEFAULT_DATABASE_URL,
    DEFAULT_LOCAL_DATABASE_PATH,
    LEGACY_DATABASE_PATH,
    settings,
)


def _sqlite_db_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    raw_path = database_url.removeprefix("sqlite:///")
    return Path(raw_path)


def _prepare_sqlite_storage() -> None:
    sqlite_path = _sqlite_db_path(settings.database_url)
    if sqlite_path is None:
        return

    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    if (
        settings.database_url == DEFAULT_DATABASE_URL
        and LEGACY_DATABASE_PATH.exists()
        and not DEFAULT_LOCAL_DATABASE_PATH.exists()
    ):
        shutil.copy2(LEGACY_DATABASE_PATH, DEFAULT_LOCAL_DATABASE_PATH)


_prepare_sqlite_storage()


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, future=True, echo=False, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

