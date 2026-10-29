"""Снимки окна настроек на разных размерах (для проверки адаптивной раскладки в CI).
Запуск: QT_QPA_PLATFORM=offscreen python tools/ui_shots.py out_dir"""
import copy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dftranslator.config import DEFAULTS  # noqa: E402
from dftranslator.glossary import Glossary  # noqa: E402
from dftranslator.progress import Progress  # noqa: E402
from dftranslator.questdb import QuestDB  # noqa: E402
from dftranslator.quests import QuestBook  # noqa: E402
from dftranslator.questui import ImageLoader, QuestBrowser  # noqa: E402
from dftranslator.settings import SettingsWindow, detect_scale  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "shots")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
detect_scale()
from dftranslator.fonts import load_fonts  # noqa: E402
print("fonts:", load_fonts())
data = ROOT / "data"
tmp = Path(tempfile.mkdtemp())
w = SettingsWindow(copy.deepcopy(DEFAULTS), QIcon())
g = Glossary(data, None)
book = QuestBook(g, None)
db = QuestDB(data)
db.set_names(book.quest_name)
loader = ImageLoader(tmp / "img")
loader.request = lambda url: None
progress = Progress(tmp / "p.json")
b = QuestBrowser(QIcon(), loader, book.reward, progress)
b.name_lookup = book.quest_name
b.set_db(db)
w.install_quest_browser(b)
w.show()
progress.set_many([q.id for q in db.season_line("3-1")], True)


def shot(name):
    for _ in range(5):
        app.processEvents()
    w.grab().save(str(out / f"{name}.png"))


for (W, H) in ((1240, 780), (1110, 810), (820, 600), (560, 460)):
    w.resize(W, H)
    w.go("quests")
    b.select("season-207")
    shot(f"{W}x{H}_quests_card")
    if W < 700:
        b._back_to_list()
        shot(f"{W}x{H}_quests_list")
    b.set_section("season:3")
    b.select("season-312")
    shot(f"{W}x{H}_season3")
    for key in ("home", "engine", "display", "history"):
        w.go(key)
        shot(f"{W}x{H}_{key}")


# ---- перевод «на месте»: синтетический экран игры -> OCR -> перевод -> окно снимка
def ingame_shot():
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

    from dftranslator.blocks import group_blocks
    from dftranslator.colors import sample_colors
    from dftranslator.layout import Item
    from dftranslator.ocr import OcrEngine
    from dftranslator.translate import Translator
    from dftranslator.ui import SnapshotWindow
    import numpy as np

    W, H = 1280, 720
    img = QImage(W, H, QImage.Format.Format_RGB888)
    img.fill(QColor(38, 44, 40))
    p = QPainter(img)
    p.fillRect(0, 0, W, 64, QColor(22, 24, 26))
    p.fillRect(60, 110, 520, 520, QColor(18, 22, 26, 255))
    p.fillRect(640, 110, 580, 300, QColor(196, 176, 128))
    f = QFont("Microsoft YaHei")
    def text(x, y, s, size, color):
        f.setPixelSize(size)
        p.setFont(f)
        p.setPen(QColor(*color))
        p.drawText(x, y, s)
    for i, s in enumerate(["开始游戏", "仓库", "交易行", "特勤处", "部门"]):
        text(40 + i * 150, 42, s, 22, (230, 230, 230))
    text(90, 160, "临时演员", 30, (240, 220, 160))
    text(90, 210, "任务简报", 20, (200, 200, 200))
    text(90, 250, "在巴克什机密/绝密行动中，前往阿萨拉集市附近民房内指定地点，", 17, (220, 220, 220))
    text(90, 276, "超感回溯收音机处所遗留的语音线索", 17, (220, 220, 220))
    text(90, 330, "任务奖励", 20, (200, 200, 200))
    text(90, 370, "哈夫币x200000", 18, (220, 220, 220))
    text(670, 160, "HA-2重型防弹衣（几乎全新）", 22, (30, 30, 30))
    text(670, 210, "蓝室核心 (可透玻璃)", 22, (30, 30, 30))
    text(670, 260, "潮汐监狱-医疗实验区", 22, (30, 30, 30))
    p.end()
    ptr = img.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape(H, img.bytesPerLine())[:, :W * 3].reshape(H, W, 3)[:, :, ::-1].copy()
    img.save(str(out / "ingame_original.png"))
    try:
        lines = OcrEngine(0.5).read(arr, 1.0)
    except Exception as exc:  # noqa: BLE001
        print("OCR недоступен:", exc)
        return
    blocks = group_blocks(lines)
    tr = Translator(g, book, {"engine": "google", "engines": {}}, None)
    res = tr.translate([b.text for b in blocks])
    items = []
    for b, r in zip(blocks, res):
        bg, fg = sample_colors(arr, b.x0, b.y0, b.x1, b.y1)
        items.append(Item(r.zh, r.ru, b.x0, b.y0, b.x1, b.y1, b.line_h, r.source, r.lore, bg, fg))
        print("  ", r.zh, "->", r.ru, bg, fg)
    cfg = copy.deepcopy(DEFAULTS)
    sw = SnapshotWindow(cfg)
    sw.show_snapshot(QRect(0, 0, W, H), img, items, "Любая клавиша или клик — закрыть")
    for _ in range(5):
        app.processEvents()
    sw.grab().save(str(out / "ingame_translated.png"))


ingame_shot()
print("OK", sorted(p.name for p in out.glob("*.png")))
