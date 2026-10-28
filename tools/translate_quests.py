"""Переводит цели квестов из data/kkrb_quests.json через настроенный движок + глоссарий.

Результат: data/objectives_ru.json (китайский текст -> русский). Лучше запускать с движком claude:
  set ANTHROPIC_API_KEY=...   python tools/translate_quests.py claude
Потом выборочно проверьте файл глазами — машинный перевод не безошибочен.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dftranslator.config import load_config  # noqa: E402
from dftranslator.glossary import Glossary  # noqa: E402
from dftranslator.quests import QuestBook  # noqa: E402
from dftranslator.translate import Translator  # noqa: E402


def iter_objectives(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "taskObjective" and isinstance(v, list):
                for o in v:
                    if isinstance(o, dict) and o.get("objective"):
                        yield o["objective"]
            else:
                yield from iter_objectives(v)
    elif isinstance(node, list):
        for v in node:
            yield from iter_objectives(v)


def main() -> None:
    src = ROOT / "data" / "kkrb_quests.json"
    if not src.exists():
        sys.exit("Сначала: python tools/sync_kkrb.py")
    cfg = load_config()
    if len(sys.argv) > 1:
        cfg["engine"] = sys.argv[1]
    out_path = ROOT / "data" / "objectives_ru.json"
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    g = Glossary(ROOT / "data", None)
    tr = Translator(g, QuestBook(g, None), cfg, None)
    todo = sorted({t.strip() for t in iter_objectives(json.loads(src.read_text(encoding="utf-8")))} - set(done))
    print(f"К переводу: {len(todo)}")
    for i in range(0, len(todo), 20):
        chunk = todo[i:i + 20]
        for r in tr.translate(chunk):
            if r.source != "error" and r.ru:
                done[r.zh] = r.ru
        out_path.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{min(i + 20, len(todo))}/{len(todo)}")
        if tr.last_error:
            sys.exit(f"Ошибка движка: {tr.last_error}")


if __name__ == "__main__":
    main()
