import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dftranslator.blocks import OcrLine, group_blocks  # noqa: E402
from dftranslator.glossary import Glossary  # noqa: E402
from dftranslator.hotkeys import MOD_ALT, MOD_CONTROL, parse_hotkey  # noqa: E402
from dftranslator.quests import QuestBook  # noqa: E402
from dftranslator.templates import translate_objective  # noqa: E402
from dftranslator.text import clean_text, fmt_int, norm_key  # noqa: E402
from dftranslator.translate import (  # noqa: E402
    ClaudeEngine,
    Engine,
    EngineError,
    GoogleEngine,
    Translator,
)

DATA = ROOT / "data"


@pytest.fixture()
def glossary(tmp_path):
    return Glossary(DATA, tmp_path)


@pytest.fixture()
def book(glossary):
    return QuestBook(glossary)


# ------------------------------------------------------------------- text utils
def test_clean_text_removes_cjk_spaces_keeps_latin():
    assert clean_text("击 败 5 名 敌方士兵") == "击败5名敌方士兵"
    assert clean_text("使用 AKS-74U 击败") == "使用AKS-74U击败"
    assert clean_text("5.45x39mm BT") == "5.45x39mm BT"


def test_norm_key_fullwidth_and_punct():
    assert norm_key("在零号大坝，击败 5 名敌人。") == "在零号大坝,击败5名敌人"
    assert norm_key("  AZ3 ") == "az3"


def test_fmt_int():
    assert fmt_int(30000) == "30 000"
    assert fmt_int("150000") == "150 000"


# -------------------------------------------------------------------- glossary
def test_glossary_exact_and_ui_priority(glossary):
    assert glossary.lookup("零号大坝").ru.startswith("Нулевая плотина")
    assert glossary.lookup("开始游戏").ru == "Начать игру"
    # «头盔» есть и в ui, и в items: для целой строки побеждает ui
    assert glossary.lookup("头盔").ru == "Шлем"


def test_glossary_json_has_no_duplicate_keys_in_a_section():
    dups = []

    def hook(pairs):
        keys = [k for k, _ in pairs]
        dups.extend(k for k in set(keys) if keys.count(k) > 1)
        return dict(pairs)

    for name in ("glossary.json", "quest_names.json"):
        json.loads((DATA / name).read_text(encoding="utf-8"), object_pairs_hook=hook)
    assert dups == [], dups


def test_user_glossary_overrides(tmp_path):
    (tmp_path / "glossary_user.json").write_text(
        json.dumps({"places": {"零号大坝": "Нулевая дамба"}, "quest_names": {"首战": "Первая кровь"}}),
        encoding="utf-8",
    )
    g = Glossary(DATA, tmp_path)
    assert g.lookup("零号大坝").ru == "Нулевая дамба"
    assert g.lookup_quest_name("首战") == "Первая кровь"


def test_protect_and_restore_roundtrip(glossary):
    text = "在零号大坝击败阿萨拉盾兵"
    protected, mapping = glossary.protect(text)
    assert "零号大坝" not in protected and "阿萨拉盾兵" not in protected
    assert len(mapping) == 2
    # имитация движка: перевёл «中文» и оставил токены
    fake = "В Qx1z победить Qx2z"
    out = glossary.restore(fake, mapping)
    assert "Нулевая плотина" in out and "щитовик Асары" in out


def test_restore_tolerates_spacing_and_case(glossary):
    mapping = {1: "ТЕРМИН"}
    assert glossary.restore("a qx 1 Z b", mapping) == "a ТЕРМИН b"


def test_find_terms(glossary):
    terms = glossary.find_terms("前往钻石皇后酒店击败雷斯")
    assert "钻石皇后酒店" in terms and "雷斯" in terms


# ---------------------------------------------------------------------- quests
@pytest.mark.parametrize(
    "zh,expected",
    [
        ("首战", "Первый бой"),
        ("尘归尘,土归土", "Прах к праху"),
        ("尘归尘，土归土", "Прах к праху"),
        ("建造者：基础构建-1", "Строитель: базовая постройка — 1"),
        ("阿萨拉热线-枪匠3", "Горячая линия Асары — оружейник 3"),
        ("大收藏家，入会！", "Великий коллекционер: вступление!"),
    ],
)
def test_quest_names(book, zh, expected):
    assert book.quest_name(zh) == expected


def test_quest_name_unknown_series_suffix(book):
    # номер, которого нет в каталоге, подхватывается через базу
    assert book.quest_name("高耸入云7") == "Заоблачные высоты 7"


def test_quest_name_series_without_number(book):
    assert book.quest_name("博物馆狂想曲") == "Рапсодия музея"
    assert book.quest_name("关山南越") == "Дальний путь на юг"


def test_quest_name_ocr_noise_fuzzy(book):
    # одна ошибочная буква в длинном названии исправляется нечётким совпадением
    assert book.quest_name("尘归尘,土归士") == "Прах к праху"
    # короткие обрывки не угадываем — лучше промолчать, чем перевести не то
    assert book.quest_name("归未") is None


def test_rewards(book):
    assert book.reward("哈夫币x15000") == "Хаавк-коины ×15 000"
    assert book.reward("战斗部门声望x1") == "Репутация боевого отдела ×1"
    assert book.reward("CAR15小改x1") == "CAR15 (лёгкий тюнинг) ×1"
    assert book.reward("G18C满改x1") == "G18C (полный тюнинг) ×1"
    assert book.reward("未知物品x2") is None


def test_objective_db_exact_and_fuzzy(glossary, tmp_path):
    p = tmp_path / "objectives_ru.json"
    p.write_text(
        json.dumps({"在零号大坝任意战区行动中,前往主变电站指定位置进行调查。": "Нулевая плотина: осмотреть указанное место на главной подстанции."}),
        encoding="utf-8",
    )
    book = QuestBook(glossary, p)
    assert book.objective("在零号大坝任意战区行动中,前往主变电站指定位置进行调查。")
    noisy = "在零号大坝任意战区行动中,前往主变电站指定位置进行调杳。"
    assert book.objective(noisy) is not None
    assert book.objective("完全不相关的另一句很长很长的话呀呀呀呀") is None


# ------------------------------------------------------------------- templates
@pytest.mark.parametrize(
    "zh,expected",
    [
        ("在零号大坝任意战区行动中,击败5名敌方士兵。", "Нулевая плотина, любая операция: победить вражеских солдат — 5."),
        ("在巴克什任意战区行动中,击败2名阿萨拉盾兵。 ", "Браккеш, любая операция: победить щитовиков Асары — 2."),
        ("在零号大坝战区行动中,击败1名阿萨拉盾兵。", "Нулевая плотина, любая операция: победить щитовиков Асары — 1."),
        ("在航天基地任意战区行动中,击败3名敌方特战干员。", "Космическая база, любая операция: победить вражеских оперативников — 3."),
        ("从零号大坝任意战区行动中成功撤离1次。", "Нулевая плотина, любая операция: успешно эвакуироваться — 1 раз."),
        ("从巴克什机密行动中成功撤离1次。", "Браккеш, секретная операция: успешно эвакуироваться — 1 раз."),
        (
            "在零号大坝任意战区行动中,成功撤离时单局收益达到30000哈夫币,完成1次。",
            "Нулевая плотина, любая операция: успешно эвакуироваться с доходом за матч не менее 30 000 Хаавк-коинов — 1 раз.",
        ),
        (
            "在长弓溪谷任意战区行动中,成功撤离时当单局收益达到150000哈夫币,完成2次。",
            "Долина Длинного Лука, любая операция: успешно эвакуироваться с доходом за матч не менее 150 000 Хаавк-коинов — 2 раз(а).",
        ),
    ],
)
def test_templates(zh, expected):
    assert translate_objective(zh) == expected


def test_templates_miss():
    assert translate_objective("携带【徽记输液工具】，从战局中成功撤离。") is None


# ---------------------------------------------------------------------- blocks
def _ln(x0, y0, x1, y1, t):
    return OcrLine(x0, y0, x1, y1, t, 0.99)


def test_group_blocks_merges_wrapped_paragraph():
    lines = [
        _ln(100, 100, 700, 124, "在零号大坝任意战区行动中，前往主变电站指定位置进行"),
        _ln(100, 130, 520, 154, "调查并携带情报成功撤离。"),
    ]
    blocks = group_blocks(lines)
    assert len(blocks) == 1
    assert blocks[0].text.endswith("成功撤离。")


def test_group_blocks_keeps_menu_items_separate():
    lines = [
        _ln(50, 100, 150, 124, "战斗部门"),
        _ln(50, 130, 150, 154, "医疗部门"),
        _ln(50, 160, 150, 184, "战术部门"),
    ]
    assert len(group_blocks(lines)) == 3


def test_group_blocks_ignores_non_cjk():
    lines = [_ln(0, 0, 50, 20, "Settings"), _ln(0, 40, 80, 60, "设置")]
    blocks = group_blocks(lines)
    assert [b.text for b in blocks] == ["设置"]


# --------------------------------------------------------------------- hotkeys
def test_parse_hotkey():
    assert parse_hotkey("Ctrl+Alt+T") == (MOD_CONTROL | MOD_ALT, ord("T"))
    assert parse_hotkey("ctrl+alt+f5")[1] == 0x74
    with pytest.raises(ValueError):
        parse_hotkey("T")
    with pytest.raises(ValueError):
        parse_hotkey("Ctrl+Hyper+T")


# --------------------------------------------------------------------- engines
def test_google_parse():
    payload = [[["Привет", "你好", None, None, 1], [" мир", "世界", None, None, 1]], None, "zh-CN"]
    assert GoogleEngine.parse(payload) == "Привет мир"
    with pytest.raises(EngineError):
        GoogleEngine.parse({"bad": 1})


def test_claude_parse_array():
    assert ClaudeEngine.parse_array('Вот: ["а", "б"] ок', 2) == ["а", "б"]
    with pytest.raises(EngineError):
        ClaudeEngine.parse_array('["а"]', 2)
    with pytest.raises(EngineError):
        ClaudeEngine.parse_array("нет массива", 1)


class FakeEngine(Engine):
    name = "fake"

    def __init__(self):
        self.calls = []

    def translate_batch(self, texts, terms):
        self.calls.append(list(texts))
        # возвращаем строку, сохраняя токены
        return [f"<{t}>" for t in texts]


def _translator(glossary, book, tmp_path, engine):
    cfg = {"engine": "fake", "engines": {}}
    tr = Translator(glossary, book, cfg, tmp_path / "cache.json")
    tr._engine, tr._engine_name = engine, "fake"
    return tr


def test_pipeline_layers_and_engine(glossary, book, tmp_path):
    eng = FakeEngine()
    tr = _translator(glossary, book, tmp_path, eng)
    texts = ["开始游戏", "首战", "哈夫币x15000", "在零号大坝任意战区行动中,击败5名敌方士兵。", "完全陌生的句子需要机翻", "Settings"]
    res = tr.translate(texts)
    assert [r.source for r in res] == ["glossary", "quest", "reward", "template", "fake", "skip"]
    assert [r.lore for r in res] == [True, True, True, True, False, False]
    assert eng.calls == [["完全陌生的句子需要机翻"]]  # в движок ушло только неизвестное


def test_pipeline_cache_and_dedup(glossary, book, tmp_path):
    eng = FakeEngine()
    tr = _translator(glossary, book, tmp_path, eng)
    tr.translate(["神秘句子甲", "神秘句子甲"])
    assert eng.calls == [["神秘句子甲"]]  # дубликаты объединены
    tr.translate(["神秘句子甲"])
    assert len(eng.calls) == 1  # второй раз — из кэша
    assert json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))


def test_pipeline_protects_glossary_terms(glossary, book, tmp_path):
    class Echo(Engine):
        name = "echo"
        seen = []

        def translate_batch(self, texts, terms):
            Echo.seen = list(texts)
            return ["Идите в " + t for t in texts]

    tr = _translator(glossary, book, tmp_path, Echo())
    res = tr.translate(["前往钻石皇后酒店并调查神秘装置"])
    assert "钻石皇后酒店" not in Echo.seen[0]
    assert "отель «Бриллиантовая королева»" in res[0].ru


def test_pipeline_engine_error(glossary, book, tmp_path):
    class Broken(Engine):
        name = "broken"

        def translate_batch(self, texts, terms):
            raise EngineError("нет сети")

    tr = _translator(glossary, book, tmp_path, Broken())
    res = tr.translate(["开始游戏", "需要机翻的文本内容"])
    assert res[0].ru == "Начать игру"          # локальный слой работает без сети
    assert res[1].source == "error" and tr.last_error == "нет сети"


def test_qt_key_names_and_validation():
    from dftranslator.hotkeys import format_hotkey, parse_hotkey, qt_key_to_name, validate_bindings

    assert qt_key_to_name(0x54) == "T"
    assert qt_key_to_name(0x01000030) == "F1" and qt_key_to_name(0x0100003B) == "F12"
    assert qt_key_to_name(0x01000021) is None  # Ctrl сам по себе
    assert format_hotkey(True, True, False, False, "T") == "Ctrl+Alt+T"
    parse_hotkey(format_hotkey(False, False, True, True, "PageUp"))
    errs = validate_bindings({"a": "Ctrl+Alt+T", "b": "alt+ctrl+t", "c": "T", "d": "Ctrl+F5"})
    assert "b" in errs and "c" in errs and "a" not in errs and "d" not in errs


def test_updater_versions_and_release_parsing():
    from dftranslator.updater import is_newer, parse_release, parse_version

    assert parse_version("v1.2.10") == (1, 2, 10) and parse_version("мусор") == ()
    assert is_newer("1.0.10", "1.0.9") and is_newer("v2.0", "1.9.9")
    assert not is_newer("1.0.0", "1.0.0") and not is_newer("1.0", "1.0.0") and not is_newer("", "1.0.0")
    rel = parse_release({
        "tag_name": "v1.1.0", "body": "Что нового",
        "assets": [{"name": "x.txt", "browser_download_url": "u0"},
                   {"name": "DFTranslator.exe", "browser_download_url": "u1", "size": 9, "digest": "sha256:ABC"}],
    })
    assert rel and rel.version == "1.1.0" and rel.url == "u1" and rel.sha256 == "abc"
    assert parse_release({"tag_name": "v1", "assets": []}) is None


def test_input_watch_press_without_cursor_move():
    from dftranslator.inputwatch import detect_press

    assert detect_press(100, 150, (5, 5), (5, 5))        # ввод, курсор на месте → нажатие
    assert not detect_press(100, 150, (5, 5), (9, 7))    # курсор двигали → не считаем
    assert not detect_press(100, 100, (5, 5), (5, 5))    # ввода не было


def test_screen_strings_from_real_game():
    from dftranslator.patterns import split_objective_head

    g = Glossary(DATA, None)
    t = Translator(g, QuestBook(g, None), {"engine": "google", "engines": {}}, None)
    expect = {
        "赛季任务：群星": "Сезонный квест: «Созвездие»",
        "已完成 0/2": "Выполнено 0/2",
        "第二阶段：星火": "Этап 2: «Искра»",
        "2-1赛季标准支线": "2-1 · Сезонная побочная линия",
        "爱的咏叹调-4": "Ария любви — 4",
        "赛季剩余7天": "До конца сезона: 7 дн.",
        "任务简报": "Брифинг",
    }
    for zh, ru in expect.items():
        r = t.local(zh)
        assert r and r.ru == ru, (zh, r)
    head = split_objective_head("在巴克什机密/绝密行动中，前往阿萨拉集市民房区域，获取任务物品手作笨弩")
    assert head == ("Браккеш · Секретно / Совсекретно: ", "前往阿萨拉集市民房区域，获取任务物品手作笨弩")


def test_updater_tag_from_redirect():
    from dftranslator.updater import tag_from_location

    assert tag_from_location("https://github.com/a/b/releases/tag/v1.0.2") == "1.0.2"
    assert tag_from_location("https://github.com/a/b/releases") is None


def test_questdb_loads_and_matches():
    from dftranslator.questdb import QuestDB, translate_map

    db = QuestDB(DATA)
    assert len([q for q in db.quests if q.dept != "season"]) == 333
    g = Glossary(DATA, None)
    db.set_names(QuestBook(g, None).quest_name)
    q = db.match_name("电站搜寻")
    assert q and q.dept == "combat" and len(q.image_urls()) == 2
    assert q.image_urls()[0].endswith("combat_department_mission/task3_01.webp")
    assert db.match_name("建造者：基础构違-1").key == 65  # одна ошибка OCR в длинном названии
    assert db.match_name("电站搜导") is None  # короткие названия — только точно
    assert db.get("research-54").images == [1, 2, 4]
    assert "Нулевая плотина (Обычный, Секретно)" == translate_map("零号大坝（常规），零号大坝（机密）")
    items = db.get("combat-41").items()
    assert "Прецизионная карта памяти" in items
    assert [q.id for q in db.search("арбалет")] == ["season-1"] and db.search("Прецизионная")
    # все названия квестов переведены
    assert all(x.name_ru != x.name for x in db.quests), [x.name for x in db.quests if x.name_ru == x.name][:5]


def test_questdb_objectives_feed_translator():
    from dftranslator.questdb import QuestDB

    g = Glossary(DATA, None)
    book = QuestBook(g, None)
    book.add_objectives(QuestDB(DATA).objectives)
    t = Translator(g, book, {"engine": "google", "engines": {}}, None)
    r = t.local("在零号大坝任意战区行动中,前往主变电站指定位置进行调查。")
    assert r and "главной подстанции" in r.ru
    r2 = t.local("在零号大坝任意战区行动中,前往主变电站指定位罝进行调查。")  # OCR перепутал иероглиф
    assert r2 and "подстанции" in r2.ru


def test_data_manifest_is_fresh():
    """Если упал — запустите: python tools/build_manifest.py"""
    from dftranslator.datasync import build_manifest

    stored = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    assert stored == build_manifest(DATA)


def test_datasync_uses_overlay(tmp_path):
    from dftranslator.glossary import Glossary as G

    (tmp_path / "glossary.json").write_text(json.dumps({"ui": {"开始游戏": "СТАРТ"}}, ensure_ascii=False), encoding="utf-8")
    g = G(DATA, None, overlay_dir=tmp_path)
    assert g.lookup("开始游戏").ru == "СТАРТ"


def test_history_and_issue_url():
    from dftranslator.history import History, issue_url

    h = History(limit=2)
    h.add("开始游戏", "Начать игру")
    h.add("仓库", "Склад")
    h.add("开始游戏", "Начать игру")
    h.add("部门", "Отделы")
    assert [e.zh for e in h.entries()] == ["部门", "开始游戏"]
    url = issue_url("o/r", "仓库", "Склад", "Хранилище", "1.0.0")
    assert url.startswith("https://github.com/o/r/issues/new?title=")


def test_free_engines_fall_back(monkeypatch):
    import dftranslator.translate as tr

    class Bad(tr.Engine):
        def __init__(self, cfg=None):
            pass

        def translate_batch(self, texts, terms):
            raise tr.EngineError("429")

    class Good(tr.Engine):
        def __init__(self, cfg=None):
            pass

        def translate_batch(self, texts, terms):
            return [f"RU:{t}" for t in texts]

    monkeypatch.setitem(tr.ENGINES, "google", Bad)
    monkeypatch.setitem(tr.ENGINES, "microsoft", Good)
    g = Glossary(DATA, None)
    t = Translator(g, QuestBook(g, None), {"engine": "google", "engines": {}}, None)
    res = t.translate(["这是一个完全未知的句子"])
    assert res[0].ru.startswith("RU:") and t.last_error is None
    assert t.used_engine == "microsoft"


def test_block_lines_and_labels():
    g = Glossary(DATA, None)
    t = Translator(g, QuestBook(g, None), {"engine": "google", "engines": {}}, None)
    assert t.local("[任务环境]：暂无相关情报").ru == "Обстановка: Сведений пока нет"
    assert t._split_label("[任务简报]：某某某某")[0] == "Брифинг: "
    assert t.local("临时演员").ru == "Статист"


def test_progress_roundtrip(tmp_path):
    from dftranslator.progress import Progress

    p = Progress(tmp_path / "progress.json")
    calls = []
    p.listeners.append(lambda: calls.append(1))
    p.set_done("combat-1", True)
    p.set_many(["season-111", "season-112"], True)
    p2 = Progress(tmp_path / "progress.json")
    assert p2.is_done("combat-1") and p2.is_done("season-112") and len(calls) == 2


def test_season_lines_and_search():
    from dftranslator.questdb import QuestDB

    db = QuestDB(DATA)
    assert len(db.season_line("1-3")) == 5
    assert [q.name for q in db.search("2-1-4")] == ["爱的咏叹调-4"]
    assert db.season_line("02")[0].name == "临时演员"
    assert db.get("combat-3").group() == "长弓溪谷" and db.get("season-1").group() == "02|main"
