"""Render polished still frames for motion-graphics scenes."""

from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FALLBACK_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

PALETTES = [
    ((10, 17, 35), (62, 35, 115), (90, 215, 255)),
    ((8, 28, 38), (12, 93, 112), (94, 255, 214)),
    ((31, 12, 30), (125, 42, 77), (255, 135, 174)),
    ((12, 29, 22), (32, 102, 67), (164, 255, 166)),
    ((34, 22, 10), (138, 82, 22), (255, 206, 112)),
    ((15, 20, 43), (70, 69, 150), (177, 160, 255)),
]


def _load_font(size: int) -> ImageFont.ImageFont:
    custom_fonts = sorted(FONT_DIR.glob("*.ttf")) if FONT_DIR.exists() else []
    for font_path in [*custom_fonts, *(Path(p) for p in FALLBACK_FONTS)]:
        try:
            return ImageFont.truetype(str(font_path), size=max(size, 10))
        except OSError:
            continue
    return ImageFont.load_default()


def _gradient(size: Tuple[int, int], top: Tuple[int, int, int],
              bottom: Tuple[int, int, int]) -> Image.Image:
    width, height = size
    strip = Image.new("RGB", (1, height))
    draw = ImageDraw.Draw(strip)
    denominator = max(height - 1, 1)

    for y in range(height):
        t = y / denominator
        color = tuple(
            round(top[channel] + (bottom[channel] - top[channel]) * t)
            for channel in range(3)
        )
        draw.point((0, y), fill=color)

    return strip.resize((width, height))


def _wrap_text(text: str, font, draw: ImageDraw.ImageDraw,
               max_width: int, max_lines: int) -> List[str]:
    """Wrap words safely, including unusually long words."""
    words = (text or "").split()
    if not words:
        return [""]

    lines: List[str] = []
    current = ""
    truncated = False

    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ""

        # Split an individual word that is wider than the available line.
        piece = ""
        for char in word:
            trial = piece + char
            if piece and draw.textbbox((0, 0), trial, font=font)[2] > max_width:
                lines.append(piece)
                piece = char
                if len(lines) >= max_lines:
                    truncated = True
                    break
            else:
                piece = trial

        if truncated:
            break

        current = piece
        if len(lines) >= max_lines:
            truncated = True
            break

    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True

    if truncated and lines:
        last = lines[-1]
        ellipsis = "…"
        while last and draw.textbbox((0, 0), last + ellipsis, font=font)[2] > max_width:
            last = last[:-1]
        lines[-1] = (last.rstrip() + ellipsis) if last else ellipsis

    return lines or [""]


def _fit_text(text: str, size: Tuple[int, int], is_title: bool):
    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    max_width = int(width * 0.82)
    max_height = int(height * (0.50 if is_title else 0.56))
    font_size = int(height * (0.075 if is_title else 0.057))
    min_font_size = max(int(height * 0.026), 18)

    while font_size >= min_font_size:
        font = _load_font(font_size)
        lines = _wrap_text(text, font, draw, max_width, max_lines=5)
        line_height = max(int(font_size * 1.24), 1)
        if len(lines) * line_height <= max_height:
            return font, lines, line_height
        font_size = int(font_size * 0.88)

    font = _load_font(min_font_size)
    lines = _wrap_text(text, font, draw, max_width, max_lines=5)
    return font, lines, max(int(min_font_size * 1.24), 1)


def build_scene_image(
    text: str,
    size: Tuple[int, int],
    out_path: Path,
    palette_index: int = 0,
    is_title: bool = False,
    subtitle: str = "",
) -> None:
    """Create one gradient, glow, geometric-accent, and typography scene."""
    width, height = size
    top, bottom, accent = PALETTES[palette_index % len(PALETTES)]
    image = _gradient(size, top, bottom)

    # Soft vignette keeps the central typography readable.
    vignette = Image.new("L", size, 0)
    vignette_draw = ImageDraw.Draw(vignette)
    vignette_draw.ellipse(
        (-int(width * 0.30), -int(height * 0.12),
         int(width * 1.30), int(height * 1.12)),
        fill=165,
    )
    vignette = vignette.filter(ImageFilter.GaussianBlur(max(width, height) // 5))
    black = Image.new("RGB", size, (0, 0, 0))
    image = Image.composite(black, image, Image.eval(vignette, lambda value: 255 - value))

    # Blurred colored glows are composited separately for correct alpha handling.
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        (int(width * 0.58), int(height * 0.04),
         int(width * 1.08), int(height * 0.36)),
        fill=(*accent, 78),
    )
    glow_draw.ellipse(
        (-int(width * 0.22), int(height * 0.66),
         int(width * 0.38), int(height * 1.12)),
        fill=(*accent, 55),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(max(width, height) // 12))
    image = Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")

    draw = ImageDraw.Draw(image)
    margin = int(width * 0.075)

    # Fine framing lines and a small accent bar.
    draw.line(
        (margin, int(height * 0.12), width - margin, int(height * 0.12)),
        fill=(255, 255, 255),
        width=max(1, width // 720),
    )
    draw.line(
        (margin, int(height * 0.88), width - margin, int(height * 0.88)),
        fill=(255, 255, 255),
        width=max(1, width // 720),
    )
    bar_width = max(int(width * 0.10), 30)
    draw.rounded_rectangle(
        (margin, int(height * 0.145), margin + bar_width, int(height * 0.153)),
        radius=max(width // 300, 2),
        fill=accent,
    )

    # Decorative rings and dots.
    for index in range(4):
        radius = int(height * (0.045 + index * 0.018))
        center_x = width - margin - radius
        center_y = int(height * 0.24) + index * int(height * 0.045)
        draw.ellipse(
            (center_x - radius, center_y - radius,
             center_x + radius, center_y + radius),
            outline=(*accent,),
            width=max(1, width // 500),
        )

    font, lines, line_height = _fit_text(text, size, is_title)
    total_height = len(lines) * line_height
    text_top = (height - total_height) // 2

    for index, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x = (width - line_width) // 2
        y = text_top + index * line_height
        draw.text((x + 3, y + 4), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))

    if subtitle:
        subtitle_font = _load_font(max(int(height * 0.024), 16))
        subtitle_width = draw.textbbox((0, 0), subtitle, font=subtitle_font)[2]
        if subtitle_width > width * 0.82:
            subtitle_font = _load_font(max(int(height * 0.018), 13))
            subtitle_width = draw.textbbox((0, 0), subtitle, font=subtitle_font)[2]
        x = max((width - subtitle_width) // 2, margin)
        y = min(text_top + total_height + int(height * 0.035), int(height * 0.82))
        draw.text((x, y), subtitle, font=subtitle_font, fill=(225, 232, 245))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="PNG")
