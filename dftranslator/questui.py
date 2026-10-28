"""Карточка квеста: цели и награды на русском, что взять с собой, скриншоты «Где выполнять»."""
from __future__ import annotations

import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import requests
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .questdb import DEPT_RU, FORCED_RU, TYPE_RU, Quest
from .settings import build_qss, card, label, px

KKRB_HEADERS = {"Referer": "https://www.kkrb.net/", "User-Agent": "Mozilla/5.0 (DFTranslator)"}


def plain(text: str, name: str = "", wrap: bool = True) -> QLabel:
    lb = label(text, name, wrap=wrap)
    lb.setTextFormat(Qt.TextFormat.PlainText)
    return lb


class ImageLoader(QObject):
    """Скачивает скриншоты в фоне и кеширует на диске (повторно открываются мгновенно)."""

    loaded = Signal(str, QImage)
    failed = Signal(str)

    def __init__(self, cache_dir: Path):
        super().__init__()
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="dft-img")
        self._mem: dict[str, QImage] = {}

    def request(self, url: str) -> None:
        if url in self._mem:
            self.loaded.emit(url, self._mem[url])
            return
        self.pool.submit(self._job, url)

    def _job(self, url: str) -> None:
        path = self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".img")
        try:
            if path.exists():
                data = path.read_bytes()
            else:
                r = requests.get(url, headers=KKRB_HEADERS, timeout=20)
                r.raise_for_status()
                data = r.content
                path.write_bytes(data)
            img = QImage()
            if not img.loadFromData(data):  # webp без плагина Qt — конвертируем через Pillow
                from PIL import Image

                buf = io.BytesIO()
                Image.open(io.BytesIO(data)).convert("RGB").save(buf, "PNG")
                img.loadFromData(buf.getvalue(), "PNG")
            if img.isNull():
                raise ValueError("не удалось прочитать картинку")
            self._mem[url] = img
            self.loaded.emit(url, img)
        except Exception:  # noqa: BLE001
            self.failed.emit(url)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)


class ClickLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class ImageViewer(QWidget):
    """Большой просмотр скриншота: ← → листать, Esc — закрыть."""

    def __init__(self, loader: ImageLoader, icon):
        super().__init__()
        self.setWindowTitle("Где выполнять")
        self.setWindowIcon(icon)
        self.setStyleSheet(build_qss())
        self.setObjectName("root")
        self.loader = loader
        self.urls: list[str] = []
        self.index = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(px(12), px(12), px(12), px(12))
        self.img = QLabel("Загрузка…")
        self.img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img.setMinimumSize(px(640), px(360))
        self.img.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(self.img, 1)
        bar = QHBoxLayout()
        self.prev_btn = QPushButton("← Назад")
        self.next_btn = QPushButton("Вперёд →")
        self.counter = label("", "muted")
        self.prev_btn.clicked.connect(lambda: self.show_index(self.index - 1))
        self.next_btn.clicked.connect(lambda: self.show_index(self.index + 1))
        bar.addWidget(self.prev_btn)
        bar.addStretch(1)
        bar.addWidget(self.counter)
        bar.addStretch(1)
        bar.addWidget(self.next_btn)
        lay.addLayout(bar)
        self._pix: QPixmap | None = None
        loader.loaded.connect(self._on_loaded)
        self.resize(px(1100), px(720))

    def open(self, urls: list[str], index: int) -> None:
        self.urls = urls
        self.show_index(index)
        self.show()
        self.raise_()
        self.activateWindow()

    def show_index(self, i: int) -> None:
        if not self.urls:
            return
        self.index = i % len(self.urls)
        self.counter.setText(f"{self.index + 1} / {len(self.urls)}")
        self._pix = None
        self.img.setText("Загрузка…")
        self.loader.request(self.urls[self.index])

    def _on_loaded(self, url: str, image: QImage) -> None:
        if self.urls and url == self.urls[self.index]:
            self._pix = QPixmap.fromImage(image)
            self._rescale()

    def _rescale(self) -> None:
        if self._pix:
            self.img.setPixmap(self._pix.scaled(self.img.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._rescale()

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() in (Qt.Key.Key_Right, Qt.Key.Key_Space):
            self.show_index(self.index + 1)
        elif e.key() == Qt.Key.Key_Left:
            self.show_index(self.index - 1)
        elif e.key() == Qt.Key.Key_Escape:
            self.close()


class QuestCard(QWidget):
    """Окно с карточкой квеста. Открывается из раздела «Квесты» или горячей клавишей «Гид по квесту»."""

    def __init__(self, icon, loader: ImageLoader, reward_ru: Callable[[str], str | None],
                 get_quest: Callable[[str], Quest | None], children: Callable[[Quest], list[Quest]]):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("Квест — DF Translator")
        self.setWindowIcon(icon)
        self.setStyleSheet(build_qss())
        self.resize(px(760), px(820))
        self.loader = loader
        self.reward_ru = reward_ru
        self.get_quest = get_quest
        self.children = children
        self.viewer = ImageViewer(loader, icon)
        self.quest: Quest | None = None
        self._thumbs: dict[str, ClickLabel] = {}
        loader.loaded.connect(self._on_loaded)
        loader.failed.connect(self._on_failed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)

    # --------------------------------------------------------------- build
    def show_quest(self, quest: Quest) -> None:
        self.quest = quest
        self._thumbs.clear()
        inner = QWidget()
        inner.setObjectName("content")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(px(28), px(24), px(28), px(24))
        lay.setSpacing(px(14))

        lay.addWidget(plain(quest.name_ru or quest.name, "h1"))
        lay.addWidget(plain(quest.name, "muted"))
        chips = QHBoxLayout()
        chips.setSpacing(px(6))
        for text in (DEPT_RU.get(quest.dept, quest.dept), TYPE_RU.get(quest.qtype, quest.qtype), quest.map_ru()):
            if text:
                chips.addWidget(label(text, "chip"))
        chips.addStretch(1)
        lay.addLayout(chips)

        if quest.forced:
            warn = plain("⚠ " + FORCED_RU.get(quest.forced, quest.forced), "bad")
            lay.addWidget(warn)

        c, cl = card()
        cl.addWidget(label("Цели", "h2"))
        for n, (zh, ru) in enumerate(quest.objectives, 1):
            row = QVBoxLayout()
            row.setSpacing(px(2))
            t = plain(f"{n}. {ru}")
            t.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(t)
            z = plain(zh, "muted")
            z.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(z)
            cl.addLayout(row)
        lay.addWidget(c)

        items = quest.items()
        if items:
            c2, c2l = card()
            c2l.addWidget(label("Что понадобится", "h2"))
            for it in items:
                c2l.addWidget(plain("• " + it))
            lay.addWidget(c2)

        if quest.rewards:
            c3, c3l = card()
            c3l.addWidget(label("Награды", "h2"))
            for r in quest.rewards:
                c3l.addWidget(plain("• " + (self.reward_ru(r) or r)))
            lay.addWidget(c3)

        c4, c4l = card()
        c4l.addWidget(label("Где выполнять", "h2"))
        urls = quest.image_urls()
        if urls:
            grid = QGridLayout()
            grid.setSpacing(px(8))
            for i, url in enumerate(urls):
                th = ClickLabel("…")
                th.setAlignment(Qt.AlignmentFlag.AlignCenter)
                th.setFixedSize(px(210), px(124))
                th.setStyleSheet(f"background:#0f141b;border:1px solid #232b36;border-radius:{px(8)}px;color:#7d8796;")
                th.setCursor(Qt.CursorShape.PointingHandCursor)
                th.setToolTip("Открыть крупно")
                th.clicked.connect(lambda i=i, urls=urls: self.viewer.open(urls, i))
                self._thumbs[url] = th
                grid.addWidget(th, i // 3, i % 3)
                self.loader.request(url)
            c4l.addLayout(grid)
            c4l.addWidget(label("Скриншоты: kkrb.net (Key725)", "muted"))
        else:
            c4l.addWidget(label("Скриншотов для этого задания нет — ориентируйтесь по описанию целей.", "muted", wrap=True))
        lay.addWidget(c4)

        nav = QHBoxLayout()
        parent = self.get_quest(f"{quest.dept}-{quest.parent}") if quest.parent else None
        if parent:
            b = QPushButton(f"← {parent.name_ru or parent.name}")
            b.setToolTip("Предыдущее задание цепочки")
            b.clicked.connect(lambda _=False, p=parent: self.show_quest(p))
            nav.addWidget(b)
        nav.addStretch(1)
        for child in self.children(quest)[:3]:
            b = QPushButton(f"{child.name_ru or child.name} →")
            b.setToolTip("Следующее задание")
            b.clicked.connect(lambda _=False, ch=child: self.show_quest(ch))
            nav.addWidget(b)
        lay.addLayout(nav)
        lay.addStretch(1)

        self.scroll.setWidget(inner)
        self.setWindowTitle(f"{quest.name_ru or quest.name} — квест")
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_loaded(self, url: str, image: QImage) -> None:
        th = self._thumbs.get(url)
        if th is not None:
            th.setPixmap(QPixmap.fromImage(image).scaled(th.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                                         Qt.TransformationMode.SmoothTransformation))

    def _on_failed(self, url: str) -> None:
        th = self._thumbs.get(url)
        if th is not None:
            th.setText("не загрузилось")


def quest_list_text(q: Quest) -> str:
    return f"{q.name_ru or q.name}\n{q.name} · {q.map_ru() or '—'}"


__all__ = ["ImageLoader", "ImageViewer", "QuestCard", "quest_list_text", "QFrame"]
