"""Понимает «пользователь что-то нажал», не следя за клавиатурой.

Используются два безобидных системных вызова, которыми пользуются мессенджеры и заставки:
GetLastInputInfo (время последнего ввода, без информации о том, ЧТО нажато) и GetCursorPos.
Если ввод был, а курсор не сдвинулся — значит, нажали клавишу или кнопку мыши.
Никакого опроса клавиш, хуков и обращения к игре.
"""
from __future__ import annotations

import sys


def detect_press(prev_tick: int, cur_tick: int, prev_pos: tuple[int, int], cur_pos: tuple[int, int]) -> bool:
    """Был новый ввод и при этом курсор стоял на месте → нажатие (клавиша / кнопка мыши)."""
    return cur_tick != prev_tick and cur_pos == prev_pos


def last_input_tick() -> int:
    if not sys.platform.startswith("win"):
        return 0
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))  # type: ignore[attr-defined]
    return int(info.dwTime)


def cursor_pos() -> tuple[int, int]:
    if not sys.platform.startswith("win"):
        return (0, 0)
    import ctypes

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))  # type: ignore[attr-defined]
    return (pt.x, pt.y)
