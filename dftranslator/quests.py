"""Квесты: названия, награды, цели.

Три уровня точности:
  1. Названия квестов — каталог data/quest_names.json (+ правки пользователя),
     плюс разбор числового суффикса для новых серий («Название 7»).
  2. Награды вида «哈夫币x15000», «CAR15小改x1» — разбор + глоссарий.
  3. Цели — база objectives_ru.json (её готовит tools/translate_quests.py из выгрузки
     kkrb.net) с нечётким сопоставлением, чтобы шум OCR не мешал.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from .glossary import Glossary
from .text import has_cjk, fmt_int, norm_key

_WEAPON_CLASS = {
    "突击步枪": "штурмовая винтовка", "冲锋枪": "пистолет-пулемёт", "射手步枪": "марксманская винтовка",
    "狙击步枪": "снайперская винтовка", "霰弹枪": "дробовик", "轻机枪": "ручной пулемёт", "机枪": "пулемёт",
    "手枪": "пистолет", "步枪": "винтовка",
}
_SUFFIX_RE = re.compile(r"^(?P<base>.+?)(?P<sep>[-－—]?)(?P<num>\d{1,3})$")
_RU_SUFFIX_RE = re.compile(r"^(?P<base>.+?)(?P<sep>\s—\s|\s)(?P<num>\d{1,3})$")
_REWARD_RE = re.compile(r"^(?P<name>.+?)\s*[x×X](?P<n>\d[\d,]*)$")
_GRADE_RE = re.compile(r"^(?P<name>.+?)(?P<grade>小改|半改|满改|裸枪)$")


class QuestBook:
    def __init__(self, glossary: Glossary, objectives_path: Path | None = None):
        self.g = glossary
        self.objectives: dict[str, str] = {}      # norm_key(zh) -> ru
        self._obj_keys: list[str] = []
        self.series: dict[str, tuple[str, str]] = {}  # база серии -> (ru без номера, разделитель)
        self._build_series()
        if objectives_path and Path(objectives_path).exists():
            self.load_objectives(Path(objectives_path))

    def _build_series(self) -> None:
        """Из нумерованных названий каталога («高耸入云1» / «Заоблачные высоты 1») выводит базу серии."""
        for zh_key, ru in self.g.quest_names_norm.items():
            zm = _SUFFIX_RE.match(zh_key)
            rm = _RU_SUFFIX_RE.match(ru)
            if zm and rm and zm.group("num") == rm.group("num"):
                self.series.setdefault(zm.group("base"), (rm.group("base"), rm.group("sep")))

    # ------------------------------------------------------------- objectives
    def add_objectives(self, mapping: dict[str, str]) -> None:
        """Цели из базы квестов (ключи уже нормализованы)."""
        for k, v in mapping.items():
            self.objectives.setdefault(norm_key(k), v)
        self._obj_keys = list(self.objectives)

    def load_objectives(self, path: Path) -> None:
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
        self.objectives = {norm_key(k): v for k, v in raw.items() if isinstance(v, str) and v}
        self._obj_keys = list(self.objectives)

    def objective(self, text: str, cutoff: float = 0.92) -> str | None:
        key = norm_key(text)
        if key in self.objectives:
            return self.objectives[key]
        if len(key) < 10 or not self._obj_keys:
            return None
        # Нечёткое сопоставление только среди строк близкой длины — быстро и безопасно.
        lo, hi = int(len(key) * 0.85), int(len(key) * 1.15) + 1
        candidates = [k for k in self._obj_keys if lo <= len(k) <= hi]
        match = difflib.get_close_matches(key, candidates, n=1, cutoff=cutoff)
        return self.objectives[match[0]] if match else None

    # ------------------------------------------------------------------ names
    def quest_name(self, text: str, fuzzy_cutoff: float = 0.85) -> str | None:
        direct = self.g.lookup_quest_name(text)
        if direct:
            return direct
        key = norm_key(text)
        # «Название 7» для серий, которых нет в каталоге: переводим базу, сохраняем номер.
        if key in self.series:  # заголовок серии без номера
            return self.series[key][0]
        m = _SUFFIX_RE.match(key)
        if m and m.group("base") in self.series:
            base_ru, sep = self.series[m.group("base")]
            return f"{base_ru}{sep}{m.group('num')}"
        if m and m.group("base") in self.g.quest_names_norm:  # «爱的咏叹调-4» при известной базе
            return f"{self.g.quest_names_norm[m.group('base')]} — {m.group('num')}"
        # Нечёткое совпадение для шума OCR (только для названий от 3 символов).
        if len(key) >= 3:
            match = difflib.get_close_matches(key, list(self.g.quest_names_norm), n=1, cutoff=fuzzy_cutoff)
            if match:
                return self.g.quest_names_norm[match[0]]
        return None

    # ---------------------------------------------------------------- rewards
    def reward(self, text: str) -> str | None:
        """«哈夫币x15000» -> «Хаавк-коины ×15 000», «CAR15小改x1» -> «CAR15 (лёгкий тюнинг) ×1»."""
        raw = text.strip()
        count = None
        m = _REWARD_RE.match(raw)
        name = raw
        if m:
            name, count = m.group("name"), m.group("n").replace(",", "")
        name_ru = self._reward_name(name)
        if name_ru is None:
            return None
        return f"{name_ru} ×{fmt_int(count)}" if count is not None else name_ru

    def _reward_name(self, name: str) -> str | None:
        hit = self.g.lookup(name)
        if hit:
            return hit.ru
        name = name.strip()
        gm = _GRADE_RE.match(name)
        if gm:
            grade = self.g.lookup(gm.group("grade"))
            base_ru = self._reward_name(gm.group("name")) or gm.group("name")
            if grade:
                if base_ru.endswith(")"):   # «QJB201 (ручной пулемёт)» -> «QJB201 (ручной пулемёт, лёгкий тюнинг)»
                    return f"{base_ru[:-1]}, {grade.ru})"
                return f"{base_ru} ({grade.ru})"
        pm = re.match(r"^(小改|半改|满改|裸枪)(.+)$", name)  # «半改M14»
        if pm:
            return self._reward_name(pm.group(2) + pm.group(1))
        for suffix, ru in _WEAPON_CLASS.items():  # «Vector冲锋枪»
            if name.endswith(suffix) and not has_cjk(name[: -len(suffix)]):
                return f"{name[: -len(suffix)].strip()} ({ru})"
        if not has_cjk(name):  # патроны, модели оружия: «5.45x39mm BT»
            return name
        return None
