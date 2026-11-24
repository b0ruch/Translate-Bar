#!/usr/bin/env python3
"""Verify that every binary dependency in the environment carries the needed architectures.

Usage:
    .venv-universal/bin/python check_universal2.py

Required before a universal2 build: PyInstaller demands that every extension
module (*.so) contains both x86_64 and arm64. If even one is thin, the build
fails with IncompatibleBinaryArchError, and this script shows which package is
to blame.
"""

import subprocess
import sys
from pathlib import Path

REQUIRED = {"x86_64", "arm64"}


def archs(path: Path) -> set[str]:
    out = subprocess.run(
        ["lipo", "-archs", str(path)], capture_output=True, text=True
    ).stdout.strip()
    return set(out.split()) if out else set()


def main() -> int:
    root = Path(sys.prefix) / "lib"
    binaries = [
        p
        for p in root.rglob("*.so")
        if "dSYM" not in str(p) and "PyObjCTest" not in str(p)
    ]
    if not binaries:
        print("No .so files found — is the environment empty?")
        return 1

    bad: list[tuple[Path, set[str]]] = []
    for path in sorted(binaries):
        found = archs(path)
        status = "OK " if REQUIRED <= found else "THIN"
        rel = path.relative_to(root)
        print(f"{status} {' '.join(sorted(found)):>14}  {rel}")
        if not REQUIRED <= found:
            bad.append((path, found))

    print()
    print(f"Total .so: {len(binaries)}; problematic: {len(bad)}")
    if bad:
        print("\nThese packages are built for a single architecture:")
        for path, found in bad:
            pkg = path.relative_to(root).parts[2] if len(path.relative_to(root).parts) > 2 else "?"
            print(f"  - {pkg}: {sorted(found)}")
        return 1
    print("All dependencies are universal2 — ready to build.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
