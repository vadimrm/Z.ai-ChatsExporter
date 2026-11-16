# -*- coding: utf-8 -*-
"""Тесты поставки (раунд 19): ОДИН ExportChat.exe (GUI + адаптеры в одном
процессе), без CLI-режима, GUI без PATH, single-instance.

CLI-проверки движков (engine exe, /ver, /list /api, кодировка пайпов,
байт-в-байт идентичность) удалены вместе с самим CLI — API_CONTRACT.md
помечен архивным (AGREEMENTS.md, раунд 19).

Запуск: python frontend\\tests\\test_release.py  (перед этим build\\build.bat)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / "release"
EXE = RELEASE / "ExportChat.exe"
FOR_TESTS = ROOT / "for tests"

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

PASS_COUNT = 0
FAIL_COUNT = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print(f"  PASS  {name}")
    else:
        FAIL_COUNT += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def run_arg(args: list[str], env: dict, timeout: int = 60) -> tuple[int, str, str]:
    """Передать аргументы exe при живом первом экземпляре.

    Ожидание: мьютекс занят — процесс сразу выходит rc 0, вывода нет
    (noconsole-сборка). Если первый экземпляр внезапно умер, аргументы
    НЕ станут «CLI-командой»: экземпляр откроет окно и зависнет до
    таймаута — фиксируем как провал, а не падение теста.
    """
    try:
        res = subprocess.run([str(EXE)] + args, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", env=env,
                             timeout=timeout, creationflags=CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return -1, "", "timeout: экземпляр не завершился (мьютекс свободен?)"
    return res.returncode, res.stdout or "", res.stderr or ""


def check_bundle_modules() -> None:
    """Адаптеры обязаны быть в бандле: их импорт ленивый, «живое окно»
    не доказывает включение. Проверяем TOC PYZ через PyInstaller из
    build-venv; нет venv (сторонняя машина) — проверка пропускается."""
    venv_python = ROOT / "build" / "venv" / "Scripts" / "python.exe"
    if not venv_python.is_file():
        print("      (build-venv не найден — проверка бандла пропущена)")
        return
    script = (
        "import io, os, tempfile\n"
        "from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader\n"
        f"ar = CArchiveReader(r'{EXE}')\n"
        "pyz = [n for n, v in ar.toc.items() if v[4] == 'z'][0]\n"
        "tmp = tempfile.NamedTemporaryFile(suffix='.pyz', delete=False)\n"
        "tmp.write(ar.extract(pyz)); tmp.close()\n"
        "z = ZlibArchiveReader(tmp.name, check_pymagic=False)\n"
        "names = set(z.toc); os.unlink(tmp.name)\n"
        "targets = ['adapter', 'export_chat', 'zcode_export', 'job_runner', 'db_profiles']\n"
        "missing = [t for t in targets if t not in names]\n"
        "print('OK' if not missing else 'MISSING: ' + ', '.join(missing))\n"
    )
    try:
        res = subprocess.run([str(venv_python), "-c", script], capture_output=True,
                             text=True, encoding="utf-8", errors="replace",
                             timeout=120, creationflags=CREATE_NO_WINDOW)
        out = (res.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        out = f"сбой проверки: {exc}"
    check("адаптеры/job_runner/db_profiles в бандле exe",
          out == "OK", out[:200])


def cleanup_runtime_files() -> None:
    """Настройки, созданные экзе при запуске рядом с собой (release/ —
    рабочая папка теста, не состав поставки): убираем до и после прогона,
    чтобы «чистая поставка» не замусоривалась."""
    for name in ("ExportChat.cfg", "ExportChat.cfg.tmp", "config.json"):
        p = RELEASE / name
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def main() -> int:
    cleanup_runtime_files()
    check("ExportChat.exe существует в release/", EXE.is_file(), str(EXE))
    check("db_profiles.cfg лежит в поставке рядом с exe (раунд 19)",
          (RELEASE / "db_profiles.cfg").is_file(), str(RELEASE / "db_profiles.cfg"))
    check("«for tests»: exe, README.txt и db_profiles.cfg на месте",
          (FOR_TESTS / "ExportChat.exe").is_file()
          and (FOR_TESTS / "README.txt").is_file()
          and (FOR_TESTS / "db_profiles.cfg").is_file(), str(FOR_TESTS))
    check("в поставке НЕТ настроек ExportChat.cfg (создаётся при первом старте)",
          not (RELEASE / "ExportChat.cfg").is_file()
          and not (RELEASE / "config.json").is_file(),
          str(RELEASE))
    check_bundle_modules()

    # --- GUI живёт без PATH (чистая машина). --second-instance: тест не
    # конфликтует с возможно запущенным приложением владельца ---
    env = os.environ.copy()
    env["PATH"] = ""
    proc = subprocess.Popen([str(EXE), "--second-instance"], env=env)
    time.sleep(6)
    alive = proc.poll() is None
    check("exe жив через 6 с без PATH", alive, f"код выхода={proc.poll()}")

    if alive:
        # --- CLI-режима нет: аргументы не дают консольного вывода и не
        # «выполняются» — процесс ведёт себя как обычный запуск GUI
        # (мьютекс занят, мгновенный выход rc 0) ---
        rc, out, err = run_arg(["/ver"], env)
        check("аргумент /ver: rc 0 (не CLI-команда)", rc == 0, f"rc={rc}")
        check("аргумент /ver: вывода нет (окно, не CLI)",
              out.strip() == "" and err.strip() == "",
              f"out={out[:120]!r}, err={err[:120]!r}")
        rc, out, err = run_arg(["/zzz-неизвестный", "/api"], env)
        check("неизвестные ключи: rc 0 и без вывода (нет CLI-ошибок)",
              rc == 0 and out.strip() == "" and err.strip() == "",
              f"rc={rc}, out={out[:120]!r}")

        # --- единственный экземпляр: второй запуск сразу выходит (rc 0) ---
        second = subprocess.Popen([str(EXE)], env=env)
        try:
            rc_second = second.wait(timeout=15)
            check("второй экземпляр сразу завершился", rc_second == 0,
                  f"rc={rc_second}")
        except subprocess.TimeoutExpired:
            check("второй экземпляр сразу завершился", False,
                  "не вышел за 15 с — копия не детектируется")
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(second.pid)],
                           capture_output=True, creationflags=CREATE_NO_WINDOW)
        check("первый экземпляр всё ещё жив", proc.poll() is None)

    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                   capture_output=True, creationflags=CREATE_NO_WINDOW)
    cleanup_runtime_files()

    print("-" * 60)
    print(f"Итого: PASS={PASS_COUNT}, FAIL={FAIL_COUNT}")
    for line in FAILURES:
        print(f"  провал: {line}")
    return 1 if FAIL_COUNT else 0


if __name__ == "__main__":
    sys.exit(main())
