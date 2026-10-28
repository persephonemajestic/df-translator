"""История последних переводов (для окна «История» и исправлений)."""
from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from urllib.parse import urlencode


@dataclass
class Entry:
    zh: str
    ru: str
    source: str
    lore: bool
    ts: float


class History:
    def __init__(self, limit: int = 300):
        self.limit = limit
        self._items: "OrderedDict[str, Entry]" = OrderedDict()

    def add(self, zh: str, ru: str, source: str = "", lore: bool = False) -> None:
        self._items.pop(zh, None)
        self._items[zh] = Entry(zh, ru, source, lore, time.time())
        while len(self._items) > self.limit:
            self._items.popitem(last=False)

    def entries(self) -> list[Entry]:
        return list(reversed(self._items.values()))

    def clear(self) -> None:
        self._items.clear()


def issue_url(repo: str, zh: str, ru_old: str, ru_new: str, version: str) -> str:
    """Ссылка на готовое предложение исправления в GitHub (человек сам нажмёт «Submit»)."""
    title = f"Перевод: {zh[:60]}"
    body = (
        f"**Оригинал:** {zh}\n\n**Сейчас:** {ru_old}\n\n**Предлагаю:** {ru_new}\n\n"
        f"_Отправлено из DF Translator {version}_"
    )
    return f"https://github.com/{repo}/issues/new?" + urlencode({"title": title, "body": body})
