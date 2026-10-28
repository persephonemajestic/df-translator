"""Скачивает квесты с kkrb.net в data/kkrb_quests.json (вежливо: пауза между запросами).

Сайт ведёт Key725 — прежде чем публиковать производные данные, спросите разрешения.
"""
import json
import sys
import time
from pathlib import Path

import requests

BASE = "https://www.kkrb.net"
DEPARTMENTS = ["Combat", "Medical", "Tactical", "Logistics", "Research", "GTI"]
OUT = Path(__file__).resolve().parent.parent / "data" / "kkrb_quests.json"


def main() -> None:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (DFTranslator quest sync)",
        "Referer": BASE + "/?viewpage=overview",
        "X-Requested-With": "XMLHttpRequest",
    })
    s.get(BASE + "/?viewpage=overview", timeout=30)
    out = {}
    for dep in DEPARTMENTS:
        r = s.post(BASE + "/getMissionGuidanceData", data={"department": f"{dep}_Department_Mission"}, timeout=30)
        j = r.json()
        if j.get("code") not in (0, 200, None) and "data" not in j:
            print(dep, "ошибка:", j, file=sys.stderr)
            continue
        out[dep] = j.get("data", j)
        print(dep, "ok")
        time.sleep(1.5)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Сохранено:", OUT)


if __name__ == "__main__":
    main()
