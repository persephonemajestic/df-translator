"""Qt/onnxruntime иногда падают при выгрузке DLL на выходе из процесса (после того как все тесты
прошли). Завершаем процесс тестов сразу после итогов pytest, минуя выгрузку DLL, с настоящим кодом."""
import os
import sys


def pytest_sessionfinish(session, exitstatus):
    session.config._df_exit = int(exitstatus)


def pytest_unconfigure(config):
    if "PySide6" not in sys.modules:
        return
    code = getattr(config, "_df_exit", 0)
    sys.stdout.flush()
    sys.stderr.flush()
    if sys.platform.startswith("win"):
        import ctypes

        k = ctypes.windll.kernel32
        k.TerminateProcess(k.GetCurrentProcess(), code)
    os._exit(code)
