import asyncio
import json
import logging
from pathlib import Path
import shutil

logger = logging.getLogger("downloader.image_processor")


async def get_image_dimensions(image_path: Path) -> tuple[int, int]:
    """Визначає (width, height) зображення через ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(image_path),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0 and stdout:
            data = json.loads(stdout.decode())
            streams = data.get("streams", [])
            if streams:
                w = streams[0].get("width")
                h = streams[0].get("height")
                if w and h:
                    return int(w), int(h)
    except Exception as exc:
        logger.warning("Не вдалося отримати розміри через ffprobe: %s", exc)
    return 0, 0


async def process_image(
    input_path: Path,
    target_format: str | None = None,  # 'original', 'jpg', 'png', 'webp', 'avif'
    max_side: int | None = None,  # максимальний розмір по більшій стороні (наприклад, 1080, 1920, 2560)
    quality: int = 90,  # якість стиснення (1-100)
) -> Path:
    """
    Конвертує та масштабує зображення за допомогою ffmpeg:
    - target_format: змінює розширення та формат (jpg, png, webp, avif)
    - max_side: якщо задано, пропорційно зменшує зображення, якщо його більша сторона перевищує max_side
    """
    if not input_path.exists():
        return input_path

    fmt = (target_format or "original").lower().lstrip(".")
    needs_format_change = fmt not in ("original", "", input_path.suffix.lower().lstrip("."))

    orig_w, orig_h = await get_image_dimensions(input_path)
    needs_scale = False
    scale_filter = None

    if max_side and max_side > 0 and (orig_w > 0 and orig_h > 0):
        longer_side = max(orig_w, orig_h)
        if longer_side > max_side:
            needs_scale = True
            # Масштабування по більшій стороні зі збереженням пропорцій (-1 або -2 для парності)
            if orig_w >= orig_h:
                scale_filter = f"scale={max_side}:-2"
            else:
                scale_filter = f"scale=-2:{max_side}"

    if not needs_format_change and not needs_scale:
        return input_path

    # Визначаємо цільове розширення
    new_ext = f".{fmt}" if needs_format_change else input_path.suffix.lower()
    if new_ext == ".jpeg":
        new_ext = ".jpg"

    output_path = input_path.with_name(f"{input_path.stem}_proc{new_ext}")

    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(input_path)]

    if scale_filter:
        cmd.extend(["-vf", scale_filter])

    # Специфічні кодеки та параметри якості
    if new_ext in (".jpg", ".jpeg"):
        cmd.extend(["-q:v", str(max(1, min(31, int((100 - quality) / 3))))])
    elif new_ext == ".webp":
        cmd.extend(["-c:v", "libwebp", "-quality", str(quality)])
    elif new_ext == ".png":
        cmd.extend(["-c:v", "png"])
    elif new_ext == ".avif":
        cmd.extend(["-c:v", "libaom-av1", "-still-picture", "1", "-crf", str(int((100 - quality) / 2))])

    cmd.append(str(output_path))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            # Замінюємо старий файл або залишаємо новий
            final_path = input_path.with_suffix(new_ext)
            if final_path != input_path and input_path.exists():
                input_path.unlink()
            shutil.move(str(output_path), str(final_path))
            return final_path
        else:
            logger.warning("FFmpeg помилка конвертації: %s", stderr.decode(errors="ignore"))
    except Exception as exc:
        logger.error("Виняток при обробці зображення: %s", exc)

    return input_path

