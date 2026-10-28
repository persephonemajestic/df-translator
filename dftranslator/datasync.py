"""Обновление словаря и базы квестов без обновления программы.

На GitHub лежит data/manifest.json со списком файлов и их SHA-256. Если файл у пользователя
отличается, свежая версия скачивается в %APPDATA%/DFTranslator/data и читается вместо встроенной.
Исправил термин в репозитории — через несколько минут он у всех.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import requests

RAW = "https://raw.githubusercontent.com/{repo}/main/data/{name}"
UA = "DFTranslator-datasync"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(data_dir: Path) -> dict:
    files = {}
    for p in sorted(data_dir.rglob("*.json")):
        rel = p.relative_to(data_dir).as_posix()
        if rel == "manifest.json":
            continue
        files[rel] = sha256_file(p)
    return {"files": files}


def sync(repo: str, bundled: Path, overlay: Path, timeout: float = 15) -> list[str]:
    """Возвращает список обновлённых файлов. Бросает исключение при сетевой ошибке."""
    r = requests.get(RAW.format(repo=repo, name="manifest.json"), headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    manifest = r.json().get("files", {})
    changed: list[str] = []
    for name, sha in manifest.items():
        if ".." in name or name.startswith("/"):
            continue
        local_overlay, local_bundled = overlay / name, bundled / name
        if local_bundled.exists() and sha256_file(local_bundled) == sha:
            if local_overlay.exists():  # встроенный файл уже свежий — скачанная копия не нужна
                local_overlay.unlink()
                changed.append(name)
            continue
        if local_overlay.exists() and sha256_file(local_overlay) == sha:
            continue
        d = requests.get(RAW.format(repo=repo, name=name), headers={"User-Agent": UA}, timeout=timeout)
        d.raise_for_status()
        if hashlib.sha256(d.content).hexdigest() != sha:
            continue  # файл обновился между запросами — заберём в следующий раз
        json.loads(d.content.decode("utf-8"))  # битый JSON не сохраняем
        local_overlay.parent.mkdir(parents=True, exist_ok=True)
        tmp = local_overlay.with_suffix(".part")
        tmp.write_bytes(d.content)
        os.replace(tmp, local_overlay)
        changed.append(name)
    return changed
