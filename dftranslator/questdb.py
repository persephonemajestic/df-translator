"""База квестов отделов (data/quests/*.json): цели с переводом, награды, карты, скриншоты мест.

Данные и скриншоты — kkrb.net (автор Key725); переводы целей — по лору игры.
Модуль без Qt — тестируется отдельно.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .text import norm_key

IMG_BASE = "https://images.kkrb.net/image/department/guidance/"
DEPTS = ["combat", "medical", "tactical", "logistics", "research", "season"]
DEPT_RU = {
    "combat": "Боевой отдел · «Ударная волна»",
    "medical": "Медицинский отдел · «За чертой жизни»",
    "tactical": "Тактический отдел · «Оружейник Асары»",
    "logistics": "Отдел снабжения · «В полной выкладке»",
    "research": "Отдел исследований · «Воля Матрицы»",
    "season": "Сезонные задания · «Созвездие»",
}
TYPE_RU = {"主线任务": "Основной", "支线任务": "Побочный", "赛季主线": "Сезонная основная линия",
           "赛季标准支线": "Сезонная побочная линия"}
MAP_RU = {
    "零号大坝": "Нулевая плотина", "长弓溪谷": "Долина Длинного Лука", "航天基地": "Космическая база",
    "巴克什": "Браккеш", "潮汐监狱": "Приливная тюрьма", "任意战区行动": "Любая карта",
    "任意机密/绝密行动": "Любая карта (Секретно / Совсекретно)", "局外": "Вне рейда",
}
MODE_RU = {"常规": "Обычный", "机密": "Секретно", "绝密": "Совсекретно", "永夜": "Вечная ночь"}
FORCED_RU = {
    "单局未完成全部目标任务重置": "Все цели — за один рейд, иначе прогресс сбросится",
    "单局内未完成任务此目标将重置": "Цель нужно выполнить за один рейд, иначе она сбросится",
    "任务中撤离失败一次则整个任务进度重置": "Одна неудачная эвакуация — и прогресс задания сбросится",
    "单局任务目标全部完成否则重置整个任务进度": "Все цели — за один рейд, иначе прогресс задания сбросится",
}


@dataclass
class Quest:
    dept: str
    key: int
    parent: int | None
    name: str
    qtype: str
    map: str
    forced: str
    images: list[int]
    objectives: list[tuple[str, str]]
    rewards: list[str]
    name_ru: str = ""

    @property
    def id(self) -> str:
        return f"{self.dept}-{self.key}"

    def image_urls(self) -> list[str]:
        return [f"{IMG_BASE}{self.dept}_department_mission/task{self.key}_{n:02d}.webp" for n in self.images]

    def map_ru(self) -> str:
        return translate_map(self.map)

    def items(self) -> list[str]:
        """Квестовые предметы и то, что нужно принести с собой — по переводу целей."""
        out: list[str] = []
        for _, ru in self.objectives:
            for m in re.finditer(r"квестовый предмет «([^»]+)»", ru):
                out.append(m.group(1))
            if "принести с собой" in ru or "нужен ключ" in ru or "нужна ключ" in ru:
                note = re.search(r"\(([^)]*(?:принести с собой|нужен ключ|нужна ключ)[^)]*)\)", ru)
                what = re.search(r"(?:положить|поставить) (.+?) (?:в|на|у|под) ", ru)
                if what and "принести" in (note.group(1) if note else ""):
                    out.append(f"{what.group(1)} — взять с собой")
                elif note:
                    out.append(note.group(1)[0].upper() + note.group(1)[1:])
        seen, uniq = set(), []
        for x in out:
            k = x.lower()
            if k not in seen:
                seen.add(k)
                uniq.append(x)
        return uniq


def translate_map(text: str) -> str:
    parts = [p.strip() for p in re.split(r"[,，]", text or "") if p.strip()]
    grouped: dict[str, list[str]] = {}
    for p in parts:
        m = re.match(r"^(.+?)[（(](.+?)[)）]$", p)
        base, mode = (m.group(1), m.group(2)) if m else (p, "")
        name = MAP_RU.get(base, base)
        grouped.setdefault(name, [])
        if mode:
            grouped[name].append(MODE_RU.get(mode, mode))
    return "; ".join(f"{k} ({', '.join(v)})" if v else k for k, v in grouped.items())


class QuestDB:
    def __init__(self, data_dir: Path, overlay_dir: Path | None = None):
        self.quests: list[Quest] = []
        self.by_name: dict[str, Quest] = {}
        self.objectives: dict[str, str] = {}
        self._load(Path(data_dir), Path(overlay_dir) if overlay_dir else None)

    def _load(self, data_dir: Path, overlay: Path | None) -> None:
        for dept in DEPTS:
            path = None
            for base in (overlay, data_dir):
                if base and (base / "quests" / f"{dept}.json").exists():
                    path = base / "quests" / f"{dept}.json"
                    break
            if path is None:
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for q in raw:
                imgs = q.get("i", 0)
                images = list(range(1, int(imgs) + 1)) if isinstance(imgs, int) else [int(x) for x in imgs]
                quest = Quest(
                    dept=dept, key=int(q["k"]), parent=q.get("p"), name=q["n"], qtype=q.get("t", ""),
                    map=q.get("m", ""), forced=q.get("f", ""), images=images,
                    objectives=[(a, b) for a, b in q.get("o", [])], rewards=list(q.get("r", [])),
                )
                self.quests.append(quest)
                self.by_name.setdefault(norm_key(quest.name), quest)
                for zh, ru in quest.objectives:
                    self.objectives[norm_key(zh)] = ru

    def set_names(self, lookup) -> None:
        """lookup(zh) -> ru: проставляет русские названия (из quest_names.json)."""
        for q in self.quests:
            q.name_ru = lookup(q.name) or q.name

    def get(self, quest_id: str) -> Quest | None:
        return next((q for q in self.quests if q.id == quest_id), None)

    def match_name(self, text: str, cutoff: float = 0.86) -> Quest | None:
        key = norm_key(text)
        if not key:
            return None
        if key in self.by_name:
            return self.by_name[key]
        if len(key) >= 3:
            m = difflib.get_close_matches(key, list(self.by_name), n=1, cutoff=cutoff)
            if m:
                return self.by_name[m[0]]
        return None

    def search(self, query: str, dept: str = "") -> list[Quest]:
        q = query.strip().lower()
        out = []
        for quest in self.quests:
            if dept and quest.dept != dept:
                continue
            if not q or q in quest.name.lower() or q in quest.name_ru.lower() \
                    or any(q in ru.lower() or q in zh for zh, ru in quest.objectives):
                out.append(quest)
        return out
