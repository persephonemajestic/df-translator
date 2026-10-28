"""Переносит пары из заявки GitHub в data/community.json (запускает workflow community.yml).
Использование: python tools/community_apply.py event.json  ->  печатает число добавленных строк."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dftranslator.community import merge, parse_issue  # noqa: E402
from dftranslator.datasync import build_manifest  # noqa: E402

event = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
body = (event.get("issue") or {}).get("body") or ""
pairs = parse_issue(body)
changed = merge(ROOT / "data" / "community.json", pairs) if pairs else 0
(ROOT / "data" / "manifest.json").write_text(json.dumps(build_manifest(ROOT / "data"), indent=1) + "\n", encoding="utf-8")
print(f"pairs={len(pairs)} changed={changed}")
out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
if out:
    out.write_text(f"pairs={len(pairs)}\nchanged={changed}\n", encoding="utf-8")
