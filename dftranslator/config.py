"""Настройки программы (JSON в папке пользователя)."""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

APP_NAME = "DFTranslator"

DEFAULTS: dict = {
    "hotkeys": {
        "full_screen": "Ctrl+Alt+T",
        "region": "Ctrl+Alt+R",
        "clear": "Ctrl+Alt+C",
        "toggle_mode": "Ctrl+Alt+M",
        "quit": "Ctrl+Alt+Q",
    },
    # google — без ключа (неофициальный бесплатный эндпоинт); deepl и claude — по ключу.
    "engine": "google",
    "engines": {
        "google": {},
        "deepl": {"api_key": ""},
        "claude": {"api_key": "", "model": "claude-haiku-5-5"},
    },
    "display": {
        # overlay — перевод поверх оригинала (прозрачное окно, клики проходят сквозь него)
        # panel   — отдельное окно со списком (его можно вынести на второй монитор)
        "mode": "overlay",
        "min_font_px": 11,
        "max_font_px": 22,
        "opacity": 0.93,
        "auto_hide_sec": 0,
        "panel_always_on_top": True,
        "show_source_dots": True,
        "show_hint": True,
        "hide_on_input": True,     # убирать перевод после любого нажатия клавиши/кнопки мыши
        "hide_delay_sec": 1.5,     # через сколько секунд после нажатия
    },
    "updates": {
        "auto": True,   # скачивать и ставить обновления тихо, когда программа не занята
        "repo": "persephonemajestic/df-translator",
    },
    "ocr": {
        "min_score": 0.55,
        "merge_lines": True,
        "region_upscale": True,
    },
}


def config_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _merge(dst: dict, src: dict) -> dict:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def load_config(path: Path | None = None) -> dict:
    path = path or (config_dir() / "config.json")
    cfg = copy.deepcopy(DEFAULTS)
    if path.exists():
        try:
            with path.open(encoding="utf-8") as f:
                _merge(cfg, json.load(f))
        except (OSError, ValueError):
            pass  # битый файл — работаем с настройками по умолчанию
    else:
        save_config(cfg, path)
    # Ключи можно задавать переменными окружения, чтобы не хранить их в файле.
    env_claude = os.environ.get("ANTHROPIC_API_KEY")
    if env_claude and not cfg["engines"]["claude"].get("api_key"):
        cfg["engines"]["claude"]["api_key"] = env_claude
    env_deepl = os.environ.get("DEEPL_API_KEY")
    if env_deepl and not cfg["engines"]["deepl"].get("api_key"):
        cfg["engines"]["deepl"]["api_key"] = env_deepl
    return cfg


def save_config(cfg: dict, path: Path | None = None) -> None:
    path = path or (config_dir() / "config.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
