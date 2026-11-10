"""
scene_builder.py
Gambar satu frame PNG (background gradient + teks) untuk tiap scene,
dengan Pillow. Font pakai DejaVu Sans yang sudah terpasang di Ubuntu runner
(fonts-dejavu-core), atau font custom di assets/fonts/ kalau ada.
"""

import textwrap
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ASSETS_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FALLBACK_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

# Beberapa kombinasi warna gradient supaya tiap scene tidak monoton
PALETTES = [
    ((20, 24, 38), (64, 36, 120)),
    ((10, 30, 40), (10, 90, 110)),
    ((40, 15, 30), (120, 40, 60)),
    ((15, 35, 20), (30, 110, 70)),
    ((35, 25, 10), (140, 90, 20)),
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


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def build_scene_image(
    text: str,
    size: Tuple[int, int],
    out_path: Path,
    palette_index: int = 0,
    is_title: bool = False,
    subtitle: str = "",
) -> None:
    """
    Render satu PNG scene berisi background gradient + teks utama
    (dan subtitle kecil kalau ini scene judul).
    """
    width, height = size
    top_color, bottom_color = PALETTES[palette_index % len(PALETTES)]
    img = _vertical_gradient(size, top_color, bottom_color)

    # Vignette halus biar teks lebih kebaca
    overlay = Image.new("L", size, 0)
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle([0, int(height * 0.35), width, height], fill=140)
    overlay = overlay.filter(ImageFilter.GaussianBlur(80))
    dark = Image.new("RGB", size, (0, 0, 0))
    img = Image.composite(dark, img, overlay)

    draw = ImageDraw.Draw(img)

    margin = int(width * 0.09)
    max_text_width = width - margin * 2

    font_size = int(height * (0.07 if is_title else 0.055))
    font = _load_font(font_size)
    lines = _wrap_text(text, font, max_text_width, draw)

    line_height = int(font_size * 1.25)
    total_text_height = line_height * len(lines)
    start_y = (height - total_text_height) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x = (width - line_width) // 2
        y = start_y + i * line_height
        # shadow
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
    img.save(out_path)
