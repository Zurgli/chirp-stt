from __future__ import annotations

import argparse
import contextlib
import ctypes
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence

from .config_manager import PROJECT_ROOT

WATCH_EXTENSIONS = {".py", ".toml", ".bat"}
IGNORED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
IGNORED_PATH_PARTS = {("src", "chirp", "assets", "models")}
DEV_MUTEX_NAME = "Local\\ChirpDevSingleton"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chirp-dev",
        description="Run Chirp in development mode and restart when repo files change.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds between file change scans (default: 1.0).",
    )
    parser.add_argument(
        "chirp_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to Chirp. Use '-- --verbose' to pass flags through.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = _build_parser().parse_args(argv)
    forwarded_args = list(args.chirp_args)
    if forwarded_args and forwarded_args[0] == "--":
        forwarded_args = forwarded_args[1:]

    with _dev_singleton():
        snapshot = _snapshot_repo(PROJECT_ROOT)
        child = _start_child(forwarded_args)
        print("chirp-dev: watching repo for changes", flush=True)

        try:
            while True:
                time.sleep(max(0.1, args.interval))

                if child.poll() is not None:
                    print("chirp-dev: app exited; restarting", flush=True)
                    child = _start_child(forwarded_args)
                    snapshot = _snapshot_repo(PROJECT_ROOT)
                    continue

                new_snapshot = _snapshot_repo(PROJECT_ROOT)
                changed = _detect_changes(snapshot, new_snapshot)
                if changed:
                    print(f"chirp-dev: change detected in {changed}; restarting", flush=True)
                    _stop_child(child)
                    child = _start_child(forwarded_args)
                    snapshot = new_snapshot
        except KeyboardInterrupt:
            print("chirp-dev: stopping", flush=True)
        finally:
            _stop_child(child)


@contextlib.contextmanager
def _dev_singleton():
    if os.name != "nt":
        yield
        return

    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, DEV_MUTEX_NAME)
    if not mutex:
        raise OSError("chirp-dev: failed to create singleton mutex")
    if kernel32.GetLastError() == 183:
        kernel32.CloseHandle(mutex)
        raise SystemExit("chirp-dev: another dev runner is already active")

    try:
        yield
    finally:
        kernel32.ReleaseMutex(mutex)
        kernel32.CloseHandle(mutex)


def _start_child(chirp_args: Sequence[str]) -> subprocess.Popen[str]:
    command = [sys.executable, "-m", "chirp.main", *chirp_args]
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(command, cwd=PROJECT_ROOT, creationflags=creationflags)


def _stop_child(process: subprocess.Popen[str], timeout: float = 5.0) -> None:
    if process.poll() is not None:
        return

    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
        process.wait(timeout=timeout)
    except Exception:
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=timeout)


def _detect_changes(
    old_snapshot: Dict[str, tuple[int, int]],
    new_snapshot: Dict[str, tuple[int, int]],
) -> Optional[str]:
    old_paths = set(old_snapshot)
    new_paths = set(new_snapshot)

    removed = sorted(old_paths - new_paths)
    if removed:
        return removed[0]

    added = sorted(new_paths - old_paths)
    if added:
        return added[0]

    for path in sorted(old_paths & new_paths):
        if old_snapshot[path] != new_snapshot[path]:
            return path

    return None


def _snapshot_repo(root: Path) -> Dict[str, tuple[int, int]]:
    snapshot: Dict[str, tuple[int, int]] = {}
    for path in _iter_watch_files(root):
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshot[str(path.relative_to(root))] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _iter_watch_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        current_dir = Path(dirpath)
        relative_parts = current_dir.relative_to(root).parts

        dirnames[:] = [
            name
            for name in dirnames
            if name not in IGNORED_DIRS
            and (*relative_parts, name) not in IGNORED_PATH_PARTS
        ]

        for filename in filenames:
            path = current_dir / filename
            if _should_watch(path, root):
                yield path


def _should_watch(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    if any(part in IGNORED_DIRS for part in relative_parts):
        return False
    if any(
        relative_parts[: len(ignored_parts)] == ignored_parts
        for ignored_parts in IGNORED_PATH_PARTS
    ):
        return False
    return path.suffix.lower() in WATCH_EXTENSIONS
