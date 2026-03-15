import logging
from logging.config import dictConfig

from config.settings import settings


def configure_logging() -> None:
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "level": settings.log_level,
                },
                "file": {
                    "class": "logging.FileHandler",
                    "filename": str(settings.logs_dir / "platform.log"),
                    "formatter": "standard",
                    "level": settings.log_level,
                },
            },
            "root": {
                "handlers": ["console", "file"],
                "level": settings.log_level,
            },
        }
    )

    logging.getLogger(__name__).info("Logging configured")

