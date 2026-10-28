"""Захват экрана средствами ОС (mss). Процесс игры не затрагивается.

Игра должна работать в режиме «Окно без рамки» (borderless), иначе при
полноэкранном эксклюзивном режиме снимок может оказаться чёрным.
"""
from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

import numpy as np


@dataclass
class Frame:
    image: np.ndarray  # BGR, HxWx3
    left: int
    top: int

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])


def cursor_pos() -> tuple[int, int]:
    if sys.platform.startswith("win"):
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))  # type: ignore[attr-defined]
        return pt.x, pt.y
    return 0, 0


def pick_monitor(monitors: list[dict], x: int, y: int) -> dict:
    for m in monitors:
        if m["left"] <= x < m["left"] + m["width"] and m["top"] <= y < m["top"] + m["height"]:
            return m
    return monitors[0]


def grab_monitor_at_cursor() -> Frame:
    import mss  # импортируем здесь: mss создаётся в потоке, который его использует

    with mss.mss() as sct:
        monitors = sct.monitors[1:] or [sct.monitors[0]]
        mon = pick_monitor(monitors, *cursor_pos())
        shot = sct.grab(mon)
        bgr = np.ascontiguousarray(np.asarray(shot)[:, :, :3])
        return Frame(bgr, int(mon["left"]), int(mon["top"]))


def crop(frame: Frame, x: int, y: int, w: int, h: int) -> Frame:
    x, y = max(0, x), max(0, y)
    w, h = min(w, frame.width - x), min(h, frame.height - y)
    return Frame(np.ascontiguousarray(frame.image[y : y + h, x : x + w]), frame.left + x, frame.top + y)
