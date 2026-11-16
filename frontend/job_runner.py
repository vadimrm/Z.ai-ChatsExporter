# -*- coding: utf-8 -*-
"""Фоновые задания экспорта в одном рабочем потоке (AGREEMENTS.md, раунд 19).

Замена subprocess-обёртки engine_client: движки работают в самом процессе
GUI (один exe). Серия «чаты × форматы» — ОДНО задание в ОДНОМ потоке:
не по процессу на каждый чат (30 000 запусков = часы на большой базе).

Правила:
- одно задание за раз (busy); UI-поток никогда не блокируется — результаты
  кладутся в очередь, App забирает их drain() из _poll();
- try/except на каждый элемент серии: неудачный чат пишется в ошибки,
  серия продолжается (устойчивость не ниже изоляции процессами);
- отмена кооперативная (cancel() — флаг, проверяется между элементами;
  закрытие окна — демон-поток умирает вместе с процессом);
- события-кортежи: ("list", rows) / ("list_error", msg) /
  ("progress", done, total) / ("item_done", id, fmt, result) /
  ("item_error", id, fmt, msg) / ("batch_done", ok, errors, cancelled) /
  ("job_error", msg).
"""
from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path

# Исходники: адаптеры лежат в backend/ рядом с frontend/. В замороженном exe
# модули даёт PyInstaller (hiddenimports) — вставка пути тогда безвредна.
_BACKEND = str(Path(__file__).resolve().parents[1] / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from adapter import AdapterError, ExportOptions, adapter_for  # noqa: E402


class JobRunner:
    """Один рабочий поток на всё приложение; задания — словари:

    {"kind": "list",   "mode": "autoclaw|zcode", "db": "<путь>"}
    {"kind": "batch",  "mode", "db", "items": [(chat_id, fmt), …],
     "out_dir": "<путь>", "options": {fmt: {поля ExportOptions}}}
    {"kind": "single", "mode", "db", "formats": [fmt, …],
     "out_dir": "<путь>", "options": {fmt: {…}},
     "chat_ids": [id, …] | None}   # None — все диалоги; список — выбранные (р20)
    """

    def __init__(self, adapter_factory=adapter_for) -> None:
        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._busy = False
        self._cancel = threading.Event()
        self._factory = adapter_factory

    def busy(self) -> bool:
        return self._busy

    def cancel(self) -> None:
        """Кооперативная отмена: текущий элемент доищется, следующие нет."""
        self._cancel.set()

    def submit(self, job: dict) -> None:
        if self._busy:
            return
        self._busy = True
        self._cancel.clear()
        threading.Thread(target=self._worker, args=(job,), daemon=True).start()

    def drain(self) -> list[tuple]:
        """Все готовые события для UI-потока."""
        items: list[tuple] = []
        while True:
            try:
                items.append(self._queue.get_nowait())
            except queue.Empty:
                return items

    # ------------------------------------------------------------- internals

    def _worker(self, job: dict) -> None:
        try:
            self._run(job)
        finally:
            self._busy = False

    def _put(self, *event: object) -> None:
        self._queue.put(event)

    def _run(self, job: dict) -> None:
        kind = job.get("kind", "?")
        try:
            ad = self._factory(job.get("mode", "autoclaw"))
        except Exception as exc:  # импорт адаптера сломан — редкий, но честный случай
            self._put("job_error", f"{type(exc).__name__}: {exc}")
            return
        con = None
        try:
            try:
                con = ad.open(job.get("db"))
            except AdapterError as exc:
                self._put(f"{kind}_error", exc.message)
                return
            except Exception as exc:  # неожиданное (битый файл на уровне sqlite)
                self._put(f"{kind}_error", f"{type(exc).__name__}: {exc}")
                return
            if kind == "list":
                try:
                    self._put("list", ad.list_chats(con))
                except AdapterError as exc:
                    self._put("list_error", exc.message)
            elif kind == "batch":
                self._series(ad, con, job,
                             [(chat_id, fmt) for chat_id, fmt in job["items"]])
            elif kind == "single":
                self._series(ad, con, job,
                             [("__single__", fmt) for fmt in job["formats"]])
            else:
                self._put("job_error", f"неизвестный тип задания: {kind}")
        finally:
            if con is not None:
                try:
                    ad.close(con)
                except Exception:
                    pass

    def _series(self, ad, con, job: dict, items: list[tuple]) -> None:
        total = len(items)
        done = 0
        ok = 0
        errors: list[tuple] = []
        out_dir = job["out_dir"]
        chat_ids = job.get("chat_ids")  # раунд 20: single — только выбранные
        for chat_id, fmt in items:
            if self._cancel.is_set():
                break
            self._put("progress", done, total)
            try:
                if chat_id == "__single__":
                    result = ad.export_single_file(con, out_dir,
                                                   self._options(job, fmt),
                                                   chat_ids)
                else:
                    result = ad.export_chat(con, chat_id, out_dir,
                                            self._options(job, fmt))
                ok += 1
                self._put("item_done", chat_id, fmt, result)
            except AdapterError as exc:
                errors.append((chat_id, fmt, exc.message))
                self._put("item_error", chat_id, fmt, exc.message)
            except Exception as exc:  # баг/сбой — чат в ошибки, серия жива
                message = f"{type(exc).__name__}: {exc}"
                errors.append((chat_id, fmt, message))
                self._put("item_error", chat_id, fmt, message)
            done += 1
        self._put("batch_done", ok, errors, self._cancel.is_set())

    def _options(self, job: dict, fmt: str) -> ExportOptions:
        raw = dict(job["options"][fmt])
        raw["fmt"] = fmt
        return ExportOptions(**raw)
