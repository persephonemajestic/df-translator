"""Шаблонный перевод самых частых целей квестов.

Это точный и предсказуемый слой для формулировок вида
«在零号大坝任意战区行动中,击败5名敌方士兵。». Всё, что не подошло под шаблон,
уходит дальше (база целей, затем машинный перевод с защитой терминов).

Формулировки намеренно без склонений числительных («…: 5»), чтобы не ошибаться
в падежах.
"""
from __future__ import annotations

import re

from .text import fmt_int, norm_key

MAPS = {
    "零号大坝": "Нулевая плотина",
    "长弓溪谷": "Долина Длинного Лука",
    "航天基地": "Космическая база",
    "巴克什": "Браккеш",
    "潮汐监狱": "Приливная тюрьма",
}

SCOPES = {
    "任意战区行动": "любая операция",
    "战区行动": "любая операция",
    "任意战局": "любая операция",
    "任意战区": "любая операция",
    "机密行动": "секретная операция",
    "绝密行动": "совсекретная операция",
    "行动": "любая операция",
    "战局": "любой матч",
}

ENEMIES_GEN = {
    "敌方士兵": "вражеских солдат",
    "敌方特战干员": "вражеских оперативников",
    "敌对特战干员": "вражеских оперативников",
    "敌方玩家": "вражеских игроков",
    "敌方特殊兵种": "вражеских спецбойцов",
    "阿萨拉盾兵": "щитовиков Асары",
    "阿萨拉火箭兵": "ракетчиков Асары",
    "阿萨拉狙击兵": "снайперов Асары",
    "阿萨拉机枪兵": "пулемётчиков Асары",
    "哈夫克机枪兵": "пулемётчиков Хаавк",
    "哈夫克盾兵": "щитовиков Хаавк",
    "喷火兵": "огнемётчиков",
}

_MAP_ALT = "|".join(map(re.escape, MAPS))
_SCOPE_ALT = "|".join(map(re.escape, sorted(SCOPES, key=len, reverse=True)))
_ENEMY_ALT = "|".join(map(re.escape, sorted(ENEMIES_GEN, key=len, reverse=True)))

_PREFIX = rf"^(?:在|从|前往)?(?P<map>{_MAP_ALT})(?P<scope>{_SCOPE_ALT})?(?:中|内)?,?"

_KILL = re.compile(rf"{_PREFIX}(?:击败|击杀|淘汰)(?P<n>\d+)(?:名|只|个)(?P<e>{_ENEMY_ALT})$")
_EXTRACT_N = re.compile(rf"{_PREFIX}成功撤离(?P<n>\d+)次$")
_EXTRACT_ONCE = re.compile(rf"{_PREFIX}成功撤离$")
_PROFIT = re.compile(
    rf"{_PREFIX}成功撤离时(?:当)?单局收益(?:达到|需?大于等于|不低于)(?P<v>\d+)哈夫币,?完成(?P<n>\d+)次$"
)


def _head(m: re.Match) -> str:
    scope = SCOPES.get(m.group("scope") or "行动", "любая операция")
    return f"{MAPS[m.group('map')]}, {scope}"


def _times(n: int) -> str:
    return "1 раз" if n == 1 else f"{n} раз(а)"


def translate_objective(text: str) -> str | None:
    s = norm_key(text)
    s = s.replace("。", "").rstrip(".")

    m = _KILL.match(s)
    if m:
        return f"{_head(m)}: победить {ENEMIES_GEN[m.group('e')]} — {m.group('n')}."

    m = _PROFIT.match(s)
    if m:
        return (
            f"{_head(m)}: успешно эвакуироваться с доходом за матч не менее "
            f"{fmt_int(m.group('v'))} Хаавк-коинов — {_times(int(m.group('n')))}."
        )

    m = _EXTRACT_N.match(s)
    if m:
        return f"{_head(m)}: успешно эвакуироваться — {_times(int(m.group('n')))}."

    m = _EXTRACT_ONCE.match(s)
    if m:
        return f"{_head(m)}: успешно эвакуироваться — 1 раз."

    return None
