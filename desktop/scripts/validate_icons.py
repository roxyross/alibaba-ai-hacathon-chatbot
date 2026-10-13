#!/usr/bin/env python3
"""Validate desktop application icons for Windows, macOS, and Linux packaging."""

from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image


def validate_icons(resources_dir: Path | None = None) -> bool:
    if resources_dir is None:
        resources_dir = Path(__file__).resolve().parents[1] / "resources"

    if not resources_dir.exists():
        print(f"ERROR: Resources directory not found: {resources_dir}", file=sys.stderr)
        return False

    png_path = resources_dir / "icon.png"
    ico_path = resources_dir / "icon.ico"
    icns_path = resources_dir / "icon.icns"

    for p in (png_path, ico_path, icns_path):
        if not p.exists():
            print(f"ERROR: Missing icon file: {p}", file=sys.stderr)
            return False

    # 1. Linux icon (icon.png)
    try:
        with Image.open(png_path) as img:
            if img.format != "PNG":
                print(f"ERROR: icon.png format is {img.format}, expected PNG", file=sys.stderr)
                return False
            if img.width < 256 or img.height < 256:
                print(f"ERROR: icon.png size {img.size} is less than required 256x256", file=sys.stderr)
                return False
            print(f"SUCCESS: icon.png validated ({img.size}, {img.format})")
    except Exception as exc:
        print(f"ERROR: Failed reading icon.png: {exc}", file=sys.stderr)
        return False

    # 2. Windows icon (icon.ico)
    try:
        with Image.open(ico_path) as img:
            if img.format != "ICO":
                print(f"ERROR: icon.ico format is {img.format}, expected ICO", file=sys.stderr)
                return False
            if img.width < 256 or img.height < 256:
                print(f"ERROR: icon.ico size {img.size} is less than required 256x256", file=sys.stderr)
                return False
            print(f"SUCCESS: icon.ico validated ({img.size}, {img.format})")
    except Exception as exc:
        print(f"ERROR: Failed reading icon.ico: {exc}", file=sys.stderr)
        return False

    # 3. macOS icon (icon.icns)
    try:
        with Image.open(icns_path) as img:
            if img.format != "ICNS":
                print(f"ERROR: icon.icns format is {img.format}, expected ICNS", file=sys.stderr)
                return False
            if img.width < 512 or img.height < 512:
                print(f"ERROR: icon.icns size {img.size} is less than required 512x512", file=sys.stderr)
                return False
            print(f"SUCCESS: icon.icns validated ({img.size}, {img.format})")
    except Exception as exc:
        print(f"ERROR: Failed reading icon.icns: {exc}", file=sys.stderr)
        return False

    print("ALL desktop application icons passed validation!")
    return True


if __name__ == "__main__":
    success = validate_icons()
    sys.exit(0 if success else 1)
