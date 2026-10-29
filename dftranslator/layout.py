"""Раскладка плашек с переводом по экрану (чистая логика, без Qt — тестируется отдельно)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# measure(text, font_px, max_width_px) -> (width_px, height_px)
Measure = Callable[[str, int, int], tuple[int, int]]


@dataclass
class Item:
    zh: str
    ru: str
    x0: float
    y0: float
    x1: float
    y1: float
    line_h: float
    source: str = ""
    lore: bool = False
    bg: tuple[int, int, int] | None = None   # цвет фона под оригинальным текстом (для замены «на месте»)
    fg: tuple[int, int, int] | None = None   # цвет текста оригинала
    room_right: float | None = None          # докуда вправо тянется тот же фон (край панели)
    room_bottom: float | None = None         # докуда вниз

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0


@dataclass
class Placed:
    x: int
    y: int
    w: int
    h: int
    font_px: int
    text: str
    zh: str
    source: str
    lore: bool
    bg: tuple[int, int, int] | None = None
    fg: tuple[int, int, int] | None = None

    @property
    def bottom(self) -> int:
        return self.y + self.h


def _overlaps(a: tuple[int, int, int, int], b: Placed) -> bool:
    ax, ay, aw, ah = a
    return ax < b.x + b.w and ax + aw > b.x and ay < b.y + b.h and ay + ah > b.y


def place(
    items: list[Item],
    screen_w: int,
    screen_h: int,
    measure: Measure,
    min_font: int = 11,
    max_font: int = 22,
    pad: int = 5,
    min_width: int = 190,
) -> list[Placed]:
    placed: list[Placed] = []
    for it in sorted(items, key=lambda i: (i.y0, i.x0)):
        if not it.ru.strip():
            continue
        font = int(max(min_font, min(max_font, round(it.line_h * 0.78))))
        width = int(min(max(it.w + 2 * pad, min_width), screen_w - 4))
        # Если перевод не помещается в разумную высоту — сначала уменьшаем шрифт, затем расширяем плашку.
        budget = max(it.h * 2.4, it.line_h * 3.2)
        while True:
            _, th = measure(it.ru, font, width - 2 * pad)
            if th + 2 * pad <= budget or font <= min_font:
                break
            font -= 1
        if th + 2 * pad > budget:
            wide = int(min(width * 1.6, screen_w - 4))
            _, th2 = measure(it.ru, font, wide - 2 * pad)
            if th2 < th:
                width, th = wide, th2
        height = int(th + 2 * pad)

        x = int(min(max(0, it.x0 - pad), max(0, screen_w - width)))
        y = int(min(max(0, it.y0 - pad), max(0, screen_h - height)))

        for _ in range(40):  # сдвигаем вниз, пока плашка не перестанет перекрывать уже размещённые
            hit = next((p for p in placed if _overlaps((x, y, width, height), p)), None)
            if hit is None:
                break
            y = hit.bottom + 2
        if y + height > screen_h:
            y = max(0, screen_h - height)

        placed.append(Placed(x, y, width, height, font, it.ru, it.zh, it.source, it.lore))
    return placed


def _hits(r: tuple[int, int, int, int], o: tuple[int, int, int, int]) -> bool:
    return r[0] < o[0] + o[2] and r[0] + r[2] > o[0] and r[1] < o[1] + o[3] and r[1] + r[3] > o[1]


def place_inplace(
    items: list[Item],
    screen_w: int,
    screen_h: int,
    measure: Measure,
    min_font: int = 9,
    max_font: int = 26,
    pad: int = 2,
) -> list[Placed]:
    """Перевод «на месте»: плашка закрывает ровно китайский текст и стоит там же.

    Русский текст обычно длиннее китайского, поэтому:
      1) подбираем шрифт под высоту строки оригинала и уменьшаем, пока текст не влезет;
      2) если не влез даже мелким шрифтом — расширяем плашку вправо, в свободное место
         (до соседнего текста или края экрана), потом вниз — тоже до соседа;
      3) соседние надписи при этом не перекрываются, если только места нет совсем.
    """
    src = [it for it in items if it.ru.strip()]
    # запас вокруг рамки OCR: рамка плотная, а хвосты иероглифов и сглаживание выходят за неё
    pads = [max(pad, round((it.line_h or it.h) * 0.16)) for it in src]
    rects = [(int(it.x0) - pd, int(it.y0) - pd, int(it.w) + 2 * pd, int(it.h) + 2 * pd) for it, pd in zip(src, pads)]
    out: list[Placed] = []
    for i, it in enumerate(src):
        x, y, w, h = rects[i]
        x, y = max(0, x), max(0, y)
        others = [r for j, r in enumerate(rects) if j != i]
        font = int(max(min_font, min(max_font, round(it.line_h * 0.8))))
        inner = lambda ww: max(10, ww - 2 * pad)  # noqa: E731

        def fits(ww: int, hh: int, f: int) -> bool:
            tw, th = measure(it.ru, f, inner(ww))
            # слово, которое не переносится, может оказаться шире плашки — это тоже «не влезло»
            return tw <= inner(ww) + 1 and th <= hh - 2 * pad + max(1, f // 5)

        # 0) короткая надпись: лучше одна строка в свободное место справа, чем перенос или мелкий шрифт
        if not fits(w, h, font):
            right0 = int(it.room_right) if it.room_right else screen_w
            for o in others:
                if o[1] < y + h and o[1] + o[3] > y and o[0] >= x + w - 2:
                    right0 = min(right0, o[0] - 2)
            one = measure(it.ru, font, 100000)[0] + 2 * pad + 2
            if x + one <= right0 and measure(it.ru, font, 100000)[1] <= h - 2 * pad + max(1, font // 5):
                w = one
        # 1) уменьшаем шрифт, но не ниже 70% от размера оригинала (иначе нечитаемо — лучше расширить)
        floor = max(min_font, int(font * 0.7))
        f = font
        while f > floor and not fits(w, h, f):
            f -= 1
        if not fits(w, h, f):
            # 2) вправо до соседа на той же высоте, края панели или экрана
            right = int(it.room_right) if it.room_right else screen_w
            for o in others:
                if o[1] < y + h and o[1] + o[3] > y and o[0] >= x + w - 2:
                    right = min(right, o[0] - 2)
            one_line_w = measure(it.ru, f, 100000)[0] + 2 * pad + 2
            w = max(w, min(right - x, one_line_w))
            if not fits(w, h, f):
                # 3) вниз до соседа ниже
                _, th = measure(it.ru, f, inner(w))
                need = th + 2 * pad
                bottom = int(it.room_bottom) if it.room_bottom else screen_h
                for o in others:
                    if o[0] < x + w and o[0] + o[2] > x and o[1] >= y + h - 2:
                        bottom = min(bottom, o[1] - 2)
                h = max(h, min(need, bottom - y))
                # 4) всё ещё не влезло — уменьшаем шрифт до минимума
                while f > min_font and not fits(w, h, f):
                    f -= 1
                if not fits(w, h, f):  # места нет совсем — текст важнее соседей
                    _, th = measure(it.ru, f, inner(w))
                    h = th + 2 * pad
        w = min(w, screen_w - x)
        if y + h > screen_h:
            y = max(0, screen_h - h)
        out.append(Placed(x, y, int(w), int(h), f, it.ru, it.zh, it.source, it.lore, it.bg, it.fg))
    return out
