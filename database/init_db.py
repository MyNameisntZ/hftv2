from sqlalchemy import text

from database.base import Base
from database.session import engine
from utils.preferences import ensure_strategy_defaults

# Import models so metadata is registered.
from database import models  # noqa: F401


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_strategy_defaults()

    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))

