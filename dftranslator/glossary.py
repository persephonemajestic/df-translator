"""Глоссарий терминов: точные совпадения, защита терминов при машинном переводе.

Файлы:
  data/glossary.json       — базовый глоссарий (поставляется с программой)
  <user>/glossary_user.json — правки сообщества/пользователя, важнее базового:
        {"ui": {...}, "places": {...}, "items": {...}, "quest_names": {...}, ...}
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .text import norm_key

# Категории, термины которых защищаются внутри предложений при машинном переводе.
PROTECT_CATEGORIES = ("places", "factions", "departments", "terms", "locations", "enemies", "items")
# Категории, сопоставляемые с целой строкой.
EXACT_CATEGORIES = ("ui", "places", "factions", "departments", "terms", "locations", "enemies", "items")

PLACEHOLDER_FMT = "Qx{n}z"
_PLACEHOLDER_RE = re.compile(r"Q\s*x\s*(\d+)\s*z", re.IGNORECASE)


@dataclass(frozen=True)
class Hit:
    ru: str
    category: str
    zh: str


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


class Glossary:
    def __init__(self, data_dir: Path, user_dir: Path | None = None, overlay_dir: Path | None = None):
        self.data_dir = Path(data_dir)
        # overlay_dir — свежий словарь, скачанный с GitHub без обновления программы (приоритетнее встроенного)
        self.overlay_dir = Path(overlay_dir) if overlay_dir else None
        self.user_dir = Path(user_dir) if user_dir else None
        self.exact: dict[str, Hit] = {}
        self.protect_terms: dict[str, Hit] = {}
        self.quest_names: dict[str, str] = {}
        self.quest_names_norm: dict[str, str] = {}
        self._protect_re: re.Pattern | None = None
        self.reload()

    # ------------------------------------------------------------------ load
    def reload(self) -> None:
        self.exact.clear()
        self.protect_terms.clear()
        self.quest_names.clear()
        self.quest_names_norm.clear()

        base = _load_json(self._path("glossary.json"))
        names = _load_json(self._path("quest_names.json"))
        user = _load_json(self.user_dir / "glossary_user.json") if self.user_dir else {}

        for source in (base, user):  # пользовательские правки перекрывают базовые
            for cat in EXACT_CATEGORIES:
                for zh, ru in (source.get(cat) or {}).items():
                    self._add(cat, zh, ru)

        for source in (names, user):
            for section, mapping in source.items():
                if section.startswith("_"):
                    continue
                if source is user and section != "quest_names":
                    continue
                if not isinstance(mapping, dict):
                    continue
                if source is names and section == "categories":
                    for zh, ru in mapping.items():
                        self._add("terms", zh, ru)
                    continue
                for zh, ru in mapping.items():
                    self.quest_names[zh] = ru

        self.quest_names_norm = {norm_key(k): v for k, v in self.quest_names.items()}
        self._build_protect_regex()

    def _path(self, name: str) -> Path:
        if self.overlay_dir and (self.overlay_dir / name).exists():
            return self.overlay_dir / name
        return self.data_dir / name

    def _add(self, category: str, zh: str, ru: str) -> None:
        key = norm_key(zh)
        if not key:
            return
        hit = Hit(ru=ru, category=category, zh=zh)
        # ui имеет приоритет для целых строк интерфейса, но не для защиты терминов
        if key not in self.exact or category == "ui" or self.exact[key].category != "ui":
            self.exact[key] = hit
        if category in PROTECT_CATEGORIES and len(key) >= 2:
            self.protect_terms[key] = hit

    def _build_protect_regex(self) -> None:
        keys = sorted(self.protect_terms, key=len, reverse=True)
        self._protect_re = re.compile("|".join(re.escape(k) for k in keys)) if keys else None

    # ---------------------------------------------------------------- lookup
    def lookup(self, text: str) -> Hit | None:
        return self.exact.get(norm_key(text))

    def lookup_quest_name(self, text: str) -> str | None:
        key = norm_key(text)
        if key in self.quest_names_norm:
            return self.quest_names_norm[key]
        return None

    # --------------------------------------------------------------- protect
    def find_terms(self, text: str) -> dict[str, str]:
        """Термины глоссария, найденные в тексте: {zh: ru} (для подсказки LLM)."""
        found: dict[str, str] = {}
        if not self._protect_re:
            return found
        key_text = norm_key(text)
        for m in self._protect_re.finditer(key_text):
            hit = self.protect_terms[m.group(0)]
            found[hit.zh] = hit.ru
        return found

    def protect(self, text: str) -> tuple[str, dict[int, str]]:
        """Заменяет термины на нейтральные токены Qx1z... Возвращает (текст, {n: ru})."""
        mapping: dict[int, str] = {}
        if not self._protect_re:
            return text, mapping
        # Ищем в тексте с учётом регистра исходной строки: ключи в нижнем регистре,
        # поэтому работаем по копии без пробелов только для китайской части.
        lowered = text.lower()
        out: list[str] = []
        pos = 0
        counter = 0
        for m in self._protect_re.finditer(lowered):
            counter += 1
            hit = self.protect_terms[m.group(0)]
            out.append(text[pos : m.start()])
            out.append(PLACEHOLDER_FMT.format(n=counter))
            mapping[counter] = hit.ru
            pos = m.end()
        out.append(text[pos:])
        return "".join(out), mapping

    @staticmethod
    def restore(text: str, mapping: dict[int, str]) -> str:
        if not mapping:
            return text

        def repl(m: re.Match) -> str:
            return mapping.get(int(m.group(1)), m.group(0))

        return _PLACEHOLDER_RE.sub(repl, text)
