#!/usr/bin/env python3
"""Проверка, что все бинарные зависимости в окружении содержат нужные архитектуры.

Использование:
    .venv-universal/bin/python check_universal2.py

Нужен перед сборкой universal2: PyInstaller требует, чтобы каждый
расширяемый модуль (*.so) содержал и x86_64, и arm64. Если хоть один
thin — сборка упадёт с IncompatibleBinaryArchError, и этот скрипт
покажет, какой именно пакет виноват.
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
        print("Не найдено ни одного .so — окружение пустое?")
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
    print(f"Всего .so: {len(binaries)}; проблемных: {len(bad)}")
    if bad:
        print("\nЭти пакеты собраны под одну архитектуру:")
        for path, found in bad:
            pkg = path.relative_to(root).parts[2] if len(path.relative_to(root).parts) > 2 else "?"
            print(f"  - {pkg}: {sorted(found)}")
        return 1
    print("Все зависимости universal2 — можно собирать.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
