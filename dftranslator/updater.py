"""Автообновление через GitHub Releases (без Qt — логика тестируется отдельно).

Схема для одиночного .exe: новый файл скачивается рядом со старым как DFTranslator.exe.new,
старый переименовывается в .old (Windows разрешает переименовать запущенный exe), новый встаёт на
его место и запускается. .old удаляется при следующем старте.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

ASSET_NAME = "DFTranslator.exe"
API = "https://api.github.com/repos/{repo}/releases/latest"
UA = "DFTranslator-updater"


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.10' -> (1, 2, 10); мусор -> ()."""
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)", text or "")
    return tuple(int(p) for p in m.group(1).split(".")) if m else ()


def is_newer(remote: str, local: str) -> bool:
    r, l = parse_version(remote), parse_version(local)
    if not r:
        return False
    n = max(len(r), len(l))
    return r + (0,) * (n - len(r)) > l + (0,) * (n - len(l))


@dataclass
class ReleaseInfo:
    version: str
    notes: str
    url: str
    size: int
    sha256: str | None


def parse_release(payload: dict) -> ReleaseInfo | None:
    for a in payload.get("assets") or []:
        if a.get("name") == ASSET_NAME and a.get("browser_download_url"):
            digest = a.get("digest") or ""
            return ReleaseInfo(
                version=str(payload.get("tag_name", "")).lstrip("vV"),
                notes=(payload.get("body") or "").strip(),
                url=a["browser_download_url"],
                size=int(a.get("size") or 0),
                sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None,
            )
    return None


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def exe_path() -> Path:
    return Path(sys.executable)


def tag_from_location(location: str) -> str | None:
    """'https://github.com/o/r/releases/tag/v1.0.2' -> '1.0.2'."""
    m = re.search(r"/releases/tag/v?([^/?#]+)", location or "")
    return m.group(1) if m else None


def fetch_latest(repo: str) -> ReleaseInfo | None:
    """Узнаёт последнюю версию без GitHub API (у API лимит 60 запросов в час на IP — у провайдеров
    с общим IP он быстро кончается). Используются обычные ссылки github.com, у них такого лимита нет."""
    headers = {"User-Agent": UA}
    r = requests.get(f"https://github.com/{repo}/releases/latest", headers=headers, allow_redirects=False, timeout=15)
    if r.status_code in (301, 302, 303, 307, 308):
        version = tag_from_location(r.headers.get("Location", ""))
    elif r.status_code == 404:
        return None  # релизов ещё нет
    else:
        r.raise_for_status()
        version = None
    if not version:
        return None
    url = f"https://github.com/{repo}/releases/download/v{version}/{ASSET_NAME}"
    head = requests.head(url, headers=headers, allow_redirects=True, timeout=15)
    if head.status_code != 200:
        return None  # релиз создан, но exe ещё собирается
    notes = ""
    try:
        n = requests.get(f"https://raw.githubusercontent.com/{repo}/v{version}/RELEASE_NOTES.md", headers=headers, timeout=10)
        if n.status_code == 200:
            notes = n.text.strip()
    except requests.RequestException:
        pass
    size = int(head.headers.get("Content-Length") or 0)
    return ReleaseInfo(version=version, notes=notes, url=url, size=size, sha256=None)


def download(info: ReleaseInfo, target: Path, progress: Callable[[float], None] | None = None) -> Path:
    tmp = target.with_name(target.name + ".part")
    h = hashlib.sha256()
    with requests.get(info.url, headers={"User-Agent": UA}, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or info.size or 0)
        done = 0
        with tmp.open("wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)
    if info.sha256 and h.hexdigest() != info.sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Контрольная сумма файла обновления не совпала")
    if tmp.stat().st_size < 5_000_000:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Скачанный файл слишком мал — похоже на ошибку")
    with tmp.open("rb") as f:
        if f.read(2) != b"MZ":  # заголовок любого Windows-exe
            tmp.unlink(missing_ok=True)
            raise RuntimeError("Скачанный файл не похож на программу")
    os.replace(tmp, target)
    return target


def staging_path() -> Path:
    cur = exe_path()
    return cur.with_name(cur.name + ".new")


def can_write_here() -> bool:
    try:
        probe = exe_path().with_name(".write_test")
        probe.write_bytes(b"1")
        probe.unlink()
        return True
    except OSError:
        return False


def apply_update(new_file: Path) -> None:
    """Подменяет запущенный exe новым и стартует его. Вызывающий после этого закрывает программу."""
    cur = exe_path()
    old = cur.with_name(cur.name + ".old")
    old.unlink(missing_ok=True)
    os.replace(cur, old)
    try:
        os.replace(new_file, cur)
    except OSError:
        os.replace(old, cur)  # откат
        raise
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"  # иначе onefile-загрузчик возьмёт распакованное старое окружение
    flags = 0x00000008 | 0x00000200 if sys.platform.startswith("win") else 0  # DETACHED | NEW_PROCESS_GROUP
    subprocess.Popen([str(cur), "--tray", "--updated"], env=env, creationflags=flags, close_fds=True)


def cleanup_leftovers() -> None:
    if not is_frozen():
        return
    cur = exe_path()
    for suffix in (".old", ".part"):
        p = cur.with_name(cur.name + suffix)
        for _ in range(5):
            try:
                p.unlink(missing_ok=True)
                break
            except OSError:
                time.sleep(1)
