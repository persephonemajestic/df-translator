"""Определяет «пользователь что-то нажал» (клавиша или кнопка мыши) без хуков и без доступа к игре.

Используется обычный опрос GetAsyncKeyState, пока на экране висит перевод. Какие именно клавиши нажаты,
нигде не сохраняется и не передаётся — важен только сам факт нового нажатия.
"""
from __future__ import annotations

import sys

VK_RANGE = range(0x01, 0xFF)
SKIP = {0x03, 0x07, 0x0A, 0x0B, 0x0E, 0x0F}  # не назначенные коды


def detect_new_press(prev: frozenset[int], cur: frozenset[int]) -> bool:
    """True, если появилась клавиша, которой не было в прошлом опросе (удержание не считается)."""
    return bool(cur - prev)


def pressed_keys() -> frozenset[int]:
    if not sys.platform.startswith("win"):
        return frozenset()
    import ctypes

    get = ctypes.windll.user32.GetAsyncKeyState  # type: ignore[attr-defined]
    return frozenset(vk for vk in VK_RANGE if vk not in SKIP and get(vk) & 0x8000)
