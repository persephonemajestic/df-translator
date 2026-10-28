"""Автозапуск с Windows через ключ реестра HKCU\\...\\Run (права администратора не нужны)."""
from __future__ import annotations

import sys

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "DFTranslator"


def supported() -> bool:
    return sys.platform.startswith("win")


def command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{exe}" -m dftranslator --tray'


def is_enabled() -> bool:
    if not supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            winreg.QueryValueEx(k, NAME)
            return True
    except OSError:
        return False


def set_enabled(on: bool) -> None:
    if not supported():
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(k, NAME)
            except OSError:
                pass
