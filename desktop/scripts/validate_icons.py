#!/usr/bin/env python3
"""Validate desktop application icons using only Python standard library (no external dependencies)."""

from __future__ import annotations

import struct
import sys
from pathlib import Path


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
        with open(png_path, "rb") as f:
            header = f.read(24)
            if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
                print(f"ERROR: icon.png is not a valid PNG file", file=sys.stderr)
                return False
            # Width and height are in IHDR chunk at bytes 16..24
            width, height = struct.unpack(">II", header[16:24])
            if width < 256 or height < 256:
                print(f"ERROR: icon.png size {width}x{height} is less than required 256x256", file=sys.stderr)
                return False
            print(f"SUCCESS: icon.png validated ({width}x{height}, PNG)")
    except Exception as exc:
        print(f"ERROR: Failed reading icon.png: {exc}", file=sys.stderr)
        return False

    # 2. Windows icon (icon.ico)
    try:
        with open(ico_path, "rb") as f:
            header = f.read(6)
            if len(header) < 6:
                print("ERROR: icon.ico file too short", file=sys.stderr)
                return False
            reserved, ico_type, count = struct.unpack("<HHH", header)
            if reserved != 0 or ico_type != 1 or count == 0:
                print("ERROR: icon.ico is not a valid ICO file", file=sys.stderr)
                return False

            max_w, max_h = 0, 0
            for _ in range(count):
                entry = f.read(16)
                if len(entry) < 16:
                    break
                w, h = entry[0], entry[1]
                w = 256 if w == 0 else w
                h = 256 if h == 0 else h
                max_w = max(max_w, w)
                max_h = max(max_h, h)

            if max_w < 256 or max_h < 256:
                print(f"ERROR: icon.ico max resolution {max_w}x{max_h} is less than 256x256", file=sys.stderr)
                return False
            print(f"SUCCESS: icon.ico validated (max {max_w}x{max_h}, {count} frames, ICO)")
    except Exception as exc:
        print(f"ERROR: Failed reading icon.ico: {exc}", file=sys.stderr)
        return False

    # 3. macOS icon (icon.icns)
    try:
        with open(icns_path, "rb") as f:
            header = f.read(8)
            if len(header) < 8 or header[:4] != b"icns":
                print("ERROR: icon.icns is not a valid ICNS file", file=sys.stderr)
                return False
            file_len = struct.unpack(">I", header[4:8])[0]
            actual_size = icns_path.stat().st_size
            if file_len != actual_size or actual_size < 10000:
                print(f"ERROR: icon.icns size mismatch or too small ({actual_size} bytes)", file=sys.stderr)
                return False
            print(f"SUCCESS: icon.icns validated ({actual_size} bytes, ICNS)")
    except Exception as exc:
        print(f"ERROR: Failed reading icon.icns: {exc}", file=sys.stderr)
        return False

    print("ALL desktop application icons passed validation!")
    return True


if __name__ == "__main__":
    success = validate_icons()
    sys.exit(0 if success else 1)
