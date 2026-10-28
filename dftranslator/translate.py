"""Конвейер перевода: локальные слои -> кэш -> машинный перевод с глоссарием."""
from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .glossary import Glossary
from .quests import QuestBook
from .patterns import compose, split_objective_head
from .templates import translate_objective
from .text import clean_text, has_cjk

try:  # requests нужен только для сетевых движков
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

USER_AGENT = "DFTranslator/1.0 (+screen translator for Delta Force CN)"


class EngineError(RuntimeError):
    pass


@dataclass
class Result:
    zh: str
    ru: str
    source: str          # glossary | quest | reward | template | objective | cache | <engine> | error
    lore: bool = False   # True — перевод из выверенных слоёв, не машинный


# --------------------------------------------------------------------------- engines
class Engine:
    name = "base"
    uses_placeholders = True

    def translate_batch(self, texts: list[str], terms: list[dict[str, str]]) -> list[str]:
        raise NotImplementedError


class GoogleEngine(Engine):
    """Бесплатный веб-эндпоинт Google Translate (неофициальный, без ключа)."""

    name = "google"
    URL = "https://translate.googleapis.com/translate_a/single"

    def __init__(self, cfg: dict | None = None):
        self.session = requests.Session() if requests else None
        if self.session:
            self.session.headers["User-Agent"] = USER_AGENT

    @staticmethod
    def parse(payload) -> str:
        try:
            return "".join(seg[0] for seg in payload[0] if seg and seg[0])
        except (TypeError, IndexError, KeyError) as exc:
            raise EngineError(f"Неожиданный ответ Google: {exc}") from exc

    def _one(self, text: str) -> str:
        params = {"client": "gtx", "sl": "zh-CN", "tl": "ru", "dt": "t"}
        try:
            if len(text) > 700:
                r = self.session.post(self.URL, params=params, data={"q": text}, timeout=10, allow_redirects=False)
            else:
                r = self.session.get(self.URL, params={**params, "q": text}, timeout=10, allow_redirects=False)
            if r.status_code in (429, 302, 303):  # Google отправляет на /sorry — лимит для этого IP
                raise EngineError("Google временно ограничил запросы с вашего IP (429)")
            r.raise_for_status()
            return self.parse(r.json())
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"Google Translate недоступен: {exc}") from exc

    def translate_batch(self, texts, terms):
        if not self.session:
            raise EngineError("Не установлен пакет requests")
        # Одним запросом на весь экран (строки через перевод строки) — так Google реже ограничивает.
        joined = "\n".join(texts)
        out = self._one(joined).split("\n")
        if len(out) == len(texts):
            return [o.strip() for o in out]
        return [self._one(t) for t in texts]  # не совпало число строк — по одной, последовательно


class MicrosoftEngine(Engine):
    """Бесплатный переводчик Microsoft (тот же, что встроен в браузер Edge), без ключа."""

    name = "microsoft"
    AUTH = "https://edge.microsoft.com/translate/auth"
    URL = "https://api-edge.cognitive.microsofttranslator.com/translate"
    _token: str = ""
    _token_ts: float = 0.0
    _lock = threading.Lock()

    def __init__(self, cfg: dict | None = None):
        self.session = requests.Session() if requests else None
        if self.session:
            self.session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edg/130.0"

    def _get_token(self) -> str:
        import time

        with MicrosoftEngine._lock:
            if not MicrosoftEngine._token or time.time() - MicrosoftEngine._token_ts > 480:
                r = self.session.get(self.AUTH, timeout=10)
                r.raise_for_status()
                MicrosoftEngine._token, MicrosoftEngine._token_ts = r.text.strip(), time.time()
            return MicrosoftEngine._token

    def translate_batch(self, texts, terms):
        if not self.session:
            raise EngineError("Не установлен пакет requests")
        try:
            token = self._get_token()
            out: list[str] = []
            for i in range(0, len(texts), 50):
                chunk = texts[i:i + 50]
                r = self.session.post(
                    self.URL, params={"from": "zh-Hans", "to": "ru", "api-version": "3.0"},
                    headers={"Authorization": f"Bearer {token}"},
                    json=[{"Text": t} for t in chunk], timeout=15,
                )
                r.raise_for_status()
                out += [item["translations"][0]["text"] for item in r.json()]
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"Microsoft Translator недоступен: {exc}") from exc
        if len(out) != len(texts):
            raise EngineError("Microsoft вернул другое число строк")
        return out


class DeepLEngine(Engine):
    name = "deepl"

    def __init__(self, cfg: dict):
        self.key = (cfg or {}).get("api_key", "")
        if not self.key:
            raise EngineError("Для DeepL нужен api_key (config.json или переменная DEEPL_API_KEY)")
        self.url = (
            "https://api-free.deepl.com/v2/translate"
            if self.key.endswith(":fx")
            else "https://api.deepl.com/v2/translate"
        )

    def translate_batch(self, texts, terms):
        try:
            r = requests.post(
                self.url,
                headers={"Authorization": f"DeepL-Auth-Key {self.key}", "User-Agent": USER_AGENT},
                json={"text": texts, "source_lang": "ZH", "target_lang": "RU"},
                timeout=20,
            )
            r.raise_for_status()
            out = [t["text"] for t in r.json()["translations"]]
        except Exception as exc:
            raise EngineError(f"DeepL: {exc}") from exc
        if len(out) != len(texts):
            raise EngineError("DeepL вернул другое число строк")
        return out


CLAUDE_SYSTEM = (
    "Ты переводчик интерфейса и квестов китайской версии игры Delta Force (三角洲行动, Hawk Ops) "
    "с китайского на русский. Мир игры: частная военная корпорация Хаавк (Haavk), мятежная Гвардия "
    "Асары (Ahsarah Guard) и миротворцы GTI; режим «Опасные операции» — экстракшн-шутер на картах "
    "Нулевая плотина, Долина Длинного Лука, Космическая база, Браккеш. "
    "Правила: 1) переводи точно, кратко и естественно, в стиле игрового интерфейса; "
    "2) термины из поля glossary используй строго как заданы; "
    "3) числа, латиницу, названия оружия, патронов и моделей оставляй как есть; "
    "4) если строка — мусор распознавания, верни её без изменений; "
    "5) ответ — ТОЛЬКО JSON-массив строк, столько же и в том же порядке, что в lines, без пояснений."
)


class ClaudeEngine(Engine):
    """Claude API: лучший вариант для лора — глоссарий передаётся прямо в запрос."""

    name = "claude"
    uses_placeholders = False
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, cfg: dict):
        self.key = (cfg or {}).get("api_key", "")
        self.model = (cfg or {}).get("model", "claude-haiku-5-5")
        if not self.key:
            raise EngineError("Для Claude нужен api_key (config.json или переменная ANTHROPIC_API_KEY)")

    @staticmethod
    def parse_array(text: str, expected: int) -> list[str]:
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            raise EngineError("Claude вернул ответ не в формате JSON-массива")
        try:
            arr = json.loads(text[start : end + 1])
        except ValueError as exc:
            raise EngineError(f"Не удалось разобрать ответ Claude: {exc}") from exc
        if not isinstance(arr, list) or len(arr) != expected or not all(isinstance(x, str) for x in arr):
            raise EngineError("Claude вернул неверное число строк")
        return arr

    def translate_batch(self, texts, terms):
        glossary: dict[str, str] = {}
        for t in terms:
            glossary.update(t)
        payload = {"glossary": glossary, "lines": texts}
        body = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": 0,
            "system": CLAUDE_SYSTEM,
            "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        }
        try:
            r = requests.post(
                self.URL,
                headers={
                    "x-api-key": self.key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                    "User-Agent": USER_AGENT,
                },
                json=body,
                timeout=40,
            )
            r.raise_for_status()
            content = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        except Exception as exc:
            raise EngineError(f"Claude API: {exc}") from exc
        return self.parse_array(content, len(texts))


ENGINES = {"google": GoogleEngine, "microsoft": MicrosoftEngine, "deepl": DeepLEngine, "claude": ClaudeEngine}
FREE_FALLBACK = {"google": "microsoft", "microsoft": "google"}  # бесплатные движки подстраховывают друг друга


def build_engine(name: str, cfg: dict) -> Engine:
    cls = ENGINES.get(name)
    if not cls:
        raise EngineError(f"Неизвестный движок: {name}")
    return cls((cfg.get("engines") or {}).get(name, {}))


# ------------------------------------------------------------------------- pipeline
class Cache:
    def __init__(self, path: Path | None, limit: int = 20000):
        self.path = path
        self.limit = limit
        self.data: dict[str, str] = {}
        self._dirty = False
        self._lock = threading.Lock()
        if path and path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.data = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def put(self, key: str, value: str) -> None:
        with self._lock:
            if len(self.data) >= self.limit:
                self.data.pop(next(iter(self.data)))
            self.data[key] = value
            self._dirty = True

    def clear(self) -> int:
        with self._lock:
            n = len(self.data)
            self.data.clear()
            self._dirty = True
        self.flush()
        return n

    def flush(self) -> None:
        if not (self.path and self._dirty):
            return
        with self._lock:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=0), encoding="utf-8")
            self._dirty = False


class Translator:
    def __init__(self, glossary: Glossary, quests: QuestBook, cfg: dict, cache_path: Path | None = None):
        self.g = glossary
        self.q = quests
        self.cfg = cfg
        self.cache = Cache(cache_path)
        self._engine: Engine | None = None
        self._engine_name: str | None = None
        self.last_error: str | None = None

    # -- engine management
    @property
    def engine_name(self) -> str:
        return self.cfg.get("engine", "google")

    def set_engine(self, name: str) -> None:
        self.cfg["engine"] = name
        self._engine = None

    def _get_engine(self) -> Engine:
        if self._engine is None or self._engine_name != self.engine_name:
            self._engine = build_engine(self.engine_name, self.cfg)
            self._engine_name = self.engine_name
        return self._engine

    # -- local layers
    def local(self, text: str, _depth: int = 0) -> Result | None:
        hit = self.g.lookup(text)
        if hit:
            return Result(text, hit.ru, "glossary", True)
        name = self.q.quest_name(text)
        if name:
            return Result(text, name, "quest", True)
        reward = self.q.reward(text)
        if reward:
            return Result(text, reward, "reward", True)
        obj = self.q.objective(text)
        if obj:
            return Result(text, obj, "objective", True)
        tmpl = translate_objective(text)
        if tmpl:
            return Result(text, tmpl, "template", True)
        if _depth < 2:
            def part(t: str) -> str | None:
                r = self.local(t, _depth + 1)
                return r.ru if r else None

            comp = compose(text, part)
            if comp:
                return Result(text, comp, "glossary", True)
            head = split_objective_head(clean_text(text))
            if head:
                rest = self.local(head[1], _depth + 1)
                if rest:
                    return Result(text, head[0] + rest.ru, "template", True)
        return None

    _LABEL_RE = re.compile(r"^[\[【［]?\s*([^\]】］:：]{1,10}?)\s*[\]】］]?\s*[:：]\s*(.+)$")

    def _split_label(self, text: str) -> tuple[str, str] | None:
        """«[任务简报]：塔马齐格特…» -> («Брифинг: », «塔马齐格特…»), если подпись известна."""
        m = self._LABEL_RE.match(text)
        if not m or not has_cjk(m.group(2)):
            return None
        hit = self.local(m.group(1), 2)
        return (hit.ru + ": ", m.group(2)) if hit else None

    # -- main entry
    def translate(self, texts: list[str]) -> list[Result]:
        self.last_error = None
        results: list[Result | None] = [None] * len(texts)
        pending: dict[str, list[int]] = {}
        prefixes: dict[int, str] = {}
        for i, raw in enumerate(texts):
            if not has_cjk(raw):
                results[i] = Result(raw, raw, "skip", False)
                continue
            local = self.local(raw)
            if local:
                results[i] = local
                continue
            clean = clean_text(raw)
            head = split_objective_head(clean) or self._split_label(clean)
            if head:  # карта и режим / подпись поля — точно, остальное переводит движок
                prefixes[i] = head[0]
                clean = head[1]
            cached = self.cache.get(clean)
            if cached:
                results[i] = Result(raw, prefixes.get(i, "") + cached, "cache", False)
                continue
            pending.setdefault(clean, []).append(i)

        if pending:
            cleaned = list(pending)
            try:
                translated = self._machine(cleaned)
            except EngineError as exc:
                self.last_error = str(exc)
                translated = None
            for n, clean in enumerate(cleaned):
                for idx in pending[clean]:
                    if translated is None:
                        results[idx] = Result(texts[idx], "", "error", False)
                    else:
                        results[idx] = Result(texts[idx], prefixes.get(idx, "") + translated[n], self.engine_name, False)
                if translated is not None and translated[n]:
                    self.cache.put(clean, translated[n])
            self.cache.flush()
        return [r for r in results if r is not None]  # type: ignore[misc]

    def _machine(self, cleaned: list[str]) -> list[str]:
        import time

        primary = self.engine_name
        order = [primary] + ([FREE_FALLBACK[primary]] if primary in FREE_FALLBACK else [])
        # Движок, который недавно упёрся в лимит, на 20 минут пропускаем, чтобы не ждать его каждый раз.
        skip_until = getattr(self, "_skip_until", {})
        live = [n for n in order if skip_until.get(n, 0) < time.time()] or order
        last_exc: EngineError | None = None
        for name in live:
            try:
                engine = self._get_engine() if name == primary else build_engine(name, self.cfg)
                out = self._run_engine(engine, cleaned)
                self.used_engine = name
                return out
            except EngineError as exc:
                last_exc = exc
                skip_until[name] = time.time() + 20 * 60
                self._skip_until = skip_until
        raise last_exc or EngineError("Нет доступного движка перевода")

    def _run_engine(self, engine: Engine, cleaned: list[str]) -> list[str]:
        if engine.uses_placeholders:
            protected = [self.g.protect(t) for t in cleaned]
            out = engine.translate_batch([p[0] for p in protected], [])
            if len(out) != len(cleaned):
                raise EngineError("Движок вернул другое число строк")
            return [self.g.restore(o, p[1]) for o, p in zip(out, protected)]
        terms = [self.g.find_terms(t) for t in cleaned]
        return engine.translate_batch(cleaned, terms)
