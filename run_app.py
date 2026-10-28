"""Точка входа (в т.ч. для PyInstaller). Пишет лог и показывает окно с ошибкой, если запуск не удался."""
import faulthandler
import os
import sys
import traceback
from pathlib import Path


def _log_dir() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home() / ".config")
    d = base / "DFTranslator"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _message_box(text: str) -> None:
    if sys.platform.startswith("win"):
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "DF Translator — ошибка", 0x10)  # type: ignore[attr-defined]


_mutex = None  # держим дескриптор до конца работы процесса


def _single_instance(wait_s: float) -> bool:
    """Именованный мьютекс Windows: вторая копия не запускается (иначе конфликт горячих клавиш)."""
    global _mutex
    if not sys.platform.startswith("win"):
        return True
    import ctypes
    import time

    deadline = time.time() + wait_s
    while True:
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\DFTranslator_single_instance")  # type: ignore[attr-defined]
        if ctypes.windll.kernel32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
            return True
        ctypes.windll.kernel32.CloseHandle(_mutex)
        if time.time() >= deadline:
            return False
        time.sleep(0.3)


def main() -> None:
    log_path = _log_dir() / "app.log"
    log = open(log_path, "a", encoding="utf-8", buffering=1)
    # В режиме --windowed у процесса нет консоли: stdout/stderr = None, и библиотеки могут падать на print.
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log
    faulthandler.enable(log)
    if not _single_instance(8.0 if "--updated" in sys.argv else 0.0):
        _message_box("DF Translator уже запущен — ищите значок «译» в трее (возле часов).")
        return
    print("--- старт, Python", sys.version.split()[0], "---", file=log)
    try:
        from dftranslator.app import main as app_main

        app_main()
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001
        tb = traceback.format_exc()
        print(tb, file=log)
        _message_box(f"Программа не запустилась.\n\n{tb[-1500:]}\n\nЛог: {log_path}")
        raise


if __name__ == "__main__":
    main()
