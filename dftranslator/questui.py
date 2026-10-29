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
from .settings import ChipLabel, FlowLayout, build_qss, card, flow_widget, label, px

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


def objective_html(n: int, ru: str) -> str:
    """Цель квеста: номер зелёной цифрой, «где» (карта · режим) — отдельной строкой шрифтом DIN,
    «что сделать» — основным текстом с воздухом между строками."""
    import html as _h

    from .fonts import display_family
    from .settings import ACCENT, MUTED

    where, what = "", ru
    head, sep, tail = ru.partition(": ")
    if sep and len(head) <= 70 and ("·" in head or "Любая карта" in head):
        where, what = head, tail[:1].upper() + tail[1:]
    disp = display_family()
    where_html = (f"<div style=\"font-family:'{disp}'; color:{MUTED}; font-size:{px(13)}px; letter-spacing:0.3px;\">"
                  f"{_h.escape(where)}</div>") if where else ""
    return (f"<table cellspacing='0' cellpadding='0'><tr>"
            f"<td style=\"font-family:'{disp}'; color:{ACCENT}; font-size:{px(18)}px; font-weight:600; "
            f"padding-right:{px(10)}px;\">{n}</td>"
            f"<td>{where_html}<p style=\"margin:0; line-height:118%;\">{_h.escape(what)}</p></td></tr></table>")


class QuestCard(QWidget):
    """Окно с карточкой квеста. Открывается из раздела «Квесты» или горячей клавишей «Гид по квесту»."""

    def __init__(self, icon, loader: ImageLoader, reward_ru: Callable[[str], str | None],
                 get_quest: Callable[[str], Quest | None], children: Callable[[Quest], list[Quest]],
                 embedded: bool = False, progress=None, on_open: Callable[[Quest], None] | None = None):
        super().__init__()
        self.embedded = embedded
        self.progress = progress      # объект с is_done(id) / set_done(id, bool)
        self.on_open = on_open        # переход к другому квесту (во встроенном режиме — выделить в списке)
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
        self.show_back = False                       # кнопка «←» к списку (узкое окно справочника)
        self.on_marked: Callable[[str], None] | None = None   # задание только что отмечено выполненным
        self.on_back: Callable[[], None] | None = None
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
        narrow = self.width() < px(520)
        lay.setContentsMargins(px(14) if narrow else px(28), px(16) if narrow else px(24),
                               px(14) if narrow else px(28), px(16) if narrow else px(24))
        lay.setSpacing(px(12) if narrow else px(14))

        head = QHBoxLayout()
        if self.show_back and self.on_back is not None:
            back = QPushButton("←")
            back.setToolTip("К списку заданий")
            back.clicked.connect(self.on_back)
            head.addWidget(back, 0, Qt.AlignmentFlag.AlignTop)
        head.addWidget(plain(quest.name_ru or quest.name, "qtitle"), 1)
        done_btn = None
        if self.progress is not None:
            done = self.progress.is_done(quest.id)
            done_btn = QPushButton("✓ Выполнено" if done else "Отметить выполненным")
            done_btn.setObjectName("" if done else "primary")
            done_btn.setToolTip("Выполненные задания скрываются из списка (их можно показать переключателем)")
            done_btn.clicked.connect(lambda _=False, q=quest: self._toggle_done(q))
            if not narrow:
                head.addWidget(done_btn, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)
        if done_btn is not None and narrow:   # в узком окне кнопка — отдельной строкой под названием
            lay.addWidget(done_btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(plain(quest.name, "muted"))
        chip_texts = [DEPT_RU.get(quest.dept, quest.dept)]
        if quest.dept == "season" and quest.line:
            chip_texts.append("Основная линия" if quest.line == "main" else f"Ветка {quest.line}")
        chip_texts += [TYPE_RU.get(quest.qtype, quest.qtype), quest.map_ru()]
        chips = []
        for text in chip_texts:
            if text:
                ch = ChipLabel(text)
                chips.append(ch)
        lay.addWidget(flow_widget(chips, px(6)))

        if quest.forced:
            warn = plain("⚠ " + quest.forced_text(), "bad")
            lay.addWidget(warn)

        c, cl = card()
        cl.addWidget(label("Цели", "h2"))
        if not quest.objectives:
            cl.addWidget(plain("Подробностей по этому заданию пока нет — они появятся, когда задание добавят на kkrb.net. "
                               "А пока переведите экран задания в игре (Ctrl+Alt+T).", "muted"))
        for n, (zh, ru) in enumerate(quest.objectives, 1):
            row = QVBoxLayout()
            row.setSpacing(px(2))
            t = label(objective_html(n, ru), "", wrap=True)
            t.setTextFormat(Qt.TextFormat.RichText)
            t.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(t)
            z = plain(zh, "muted")
            z.setContentsMargins(px(24), 0, 0, 0)   # под текстом цели, а не под номером
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
            thumbs = []
            for i, url in enumerate(urls):
                th = ClickLabel("…")
                th.setAlignment(Qt.AlignmentFlag.AlignCenter)
                th.setFixedSize(px(210), px(124))
                th.setStyleSheet(f"background:#08131a;border:1px solid #1d3140;border-radius:{px(8)}px;color:#8d9ca6;")
                th.setCursor(Qt.CursorShape.PointingHandCursor)
                th.setToolTip("Открыть крупно")
                th.clicked.connect(lambda i=i, urls=urls: self.viewer.open(urls, i))
                self._thumbs[url] = th
                thumbs.append(th)
                self.loader.request(url)
            c4l.addWidget(flow_widget(thumbs))
            c4l.addWidget(label("Скриншоты: kkrb.net (Key725)", "muted"))
        else:
            c4l.addWidget(label("Скриншотов для этого задания нет — ориентируйтесь по описанию целей.", "muted", wrap=True))
        lay.addWidget(c4)

        nav = []
        parent = self.get_quest(f"{quest.dept}-{quest.parent}") if quest.parent else None
        if parent:
            b = QPushButton(f"← {parent.name_ru or parent.name}")
            b.setToolTip("Предыдущее задание цепочки")
            b.clicked.connect(lambda _=False, p=parent: self._go(p))
            nav.append(b)
        for child in self.children(quest)[:3]:
            b = QPushButton(f"{child.name_ru or child.name} →")
            b.setToolTip("Следующее задание")
            b.clicked.connect(lambda _=False, ch=child: self._go(ch))
            nav.append(b)
        if nav:
            lay.addWidget(flow_widget(nav))
        lay.addStretch(1)

        # Старое содержимое удаляем отложенно: show_quest может вызываться из обработчика кнопки,
        # лежащей в этом самом содержимом (мгновенное удаление роняло программу).
        old = self.scroll.takeWidget()
        if old is not None:
            old.hide()
            old.deleteLater()
        self.scroll.setWidget(inner)
        if not self.embedded:
            self.setWindowTitle(f"{quest.name_ru or quest.name} — квест")
            self.show()
            self.raise_()
            self.activateWindow()

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        narrow = self.width() < px(520)
        if self.quest is not None and narrow != getattr(self, "_was_narrow", narrow):
            self.show_quest(self.quest)
        self._was_narrow = narrow

    def _go(self, quest: Quest) -> None:
        if self.on_open:
            self.on_open(quest)
        else:
            self.show_quest(quest)

    def _toggle_done(self, quest: Quest) -> None:
        from PySide6.QtCore import QTimer

        def apply() -> None:
            done = not self.progress.is_done(quest.id)
            if done and self.on_marked is not None:
                self.on_marked(quest.id)
            self.progress.set_done(quest.id, done)
            if self.quest is quest:
                self.show_quest(quest)

        QTimer.singleShot(0, apply)  # не перестраиваем карточку внутри обработчика её же кнопки

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


# ----------------------------------------------------------------------------- справочник
DEPT_SHORT = [("combat", "Боевой"), ("medical", "Медицинский"), ("tactical", "Тактический"),
              ("logistics", "Снабжения"), ("research", "Исследований")]
MAP_ORDER = ["零号大坝", "长弓溪谷", "航天基地", "巴克什", "潮汐监狱", "任意战区行动", "任意机密/绝密行动", "局外"]
SEASON_STAGES = {1: "沉舟", 2: "星火", 3: "面具", 4: "众生"}   # запасные названия, если нет season_meta.json

# Ширина справочника, при которой меняется раскладка
WIDE_MIN = 900      # рельс + список + карточка
SPLIT_MIN = 640     # выпадающий список разделов + список + карточка; уже — список ИЛИ карточка


def browser_qss() -> str:
    from .fonts import display_family
    from .settings import ACCENT, ACCENT_DIM, CARD, CHECK_SVG, DASH_SVG, DONE, LINE, MUTED, TEXT, icon_file

    disp = display_family()

    return f"""
QFrame#rail {{ background: transparent; }}
QLabel#railcap {{ color: {MUTED}; font-size: {px(13)}px; font-weight: 600; padding: {px(8)}px {px(4)}px {px(2)}px {px(4)}px; }}
QPushButton#railbtn {{ font-size: {px(15)}px; text-align: left; padding: {px(9)}px {px(12)}px; border-radius: {px(4)}px; background: {CARD};
  border: 1px solid {LINE}; color: {TEXT}; }}
QPushButton#railbtn:hover {{ border-color: #2c4a5e; }}
QPushButton#railbtn:checked {{ background: {ACCENT_DIM}; border: 1px solid {ACCENT}; border-left: {px(4)}px solid {ACCENT};
  color: {ACCENT}; font-weight: 700; }}
QPushButton#railbtn:disabled {{ color: #4c5c66; background: #0a141b; }}
QTreeWidget#qtree {{ font-family: "{disp}"; font-size: {px(15)}px; background: {CARD}; border: 1px solid {LINE}; border-radius: {px(4)}px; padding: {px(4)}px; outline: 0; }}
QTreeWidget#qtree::item {{ padding: {px(7)}px {px(4)}px; border-radius: {px(6)}px; }}
QTreeWidget#qtree::item:hover {{ background: #10202a; }}
QTreeWidget#qtree::item:selected {{ background: {ACCENT_DIM}; color: {TEXT}; border-left: {px(3)}px solid {ACCENT}; }}
QTreeWidget#qtree::branch {{ background: transparent; }}
QTreeWidget#qtree::branch:selected {{ background: transparent; border: 0; }}
QTreeWidget#qtree::indicator {{ width: {px(16)}px; height: {px(16)}px; border: 1px solid #2c4a5e; border-radius: {px(4)}px;
  background: #08131a; }}
QTreeWidget#qtree::indicator:hover {{ border-color: {ACCENT}; }}
QTreeWidget#qtree::indicator:checked {{ background: {DONE}; border-color: {DONE}; image: url("{icon_file('check', CHECK_SVG)}"); }}
QTreeWidget#qtree::indicator:indeterminate {{ background: #1d8a64; border-color: #1d8a64; image: url("{icon_file('dash', DASH_SVG)}"); }}
QLabel#unlock {{ color: #ffa24a; font-size: {px(12)}px; }}
"""


TEXT_COLOR = "#e7e9ea"


class QuestBrowser(QWidget):
    """Справочник как в игре: слева отделы и этапы сезона, в середине ветки и задания, справа карточка.

    Раскладка зависит от ширины: широкое окно — три колонки; среднее — разделы в выпадающем списке,
    список и карточка рядом; узкое — список, а по клику карточка с кнопкой «←» назад."""

    def __init__(self, icon, loader: ImageLoader, reward_ru, progress):
        super().__init__()
        from PySide6.QtWidgets import QButtonGroup, QComboBox, QLineEdit, QTreeWidget

        from .settings import Switch

        self.db = None
        self.progress = progress
        self.section = "combat"
        self._building = False
        self._mode = ""
        self._card_open = False   # узкий режим: показана карточка вместо списка
        # Отмеченные сейчас задания не исчезают сразу — остаются серыми, пока не смените раздел.
        self._keep: set[str] = set()
        self._refresh_pending = False
        self._rows: list = []
        self._rows_key = None
        self.setStyleSheet(browser_qss())

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(px(12))

        # --- рельс: отделы и этапы сезона (прокручивается, если окно низкое)
        rail = QFrame()
        rail.setObjectName("rail")
        rl = QVBoxLayout(rail)
        rl.setContentsMargins(0, 0, px(4), 0)
        rl.setSpacing(px(6))
        self.rail_group = QButtonGroup(self)
        self.rail_btns: dict[str, QPushButton] = {}
        rl.addWidget(label("Отделы", "railcap"))
        for key, title in DEPT_SHORT:
            self._rail_btn(rl, key, title)
        rl.addSpacing(px(8))
        rl.addWidget(label("Сезон «Созвездие»", "railcap"))
        self.rail_season_lay = rl
        for stage in SEASON_STAGES:
            self._rail_btn(rl, f"season:{stage}", f"{stage:02d}")
        rl.addStretch(1)
        self.rail_scroll = QScrollArea()
        self.rail_scroll.setWidgetResizable(True)
        self.rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rail_scroll.setWidget(rail)
        self.rail_scroll.setFixedWidth(px(196))
        root.addWidget(self.rail_scroll)

        # --- список
        mid = QVBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(px(8))
        self.combo = QComboBox()
        self.combo.setToolTip("Раздел: отдел или этап сезона")
        self.combo.activated.connect(lambda i: self.set_section(self.combo.itemData(i)))
        mid.addWidget(self.combo)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск: название, предмет, место, «1-3», «2-1-4»")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: (self._keep.clear(), self.rebuild()))
        mid.addWidget(self.search)
        hide_row = QHBoxLayout()
        hide_row.addWidget(label("Скрывать выполненные", "muted"), 1)
        self.hide_done = Switch(True)
        self.hide_done.setToolTip("Выполненные задания прячутся, закрытые ветки сворачиваются в серую строку")
        self.hide_done.toggled.connect(lambda _v: self._refresh_now())
        hide_row.addWidget(self.hide_done)
        mid.addLayout(hide_row)
        self.unlock = label("", "unlock", wrap=True)
        self.unlock.setVisible(False)
        mid.addWidget(self.unlock)
        self._mid = mid
        self.tree = self._make_tree()
        mid.addWidget(self.tree, 1)
        self.stats = label("", "muted")
        mid.addWidget(self.stats)
        self.midw = QWidget()
        self.midw.setLayout(mid)
        root.addWidget(self.midw)

        # --- карточка
        self.card = QuestCard(icon, loader, reward_ru, self._get, self._children,
                              embedded=True, progress=progress, on_open=lambda q: self.select(q.id))
        self.card.on_back = self._back_to_list
        self.card.on_marked = self._keep.add
        self.card.setMinimumWidth(px(260))
        root.addWidget(self.card, 1)
        progress.listeners.append(self._on_progress_changed)
        self._apply_mode()

    def _make_tree(self):
        from PySide6.QtWidgets import QTreeWidget

        t = QTreeWidget()
        t.setObjectName("qtree")
        from PySide6.QtGui import QColor, QPalette

        from .settings import ACCENT_DIM
        pal = t.palette()   # системная синяя подсветка выбранной строки — в цвет темы
        for grp in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            pal.setColor(grp, QPalette.ColorRole.Highlight, QColor(ACCENT_DIM))
        t.setPalette(pal)
        t.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # без системной рамки фокуса поверх строки
        t.setHeaderHidden(True)
        t.setIndentation(px(14))
        t.setMinimumWidth(px(220))
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        t.setTextElideMode(Qt.TextElideMode.ElideRight)
        t.itemChanged.connect(self._on_item_changed)
        t.currentItemChanged.connect(self._on_current)
        t.itemClicked.connect(self._on_clicked)
        return t

    # ------------------------------------------------------------ раскладка
    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._apply_mode()

    def _apply_mode(self) -> None:
        w = self.width()
        mode = "wide" if w >= px(WIDE_MIN) else "split" if w >= px(SPLIT_MIN) else "narrow"
        changed = mode != self._mode
        self._mode = mode
        self.rail_scroll.setVisible(mode == "wide")
        self.unlock.setVisible(bool(self.unlock.text()) and self.height() >= px(480))
        self.combo.setVisible(mode != "wide")
        if mode == "narrow":
            self.midw.setMinimumWidth(0)
            self.midw.setMaximumWidth(16777215)
            self.midw.setVisible(not self._card_open)
            self.card.setVisible(self._card_open)
            self.card.setMinimumWidth(0)
        else:
            free = w - (px(208) if mode == "wide" else 0)
            list_w = max(px(250), min(px(330), int(free * 0.42)))
            self.midw.setFixedWidth(list_w)
            self.midw.setVisible(True)
            self.card.setVisible(True)
            self.card.setMinimumWidth(px(260))
        want_back = mode == "narrow"
        if changed or self.card.show_back != want_back:
            self.card.show_back = want_back
            if self.card.quest is not None:
                self.card.show_quest(self.card.quest)

    def _open_card(self) -> None:
        if self._mode == "narrow" and not self._card_open:
            self._card_open = True
            self._apply_mode()

    def _back_to_list(self) -> None:
        self._card_open = False
        self._apply_mode()
        self.tree.setFocus()

    # ---------------------------------------------------------------- data
    def _rail_btn(self, lay, key: str, title: str) -> None:
        b = QPushButton(title)
        b.setObjectName("railbtn")
        b.setCheckable(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda _=False, k=key: self.set_section(k))
        self.rail_group.addButton(b)
        self.rail_btns[key] = b
        lay.addWidget(b)

    def set_db(self, db) -> None:
        self.db = db
        self._update_rail()
        self.set_section(self.section)

    def _get(self, quest_id: str):
        return self.db.get(quest_id) if self.db else None

    def _children(self, q: Quest) -> list[Quest]:
        if not self.db:
            return []
        return [x for x in self.db.quests if x.dept == q.dept and x.parent == q.key]

    def _section_quests(self, section: str) -> list[Quest]:
        if section.startswith("season:"):
            stage = int(section.split(":")[1])
            return [q for q in self.db.quests if q.dept == "season" and q.stage == stage]
        return [q for q in self.db.quests if q.dept == section]

    def _stage_name(self, stage: int) -> str:
        zh = ""
        if self.db is not None and hasattr(self.db, "stage_name"):
            zh = self.db.stage_name(stage)
            zh = zh.split("：")[-1] if zh else ""
        return self._line_ru(zh or SEASON_STAGES.get(stage, ""))

    def _section_title(self, key: str) -> tuple[str, int, int, bool]:
        """Название раздела, сколько выполнено, всего, доступен ли."""
        qs = self._section_quests(key)
        done = sum(self.progress.is_done(q.id) for q in qs)
        if key.startswith("season:"):
            stage = int(key.split(":")[1])
            return f"{stage:02d} · {self._stage_name(stage)}", done, len(qs), bool(qs)
        return dict(DEPT_SHORT)[key], done, len(qs), True

    def _update_rail(self) -> None:
        if self.db is None:
            return
        self.combo.blockSignals(True)
        self.combo.clear()
        for key, title in DEPT_SHORT:
            name, done, total, _ok = self._section_title(key)
            self.rail_btns[key].setText(f"{name}\n{done}/{total}")
            self.combo.addItem(f"{name} — {done}/{total}", key)
        for stage in SEASON_STAGES:
            key = f"season:{stage}"
            name, done, total, ok = self._section_title(key)
            b = self.rail_btns[key]
            fm = b.fontMetrics()
            short = fm.elidedText(name, Qt.TextElideMode.ElideRight, px(196) - px(34))
            b.setToolTip(name + ("\n" + self.db.stage_unlock(stage) if hasattr(self.db, "stage_unlock")
                                 and self.db.stage_unlock(stage) else ""))
            if ok:
                b.setText(f"{short}\n{done}/{total}")
                b.setEnabled(True)
                self.combo.addItem(f"Сезон {name} — {done}/{total}", key)
            else:
                b.setText(f"{stage:02d}  🔒\nпоявится позже")
                b.setEnabled(False)
        i = self.combo.findData(self.section)
        if i >= 0:
            self.combo.setCurrentIndex(i)
        self.combo.blockSignals(False)

    def _line_ru(self, zh: str) -> str:
        return (self._lookup_name(zh) or zh) if zh else ""

    def _lookup_name(self, zh: str) -> str:
        fn = getattr(self, "name_lookup", None)
        return (fn(zh) if fn else "") or ""

    def set_section(self, section: str) -> None:
        if not section:
            return
        self.section = section
        if section in self.rail_btns:
            self.rail_btns[section].setChecked(True)
        self._card_open = False
        self._keep.clear()
        self.rebuild()
        self._apply_mode()

    # --------------------------------------------------------------- tree
    def _groups(self) -> list[tuple[str, list[Quest]]]:
        query = self.search.text().strip()
        if query:
            found = self.db.search(query)
            return [(f"Найдено: {len(found)}", found)]
        qs = self._section_quests(self.section)
        groups: dict[str, list[Quest]] = {}
        for q in qs:
            groups.setdefault(q.group(), []).append(q)
        if self.section.startswith("season:"):
            def key(g: str) -> tuple:
                line = g.split("|")[1]
                return (0, 0) if line == "main" else (1, int(line.split("-")[1]))
            ordered = sorted(groups.items(), key=lambda kv: key(kv[0]))
            out = []
            for g, items in ordered:
                line = g.split("|")[1]
                name = self._line_ru(items[0].line_name)
                if line == "main":
                    title = f"Основная линия · «{name}»"
                else:
                    reserve = any(q.qtype == "赛季备用支线" for q in items)
                    title = f"{line} · «{name}»" + (" · резерв" if reserve else "")
                out.append((title, items))
            return out
        order = {m: i for i, m in enumerate(MAP_ORDER)}
        from .questdb import MAP_RU
        return [(MAP_RU.get(g, g), items) for g, items in sorted(groups.items(), key=lambda kv: order.get(kv[0], 99))]

    def rebuild(self, keep: str | None = None) -> None:
        if self.db is None:
            return
        if getattr(self, "_sync_pending", False):   # сначала сохраняем только что поставленные галочки
            self._sync_from_tree()
        from PySide6.QtGui import QBrush, QColor, QFont
        from PySide6.QtWidgets import QTreeWidgetItem

        cur = self.tree.currentItem()
        keep = keep or (cur.data(0, Qt.ItemDataRole.UserRole) if cur else None)
        hide = self.hide_done.isChecked()
        self._building = True
        # Новый список вместо очистки старого. Синхронная очистка дерева (clear) иногда роняла
        # программу, если в этот момент Qt ещё обрабатывал клик или галочку в нём. Старый список
        # удаляется отложенно — когда Qt закончит с ним все дела.
        old = self.tree
        old.blockSignals(True)
        self._rows = []
        self.tree = self._make_tree()
        self.tree.blockSignals(True)
        self.tree.setUpdatesEnabled(False)
        self._mid.replaceWidget(old, self.tree)
        old.hide()
        old.deleteLater()
        searching = bool(self.search.text().strip())
        unlock = ""
        if self.section.startswith("season:") and not searching and hasattr(self.db, "stage_unlock"):
            unlock = self.db.stage_unlock(int(self.section.split(":")[1]))
        self.unlock.setText("🔓 " + unlock if unlock else "")
        self.unlock.setVisible(bool(unlock) and self.height() >= px(480))
        self.combo.setToolTip(unlock or "Раздел: отдел или этап сезона")
        # Храним только заголовки и квесты, а не сами строки: ссылки Python на строки дерева после
        # очистки списка указывали в освобождённую память (отсюда вылеты). Строки берём у дерева.
        self._rows = []   # (заголовок ветки, [квесты])
        self._rows_key = (self.section, self.search.text().strip())
        for title, items in self._groups():
            g = QTreeWidgetItem(self.tree, [title])   # родитель сразу в конструкторе: строкой владеет Qt
            f = QFont(g.font(0))
            f.setBold(True)
            g.setFont(0, f)
            # Без ItemIsAutoTristate: автоматическое «полувыбранное» состояние Qt портило дерево и роняло
            # программу при очистке списка. Состояние ветки считаем сами в _apply_states.
            g.setFlags(g.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            g.setData(0, Qt.ItemDataRole.UserRole + 1, len(self._rows))   # номер ветки
            tip = "Галочка на ветке — закрыть / открыть все её задания"
            if items and items[0].dept == "season" and not searching and hasattr(self.db, "line_info"):
                info = self.db.line_info(items[0].stage, items[0].line)
                if info.get("goal"):
                    tip = f"{info['goal']}\n{tip}"
            g.setToolTip(0, f"{title}\n{tip}")
            quests = []
            for q in items:
                sub = q.name
                if searching:
                    sub += " · " + (f"Сезон {q.line}" if q.dept == "season" and q.line != "main"
                                    else dict(DEPT_SHORT).get(q.dept, "Сезон"))
                elif q.dept != "season":
                    sub += " · " + ("Побочный" if q.qtype == "支线任务" else "Основной")
                if not q.objectives:
                    sub += " · нет данных"
                elif q.images:
                    sub += f" · 📷 {len(q.images)}"
                if q.forced:
                    sub += " · ⚠"
                it = QTreeWidgetItem(g, [f"{q.name_ru or q.name}\n{sub}"])
                it.setData(0, Qt.ItemDataRole.UserRole, q.id)
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setToolTip(0, f"{q.name_ru or q.name}\n{q.name}\nГалочка — задание выполнено")
                quests.append(q)
            self._rows.append((title, quests))
        self._apply_states(first=True)
        self.tree.setUpdatesEnabled(True)
        self.tree.blockSignals(False)
        self._building = False
        if keep:
            self._select_item(keep)

    def _iter_rows(self):
        """(строка ветки, заголовок, [(строка задания, квест)]) — строки берутся у дерева при каждом вызове."""
        n = min(self.tree.topLevelItemCount(), len(self._rows))
        for i in range(n):
            g = self.tree.topLevelItem(i)
            title, quests = self._rows[i]
            m = min(g.childCount(), len(quests))
            yield g, title, [(g.child(j), quests[j]) for j in range(m)]

    def _apply_states(self, first: bool = False) -> None:
        """Галочки, серый цвет, скрытие и счётчики — без пересоздания строк.

        Отметка задания больше не пересобирает список: строки остаются теми же объектами,
        меняется только их вид (быстро, без прыжков прокрутки и без вылетов)."""
        from PySide6.QtGui import QBrush, QColor, QFont

        hide = self.hide_done.isChecked()
        searching = bool(self.search.text().strip())
        grey, normal = QBrush(QColor("#5f6f79")), QBrush(QColor(TEXT_COLOR))
        was = self.tree.signalsBlocked()
        self.tree.blockSignals(True)
        self._building = True
        total = done_total = 0
        try:
            for g, title, rows in self._iter_rows():
                done_n = 0
                for it, q in rows:
                    done = self.progress.is_done(q.id)
                    done_n += done
                    it.setCheckState(0, Qt.CheckState.Checked if done else Qt.CheckState.Unchecked)
                    it.setForeground(0, grey if done else normal)
                    fnt = QFont(it.font(0))
                    fnt.setStrikeOut(done)
                    it.setFont(0, fnt)
                    it.setHidden(done and hide and not searching and q.id not in self._keep)
                total += len(rows)
                done_total += done_n
                closed = bool(rows) and done_n == len(rows)
                just_closed = closed and any(q.id in self._keep for _it, q in rows)
                g.setText(0, f"{'✓ ' if closed else ''}{title}   {done_n}/{len(rows)}")
                g.setCheckState(0, Qt.CheckState.Checked if closed else
                                Qt.CheckState.PartiallyChecked if done_n else Qt.CheckState.Unchecked)
                g.setForeground(0, grey if closed else normal)
                if first or closed:
                    g.setExpanded(not (closed and hide and not just_closed) or searching)
        finally:
            self._building = False
            self.tree.blockSignals(was)
        self.stats.setText(f"Выполнено: {done_total} из {total}")
        self._update_rail()

    def _select_item(self, quest_id: str) -> bool:
        from PySide6.QtWidgets import QTreeWidgetItemIterator

        itr = QTreeWidgetItemIterator(self.tree)
        while itr.value():
            it = itr.value()
            if it.data(0, Qt.ItemDataRole.UserRole) == quest_id:
                it.setHidden(False)
                if it.parent():
                    it.parent().setExpanded(True)
                self.tree.setCurrentItem(it)
                self.tree.scrollToItem(it)
                return True
            itr += 1
        return False

    def select(self, quest_id: str) -> None:
        q = self._get(quest_id)
        if q is None:
            return
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        section = f"season:{q.stage}" if q.dept == "season" else q.dept
        if section != self.section:
            self.section = section
            if section in self.rail_btns:
                self.rail_btns[section].setChecked(True)
        self.rebuild(keep=quest_id)
        self.card.show_quest(q)
        self._open_card()

    def _on_current(self, it, _prev=None) -> None:
        if it is None or self._building:
            return
        qid = it.data(0, Qt.ItemDataRole.UserRole)
        if qid:
            q = self._get(qid)
            if q:
                self.card.show_quest(q)

    def _on_clicked(self, it, _col=0) -> None:
        if getattr(self, "_just_checked", False):   # клик был по галочке — карточку не открываем
            self._just_checked = False
            return
        if it is not None and it.data(0, Qt.ItemDataRole.UserRole) and not self._building:
            self._on_current(it)
            self._open_card()

    def _on_item_changed(self, it, _col) -> None:
        """Галочку поставили или сняли: запоминаем, что изменить, и сохраняем после клика."""
        if self._building or it is None:
            return
        self._just_checked = True
        on = it.checkState(0) == Qt.CheckState.Checked
        pending = getattr(self, "_pending", {})
        qid = it.data(0, Qt.ItemDataRole.UserRole)
        if qid:
            pending[qid] = on
        else:  # галочка на ветке — все её задания
            idx = it.data(0, Qt.ItemDataRole.UserRole + 1)
            if isinstance(idx, int) and 0 <= idx < len(self._rows):
                for q in self._rows[idx][1]:
                    pending[q.id] = on
        self._pending = pending
        if getattr(self, "_sync_pending", False):
            return
        self._sync_pending = True
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._sync_from_tree)

    def _sync_from_tree(self) -> None:
        self._sync_pending = False
        pending, self._pending = getattr(self, "_pending", {}), {}
        on = [q for q, v in pending.items() if v and not self.progress.is_done(q)]
        off = [q for q, v in pending.items() if not v and self.progress.is_done(q)]
        if on:
            self._keep.update(on)
            self.progress.set_many(on, True)
        if off:
            self.progress.set_many(off, False)
        if pending and not on and not off:   # ничего не поменялось — вернуть вид строк
            self._apply_states()

    def _on_progress_changed(self) -> None:
        # Перестраиваем после того, как Qt закончит обрабатывать текущий клик/галочку:
        # очистка дерева прямо внутри его же сигнала роняла программу.
        if self._refresh_pending:
            return
        self._refresh_pending = True
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._refresh_now)

    def _refresh_now(self) -> None:
        self._refresh_pending = False
        if getattr(self, "_sync_pending", False):   # галочки, поставленные только что, — сначала сохранить
            self._sync_from_tree()
            self._refresh_pending = False
        if self._rows_key == (self.section, self.search.text().strip()) and self._rows:
            self._apply_states()
        else:
            self.rebuild()
        if self.card.quest is not None:
            self.card.show_quest(self.card.quest)
