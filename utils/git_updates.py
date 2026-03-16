from __future__ import annotations

import subprocess
import time
from pathlib import Path

from config.settings import ROOT_DIR, settings


UPDATE_REQUEST_FILE = settings.local_state_dir / "git_update_requested.flag"
FETCH_CACHE_TTL_SECONDS = 45
MAX_PENDING_COMMITS = 8
MAX_CHANGED_FILES = 20

_last_fetch_attempt = 0.0


def _run_git(*args: str) -> subprocess.CompletedProcess | None:
    git_dir = ROOT_DIR / ".git"
    if not git_dir.exists():
        return None

    try:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None


def _git_stdout(*args: str) -> str | None:
    result = _run_git(*args)
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _has_upstream() -> bool:
    return _git_stdout("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") is not None


def _is_dirty() -> bool:
    result = _run_git("status", "--porcelain")
    return bool(result and result.stdout.strip())


def fetch_remote_if_needed(force: bool = False) -> bool:
    global _last_fetch_attempt

    now = time.time()
    if not force and now - _last_fetch_attempt < FETCH_CACHE_TTL_SECONDS:
        return True
    _last_fetch_attempt = now

    result = _run_git("fetch", "--quiet")
    return result is not None and result.returncode == 0


def _pending_commits() -> list[dict]:
    result = _run_git(
        "log",
        "--format=%H%x1f%h%x1f%an%x1f%ad%x1f%s",
        f"-n{MAX_PENDING_COMMITS}",
        "HEAD..@{u}",
    )
    if result is None or result.returncode != 0:
        return []

    commits = []
    for line in result.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 5:
            continue
        full_hash, short_hash, author, authored_at, subject = parts
        commits.append(
            {
                "hash": full_hash,
                "short_hash": short_hash,
                "author": author,
                "authored_at": authored_at,
                "subject": subject,
            }
        )
    return commits


def _changed_files() -> list[str]:
    result = _run_git("diff", "--name-only", "HEAD", "@{u}")
    if result is None or result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()][:MAX_CHANGED_FILES]


def get_git_update_status(force_fetch: bool = False) -> dict:
    if not (ROOT_DIR / ".git").exists():
        return {
            "available": False,
            "can_apply": False,
            "reason": "not_git_checkout",
            "message": "This workstation is not running from a git clone.",
            "pending_commits": [],
            "changed_files": [],
            "update_requested": UPDATE_REQUEST_FILE.exists(),
        }

    if not _has_upstream():
        return {
            "available": False,
            "can_apply": False,
            "reason": "no_upstream",
            "message": "The current branch has no upstream remote configured.",
            "pending_commits": [],
            "changed_files": [],
            "update_requested": UPDATE_REQUEST_FILE.exists(),
        }

    fetch_ok = fetch_remote_if_needed(force_fetch)
    local_head = _git_stdout("rev-parse", "HEAD")
    upstream_head = _git_stdout("rev-parse", "@{u}")
    is_dirty = _is_dirty()
    available = bool(local_head and upstream_head and local_head != upstream_head)
    pending_commits = _pending_commits() if available else []
    changed_files = _changed_files() if available else []

    if not fetch_ok:
        message = "Could not refresh remote git metadata from GitHub."
    elif available:
        message = f"{len(pending_commits)} incoming commit(s) available from GitHub."
    else:
        message = "This workstation is up to date."

    if is_dirty and available:
        message = "Incoming changes detected, but this workstation has local uncommitted changes."

    return {
        "available": available,
        "can_apply": available and not is_dirty,
        "reason": "dirty_worktree" if is_dirty and available else None,
        "message": message,
        "current_commit": local_head,
        "upstream_commit": upstream_head,
        "pending_commits": pending_commits,
        "changed_files": changed_files,
        "update_requested": UPDATE_REQUEST_FILE.exists(),
        "fetch_ok": fetch_ok,
        "is_dirty": is_dirty,
    }


def request_git_update() -> dict:
    status = get_git_update_status(force_fetch=True)
    if not status.get("available"):
        return {
            **status,
            "requested": False,
            "message": "No incoming git update is currently available.",
        }
    if not status.get("can_apply"):
        return {
            **status,
            "requested": False,
            "message": "This workstation cannot apply the update until local changes are committed or stashed.",
        }

    UPDATE_REQUEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    UPDATE_REQUEST_FILE.write_text(str(time.time()), encoding="utf-8")
    return {
        **status,
        "requested": True,
        "update_requested": True,
        "message": "Update requested. The launcher will pull the new revision and restart the backend shortly.",
    }


def clear_update_request() -> None:
    if UPDATE_REQUEST_FILE.exists():
        UPDATE_REQUEST_FILE.unlink()
