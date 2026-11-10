"""
scene_builder.py
Membuat frame PNG cinematic untuk tiap scene dengan background gradient,
accent shapes, dan layout teks yang lebih rapi.
"""

from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FALLBACK_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

PALETTES = [
    ((12, 18, 32), (70, 40, 120)),
    ((14, 30, 38), (20, 95, 118)),
    ((30, 14, 26), (132, 60, 92)),
    ((20, 28, 18), (42, 118, 74)),
    ((34, 22, 11), (156, 102, 30)),
    ((15, 22, 42), (92, 62, 166)),
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    custom_fonts = sorted(ASSETS_FONT_DIR.glob("*.ttf")) if ASSETS_FONT_DIR.exists() else []
    candidates = [str(p) for p in custom_fonts] + FALLBACK_FONT_PATHS
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _vertical_gradient(size: Tuple[int, int], top_color, bottom_color) -> Image.Image:
    width, height = size
    base = Image.new("RGB", (1, height), color=0)
    draw = ImageDraw.Draw(base)
    for y in range(height):
        t = y / max(height - 1, 1)
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
        draw.point((0, y), fill=(r, g, b))
    return base.resize((width, height))


def _safe_wrap_text(text: str, font, max_width: int, draw: ImageDraw.ImageDraw, max_lines: int = 4):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
        if len(lines) >= max_lines - 1 and current:
            break
    if current:
        lines.append(current)
    return lines[:max_lines]


def build_scene_image(
    text: str,
    size: Tuple[int, int],
    out_path: Path,
    palette_index: int = 0,
    is_title: bool = False,
    subtitle: str = "",
) -> None:
    """Render satu frame scene dengan elemen visual tambahan buat motion graphics."""
    width, height = size
    top_color, bottom_color = PALETTES[palette_index % len(PALETTES)]

    bg = _vertical_gradient(size, top_color, bottom_color)

    overlay = Image.new("L", size, 0)
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle([0, int(height * 0.32), width, height], fill=165)
    overlay = overlay.filter(ImageFilter.GaussianBlur(55))
    dark = Image.new("RGB", size, (0, 0, 0))
    bg = Image.composite(dark, bg, overlay)

    draw = ImageDraw.Draw(bg)

    accent_count = 8
    for i in range(accent_count):
        x = int(width * (0.12 + i * 0.1))
        y = int(height * (0.18 + (i % 3) * 0.18))
        radius = int(height * (0.03 + (i % 4) * 0.02))
        alpha = 70 + i * 10
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            outline=(255, 255, 255, alpha),
            width=2,
        )

    line_margin = int(width * 0.095)
    text_width = width - (line_margin * 2)
    font_size = int(height * (0.072 if is_title else 0.055))
    font = _load_font(font_size)
    lines = _safe_wrap_text(text, font, text_width, draw, max_lines=4)

    line_height = int(font_size * 1.25)
    total_text_height = len(lines) * line_height
    start_y = (height - total_text_height) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x = (width - line_width) // 2
        y = start_y + i * line_height
        draw.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0, 180))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))

    if is_title and subtitle:
        sub_font = _load_font(int(height * 0.028))
        bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
        sub_width = bbox[2] - bbox[0]
        x = (width - sub_width) // 2
        y = start_y + total_text_height + int(height * 0.03)
        draw.text((x, y), subtitle, font=sub_font, fill=(230, 230, 230))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    bg.save(out_path)
