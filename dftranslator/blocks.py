"""Группировка строк OCR в смысловые блоки (абзацы описаний квестов, подписи кнопок)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .text import has_cjk


@dataclass
class OcrLine:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    score: float = 1.0

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0


@dataclass
class Block:
    x0: float
    y0: float
    x1: float
    y1: float
    lines: list[OcrLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        out = ""
        for ln in self.lines:
            t = ln.text.strip()
            if out and out[-1].isascii() and out[-1].isalnum() and t[:1].isascii() and t[:1].isalnum():
                out += " "
            out += t
        return out

    @property
    def line_h(self) -> float:
        return sum(l.h for l in self.lines) / len(self.lines)

    @classmethod
    def from_line(cls, ln: OcrLine) -> "Block":
        return cls(ln.x0, ln.y0, ln.x1, ln.y1, [ln])

    def add(self, ln: OcrLine) -> None:
        self.lines.append(ln)
        self.x0, self.y0 = min(self.x0, ln.x0), min(self.y0, ln.y0)
        self.x1, self.y1 = max(self.x1, ln.x1), max(self.y1, ln.y1)


def box_to_rect(points) -> tuple[float, float, float, float]:
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _can_join(block: Block, ln: OcrLine) -> bool:
    last = block.lines[-1]
    h = (last.h + ln.h) / 2 or 1.0
    gap = ln.y0 - last.y1
    if not (-0.4 * h <= gap <= 0.6 * h):
        return False
    if not (0.7 <= (ln.h / last.h if last.h else 0) <= 1.4):
        return False
    if abs(ln.x0 - block.lines[0].x0) > 0.8 * h:
        return False
    if ln.x0 >= block.x1 or ln.x1 <= block.x0:
        return False
    # Предыдущая строка абзаца обычно «полная»; короткие подписи (пункты меню, кнопки) не склеиваем.
    if len(last.text.strip()) < 8:
        return False
    if last.x1 < block.x1 - 2.5 * h:
        return False
    return True


def group_blocks(lines: list[OcrLine], merge: bool = True) -> list[Block]:
    cjk = [l for l in lines if has_cjk(l.text)]
    cjk.sort(key=lambda l: (round(l.y0 / 4), l.x0))
    blocks: list[Block] = []
    for ln in cjk:
        target = None
        if merge:
            for b in reversed(blocks[-8:]):
                if _can_join(b, ln):
                    target = b
                    break
        if target is not None:
            target.add(ln)
        else:
            blocks.append(Block.from_line(ln))
    blocks.sort(key=lambda b: (b.y0, b.x0))
    return blocks
