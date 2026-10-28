"""Рисует assets/icon.ico (зелёный скруглённый квадрат с «译»; без китайского шрифта — «DF»)."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
FONTS = ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]


def draw(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 8, size - 8, size - 8), radius=size // 4, fill=(34, 197, 139, 255))
    font, text = None, "DF"
    for f in FONTS:
        try:
            font, text = ImageFont.truetype(f, int(size * 0.62)), "译"
            break
        except OSError:
            continue
    if font is None:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(size * 0.5))
        except OSError:
            font = ImageFont.load_default()
    d.text((size / 2, size / 2), text, font=font, fill=(6, 35, 26, 255), anchor="mm")
    return img


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    draw().save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("OK", OUT, file=sys.stderr)
