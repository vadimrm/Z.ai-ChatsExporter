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

import os
import queue
import sqlite3
import sys
import threading
from pathlib import Path

import config  # р46: локальные папки/имена копий
import db_profiles  # р65: имена/пути мастер-баз

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
        if kind == "import":
            # р46: импорт не открывает адаптер/мастер через ad.open —
            # только снапшот; ДО общего блока, иначе ad.open(None) падает
            self._import_master_job(job)
            return
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
                # раунд 31: событие помечается режимом задания — результат,
                # пришедший после переключения режима, отбрасывается GUI
                try:
                    self._put("list", ad.list_chats(
                        con, index_db=job.get("index_db") or None),
                        job.get("mode"))
                except AdapterError as exc:
                    self._put("list_error", exc.message, job.get("mode"))
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

    def _import_master_job(self, job: dict) -> None:
        """Раунд 46: импорт мастер-базы в локальную копию (снапшот через
        backup-API SQLite — целостно даже при работающем приложении).
        р65: безопасный алгоритм — tmp-проверка до бэкапов; minimal —
        нет 2-й базы ZCode. {"kind": "import", "mode": …, "master":
        "<путь>", "profiles": {db_profiles}}"""
        mode = job.get("mode", "")
        try:
            local, minimal = import_master(mode, Path(job["master"]),
                                           job.get("profiles"))
        except Exception as exc:
            self._put("import_error", mode, f"{type(exc).__name__}: {exc}")
            return
        self._put("import_done", mode, str(local), minimal)

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
            index_db = job.get("index_db") or None  # 2-я база ZCode (р31)
            try:
                if chat_id == "__single__":
                    result = ad.export_single_file(con, out_dir,
                                                   self._options(job, fmt),
                                                   chat_ids,
                                                   job.get("include_subagents",
                                                           False),
                                                   index_db)
                else:
                    result = ad.export_chat(con, chat_id, out_dir,
                                            self._options(job, fmt), index_db)
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

def import_master(mode: str, master: Path,
                  profiles: dict | None = None) -> tuple[Path, bool]:
    """р65: безопасный импорт мастер-базы (алгоритм владельца + tmp).

    1) имена файлов — из db_profiles.cfg (filename / index_filename);
    2) мастер → локальный <db>.tmp (backup-API, ro); для ZCode индекс
       → свой tmp (поиск: index_paths профиля, затем рядом с мастером);
    3) проверка tmp ЛОКАЛЬНО: есть таблица чатов (session /
       work_sessions). Мусор (например, выбранный tasks-index) → tmp
       удалён, AdapterError «в файле нет таблиц диалогов», локальные
       файлы НЕ ТРОНУТЫ — ни бэкапов, ни отката не требуется;
    4) валидно → ротация бэкапов (≤3: .bak3 стёрт, .bak2→.bak3,
       .bak1→.bak2, рабочий→.bak1 — bak1 всегда самый свежий) и
       os.replace(tmp → рабочее имя); сбой replace → bak1 возвращается.
    Возвращает (локальный путь, minimal): minimal=True — 2-ю базу ZCode
    не нашли или не скопировали (функционал неполный, не блокирует)."""
    if mode not in config.DATA_DIR_NAMES:
        raise ValueError(f"неизвестный режим: {mode}")
    names = _profile_names(mode, profiles)
    chat_table = CHAT_TABLES[mode]
    dst_dir = config.data_dir(mode)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / config.DATA_FILE[mode]
    tmp = dst.with_suffix(".tmp")

    # --- 2) мастер → tmp (не трогаем локальные файлы) ---
    try:
        src_con = sqlite3.connect(f"file:{master.as_posix()}?mode=ro",
                                  uri=True, timeout=5)
        try:
            out = sqlite3.connect(tmp)
            try:
                src_con.backup(out)
            finally:
                out.close()
        finally:
            src_con.close()
    except sqlite3.DatabaseError as exc:
        tmp.unlink(missing_ok=True)
        raise AdapterError(
            f"не удалось прочитать файл как базу SQLite ({exc}): {master}"
        ) from exc

    # --- 3) проверка tmp: таблица чатов есть? локальные не тронуты ---
    index_tmp = (_copy_index_tmp(mode, master, names, profiles)
                 if mode == "zcode" else None)
    try:
        con = sqlite3.connect(tmp)
        try:
            row = con.execute(
                "select 1 from sqlite_master where type='table' and name=?",
                (chat_table,)).fetchone()
        finally:
            con.close()
    except sqlite3.DatabaseError:
        row = None
    if row is None:
        tmp.unlink(missing_ok=True)
        if index_tmp is not None:
            index_tmp.unlink(missing_ok=True)
        label = MODE_LABELS_IMPORT.get(mode, mode)
        raise AdapterError(
            f"В файле нет таблиц диалогов — это не база {label}: {master}")

    # --- 4) ротация бэкапов и атомарная замена ---
    # р68 (владелец): бэкапится ВЕСЬ комплект из конфига — ОБЕ группы
    # (main и second с их wal/shm) ВСЕГДА, в том числе когда 2-ю базу не
    # нашли/не скопировали (minimal): старые локальные файлы 2-й группы
    # не должны оставаться рядом с новой базой без бэкапа
    # р71 (владелец): minimal — только про 2-ю базу ZCode; у AutoClaw
    #     её не бывает — р65-баг: всегда True → жёлтый статус-ложь
    minimal = mode == "zcode" and index_tmp is None
    index_dst = config.local_index_path()
    _rotate_backup(dst, names, "main")
    _rotate_backup(index_dst, names, "second")
    try:
        os.replace(tmp, dst)
    except OSError:
        # сбой на последнем шаге: вернуть свежие бэкапы на место
        for target in (dst, index_dst):
            bak1 = target.with_name(target.name + ".bak1")
            if bak1.is_file() and not target.exists():
                os.replace(bak1, target)
        tmp.unlink(missing_ok=True)
        if index_tmp is not None:
            index_tmp.unlink(missing_ok=True)
        raise
    if index_tmp is not None:
        try:
            os.replace(index_tmp, index_dst)
        except OSError:
            bak1 = index_dst.with_name(index_dst.name + ".bak1")
            if bak1.is_file() and not index_dst.exists():
                os.replace(bak1, index_dst)
            index_tmp.unlink(missing_ok=True)
    return dst, minimal


BACKUP_KEEP = 3  # р65: сколько бэкапов каждого файла держим (владелец)
CHAT_TABLES = {"autoclaw": "work_sessions", "zcode": "session"}
MODE_LABELS_IMPORT = {"autoclaw": "AutoClaw", "zcode": "ZCode"}


def _profile_names(mode: str, profiles: dict | None) -> dict:
    """р67: имена из db_profiles v3 — главный файл, 2-я база (если есть)
    и полный комплект файлов (фолбэк — заводские значения)."""
    section = (profiles or {}).get(mode) or {}
    factory = db_profiles.FACTORY_DOC[mode]
    return {
        "main": section.get("main_file") or factory["main_file"],
        "second": section.get("second_file")
                   or factory.get("second_file"),
        "files": dict(section.get("files") or factory.get("files") or {}),
    }


def _copy_index_tmp(mode: str, master: Path, names: dict,
                    profiles: dict | None = None) -> Path | None:
    """р67: 2-я база ZCode → свой tmp. Путь — по конфигу (относительная
    папка из files против выбранного мастера; варианты путей только у
    главного файла). р74 (владелец): если по конфигу не найдено — ФОЛБЭК
    «рядом с главным файлом» (комплект в одной папке) — грузим оттуда
    МОЛЧА (без ошибки/предупреждения); не нашли нигде → None (minimal)."""
    second = names.get("second")
    if not second:
        return None
    candidates = [
        master.parent / (names["files"].get(second) or ".") / second,
        master.parent / second,                      # р74: фолбэк рядом
    ]
    tmp_i = config.local_index_path().with_suffix(".tmp")
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            src_i = sqlite3.connect(f"file:{candidate.as_posix()}?mode=ro",
                                    uri=True, timeout=5)
            try:
                out_i = sqlite3.connect(tmp_i)
                try:
                    src_i.backup(out_i)
                finally:
                    out_i.close()
            finally:
                src_i.close()
            return tmp_i
        except sqlite3.DatabaseError:
            tmp_i.unlink(missing_ok=True)
            continue
    return None


def _rotate_backup(path: Path, names: dict | None = None,
                   group: str = "main") -> None:
    """р65-р67: ротация бэкапов группы файлов. Список имён — из
    db_profiles v3 (files; владелец: бэкапится весь комплект): группа
    main — главный файл и его спутники (всегда), группа second — 2-я
    база и её спутники (только когда импортируем 2-ю). Каждый файл —
    в свои .bakN (≤ BACKUP_KEEP; .bak1 — самый свежий)."""
    if names and names.get("files"):
        anchor = names.get("second" if group == "second" else "main")
        if not anchor:
            return
        for name in names["files"]:
            if name == anchor or name.startswith(anchor + "-"):
                _rotate_one(path.parent / name)
        return
    # без конфига — прежнее семейство по суффиксам (совместимость)
    for member in (path,
                   path.with_name(path.name + "-wal"),
                   path.with_name(path.name + "-shm")):
        _rotate_one(member)


def _rotate_one(path: Path) -> None:
    """Ротация одного файла: .bak3 стирается, .bak2→.bak3, .bak1→.bak2,
    рабочий → .bak1 (итого ≤ BACKUP_KEEP бэкапов, .bak1 — свежий)."""
    if not path.exists():
        return
    bak3 = path.with_name(path.name + ".bak3")
    bak2 = path.with_name(path.name + ".bak2")
    bak1 = path.with_name(path.name + ".bak1")
    bak3.unlink(missing_ok=True)
    if bak2.exists():
        os.replace(bak2, bak3)
    if bak1.exists():
        os.replace(bak1, bak2)
    os.replace(path, bak1)
