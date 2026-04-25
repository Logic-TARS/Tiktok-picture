from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps


TARGET_SIZE = (1080, 1920)
BLUR_BACKGROUND = "blur_background"
CROP_CENTER = "crop_center"


def prepare_9x16_uploads(
    paths: list[str],
    *,
    mode: str = BLUR_BACKGROUND,
) -> tuple[list[str], Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="douyin-9x16-"))
    prepared: list[str] = []
    for index, path in enumerate(paths, start=1):
        source = Path(path)
        output_path = temp_dir / f"{index:02d}.jpg"
        convert_to_9x16(source, output_path, mode=mode)
        prepared.append(str(output_path))
    return prepared, temp_dir


def cleanup_temp_dir(path: Path | None) -> None:
    if not path:
        return
    shutil.rmtree(path, ignore_errors=True)


def convert_to_9x16(source: Path, target: Path, *, mode: str = BLUR_BACKGROUND) -> None:
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        foreground = image.convert("RGBA")
        target.parent.mkdir(parents=True, exist_ok=True)

        if mode == CROP_CENTER:
            cropped = ImageOps.fit(
                foreground,
                TARGET_SIZE,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            cropped.convert("RGB").save(target, format="JPEG", quality=95, optimize=True)
            return

        background = ImageOps.fit(
            foreground,
            TARGET_SIZE,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        ).filter(ImageFilter.GaussianBlur(radius=26))

        canvas = background.convert("RGBA")
        contained = ImageOps.contain(foreground, TARGET_SIZE, method=Image.Resampling.LANCZOS)
        offset = (
            (TARGET_SIZE[0] - contained.width) // 2,
            (TARGET_SIZE[1] - contained.height) // 2,
        )
        canvas.paste(contained, offset, contained)
        canvas.convert("RGB").save(target, format="JPEG", quality=95, optimize=True)
