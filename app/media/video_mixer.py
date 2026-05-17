from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from app.config import DATA_DIR
from app.media.image_9x16 import BLUR_BACKGROUND, CROP_CENTER


VIDEO_EFFECTS = {"none", "fade", "motion", "motion_fade"}
DEFAULT_VIDEO_EFFECT = "motion_fade"
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FPS = 25
SEGMENT_DURATION = 2.8
TRANSITION_DURATION = 0.45
DEFAULT_AUDIO_VOLUME = 0.22


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


def normalize_frame_mode(frame_mode: str | None) -> str:
    mode = str(frame_mode or BLUR_BACKGROUND).strip().lower()
    return mode if mode in {BLUR_BACKGROUND, CROP_CENTER} else BLUR_BACKGROUND


def _build_frame_filter(input_index: int, frame_mode: str, output_label: str) -> str:
    if frame_mode == CROP_CENTER:
        return (
            f"[{input_index}:v]"
            f"fps={OUTPUT_FPS},"
            f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},"
            "setsar=1"
            f"[{output_label}]"
        )

    return (
        f"[{input_index}:v]split=2[bg{input_index}][fg{input_index}];"
        f"[bg{input_index}]"
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},"
        "gblur=sigma=18"
        f"[bgf{input_index}];"
        f"[fg{input_index}]"
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease"
        f"[fgf{input_index}];"
        f"[bgf{input_index}][fgf{input_index}]"
        f"overlay=(W-w)/2:(H-h)/2,setsar=1"
        f"[{output_label}]"
    )


def _build_image_stream_filter(input_index: int, effect_mode: str, frame_mode: str) -> tuple[str, str]:
    segment_frames = int(SEGMENT_DURATION * OUTPUT_FPS)
    base_label = f"base{input_index}"
    frame_filter = _build_frame_filter(input_index, frame_mode, base_label)
    label = f"v{input_index}"

    if effect_mode in {"motion", "motion_fade"}:
        filter_text = (
            f"{frame_filter};"
            f"[{base_label}]"
            f"zoompan=z='min(zoom+0.0007\\,1.08)':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            f"d={segment_frames}:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}:fps={OUTPUT_FPS},"
            f"trim=duration={SEGMENT_DURATION:.2f},"
            f"setpts=PTS-STARTPTS[{label}]"
        )
        return filter_text, label

    filter_text = (
        f"{frame_filter};"
        f"[{base_label}]"
        f"trim=duration={SEGMENT_DURATION:.2f},"
        f"setpts=PTS-STARTPTS[{label}]"
    )
    return filter_text, label


def _build_filter_complex(image_paths: list[str], effect_mode: str, frame_mode: str) -> tuple[str, str]:
    filter_parts: list[str] = []
    input_labels: list[str] = []

    for index, _ in enumerate(image_paths):
        filter_text, label = _build_image_stream_filter(index, effect_mode, frame_mode)
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


def _stage_audio_file(audio_path: str, output_dir: Path) -> tuple[str, Path]:
    stage_dir = output_dir / f"ffmpeg_audio_{uuid.uuid4().hex[:8]}"
    stage_dir.mkdir(parents=True, exist_ok=True)
    source = Path(audio_path)
    suffix = source.suffix or ".mp3"
    target = stage_dir / f"bgm{suffix.lower()}"
    shutil.copy2(source, target)
    return str(target), stage_dir


def _prepare_audio_loop_source(
    ffmpeg_bin: str,
    staged_audio_path: str,
    stage_dir: Path,
    *,
    start_seconds: float,
    clip_duration: float,
) -> str:
    if start_seconds <= 0 and clip_duration <= 0:
        return staged_audio_path

    clipped_path = stage_dir / "bgm_clip.m4a"
    command = [ffmpeg_bin, "-y"]
    if start_seconds > 0:
        command.extend(["-ss", f"{start_seconds:.2f}"])
    command.extend(["-i", str(Path(staged_audio_path).resolve())])
    if clip_duration > 0:
        command.extend(["-t", f"{clip_duration:.2f}"])
    command.extend(["-vn", "-c:a", "aac", "-b:a", "192k", str(clipped_path)])
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"FFmpeg audio clip failed: {stderr or 'unknown ffmpeg error'}")
    return str(clipped_path)


def _estimate_output_duration(image_count: int, effect_mode: str) -> float:
    if image_count <= 0:
        return 0.0
    if image_count == 1:
        return SEGMENT_DURATION
    if effect_mode in {"fade", "motion_fade"}:
        return (image_count * SEGMENT_DURATION) - ((image_count - 1) * TRANSITION_DURATION)
    return image_count * SEGMENT_DURATION


def normalize_audio_start_seconds(value: float | str | None) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def normalize_audio_clip_duration(value: float | str | None) -> float:
    try:
        seconds = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, seconds)


def mix_images_to_video(
    image_paths: list[str],
    output_name: str = "mixed.mp4",
    *,
    effect_mode: str | None = None,
    frame_mode: str | None = None,
    bgm_path: str | None = None,
    bgm_start_seconds: float | str | None = None,
    bgm_clip_duration: float | str | None = None,
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
    normalized_frame_mode = normalize_frame_mode(frame_mode)
    normalized_audio_start = normalize_audio_start_seconds(bgm_start_seconds)
    normalized_audio_duration = normalize_audio_clip_duration(bgm_clip_duration)
    staged_paths, stage_dir = _stage_input_images(image_paths, output_dir)
    filter_complex, map_label = _build_filter_complex(staged_paths, normalized_effect, normalized_frame_mode)
    output_duration = _estimate_output_duration(len(staged_paths), normalized_effect)
    staged_audio_path = ""
    audio_stage_dir: Path | None = None
    audio_input_index: int | None = None

    command = [ffmpeg_bin, "-y"]
    try:
        for path in staged_paths:
            command.extend(["-loop", "1", "-t", f"{SEGMENT_DURATION:.2f}", "-i", str(Path(path).resolve())])
        if bgm_path:
            staged_audio_path, audio_stage_dir = _stage_audio_file(bgm_path, output_dir)
            audio_input_index = len(staged_paths)
            audio_loop_source = _prepare_audio_loop_source(
                ffmpeg_bin,
                staged_audio_path,
                audio_stage_dir,
                start_seconds=normalized_audio_start,
                clip_duration=normalized_audio_duration,
            )
            command.extend(["-stream_loop", "-1", "-i", str(Path(audio_loop_source).resolve())])
        command.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                map_label,
            ]
        )
        if audio_input_index is not None:
            command.extend(
                [
                    "-map",
                    f"{audio_input_index}:a:0",
                    "-af",
                    f"volume={DEFAULT_AUDIO_VOLUME},atrim=duration={output_duration:.2f}",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-shortest",
                ]
            )
        command.extend(
            [
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
        if audio_stage_dir is not None:
            shutil.rmtree(audio_stage_dir, ignore_errors=True)
    return str(output_path)
