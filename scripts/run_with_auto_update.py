from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from config.settings import settings
from utils.git_updates import UPDATE_REQUEST_FILE, clear_update_request


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

START_SCRIPT = PROJECT_ROOT / "scripts" / "start_platform.py"
HEALTH_URL = "http://127.0.0.1:8000/health"
DEFAULT_CHECK_INTERVAL_SECONDS = 60
DEPENDENCY_FILES = {"pyproject.toml", "requirements.txt"}


def _truthy(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _run_command(command: list[str], *, check: bool = False, capture_output: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=capture_output,
        check=check,
    )


def _run_git(*args: str, check: bool = False) -> subprocess.CompletedProcess | None:
    if not (PROJECT_ROOT / ".git").exists():
        return None
    try:
        return _run_command(["git", *args], check=check)
    except OSError:
        return None


def _git_stdout(*args: str) -> str | None:
    result = _run_git(*args)
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _is_git_checkout() -> bool:
    return (PROJECT_ROOT / ".git").exists()


def _is_git_dirty() -> bool:
    result = _run_git("status", "--porcelain")
    return bool(result and result.stdout.strip())


def _has_upstream() -> bool:
    return _git_stdout("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") is not None


def _fetch_remote() -> bool:
    result = _run_git("fetch", "--quiet")
    return result is not None and result.returncode == 0


def _pending_update_files() -> list[str]:
    result = _run_git("diff", "--name-only", "HEAD", "@{u}")
    if result is None or result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _is_behind_upstream() -> bool:
    local_head = _git_stdout("rev-parse", "HEAD")
    upstream_head = _git_stdout("rev-parse", "@{u}")
    return bool(local_head and upstream_head and local_head != upstream_head)


def _install_dependencies(python_executable: str) -> None:
    print("Detected dependency file changes. Refreshing Python environment...")
    result = _run_command([python_executable, "-m", "pip", "install", "-e", "."], capture_output=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError("Dependency refresh failed after pulling the latest code.")


def _wait_for_health(timeout_seconds: int = 45) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=3) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1)
    return False


class PlatformSupervisor:
    def __init__(
        self,
        python_executable: str,
        open_browser: bool,
        check_interval_seconds: int,
        auto_apply_enabled: bool,
    ) -> None:
        self.python_executable = python_executable
        self.open_browser = open_browser
        self.check_interval_seconds = max(15, check_interval_seconds)
        self.auto_apply_enabled = auto_apply_enabled
        self.process: subprocess.Popen | None = None
        self.browser_opened = False

    def start_backend(self) -> None:
        print("Starting trading platform backend...")
        self.process = subprocess.Popen(
            [self.python_executable, str(START_SCRIPT)],
            cwd=PROJECT_ROOT,
        )

    def stop_backend(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return

        print("Stopping backend for refresh...")
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)

    def ensure_browser_open(self) -> None:
        if self.browser_opened or not self.open_browser:
            return
        if _wait_for_health():
            webbrowser.open("http://127.0.0.1:8000/")
            self.browser_opened = True
        else:
            print("Backend did not report healthy within the expected window.")

    def sync_with_remote(self, *, apply_update: bool) -> bool:
        if not _is_git_checkout():
            print("Auto update is disabled because this folder is not a git clone yet.")
            return False
        if not _has_upstream():
            print("Auto update is disabled because the current branch has no upstream remote.")
            return False
        if _is_git_dirty():
            print("Skipping auto update because the working tree has local changes.")
            return False
        if not _fetch_remote():
            print("Git fetch failed. Keeping the current local version.")
            return False
        if not _is_behind_upstream():
            clear_update_request()
            return False
        if not apply_update:
            print("Git update detected. Waiting for an in-app approval before applying it.")
            return False

        changed_files = _pending_update_files()
        print("New Git revision detected. Pulling latest changes...")
        result = _run_git("pull", "--ff-only")
        if result is None or result.returncode != 0:
            print((result.stdout if result else "").strip())
            print((result.stderr if result else "").strip())
            print("Git pull failed. Keeping the existing backend process running.")
            return False

        if any(Path(path).name in DEPENDENCY_FILES for path in changed_files):
            _install_dependencies(self.python_executable)

        print("Code updated from Git. Restarting backend...")
        clear_update_request()
        return True

    def update_requested(self) -> bool:
        return UPDATE_REQUEST_FILE.exists()

    def run(self) -> None:
        try:
            self.sync_with_remote(apply_update=self.auto_apply_enabled)
            self.start_backend()
            self.ensure_browser_open()
            next_update_check = time.time() + self.check_interval_seconds

            while True:
                if self.process is not None and self.process.poll() is not None:
                    print("Backend exited. Restarting in 2 seconds...")
                    time.sleep(2)
                    self.start_backend()
                    self.ensure_browser_open()
                    next_update_check = time.time() + self.check_interval_seconds

                if self.update_requested():
                    try:
                        should_restart = self.sync_with_remote(apply_update=True)
                    except RuntimeError as error:
                        print(str(error))
                        should_restart = False
                    if should_restart:
                        self.stop_backend()
                        self.start_backend()
                        self.ensure_browser_open()
                    next_update_check = time.time() + self.check_interval_seconds

                if time.time() >= next_update_check:
                    try:
                        should_restart = self.sync_with_remote(
                            apply_update=self.auto_apply_enabled or self.update_requested()
                        )
                    except RuntimeError as error:
                        print(str(error))
                        should_restart = False
                    if should_restart:
                        self.stop_backend()
                        self.start_backend()
                        self.ensure_browser_open()
                    next_update_check = time.time() + self.check_interval_seconds

                time.sleep(2)
        except KeyboardInterrupt:
            print("Shutting down platform supervisor...")
        finally:
            self.stop_backend()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the trading platform with optional Git auto-update.")
    parser.add_argument("--open-browser", action="store_true", help="Open the local dashboard in a browser once healthy.")
    args = parser.parse_args()

    auto_update_enabled = _truthy(os.getenv("GIT_AUTO_UPDATE_ENABLED"), default=True)
    auto_apply_enabled = _truthy(os.getenv("GIT_AUTO_APPLY_ENABLED"), default=False)
    check_interval_seconds = int(os.getenv("GIT_AUTO_UPDATE_INTERVAL_SECONDS", DEFAULT_CHECK_INTERVAL_SECONDS))
    settings.local_state_dir.mkdir(parents=True, exist_ok=True)

    supervisor = PlatformSupervisor(
        python_executable=sys.executable,
        open_browser=args.open_browser,
        check_interval_seconds=check_interval_seconds,
        auto_apply_enabled=auto_apply_enabled,
    )

    if not auto_update_enabled:
        supervisor.start_backend()
        supervisor.ensure_browser_open()
        try:
            while supervisor.process is not None and supervisor.process.poll() is None:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down platform launcher...")
        finally:
            supervisor.stop_backend()
        return 0

    supervisor.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
