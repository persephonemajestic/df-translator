"""Пересобирает data/manifest.json (запускать после любой правки в data/). Тест проверяет, что он свежий."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dftranslator.datasync import build_manifest  # noqa: E402

out = ROOT / "data" / "manifest.json"
out.write_text(json.dumps(build_manifest(ROOT / "data"), indent=1) + "\n", encoding="utf-8")
print("OK", out)
