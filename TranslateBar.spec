# SPDX-License-Identifier: MIT
# -*- mode: python ; coding: utf-8 -*-
"""Сборка Translate Bar.

arm64 (по умолчанию):
    ./.venv/bin/python -m pip install -r requirements-build.txt
    ./.venv/bin/pyinstaller -y TranslateBar.spec

universal2 (нужен universal2-Python от python.org, см. README):
    TARGET_ARCH=universal2 ./.venv-universal/bin/pyinstaller -y TranslateBar.spec
"""

import os
import sys

from PyInstaller.utils.hooks import collect_data_files

# Версия живёт в version.py, чтобы не дублироваться с menubar.py.
if SPECPATH not in sys.path:
    sys.path.insert(0, SPECPATH)
from version import APP_VERSION  # noqa: E402

# PyInstaller does not cross-compile: target_arch only validates/selects the
# architecture slices of already-built binaries. Building universal2 or x86_64
# requires an appropriately built Python environment.
TARGET_ARCH = os.environ.get("TARGET_ARCH", "arm64")
if TARGET_ARCH not in ("arm64", "x86_64", "universal2"):
    raise SystemExit(
        "TARGET_ARCH must be one of arm64, x86_64, universal2; got %r" % (TARGET_ARCH,)
    )

datas = collect_data_files("langdetect")

a = Analysis(
    ["menubar.py"],
    pathex=[SPECPATH],
    binaries=[],
    datas=datas,
    hiddenimports=["ServiceManagement"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Translate Bar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=TARGET_ARCH,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Translate Bar",
)
app = BUNDLE(
    coll,
    name="Translate Bar.app",
    icon="assets/icon.icns",
    bundle_identifier="com.translatebar.menubar",
    info_plist={
        "CFBundleDisplayName": "Translate Bar",
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
        "CFBundleURLTypes": [
            {
                "CFBundleURLName": "com.translatebar.menubar.translate",
                "CFBundleURLSchemes": ["translatebar"],
            },
        ],
    },
)
