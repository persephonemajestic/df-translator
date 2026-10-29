"""Шрифты в стиле Delta Force.

У самой игры: DIN 2014 в заголовках и Noto Sans в тексте. Поэтому:
  • текст — Noto Sans (статичные начертания с хинтингом: чёткие на тёмном фоне при любом размере),
    файлы кладёт в assets/fonts сборка на GitHub (лицензия SIL OFL);
  • заголовки — Bahnschrift: это DIN, встроенный в Windows 10/11, с кириллицей.
Если чего-то нет, берутся Segoe UI / Segoe UI Semibold.
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
    from PySide6.QtGui import QFont, QFontDatabase

    for path in sorted(fonts_dir().glob("NotoSans-*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(path))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if fams and "ui" not in _FAMILIES:
            _FAMILIES["ui"] = "Noto Sans" if "Noto Sans" in fams else fams[0]
    if "Bahnschrift" in QFontDatabase.families():
        _FAMILIES["display"] = "Bahnschrift"

    # Иероглифов и части значков в этих шрифтах нет — явно говорим Qt, чем их подменять.
    cjk: list[str] = []
    for path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyh.ttf"):
        if Path(path).exists():
            fid = QFontDatabase.addApplicationFont(path)
            cjk = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            break
    for fam in set(_FAMILIES.values()):
        QFont.insertSubstitutions(fam, cjk + ["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "Segoe UI Symbol",
                                              "Segoe UI Emoji", "SimSun"])
    return dict(_FAMILIES)


def ui_family() -> str:
    return _FAMILIES.get("ui", FALLBACK_UI)


def display_family() -> str:
    return _FAMILIES.get("display", FALLBACK_DISPLAY)
