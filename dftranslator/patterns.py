"""Составные строки интерфейса: «赛季任务：群星», «已完成 0/2», «第二阶段», «2-1赛季标准支线»,
и голова целей квеста «在巴克什机密/绝密行动中，…» (карта + режим переводятся точно, остальное — дальше)."""
from __future__ import annotations

import re
from typing import Callable

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

MAPS = {
    "零号大坝": "Нулевая плотина", "长弓溪谷": "Долина Длинного Лука", "航天基地": "Космическая база",
    "巴克什": "Браккеш", "潮汐监狱": "Приливная тюрьма",
}
MODES = {"机密": "Секретно", "绝密": "Совсекретно", "永夜": "Вечная ночь", "常规": "Обычный",
         "任意战区": "любой режим", "任意": "любой режим"}

_HEAD = re.compile(
    r"^在(?P<map>" + "|".join(MAPS) + r")(?P<mode>[^，,]*?)(?:战区)?行动中[，,]\s*(?P<rest>.+)$"
)
_TAIL = re.compile(r"^(?P<head>.*?[^\d\s/x×])\s*(?P<tail>\(?\d[\d,]*\s*/\s*\d[\d,]*\)?|[x×]\s*\d+)$")


def _num(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    return CN_NUM.get(s)


def split_objective_head(text: str) -> tuple[str, str] | None:
    """'在巴克什机密/绝密行动中，前往…' -> ('Браккеш · Секретно / Совсекретно: ', '前往…')."""
    m = _HEAD.match(text.strip())
    if not m:
        return None
    modes = [MODES.get(x) for x in m.group("mode").split("/") if x]
    if any(x is None for x in modes):
        return None
    mode = " / ".join(modes) if modes else "любой режим"
    return f"{MAPS[m.group('map')]} · {mode}: ", m.group("rest")


def compose(text: str, local: Callable[[str], str | None]) -> str | None:
    """Пробует собрать перевод из уже известных частей. local(part) -> перевод или None."""
    s = text.strip()

    m = re.fullmatch(r"第([一二三四五六七八九十\d]+)阶段", s)
    if m and _num(m.group(1)):
        return f"Этап {_num(m.group(1))}"
    m = re.fullmatch(r"赛季目标([一二三四五六七八九十\d]+)", s)
    if m and _num(m.group(1)):
        return f"Сезонная цель {_num(m.group(1))}"
    m = re.fullmatch(r"(\d+-\d+)\s*赛季标准支线", s)
    if m:
        return f"{m.group(1)} · Сезонная побочная линия"
    m = re.fullmatch(r"赛季剩余\s*(\d+)\s*天", s)
    if m:
        return f"До конца сезона: {m.group(1)} дн."
    m = re.fullmatch(r"(?:(\d+)天)?(?:(\d+)时)?(?:(\d+)分)?刷新委托", s)
    if m and any(m.groups()):
        parts = [f"{v} {u}" for v, u in zip(m.groups(), ("дн.", "ч", "мин")) if v]
        return "Новые заказы через " + " ".join(parts)

    # «A：B» — обе части известны
    for sep in ("：", ":"):
        if sep in s:
            a, b = s.split(sep, 1)
            ra, rb = local(a.strip()), local(b.strip()) if b.strip() else ""
            if ra and rb is not None and (rb or not b.strip()):
                return f"{ra}: {rb}".rstrip(": ") if rb else f"{ra}:"
    # «已完成 0/2», «星火 x8»
    m = _TAIL.match(s)
    if m:
        rh = local(m.group("head").strip())
        if rh:
            return f"{rh} {m.group('tail').replace(' ', '')}"
    return None
