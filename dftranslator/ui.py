"""Окна на PySide6: оверлей с переводом, панель-список, выбор области, уведомление."""
from __future__ import annotations

import html

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

from .colors import readable_fg
from .layout import Item, Placed, place, place_inplace

PAD = 5
LORE_DOT = QColor(147, 180, 111)      # зелёная точка: перевод из лор-глоссария
MACHINE_DOT = QColor(233, 162, 59)   # жёлтая точка: машинный перевод


def _flag(*flags) -> int:
    """Qt-флаги в int — работает и с enum-классами PySide6 6.4+, и со старыми версиями."""
    value = 0
    for f in flags:
        value |= int(getattr(f, "value", f))
    return value


TEXT_FLAGS = _flag(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignTop, Qt.TextFlag.TextWordWrap)
CENTER_FLAGS = _flag(Qt.AlignmentFlag.AlignCenter)
INPLACE_FLAGS = _flag(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignVCenter, Qt.TextFlag.TextWordWrap)


def frame_to_qimage(frame) -> QImage:
    h, w, _ = frame.image.shape
    img = QImage(frame.image.data, w, h, 3 * w, QImage.Format.Format_BGR888)
    return img.copy()  # копия — чтобы не зависеть от времени жизни numpy-буфера


def _click_through_flags():
    return (
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.Tool
        | Qt.WindowType.WindowTransparentForInput
        | Qt.WindowType.WindowDoesNotAcceptFocus
        | Qt.WindowType.NoDropShadowWindowHint
    )


class OverlayWindow(QWidget):
    """Прозрачное окно поверх экрана: клики проходят сквозь него, фокус не забирается."""

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.setWindowFlags(_click_through_flags())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.placed: list[Placed] = []
        self.hint = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.clear)

    def _font(self, px: int) -> QFont:
        from .fonts import ui_family

        f = QFont(ui_family())
        f.setPixelSize(px)
        f.setWeight(QFont.Weight.Medium)
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        return f

    def _measure(self, text: str, font_px: int, max_w: int) -> tuple[int, int]:
        rect = QFontMetrics(self._font(font_px)).boundingRect(QRect(0, 0, max(10, max_w), 10000), TEXT_FLAGS, text)
        return rect.width(), rect.height()

    def show_items(self, screen: QRect, items: list[Item], hint: str = "") -> None:
        d = self.cfg["display"]
        self.hint = hint if d.get("show_hint", True) else ""
        self.setGeometry(screen)
        self.inplace = bool(d.get("inplace", True))
        if self.inplace:  # перевод ложится ровно на место китайского текста
            self.placed = place_inplace(items, screen.width(), screen.height(), self._measure,
                                        min_font=max(8, int(d["min_font_px"]) - 2), max_font=int(d["max_font_px"]) + 4)
        else:
            self.placed = place(
                items, screen.width(), screen.height(), self._measure,
                min_font=int(d["min_font_px"]), max_font=int(d["max_font_px"]), pad=PAD,
            )
        self.show()
        self.raise_()
        self.update()
        sec = float(d.get("auto_hide_sec", 0) or 0)
        if sec > 0:
            self._timer.start(int(sec * 1000))

    def clear(self) -> None:
        self.placed = []
        self.hint = ""
        self.hide()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        self._paint_plates(p)
        p.end()

    def _paint_plates(self, p: QPainter) -> None:
        d = self.cfg["display"]
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha = int(255 * max(0.3, min(1.0, float(d["opacity"]))))
        if getattr(self, "inplace", False):
            self._paint_inplace(p, d, alpha)
            self._paint_hint(p)
            return
        for it in self.placed:
            rect = QRect(it.x, it.y, it.w, it.h)
            p.setPen(QPen(QColor(78, 90, 108, 235), 1))
            p.setBrush(QColor(16, 18, 24, alpha))
            p.drawRoundedRect(rect, 5, 5)
            p.setFont(self._font(it.font_px))
            p.setPen(QColor(238, 240, 245))
            p.drawText(rect.adjusted(PAD, PAD, -PAD, -PAD), TEXT_FLAGS, it.text)
            if d.get("show_source_dots", True):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(LORE_DOT if it.lore else MACHINE_DOT)
                p.drawEllipse(rect.right() - 9, rect.top() + 3, 6, 6)
        self._paint_hint(p)

    def _paint_inplace(self, p: QPainter, d: dict, alpha: int) -> None:
        """Плашка цвета фона закрывает оригинал, поверх — перевод цветом оригинального текста."""
        a = max(alpha, 240)  # китайский текст должен быть закрыт полностью
        for it in self.placed:
            rect = QRect(it.x, it.y, it.w, it.h)
            bg = it.bg or (16, 18, 24)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(bg[0], bg[1], bg[2], a))
            p.drawRoundedRect(rect, 3, 3)
            fg = readable_fg(it.bg, it.fg)
            p.setFont(self._font(it.font_px))
            p.setPen(QColor(*fg))
            p.drawText(rect.adjusted(2, 0, -2, 0), INPLACE_FLAGS, it.text)
            if d.get("show_source_dots", True) and not it.lore:
                p.setPen(Qt.PenStyle.NoPen)  # жёлтая точка только у машинного перевода — проверяйте по смыслу
                p.setBrush(MACHINE_DOT)
                p.drawEllipse(rect.right() - 5, rect.top() + 1, 4, 4)

    def _paint_hint(self, p: QPainter) -> None:
        if self.hint:  # подсказка, как убрать перевод
            f = self._font(14)
            fm = QFontMetrics(f)
            w, h = fm.horizontalAdvance(self.hint) + 28, fm.height() + 14
            r = QRect((self.width() - w) // 2, self.height() - h - 24, w, h)
            p.setPen(QPen(QColor(214, 174, 98, 220), 1))
            p.setBrush(QColor(16, 18, 24, 235))
            p.drawRoundedRect(r, h / 2, h / 2)
            p.setFont(f)
            p.setPen(QColor(232, 235, 240))
            p.drawText(r, CENTER_FLAGS, self.hint)


class SnapshotWindow(OverlayWindow):
    """Безопасный режим: обычное непрозрачное окно со снимком экрана и переводом поверх.

    В отличие от оверлея, это не прозрачное «сквозное» окно поверх игры, а обыкновенное окно
    приложения (как просмотр картинки). Закрывается любой клавишей или кликом — эти нажатия окно
    получает само, поэтому не нужно ни следить за клавиатурой, ни опрашивать кнопки.
    """

    closed = Signal()

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.pix: QPixmap | None = None

    def show_snapshot(self, screen: QRect, image: QImage, items: list[Item], hint: str = "") -> None:
        self.pix = QPixmap.fromImage(image)
        self.show_items(screen, items, hint)
        self.activateWindow()
        self.setFocus()

    def clear(self) -> None:
        was = self.isVisible()
        super().clear()
        self.pix = None
        if was:
            self.closed.emit()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        if self.pix is not None:
            p.drawPixmap(0, 0, self.pix)
        else:
            p.fillRect(self.rect(), QColor(10, 12, 16))
        self._paint_plates(p)
        p.end()

    def keyPressEvent(self, _e) -> None:  # noqa: N802
        self.clear()

    def mousePressEvent(self, _e) -> None:  # noqa: N802
        self.clear()

    def focusOutEvent(self, e) -> None:  # noqa: N802
        super().focusOutEvent(e)
        QTimer.singleShot(0, self.clear)  # переключились на другое окно (Alt+Tab) — закрываемся


class PanelWindow(QWidget):
    """Обычное окно со списком «оригинал / перевод». Его можно вынести на второй монитор."""

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("DF Translator — перевод")
        flags = Qt.WindowType.Window
        if cfg["display"].get("panel_always_on_top", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)  # не отнимаем фокус у игры
        self.resize(470, 640)
        self.browser = QTextBrowser(self)
        self.browser.setOpenLinks(False)
        self.browser.setStyleSheet(
            "QTextBrowser { background:#161b21; color:#ece7dc; border:0; padding:8px; font-size:14px; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.browser)

    def apply_flags(self) -> None:
        flags = Qt.WindowType.Window
        if self.cfg["display"].get("panel_always_on_top", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()

    def show_items(self, items: list[Item], hint: str = "") -> None:
        rows = []
        if hint and self.cfg["display"].get("show_hint", True):
            rows.append(f"<div style='color:#e6c27a;margin:0 0 14px 0'>{html.escape(hint)}</div>")
        for it in sorted(items, key=lambda i: (round(i.y0 / 12), i.x0)):
            dot = "#93b46f" if it.lore else "#e9a23b"
            ru = html.escape(it.ru) if it.ru else "<i style='color:#c66'>нет перевода</i>"
            rows.append(
                f"<div style='margin:0 0 12px 0'>"
                f"<div style='color:#97a3ae;font-size:11px'>{html.escape(it.zh)}</div>"
                f"<div><span style='color:{dot}'>●</span> {ru}</div></div>"
            )
        self.browser.setHtml("".join(rows) or "<i style='color:#97a3ae'>Китайский текст не найден</i>")
        self.show()
        self.raise_()


class RegionSelector(QWidget):
    """Замороженный снимок экрана, на котором мышью выделяется область."""

    selected = Signal(QRect)   # координаты внутри снимка (пиксели монитора)
    cancelled = Signal()

    def __init__(self, image: QImage, geometry: QRect):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.setGeometry(geometry)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.pix = QPixmap.fromImage(image)
        self._origin = None
        self._current = None
        self._done = False

    def _rect(self) -> QRect | None:
        if self._origin is None or self._current is None:
            return None
        return QRect(self._origin, self._current).normalized()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.drawPixmap(0, 0, self.pix)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        r = self._rect()
        if r:
            p.drawPixmap(r, self.pix, r)
            p.setPen(QPen(QColor(214, 174, 98), 2))
            p.drawRect(r)
            p.setPen(QColor(255, 255, 255))
            p.drawText(r.left() + 4, max(14, r.top() - 6), f"{r.width()}×{r.height()}")
        else:
            p.setPen(QColor(255, 255, 255))
            p.setFont(QFont(self.font().family(), 14))
            p.drawText(self.rect(), CENTER_FLAGS, "Выделите область с текстом · Esc — отмена")
        p.end()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._origin = e.position().toPoint()
            self._current = self._origin
            self.update()
        else:
            self._finish(None)

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._origin is not None:
            self._current = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._origin is None:
            return
        self._current = e.position().toPoint()
        r = self._rect()
        self._finish(r if r and r.width() >= 16 and r.height() >= 10 else None)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self._finish(None)

    def _finish(self, rect: QRect | None) -> None:
        if self._done:
            return
        self._done = True
        self.close()
        (self.selected.emit(rect) if rect else self.cancelled.emit())


class Toast(QWidget):
    """Короткое сообщение сверху по центру монитора; не перехватывает клики."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(_click_through_flags())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._text = ""
        self._error = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, screen: QRect, text: str, error: bool = False, ms: int = 1800) -> None:
        self._text, self._error = text, error
        font = QFont(self.font())
        font.setPixelSize(15)
        fm = QFontMetrics(font)
        w = min(screen.width() - 40, fm.horizontalAdvance(text) + 36)
        self.setGeometry(screen.x() + (screen.width() - w) // 2, screen.y() + 36, w, fm.height() + 20)
        self.show()
        self.raise_()
        self.update()
        self._timer.start(ms if not error else max(ms, 5000))

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(120, 30, 30, 235) if self._error else QColor(16, 18, 24, 235))
        p.drawRoundedRect(self.rect(), 8, 8)
        font = QFont(self.font())
        font.setPixelSize(15)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255))
        p.drawText(self.rect(), CENTER_FLAGS, self._text)
        p.end()
