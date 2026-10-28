"""Скачивает квесты с kkrb.net в data/kkrb_quests.json (компактный формат, см. ниже).

Запускается в GitHub Actions (workflow «Sync kkrb») раз в неделю и при изменении этого файла.
Сайт ведёт Key725 — запросов немного и с паузами.

Формат: {"titles": {отдел: заголовок}, "required": {отдел: [...]},
         "quests": [{d, g, k, p, n, t, m, c, f, o:[цели], r:[награды], i:[картинки]}]}
"""
import json
import sys
import time
from pathlib import Path

import requests

BASE = "https://www.kkrb.net"
DEPTS = {"Combat": "combat", "Medical": "medical", "Tactical": "tactical",
         "Logistics": "logistics", "Research": "research", "GTI": "season"}
IMG = "https://images.kkrb.net/image/department/guidance/"
OUT = Path(__file__).resolve().parent.parent / "data" / "kkrb_quests.json"


def fetch(s: requests.Session, dep: str) -> dict:
    for attempt in range(3):
        r = s.post(BASE + "/getMissionGuidanceData", data={"department": f"{dep}_Department_Mission"}, timeout=30)
        if r.status_code != 200:
            print(dep, "HTTP", r.status_code, r.text[:300].replace("\n", " "), file=sys.stderr)
            time.sleep(5 * (attempt + 1))
            continue
        try:
            j = r.json()
        except ValueError:
            print(dep, "не JSON:", r.text[:300].replace("\n", " "), file=sys.stderr)
            time.sleep(5 * (attempt + 1))
            continue
        if j.get("code") == 1 and isinstance(j.get("data"), dict):
            return j["data"]
        print(dep, "ответ:", str(j)[:200], file=sys.stderr)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"kkrb не отдал {dep}")


def compact(code: str, d: dict) -> list[dict]:
    lines = d.get("departmentMissionLine") or []
    groups = {"main": lines} if isinstance(lines, list) else lines
    out = []
    for g, arr in groups.items():
        for q in arr or []:
            imgs = [x["imageUrl"] for x in (q.get("taskGuidance") or []) if x.get("imageUrl")]
            out.append({
                "d": code, "g": g, "k": q.get("key"), "p": q.get("parent"), "n": q.get("taskName", ""),
                "t": q.get("taskType", ""), "m": q.get("taskMap", ""), "c": q.get("taskCategory", ""),
                "f": q.get("taskForced") or "",
                "o": [x.get("objective", "") for x in (q.get("taskObjective") or [])],
                "r": [x.get("reward", "") for x in (q.get("taskReward") or [])],
                "i": [u[len(IMG):] if u.startswith(IMG) else u for u in imgs],
            })
    return out


def main() -> None:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (DFTranslator quest sync; github.com/persephonemajestic/df-translator)",
        "Referer": BASE + "/?viewpage=overview",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    s.get(BASE + "/?viewpage=overview", timeout=30)
    result = {"titles": {}, "required": {}, "quests": []}
    for dep, code in DEPTS.items():
        d = fetch(s, dep)
        result["titles"][code] = d.get("departmentMissionTitle", "")
        if d.get("departmentMissionRequiredItem"):
            result["required"][code] = d["departmentMissionRequiredItem"]
        result["quests"].extend(compact(code, d))
        print(code, "ok", file=sys.stderr)
        time.sleep(2)
    if len(result["quests"]) < 200:
        raise RuntimeError(f"Слишком мало квестов: {len(result['quests'])}")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=0), encoding="utf-8")
    print("Сохранено:", OUT, len(result["quests"]), "квестов", file=sys.stderr)


if __name__ == "__main__":
    main()
