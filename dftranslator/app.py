"""Приложение: иконка в трее, горячие клавиши, фоновая обработка."""
from __future__ import annotations

import copy
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Qt-координаты должны совпадать с пикселями снимка экрана: отключаем масштабирование Qt.
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

from PySide6.QtCore import QObject, QRect, QTimer, QUrl, Signal  # noqa: E402
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QLinearGradient, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon  # noqa: E402

from . import CREDIT, __version__, capture, datasync, inputwatch, updater  # noqa: E402
from .history import History, issue_url  # noqa: E402
from .questdb import QuestDB  # noqa: E402
from .blocks import group_blocks  # noqa: E402
from .config import _merge, config_dir, load_config, save_config  # noqa: E402
from .glossary import Glossary  # noqa: E402
from .hotkeys import HotkeyListener, validate_bindings  # noqa: E402
from .settings import SettingsWindow, detect_scale  # noqa: E402
from .layout import Item  # noqa: E402
from .ocr import OcrEngine, OcrUnavailable, region_scale  # noqa: E402
from .quests import QuestBook  # noqa: E402
from .text import norm_key  # noqa: E402
from .translate import ENGINES, Translator, build_engine  # noqa: E402
from .ui import OverlayWindow, PanelWindow, RegionSelector, SnapshotWindow, Toast, frame_to_qimage, CENTER_FLAGS  # noqa: E402

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
DATA_DIR = ROOT / "data"
HIDE_DELAY_MS = 90  # даём системе перерисовать экран без нашего оверлея перед снимком

MODE_TITLES = {
    "snapshot": "Безопасный снимок (рекомендуется)",
    "panel": "Отдельная панель",
    "overlay": "Поверх игры (прозрачный оверлей)",
}

ENGINE_TITLES = {
    "google": "Google (без ключа)",
    "microsoft": "Microsoft (без ключа)",
    "deepl": "DeepL (нужен ключ)",
    "claude": "Claude (нужен ключ, лучше всего по лору)",
}


class Bridge(QObject):
    hotkey = Signal(str)
    results = Signal(object, object)   # прямоугольник монитора, список Item
    status = Signal(str, bool)         # текст, это ошибка?
    test_done = Signal(bool, str)      # результат проверки движка
    update_state = Signal(object)      # dict для окна настроек
    quest_found = Signal(str)          # id квеста, найденного на экране
    data_updated = Signal(object)      # список обновлённых файлов словаря


def make_icon() -> QIcon:
    """Иконка окна и трея — та же, что у exe (assets/icon.png собирается вместе с программой)."""
    png = ROOT / "assets" / "icon.png"
    if png.exists():
        return QIcon(str(png))
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, 64, 64)
    grad.setColorAt(0, QColor(47, 214, 155))
    grad.setColorAt(1, QColor(23, 160, 112))
    p.setBrush(grad)
    p.setPen(QColor(0, 0, 0, 0))
    p.drawRoundedRect(3, 3, 58, 58, 15, 15)
    p.setPen(QColor(6, 35, 26))
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
        self.data_overlay = user_dir / "data"  # свежий словарь с GitHub (см. datasync)
        self.glossary = Glossary(DATA_DIR, user_dir, overlay_dir=self.data_overlay)
        self.quest_db = QuestDB(DATA_DIR, self.data_overlay)
        self.quest_db.set_names(QuestBook(self.glossary, None).quest_name)
        obj_user = user_dir / "objectives_ru.json"
        self.quests = QuestBook(self.glossary, obj_user if obj_user.exists() else None)
        self.quests.add_objectives(self.quest_db.objectives)
        self.translator = Translator(self.glossary, self.quests, self.cfg, user_dir / "cache.json")
        self.history = History()
        self._img_loader = None
        self.ocr = OcrEngine(self.cfg["ocr"]["min_score"])

        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dft-worker")
        self.busy = False
        self._selector: RegionSelector | None = None
        self._monitor_rect = QRect(0, 0, 1920, 1080)

        self.overlay = OverlayWindow(self.cfg)
        self.snapshot = SnapshotWindow(self.cfg)
        self._last_frame = None
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
        # автоскрытие перевода после нажатия клавиши / кнопки мыши
        self._shown_gen = 0
        self._input_prev = frozenset()
        self._input_armed_at = 0.0
        self._input_timer = QTimer(self.qt)
        self._input_timer.setInterval(40)
        self._input_timer.timeout.connect(self._poll_input)
        self._hide_scheduled = False
        self._update_info = None
        self.bridge.test_done.connect(self.settings.set_test_result)
        self.settings.open_quest.connect(self.open_quest)
        self.settings.history_fix.connect(self.on_history_fix)
        self.settings.history_clear.connect(self.on_history_clear)
        from .progress import Progress
        from .questui import ImageLoader, QuestBrowser

        self.progress = Progress(self.user_dir / "progress.json")
        self._img_loader = ImageLoader(self.user_dir / "img_cache")
        self.quest_browser = QuestBrowser(make_icon(), self._img_loader, lambda r: self.quests.reward(r), self.progress)
        self.quest_browser.name_lookup = lambda zh: self.quests.quest_name(zh)
        self.quest_browser.set_db(self.quest_db)
        self.settings.install_quest_browser(self.quest_browser)
        self.settings.set_history(self.history)
        self.bridge.quest_found.connect(self.open_quest)
        self.bridge.data_updated.connect(self.on_data_updated)

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
        QTimer.singleShot(20000, self.sync_data)
        self._data_timer = QTimer(self.qt)
        self._data_timer.timeout.connect(self.sync_data)
        self._data_timer.start(3 * 3600 * 1000)
        self._apply_timer = QTimer(self.qt)
        self._apply_timer.timeout.connect(self._maybe_apply)
        self._apply_timer.start(30 * 1000)
        if not self.start_hidden:
            self.show_settings()
        self.pool.submit(self._warmup)

    # ------------------------------------------------------------------ tray
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(make_icon(), self.qt)
        self.tray.setToolTip(f"DF Translator {__version__}\n{CREDIT}")
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
        menu.addAction(f"Гид по квесту на экране ({hk['quest_guide']})", self.quest_guide)
        menu.addSeparator()
        menu.addAction("Квесты…", lambda: (self.show_settings(), self.settings.go("quests")))
        menu.addAction("История переводов…", lambda: (self.show_settings(), self.settings.go("history")))
        menu.addSeparator()

        mode_menu = menu.addMenu("Режим показа")
        self.mode_actions: dict[str, QAction] = {}
        for key, title in MODE_TITLES.items():
            act = QAction(title, mode_menu, checkable=True)
            act.setChecked(self.cfg["display"]["mode"] == key)
            act.triggered.connect(lambda _=False, k=key: self.set_mode(k))
            mode_menu.addAction(act)
            self.mode_actions[key] = act

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
                    or self.snapshot.isVisible()
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
            # Чаще всего файл программы держит открытым античит игры — повторим позже, когда игру закроют.
            self._apply_failures = getattr(self, "_apply_failures", 0) + 1
            self._emit_update(
                f"Пока не получилось заменить файл (его держит другая программа, обычно игра). "
                f"Повторю позже сам. ({exc})", "bad", can_install=True)
            return
        self.qt.quit()

    def _startup_notice(self) -> None:
        if self.just_updated:
            self.tray.showMessage(
                f"DF Translator обновлён до {__version__}",
                "Что нового — в панели (клик по значку 译): разделы «Квесты» и «История», "
                f"гид по квесту {self.cfg['hotkeys']['quest_guide']}.",
                QSystemTrayIcon.MessageIcon.Information, 8000)
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
            "toggle_mode": lambda: self.set_mode("panel" if self.cfg["display"]["mode"] != "panel" else "snapshot"),
            "quest_guide": self.quest_guide,
            "under_cursor": self.translate_under_cursor,
            "quit": self.qt.quit,
        }.get(name, lambda: None)()

    def set_mode(self, mode: str) -> None:
        self.cfg["display"]["mode"] = mode
        for k, act in self.mode_actions.items():
            act.setChecked(k == mode)
        self.settings.sync_after_external_change()
        self.clear_all()
        self.say("Режим: " + MODE_TITLES.get(mode, mode))
        save_config(self.cfg)

    def set_engine(self, name: str) -> None:
        self.translator.set_engine(name)
        for n, act in self.engine_actions.items():
            act.setChecked(n == name)
        self.settings.sync_after_external_change()
        save_config(self.cfg)
        self.say("Движок перевода: " + ENGINE_TITLES.get(name, name))

    def _start_input_watch(self) -> None:
        self._shown_gen += 1
        self._hide_scheduled = False
        if self.cfg["display"]["mode"] == "overlay" and self.cfg["display"].get("hide_on_input", True):
            self._input_prev = (inputwatch.last_input_tick(), inputwatch.cursor_pos())
            self._input_armed_at = time.monotonic() + 0.4
            self._input_timer.start()

    def _poll_input(self) -> None:
        cur = (inputwatch.last_input_tick(), inputwatch.cursor_pos())
        prev, self._input_prev = self._input_prev, cur
        if self._hide_scheduled or time.monotonic() < self._input_armed_at:
            return
        if not inputwatch.detect_press(prev[0], cur[0], prev[1], cur[1]):
            return
        self._hide_scheduled = True
        gen = self._shown_gen
        delay = int(float(self.cfg["display"].get("hide_delay_sec", 1.5)) * 1000)
        QTimer.singleShot(delay, lambda: self._auto_hide(gen))

    def _auto_hide(self, gen: int) -> None:
        if gen == self._shown_gen and self.overlay.isVisible():
            self.overlay.clear()
        self._input_timer.stop()

    def clear_all(self) -> None:
        self._input_timer.stop()
        self._shown_gen += 1
        self.overlay.clear()
        self.snapshot.clear()
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
        self.snapshot.clear()
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
        self.snapshot.clear()
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
        self._last_frame = full_frame
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
            # Если OCR склеил в абзац строки, которые по отдельности есть в словаре
            # (пункты списка, подписи), переводим их по одной — так точнее.
            units = []  # (текст, x0, y0, x1, y1, высота строки)
            for b in blocks:
                if len(b.lines) > 1 and self.translator.local(b.text) is None \
                        and any(self.translator.local(ln.text.strip()) for ln in b.lines):
                    units += [(ln.text.strip(), ln.x0, ln.y0, ln.x1, ln.y1, ln.h) for ln in b.lines]
                else:
                    units.append((b.text, b.x0, b.y0, b.x1, b.y1, b.line_h))
            self.bridge.status.emit(f"Перевожу ({len(units)})…", False)
            results = self.translator.translate([u[0] for u in units])
            items = [
                Item(
                    zh=r.zh, ru=r.ru,
                    x0=u[1] + dx, y0=u[2] + dy, x1=u[3] + dx, y1=u[4] + dy,
                    line_h=u[5], source=r.source, lore=r.lore,
                )
                for u, r in zip(units, results)
            ]
            self._last_error = self.translator.last_error
            if self.translator.last_error:
                self.bridge.status.emit(f"Машинный перевод недоступен: {self.translator.last_error}", True)
            self.bridge.results.emit(self._monitor_rect, items)
        except OcrUnavailable as exc:
            self.bridge.status.emit(str(exc), True)
        except Exception as exc:  # noqa: BLE001
            self.bridge.status.emit(f"{type(exc).__name__}: {exc}", True)
        finally:
            self.busy = False

    def on_results(self, monitor: QRect, items: list[Item]) -> None:
        mode = self.cfg["display"]["mode"]
        clear_key = self.cfg["hotkeys"]["clear"]
        if getattr(self, "_last_error", None):
            hint = "⚠ Машинный перевод недоступен (интернет/лимит) — показано только из словаря"
        elif mode == "snapshot":
            hint = "Любая клавиша или клик — закрыть"
        elif mode == "overlay" and self.cfg["display"].get("hide_on_input", True):
            hint = f"Исчезнет после любого нажатия · {clear_key} — убрать сразу"
        else:
            hint = f"{clear_key} — убрать перевод"
        self._remember(items)
        if mode == "panel":
            self.panel.show_items(items, hint)
        elif mode == "snapshot" and self._last_frame is not None:
            self.snapshot.show_snapshot(monitor, frame_to_qimage(self._last_frame), items, hint)
        else:
            self.overlay.show_items(monitor, items, hint)
            self._start_input_watch()

    def _remember(self, items: list[Item]) -> None:
        """История переводов для окна «История» и исправлений."""
        for it in items:
            if it.ru and it.zh and it.source not in ("skip", "error"):
                self.history.add(it.zh, it.ru, it.source, it.lore)
        if self.settings.isVisible():
            self.settings.refresh_history()

    # ------------------------------------------------- квесты и история
    def open_quest(self, quest_id: str) -> None:
        if self.quest_db.get(quest_id) is None:
            return
        self.snapshot.clear()
        self.show_settings()
        self.settings.go("quests")
        self.quest_browser.select(quest_id)

    def quest_guide(self) -> None:
        """Ищет на экране название квеста из базы и открывает его карточку."""
        if self.busy:
            return
        self.overlay.hide()
        self.snapshot.clear()
        self.toast.hide()
        QTimer.singleShot(HIDE_DELAY_MS, self._capture_guide)

    def _capture_guide(self) -> None:
        try:
            frame = capture.grab_monitor_at_cursor()
        except Exception as exc:  # noqa: BLE001
            self.say(f"Не удалось сделать снимок экрана: {exc}", True)
            return
        self._monitor_rect = QRect(frame.left, frame.top, frame.width, frame.height)
        self.busy = True
        self.say("Ищу квест на экране…")
        self.pool.submit(self._guide_job, frame.image)

    def _guide_job(self, image) -> None:
        try:
            lines = self.ocr.read(image, 1.0)
            best = None
            for ln in lines:
                q = self.quest_db.match_name(ln.text)
                if q is None:
                    continue
                score = ln.h + (1000 if norm_key(ln.text) == norm_key(q.name) else 0)
                if best is None or score > best[0]:
                    best = (score, q)
            if best:
                self.bridge.status.emit(f"Квест: {best[1].name_ru}", False)
                self.bridge.quest_found.emit(best[1].id)
            else:
                self.bridge.status.emit("Квест на экране не найден — откройте описание задания в игре. "
                                        "Сезонных квестов в базе пока нет.", True)
        except OcrUnavailable as exc:
            self.bridge.status.emit(str(exc), True)
        except Exception as exc:  # noqa: BLE001
            self.bridge.status.emit(f"{type(exc).__name__}: {exc}", True)
        finally:
            self.busy = False

    def translate_under_cursor(self) -> None:
        if self.busy:
            return
        self.overlay.hide()
        self.snapshot.clear()
        self.toast.hide()
        QTimer.singleShot(HIDE_DELAY_MS, self._capture_under_cursor)

    def _capture_under_cursor(self) -> None:
        try:
            frame = capture.grab_monitor_at_cursor()
        except Exception as exc:  # noqa: BLE001
            self.say(f"Не удалось сделать снимок экрана: {exc}", True)
            return
        self._monitor_rect = QRect(frame.left, frame.top, frame.width, frame.height)
        cx, cy = capture.cursor_pos()
        cx, cy = cx - frame.left, cy - frame.top
        w, h = min(1000, frame.width), min(150, frame.height)
        x = max(0, min(frame.width - w, cx - w // 2))
        y = max(0, min(frame.height - h, cy - h // 2))
        self._submit(frame, capture.crop(frame, x, y, w, h), region=True)

    def on_history_fix(self, zh: str, ru: str, send: bool) -> None:
        path = self.user_dir / "glossary_user.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError):
            data = {}
        old = next((e.ru for e in self.history.entries() if e.zh == zh), "")
        data.setdefault("ui", {})[zh] = ru
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        self.glossary.reload()
        self.history.add(zh, ru, "glossary", True)
        self.settings.refresh_history()
        if send:
            QDesktopServices.openUrl(QUrl(issue_url(self.cfg["updates"].get("repo", ""), zh, old, ru, __version__)))

    def on_history_clear(self) -> None:
        self.history.clear()
        self.settings.refresh_history()

    # ------------------------------------------------ словарь с GitHub
    def sync_data(self) -> None:
        if not self.cfg["updates"].get("data_sync", True):
            return

        def job() -> None:
            try:
                changed = datasync.sync(self.cfg["updates"].get("repo", ""), DATA_DIR, self.data_overlay)
                if changed:
                    self.bridge.data_updated.emit(changed)
            except Exception:  # noqa: BLE001 — нет сети и т.п.: попробуем в следующий раз
                pass

        self.upool.submit(job)

    def on_data_updated(self, changed) -> None:
        self.glossary.reload()
        self.quest_db = QuestDB(DATA_DIR, self.data_overlay)
        self.quest_db.set_names(QuestBook(self.glossary, None).quest_name)
        obj_user = self.user_dir / "objectives_ru.json"
        self.quests = QuestBook(self.glossary, obj_user if obj_user.exists() else None)
        self.quests.add_objectives(self.quest_db.objectives)
        self.translator.q = self.quests
        self.quest_browser.set_db(self.quest_db)
        self.tray.showMessage("DF Translator", "Словарь и база квестов обновлены", QSystemTrayIcon.MessageIcon.Information, 3000)

    # ------------------------------------------------------------- lifecycle
    def _shutdown(self) -> None:
        if self._img_loader is not None:
            self._img_loader.shutdown()
        self.hotkeys.stop()
        self.translator.cache.flush()
        self.pool.shutdown(wait=False, cancel_futures=True)

    def run(self) -> int:
        return self.qt.exec()


def main() -> None:
    app = TranslatorApp()  # QApplication создаётся внутри; до этого Qt-классы трогать нельзя
    sys.exit(app.run())
