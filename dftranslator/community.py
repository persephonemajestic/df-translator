"""Общая база переводов сообщества.

Как это работает:
  1. Игрок исправляет перевод в «Истории» (или жмёт «Поделиться всеми правками»).
  2. Программа открывает в браузере готовую заявку на GitHub: внутри блок ```dft``` с парами
     «оригинал → перевод» в JSON (по строке на пару). Игрок нажимает «Submit new issue».
  3. Автор проверяет и пишет в заявке комментарий «/принять» (или ставит метку «принято»).
     GitHub Actions переносит пары в data/community.json и закрывает заявку.
  4. Через синхронизацию данных правка приходит всем без обновления программы.

Модуль без Qt — тестируется отдельно.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlencode

from .text import has_cjk

MAX_URL = 7000          # браузеры и GitHub надёжно принимают ссылки примерно до 8 КБ
BLOCK_RE = re.compile(r"```dft\s*\n(.*?)```", re.S)


def make_issue_urls(repo: str, pairs: list[tuple[str, str, str]], version: str) -> list[str]:
    """pairs: (оригинал, было, стало). Длинный список делится на несколько заявок."""
    urls, chunk = [], []

    def build(items) -> str:
        lines = [json.dumps({"zh": zh, "ru": ru, "old": old}, ensure_ascii=False) for zh, old, ru in items]
        title = (f"Перевод: {items[0][0][:50]}" if len(items) == 1 else f"Переводы для общей базы: {len(items)} шт.")
        body = ("Предложение в общую базу переводов. Проверьте и напишите комментарий `/принять` — "
                "строки сами попадут в базу.\n\n```dft\n" + "\n".join(lines) + "\n```\n\n"
                f"_Отправлено из DF Translator {version}_")
        return f"https://github.com/{repo}/issues/new?" + urlencode({"title": title, "body": body})

    for p in pairs:
        if not (p[0].strip() and p[2].strip()):
            continue
        trial = chunk + [p]
        if chunk and len(build(trial)) > MAX_URL:
            urls.append(build(chunk))
            chunk = [p]
        else:
            chunk = trial
    if chunk:
        urls.append(build(chunk))
    return urls


def parse_issue(body: str) -> list[tuple[str, str]]:
    """Достаёт пары из заявки. Мусор и подозрительные строки отбрасываются."""
    out: list[tuple[str, str]] = []
    for block in BLOCK_RE.findall(body or ""):
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            zh, ru = str(d.get("zh", "")).strip(), str(d.get("ru", "")).strip()
            if valid_pair(zh, ru):
                out.append((zh, ru))
    return out


def valid_pair(zh: str, ru: str) -> bool:
    if not zh or not ru or len(zh) > 300 or len(ru) > 600:
        return False
    if not has_cjk(zh) or has_cjk(ru):
        return False
    if re.search(r"https?://|<[a-z/]|\bjavascript:", ru, re.I):   # ссылки и разметка в базу не пускаем
        return False
    return True


def merge(path: Path, pairs: list[tuple[str, str]]) -> int:
    """Добавляет пары в data/community.json (раздел ui). Возвращает число новых/изменённых строк."""
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.setdefault("_meta", {"about": "Общая база переводов сообщества: правки игроков, одобренные автором. "
                                       "Важнее базового глоссария, но слабее личных правок."})
    ui = data.setdefault("ui", {})
    changed = 0
    for zh, ru in pairs:
        if ui.get(zh) != ru:
            ui[zh] = ru
            changed += 1
    data["ui"] = dict(sorted(ui.items()))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return changed
