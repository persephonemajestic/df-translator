"""Глобальные горячие клавиши через RegisterHotKey (Windows).

Используется штатный системный механизм: никаких низкоуровневых хуков клавиатуры
и никакого взаимодействия с процессом игры.
"""
from __future__ import annotations

import sys
import threading
from typing import Callable

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}


def parse_hotkey(spec: str) -> tuple[int, int]:
    """'Ctrl+Alt+T' -> (modifiers, virtual_key)."""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError("Пустое сочетание клавиш")
    mods = 0
    key = parts[-1]
    for p in parts[:-1]:
        if p not in _MODS:
            raise ValueError(f"Неизвестный модификатор «{p}» в «{spec}»")
        mods |= _MODS[p]
    if mods == 0:
        raise ValueError(f"В «{spec}» нужен хотя бы один модификатор (Ctrl/Alt/Shift/Win)")
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    else:
        named = {"space": 0x20, "tab": 0x09, "enter": 0x0D, "esc": 0x1B, "insert": 0x2D,
                 "delete": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22}
        if key not in named:
            raise ValueError(f"Неизвестная клавиша «{key}» в «{spec}»")
        vk = named[key]
    return mods, vk


# Коды клавиш Qt (Qt.Key_*), которые можно назначить. Без импорта Qt — чтобы тестировать отдельно.
_QT_NAMED = {
    0x20: "Space", 0x01000001: "Tab", 0x01000004: "Enter", 0x01000005: "Enter", 0x01000006: "Insert",
    0x01000007: "Delete", 0x01000010: "Home", 0x01000011: "End", 0x01000016: "PageUp", 0x01000017: "PageDown",
}


def qt_key_to_name(code: int) -> str | None:
    """Код клавиши Qt -> имя для parse_hotkey; None, если клавишу назначить нельзя (в т.ч. модификаторы)."""
    if 0x41 <= code <= 0x5A or 0x30 <= code <= 0x39:
        return chr(code)
    if 0x01000030 <= code <= 0x01000047:  # F1..F24
        return f"F{code - 0x01000030 + 1}"
    return _QT_NAMED.get(code)


def format_hotkey(ctrl: bool, alt: bool, shift: bool, win: bool, key: str) -> str:
    parts = [n for n, on in (("Ctrl", ctrl), ("Alt", alt), ("Shift", shift), ("Win", win)) if on]
    return "+".join(parts + [key])


def validate_bindings(bindings: dict[str, str]) -> dict[str, str]:
    """Возвращает {действие: сообщение об ошибке} — неверные сочетания и дубликаты."""
    errors: dict[str, str] = {}
    seen: dict[tuple[int, int], str] = {}
    for name, spec in bindings.items():
        try:
            key = parse_hotkey(spec)
        except ValueError as exc:
            errors[name] = str(exc)
            continue
        if key in seen:
            errors[name] = f"Уже занято действием «{seen[key]}»"
        else:
            seen[key] = name
    return errors


class HotkeyListener:
    """Поток с циклом сообщений Windows; вызывает callback(name) при нажатии."""

    def __init__(self, bindings: dict[str, str], callback: Callable[[str], None]):
        self.bindings = bindings
        self.callback = callback
        self.errors: list[str] = []
        self._thread: threading.Thread | None = None
        self._tid = 0
        self._ready = threading.Event()

    def start(self) -> None:
        if not sys.platform.startswith("win"):
            self.errors.append("Горячие клавиши поддерживаются только в Windows")
            return
        self._thread = threading.Thread(target=self._run, name="hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(2.0)

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32  # type: ignore[attr-defined]
        self._tid = kernel32.GetCurrentThreadId()
        names: dict[int, str] = {}
        for i, (name, spec) in enumerate(self.bindings.items(), start=1):
            try:
                mods, vk = parse_hotkey(spec)
            except ValueError as exc:
                self.errors.append(str(exc))
                continue
            if user32.RegisterHotKey(None, i, mods | MOD_NOREPEAT, vk):
                names[i] = name
            else:
                self.errors.append(f"Сочетание {spec} уже занято другой программой")
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY and msg.wParam in names:
                try:
                    self.callback(names[msg.wParam])
                except Exception:  # noqa: BLE001 — хоткей не должен ронять поток
                    pass
        for i in names:
            user32.UnregisterHotKey(None, i)

    def stop(self) -> None:
        if self._tid and sys.platform.startswith("win"):
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)  # type: ignore[attr-defined]
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(1.0)  # дождаться UnregisterHotKey, иначе новое сочетание может не зарегистрироваться
