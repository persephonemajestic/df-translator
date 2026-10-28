"""Qt иногда падает при завершении интерпретатора (уборка окон/потоков после тестов),
хотя все тесты прошли. Завершаем процесс сразу после итогов pytest с его настоящим кодом."""
import os
import sys


def pytest_sessionfinish(session, exitstatus):
    session.config._df_exit = int(exitstatus)


def pytest_unconfigure(config):
    if "PySide6" in sys.modules:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(getattr(config, "_df_exit", 0))
