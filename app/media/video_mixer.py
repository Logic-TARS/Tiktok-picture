from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.config import DATA_DIR


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def mix_images_to_video(image_paths: list[str], output_name: str = "mixed.mp4") -> str:
    if not ffmpeg_available():
        raise RuntimeError("FFmpeg is not installed or not available in PATH.")
    if not image_paths:
        raise ValueError("No images were provided.")

    output_dir = DATA_DIR / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    list_file = output_dir / "ffmpeg_images.txt"
    lines: list[str] = []
    for path in image_paths:
        escaped = Path(path).resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
        lines.append("duration 2")
    lines.append(f"file '{Path(image_paths[-1]).resolve().as_posix()}'")
    list_file.write_text("\n".join(lines), encoding="utf-8")

    output_path = output_dir / output_name
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    subprocess.run(command, check=True)
    return str(output_path)

