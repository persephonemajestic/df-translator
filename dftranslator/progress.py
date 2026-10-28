"""Отметки «задание выполнено» (хранятся у пользователя в progress.json)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


class Progress:
    def __init__(self, path: Path | None):
        self.path = path
        self.done: set[str] = set()
        self.listeners: list[Callable[[], None]] = []
        if path and path.exists():
            try:
                self.done = set(json.loads(path.read_text(encoding="utf-8")).get("done", []))
            except (OSError, ValueError):
                self.done = set()

    def is_done(self, quest_id: str) -> bool:
        return quest_id in self.done

    def set_done(self, quest_id: str, value: bool, notify: bool = True) -> None:
        (self.done.add if value else self.done.discard)(quest_id)
        self.save()
        if notify:
            for fn in list(self.listeners):
                fn()

    def set_many(self, ids: list[str], value: bool) -> None:
        for i in ids:
            (self.done.add if value else self.done.discard)(i)
        self.save()
        for fn in list(self.listeners):
            fn()

    def save(self) -> None:
        if self.path:
            self.path.write_text(json.dumps({"done": sorted(self.done)}, ensure_ascii=False), encoding="utf-8")
