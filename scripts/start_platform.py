from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import app as fastapi_app
from config.settings import settings


if __name__ == "__main__":
    uvicorn.run(
        fastapi_app,
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )

