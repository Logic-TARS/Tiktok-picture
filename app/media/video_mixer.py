from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from app.config import DATA_DIR


VIDEO_EFFECTS = {"none", "fade", "motion", "motion_fade"}
DEFAULT_VIDEO_EFFECT = "motion_fade"
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FPS = 25
SEGMENT_DURATION = 2.8
TRANSITION_DURATION = 0.45


def resolve_ffmpeg_path() -> str | None:
    direct = shutil.which("ffmpeg")
    if direct:
        return direct

    candidates: list[Path] = []
    conda_prefix = os.getenv("CONDA_PREFIX")
    if conda_prefix:
        candidates.append(Path(conda_prefix) / "Library" / "bin" / "ffmpeg.exe")

    python_dir = Path(sys.executable).resolve().parent
    candidates.extend(
        [
            python_dir / "Library" / "bin" / "ffmpeg.exe",
            python_dir.parent / "Library" / "bin" / "ffmpeg.exe",
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def ffmpeg_available() -> bool:
    return resolve_ffmpeg_path() is not None


def normalize_effect_mode(effect_mode: str | None) -> str:
    mode = str(effect_mode or DEFAULT_VIDEO_EFFECT).strip().lower()
    return mode if mode in VIDEO_EFFECTS else DEFAULT_VIDEO_EFFECT


def _build_image_stream_filter(input_index: int, effect_mode: str) -> tuple[str, str]:
    segment_frames = int(SEGMENT_DURATION * OUTPUT_FPS)
    base = (
        f"[{input_index}:v]"
        f"fps={OUTPUT_FPS},"
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1"
    )
    label = f"v{input_index}"

    if effect_mode in {"motion", "motion_fade"}:
        filter_text = (
            f"{base},"
            f"zoompan=z='min(zoom+0.0007\\,1.08)':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            f"d={segment_frames}:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}:fps={OUTPUT_FPS},"
            f"trim=duration={SEGMENT_DURATION:.2f},"
            f"setpts=PTS-STARTPTS[{label}]"
        )
        return filter_text, label

    filter_text = (
        f"{base},"
        f"trim=duration={SEGMENT_DURATION:.2f},"
        f"setpts=PTS-STARTPTS[{label}]"
    )
    return filter_text, label


def _build_filter_complex(image_paths: list[str], effect_mode: str) -> tuple[str, str]:
    filter_parts: list[str] = []
    input_labels: list[str] = []

    for index, _ in enumerate(image_paths):
        filter_text, label = _build_image_stream_filter(index, effect_mode)
        filter_parts.append(filter_text)
        input_labels.append(label)

    if len(input_labels) == 1:
        return ";".join(filter_parts), f"[{input_labels[0]}]"

    if effect_mode in {"fade", "motion_fade"}:
        current_label = input_labels[0]
        offset = SEGMENT_DURATION - TRANSITION_DURATION
        for index, next_label in enumerate(input_labels[1:], start=1):
            output_label = f"x{index}"
            filter_parts.append(
                f"[{current_label}][{next_label}]"
                f"xfade=transition=fade:duration={TRANSITION_DURATION:.2f}:offset={offset:.2f},"
                f"format=yuv420p[{output_label}]"
            )
            current_label = output_label
            offset += SEGMENT_DURATION - TRANSITION_DURATION
        return ";".join(filter_parts), f"[{current_label}]"

    concat_inputs = "".join(f"[{label}]" for label in input_labels)
    filter_parts.append(f"{concat_inputs}concat=n={len(input_labels)}:v=1:a=0,format=yuv420p[vout]")
    return ";".join(filter_parts), "[vout]"


def _stage_input_images(image_paths: list[str], output_dir: Path) -> tuple[list[str], Path]:
    stage_dir = output_dir / f"ffmpeg_stage_{uuid.uuid4().hex[:8]}"
    stage_dir.mkdir(parents=True, exist_ok=True)
    staged_paths: list[str] = []
    for index, path in enumerate(image_paths, start=1):
        source = Path(path)
        suffix = source.suffix or ".png"
        target = stage_dir / f"frame_{index:03d}{suffix.lower()}"
        shutil.copy2(source, target)
        staged_paths.append(str(target))
    return staged_paths, stage_dir


def mix_images_to_video(
    image_paths: list[str],
    output_name: str = "mixed.mp4",
    *,
    effect_mode: str | None = None,
) -> str:
    if not ffmpeg_available():
        raise RuntimeError("FFmpeg is not installed or not available in PATH.")
    if not image_paths:
        raise ValueError("No images were provided.")

    output_dir = DATA_DIR / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_name

    ffmpeg_bin = resolve_ffmpeg_path()
    if not ffmpeg_bin:
        raise RuntimeError("FFmpeg is not installed or not available in PATH.")

    normalized_effect = normalize_effect_mode(effect_mode)
    staged_paths, stage_dir = _stage_input_images(image_paths, output_dir)
    filter_complex, map_label = _build_filter_complex(staged_paths, normalized_effect)

    command = [ffmpeg_bin, "-y"]
    try:
        for path in staged_paths:
            command.extend(["-loop", "1", "-t", f"{SEGMENT_DURATION:.2f}", "-i", str(Path(path).resolve())])
        command.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                map_label,
                "-r",
                str(OUTPUT_FPS),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )

        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"FFmpeg mix failed: {stderr or 'unknown ffmpeg error'}")
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
    return str(output_path)
