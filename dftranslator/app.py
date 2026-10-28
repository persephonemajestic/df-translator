"""Приложение: иконка в трее, горячие клавиши, фоновая обработка."""
from __future__ import annotations

import copy
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Qt-координаты должны совпадать с пикселями снимка экрана: отключаем масштабирование Qt.
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

from PySide6.QtCore import QObject, QRect, QTimer, QUrl, Signal  # noqa: E402
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon  # noqa: E402

from . import __version__, capture, updater  # noqa: E402
from .blocks import group_blocks  # noqa: E402
from .config import _merge, config_dir, load_config, save_config  # noqa: E402
from .glossary import Glossary  # noqa: E402
from .hotkeys import HotkeyListener, validate_bindings  # noqa: E402
from .settings import SettingsWindow, detect_scale  # noqa: E402
from .layout import Item  # noqa: E402
from .ocr import OcrEngine, OcrUnavailable, region_scale  # noqa: E402
from .quests import QuestBook  # noqa: E402
from .translate import ENGINES, Translator, build_engine  # noqa: E402
from .ui import OverlayWindow, PanelWindow, RegionSelector, Toast, frame_to_qimage, CENTER_FLAGS  # noqa: E402

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
DATA_DIR = ROOT / "data"
HIDE_DELAY_MS = 90  # даём системе перерисовать экран без нашего оверлея перед снимком

ENGINE_TITLES = {
    "google": "Google (без ключа)",
    "deepl": "DeepL (нужен ключ)",
    "claude": "Claude (нужен ключ, лучше всего по лору)",
}


class Bridge(QObject):
    hotkey = Signal(str)
    results = Signal(object, object)   # прямоугольник монитора, список Item
    status = Signal(str, bool)         # текст, это ошибка?
    test_done = Signal(bool, str)      # результат проверки движка
    update_state = Signal(object)      # dict для окна настроек


def make_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(34, 120, 90))
    p.setPen(QColor(0, 0, 0, 0))
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    p.setPen(QColor(255, 255, 255))
    font = QFont()
    font.setPixelSize(40)
    font.setBold(True)
    p.setFont(font)
    p.drawText(pm.rect(), CENTER_FLAGS, "译")
    p.end()
    return QIcon(pm)


class TranslatorApp:
    def __init__(self) -> None:
        self.qt = QApplication(sys.argv)
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setApplicationName("DF Translator")
        detect_scale()
        self.start_hidden = "--tray" in sys.argv
        self.just_updated = "--updated" in sys.argv
        if self.just_updated:
            time.sleep(1.5)  # старый процесс ещё освобождает горячие клавиши
        updater.cleanup_leftovers()

        self.cfg = load_config()
        user_dir = config_dir()
        self.user_dir = user_dir
        self.glossary = Glossary(DATA_DIR, user_dir)
        obj_user, obj_data = user_dir / "objectives_ru.json", DATA_DIR / "objectives_ru.json"
        self.quests = QuestBook(self.glossary, obj_user if obj_user.exists() else obj_data)
        self.translator = Translator(self.glossary, self.quests, self.cfg, user_dir / "cache.json")
        self.ocr = OcrEngine(self.cfg["ocr"]["min_score"])

        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dft-worker")
        self.busy = False
        self._selector: RegionSelector | None = None
        self._monitor_rect = QRect(0, 0, 1920, 1080)

        self.overlay = OverlayWindow(self.cfg)
        self.panel = PanelWindow(self.cfg)
        self.toast = Toast()

        self.bridge = Bridge()
        self.bridge.hotkey.connect(self.on_hotkey)
        self.bridge.results.connect(self.on_results)
        self.bridge.status.connect(self.on_status)

        self.settings = SettingsWindow(self.cfg, make_icon())
        self.settings.action.connect(self.on_ui_action)
        self.settings.saved.connect(self.apply_settings)
        self.settings.hotkey_capture.connect(self.on_hotkey_capture)
        self.settings.test_engine.connect(self.on_test_engine)
        self.settings.maintenance.connect(self.on_maintenance)
        self.settings.check_updates.connect(lambda: self.check_updates(manual=True))
        self.settings.install_update.connect(self.install_now)
        self.bridge.update_state.connect(self.settings.set_update_state)
        self.upool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dft-update")
        self.pending_update = None  # путь к скачанному и проверенному файлу
        self._update_info = None
        self.bridge.test_done.connect(self.settings.set_test_result)

        self._build_tray()
        self.hotkeys = self._new_listener()
        self.hotkeys.start()
        self.settings.set_hotkey_status(self.hotkeys.errors)

        self.qt.aboutToQuit.connect(self._shutdown)
        QTimer.singleShot(400, self._startup_notice)
        QTimer.singleShot(8000, lambda: self.check_updates(manual=False))
        self._update_timer = QTimer(self.qt)
        self._update_timer.timeout.connect(lambda: self.check_updates(manual=False))
        self._update_timer.start(6 * 3600 * 1000)
        self._apply_timer = QTimer(self.qt)
        self._apply_timer.timeout.connect(self._maybe_apply)
        self._apply_timer.start(30 * 1000)
        if not self.start_hidden:
            self.show_settings()
        self.pool.submit(self._warmup)

    # ------------------------------------------------------------------ tray
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(make_icon(), self.qt)
        self.tray.setToolTip(f"DF Translator {__version__}")
        self.tray.activated.connect(self._on_tray_activated)
        self._menu = QMenu()
        self.tray.setContextMenu(self._menu)
        self._fill_menu()
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_settings()

    def show_settings(self) -> None:
        if not self.settings.isVisible():
            self.settings.sync_after_external_change()
        self.settings.showNormal()
        self.settings.raise_()
        self.settings.activateWindow()

    def _fill_menu(self) -> None:
        menu = self._menu
        menu.clear()
        hk = self.cfg["hotkeys"]
        menu.addAction("Панель управления…", self.show_settings)
        menu.addSeparator()
        menu.addAction(f"Перевести весь экран ({hk['full_screen']})", self.translate_full)
        menu.addAction(f"Перевести выделенную область ({hk['region']})", self.translate_region)
        menu.addAction(f"Убрать перевод ({hk['clear']})", self.clear_all)
        menu.addSeparator()

        self.mode_action = QAction("Режим: поверх игры (оверлей)", menu, checkable=True)
        self.mode_action.setChecked(self.cfg["display"]["mode"] == "overlay")
        self.mode_action.triggered.connect(lambda checked: self.set_mode("overlay" if checked else "panel"))
        menu.addAction(self.mode_action)

        eng_menu = menu.addMenu("Движок перевода")
        self.engine_actions: dict[str, QAction] = {}
        for name in ENGINES:
            act = QAction(ENGINE_TITLES.get(name, name), eng_menu, checkable=True)
            act.setChecked(self.translator.engine_name == name)
            act.triggered.connect(lambda _=False, n=name: self.set_engine(n))
            eng_menu.addAction(act)
            self.engine_actions[name] = act

        menu.addSeparator()
        menu.addAction("Открыть папку настроек и глоссария", self.open_config_dir)
        menu.addAction("Перечитать глоссарий", self.reload_glossary)
        menu.addSeparator()
        menu.addAction(f"Выход ({hk['quit']})", self.qt.quit)

    # ------------------------------------------------------------ обновления
    def _emit_update(self, text: str, kind: str = "muted", notes: str = "", can_install: bool = False, busy: bool = False) -> None:
        self.bridge.update_state.emit({"text": text, "kind": kind, "notes": notes, "can_install": can_install, "busy": busy})

    def check_updates(self, manual: bool) -> None:
        if self.pending_update:
            self._emit_update(f"Версия {self._update_info.version} скачана и готова к установке", "ok", self._update_info.notes, True)
            return
        self.upool.submit(self._update_job, manual)

    def _update_job(self, manual: bool) -> None:
        repo = self.cfg["updates"].get("repo", "")
        try:
            if manual:
                self._emit_update("Проверяю…", busy=True)
            info = updater.fetch_latest(repo)
            if info is None or not updater.is_newer(info.version, __version__):
                if manual:
                    self._emit_update(f"У вас последняя версия ({__version__})", "ok")
                return
            self._update_info = info
            frozen = updater.is_frozen() and updater.can_write_here()
            if not frozen:
                why = "программа запущена не из .exe" if not updater.is_frozen() else "нет прав на запись в папку с программой"
                self._emit_update(f"Доступна версия {info.version}, но автоустановка невозможна: {why}. Скачайте её на GitHub.", "bad", info.notes)
                return
            if not (manual or self.cfg["updates"].get("auto", True)):
                self._emit_update(f"Доступна версия {info.version}", "ok", info.notes, can_install=False)
                return
            self._emit_update(f"Скачиваю версию {info.version}…", notes=info.notes, busy=True)
            last = [0.0]

            def progress(f: float) -> None:
                if f - last[0] >= 0.05:
                    last[0] = f
                    self._emit_update(f"Скачиваю версию {info.version}: {int(f * 100)} %", notes=info.notes, busy=True)

            self.pending_update = updater.download(info, updater.staging_path(), progress)
            self._emit_update(f"Версия {info.version} скачана. Установится, когда программа не занята.", "ok", info.notes, True)
        except Exception as exc:  # noqa: BLE001
            if manual:
                self._emit_update(f"Не удалось проверить обновления: {exc}", "bad")

    def _is_idle(self) -> bool:
        return not (self.busy or self.settings.isVisible() or self.overlay.isVisible() or self.panel.isVisible()
                    or self._selector is not None and self._selector.isVisible())

    def _maybe_apply(self) -> None:
        if self.pending_update and self.cfg["updates"].get("auto", True) and self._is_idle():
            self.install_now()

    def install_now(self) -> None:
        if not self.pending_update:
            return
        try:
            updater.apply_update(self.pending_update)
        except Exception as exc:  # noqa: BLE001
            self.pending_update = None
            self._emit_update(f"Не удалось установить: {exc}", "bad")
            return
        self.qt.quit()

    def _startup_notice(self) -> None:
        if self.just_updated:
            self.tray.showMessage("DF Translator обновлён", f"Установлена версия {__version__}", QSystemTrayIcon.MessageIcon.Information, 6000)
            return
        if not self.start_hidden and not self.hotkeys.errors:
            return
        hk = self.cfg["hotkeys"]
        lines = [f"Весь экран: {hk['full_screen']}", f"Область: {hk['region']}", f"Убрать: {hk['clear']}"]
        if self.hotkeys.errors:
            lines.append("⚠ " + "; ".join(self.hotkeys.errors))
        self.tray.showMessage("DF Translator запущен", "\n".join(lines), QSystemTrayIcon.MessageIcon.Information, 6000)

    # -------------------------------------------------- settings window glue
    def _new_listener(self) -> HotkeyListener:
        return HotkeyListener(dict(self.cfg["hotkeys"]), lambda name: self.bridge.hotkey.emit(name))

    def _restart_hotkeys(self) -> None:
        self.hotkeys.stop()
        self.hotkeys = self._new_listener()
        self.hotkeys.start()

    def on_hotkey_capture(self, on: bool) -> None:
        """Пока записываем новое сочетание, глобальные хоткеи отключены, иначе они сработают сами."""
        if on:
            self.hotkeys.stop()
        else:
            self._restart_hotkeys()

    def on_ui_action(self, name: str) -> None:
        if name == "clear":
            self.clear_all()
            return
        self.settings.hide()
        QTimer.singleShot(150, self.translate_full if name == "full" else self.translate_region)

    def apply_settings(self, new: dict) -> None:
        if validate_bindings(new["hotkeys"]):
            return
        _merge(self.cfg, new)
        save_config(self.cfg)
        self.ocr.min_score = float(self.cfg["ocr"]["min_score"])
        self.translator.set_engine(self.cfg["engine"])
        self.panel.apply_flags()
        self._fill_menu()  # заново создаёт пункты меню с актуальными хоткеями, режимом и движком
        self._restart_hotkeys()
        self.settings.cfg = self.cfg
        self.settings.draft = copy.deepcopy(self.cfg)
        self.settings.refresh_home()
        self.settings.set_hotkey_status(self.hotkeys.errors)
        self.settings._refresh_dirty()
        if self.hotkeys.errors:
            self.say("⚠ " + "; ".join(self.hotkeys.errors), True)
        else:
            self.say("Настройки сохранены")

    def on_test_engine(self, name: str, part: dict) -> None:
        def job() -> None:
            try:
                eng = build_engine(name, part)
                out = eng.translate_batch(["开始游戏"], [{"开始游戏": "Начать игру"}] if not eng.uses_placeholders else [])
                self.bridge.test_done.emit(True, f"Работает: «开始游戏» → «{out[0]}»")
            except Exception as exc:  # noqa: BLE001
                self.bridge.test_done.emit(False, str(exc))

        self.pool.submit(job)

    def on_maintenance(self, what: str) -> None:
        if what == "open_dir":
            self.open_config_dir()
        elif what == "reload_glossary":
            self.glossary.reload()
            self.settings.show_note("Глоссарий перечитан")
        elif what == "clear_cache":
            n = self.translator.cache.clear()
            self.settings.show_note(f"Кэш очищен ({n} записей)")

    # ------------------------------------------------------------- handlers
    def on_hotkey(self, name: str) -> None:
        {
            "full_screen": self.translate_full,
            "region": self.translate_region,
            "clear": self.clear_all,
            "toggle_mode": lambda: self.set_mode("panel" if self.cfg["display"]["mode"] == "overlay" else "overlay"),
            "quit": self.qt.quit,
        }.get(name, lambda: None)()

    def set_mode(self, mode: str) -> None:
        self.cfg["display"]["mode"] = mode
        self.mode_action.setChecked(mode == "overlay")
        self.settings.sync_after_external_change()
        self.clear_all()
        self.say("Режим: " + ("поверх игры" if mode == "overlay" else "отдельная панель"))
        save_config(self.cfg)

    def set_engine(self, name: str) -> None:
        self.translator.set_engine(name)
        for n, act in self.engine_actions.items():
            act.setChecked(n == name)
        self.settings.sync_after_external_change()
        save_config(self.cfg)
        self.say("Движок перевода: " + ENGINE_TITLES.get(name, name))

    def clear_all(self) -> None:
        self.overlay.clear()
        self.panel.hide()

    def open_config_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.user_dir)))

    def reload_glossary(self) -> None:
        self.glossary.reload()
        self.say("Глоссарий перечитан")

    def say(self, text: str, error: bool = False) -> None:
        self.toast.show_message(self._monitor_rect, text, error)

    def on_status(self, text: str, error: bool) -> None:
        self.say(text, error)

    # ---------------------------------------------------------- translation
    def translate_full(self) -> None:
        if self.busy:
            return
        self.overlay.hide()
        self.toast.hide()
        QTimer.singleShot(HIDE_DELAY_MS, self._capture_full)

    def _capture_full(self) -> None:
        try:
            frame = capture.grab_monitor_at_cursor()
        except Exception as exc:  # noqa: BLE001
            self.say(f"Не удалось сделать снимок экрана: {exc}", True)
            return
        self._monitor_rect = QRect(frame.left, frame.top, frame.width, frame.height)
        self._submit(frame, frame, region=False)

    def translate_region(self) -> None:
        if self.busy:
            return
        self.overlay.hide()
        self.toast.hide()
        QTimer.singleShot(HIDE_DELAY_MS, self._capture_region)

    def _capture_region(self) -> None:
        try:
            frame = capture.grab_monitor_at_cursor()
        except Exception as exc:  # noqa: BLE001
            self.say(f"Не удалось сделать снимок экрана: {exc}", True)
            return
        self._monitor_rect = QRect(frame.left, frame.top, frame.width, frame.height)
        sel = RegionSelector(frame_to_qimage(frame), self._monitor_rect)
        sel.selected.connect(lambda r, f=frame: self._on_region_selected(f, r))
        self._selector = sel
        sel.show()
        sel.raise_()
        sel.activateWindow()
        sel.setFocus()

    def _on_region_selected(self, frame, rect: QRect) -> None:
        sub = capture.crop(frame, rect.x(), rect.y(), rect.width(), rect.height())
        self._submit(frame, sub, region=True)

    def _submit(self, full_frame, sub_frame, region: bool) -> None:
        self.busy = True
        self.say("Распознаю текст…")
        dx, dy = sub_frame.left - full_frame.left, sub_frame.top - full_frame.top
        self.pool.submit(self._job, sub_frame.image, dx, dy, region)

    def _warmup(self) -> None:
        try:
            self.ocr.warmup()
        except OcrUnavailable as exc:
            self.bridge.status.emit(str(exc), True)
        except Exception:  # noqa: BLE001
            self.bridge.status.emit("Не удалось загрузить OCR:\n" + traceback.format_exc(limit=1), True)

    def _job(self, image, dx: int, dy: int, region: bool) -> None:
        try:
            scale = 1.0
            if region and self.cfg["ocr"].get("region_upscale", True):
                scale = region_scale(image.shape[1], image.shape[0])
            lines = self.ocr.read(image, scale)
            blocks = group_blocks(lines, merge=bool(self.cfg["ocr"].get("merge_lines", True)))
            if not blocks:
                self.bridge.status.emit("Китайский текст не найден", False)
                return
            self.bridge.status.emit(f"Перевожу ({len(blocks)})…", False)
            results = self.translator.translate([b.text for b in blocks])
            items = [
                Item(
                    zh=r.zh, ru=r.ru,
                    x0=b.x0 + dx, y0=b.y0 + dy, x1=b.x1 + dx, y1=b.y1 + dy,
                    line_h=b.line_h, source=r.source, lore=r.lore,
                )
                for b, r in zip(blocks, results)
            ]
            if self.translator.last_error:
                self.bridge.status.emit(f"Ошибка перевода: {self.translator.last_error}", True)
            self.bridge.results.emit(self._monitor_rect, items)
        except OcrUnavailable as exc:
            self.bridge.status.emit(str(exc), True)
        except Exception as exc:  # noqa: BLE001
            self.bridge.status.emit(f"{type(exc).__name__}: {exc}", True)
        finally:
            self.busy = False

    def on_results(self, monitor: QRect, items: list[Item]) -> None:
        hint = f"{self.cfg['hotkeys']['clear']} — убрать перевод"
        if self.cfg["display"]["mode"] == "panel":
            self.panel.show_items(items, hint)
        else:
            self.overlay.show_items(monitor, items, hint)

    # ------------------------------------------------------------- lifecycle
    def _shutdown(self) -> None:
        self.hotkeys.stop()
        self.translator.cache.flush()
        self.pool.shutdown(wait=False, cancel_futures=True)

    def run(self) -> int:
        return self.qt.exec()


def main() -> None:
    app = TranslatorApp()  # QApplication создаётся внутри; до этого Qt-классы трогать нельзя
    sys.exit(app.run())
