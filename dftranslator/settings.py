"""Окно настроек и панель управления (PySide6)."""
from __future__ import annotations

import copy

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QButtonGroup, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QSlider,
    QStackedWidget, QVBoxLayout, QWidget,
)

from . import CREDIT, TELEGRAM, __version__, autostart
from .config import DEFAULTS
from .hotkeys import format_hotkey, qt_key_to_name, validate_bindings

ACCENT = "#22c58b"
ACCENT_DIM = "#17382f"
BG, SIDE, CARD, LINE = "#0e1116", "#12161c", "#161b23", "#232b36"
TEXT, MUTED, DANGER = "#e8ebf0", "#7d8796", "#e5676b"

_scale = 1.0


def px(v: float) -> int:
    return max(1, round(v * _scale))


def detect_scale() -> float:
    """Qt-масштабирование отключено (иначе координаты не совпадут со снимком), поэтому
    размеры интерфейса подгоняем под DPI сами."""
    global _scale
    scr = QApplication.primaryScreen()
    _scale = max(1.0, min(3.0, scr.logicalDotsPerInch() / 96.0)) if scr else 1.0
    return _scale


def build_qss() -> str:
    return f"""
* {{ font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: {px(14)}px; color: {TEXT}; }}
QWidget#root {{ background: {BG}; }}
QWidget#content {{ background: {BG}; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: {px(10)}px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: {px(5)}px; min-height: {px(30)}px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QFrame#side {{ background: {SIDE}; border-right: 1px solid {LINE}; }}
QLabel#brand {{ font-size: {px(18)}px; font-weight: 700; }}
QLabel#version {{ color: {MUTED}; font-size: {px(12)}px; }}
QListWidget#nav {{ background: transparent; border: 0; outline: 0; }}
QListWidget#nav::item {{ padding: {px(11)}px {px(14)}px; margin: {px(2)}px {px(10)}px; border-radius: {px(8)}px; color: {MUTED}; }}
QListWidget#nav::item:hover {{ background: #1a212b; color: {TEXT}; }}
QListWidget#nav::item:selected {{ background: {ACCENT_DIM}; color: {ACCENT}; }}

QLabel#h1 {{ font-size: {px(24)}px; font-weight: 700; }}
QLabel#h2 {{ font-size: {px(15)}px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; font-size: {px(13)}px; }}
QLabel#value {{ color: {ACCENT}; font-weight: 600; min-width: {px(64)}px; }}
QLabel#ok {{ color: {ACCENT}; }}
QLabel#bad {{ color: {DANGER}; }}

QFrame#card {{ background: {CARD}; border: 1px solid {LINE}; border-radius: {px(12)}px; }}
QFrame#card QLabel {{ background: transparent; }}
QFrame#sep {{ background: {LINE}; max-height: 1px; min-height: 1px; border: 0; }}

QPushButton {{ background: #1c2330; border: 1px solid {LINE}; border-radius: {px(8)}px; padding: {px(8)}px {px(16)}px; }}
QPushButton:hover {{ background: #232c3b; }}
QPushButton:pressed {{ background: #1a212c; }}
QPushButton:disabled {{ color: #4b5563; background: #151a22; }}
QPushButton#primary {{ background: {ACCENT}; border: 0; color: #06231a; font-weight: 700; }}
QPushButton#primary:hover {{ background: #2fd69b; }}
QPushButton#primary:disabled {{ background: #1f3a31; color: #4f7566; }}
QPushButton#danger {{ color: {DANGER}; }}
QPushButton#action {{ text-align: left; font-weight: 600; padding: {px(16)}px {px(18)}px; border-radius: {px(12)}px; background: {CARD}; }}
QPushButton#action:hover {{ border-color: {ACCENT}; background: #19212b; }}
QPushButton#engine {{ text-align: left; padding: {px(14)}px {px(16)}px; border-radius: {px(12)}px; background: {CARD}; }}
QPushButton#engine:hover {{ border-color: #3a4656; }}
QPushButton#engine:checked {{ border: 1px solid {ACCENT}; background: {ACCENT_DIM}; }}
QPushButton#seg {{ border-radius: 0; padding: {px(9)}px {px(20)}px; min-width: {px(130)}px; background: {CARD}; }}
QPushButton#seg:checked {{ background: {ACCENT}; color: #06231a; font-weight: 700; border-color: {ACCENT}; }}
QPushButton#hotkey {{ font-family: Consolas, "Cascadia Mono", monospace; font-weight: 600; min-width: {px(170)}px; padding: {px(8)}px {px(14)}px; background: #0f141b; }}
QPushButton#hotkey:hover {{ border-color: #3a4656; }}
QPushButton#hotkey[capturing="true"] {{ border: 1px solid {ACCENT}; color: {ACCENT}; background: {ACCENT_DIM}; }}
QPushButton#hotkey[bad="true"] {{ border: 1px solid {DANGER}; color: {DANGER}; }}

QLineEdit {{ background: #0f141b; border: 1px solid {LINE}; border-radius: {px(8)}px; padding: {px(9)}px {px(12)}px; selection-background-color: {ACCENT}; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QComboBox {{ background: #0f141b; border: 1px solid {LINE}; border-radius: {px(8)}px; padding: {px(8)}px {px(12)}px; min-width: {px(200)}px; }}
QComboBox:hover {{ border-color: #3a4656; }}
QComboBox::drop-down {{ border: 0; width: {px(26)}px; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {LINE}; selection-background-color: {ACCENT_DIM}; selection-color: {ACCENT}; outline: 0; }}

QToolTip {{ background: #1c2330; color: {TEXT}; border: 1px solid #3a4656; padding: {px(6)}px {px(8)}px; border-radius: {px(6)}px; }}
QLabel#key {{ font-family: Consolas, "Cascadia Mono", monospace; font-size: {px(12)}px; font-weight: 700; color: {TEXT};
  background: #0f141b; border: 1px solid #2b3442; border-bottom: {px(2)}px solid #2b3442; border-radius: {px(6)}px; padding: {px(2)}px {px(8)}px; }}
QLabel#plus {{ color: {MUTED}; font-size: {px(12)}px; }}
QLabel#glyph {{ background: {ACCENT_DIM}; color: {ACCENT}; border-radius: {px(10)}px; font-size: {px(20)}px; font-weight: 700; min-width: {px(40)}px; max-width: {px(40)}px; min-height: {px(40)}px; max-height: {px(40)}px; }}
QLabel#glyphDanger {{ background: #3a1d20; color: {DANGER}; border-radius: {px(10)}px; font-size: {px(20)}px; font-weight: 700; min-width: {px(40)}px; max-width: {px(40)}px; min-height: {px(40)}px; max-height: {px(40)}px; }}
QFrame#actionCard {{ background: {CARD}; border: 1px solid {LINE}; border-radius: {px(14)}px; }}
QFrame#actionCard:hover {{ border-color: {ACCENT}; background: #19212b; }}
QFrame#actionCard QLabel {{ background: transparent; }}
QLabel#chip {{ background: #1c2330; border: 1px solid {LINE}; border-radius: {px(11)}px; padding: {px(3)}px {px(10)}px; color: {MUTED}; font-size: {px(12)}px; }}
QLabel#statusOk {{ color: {ACCENT}; font-weight: 600; font-size: {px(15)}px; }}
QLabel#statusBad {{ color: #ebb43c; font-weight: 600; font-size: {px(15)}px; }}
QLabel#tip {{ color: #b6bfcc; font-size: {px(13)}px; }}
QSlider::groove:horizontal {{ height: {px(6)}px; background: {LINE}; border-radius: {px(3)}px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: {px(3)}px; }}
QSlider::handle:horizontal {{ background: #fff; width: {px(16)}px; height: {px(16)}px; margin: -{px(5)}px 0; border-radius: {px(8)}px; }}
"""


# ------------------------------------------------------------------ widgets
class Switch(QAbstractButton):
    def __init__(self, checked: bool = False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(px(44), px(24))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(px(44), px(24))

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ACCENT if self.isChecked() else "#2b3442"))
        p.drawRoundedRect(self.rect(), self.height() / 2, self.height() / 2)
        d = self.height() - px(6)
        x = self.width() - d - px(3) if self.isChecked() else px(3)
        p.setBrush(QColor("#ffffff" if self.isEnabled() else "#8a93a0"))
        p.drawEllipse(QRect(x, px(3), d, d))
        p.end()


class HotkeyEdit(QPushButton):
    """Кнопка-поле: клик → нажмите сочетание. Esc — отмена, Backspace — вернуть прежнее."""

    changed = Signal(str)
    capturing = Signal(bool)

    def __init__(self, value: str):
        super().__init__(value)
        self.setObjectName("hotkey")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.value = value
        self._on = False
        self.clicked.connect(self._begin)

    def set_value(self, v: str) -> None:
        self.value = v
        if not self._on:
            self.setText(v)

    def set_bad(self, bad: bool) -> None:
        self.setProperty("bad", bad)
        self.style().unpolish(self)
        self.style().polish(self)

    def _set_capture(self, on: bool) -> None:
        self._on = on
        self.setProperty("capturing", on)
        self.setText("Нажмите сочетание…" if on else self.value)
        self.style().unpolish(self)
        self.style().polish(self)
        self.capturing.emit(on)

    def _begin(self) -> None:
        if not self._on:
            self._set_capture(True)
            self.setFocus()

    def focusOutEvent(self, e) -> None:  # noqa: N802
        if self._on:
            self._set_capture(False)
        super().focusOutEvent(e)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if not self._on:
            return super().keyPressEvent(e)
        if e.key() == Qt.Key.Key_Escape:
            self._set_capture(False)
            return
        name = qt_key_to_name(int(e.key()))
        if name is None:
            return  # нажат только модификатор — ждём основную клавишу
        m = e.modifiers()
        ctrl = bool(m & Qt.KeyboardModifier.ControlModifier)
        alt = bool(m & Qt.KeyboardModifier.AltModifier)
        shift = bool(m & Qt.KeyboardModifier.ShiftModifier)
        win = bool(m & Qt.KeyboardModifier.MetaModifier)
        if not (ctrl or alt or shift or win):
            self.setText("Нужен Ctrl / Alt / Shift / Win…")
            return
        self.value = format_hotkey(ctrl, alt, shift, win, name)
        self._set_capture(False)
        self.changed.emit(self.value)


def fill_keycaps(lay: QHBoxLayout, spec: str) -> None:
    while lay.count():
        it = lay.takeAt(0)
        w = it.widget()
        if w:
            w.deleteLater()
    parts = [p for p in spec.split("+") if p]
    for i, part in enumerate(parts):
        if i:
            lay.addWidget(label("+", "plus"))
        lay.addWidget(label(part, "key"))
    lay.addStretch(1)


class KeyCaps(QWidget):
    def __init__(self, spec: str = ""):
        super().__init__()
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(px(4))
        self.set_spec(spec)

    def set_spec(self, spec: str) -> None:
        fill_keycaps(self.lay, spec)


class ActionCard(QFrame):
    clicked = Signal()

    def __init__(self, glyph: str, title: str, desc: str, danger: bool = False):
        super().__init__()
        self.setObjectName("actionCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(px(18), px(16), px(18), px(16))
        lay.setSpacing(px(10))
        top = QHBoxLayout()
        top.setSpacing(px(12))
        g = label(glyph, "glyphDanger" if danger else "glyph")
        g.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(g)
        col = QVBoxLayout()
        col.setSpacing(px(1))
        col.addWidget(label(title, "h2"))
        col.addWidget(label(desc, "muted", wrap=True))
        top.addLayout(col, 1)
        lay.addLayout(top)
        self.keys = KeyCaps()
        lay.addWidget(self.keys)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


def card() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(px(20), px(18), px(20), px(18))
    lay.setSpacing(px(14))
    return f, lay


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def sep() -> QFrame:
    f = QFrame()
    f.setObjectName("sep")
    return f


def row(title: str, hint: str, control: QWidget) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(px(16))
    col = QVBoxLayout()
    col.setSpacing(px(2))
    col.addWidget(label(title, "h2"))
    if hint:
        col.addWidget(label(hint, "muted", wrap=True))
    h.addLayout(col, 1)
    if hint and not control.toolTip():
        control.setToolTip(hint)
    h.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
    return w


def page(title: str, subtitle: str) -> tuple[QScrollArea, QVBoxLayout]:
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    inner = QWidget()
    inner.setObjectName("content")
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(px(32), px(28), px(32), px(28))
    lay.setSpacing(px(16))
    lay.addWidget(label(title, "h1"))
    if subtitle:
        lay.addWidget(label(subtitle, "muted", wrap=True))
    sc.setWidget(inner)
    return sc, lay


HOTKEY_INFO = [
    ("full_screen", "Перевести весь экран", "Снимок монитора, на котором курсор"),
    ("region", "Перевести область", "Выделите прямоугольник мышью (Esc — отмена)"),
    ("clear", "Убрать перевод", "Скрыть плашки и панель"),
    ("toggle_mode", "Сменить режим", "Поверх игры ⇄ отдельная панель"),
    ("quit", "Выход", "Закрыть программу"),
]
ENGINE_INFO = [
    ("google", "Google", "Без ключа. Быстро, но лор знает хуже — опирается на глоссарий."),
    ("deepl", "DeepL", "Нужен ключ DeepL API (free — ключ с «:fx» на конце)."),
    ("claude", "Claude", "Нужен ключ Anthropic. Лучше всего держит лор: глоссарий уходит в запрос."),
]


class SettingsWindow(QWidget):
    action = Signal(str)               # full | region | clear
    saved = Signal(dict)               # новая конфигурация
    hotkey_capture = Signal(bool)      # на время записи сочетания глобальные хоткеи выключаются
    test_engine = Signal(str, dict)    # имя движка, его настройки
    maintenance = Signal(str)          # open_dir | reload_glossary | clear_cache
    check_updates = Signal()
    install_update = Signal()

    def __init__(self, cfg: dict, icon):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("DF Translator")
        self.setWindowIcon(icon)
        self.resize(px(940), px(660))
        self.setMinimumSize(px(780), px(520))
        self.setStyleSheet(build_qss())
        self.cfg = cfg
        self.draft = copy.deepcopy(cfg)
        self._building = True

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(px(220))
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, px(22), 0, px(16))
        sl.setSpacing(0)
        brand = QHBoxLayout()
        brand.setContentsMargins(px(22), 0, px(16), px(18))
        brand.addWidget(label("译  DF Translator", "brand"))
        sl.addLayout(brand)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for t, tip in (("⌂   Главная", "Быстрые действия и все горячие клавиши"),
                       ("⌨   Горячие клавиши", "Изменить сочетания клавиш"),
                       ("文   Перевод", "Движок перевода и ключи"),
                       ("◐   Отображение", "Вид плашек с переводом"),
                       ("◎   Распознавание", "Настройки OCR"),
                       ("⟳   Обновления", "Проверка и установка новых версий"),
                       ("ⓘ   О программе", "Автозапуск, глоссарий, античит")):
            it = QListWidgetItem(t)
            it.setToolTip(tip)
            self.nav.addItem(it)
        sl.addWidget(self.nav, 1)
        ver = label(f"v{__version__} · by LastNova", "version")
        ver.setToolTip(f"{CREDIT}\nВопросы: Discord-чат или Telegram @{TELEGRAM}")
        sl.addWidget(ver, 0, Qt.AlignmentFlag.AlignHCenter)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_home())
        self.stack.addWidget(self._page_hotkeys())
        self.stack.addWidget(self._page_engine())
        self.stack.addWidget(self._page_display())
        self.stack.addWidget(self._page_ocr())
        self.stack.addWidget(self._page_updates())
        self.stack.addWidget(self._page_about())
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        right = QVBoxLayout()
        right.setSpacing(0)
        right.addWidget(self.stack, 1)
        right.addWidget(self._save_bar())
        root.addWidget(side)
        right_w = QWidget()
        right_w.setObjectName("content")
        right_w.setLayout(right)
        root.addWidget(right_w, 1)

        self._building = False
        self.refresh_home()
        self._refresh_dirty()

    # --------------------------------------------------------------- save bar
    def _save_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("side")
        bar.setStyleSheet(f"QFrame#side {{ border-right: 0; border-top: 1px solid {LINE}; }}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(px(32), px(12), px(32), px(12))
        self.dirty_label = label("", "muted")
        h.addWidget(self.dirty_label, 1)
        self.btn_reset = QPushButton("Отменить изменения")
        self.btn_reset.clicked.connect(self.discard)
        self.btn_save = QPushButton("Сохранить")
        self.btn_save.setObjectName("primary")
        self.btn_save.clicked.connect(self.save)
        self.btn_save.setToolTip("Применить и сохранить изменения")
        self.btn_reset.setToolTip("Вернуть последние сохранённые настройки")
        h.addWidget(self.btn_reset)
        h.addWidget(self.btn_save)
        return bar

    def _refresh_dirty(self) -> None:
        errs = validate_bindings(self.draft["hotkeys"])
        for name, edit in self.hk_edits.items():
            edit.set_bad(name in errs)
        dirty = self.draft != self.cfg
        self.btn_save.setEnabled(dirty and not errs)
        self.btn_reset.setEnabled(dirty)
        if errs:
            first = next(iter(errs.items()))
            self.dirty_label.setText("Горячие клавиши: " + first[1])
        else:
            self.dirty_label.setText("Есть несохранённые изменения" if dirty else "Все изменения сохранены")

    def save(self) -> None:
        self.saved.emit(copy.deepcopy(self.draft))
        self._refresh_dirty()

    def discard(self) -> None:
        self.draft = copy.deepcopy(self.cfg)
        self.load_from_draft()

    def load_from_draft(self) -> None:
        self._building = True
        d = self.draft
        for n, e in self.hk_edits.items():
            e.set_value(d["hotkeys"][n])
        self.mode_btns[d["display"]["mode"]].setChecked(True)
        self.engine_btns[d["engine"]].setChecked(True)
        self.deepl_key.setText(d["engines"]["deepl"].get("api_key", ""))
        self.claude_key.setText(d["engines"]["claude"].get("api_key", ""))
        self.claude_model.setCurrentText(d["engines"]["claude"].get("model", ""))
        for key, (sl, _lbl) in self.sliders.items():
            sl.setValue(self._slider_get(key))
        for key, sw in self.switches.items():
            sw.setChecked(bool(self._switch_get(key)))
        self._building = False
        self.refresh_home()
        self._refresh_dirty()

    def sync_after_external_change(self) -> None:
        """Режим/движок поменяли из трея или хоткеем — подтянуть в окно."""
        self.draft["display"]["mode"] = self.cfg["display"]["mode"]
        self.draft["engine"] = self.cfg["engine"]
        self.load_from_draft()

    # ------------------------------------------------------------------ pages
    def _page_home(self) -> QWidget:
        sc, lay = page("Главная", "")
        # --- статус
        sc_card, sl = card()
        top = QHBoxLayout()
        top.setSpacing(px(12))
        self.status_label = label("● Готово к работе", "statusOk")
        top.addWidget(self.status_label)
        top.addStretch(1)
        self.chip_mode = label("", "chip")
        self.chip_engine = label("", "chip")
        top.addWidget(self.chip_mode)
        top.addWidget(self.chip_engine)
        sl.addLayout(top)
        self.status_sub = label("Нажмите горячую клавишу в игре или карточку ниже — окно скроется на время снимка.", "muted", wrap=True)
        sl.addWidget(self.status_sub)
        lay.addWidget(sc_card)

        # --- действия
        cards = QHBoxLayout()
        cards.setSpacing(px(14))
        self.action_cards: dict[str, ActionCard] = {}
        for key, glyph, title, desc, hk, danger, tip in (
            ("full", "⛶", "Весь экран", "Перевести монитор, где курсор", "full_screen", False,
             "Снимок всего монитора и перевод всех найденных китайских надписей"),
            ("region", "▭", "Область", "Выделить текст мышью", "region", False,
             "Выделите рамкой только нужный текст — точнее и быстрее. Esc отменяет"),
            ("clear", "✕", "Убрать перевод", "Скрыть плашки и панель", "clear", True,
             "Убирает перевод с экрана. Работает и из игры — по горячей клавише"),
        ):
            c = ActionCard(glyph, title, desc, danger)
            c.setToolTip(tip)
            c.clicked.connect(lambda k=key: self.action.emit(k))
            c.hk_name = hk
            self.action_cards[key] = c
            cards.addWidget(c, 1)
        lay.addLayout(cards)

        # --- все горячие клавиши
        kc, kl = card()
        head = QHBoxLayout()
        head.addWidget(label("Горячие клавиши", "h2"), 1)
        edit = QPushButton("Изменить")
        edit.setToolTip("Открыть настройку сочетаний клавиш")
        edit.clicked.connect(lambda: self.nav.setCurrentRow(1))
        head.addWidget(edit)
        kl.addLayout(head)
        grid = QGridLayout()
        grid.setHorizontalSpacing(px(24))
        grid.setVerticalSpacing(px(10))
        self.home_keys: dict[str, KeyCaps] = {}
        for i, (name, title, hint) in enumerate(HOTKEY_INFO):
            lb = label(title, "")
            lb.setToolTip(hint)
            kcp = KeyCaps()
            kcp.setToolTip(hint)
            self.home_keys[name] = kcp
            grid.addWidget(lb, i, 0)
            grid.addWidget(kcp, i, 1)
        grid.setColumnStretch(1, 1)
        kl.addLayout(grid)
        lay.addWidget(kc)

        # --- режим
        self.mode_btns: dict[str, QPushButton] = {}
        seg = QHBoxLayout()
        seg.setSpacing(0)
        grp = QButtonGroup(self)
        for key, text, tip in (("overlay", "Поверх игры", "Плашки рисуются прямо над текстом игры"),
                               ("panel", "Отдельная панель", "Список перевода в отдельном окне — удобно на втором мониторе")):
            b = QPushButton(text)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setToolTip(tip)
            grp.addButton(b)
            b.clicked.connect(lambda _=False, k=key: self._set("display.mode", k))
            self.mode_btns[key] = b
            seg.addWidget(b)
        segw = QWidget()
        segw.setLayout(seg)
        mc, ml = card()
        ml.addWidget(row("Режим показа", "Панель на втором мониторе — самый безопасный вариант для античита.", segw))
        lay.addWidget(mc)

        # --- подсказки
        tc, tl = card()
        tl.addWidget(label("Подсказки", "h2"))
        self.tip_labels: list[tuple[QLabel, str]] = []
        for text in (
            "<b>Как убрать перевод:</b> он сам пропадает через 1–2 секунды после любого нажатия клавиши или мыши (настраивается в «Отображении»). Сразу убрать — {clear}.",
            "<b>Плашек не видно поверх игры?</b> Включите в игре «Окно без рамки» или нажмите {toggle_mode} — перевод откроется отдельным окном.",
            "<b>Только часть экрана:</b> {region}, затем выделите текст мышью. Esc — отмена.",
            "<b>Окно закрыто — программа работает:</b> значок «译» в трее у часов. Выход: {quit} или правый клик по значку.",
            f"<b>Что-то не так?</b> Пишите в Discord-чат или Telegram <b style='color:#2fd69b'>@{TELEGRAM}</b>.",
            "<span style='color:#46c878'>●</span> перевод из лор-глоссария (точный) &nbsp; <span style='color:#ebb43c'>●</span> машинный — проверяйте по смыслу.",
        ):
            lb = label("", "tip", wrap=True)
            lb.setTextFormat(Qt.TextFormat.RichText)
            self.tip_labels.append((lb, text))
            tl.addWidget(lb)
        lay.addWidget(tc)
        lay.addStretch(1)
        return sc

    def refresh_home(self) -> None:
        """Обновляет бинды, подсказки и сводку на главной по сохранённой конфигурации."""
        hk = self.cfg["hotkeys"]
        for c in self.action_cards.values():
            c.keys.set_spec(hk[c.hk_name])
        for name, kcp in self.home_keys.items():
            kcp.set_spec(hk[name])

        def fmt(spec: str) -> str:
            return f"<b style='color:#2fd69b'>{spec}</b>"

        for lb, text in self.tip_labels:
            lb.setText(text.format(**{k: fmt(v) for k, v in hk.items()}))
        self.chip_mode.setText("Поверх игры" if self.cfg["display"]["mode"] == "overlay" else "Отдельная панель")
        eng = {"google": "Google", "deepl": "DeepL", "claude": "Claude"}.get(self.cfg["engine"], self.cfg["engine"])
        self.chip_engine.setText(f"Движок: {eng}")

    def set_hotkey_status(self, errors: list[str]) -> None:
        if errors:
            self.status_label.setText("⚠ Часть горячих клавиш не работает")
            self.status_label.setObjectName("statusBad")
            self.status_sub.setText("; ".join(errors) + ". Измените сочетание в разделе «Горячие клавиши».")
        else:
            self.status_label.setText("● Готово к работе")
            self.status_label.setObjectName("statusOk")
            self.status_sub.setText("Нажмите горячую клавишу в игре или карточку ниже — окно скроется на время снимка.")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _page_hotkeys(self) -> QWidget:
        sc, lay = page("Горячие клавиши", "Нажмите на поле и введите новое сочетание. Нужен хотя бы один модификатор: Ctrl, Alt, Shift или Win.")
        c, cl = card()
        self.hk_edits: dict[str, HotkeyEdit] = {}
        for i, (name, title, hint) in enumerate(HOTKEY_INFO):
            e = HotkeyEdit(self.draft["hotkeys"][name])
            e.setToolTip("Нажмите и введите новое сочетание. Esc — отмена")
            e.changed.connect(lambda v, n=name: self._set(f"hotkeys.{n}", v))
            e.capturing.connect(self.hotkey_capture.emit)
            self.hk_edits[name] = e
            if i:
                cl.addWidget(sep())
            cl.addWidget(row(title, hint, e))
        lay.addWidget(c)
        b = QPushButton("Сбросить по умолчанию")
        b.clicked.connect(self._reset_hotkeys)
        lay.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(label("Если сочетание занято другой программой, после сохранения появится предупреждение.", "muted", wrap=True))
        lay.addStretch(1)
        return sc

    def _reset_hotkeys(self) -> None:
        self.draft["hotkeys"] = copy.deepcopy(DEFAULTS["hotkeys"])
        for n, e in self.hk_edits.items():
            e.set_value(self.draft["hotkeys"][n])
        self._refresh_dirty()

    def _page_engine(self) -> QWidget:
        sc, lay = page("Перевод", "Глоссарий и названия квестов переводятся локально всегда. Движок нужен только для текста, которого нет в базе.")
        self.engine_btns: dict[str, QPushButton] = {}
        grp = QButtonGroup(self)
        for key, title, desc in ENGINE_INFO:
            b = QPushButton(f"{title}\n{desc}")
            b.setObjectName("engine")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            grp.addButton(b)
            b.clicked.connect(lambda _=False, k=key: self._set("engine", k))
            self.engine_btns[key] = b
            lay.addWidget(b)
        c, cl = card()
        self.deepl_key = self._key_edit("engines.deepl.api_key", self.draft["engines"]["deepl"].get("api_key", ""))
        self.claude_key = self._key_edit("engines.claude.api_key", self.draft["engines"]["claude"].get("api_key", ""))
        cl.addWidget(row("Ключ DeepL", "Хранится в config.json на вашем компьютере.", self.deepl_key))
        cl.addWidget(sep())
        cl.addWidget(row("Ключ Anthropic (Claude)", "Либо переменная окружения ANTHROPIC_API_KEY.", self.claude_key))
        cl.addWidget(sep())
        self.claude_model = QComboBox()
        self.claude_model.setEditable(True)
        self.claude_model.addItems(["claude-haiku-5-5", "claude-sonnet-5-5"])
        self.claude_model.setCurrentText(self.draft["engines"]["claude"].get("model", "claude-haiku-5-5"))
        self.claude_model.currentTextChanged.connect(lambda v: self._set("engines.claude.model", v.strip()))
        cl.addWidget(row("Модель Claude", "Haiku — дёшево и быстро; Sonnet — точнее.", self.claude_model))
        lay.addWidget(c)
        t = QHBoxLayout()
        self.test_btn = QPushButton("Проверить выбранный движок")
        self.test_btn.clicked.connect(self._run_test)
        self.test_result = label("", "muted", wrap=True)
        t.addWidget(self.test_btn)
        t.addWidget(self.test_result, 1)
        lay.addLayout(t)
        lay.addStretch(1)
        return sc

    def _key_edit(self, path: str, value: str) -> QLineEdit:
        e = QLineEdit(value)
        e.setEchoMode(QLineEdit.EchoMode.Password)
        e.setMinimumWidth(px(300))
        e.setPlaceholderText("не задан")
        e.textChanged.connect(lambda v: self._set(path, v.strip()))
        return e

    def _run_test(self) -> None:
        name = self.draft["engine"]
        self.test_btn.setEnabled(False)
        self.test_result.setObjectName("muted")
        self.test_result.setText("Проверяю…")
        self.test_engine.emit(name, {"engines": copy.deepcopy(self.draft["engines"])})

    def set_test_result(self, ok: bool, text: str) -> None:
        self.test_btn.setEnabled(True)
        self.test_result.setObjectName("ok" if ok else "bad")
        self.test_result.style().unpolish(self.test_result)
        self.test_result.style().polish(self.test_result)
        self.test_result.setText(text)

    def _slider_row(self, key: str, path: str, title: str, hint: str, lo: int, hi: int, fmt) -> QWidget:
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(lo, hi)
        sl.setMinimumWidth(px(220))
        val = label("", "value")
        val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.sliders[key] = (sl, val)
        sl.setValue(self._slider_get(key))
        val.setText(fmt(sl.value()))

        def changed(v: int) -> None:
            val.setText(fmt(v))
            self._set(path, self._slider_to_cfg(key, v))

        sl.valueChanged.connect(changed)
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(sl)
        h.addWidget(val)
        return row(title, hint, box)

    _SLIDERS = {
        "min_font": ("display.min_font_px", 1), "max_font": ("display.max_font_px", 1),
        "opacity": ("display.opacity", 100), "auto_hide": ("display.auto_hide_sec", 1), "hide_delay": ("display.hide_delay_sec", 2),
        "min_score": ("ocr.min_score", 100),
    }

    def _get(self, path: str):
        node = self.draft
        for part in path.split("."):
            node = node[part]
        return node

    def _slider_get(self, key: str) -> int:
        path, mul = self._SLIDERS[key]
        return int(round(float(self._get(path)) * mul))

    def _slider_to_cfg(self, key: str, v: int):
        _, mul = self._SLIDERS[key]
        return v / mul if mul != 1 else v

    def _switch_get(self, key: str):
        return self._get(self._SWITCHES[key])

    _SWITCHES = {
        "dots": "display.show_source_dots", "on_top": "display.panel_always_on_top",
        "merge": "ocr.merge_lines", "upscale": "ocr.region_upscale", "auto_update": "updates.auto", "hint": "display.show_hint", "hide_on_input": "display.hide_on_input",
    }

    def _switch_row(self, key: str, title: str, hint: str) -> QWidget:
        sw = Switch(bool(self._switch_get(key)))
        sw.toggled.connect(lambda v: self._set(self._SWITCHES[key], bool(v)))
        self.switches[key] = sw
        return row(title, hint, sw)

    def _page_display(self) -> QWidget:
        self.sliders: dict = getattr(self, "sliders", {})
        self.switches: dict = getattr(self, "switches", {})
        sc, lay = page("Отображение", "Как выглядят плашки с переводом поверх игры и окно-панель.")
        c, cl = card()
        cl.addWidget(self._slider_row("min_font", "display.min_font_px", "Минимальный шрифт", "Меньше этого размера текст не сжимается.", 8, 24, lambda v: f"{v} px"))
        cl.addWidget(sep())
        cl.addWidget(self._slider_row("max_font", "display.max_font_px", "Максимальный шрифт", "Потолок размера для крупных надписей.", 12, 40, lambda v: f"{v} px"))
        cl.addWidget(sep())
        cl.addWidget(self._slider_row("opacity", "display.opacity", "Непрозрачность плашек", "Ниже — виднее игра под переводом.", 30, 100, lambda v: f"{v} %"))
        cl.addWidget(sep())
        cl.addWidget(self._switch_row("hide_on_input", "Убирать перевод после нажатия",
                                      "Любая клавиша или кнопка мыши (в том числе ЛКМ в игре) скрывает перевод — без Ctrl+Alt+C."))
        cl.addWidget(sep())
        cl.addWidget(self._slider_row("hide_delay", "display.hide_delay_sec", "Задержка скрытия",
                                      "Через сколько секунд после нажатия перевод пропадёт.", 1, 10,
                                      lambda v: f"{v / 2:g} с"))
        cl.addWidget(sep())
        cl.addWidget(self._slider_row("auto_hide", "display.auto_hide_sec", "Автоскрытие", "Через сколько секунд убирать перевод. 0 — не убирать.", 0, 60, lambda v: "выкл" if v == 0 else f"{v} с"))
        lay.addWidget(c)
        c2, c2l = card()
        c2l.addWidget(self._switch_row("hint", "Подсказка «как убрать перевод»", "Маленькая надпись с горячей клавишей, пока перевод на экране."))
        c2l.addWidget(sep())
        c2l.addWidget(self._switch_row("dots", "Цветные точки источника", "Зелёная — глоссарий, жёлтая — машинный перевод."))
        c2l.addWidget(sep())
        c2l.addWidget(self._switch_row("on_top", "Панель поверх всех окон", "Применится сразу после сохранения."))
        lay.addWidget(c2)
        lay.addStretch(1)
        return sc

    def _page_ocr(self) -> QWidget:
        self.sliders = getattr(self, "sliders", {})
        self.switches = getattr(self, "switches", {})
        sc, lay = page("Распознавание", "Настройки OCR. Если в перевод попадает мусор — поднимите порог; если пропадает текст — опустите.")
        c, cl = card()
        cl.addWidget(self._slider_row("min_score", "ocr.min_score", "Порог уверенности", "Строки с оценкой ниже порога отбрасываются.", 20, 95, lambda v: f"{v / 100:.2f}"))
        cl.addWidget(sep())
        cl.addWidget(self._switch_row("merge", "Склеивать строки в абзацы", "Описания квестов переводятся целиком, а не по строчке."))
        cl.addWidget(sep())
        cl.addWidget(self._switch_row("upscale", "Увеличивать мелкие области", "Улучшает распознавание при выделении маленького текста."))
        lay.addWidget(c)
        lay.addStretch(1)
        return sc

    def _page_updates(self) -> QWidget:
        self.switches = getattr(self, "switches", {})
        sc, lay = page("Обновления", "Программа сама проверяет новые версии на GitHub. Достаточно запускать один файл DFTranslator.exe.")
        c, cl = card()
        cl.addWidget(row("Текущая версия", "", label(__version__, "value")))
        cl.addWidget(sep())
        cl.addWidget(self._switch_row("auto_update", "Обновлять автоматически",
                                      "Новая версия скачивается тихо и ставится, когда программа не занята; затем она перезапускается в трее."))
        lay.addWidget(c)
        c2, c2l = card()
        self.update_status = label("Ещё не проверялось", "muted", wrap=True)
        c2l.addWidget(self.update_status)
        btns = QHBoxLayout()
        self.btn_check = QPushButton("Проверить сейчас")
        self.btn_check.clicked.connect(self.check_updates.emit)
        self.btn_install = QPushButton("Установить и перезапустить")
        self.btn_install.setObjectName("primary")
        self.btn_install.setVisible(False)
        self.btn_install.clicked.connect(self.install_update.emit)
        btns.addWidget(self.btn_check)
        btns.addWidget(self.btn_install)
        btns.addStretch(1)
        c2l.addLayout(btns)
        lay.addWidget(c2)
        self.notes_card, nl = card()
        nl.addWidget(label("Что нового", "h2"))
        self.notes_label = label("", "muted", wrap=True)
        nl.addWidget(self.notes_label)
        self.notes_card.setVisible(False)
        lay.addWidget(self.notes_card)
        lay.addStretch(1)
        return sc

    def set_update_state(self, st: dict) -> None:
        """st: text, kind (muted|ok|bad), notes, can_install, busy."""
        self.update_status.setText(st.get("text", ""))
        self.update_status.setObjectName(st.get("kind", "muted"))
        self.update_status.style().unpolish(self.update_status)
        self.update_status.style().polish(self.update_status)
        self.btn_check.setEnabled(not st.get("busy", False))
        self.btn_install.setVisible(bool(st.get("can_install")))
        notes = (st.get("notes") or "").strip()
        self.notes_card.setVisible(bool(notes))
        self.notes_label.setText(notes[:1500])

    def _page_about(self) -> QWidget:
        sc, lay = page("О программе", "")
        a, al = card()
        al.addWidget(label(CREDIT, "h2"))
        al.addWidget(label("Для китайских игроков Delta Force.", "muted"))
        links = label(
            f"Вопросы и проблемы: Discord-чат комьюнити или "
            f"<a style='color:#2fd69b' href='https://t.me/{TELEGRAM}'>Telegram @{TELEGRAM}</a>", "", wrap=True)
        links.setOpenExternalLinks(True)
        links.setTextFormat(Qt.TextFormat.RichText)
        al.addWidget(links)
        lay.addWidget(a)
        c, cl = card()
        self.autostart_sw = Switch(autostart.is_enabled())
        self.autostart_sw.setEnabled(autostart.supported())
        self.autostart_sw.toggled.connect(self._toggle_autostart)
        cl.addWidget(row("Запускать вместе с Windows", "Значок появится в трее.", self.autostart_sw))
        cl.addWidget(sep())
        for text, key, danger in (("Открыть папку настроек", "open_dir", False), ("Перечитать глоссарий", "reload_glossary", False),
                                  ("Очистить кэш машинных переводов", "clear_cache", True)):
            b = QPushButton(text)
            if danger:
                b.setObjectName("danger")
            b.clicked.connect(lambda _=False, k=key: self.maintenance.emit(k))
            cl.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        self.maint_note = label("", "muted", wrap=True)
        cl.addWidget(self.maint_note)
        lay.addWidget(c)
        c2, c2l = card()
        c2l.addWidget(label("Про античит", "h2"))
        c2l.addWidget(label(
            "Не внедряется в игру и не читает её память — только снимок экрана и отдельное окно. "
            "Гарантий от ACE нет; осторожнее всего — «Отдельная панель» на втором мониторе.", "muted", wrap=True))
        lay.addWidget(c2)
        lay.addWidget(label("Данные квестов — kkrb.net (Key725).", "muted", wrap=True))
        lay.addStretch(1)
        return sc

    def _toggle_autostart(self, on: bool) -> None:
        try:
            autostart.set_enabled(on)
            self.show_note("Автозапуск включён" if on else "Автозапуск выключен")
        except OSError as exc:
            self.show_note(f"Не удалось изменить автозапуск: {exc}")

    def show_note(self, text: str) -> None:
        self.maint_note.setText(text)

    # --------------------------------------------------------------- plumbing
    def _set(self, path: str, value) -> None:
        if self._building:
            return
        parts = path.split(".")
        node = self.draft
        for p in parts[:-1]:
            node = node[p]
        node[parts[-1]] = value
        self._refresh_dirty()

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        self._dark_title_bar()

    def _dark_title_bar(self) -> None:
        """Тёмный заголовок окна в Windows 10/11 (иначе он светлый/цветной и выбивается из дизайна)."""
        import sys
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            dwm = ctypes.windll.dwmapi  # type: ignore[attr-defined]
            one = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(one), 4)  # DWMWA_USE_IMMERSIVE_DARK_MODE
            cap = ctypes.c_int(0x0016110E)  # цвет заголовка #0e1116 (BGR), Windows 11
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cap), 4)
            txt = ctypes.c_int(0x00F0EBE8)
            dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(txt), 4)
        except Exception:  # noqa: BLE001
            pass

    def closeEvent(self, e) -> None:  # noqa: N802
        e.ignore()  # закрытие окна = свернуть в трей
        self.hide()
