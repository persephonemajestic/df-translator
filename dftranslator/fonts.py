"""Встроенные шрифты: Golos Text (текст интерфейса и перевод на экране) и Unbounded (заголовки).

Оба под лицензией SIL OFL, сделаны с полной поддержкой кириллицы. Файлы кладёт в assets/fonts
сборка на GitHub; если их нет (запуск из исходников), берутся системные шрифты.
"""
from __future__ import annotations

import sys
from pathlib import Path

_FAMILIES: dict[str, str] = {}
FALLBACK_UI = "Segoe UI"
FALLBACK_DISPLAY = "Segoe UI Semibold"


def fonts_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / "fonts"


def load_fonts() -> dict[str, str]:
    """Регистрирует шрифты в Qt. Вызывать после создания QApplication."""
    from PySide6.QtGui import QFontDatabase

    for key, pattern in (("ui", "GolosText*.ttf"), ("display", "Unbounded*.ttf")):
        for path in sorted(fonts_dir().glob(pattern)):
            fid = QFontDatabase.addApplicationFont(str(path))
            fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            if fams:
                _FAMILIES[key] = fams[0]
                break
    return dict(_FAMILIES)


def ui_family() -> str:
    return _FAMILIES.get("ui", FALLBACK_UI)


def display_family() -> str:
    return _FAMILIES.get("display", FALLBACK_DISPLAY)
