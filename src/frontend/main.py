# -*- coding: utf-8 -*-
"""Точка входа GUI: единственный экземпляр, DPI-настройка, главное окно.

Один экземпляр (AGREEMENTS.md раунд 3 №4): повторный запуск не создаёт
копию — существующее окно выводится на передний план. Ключ --second-instance
обходит проверку: для сознательных фоновых копий (2-й этап) и тестов.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

BRAND = "Z.ai Chats Exporter by Vadim R.M."
MUTEX_NAME = "Local\\Z.aiChatsExporterByVadimRM"
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9


def _enable_dpi_awareness() -> None:
    """Чёткость текста при масштабе 125–150 % (GUI_PLAN.md §1.5.4)."""
    if os.name != "nt":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _acquire_mutex() -> bool:
    """Захват мьютекса. True — это первый экземпляр; False — уже работает другой.

    Мьютекс создаётся всегда (даже фоновыми копиями с --second-instance) —
    это регистрация экземпляра, а не только проверка.
    """
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW(None, False, MUTEX_NAME)
        return kernel32.GetLastError() != ERROR_ALREADY_EXISTS
    except Exception:
        return True


def _activate_existing_window() -> bool:
    """Поиск окна первого экземпляра по заголовку и вывод на передний план."""
    if os.name != "nt":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        found: list[int] = []

        @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
        def callback(hwnd, _lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if buf.value.startswith(BRAND):
                    found.append(hwnd)
                    return 0
            return 1

        user32.EnumWindows(callback, None)
        if not found:
            return False
        hwnd = found[0]
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        return True
    except Exception:
        return False


def main() -> int:
    primary = _acquire_mutex()
    if not primary and "--second-instance" not in sys.argv:
        _activate_existing_window()
        return 0
    _enable_dpi_awareness()
    import tkinter as tk

    from app import App

    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
