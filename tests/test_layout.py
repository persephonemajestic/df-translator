import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dftranslator.layout import Item, place  # noqa: E402


def fake_measure(text, font_px, max_w):
    """Моноширинная модель: ширина символа = 0.55*font, перенос по словам не моделируем."""
    char_w = font_px * 0.55
    per_line = max(1, int(max_w / char_w))
    lines = -(-len(text) // per_line)
    return min(len(text) * char_w, max_w), int(lines * font_px * 1.3)


def item(x0, y0, x1, y1, ru, lore=True):
    return Item("中", ru, x0, y0, x1, y1, line_h=y1 - y0, source="glossary", lore=lore)


def test_short_label_stays_in_place():
    p = place([item(100, 100, 220, 124, "Начать игру")], 1920, 1080, fake_measure)
    assert len(p) == 1
    assert p[0].x <= 100 and p[0].y <= 100
    assert p[0].w >= 190


def test_overlapping_items_are_pushed_down():
    items = [item(100, 100, 220, 124, "Первый"), item(100, 105, 220, 129, "Второй")]
    p = place(items, 1920, 1080, fake_measure)
    assert p[1].y >= p[0].bottom


def test_clamped_to_screen():
    p = place([item(1850, 1060, 1915, 1078, "Длинный перевод у самого края экрана")], 1920, 1080, fake_measure)
    assert p[0].x + p[0].w <= 1920
    assert p[0].y + p[0].h <= 1080


def test_long_text_shrinks_font_or_widens():
    long_ru = "Нулевая плотина, любая операция: успешно эвакуироваться с доходом за матч не менее 150 000 Хаавк-коинов — 2 раза."
    it = item(100, 100, 300, 120, long_ru)
    p = place([it], 1920, 1080, fake_measure, min_font=11, max_font=22)[0]
    assert p.font_px <= 16
    assert p.w > 200


def test_empty_translation_skipped():
    assert place([item(0, 0, 10, 10, "  ")], 800, 600, fake_measure) == []


from dftranslator.layout import place_inplace  # noqa: E402


def test_inplace_covers_original_position():
    p = place_inplace([item(100, 100, 220, 124, "Начать")], 1920, 1080, fake_measure)[0]
    assert abs(p.x - 98) <= 2 and abs(p.y - 98) <= 2
    assert p.w >= 120 and p.h >= 24


def test_inplace_long_text_grows_right_not_over_neighbour():
    a = item(100, 100, 160, 120, "Очень длинный перевод короткой китайской подписи")
    b = item(400, 100, 460, 120, "Сосед")
    pa, pb = place_inplace([a, b], 1920, 1080, fake_measure)
    assert pa.x + pa.w <= pb.x + 2          # не залезли на соседа справа
    assert pa.y <= 100 and pb.y <= 100       # обе остались на своих строках


def test_inplace_grows_down_when_no_room_right():
    a = item(1800, 100, 1900, 120, "Длинный перевод у правого края экрана, который не влезает")
    p = place_inplace([a], 1920, 1080, fake_measure, min_font=9)[0]
    assert p.x + p.w <= 1920 and p.h > 24


def test_inplace_unbreakable_word_widens_plate():
    def measure(text, font_px, max_w):   # одно длинное слово не переносится
        w = len(text) * font_px * 0.55
        return w, int(font_px * 1.3)
    p = place_inplace([item(100, 100, 130, 124, "Спецотдел")], 1920, 1080, measure, min_font=12)[0]
    assert p.w - 4 >= len("Спецотдел") * p.font_px * 0.55 - 1


def test_inplace_short_label_prefers_one_line():
    p = place_inplace([item(100, 100, 150, 124, "Награда за задание")], 1920, 1080, fake_measure)[0]
    assert p.h <= 24 + 8 and p.w > 60      # одна строка, плашка расширилась вправо
