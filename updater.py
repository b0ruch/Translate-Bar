# SPDX-License-Identifier: MIT
"""Translate Bar update check and install via GitHub Releases.

AppKit-free: everything UI-related lives in menubar.py. Network failures,
corrupt images and an impossible self-replace are returned as statuses, not
exceptions — the caller simply renders text.

The check goes through api.github.com (60 unauthenticated requests per hour per
IP, we need one a day) — no token required.
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
    """'v1.2.0' -> (1, 2, 0). A pre-release suffix is dropped."""
    match = _VERSION_RE.search(str(value).strip().lstrip("vV"))
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def _pad(parts: tuple[int, ...], size: int) -> tuple[int, ...]:
    return parts + (0,) * (size - len(parts))


def is_newer(remote: str, current: str) -> bool:
    """Tuple comparison: (1, 2) == (1, 2, 0), (1, 10) > (1, 9)."""
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
    """Result: status = "update" | "current" | "error"."""
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
    """The user cancelled the download."""


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
    """Download the image to dest.part, verify sha256 and rename it.

    progress(downloaded, total) is called along the way. cancelled() -> bool
    lets the caller abort; an incomplete .part stays on disk and is reused on
    the next attempt.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    # Resume: GitHub sends Accept-Ranges, but starting over is simpler and safer
    # when the size does not match — the images are small (~26 MB).
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
    """Mount the image and check that it contains our bundle at the right version.

    Returns {"ok": True, "mount": str, "app": str, "version": str} or
    {"ok": False, "error": str}. The image stays mounted — the caller is
    responsible for detaching it (updater.unmount).
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
    """Path to the .app if the app was launched from a built bundle."""
    if not getattr(sys, "frozen", False):
        return None
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None


def can_self_update(bundle: Path | None = None) -> bool:
    """Whether the bundle can be replaced in place: a built app and we have rights."""
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
    """Spawn the helper that replaces the bundle after this app exits.

    Returns immediately: the caller must terminate the process, otherwise the
    helper waits forever.
    """
    script = Path(tempfile.mkdtemp(prefix="translatebar-update-")) / "install.sh"
    script.write_text(_HELPER.format(**{"src": _q(source_app)}), encoding="utf-8")
    log = script.with_suffix(".log")
    with log.open("wb") as log_fh:
        subprocess.Popen(
            # Paths are passed as argv entries verbatim: quoting is only needed
            # inside the script text ({src}), not in argv.
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

# Wait for the app to exit: replacing a live bundle is unreliable.
# Time limit: a zombie process also answers kill -0, and the helper must not
# hang forever.
i=0
while kill -0 "$PID" 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -gt 400 ]; then break; fi
  sleep 0.3
done

trap restore EXIT

rm -rf "$NEW" "$OLD" 2>/dev/null || true
# ditto into a copy next to the target: mv then stays within one volume.
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
