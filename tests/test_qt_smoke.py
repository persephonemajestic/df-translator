"""Проверка окон Qt и OCR. Запускается в GitHub Actions на Windows перед выпуском релиза
(локально без PySide6 пропускается). Ловит падения вроде «access violation» до того, как они дойдут до людей."""
import copy
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def errors(monkeypatch):
    caught = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: caught.append(a))
    return caught


def test_settings_window_all_pages(qapp, errors):
    from PySide6.QtGui import QIcon

    from dftranslator.config import DEFAULTS
    from dftranslator.history import History
    from dftranslator.questdb import QuestDB
    from dftranslator.settings import SettingsWindow, detect_scale

    detect_scale()
    cfg = copy.deepcopy(DEFAULTS)
    w = SettingsWindow(cfg, QIcon())
    w.show()
    db = QuestDB(DATA)
    h = History()
    h.add("开始游戏", "Начать игру", "glossary", True)
    w.set_history(h)
    for i in range(w.nav.count()):
        w.nav.setCurrentRow(i)
        qapp.processEvents()
        w.grab()
    w.load_from_draft()
    w.refresh_home()
    w.set_hotkey_status(["тест"])
    w.set_update_state({"text": "t", "notes": "что нового", "can_install": True})
    w.set_test_result(True, "ok")
    qapp.processEvents()
    assert not errors, errors


def test_translation_windows_paint(qapp, errors):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage

    from dftranslator.config import DEFAULTS
    from dftranslator.layout import Item
    from dftranslator.ui import OverlayWindow, PanelWindow, SnapshotWindow, Toast

    cfg = copy.deepcopy(DEFAULTS)
    items = [Item("开始游戏", "Начать игру", 100, 100, 220, 124, 24, "glossary", True),
             Item("仓库", "Склад", 100, 110, 160, 130, 20, "google", False)]
    rect = QRect(0, 0, 800, 600)
    o = OverlayWindow(cfg)
    o.show_items(rect, items, "подсказка")
    o.grab()
    s = SnapshotWindow(cfg)
    img = QImage(800, 600, QImage.Format.Format_RGB888)
    img.fill(0)
    s.show_snapshot(rect, img, items, "подсказка")
    s.grab()
    s.clear()
    p = PanelWindow(cfg)
    p.show_items(items, "подсказка")
    p.apply_flags()
    t = Toast()
    t.show_message(rect, "сообщение")
    t.grab()
    qapp.processEvents()
    assert not errors, errors


def test_quest_card(qapp, errors, tmp_path, monkeypatch):
    from PySide6.QtGui import QIcon

    from dftranslator.glossary import Glossary
    from dftranslator.questdb import QuestDB
    from dftranslator.quests import QuestBook
    from dftranslator.questui import ImageLoader, QuestCard

    g = Glossary(DATA, None)
    db = QuestDB(DATA)
    db.set_names(g.lookup_quest_name)
    book = QuestBook(g, None)
    loader = ImageLoader(tmp_path)
    monkeypatch.setattr(loader, "request", lambda url: None)  # без сети
    card = QuestCard(QIcon(), loader, book.reward, db.get,
                     lambda q: [x for x in db.quests if x.dept == q.dept and x.parent == q.key])
    for qid in ("combat-3", "combat-69", "tactical-8", "research-54", "medical-23"):
        card.show_quest(db.get(qid))
        qapp.processEvents()
        card.grab()
    card.viewer.open(db.get("combat-3").image_urls(), 1)
    card.viewer.grab()
    assert not errors, errors


def test_full_app_starts_and_quits(tmp_path):
    """Запускает программу целиком в отдельном процессе и закрывает через 3 секунды."""
    code = textwrap.dedent("""
        import sys
        from PySide6.QtCore import QTimer
        from dftranslator.app import TranslatorApp
        app = TranslatorApp()
        QTimer.singleShot(3000, app.qt.quit)
        sys.exit(app.run())
    """)
    env = dict(os.environ, APPDATA=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path), QT_QPA_PLATFORM="offscreen")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-4000:]
    assert "Traceback" not in r.stderr, r.stderr[-4000:]


def test_ocr_reads_chinese():
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    if not font_path.exists():
        pytest.skip("нет китайского шрифта")
    pytest.importorskip("rapidocr_onnxruntime")
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    from dftranslator.ocr import OcrEngine

    img = Image.new("RGB", (900, 220), (22, 28, 36))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(font_path), 40)
    d.text((40, 40), "开始游戏", font=font, fill=(235, 235, 235))
    d.text((40, 120), "在零号大坝任意战区行动中", font=font, fill=(235, 235, 235))
    bgr = np.array(img)[:, :, ::-1].copy()
    lines = OcrEngine(0.5).read(bgr, 1.0)
    text = " ".join(ln.text for ln in lines)
    assert "开始游戏" in text, text
    assert "零号大坝" in text, text


def test_quest_browser(qapp, errors, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon

    from dftranslator.glossary import Glossary
    from dftranslator.progress import Progress
    from dftranslator.questdb import QuestDB
    from dftranslator.quests import QuestBook
    from dftranslator.questui import ImageLoader, QuestBrowser

    g = Glossary(DATA, None)
    book = QuestBook(g, None)
    db = QuestDB(DATA)
    db.set_names(book.quest_name)
    loader = ImageLoader(tmp_path / "img")
    monkeypatch.setattr(loader, "request", lambda url: None)
    progress = Progress(tmp_path / "progress.json")
    b = QuestBrowser(QIcon(), loader, book.reward, progress)
    b.name_lookup = book.quest_name
    b.set_db(db)
    b.resize(1400, 800)
    b.show()
    for key in list(b.rail_btns):
        if b.rail_btns[key].isEnabled():
            b.set_section(key)
            qapp.processEvents()
            b.grab()
    b.select("season-5")
    assert b.section == "season:2"
    progress.set_many([q.id for q in db.season_line("1-3")], True)
    b.set_section("season:1")
    top = [b.tree.topLevelItem(i).text(0) for i in range(b.tree.topLevelItemCount())]
    assert any(t.startswith("✓ 1-3") for t in top), top
    # галочка на ветке закрывает все её задания
    grp = next(b.tree.topLevelItem(i) for i in range(b.tree.topLevelItemCount()) if "1-1" in b.tree.topLevelItem(i).text(0))
    grp.setCheckState(0, Qt.CheckState.Checked)
    qapp.processEvents()
    assert all(progress.is_done(q.id) for q in db.season_line("1-1"))
    b.search.setText("2-1-4")
    qapp.processEvents()
    b.select("combat-3")
    b.card.grab()
    assert not errors, errors
