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
print("OK", sorted(p.name for p in out.glob("*.png")))
