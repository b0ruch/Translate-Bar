# SPDX-License-Identifier: MIT
"""Translate Bar data paths (Application Support + migration from the project folder)."""

from pathlib import Path

APP_DIR_NAME = "Translate Bar"

_migrated = False


def project_dir() -> Path:
    return Path(__file__).parent


def data_dir() -> Path:
    target = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    target.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_files(target)
    return target


def _migrate_legacy_files(target: Path) -> None:
    global _migrated
    if _migrated:
        return
    _migrated = True
    legacy = project_dir()
    if legacy == target:
        return
    for name in ("history.json", "settings.json"):
        src = legacy / name
        dst = target / name
        try:
            if src.exists() and not dst.exists():
                dst.write_bytes(src.read_bytes())
        except OSError:
            pass


def history_path() -> Path:
    return data_dir() / "history.json"


def settings_path() -> Path:
    return data_dir() / "settings.json"


def updates_dir() -> Path:
    """Downloaded update images.

    Not ~/Downloads: that folder is TCC-protected, so the app would trigger a
    system permission prompt on the first download.
    """
    target = data_dir() / "updates"
    target.mkdir(parents=True, exist_ok=True)
    return target
