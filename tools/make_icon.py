"""Рисует иконку программы: assets/icon.ico (для exe) и assets/icon.png (окно и трей).

Тот же стиль, что у баннера в README: скруглённый квадрат с зелёным градиентом и тёмный «译».
Без китайского шрифта (не Windows) вместо «译» пишется «DF».
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONTS = ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]
TOP, BOTTOM, INK = (47, 214, 155), (23, 160, 112), (6, 35, 26)


def draw(size: int = 1024) -> Image.Image:
    s = size
    pad, radius = int(s * 0.04), int(s * 0.23)
    # градиент по диагонали
    grad = Image.new("RGBA", (s, s))
    gp = grad.load()
    for y in range(s):
        for x in range(s):
            t = (x + y) / (2 * s - 2)
            gp[x, y] = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)) + (255,)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((pad, pad, s - pad, s - pad), radius=radius, fill=255)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    # лёгкий блик сверху
    hl = Image.new("L", (s, s), 0)
    ImageDraw.Draw(hl).rounded_rectangle((pad, pad, s - pad, int(s * 0.52)), radius=radius, fill=26)
    hl = Image.composite(hl, Image.new("L", (s, s), 0), mask)
    img = Image.alpha_composite(img, Image.merge("RGBA", (Image.new("L", (s, s), 255),) * 3 + (hl,)))

    font, text = None, "DF"
    for f in FONTS:
        try:
            font, text = ImageFont.truetype(f, int(s * 0.56)), "译"
            break
        except OSError:
            continue
    if font is None:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(s * 0.44))
        except OSError:
            font = ImageFont.load_default()
    # мягкая тень под знаком
    sh = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((s / 2, s / 2 + s * 0.012), text, font=font, fill=(0, 0, 0, 70), anchor="mm")
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(s * 0.01)))
    ImageDraw.Draw(img).text((s / 2, s / 2 - s * 0.01), text, font=font, fill=INK + (255,), anchor="mm")
    return img


if __name__ == "__main__":
    ASSETS.mkdir(exist_ok=True)
    big = draw()
    big.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon.png")
    big.resize((256, 256), Image.LANCZOS).save(
        ASSETS / "icon.ico", sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    print("OK", ASSETS / "icon.ico", ASSETS / "icon.png")
