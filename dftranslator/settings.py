"""Окно настроек и панель управления (PySide6)."""
from __future__ import annotations

import copy

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QBoxLayout, QButtonGroup, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QSlider,
    QStackedWidget, QVBoxLayout, QWidget,
)

from . import CREDIT, TELEGRAM, __version__, autostart
from .config import DEFAULTS
from .hotkeys import format_hotkey, qt_key_to_name, validate_bindings

ACCENT = "#28fbb1"
ACCENT_DIM = "#0b3328"
BG, SIDE, CARD, LINE = "#070f14", "#0a141b", "#0e1a22", "#1d3140"
DONE = "#2fd39a"   # зелёный «выполнено» (приглушённый фирменный)
TEXT, MUTED, DANGER = "#e7e9ea", "#8d9ca6", "#ff7a2e"

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


def icon_file(name: str, svg: str) -> str:
    """Маленькая SVG-иконка для QSS (галочка в чекбоксах): пишется во временную папку один раз."""
    import tempfile
    from pathlib import Path

    path = Path(tempfile.gettempdir()) / f"dftranslator_{name}.svg"
    try:
        if not path.exists() or path.read_text(encoding="utf-8") != svg:
            path.write_text(svg, encoding="utf-8")
    except OSError:
        return ""
    return path.as_posix()


CHECK_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-7" fill="none" '
             'stroke="#02140d" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
DASH_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M4 8h8" stroke="#02140d" '
            'stroke-width="2.2" stroke-linecap="round"/></svg>')


def build_qss() -> str:
    from .fonts import display_family, ui_family

    ui, disp = ui_family(), display_family()
    return f"""
* {{ font-family: "{ui}", "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: {px(14)}px; color: {TEXT}; }}
QWidget#root {{ background: {BG}; }}
QWidget#content {{ background: {BG}; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: {px(10)}px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: {px(5)}px; min-height: {px(30)}px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QFrame#side {{ background: {SIDE}; border-right: 1px solid {LINE}; }}
QLabel#brand {{ font-family: "{disp}", "{ui}"; font-size: {px(19)}px; font-weight: 700; color: {ACCENT}; letter-spacing: 1px; }}
QLabel#version {{ color: {MUTED}; font-size: {px(12)}px; }}
QListWidget#nav {{ background: transparent; border: 0; outline: 0; }}
QListWidget#nav::item {{ padding: {px(11)}px {px(14)}px; margin: {px(2)}px {px(10)}px; border-radius: {px(3)}px; color: {MUTED}; }}
QListWidget#nav::item:hover {{ background: #10202a; color: {TEXT}; }}
QListWidget#nav::item:selected {{ background: {ACCENT_DIM}; color: {ACCENT}; border-left: {px(3)}px solid {ACCENT}; }}

QLabel#h1 {{ font-family: "{disp}", "{ui}"; font-size: {px(26)}px; font-weight: 600; letter-spacing: 1px; }}
QLabel#qtitle {{ font-family: "{disp}", "{ui}"; font-size: {px(24)}px; font-weight: 600; }}
QLabel#h2 {{ font-size: {px(15)}px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; font-size: {px(13)}px; }}
QLabel#value {{ color: {ACCENT}; font-weight: 600; min-width: {px(64)}px; }}
QLabel#ok {{ color: {DONE}; }}
QLabel#bad {{ color: {DANGER}; }}

QFrame#card {{ background: {CARD}; border: 1px solid {LINE}; border-radius: {px(4)}px; }}
QFrame#card QLabel {{ background: transparent; }}
QFrame#sep {{ background: {LINE}; max-height: 1px; min-height: 1px; border: 0; }}

QPushButton {{ background: #122330; border: 1px solid {LINE}; border-radius: {px(3)}px; padding: {px(8)}px {px(16)}px; }}
QPushButton:hover {{ background: #183040; }}
QPushButton:pressed {{ background: #0f1e28; }}
QPushButton:disabled {{ color: #4c5c66; background: #0c171e; }}
QPushButton#primary {{ background: {ACCENT}; border: 0; color: #02140d; font-weight: 700; }}
QPushButton#primary:hover {{ background: #7dffd0; }}
QPushButton#primary:disabled {{ background: #0f2a23; color: #3f7a66; }}
QPushButton#danger {{ color: {DANGER}; }}
QPushButton#action {{ text-align: left; font-weight: 600; padding: {px(16)}px {px(18)}px; border-radius: {px(4)}px; background: {CARD}; }}
QPushButton#action:hover {{ border-color: {ACCENT}; background: #11222c; }}
QPushButton#engine {{ text-align: left; padding: {px(14)}px {px(16)}px; border-radius: {px(4)}px; background: {CARD}; }}
QPushButton#engine:hover {{ border-color: #2c4a5e; }}
QPushButton#engine:checked {{ border: 1px solid {ACCENT}; background: {ACCENT_DIM}; }}
QPushButton#seg {{ border-radius: 0; padding: {px(9)}px {px(12)}px; min-width: {px(78)}px; background: {CARD}; }}
QPushButton#seg:checked {{ background: {ACCENT}; color: #02140d; font-weight: 700; border-color: {ACCENT}; }}
QPushButton#hotkey {{ font-family: Consolas, "Cascadia Mono", monospace; font-weight: 600; min-width: {px(170)}px; padding: {px(8)}px {px(14)}px; background: #08131a; }}
QPushButton#hotkey:hover {{ border-color: #2c4a5e; }}
QPushButton#hotkey[capturing="true"] {{ border: 1px solid {ACCENT}; color: {ACCENT}; background: {ACCENT_DIM}; }}
QPushButton#hotkey[bad="true"] {{ border: 1px solid {DANGER}; color: {DANGER}; }}

QLineEdit {{ background: #08131a; border: 1px solid {LINE}; border-radius: {px(3)}px; padding: {px(9)}px {px(12)}px; selection-background-color: {ACCENT}; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QComboBox {{ background: #08131a; border: 1px solid {LINE}; border-radius: {px(3)}px; padding: {px(8)}px {px(12)}px; min-width: {px(150)}px; }}
QComboBox:hover {{ border-color: #2c4a5e; }}
QComboBox::drop-down {{ border: 0; width: {px(26)}px; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {LINE}; selection-background-color: {ACCENT_DIM}; selection-color: {ACCENT}; outline: 0; }}

QToolTip {{ background: #122330; color: {TEXT}; border: 1px solid #2c4a5e; padding: {px(6)}px {px(8)}px; border-radius: {px(6)}px; }}
QLabel#key {{ font-family: Consolas, "Cascadia Mono", monospace; font-size: {px(12)}px; font-weight: 700; color: {TEXT};
  background: #08131a; border: 1px solid #27455c; border-bottom: {px(2)}px solid #27455c; border-radius: {px(6)}px; padding: {px(2)}px {px(8)}px; }}
QLabel#plus {{ color: {MUTED}; font-size: {px(12)}px; }}
QLabel#glyph {{ background: {ACCENT_DIM}; color: {ACCENT}; border-radius: {px(4)}px; font-size: {px(20)}px; font-weight: 700; min-width: {px(40)}px; max-width: {px(40)}px; min-height: {px(40)}px; max-height: {px(40)}px; }}
QLabel#glyphDanger {{ background: #3a1d0c; color: {DANGER}; border-radius: {px(4)}px; font-size: {px(20)}px; font-weight: 700; min-width: {px(40)}px; max-width: {px(40)}px; min-height: {px(40)}px; max-height: {px(40)}px; }}
QFrame#actionCard {{ background: {CARD}; border: 1px solid {LINE}; border-radius: {px(4)}px; }}
QFrame#actionCard:hover {{ border-color: {ACCENT}; background: #11222c; }}
QFrame#actionCard QLabel {{ background: transparent; }}
QLabel#chip {{ background: #122330; border: 1px solid {LINE}; border-radius: {px(4)}px; padding: {px(3)}px {px(10)}px; color: {MUTED}; font-size: {px(12)}px; }}
QLabel#statusOk {{ color: {DONE}; font-weight: 600; font-size: {px(15)}px; }}
QLabel#statusBad {{ color: #ffa24a; font-weight: 600; font-size: {px(15)}px; }}
QLabel#tip {{ color: #c4ccd1; font-size: {px(13)}px; }}
QSlider::groove:horizontal {{ height: {px(6)}px; background: {LINE}; border-radius: {px(3)}px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: {px(3)}px; }}
QSlider::handle:horizontal {{ background: #fff; width: {px(16)}px; height: {px(16)}px; margin: -{px(5)}px 0; border-radius: {px(3)}px; }}
"""


# ------------------------------------------------------------------ widgets
class FlowLayout(QLayout):
    """Раскладка «как текст»: элементы идут в строку и переносятся, когда не помещаются.
    Нужна, чтобы чипы, кнопки и миниатюры не распирали узкое окно."""

    def __init__(self, parent=None, spacing: int | None = None):
        super().__init__(parent)
        self._items: list = []
        self._sp = px(8) if spacing is None else spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int):  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int):  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, w: int) -> int:  # noqa: N802
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, r: QRect) -> None:  # noqa: N802
        super().setGeometry(r)
        self._do(r, False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        s = QSize()
        for it in self._items:
            m = it.minimumSize()
            if it.hasHeightForWidth():      # переносимый текст сжимается до разумной ширины
                m.setWidth(min(m.width(), px(140)))
            s = s.expandedTo(m)
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do(self, r: QRect, test: bool) -> int:
        m = self.contentsMargins()
        x0, y = r.x() + m.left(), r.y() + m.top()
        right = r.right() - m.right()
        x, line_h = x0, 0
        for it in self._items:
            if it.widget() is not None and not it.widget().isVisibleTo(it.widget().parentWidget()):
                continue
            hint = it.sizeHint()
            avail = max(1, right - x0 + 1)
            w = min(hint.width(), avail)
            if x > x0 and x + w - 1 > right:
                x, y, line_h = x0, y + line_h + self._sp, 0
            h = hint.height()
            if w < hint.width() and it.hasHeightForWidth():   # длинный чип переносится по словам
                h = max(h, it.heightForWidth(w))
            if not test:
                it.setGeometry(QRect(x, y, w, h))
            x += w + self._sp
            line_h = max(line_h, h)
        return y + line_h - r.y() + m.bottom()


class ChipLabel(QLabel):
    """Чип: в одну строку, а если не помещается — переносится по словам."""

    def __init__(self, text: str, name: str = "chip"):
        super().__init__(text)
        self.setObjectName(name)
        self.setWordWrap(True)
        # невидимый двойник без переноса — даёт естественную ширину в одну строку (с учётом QSS)
        self._probe = QLabel(text, self)
        self._probe.setObjectName(name)
        self._probe.hide()

    def setText(self, text: str) -> None:  # noqa: N802
        super().setText(text)
        self._probe.setText(text)
        self.updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802
        return self._probe.sizeHint()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        s = self._probe.sizeHint()
        return QSize(min(s.width(), px(140)), s.height())


def flow_widget(widgets: list, spacing: int | None = None) -> QWidget:
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    fl = FlowLayout(w, spacing)
    for x in widgets:
        fl.addWidget(x)
    w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
    return w


class WrapButton(QPushButton):
    """Кнопка с заголовком и переносимым описанием: не распирает окно длинным текстом."""

    def __init__(self, title: str, desc: str):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(px(16), px(12), px(16), px(12))
        lay.setSpacing(px(2))
        for text, name in ((title, "h2"), (desc, "muted")):
            lb = label(text, name, wrap=True)
            lb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lb.setStyleSheet("background: transparent;")
            lay.addWidget(lb)
        sp = self.sizePolicy()
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.layout().sizeHint()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.layout().minimumSize()

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, w: int) -> int:  # noqa: N802
        return self.layout().totalHeightForWidth(w)


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
        p.setBrush(QColor(ACCENT if self.isChecked() else "#27455c"))
        p.drawRoundedRect(self.rect(), self.height() / 2, self.height() / 2)
        d = self.height() - px(6)
        x = self.width() - d - px(3) if self.isChecked() else px(3)
        p.setBrush(QColor("#ffffff" if self.isEnabled() else "#8a98a1"))
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
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
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
    w.setObjectName("row")
    h = QHBoxLayout(w)
    w.row_lay = h
    w.row_control = control
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(px(16))
    col = QVBoxLayout()
    col.setSpacing(px(2))
    col.addWidget(label(title, "h2", wrap=True))
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
    lay.addWidget(label(title.upper(), "h1"))   # заголовки разделов — капсом, как в меню игры
    if subtitle:
        lay.addWidget(label(subtitle, "muted", wrap=True))
    sc.setWidget(inner)
    return sc, lay


HOTKEY_INFO = [
    ("full_screen", "Перевести весь экран", "Снимок монитора, на котором курсор"),
    ("region", "Перевести область", "Выделите прямоугольник мышью (Esc — отмена)"),
    ("clear", "Убрать перевод", "Скрыть плашки и панель"),
    ("quest_guide", "Гид по квесту", "Откройте квест в игре и нажмите — появится карточка с целями и скриншотами мест"),
    ("under_cursor", "Перевод под курсором", "Перевести строку текста вокруг курсора мыши"),
    ("toggle_mode", "Сменить режим", "Поверх игры ⇄ отдельная панель"),
    ("quit", "Выход", "Закрыть программу"),
]
ENGINE_INFO = [
    ("google", "Google", "Без ключа. Если Google ограничит запросы, программа сама переключится на Microsoft или Яндекс."),
    ("microsoft", "Microsoft", "Без ключа (переводчик из браузера Edge). Запасной вариант для Google."),
    ("yandex", "Яндекс", "Без ключа. Часто звучит естественнее по-русски; третий запасной вариант."),
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
    open_quest = Signal(str)           # id квеста
    history_fix = Signal(str, str, bool)  # оригинал, новый перевод, отправить автору
    history_clear = Signal()
    share_all = Signal()               # отправить все личные правки в общую базу

    def __init__(self, cfg: dict, icon):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("DF Translator")
        self.setWindowIcon(icon)
        self.resize(px(1240), px(780))
        # Окно можно сделать маленьким: боковое меню сворачивается в значки, разделы перестраиваются.
        self.setMinimumSize(px(520), px(420))
        self._compact = None
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
        self.side = side
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, px(22), 0, px(16))
        sl.setSpacing(0)
        brand = QHBoxLayout()
        brand.setContentsMargins(px(22), 0, px(16), px(18))
        self.brand_label = label("", "brand")
        self.brand_label.setTextFormat(Qt.TextFormat.RichText)
        brand.addWidget(self.brand_label)
        self.brand_box = brand
        sl.addLayout(brand)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.quest_db = None
        self.history = None
        pages = [
            ("home", "⌂   Главная", "Быстрые действия и все горячие клавиши", self._page_home),
            ("quests", "≡   Квесты", "Все задания отделов: цели, награды, скриншоты мест", self._page_quests),
            ("history", "↺   История", "Последние переводы — скопировать или исправить", self._page_history),
            ("hotkeys", "⇧   Горячие клавиши", "Изменить сочетания клавиш", self._page_hotkeys),
            ("engine", "文   Перевод", "Движок перевода и ключи", self._page_engine),
            ("display", "◐   Отображение", "Вид плашек с переводом", self._page_display),
            ("ocr", "◎   Распознавание", "Настройки OCR", self._page_ocr),
            ("updates", "↻   Обновления", "Проверка и установка новых версий", self._page_updates),
            ("about", "ⓘ   О программе", "Автозапуск, глоссарий, античит", self._page_about),
        ]
        self.page_index = {key: i for i, (key, *_rest) in enumerate(pages)}
        self.nav_texts = [t for _key, t, _tip, _b in pages]
        for _key, t, tip, _builder in pages:
            it = QListWidgetItem(t)
            it.setToolTip(tip)
            self.nav.addItem(it)
        sl.addWidget(self.nav, 1)
        ver = label(f"v{__version__} · by LastNova", "version")
        ver.setToolTip(f"{CREDIT}\nВопросы: Discord-чат или Telegram @{TELEGRAM}")
        self.ver_label = ver
        sl.addWidget(ver, 0, Qt.AlignmentFlag.AlignHCenter)

        self.stack = QStackedWidget()
        for _key, _t, _tip, builder in pages:
            self.stack.addWidget(builder())
        self.page_lays = [self.stack.widget(i).widget().layout() for i in range(self.stack.count())
                          if isinstance(self.stack.widget(i), QScrollArea)]
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
        self.load_from_draft()
        self._apply_layout()

    # ------------------------------------------------------------ адаптивность
    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        if hasattr(self, "btn_reset"):
            self._apply_layout()

    def _apply_layout(self) -> None:
        """Перестраивает окно под его ширину: узкое окно — меню значками, карточки столбиком."""
        w = self.width()
        compact = w < px(980)
        if compact != self._compact:
            self._compact = compact
            self.side.setFixedWidth(px(64) if compact else px(220))
            from .fonts import ui_family
            glyph = f"<span style=\"font-family:'{ui_family()}','Microsoft YaHei UI';\">译</span>"
            self.brand_label.setText(glyph if compact else f"{glyph}&nbsp;&nbsp;DF Translator")
            self.brand_box.setContentsMargins(px(22) if not compact else px(20), 0, px(16) if not compact else 0, px(18))
            self.ver_label.setText(__version__ if compact else f"v{__version__} · by LastNova")
            self.nav.setStyleSheet(
                f"QListWidget#nav::item {{ padding: {px(9)}px 0; margin: {px(2)}px {px(8)}px; }}" if compact else "")
            for i, t in enumerate(self.nav_texts):
                it = self.nav.item(i)
                it.setText(t.split()[0] if compact else t)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter if compact else
                                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        content = w - self.side.width()
        narrow = content < px(720)
        if hasattr(self, "cards_lay"):
            self.cards_lay.setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
        if hasattr(self, "q_hint"):
            self.q_hint.setVisible(content >= px(860))
            # низкое окно: заголовок «Квесты» прячем — место нужнее списку
            low = self.height() < px(640)
            self.q_title.setVisible(not low)
            self.q_hint.setVisible(content >= px(860) and not low)
            self.q_page_lay.setContentsMargins(px(14) if narrow else px(24), px(10) if low else px(22),
                                               px(14) if narrow else px(24), px(10) if low else px(16))
        m = px(16) if narrow else px(32)
        self.save_bar_lay.setContentsMargins(m, px(10), m, px(10))
        self.btn_reset.setText("Отменить" if narrow else "Отменить изменения")
        for lay in getattr(self, "page_lays", []):
            lay.setContentsMargins(m, px(20) if narrow else px(28), m, px(20) if narrow else px(28))
        stacked = content < px(640)
        if stacked != getattr(self, "_rows_stacked", None):
            self._rows_stacked = stacked
            for r in self.findChildren(QWidget, "row"):
                lay = getattr(r, "row_lay", None)
                if lay is None:
                    continue
                lay.setDirection(QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight)
                lay.setSpacing(px(8) if stacked else px(16))
                lay.setAlignment(r.row_control, (Qt.AlignmentFlag.AlignLeft if stacked else Qt.AlignmentFlag.AlignRight)
                                 | Qt.AlignmentFlag.AlignVCenter)

    # --------------------------------------------------------------- save bar
    def _save_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("side")
        bar.setStyleSheet(f"QFrame#side {{ border-right: 0; border-top: 1px solid {LINE}; }}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(px(32), px(12), px(32), px(12))
        self.save_bar_lay = h
        self.dirty_label = label("", "muted", wrap=True)
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
        self.status_label = label("● Готово к работе", "statusOk", wrap=True)
        sl.addWidget(self.status_label)
        self.chip_mode = ChipLabel("")
        self.chip_engine = ChipLabel("")
        sl.addWidget(flow_widget([self.chip_mode, self.chip_engine], px(6)))
        self.status_sub = label("Нажмите горячую клавишу в игре или карточку ниже — окно скроется на время снимка.", "muted", wrap=True)
        sl.addWidget(self.status_sub)
        lay.addWidget(sc_card)

        # --- действия
        cards = QHBoxLayout()
        cards.setSpacing(px(14))
        self.cards_lay = cards
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
        edit.clicked.connect(lambda: self.go("hotkeys"))
        head.addWidget(edit)
        kl.addLayout(head)
        grid = QGridLayout()
        grid.setHorizontalSpacing(px(24))
        grid.setVerticalSpacing(px(10))
        self.home_keys: dict[str, KeyCaps] = {}
        for i, (name, title, hint) in enumerate(HOTKEY_INFO):
            lb = label(title, "", wrap=True)
            lb.setToolTip(hint)
            kcp = KeyCaps()
            kcp.setToolTip(hint)
            self.home_keys[name] = kcp
            grid.addWidget(lb, i, 0, Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(kcp, i, 1, Qt.AlignmentFlag.AlignVCenter)
        grid.setColumnStretch(1, 1)
        kl.addLayout(grid)
        lay.addWidget(kc)

        # --- режим
        self.mode_btns: dict[str, QPushButton] = {}
        seg = QHBoxLayout()
        seg.setSpacing(0)
        grp = QButtonGroup(self)
        for key, text, tip in (
            ("snapshot", "Безопасный", "Снимок экрана с переводом в обычном окне. Закрывается любой клавишей или кликом. "
                                       "Ничего не рисует поверх игры — самый незаметный для античита режим"),
            ("panel", "Панель", "Список перевода в отдельном окне — удобно на втором мониторе"),
            ("overlay", "Поверх игры", "Прозрачные плашки прямо над игрой. Удобно, но такие окна больше похожи на то, что ищут античиты"),
        ):
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
        ml.addWidget(row("Режим показа", "«Безопасный» рекомендуется: ничего не рисуется поверх игры.", segw))
        lay.addWidget(mc)

        # --- подсказки
        tc, tl = card()
        tl.addWidget(label("Подсказки", "h2"))
        self.tip_labels: list[tuple[QLabel, str]] = []
        for text in (
            "<b>Как убрать перевод:</b> в безопасном режиме — любая клавиша или клик. В режиме «Поверх игры» он пропадает сам после нажатия. Всегда работает {clear}.",
            "<b>Безопасность:</b> программа не трогает игру. Режим «Безопасный» не рисует поверх игры вообще; переводите в меню и лобби, а не в рейде.",
            "<b>Перевод не появляется?</b> Включите в игре «Окно без рамки». {toggle_mode} — переключить на отдельную панель.",
            "<b>Квест непонятен?</b> Откройте его в игре и нажмите {quest_guide} — карточка с целями, наградами и скриншотами мест.",
            "<b>Только часть экрана:</b> {region}, затем выделите текст мышью. {under_cursor} — строка под курсором.",
            "<b>Окно закрыто — программа работает:</b> значок «译» в трее у часов. Выход: {quit} или правый клик по значку.",
            f"<b>Что-то не так?</b> Пишите в Discord-чат или Telegram <b style='color:#7dffd0'>@{TELEGRAM}</b>.",
            "<span style='color:#2fd39a'>●</span> перевод из лор-глоссария (точный) &nbsp; <span style='color:#ffa24a'>●</span> машинный — проверяйте по смыслу.",
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
            return f"<b style='color:#7dffd0'>{spec}</b>"

        for lb, text in self.tip_labels:
            lb.setText(text.format(**{k: fmt(v) for k, v in hk.items()}))
        self.chip_mode.setText({"snapshot": "Безопасный режим", "panel": "Отдельная панель",
                                "overlay": "Поверх игры"}.get(self.cfg["display"]["mode"], ""))
        eng = {"google": "Google", "microsoft": "Microsoft", "yandex": "Яндекс", "deepl": "DeepL", "claude": "Claude"}.get(self.cfg["engine"], self.cfg["engine"])
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

    def go(self, key: str) -> None:
        self.nav.setCurrentRow(self.page_index[key])

    # ------------------------------------------------------------- квесты
    def _page_quests(self) -> QWidget:
        w = QWidget()
        w.setObjectName("content")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(px(24), px(22), px(24), px(16))
        lay.setSpacing(px(12))
        self.q_page_lay = lay
        head = QHBoxLayout()
        self.q_title = label("КВЕСТЫ", "h1")
        head.addWidget(self.q_title)
        head.addStretch(1)
        self.q_hint = label("В игре: откройте задание и нажмите «Гид по квесту» — оно откроется здесь", "muted")
        head.addWidget(self.q_hint)
        lay.addLayout(head)
        self.q_host = QVBoxLayout()
        lay.addLayout(self.q_host, 1)
        self.quest_browser = None
        return w

    def install_quest_browser(self, browser) -> None:
        self.quest_browser = browser
        self.q_host.addWidget(browser)

    # ------------------------------------------------------------ история
    def _page_history(self) -> QWidget:
        sc, lay = page("История", "Последние переводы. Если перевод неверный — впишите правильный и нажмите «Исправить»: "
                                  "правка сразу заработает у вас, а «отправить автору» добавит её в общую базу для всех "
                                  "(нужен аккаунт GitHub).")
        self.h_list = QListWidget()
        self.h_list.setObjectName("hlist")
        self.h_list.setStyleSheet(
            f"QListWidget#hlist {{ background: {CARD}; border: 1px solid {LINE}; border-radius: {px(4)}px; padding: {px(6)}px; }}"
            f"QListWidget#hlist::item {{ padding: {px(8)}px {px(12)}px; border-radius: {px(3)}px; }}"
            f"QListWidget#hlist::item:selected {{ background: {ACCENT_DIM}; color: {TEXT}; }}")
        self.h_list.setMinimumHeight(px(200))
        lay.addWidget(self.h_list, 1)
        edit_box = QHBoxLayout()
        self.h_edit = QLineEdit()
        self.h_edit.setPlaceholderText("Выберите строку выше, впишите правильный перевод…")
        self.h_list.currentItemChanged.connect(self._on_history_pick)
        edit_box.addWidget(self.h_edit, 1)
        lay.addLayout(edit_box)
        copy_btn = QPushButton("Копировать")
        copy_btn.setToolTip("Скопировать перевод выбранной строки")
        copy_btn.clicked.connect(self._history_copy)
        fix_me = QPushButton("Исправить у себя")
        fix_me.setToolTip("Сохранить правку в вашем словаре — сработает сразу")
        fix_me.clicked.connect(lambda: self._history_fix(False))
        fix_all = QPushButton("Исправить и отправить автору")
        fix_all.setObjectName("primary")
        fix_all.setToolTip("Сохранить у себя и открыть готовое предложение на GitHub — после проверки правка дойдёт до всех")
        fix_all.clicked.connect(lambda: self._history_fix(True))
        clear = QPushButton("Очистить")
        clear.clicked.connect(self.history_clear.emit)
        share = QPushButton("Поделиться всеми правками")
        share.setToolTip("Все ваши исправления — одной заявкой в общую базу. После проверки автором они придут всем")
        share.clicked.connect(self.share_all.emit)
        lay.addWidget(flow_widget([copy_btn, fix_me, fix_all, share, clear]))
        self.h_note = label("", "muted", wrap=True)
        lay.addWidget(self.h_note)
        return sc

    def set_history(self, history) -> None:
        self.history = history
        self.refresh_history()

    def refresh_history(self) -> None:
        if self.history is None:
            return
        cur = self.h_list.currentItem()
        keep = cur.data(Qt.ItemDataRole.UserRole) if cur else None
        self.h_list.clear()
        for e in self.history.entries():
            dot = "●" if e.lore else "○"
            it = QListWidgetItem(f"{dot} {e.ru}\n    {e.zh}")
            it.setData(Qt.ItemDataRole.UserRole, e.zh)
            it.setData(Qt.ItemDataRole.UserRole + 1, e.ru)
            it.setToolTip("Из лор-глоссария" if e.lore else "Машинный перевод")
            self.h_list.addItem(it)
            if e.zh == keep:
                self.h_list.setCurrentItem(it)

    def _on_history_pick(self, it, _prev=None) -> None:
        if it is not None:
            self.h_edit.setText(it.data(Qt.ItemDataRole.UserRole + 1))

    def _history_copy(self) -> None:
        it = self.h_list.currentItem()
        if it is not None:
            QApplication.clipboard().setText(it.data(Qt.ItemDataRole.UserRole + 1))
            self.h_note.setText("Скопировано")

    def _history_fix(self, send: bool) -> None:
        it = self.h_list.currentItem()
        new = self.h_edit.text().strip()
        if it is None or not new:
            self.h_note.setText("Выберите строку и впишите перевод")
            return
        self.history_fix.emit(it.data(Qt.ItemDataRole.UserRole), new, send)
        self.h_note.setText("Сохранено у вас" + (" · откроется GitHub, нажмите там «Submit new issue»" if send else ""))

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
            b = WrapButton(title, desc)
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
        self.test_btn = QPushButton("Проверить выбранный движок")
        self.test_btn.clicked.connect(self._run_test)
        self.test_result = label("", "muted", wrap=True)
        lay.addWidget(self.test_btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self.test_result)
        lay.addStretch(1)
        return sc

    def _key_edit(self, path: str, value: str) -> QLineEdit:
        e = QLineEdit(value)
        e.setEchoMode(QLineEdit.EchoMode.Password)
        e.setMinimumWidth(px(150))
        e.setMaximumWidth(px(320))
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
        sl.setMinimumWidth(px(110))
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
        "merge": "ocr.merge_lines", "upscale": "ocr.region_upscale", "auto_update": "updates.auto", "hint": "display.show_hint", "hide_on_input": "display.hide_on_input", "inplace": "display.inplace",
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
        cl.addWidget(self._switch_row("hide_on_input", "Убирать перевод после нажатия (режим «Поверх игры»)",
                                      "Любая клавиша или клик скрывает плашки. Клавиатура не отслеживается: "
                                      "программа видит только факт ввода, как мессенджеры для статуса «отошёл»."))
        cl.addWidget(sep())
        cl.addWidget(self._slider_row("hide_delay", "display.hide_delay_sec", "Задержка скрытия",
                                      "Через сколько секунд после нажатия перевод пропадёт.", 1, 10,
                                      lambda v: f"{v / 2:g} с"))
        cl.addWidget(sep())
        cl.addWidget(self._slider_row("auto_hide", "display.auto_hide_sec", "Автоскрытие", "Через сколько секунд убирать перевод. 0 — не убирать.", 0, 60, lambda v: "выкл" if v == 0 else f"{v} с"))
        lay.addWidget(c)
        c2, c2l = card()
        c2l.addWidget(self._switch_row("inplace", "Перевод на месте оригинала",
                                       "Русский текст закрывает китайский там же, в цветах игры. "
                                       "Выключите — перевод будет отдельными плашками."))
        c2l.addWidget(sep())
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
        self.btn_check = QPushButton("Проверить сейчас")
        self.btn_check.clicked.connect(self.check_updates.emit)
        self.btn_install = QPushButton("Установить и перезапустить")
        self.btn_install.setObjectName("primary")
        self.btn_install.setVisible(False)
        self.btn_install.clicked.connect(self.install_update.emit)
        c2l.addWidget(flow_widget([self.btn_check, self.btn_install]))
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
            f"<a style='color:#7dffd0' href='https://t.me/{TELEGRAM}'>Telegram @{TELEGRAM}</a>", "", wrap=True)
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
        lay.addWidget(label("Данные квестов, предметов, ключей и мест — kkrb.net (Key725), с разрешения автора. Спасибо!", "muted", wrap=True))
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
            cap = ctypes.c_int(0x0016110E)  # цвет заголовка #070f14 (BGR), Windows 11
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cap), 4)
            txt = ctypes.c_int(0x00F0EBE8)
            dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(txt), 4)
        except Exception:  # noqa: BLE001
            pass

    def closeEvent(self, e) -> None:  # noqa: N802
        e.ignore()  # закрытие окна = свернуть в трей
        self.hide()
