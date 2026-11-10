from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

THEME_MAP = {
    "otak": {"top": (6, 18, 35), "bottom": (18, 126, 170), "accent": (110, 232, 255)},
    "ai": {"top": (17, 11, 28), "bottom": (93, 45, 130), "accent": (180, 122, 255)},
    "teknologi": {"top": (15, 20, 35), "bottom": (27, 94, 117), "accent": (90, 255, 214)},
    "laut": {"top": (5, 30, 56), "bottom": (5, 121, 167), "accent": (96, 220, 255)},
    "ekonomi": {"top": (18, 24, 12), "bottom": (93, 119, 28), "accent": (195, 255, 116)},
    "bisnis": {"top": (20, 20, 18), "bottom": (123, 74, 18), "accent": (255, 216, 120)},
    "sains": {"top": (8, 18, 24), "bottom": (16, 74, 72), "accent": (139, 255, 214)},
    "kesehatan": {"top": (16, 18, 28), "bottom": (70, 18, 50), "accent": (255, 160, 210)},
    "default": {"top": (10, 17, 35), "bottom": (62, 35, 115), "accent": (90, 215, 255)},
}

def _load_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _detect_theme(text: str):
    lower = (text or "").lower()
    best_key = "default"
    best_score = 0
    for key in THEME_MAP:
        if key == "default":
            continue
        score = sum(1 for word in key.split() if word in lower)
        if score > best_score:
            best_score = score
            best_key = key
    return THEME_MAP[best_key]


def _gradient_lines(img: Image.Image, top, bottom):
    width, height = img.size
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(height - 1, 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line((0, y, width, y), fill=(r, g, b))


def _decorate_scene(img: Image.Image, accent):
    width, height = img.size
    draw = ImageDraw.Draw(img)

    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((int(width * 0.58), -int(height * 0.12), int(width * 1.2), int(height * 0.5)), fill=(*accent, 50))
    glow_draw.ellipse((-int(width * 0.15), int(height * 0.7), int(width * 0.45), int(height * 1.2)), fill=(*accent, 35))
    glow = glow.filter(ImageFilter.GaussianBlur(max(width, height) // 12))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

    margin = int(width * 0.08)
    bar_width = max(int(width * 0.12), 40)
    draw.rounded_rectangle((margin, int(height * 0.14), margin + bar_width, int(height * 0.152)), radius=4, fill=accent)

    draw.line((margin, int(height * 0.12), width - margin, int(height * 0.12)), fill=(255, 255, 255), width=2)
    draw.line((margin, int(height * 0.88), width - margin, int(height * 0.88)), fill=(255, 255, 255), width=2)

    for i in range(4):
        r = int(height * (0.04 + i * 0.018))
        cx = width - margin - r
        cy = int(height * 0.24) + i * int(height * 0.045)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=accent, width=2)

    return img


def _wrap_text(text: str, font, max_width: int, draw: ImageDraw.ImageDraw):
    words = (text or "").split()
    if not words:
        return [""]
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:5]


def build_scene_image(
    text: str,
    size: Tuple[int, int],
    out_path: Path,
    palette_index: int = 0,
    is_title: bool = False,
    subtitle: str = "",
) -> None:
    width, height = size
    theme = _detect_theme(text)
    top = theme["top"]
    bottom = theme["bottom"]
    accent = theme["accent"]

    img = Image.new("RGB", size, (0, 0, 0))
    _gradient_lines(img, top, bottom)

    vignette = Image.new("L", size, 255)
    vignette_draw = ImageDraw.Draw(vignette)
    vignette_draw.ellipse((-int(width * 0.3), -int(height * 0.2), int(width * 1.3), int(height * 1.2)), fill=0)
    vignette = vignette.filter(ImageFilter.GaussianBlur(max(width, height) // 8))
    img = Image.composite(Image.new("RGB", size, (0, 0, 0)), img, vignette)

    img = _decorate_scene(img, accent)

    draw = ImageDraw.Draw(img)
    margin = int(width * 0.1)
    font_size = int(height * (0.072 if is_title else 0.058))
    font = _load_font(font_size)
    lines = _wrap_text(text, font, width - margin * 2, draw)
    line_height = max(int(font_size * 1.28), 20)
    total_h = len(lines) * line_height
    start_y = (height - total_h) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (width - bbox[2]) // 2
        y = start_y + i * line_height
        draw.text((x + 4, y + 4), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))

    if subtitle:
        sub_font = _load_font(int(height * 0.028))
        bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
        x = (width - bbox[2]) // 2
        y = start_y + total_h + 25
        draw.text((x, y), subtitle, font=sub_font, fill=(220, 230, 240))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
