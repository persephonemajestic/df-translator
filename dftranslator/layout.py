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
