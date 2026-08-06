from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from src.application.structural_montage_final_render_v1 import (
    PIXEL_FORMAT,
    _validate_video_file,
    build_still_render_command,
    require_montage_environment,
)


def _ppm(path: Path) -> None:
    width = 96
    height = 54
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            pixels.extend((32 + x * 2 % 220, 24 + y * 3 % 220, 96))
    path.write_bytes(header + bytes(pixels))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    source = root / "pixel-format-smoke.ppm"
    output = root / "pixel-format-smoke.mp4"
    _ppm(source)
    environment = require_montage_environment(repo)
    command = build_still_render_command(
        environment,
        source,
        output,
        duration=1.0,
        motion_profile="SLOW_PUSH_IN",
        fade_in=False,
        fade_out=False,
    )
    process = subprocess.run(
        command,
        cwd=str(repo),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            "PIXEL_FORMAT_SMOKE_RENDER_FAILED\n"
            + process.stdout
            + "\n"
            + process.stderr
        )
    validation = _validate_video_file(
        environment,
        output,
        1.0,
        require_audio=False,
        tolerance=0.25,
    )
    if validation.get("pixel_format") != PIXEL_FORMAT:
        raise RuntimeError(
            "PIXEL_FORMAT_SMOKE_INVALID:"
            + str(validation.get("pixel_format"))
        )
    print(json.dumps({"status": "PASS", "validation": validation}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
