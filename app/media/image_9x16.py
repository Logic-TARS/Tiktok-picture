from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps


TARGET_SIZE = (1080, 1920)
BLUR_BACKGROUND = "blur_background"
CROP_CENTER = "crop_center"

PLATFORM_RESOLUTIONS: dict[str, tuple[int, int]] = {
    "douyin": (1080, 1920),
    "kuaishou": (1080, 1920),
    "xiaohongshu": (720, 960),
}


def prepare_platform_uploads(
    paths: list[str],
    *,
    mode: str = BLUR_BACKGROUND,
    target_size: tuple[int, int] = TARGET_SIZE,
) -> tuple[list[str], Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="publisher-resize-"))
    prepared: list[str] = []
    for index, path in enumerate(paths, start=1):
        source = Path(path)
        output_path = temp_dir / f"{index:02d}.jpg"
        convert_to_target_size(source, output_path, mode=mode, target_size=target_size)
        prepared.append(str(output_path))
    return prepared, temp_dir


def prepare_9x16_uploads(
    paths: list[str],
    *,
    mode: str = BLUR_BACKGROUND,
) -> tuple[list[str], Path]:
    return prepare_platform_uploads(paths, mode=mode, target_size=TARGET_SIZE)


def cleanup_temp_dir(path: Path | None) -> None:
    if not path:
        return
    shutil.rmtree(path, ignore_errors=True)


def convert_to_target_size(source: Path, target: Path, *, mode: str = BLUR_BACKGROUND, target_size: tuple[int, int] = TARGET_SIZE) -> None:
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        foreground = image.convert("RGBA")
        target.parent.mkdir(parents=True, exist_ok=True)

        if mode == CROP_CENTER:
            cropped = ImageOps.fit(
                foreground,
                target_size,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            cropped.convert("RGB").save(target, format="JPEG", quality=95, optimize=True)
            return

        background = ImageOps.fit(
            foreground,
            target_size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        ).filter(ImageFilter.GaussianBlur(radius=26))

        canvas = background.convert("RGBA")
        contained = ImageOps.contain(foreground, target_size, method=Image.Resampling.LANCZOS)
        offset = (
            (target_size[0] - contained.width) // 2,
            (target_size[1] - contained.height) // 2,
        )
        canvas.paste(contained, offset, contained)
        canvas.convert("RGB").save(target, format="JPEG", quality=95, optimize=True)
