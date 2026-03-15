from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from config.settings import ROOT_DIR


STARTUP_INSTANCE_ID = uuid4().hex
STARTED_AT = datetime.now(timezone.utc).isoformat()


def _run_git_command(*args: str) -> str | None:
    git_dir = ROOT_DIR / ".git"
    if not git_dir.exists():
        return None

    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None

    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def get_runtime_version() -> dict:
    commit = _run_git_command("rev-parse", "HEAD")
    short_commit = _run_git_command("rev-parse", "--short", "HEAD")
    branch = _run_git_command("rev-parse", "--abbrev-ref", "HEAD")

    return {
        "startup_instance_id": STARTUP_INSTANCE_ID,
        "started_at": STARTED_AT,
        "git_branch": branch,
        "git_commit": commit,
        "git_commit_short": short_commit,
        "is_git_checkout": (ROOT_DIR / ".git").exists(),
        "project_root": str(Path(ROOT_DIR)),
    }
