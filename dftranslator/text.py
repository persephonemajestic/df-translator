"""Мелкие утилиты для работы с китайским текстом после OCR."""
from __future__ import annotations

import re
import unicodedata

CJK_RE = re.compile(r"[㐀-䶿一-鿿]")
_CJK_CLASS = r"㐀-䶿一-鿿　-〿＀-￯"
_SPACE_NEAR_CJK = re.compile(
    rf"(?<=[{_CJK_CLASS}])\s+|\s+(?=[{_CJK_CLASS}])"
)
_WS = re.compile(r"\s+")
_TRAIL_PUNCT = re.compile(r"[。\.．、,，;；!！\s]+$")


def has_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text))


def cjk_ratio(text: str) -> float:
    letters = [c for c in text if not c.isspace()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if CJK_RE.match(c)) / len(letters)


def clean_text(text: str) -> str:
    """Подготовка строки для отправки в переводчик.

    NFKC приводит полноширинные знаки и цифры к обычным, лишние пробелы
    вокруг иероглифов (частый артефакт OCR) убираются, латиница между
    словами сохраняется.
    """
    text = unicodedata.normalize("NFKC", text)
    text = _WS.sub(" ", text).strip()
    text = _SPACE_NEAR_CJK.sub("", text)
    return text


def norm_key(text: str) -> str:
    """Ключ для точного сопоставления: NFKC, без пробелов, без хвостовой пунктуации, нижний регистр."""
    text = unicodedata.normalize("NFKC", text)
    text = _WS.sub("", text)
    text = _TRAIL_PUNCT.sub("", text)
    return text.lower()


def fmt_int(value: int | str) -> str:
    """30000 -> '30 000' (неразрывный пробел)."""
    n = int(value)
    return f"{n:,}".replace(",", " ")
