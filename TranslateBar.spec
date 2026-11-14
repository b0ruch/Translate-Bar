# SPDX-License-Identifier: MIT
# -*- mode: python ; coding: utf-8 -*-
"""Сборка Translate Bar: ./.venv/bin/python -m pip install -r requirements-build.txt && ./.venv/bin/pyinstaller TranslateBar.spec"""

import os
from PyInstaller.utils.hooks import collect_data_files

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
    pathex=[],
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
        "CFBundleShortVersionString": "1.2.0",
        "CFBundleVersion": "1.2.0",
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
