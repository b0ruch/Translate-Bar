# SPDX-License-Identifier: MIT
"""Проверка и установка обновлений Translate Bar через GitHub Releases.

Модуль без AppKit: всё, что касается UI, делает menubar.py. Сетевые ошибки,
битые образы и невозможность самозамены возвращаются как статусы, а не
исключения — вызывающая сторона просто показывает текст.

Проверка идёт через api.github.com (60 неавторизованных запросов в час на IP,
нам нужен один в сутки) — токен не требуется.
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

REPO = "b0ruch/Translate-Bar"
BUNDLE_ID = "com.translatebar.menubar"
APP_BUNDLE_NAME = "Translate Bar.app"

LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASE_TAG_URL = f"https://github.com/{REPO}/releases/tag/"
TIMEOUT = 10
CHUNK = 256 * 1024

_VERSION_RE = re.compile(r"(\d+(?:\.\d+)*)")


def parse_version(value: str) -> tuple[int, ...]:
    """'v1.2.0' -> (1, 2, 0). Пре-релизный суффикс отбрасывается."""
    match = _VERSION_RE.search(str(value).strip().lstrip("vV"))
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def _pad(parts: tuple[int, ...], size: int) -> tuple[int, ...]:
    return parts + (0,) * (size - len(parts))


def is_newer(remote: str, current: str) -> bool:
    """Сравнение кортежами: (1, 2) == (1, 2, 0), (1, 10) > (1, 9)."""
    a, b = parse_version(remote), parse_version(current)
    if not a:
        return False
    size = max(len(a), len(b))
    return _pad(a, size) > _pad(b, size)


def _pick_asset(assets: list) -> dict | None:
    dmgs = [
        a
        for a in assets
        if isinstance(a, dict) and str(a.get("name", "")).lower().endswith(".dmg")
    ]
    if not dmgs:
        return None
    for asset in dmgs:
        if "universal" in str(asset.get("name", "")).lower():
            return asset
    return dmgs[0]


def check_for_update(current: str, timeout: int = TIMEOUT) -> dict:
    """Результат: status = "update" | "current" | "error"."""
    try:
        resp = requests.get(
            LATEST_URL,
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json"},
        )
        if resp.status_code == 404:
            return {"status": "current"}
        if resp.status_code != 200:
            return {"status": "error", "error": f"HTTP {resp.status_code}"}
        data = resp.json()
    except requests.RequestException as exc:
        return {"status": "error", "error": str(exc)}
    except ValueError:
        return {"status": "error", "error": "invalid json"}

    tag = str(data.get("tag_name", ""))
    if not is_newer(tag, current):
        return {"status": "current", "version": tag.lstrip("vV") or current}

    asset = _pick_asset(data.get("assets") or [])
    if asset is None:
        return {
            "status": "error",
            "version": tag.lstrip("vV"),
            "error": "no dmg asset",
            "page": str(data.get("html_url", RELEASE_TAG_URL + tag)),
        }
    digest = str(asset.get("digest") or "")
    return {
        "status": "update",
        "version": tag.lstrip("vV"),
        "url": str(asset.get("browser_download_url", "")),
        "name": str(asset.get("name", "")),
        "size": int(asset.get("size") or 0),
        "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else "",
        "page": str(data.get("html_url", RELEASE_TAG_URL + tag)),
    }


class DownloadCancelled(Exception):
    """Пользователь отменил скачивание."""


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download_update(
    url: str,
    dest: Path,
    expected_sha256: str = "",
    total: int = 0,
    progress=None,
    cancelled=None,
) -> Path:
    """Скачивает образ в dest.part, проверяет sha256 и переименовывает.

    progress(downloaded, total) вызывается по ходу. cancelled() -> bool
    позволяет прервать загрузку; недокачанный .part остаётся на диске и
    переиспользуется при повторной попытке.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    # Докачка: GitHub отдаёт Accept-Ranges, но проще и надёжнее начать заново,
    # если размер не совпадает — образы небольшие (~26 МБ).
    if part.exists() and total and part.stat().st_size == total:
        if not expected_sha256 or _sha256_of(part) == expected_sha256:
            os.replace(part, dest)
            if progress:
                progress(total, total)
            return dest

    downloaded = 0
    try:
        with requests.get(url, stream=True, timeout=TIMEOUT) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}")
            if not total:
                total = int(resp.headers.get("Content-Length") or 0)
            with part.open("wb") as fh:
                for block in resp.iter_content(CHUNK):
                    if cancelled and cancelled():
                        raise DownloadCancelled()
                    if not block:
                        continue
                    fh.write(block)
                    downloaded += len(block)
                    if progress:
                        progress(downloaded, total)
    except requests.RequestException:
        raise RuntimeError("network")

    if expected_sha256 and _sha256_of(part) != expected_sha256:
        try:
            part.unlink()
        except OSError:
            pass
        raise RuntimeError("checksum")
    os.replace(part, dest)
    return dest


def validate_dmg(dmg_path: Path, expected_version: str = "") -> dict:
    """Монтирует образ и проверяет, что внутри наш бандл нужной версии.

    Возвращает {"ok": True, "mount": str, "app": str, "version": str} или
    {"ok": False, "error": str}. Образ остаётся смонтированным — вызывающая
    сторона обязана сделать detach (updater.unmount).
    """
    mount = Path(tempfile.mkdtemp(prefix="translatebar-dmg-"))
    try:
        proc = subprocess.run(
            [
                "hdiutil",
                "attach",
                "-nobrowse",
                "-readonly",
                "-noverify",
                "-mountpoint",
                str(mount),
                str(dmg_path),
            ],
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        shutil.rmtree(mount, ignore_errors=True)
        return {"ok": False, "error": str(exc)}
    if proc.returncode != 0:
        shutil.rmtree(mount, ignore_errors=True)
        return {"ok": False, "error": "attach failed"}

    apps = sorted(p for p in mount.iterdir() if p.suffix == ".app")
    if not apps:
        unmount(mount)
        return {"ok": False, "error": "no app in image"}

    plist_path = apps[0] / "Contents" / "Info.plist"
    try:
        with plist_path.open("rb") as fh:
            info = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException, ValueError):
        unmount(mount)
        return {"ok": False, "error": "bad Info.plist"}

    if str(info.get("CFBundleIdentifier", "")) != BUNDLE_ID:
        unmount(mount)
        return {"ok": False, "error": "wrong bundle id"}

    version = str(info.get("CFBundleShortVersionString", ""))
    if expected_version and parse_version(version) < parse_version(expected_version):
        unmount(mount)
        return {"ok": False, "error": "wrong version"}

    return {"ok": True, "mount": str(mount), "app": str(apps[0]), "version": version}


def unmount(mount) -> None:
    try:
        subprocess.run(
            ["hdiutil", "detach", str(mount), "-force"],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    shutil.rmtree(str(mount), ignore_errors=True)


def app_bundle_path() -> Path | None:
    """Путь до .app, если приложение запущено из собранного бандла."""
    if not getattr(sys, "frozen", False):
        return None
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None


def can_self_update(bundle: Path | None = None) -> bool:
    """Можно ли заменить бандл на месте: собранное приложение и есть права."""
    bundle = bundle or app_bundle_path()
    if bundle is None:
        return False
    parent = bundle.parent
    allowed = {
        Path("/Applications").resolve(),
        (Path.home() / "Applications").resolve(),
    }
    try:
        if parent.resolve() not in allowed:
            return False
    except OSError:
        return False
    return os.access(parent, os.W_OK)


def install_update(mount: str, source_app: str, bundle: Path, dmg: Path) -> None:
    """Запускает helper, который заменит бандл после выхода приложения.

    Возвращает управление сразу: вызывающая сторона должна завершить процесс,
    иначе helper будет ждать вечно.
    """
    script = Path(tempfile.mkdtemp(prefix="translatebar-update-")) / "install.sh"
    script.write_text(_HELPER.format(**{"src": _q(source_app)}), encoding="utf-8")
    log = script.with_suffix(".log")
    with log.open("wb") as log_fh:
        subprocess.Popen(
            # Пути передаются аргументами как есть: кавычки нужны только
            # внутри текста скрипта ({src}), а не в argv.
            ["/bin/sh", str(script), str(os.getpid()), str(mount), str(dmg), str(bundle)],
            stdin=subprocess.DEVNULL,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _q(value: str) -> str:
    return "'" + str(value).replace("'", "'\\''") + "'"


# $1 pid, $2 mount, $3 dmg, $4 bundle
_HELPER = """#!/bin/sh
PID="$1"
MNT="$2"
DMG="$3"
APP="$4"
NEW="$APP.new"
OLD="$APP.old"

detach() {{ hdiutil detach "$MNT" >/dev/null 2>&1 || true; }}

restore() {{
  if [ -d "$OLD" ] && [ ! -d "$APP" ]; then mv "$OLD" "$APP" 2>/dev/null || true; fi
  rm -rf "$NEW" 2>/dev/null || true
  detach
}}

# Ждём выхода приложения: замена живого бандла ненадёжна.
# Ограничение по времени: зомби-процесс тоже отвечает на kill -0, а висеть
# вечно helper не должен.
i=0
while kill -0 "$PID" 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -gt 400 ]; then break; fi
  sleep 0.3
done

trap restore EXIT

rm -rf "$NEW" "$OLD" 2>/dev/null || true
# ditto в копию рядом с целью: mv остаётся в пределах одного тома.
ditto {src} "$NEW" || exit 1
xattr -dr com.apple.quarantine "$NEW" 2>/dev/null || true

mv "$APP" "$OLD" || exit 1
mv "$NEW" "$APP" || exit 1
trap - EXIT

detach
rm -rf "$OLD" 2>/dev/null || true
rm -f "$DMG" 2>/dev/null || true
open "$APP"
"""
