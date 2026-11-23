#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Адаптер ZCode: чтение db.sqlite (только на чтение) и экспорт чатов
в Markdown, TXT и JSON (AGREEMENTS.md, раунд 19).

Было CLI-движком с /api-контрактом; после слияния в один exe — модуль
с классом ZCodeAdapter (интерфейс — backend/adapter.py). Отличия от
AutoClaw-адаптера: таблицы session/message/part, имена ZC-*, папки
проектов (последний компонент session.directory), опция служебных
файлов не поддерживается (игнорируется). База открывается только на
чтение; если она занята приложением ZCode, копируется (db+wal+shm) во
временный каталог и читается копия (каталог убирает close()).
Репозиторий (GUI): github.com/vadimrm/Z.ai-ChatsExporter; материнский
CLI-проект: github.com/vadimrm/AutoClaw.Z.ai-ExportChat
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from adapter import AdapterError, ExportOptions

LANG = "ru"

# р63 (я4): TOOL_IN_MAX (фикс 1200 для входа инструмента) убран — вызов
# обрезается тем же полем «Максимальная длина, литер», что и результат

LABELS = {
    "ru": {
        "session": "Сессия",
        "directory": "Каталог",
        "created": "Создана",
        "updated": "Обновлена",
        "messages": "Сообщений",
        # р81 (п.2): пояснение формата «N / M (вопросы/ответы)»
        "messages_qa": " (вопросы/ответы)",
        "you": "Вы",
        "system": "ZCode",
        "llm_unknown": "LLM",
        "context_copy": "Контекст",
        # р81 (п.1): «Харнесс-ядро» — версия встроенного ядра zcode.cjs
        # (session.version), а не приложения ZCode Desktop
        "harness": "Харнесс-ядро",
        "project": "Проект",
        "chat": "Чат",
        "files_line": "Файлы",
        "files_stats": "вложено {n}, готово к скачиванию {m}",
        "files_attached": "вложено {n}",
        "models": "Модели",
        "chat_type": "Тип",
        "none": "—",
        "attached": "📎 Вложено:",
        "unit_kb": "КБ",
        "unit_b": "Б",
        "tools": "Инструменты",
        "call": "Вызов",
        "result": "Результат",
        "reasoning": "Промежуточные реплики",
        # р62 (я2): строки токенов в шапке — формат владельца
        "h_context": "Контекст чата",
        "h_compact": "Автосжатие при",
        "h_spent": "Всего израсходовано",
        "exported": "Экспорт",
        "truncated": "… (обрезано, всего {size})",
        "empty_request": "[пустой запрос]",
        "db": "База:",
        "done": "Готово:",
        "conversation": "Диалог:",
        "all_chats": "Все диалоги ZCode",
        "selected_chats": "Выбранные диалоги ZCode",
        "new_dialog": "Новый диалог {path}",
        "err_db_missing": "Файл базы не найден: {p}",
        "err_no_db": "Не найдена база ZCode. Укажите файл db.sqlite в поле «SQL база».",
        "err_db_invalid": "В файле нет таблиц диалогов — это не база ZCode: {p}",
        "err_no_sessions": "В базе нет ни одного диалога.",
        "err_ambiguous": "Подходит несколько диалогов, уточните:\n{lines}",
        "err_not_found": "Диалог не найден: {needle}",
        "err_empty": "В диалоге нет сообщений: {id}",
        "lbl_done": "Готово: {path}",
        "lbl_conversation": "Диалог: {title}  ({count})",
        "ctx_summary": "Сводка уплотнённой истории",
        "ctx_boundary": "Уплотнение: выше — история свернута в сводку",
        "ctx_boundary_tokens": " (до {n} ток)",
    },
    "en": {
        "session": "Session",
        "directory": "Directory",
        "created": "Created",
        "updated": "Updated",
        "messages": "Messages",
        "messages_qa": " (prompts/answers)",
        "you": "You",
        "system": "ZCode",
        "llm_unknown": "LLM",
        "context_copy": "Context",
        "harness": "Harness core",
        "project": "Project",
        "chat": "Chat",
        "files_line": "Files",
        "files_stats": "attached {n}, ready to download {m}",
        "files_attached": "attached {n}",
        "models": "Models",
        "chat_type": "Type",
        "none": "—",
        "attached": "📎 Attached:",
        "unit_kb": "KB",
        "unit_b": "B",
        "tools": "Tools",
        "call": "Call",
        "result": "Result",
        "reasoning": "Intermediate replies",
        "h_context": "Chat context",
        "h_compact": "Auto-compact at",
        "h_spent": "Total spent",
        "exported": "Exported",
        "truncated": "… (truncated, {size} total)",
        "empty_request": "[empty request]",
        "db": "Database:",
        "done": "Done:",
        "conversation": "Conversation:",
        "all_chats": "All ZCode chats",
        "selected_chats": "Selected ZCode chats",
        "new_dialog": "New conversation {path}",
        "err_db_missing": "Database file not found: {p}",
        "err_no_db": "ZCode database not found. Set the db.sqlite file in the \"SQL database\" field.",
        "err_db_invalid": "No conversation tables in the file — this is not a ZCode database: {p}",
        "err_no_sessions": "No conversations found in the database.",
        "err_ambiguous": "Several conversations match, please specify:\n{lines}",
        "err_not_found": "Conversation not found: {needle}",
        "err_empty": "No messages in the conversation: {id}",
        "lbl_done": "Done: {path}",
        "lbl_conversation": "Conversation: {title}  ({count})",
        "ctx_summary": "Compacted-history summary",
        "ctx_boundary": "Compaction: history above is folded into the summary",
        "ctx_boundary_tokens": " (up to {n} tokens)",
    },
    "zh": {
        "session": "会话",
        "directory": "目录",
        "created": "创建时间",
        "updated": "更新时间",
        "messages": "消息",
        "messages_qa": "（问题/回答）",
        "you": "你",
        "system": "ZCode",
        "llm_unknown": "LLM",
        "context_copy": "上下文",
        "harness": "框架核心",
        "project": "项目",
        "chat": "对话",
        "files_line": "文件",
        "files_stats": "已附上 {n}，可下载 {m}",
        "files_attached": "已附上 {n}",
        "models": "模型",
        "chat_type": "类型",
        "none": "—",
        "attached": "📎 附件：",
        "unit_kb": "KB",
        "unit_b": "B",
        "tools": "工具调用",
        "call": "调用",
        "result": "结果",
        "reasoning": "中间回复",
        "h_context": "聊天上下文",
        "h_compact": "自动压缩于",
        "h_spent": "总消耗",
        "exported": "导出时间",
        "truncated": "…（已截断，共 {size}）",
        "empty_request": "[空请求]",
        "db": "数据库：",
        "done": "完成：",
        "conversation": "对话：",
        "all_chats": "全部 ZCode 对话",
        "selected_chats": "所选 ZCode 对话",
        "new_dialog": "新对话 {path}",
        "err_db_missing": "找不到数据库文件：{p}",
        "err_no_db": "未找到 ZCode 数据库。请在“SQL 数据库”字段中指定 db.sqlite 文件。",
        "err_db_invalid": "文件中没有对话表——这不是 ZCode 数据库：{p}",
        "err_no_sessions": "数据库中没有对话。",
        "err_ambiguous": "匹配到多个对话，请明确指定：\n{lines}",
        "err_not_found": "找不到对话：{needle}",
        "err_empty": "该对话没有消息：{id}",
        "lbl_done": "完成：{path}",
        "lbl_conversation": "对话：{title}  ({count})",
        "ctx_summary": "压缩历史的摘要",
        "ctx_boundary": "压缩：以上历史已折叠进摘要",
        "ctx_boundary_tokens": " (最多 {n} tokens)",
    },
}


def t(key: str, **kwargs) -> str:
    table = LABELS.get(LANG) or LABELS["ru"]
    value = table.get(key) or LABELS["ru"].get(key, key)
    return value.format(**kwargs) if kwargs else value


# ------------------------------------------------------------- база данных


def connect_ro(db: Path) -> tuple[sqlite3.Connection, Path | None]:
    """Открытие только на чтение; при блокировке — чтение временной копии.

    Файл обязательно проверяется на принадлежность к базе ZCode (таблица
    session): чужой/сломанный файл -> понятная ошибка, а не traceback.
    Возвращает (соединение, временная папка или None — её удаляет close()
    адаптера).
    """
    def open_uri() -> sqlite3.Connection:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute("select count(*) from session")
        return con

    def valid(con: sqlite3.Connection) -> bool:
        try:
            return con.execute(
                "select 1 from sqlite_master where type = 'table' and name = 'session'"
            ).fetchone() is not None
        except sqlite3.Error:
            return False

    try:
        con = open_uri()
        if valid(con):
            return con, None
        con.close()
        raise AdapterError(t("err_db_invalid", p=db))
    except sqlite3.Error:
        pass  # база занята приложением — пробуем читать временную копию

    tmp = Path(tempfile.mkdtemp(prefix="zcode-export-"))
    for ext in ("", "-wal", "-shm"):
        src = Path(str(db) + ext)
        if src.is_file():
            shutil.copy2(src, tmp / ("db.sqlite" + ext))
    try:
        con = sqlite3.connect(tmp / "db.sqlite")
        con.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        raise AdapterError(t("err_db_invalid", p=db) + f" ({exc})") from None
    if not valid(con):
        raise AdapterError(t("err_db_invalid", p=db))
    return con, tmp


# ------------------------------------------------------------- время/имена

def ms_to_dt(ms) -> datetime | None:
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000).astimezone()
    except (ValueError, OSError, OverflowError):
        return None


def local_time(ms) -> str:
    dt = ms_to_dt(ms)
    return dt.strftime("%d.%m.%Y %H:%M") if dt else ""


def iso_time(ms) -> str:
    dt = ms_to_dt(ms)
    return dt.isoformat(timespec="seconds") if dt else ""


def file_date(ms) -> str:
    dt = ms_to_dt(ms)
    return dt.strftime("%Y-%m-%d") if dt else "0000-00-00"




EXPORTER_URL = "https://www.vmgames.com"


def exporter_line(fmt: str, version: str) -> str:
    """р63 (я2): строка экспортёра — md с кликабельным линком,
    txt с URL текстом (порт из движка AutoClaw)."""
    base = f"Z.ai Chats Exporter by Vadim R.M. ver. {version}"
    if fmt == "md":
        return base + " — [" + EXPORTER_URL + "](" + EXPORTER_URL + ")"
    return base + "  " + EXPORTER_URL


def exporter_footer(fmt: str, version: str) -> str:
    """р60 (я1): строка экспортёра в конце каждого чата; р63 (я2): в
    txt — рамка из черт длиной в строку. Пустая версия — нет строки."""
    if not version:
        return ""
    line = exporter_line(fmt, version)
    if fmt == "md":
        return "\n---\n\n" + line + "\n"
    rule = "-" * len(line)
    return "\n" + rule + "\n" + line + "\n" + rule + "\n"


def exporter_header(fmt: str, version: str) -> str:
    """р62 (я8)/р63 (я1-я2): строка экспортёра последней строкой шапки —
    после пустой строки; в txt обрамлена чертами длиной в строку
    (рамка завершает шапку вместо разделителя «-»×60)."""
    if not version:
        return ""
    line = exporter_line(fmt, version)
    if fmt == "md":
        return "\n" + line + "\n"
    rule = "-" * len(line)
    return "\n" + rule + "\n" + line + "\n" + rule + "\n"


def underline(line: str) -> str:
    """р62 (я3/я4): строка из «-» длиной в заголовок — txt-замена
    крупного шрифта md-заголовков; длина по символам строки."""
    return "-" * len(line.rstrip()) + "\n"


def _plural(n: int, one: str, few: str, many: str) -> str:
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many


def fmt_num(n: int) -> str:
    """р62 (я2): тысячи с разделителем — «16 161» (ru/zh), «16,161» (en)."""
    if LANG == "en":
        return f"{n:,}"
    return f"{n:,}".replace(",", " ")


def n_tokens(n: int) -> str:
    """р62 (я2): «32 362 токена» — с падежом (ru); en — token/tokens."""
    if LANG == "ru":
        return f"{fmt_num(n)} {_plural(n, 'токен', 'токена', 'токенов')}"
    if LANG == "en":
        return f"{fmt_num(n)} token" if n == 1 else f"{fmt_num(n)} tokens"
    return fmt_num(n)


# р81 (п.3): карта моделей → окно контекста (токенов). В базе ZCode окна
# нет (р62); 1М = 1 000 000 — как в примере владельца (28 019 → 2.8%).
# Модель не из карты → «(X%/1М)» не выводится вовсе.
MODEL_WINDOWS = {
    "glm-5.3": 1_000_000,
    "glm-5.3-flash": 1_000_000,
}


def token_header_lines(st: dict | None) -> list[str]:
    """р62 (я2): строки токенов шапки — формат владельца (порт из AC).
    У ZCode в базе есть контекст (последний model_usage.input_tokens,
    как графа «Ток» р43) и расход всего (Σ provider_total_tokens);
    окна и порога автосжатия нет — эти части опускаются.
    р81 (п.3): «Контекст чата: 28 019 токенов (2.8%/1М)» — слово
    «токенов» всегда; доля от окна — только если модель последнего
    контекстного запроса есть в MODEL_WINDOWS."""
    if not st:
        return []
    lines: list[str] = []
    context = st.get("context")
    if context is not None:
        window = MODEL_WINDOWS.get((st.get("model") or "").strip().lower())
        pct = f"{context / window * 100:.1f}" if window else ""
        if LANG == "zh":
            value = f"{fmt_num(context)} token" + (f"（{pct}%/1M）" if window else "")
            lines.append(f"{t('h_context')}：{value}")
        else:
            unit = "1М" if LANG == "ru" else "1M"
            value = n_tokens(context) + (f" ({pct}%/{unit})" if window else "")
            lines.append(f"{t('h_context')}: {value}")
    total = st.get("total_spent")
    if total is not None and total >= 0:
        lines.append(f"{t('h_spent')}: {n_tokens(total)}")
    return lines


def fmt_duration(secs) -> str:
    """р62 (я5): время работы модели — «15 сек» / «0.8 сек» (десятые
    только <1 сек) / «2 мин 12 сек» / «1 час 5 мин»; единицы «сек/мин/час»."""
    try:
        secs = float(secs)
    except (TypeError, ValueError):
        return ""
    if secs < 0:
        secs = 0.0
    if LANG == "zh":
        if secs < 1:
            return f"{secs:.1f}秒"
        total = int(round(secs))
        if total < 60:
            return f"{total}秒"
        if total < 3600:
            m, s = divmod(total, 60)
            return f"{m}分" + (f"{s}秒" if s else "")
        h, m = divmod(total // 60, 60)
        return f"{h}小时" + (f"{m}分" if m else "")
    unit_s = "sec" if LANG == "en" else "сек"
    unit_m = "min" if LANG == "en" else "мин"
    unit_h = "hour" if LANG == "en" else "час"
    if secs < 1:
        return f"{secs:.1f} {unit_s}"
    total = int(round(secs))
    if total < 60:
        return f"{total} {unit_s}"
    if total < 3600:
        m, s = divmod(total, 60)
        return f"{m} {unit_m}" + (f" {s} {unit_s}" if s else "")
    h, m = divmod(total // 60, 60)
    return f"{h} {unit_h}" + (f" {m} {unit_m}" if m else "")


def fmt_size(n) -> str:
    """р49: размер вложения для человека — «61 КБ», «76917 Б» (ru);
    нет/битое — пусто (в экспорте строка без размера)."""
    if not isinstance(n, int) or n < 0:
        return ""
    if n >= 1024:
        return f"{round(n / 1024)} {t('unit_kb')}"
    return f"{n} {t('unit_b')}"


def safe_filename(title: str, limit: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", title or "")
    name = name.replace("\r", " ").replace("\n", " ")
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    if len(name) > limit:
        name = name[:limit].rstrip(". ")
    return name or "chat"


def project_subdir(session: sqlite3.Row) -> str:
    """Я6: подпапка проекта — последний компонент session.directory.

    Раунд 25/26: Tasks ZCode (directory внутри .../.zcode/workspace,
    машинно-независимая проверка маркера в самой строке пути — на чужой
    машине с чужим профилем маркер тот же) — БЕЗ проекта: пустая строка
    → экспорт в корень папки вывода и пустая графа «Проект»."""
    directory = (session["directory"] or "").strip()
    if not directory or _is_task_directory(directory):
        return ""
    return safe_filename(Path(directory).name)


def _is_task_directory(directory: str) -> bool:
    marker = chr(92) + ".zcode" + chr(92) + "workspace" + chr(92)
    norm = directory.replace("/", chr(92)).lower()
    return (marker in norm) or norm.endswith(marker.rstrip(chr(92)))


# ------------------------------------------------- имена проектов ZCode

SIDECAR_DB = Path.home() / ".zcode" / "v2" / "tasks-index.sqlite"


def load_project_index(sidecar_path=None) -> dict:
    """Данные о проектах из 2-й базы (tasks-index настольного приложения;
    путь — «SQL база 2», раунд 31; нет файла → {"missing": True}).
    Возвращает {"missing", "session_project": {task_id: имя} (р39: прямая
    связь tasks.task_id = id сессии → проект, ровно как назначено в UI),
    "root_order": [(normcase-корень, имя)] в приоритете is_primary →
    position → длина (р39), "auto_sessions" (р37)}.
    Пропускаются: projects.deleted=1 — переименованные старые имена
    (подтверждено владельцем), tasks.deleted/archived=1 — имя удалённой/
    архивной задачи не выдаётся (раунд 39, решение владельца)."""
    path = Path(sidecar_path) if sidecar_path else SIDECAR_DB
    if not path.is_file():
        return {"missing": True}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
        con.row_factory = sqlite3.Row
        names, session_project, roots = {}, {}, []
        for r in con.execute(
            "select project_id, name from projects where coalesce(deleted, 0) = 0"
        ):
            name = (r["name"] or "").strip()
            if name and r["project_id"]:
                names[r["project_id"]] = name
        # р39: прямая связь сессия→проект; PK у tasks составной
        # (workspace_key, task_id) — при дубле task_id побеждает запись
        # со свежим updated_at (order by desc + первое заполнение)
        try:
            for r in con.execute(
                "select task_id, project_id from tasks "
                "where coalesce(deleted, 0) = 0 and coalesce(archived, 0) = 0 "
                "and task_id is not null and project_id is not null "
                "order by coalesce(updated_at, 0) desc"
            ):
                tid = (r["task_id"] or "").strip()
                pid = (r["project_id"] or "").strip()
                if tid and pid in names and tid not in session_project:
                    session_project[tid] = names[pid]
        except sqlite3.Error:
            pass  # старый индекс без таблицы tasks — только корни
        try:
            raw_roots = list(con.execute(
                "select project_id, root_path, position, is_primary "
                "from project_roots"
            ))
        except sqlite3.Error:
            # колонок position/is_primary нет (старый индекс) — нули
            raw_roots = [
                {"project_id": r["project_id"], "root_path": r["root_path"],
                 "position": 0, "is_primary": 0}
                for r in con.execute(
                    "select project_id, root_path from project_roots")
            ]
        for r in raw_roots:
            project_id = (r["project_id"] or "").strip()
            root_path = (r["root_path"] or "").strip()
            if project_id in names and root_path:
                try:
                    key = os.path.normcase(os.path.realpath(root_path))
                except OSError:
                    key = os.path.normcase(root_path)
                roots.append((key, names[project_id],
                              int(r["is_primary"] or 0),
                              int(r["position"] or 0)))
        # р39 (решение владельца): главный корень бьёт позицию, позиция —
        # длину; прежняя эвристика «самый длинный» — последний критерий
        roots.sort(key=lambda x: (-x[2], x[3], -len(x[0])))
        # раунд 37: сессии планировщиков (automations/off_peak) — метка
        # «auto»; в старом индексе таблиц нет — метки просто нет
        auto_sessions: set[str] = set()
        for table in ("automations", "automation_runs", "off_peak_tasks"):
            try:
                for r in con.execute(
                    f"select session_id from {table} where session_id is not null"
                ):
                    sid = (r["session_id"] or "").strip()
                    if sid:
                        auto_sessions.add(sid)
            except sqlite3.Error:
                pass
        # раунд 41: архив UI ZCode живёт здесь — tasks.archived=1
        # (session.time_archived не пишется); такие чаты скрыты (arch)
        archived_ids: set[str] = set()
        # р48: deletion через UI тоже виден здесь раньше/вместо чатовой
        # колонки session.time_deleted (на базе владельца у удалённого
        # чата tasks.deleted=1 И tasks.archived=1, а time_deleted мог ещё
        # не доехать) — такие чаты получают метку «del» ПРЕЖНЕ архива
        deleted_ids: set[str] = set()
        try:
            for r in con.execute(
                "select task_id, coalesce(deleted, 0), coalesce(archived, 0) "
                "from tasks where task_id is not null"
            ):
                tid = (r["task_id"] or "").strip()
                if not tid:
                    continue
                if r[1]:
                    deleted_ids.add(tid)
                elif r[2]:
                    archived_ids.add(tid)
        except sqlite3.Error:
            pass  # старый индекс без tasks — архива/удаления не видно
        con.close()
        return {"missing": False,
                "session_project": session_project,
                "root_order": [(key, name) for key, name, _p, _i in roots],
                "auto_sessions": auto_sessions,
                "archived_ids": archived_ids,
                "deleted_ids": deleted_ids}
    except (sqlite3.Error, OSError):
        return {"missing": True}


def project_for(session: sqlite3.Row, info: dict) -> str:
    """Имя проекта чата (раунды 29/39) — для графы «Проект» и папок
    экспорта:
    1) прямая связь из 2-й базы: tasks.task_id (= id сессии) → проект
       (раунд 39: ровно то, что назначено в UI ZCode; чинит чаты в
       worktree и папках запуска, где корень проекта не виден);
    2) корневые директории проектов в порядке is_primary → position →
       длина (раунд 39; прежде — просто самый длинный корень);
    Tasks (directory внутри .../.zcode/workspace) — без проекта;
    индекс отсутствует (старый ZCode / машина без индекса) — лист
    директории, как прежде."""
    directory = (session["directory"] or "").strip()
    if not info.get("missing"):
        direct = info.get("session_project", {}).get(session["id"])
        if direct:
            return direct
        if directory:
            try:
                norm = os.path.normcase(os.path.realpath(directory))
            except OSError:
                norm = os.path.normcase(directory)
            for root, project_name in info.get("root_order") or []:
                if norm == root or norm.startswith(root + os.sep):
                    return project_name  # р39: первый в приоритете корней
            return ""  # индекс есть, сопоставления нет — имени не выдаём
    if _is_task_directory(directory):
        return ""
    return safe_filename(Path(directory).name) if directory else ""


def unique_path(path: Path) -> Path:
    """ER-5: не перезаписывать — суффиксы « (1)», « (2)», … до свободного имени."""
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


# ------------------------------------------------------- форки (раунд 40)

def fork_map(con: sqlite3.Connection, sessions: list) -> dict:
    """Раунд 40 (бета C, решение владельца): номера и точки расхождения
    форков. Номер среди «братьев» (форков одного parent_id) — по позиции
    boundary-сообщения в родителе (targetMessageId берётся из
    синтетического уведомления форка, расследовано в исходниках ZCode,
    см. zcode_github.md); границы нет — по времени создания форка
    («первый — ближе всего к началу чата»). Цепочка вложенности —
    подъёмом по parent_id (« frk1 frk1»). Возвращает {id: info} ТОЛЬКО
    для task_type='fork'; info: tag (« frk1»), num, parent_id,
    line («Форк от «…»: точка расхождения — сообщение «…» (дата)»)."""
    by_id = {s["id"]: s for s in sessions}
    forks = [s for s in sessions if (s["task_type"] or "").strip() == "fork"]
    if not forks:
        return {}
    info: dict[str, dict] = {}
    for s in forks:
        rec: dict = {"parent_id": (s["parent_id"] or "").strip(),
                     "target": "", "seq": None, "when": None, "snippet": None}
        note = con.execute(
            "select id, data from message where session_id = ? "
            "and json_extract(data, '$.source') = 'fork' "
            "order by sequence limit 1", (s["id"],)
        ).fetchone()
        if note:
            d = parse_payload(note[1])
            md = d.get("metadata")
            fc = md.get("forkContext") if isinstance(md, dict) else None
            parent_note, target = "", ""
            if isinstance(fc, dict):
                parent_note = str(fc.get("parentSessionId") or "").strip()
                target = str(fc.get("targetMessageId") or "").strip()
            if not target:
                # fallback: строки уведомления в тексте частей
                blob = "\n".join(
                    (parse_payload(praw).get("text") or "")
                    for (praw,) in con.execute(
                        "select data from part where message_id = ? "
                        "order by sequence", (note[0],)))
                m_parent = re.search(r"parentSessionId:\s*(\S+)", blob)
                m_target = re.search(r"targetMessageId:\s*(\S+)", blob)
                if m_parent:
                    parent_note = m_parent.group(1)
                if m_target:
                    target = m_target.group(1)
            if parent_note and not rec["parent_id"]:
                rec["parent_id"] = parent_note
            rec["target"] = target
        info[s["id"]] = rec
    for rec in info.values():
        if not rec["target"]:
            continue
        boundary = con.execute(
            "select session_id, sequence, time_created from message "
            "where id = ?", (rec["target"],)
        ).fetchone()
        if boundary is None or (rec["parent_id"]
                                and boundary[0] != rec["parent_id"]):
            continue  # граница не в родителе (удалена/уплотнена) — fallback
        rec["seq"] = boundary[1] or 0
        rec["when"] = local_time(boundary[2])
        for (praw,) in con.execute(
            "select data from part where message_id = ? order by sequence",
            (rec["target"],)
        ):
            part = parse_payload(praw)
            if part.get("type") == "text" and (part.get("text") or "").strip():
                rec["snippet"] = " ".join(part["text"].split())[:60]
                break
    brothers: dict[str, list[str]] = {}
    for fid, rec in info.items():
        brothers.setdefault(rec["parent_id"], []).append(fid)

    def brother_key(fid: str):
        rec = info[fid]
        created = by_id[fid]["time_created"] or 0
        if rec["seq"] is not None:
            return (0, rec["seq"], created)
        return (1, 0, created)

    for fids in brothers.values():
        for num, fid in enumerate(sorted(fids, key=brother_key), 1):
            info[fid]["num"] = num
    for fid in info:
        nums, cur, seen = [], fid, set()
        while cur in info and cur not in seen:
            seen.add(cur)
            nums.append(info[cur]["num"])
            cur = info[cur]["parent_id"]
        info[fid]["tag"] = "".join(f" frk{n}" for n in reversed(nums))
    for fid, rec in info.items():
        parent_id = rec["parent_id"]
        parent_row = by_id.get(parent_id)
        parent_tag = info.get(parent_id, {}).get("tag", "") if parent_id else ""
        if parent_row is not None:
            parent_disp = (parent_row["title"] or "") + parent_tag
        else:
            parent_disp = parent_id or "?"
        line = f"Форк от «{parent_disp}»"
        if rec["snippet"]:
            line += (f": точка расхождения — сообщение «{rec['snippet']}» "
                     f"({rec['when']})")
        elif rec["when"]:
            line += f": точка расхождения ({rec['when']})"
        rec["line"] = line
    return info


def with_fork_tag(session, fmap: dict) -> dict:
    """Раунд 40 (решение владельца: суффикс форка ВЕЗДЕ): копия строки
    сессии с « frkN…» в названии — попадает в имя файла, заголовок внутри
    файла и графу «Чат»; в info кладётся fork_note_info для рендеров."""
    row = dict(session)
    note = fmap.get(row["id"])
    if note:
        row["title"] = (row["title"] or "") + note["tag"]
        row["fork_note_info"] = note
    return row


def build_filename(session: sqlite3.Row, fmt: str, used: set[str] | None = None) -> str:
    # р36: между датой и названием — пробел вместо тире (как у AC-,
    # решение владельца)
    base = f"ZC-{file_date(session['time_created'])} {safe_filename(session['title'])}"
    name = base
    counter = 2
    while used is not None and name in used:
        name = f"{base}-{counter}"
        counter += 1
    if used is not None:
        used.add(name)
    return f"{name}.{fmt}"


# ------------------------------------------------------------- данные

def load_sessions(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Все пользовательские сессии, КРОМЕ внутренних subagent_child
    (раунды 26/37: их не показываем никогда). Удалённые (time_deleted /
    session_purge) и архивные (time_archived) ВКЛЮЧАЮТСЯ — их видимость
    управляет чекбокс «Показывать скрытые чаты» GUI (раунд 37). Для
    старых баз без новых колонок — упрощённый запрос (метки только по
    task_type)."""
    sql = """
        select s.id, s.title, s.directory, s.time_created, s.time_updated,
               s.task_type, s.time_deleted, s.time_archived, s.parent_id,
               exists(select 1 from session_purge p
                      where p.session_id = s.id) as purge_flag
        from session s
        where coalesce(s.task_type, '') <> 'subagent_child'
        order by s.time_updated desc
    """
    try:
        return list(con.execute(sql))
    except sqlite3.OperationalError:
        return list(
            con.execute(
                """
                select id, title, directory, time_created, time_updated,
                       task_type, null as time_deleted,
                       null as time_archived, parent_id, 0 as purge_flag
                from session
                where coalesce(task_type, '') <> 'subagent_child'
                order by time_updated desc
                """
            )
        )


def session_version(con: sqlite3.Connection, session_id: str):
    """р51: версия харнесса ZCode (session.version, «0.17.1») отдельным
    защищённым запросом — старые копии без колонки/таблиц дают None,
    не ломая основной выборке (fallback по session_purge ни при чём)."""
    try:
        row = con.execute("select version from session where id = ?",
                          (session_id,)).fetchone()
        return (row[0] or "").strip() if row and row[0] else None
    except sqlite3.OperationalError:
        return None


# Метки графы «Тип» (раунд 37, решение владельца: сокращения из
# документации, не переводятся; fork/workflow_parent — ОБЫЧНЫЕ чаты,
# не скрываются — прежний is_subagent прятал их ошибочно).
_TYPE_LABELS = {
    "workflow_child": "wfchld",
    "selection_side_chat": "selchat",
    "workflow_parent": "wfprnt",
    "fork": "fork",
}


# р49 (замена префиксной эвристики р48): автор каждой порции текста
# определяется ТОЧНО — флагом synthetic в самих данных message:
#   synthetic=true  → вставка харнесса ZCode (среда, систем-промпт,
#                     листинги инструментов, todo-напоминания) — «Система»;
#   synthetic=false/нет у role=user → человек — «Вы» (в т.ч. 6
#                     model-only реплик владельца в базе);
#   role=assistant  → агент — «ZCode» (уже подписано).
# Префиксы текста больше не нужны: [4]/[5] владельца имели флаг, но не
# мой список фраз; человеческий текст может НАЧИНАТЬСЯ с любой фразы.


def session_state(session: sqlite3.Row,
                  auto_ids: frozenset | set = frozenset(),
                  archived_ids: frozenset | set = frozenset(),
                  deleted_ids: frozenset | set = frozenset()) -> tuple[str, bool]:
    """(метка графы «Тип», скрытый?) — раунды 37/41/48; приоритет
    del > arch > тип > auto. Скрытые видны только с чекбоксом
    «Показывать скрытые чаты» и рисуются светло-серым фоном.
    Два источника «arch» (р41, найдено на базе владельца): UI ZCode
    ставит архив в tasks-index (tasks.archived=1), чатовую колонку
    session.time_archived не трогает — поэтому вторая база здесь
    главный источник; без неё архив невидим (старое поведение).
    р48: у «del» третий источник — tasks.deleted=1 из tasks-index (UI
    удаляет задачу в индексе, time_deleted в чатовой базе доезжает
    позже; на базе владельца удалённый чат имел tasks.deleted=1 И
    tasks.archived=1 — прежде показывался как «arch»)."""
    if (session["time_deleted"] is not None or session["purge_flag"]
            or session["id"] in deleted_ids):
        return "del", True
    if session["time_archived"] is not None or session["id"] in archived_ids:
        return "arch", True
    label = _TYPE_LABELS.get((session["task_type"] or "").strip(), "")
    if label:
        return label, label in ("wfchld", "selchat")
    if session["id"] in auto_ids:
        return "auto", True
    return "", False


def _is_context_copy(session) -> bool:
    """р64 (E5b): user-ходы этих чатов — копия контекста от главного
    агента/харнесса, не человек: selchat (р60 я7) и workflow_child —
    субагент-акторы (dwf-actor), им стартовый промпт передаёт харнесс."""
    return (session["task_type"] or "").strip() in (
        "selection_side_chat", "workflow_child")


def chat_type_of(session, info: dict | None = None) -> str:
    """р63 (я3): тип чата для шапки — та же метка, что в графе «Тип»
    GUI (session_state); info (tasks-index) — если есть."""
    info = info or {}
    label, _hidden = session_state(
        session,
        info.get("auto_sessions") or frozenset(),
        info.get("archived_ids") or frozenset(),
        info.get("deleted_ids") or frozenset())
    return label


def is_hidden(session: sqlite3.Row,
              auto_ids: frozenset | set = frozenset(),
              archived_ids: frozenset | set = frozenset(),
              deleted_ids: frozenset | set = frozenset()) -> bool:
    return session_state(session, auto_ids, archived_ids, deleted_ids)[1]


def count_requests(con: sqlite3.Connection, session_id: str) -> int:
    # р40: синтетические уведомления (форк/rewind) запросами не считаются
    return con.execute(
        "select count(*) from message where session_id = ? "
        "and json_extract(data, '$.role') = 'user' "
        "and coalesce(json_extract(data, '$.synthetic'), 0) = 0",
        (session_id,),
    ).fetchone()[0]


def pick_session(sessions: list[sqlite3.Row], needle: str | None) -> sqlite3.Row:
    if not sessions:
        raise AdapterError(t("err_no_sessions"))
    if not needle:
        return sessions[0]
    needle_l = needle.strip().lower()
    exact = [s for s in sessions if s["id"].lower() == needle_l]
    if exact:
        return exact[0]
    by_id = [s for s in sessions if s["id"].lower().startswith(needle_l)]
    if len(by_id) == 1:
        return by_id[0]
    by_title = [s for s in sessions if needle_l in (s["title"] or "").lower()]
    if len(by_title) == 1:
        return by_title[0]
    if len(by_title) > 1:
        lines = "\n".join(f"  {s['id']}  {s['title']}" for s in by_title)
        raise AdapterError(t("err_ambiguous", lines=lines))
    raise AdapterError(t("err_not_found", needle=needle))


def parse_payload(raw) -> dict:
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def build_turns(con: sqlite3.Connection, session_id: str,
                fork_note: dict | None = None,
                ctx_mode: bool = False,
                context_copy: bool = False) -> list[dict]:
    """Ходы: запрос пользователя -> ответы/инструменты/реплики до следующего.
    Раунд 40: синтетические сообщения (форк/rewind-уведомления,
    model-only) НЕ попадают в текст экспорта (прежде протекали как
    фейковые запросы); на месте форк-уведомления запоминается точка
    расхождения — она прикрепляется к первому НОВОМУ ходу форка, а если
    новых ходов нет — к последнему (граница копии).
    Раунд 43 (ctx_mode — «как видит модель»): срез после последнего
    уплотнения (part.type='compaction': tail_start_id — начало живого
    хвоста, summaryMessageId — сообщение-сводка, preCompactTokenCount),
    сводка уплотнённой истории — отдельным блоком в начале, model-only
    сообщения ВКЛЮЧАЮТСЯ (они в контексте), маркер границы. Без ctx_mode
    граница только помечается (маркер «уплотнение»), ничего не режется.
    р60 (я7): context_copy=True — чат-копия контекста (selection_side_chat:
    user-сообщения перенесены харнессом из главного чата) — ходы
    помечаются turn["context_copy"], в рендерах подписываются
    «Контекст», а не «Вы»."""
    messages = con.execute(
        "select id, sequence, data, time_created from message "
        "where session_id = ? order by sequence",
        (session_id,),
    )
    # р50: модель каждого ответа — model_usage по assistant_message_id
    umodels = usage_models(con)
    turns: list[dict] = []
    current: dict | None = None
    pending = fork_note
    # р43: compaction-границы — пре-скан частей (нужны ДО основного цикла,
    # чтобы ctx-режим пропустил сообщение-сводку без дублирования)
    boundaries: list[tuple[int, dict]] = []  # (seq сообщения, part)
    sum_ids: set[str] = set()
    for prow in con.execute(
        "select m.sequence as bseq, p.data from part p "
        "join message m on m.id = p.message_id "
        "where m.session_id = ? and json_extract(p.data, '$.type') = 'compaction' "
        "order by m.sequence", (session_id,)):
        part = parse_payload(prow["data"])
        boundaries.append((prow["bseq"], part))
        sid_ = (part.get("summaryMessageId") or "").strip()
        if sid_:
            sum_ids.add(sid_)
    for mid, seq, raw, created in messages:
        data = parse_payload(raw)
        is_service = (bool(data.get("synthetic")) or data.get("source")
                      or data.get("visibility") == "model-only")
        if is_service:
            if not (ctx_mode and data.get("visibility") == "model-only"):
                if fork_note and data.get("source") == "fork":
                    pending = fork_note
                continue
        if ctx_mode and mid in sum_ids:
            continue  # сводка рендерится отдельным блоком, не как ход
        role = data.get("role")
        parts = con.execute(
            "select data from part where message_id = ? order by sequence", (mid,)
        )
        if role == "user":
            current = {
                "request": "",
                "request_at": created,
                "attachments": [],
                "answers": [],
                "tools": [],
                "narration": [],
                "_seq": seq,
                # р49: автор — точный флаг synthetic из данных
                "system": bool(data.get("synthetic")),
                # р60 (я7): чат-копия контекста (selchat) — не «Вы»
                "context_copy": context_copy,
            }
            if pending:
                current["fork_note"] = pending
                pending = None
            turns.append(current)
        if current is None:
            continue
        for (praw,) in parts:
            part = parse_payload(praw)
            ptype = part.get("type")
            if ptype == "text":
                text = (part.get("text") or "").strip()
                if text:
                    if role == "user":
                        current["request"] = (current["request"] + "\n\n" + text).strip()
                    else:
                        current["answers"].append({"text": text, "at": created})
                        # р50: автор ответа — последний ответивший в ходе;
                        # р60 (я3): + время работы (duration_ms)
                        model, variant, agent, dur = umodels.get(
                            mid, (None, None, None, None))
                        current["model"] = model_label(model, variant, agent)
                        if isinstance(dur, (int, float)) and dur >= 0:
                            current["work_secs"] = dur / 1000.0
            elif ptype == "reasoning":
                text = (part.get("text") or "").strip()
                if text:
                    current["narration"].append(text)
            elif ptype == "tool":
                state = part.get("state") or {}
                output = state.get("output")
                if not isinstance(output, str):
                    output = json.dumps(output, ensure_ascii=False) if output is not None else ""
                current["tools"].append({
                    "name": part.get("tool") or "tool",
                    "status": state.get("status", "?"),
                    "input": state.get("input"),
                    "output": output,
                })
            elif ptype == "file":
                # р49: размер вложения — metadata.sizeBytes (у картинок
                # transformedSizeBytes после ресайза); нет — пусто
                meta = part.get("metadata") or {}
                size = meta.get("sizeBytes")
                if not isinstance(size, int):
                    size = meta.get("transformedSizeBytes")
                current["attachments"].append({
                    "name": part.get("filename") or part.get("url") or "file",
                    "path": part.get("url") or "",
                    "media": part.get("mime") or "",
                    "size": size if isinstance(size, int) else None,
                })
    if pending and turns:
        turns[-1]["fork_note"] = pending  # новых ходов нет — метка на границе
    # ---- р43: границы уплотнения (compaction) ----
    tail_pairs: list[tuple[int, dict]] = []  # (seq хвоста, part)
    summary_turns: list[dict] = []
    for _bseq, part in boundaries:
        tail_seq = None
        tail_id = (part.get("tail_start_id") or "").strip()
        if tail_id:
            r = con.execute(
                "select sequence, session_id from message where id = ?",
                (tail_id,)).fetchone()
            if r and r["session_id"] == session_id:
                tail_seq = r["sequence"]
        if tail_seq is not None:
            tail_pairs.append((tail_seq, part))
        sum_id = (part.get("summaryMessageId") or "").strip()
        if ctx_mode and sum_id:
            srow = con.execute(
                "select data, time_created from message where id = ? "
                "and session_id = ?", (sum_id, session_id)).fetchone()
            if srow:
                texts = []
                for (praw,) in con.execute(
                    "select data from part where message_id = ? "
                    "order by sequence", (sum_id,)):
                    pd = parse_payload(praw)
                    if pd.get("type") == "text" and (pd.get("text") or "").strip():
                        texts.append(pd["text"].strip())
                if texts:
                    summary_turns.append({
                        "request": "\n\n".join(texts),
                        "request_at": srow["time_created"],
                        "attachments": [], "answers": [], "tools": [],
                        "narration": [], "summary_history": True,
                        "compaction_tokens": part.get("preCompactTokenCount"),
                    })
    if ctx_mode and tail_pairs:
        tail = max(tail for tail, _part in tail_pairs)
        turns = [t for t in turns
                 if t.get("_seq") is None or t["_seq"] >= tail]
        turns = sorted(summary_turns,
                       key=lambda t: t["request_at"] or 0) + turns
        for t in turns:  # маркер на первом реальном ходе
            if not t.get("summary_history"):
                t["compaction_before"] = True
                break
    else:
        for tail, part in tail_pairs:  # обычный экспорт — маркеры (C)
            for t in turns:
                if t.get("_seq") is not None and t["_seq"] >= tail:
                    t["compaction_before"] = True
                    if t.get("compaction_tokens") is None:
                        t["compaction_tokens"] = part.get("preCompactTokenCount")
                    break
    turns = [t for t in turns if t["request"] or t["answers"]]
    return turns


def usage_tokens(con: sqlite3.Connection) -> dict[str, int]:
    """Раунд 43 (A): последний input_tokens сессии из model_usage —
    ТОЧНЫЙ размер контекста на момент последнего запроса (провайдерский
    счётчик). {session_id: tokens}; базы без model_usage → {}."""
    try:
        rows = con.execute(
            "select session_id, input_tokens, started_at from model_usage "
            "where input_tokens is not null order by started_at")
    except sqlite3.OperationalError:
        return {}
    last: dict[str, int] = {}
    for sid, tokens, _ts in rows:
        last[sid] = tokens  # порядок по started_at — последний выигрывает
    return last


def token_stats_zc(con: sqlite3.Connection,
                   session_id: str | None = None) -> dict[str, dict]:
    """р62 (я2): токен-статистика сессий ZCode из model_usage:
    context = последний input_tokens (та же семантика, что у графы
    «Ток» р43 — провайдерский размер контекста последнего запроса);
    total_spent = Σ provider_total_tokens по всем запросам, при null —
    computed_total_tokens («всего израсходовано»). Окна/порога
    автосжатия в базе ZCode нет. {session_id: {context, total_spent}}.
    р81 (п.3): + model — model_id последней строки с input_tokens
    (для доли «(X%/1М)» по карте MODEL_WINDOWS; неизвестная модель —
    скобки не выводятся)."""
    stats: dict[str, dict] = {}
    query = ("select session_id, input_tokens, provider_total_tokens, "
             "computed_total_tokens, model_id from model_usage")
    params: tuple = ()
    if session_id:
        query += " where session_id=?"
        params = (session_id,)
    try:
        rows = con.execute(query + " order by started_at", params)
    except sqlite3.OperationalError:
        return stats
    for sid, inp, prov, comp, model_id in rows:
        st = stats.setdefault(sid, {"context": None, "total_spent": 0})
        if isinstance(inp, int) and inp >= 0:
            st["context"] = inp  # порядок по started_at — последний выигрывает
            st["model"] = model_id
        total = prov if prov is not None else comp
        if isinstance(total, int) and total >= 0:
            st["total_spent"] += total
    return stats


def usage_models(con: sqlite3.Connection) -> dict[str, tuple]:
    """р50: автор каждого ответа — из model_usage по assistant_message_id:
    {message_id: (model_id, variant, agent, duration_ms)} — р60 (я3)
    добавлено время работы. Ретраи (attempt_index>0) дают несколько строк
    на сообщение — побеждает последняя по started_at (финальная попытка).
    Базы без model_usage/колонок → {}."""
    try:
        rows = con.execute(
            "select assistant_message_id, model_id, variant, agent, "
            "duration_ms, started_at "
            "from model_usage where assistant_message_id is not null "
            "order by started_at")
    except sqlite3.OperationalError:
        return {}
    last: dict[str, tuple] = {}
    for mid, model, variant, agent, duration_ms, _ts in rows:
        last[mid] = (model, variant, agent, duration_ms)
    return last


def model_label(model, variant, agent) -> str:
    """р50: подпись автора ответа, как в GUI ZCode: «GLM-5.3-Flash Max»
    (model_id + вариант с заглавной); субагент — суффикс « · Explore»
    (zcode- префикс агента снимается, главный агент не подписывается);
    нет данных → «LLM» (решение владельца)."""
    if not model:
        return "LLM"
    label = str(model)
    if variant:
        label += f" {str(variant).capitalize()}"
    agent = (agent or "").strip()
    if agent and agent != "zcode-agent":
        short = agent[len("zcode-"):] if agent.startswith("zcode-") else agent
        if short and short.lower() != "agent":
            if short.lower() == "workflow":
                # р64 (E5a): dwf-актор — безымянный субагент, «Workflow»
                # выглядел как имя модели; слово-пояснение по языку
                short = {"ru": "Субагент", "en": "Subagent"}.get(LANG, "子代理")
            else:
                short = short.capitalize()
            label += f" · {short}"
    return label


def session_meta(session: sqlite3.Row, turns: list[dict],
                 header: dict | None = None) -> dict:
    """р51: header — данные шапки от адаптера: {"harness": "ZCode",
    "version": <строка|None>, "project": <имя|"">}. Файлы и модели
    считаются из ходов."""
    answers = sum(len(x["answers"]) for x in turns)
    header = header or {}
    version = (header.get("version") or "").strip()
    harness = header.get("harness") or ""
    models: list[str] = []
    for turn in turns:  # порядок появления, без повторов
        label = turn.get("model")
        if turn["answers"] and label and label not in models:
            models.append(label)
    return {
        "id": session["id"],
        "title": (session["title"] or "").strip() or "ZCode chat",
        "directory": session["directory"] or "",
        "harness": (f"{harness} {version}".strip() if harness else ""),
        "project": header.get("project") or "",
        # р63 (я3): тип чата — считает адаптер (session_state с данными
        # tasks-index); обычный чат — ""
        "chat_type": header.get("chat_type") or "",
        "created_at": iso_time(session["time_created"]),
        "updated_at": iso_time(session["time_updated"]),
        "created_local": local_time(session["time_created"]),
        "updated_local": local_time(session["time_updated"]),
        "requests": len(turns),
        "answers": answers,
        "files_attached": sum(len(t["attachments"]) for t in turns),
        "models": models,
    }


# ------------------------------------------------------------- рендеры

def clip(text: str, limit: int) -> str:
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n" + t("truncated", size=f"{len(text)} симв.")


# --- Я8: снятие Markdown-разметки для txt (порт из AutoClaw-движка) ---

CODE_FENCE_RE = re.compile(r"^[ \t]*```[^\n]*\n(.*?)^[ \t]*```[ \t]*$", re.S | re.M)
TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$", re.M)
HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.M)
QUOTE_RE = re.compile(r"^[ \t]{0,3}>[ \t]?", re.M)
BULLET_RE = re.compile(r"^([ \t]*)[-*+][ \t]+", re.M)
RULE_RE = re.compile(r"^[ \t]{0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$", re.M)
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BOLD_RE = re.compile(r"(?<!\w)(\*\*|__)(?=\S)(.+?)(?<=\S)\1(?!\w)", re.M)
POWER_RE = re.compile(r"(?<=\w)\*\*(?=\w)")
POWER_PLACEHOLDER = "\x00pow\x00"
STRAY_BOLD_RE = re.compile(r"\*{2,}(?=\s|$)")
STRAY_TICKS_RE = re.compile(r"`")
STRAY_STRIKE_RE = re.compile(r"~~(?=\s|$)")
STRIKE_RE = re.compile(r"~~(.+?)~~", re.S)
ITALIC_STAR_RE = re.compile(r"(?<!\*)\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)")
ITALIC_UND_RE = re.compile(r"(?<![\w_])_(?!\s)([^_\n]+?)(?<!\s)_(?![\w_])")
INLINE_CODE_RE = re.compile(r"`+([^`\n]*)`+")
BLANKS_RE = re.compile(r"\n{3,}")


def md_to_text(text: str) -> str:
    """Убирает Markdown-разметку, оставляя читаемый текст."""
    if not text:
        return ""

    # р62 (я9): блоки кода в txt — язык отдельной строкой, код в
    # фигурных скобках («python { … }»; без языка — «{ … }»). Блок
    # целиком прячем в плейсхолдер: чистки разметки не трогают код
    # (прежде «#»-комментарии и «**» внутри кода снимались).
    fences: list[str] = []

    def _fence(m) -> str:
        lang = m.group(0).split("\n")[0].strip()[3:].strip()
        head = (lang + "\n") if lang else ""
        fences.append(head + "{\n" + m.group(1).rstrip("\n") + "\n}")
        return "\x00FENCE{}\x00".format(len(fences) - 1)

    text = CODE_FENCE_RE.sub(_fence, text)

    lines = text.split("\n")
    table_rows: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if TABLE_SEP_RE.match(stripped):
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            table_rows.append(" — ".join(c for c in cells if c))
        else:
            table_rows.append(line)
    text = "\n".join(table_rows)

    text = HEADING_RE.sub("", text)
    text = RULE_RE.sub("-" * 60, text)
    text = QUOTE_RE.sub("", text)
    text = BULLET_RE.sub(lambda m: m.group(1) + "• ", text)
    text = IMAGE_RE.sub(lambda m: (m.group(1) or m.group(2)), text)
    text = LINK_RE.sub(lambda m: f"{m.group(1)} ({m.group(2)})", text)
    text = INLINE_CODE_RE.sub(lambda m: m.group(1), text)
    text = POWER_RE.sub(POWER_PLACEHOLDER, text)
    text = BOLD_RE.sub(lambda m: m.group(2), text)
    text = STRIKE_RE.sub(lambda m: m.group(1), text)
    text = STRAY_BOLD_RE.sub("", text)
    text = STRAY_STRIKE_RE.sub("", text)
    text = ITALIC_STAR_RE.sub(lambda m: m.group(1), text)
    text = ITALIC_UND_RE.sub(lambda m: m.group(1), text)
    text = text.replace(POWER_PLACEHOLDER, "**")
    text = STRAY_TICKS_RE.sub("", text)
    text = BLANKS_RE.sub("\n\n", text)
    # р62 (я9): вернуть блоки кода (язык + { … })
    text = re.sub(r"\x00FENCE(\d+)\x00",
                  lambda m: fences[int(m.group(1))], text)
    return text.strip("\n")


def render_tool_md(tool: dict, limit: int) -> str:
    head = f"<details><summary>🔧 {tool['name']} — {tool['status']}</summary>\n"
    parts = [head]
    if tool["input"] not in (None, {}, []):
        # р63 (я4): вызов обрезается тем же лимитом, что и результат
        payload = json.dumps(tool["input"], ensure_ascii=False, indent=2)
        parts.append("\n**" + t("call") + "**\n\n```json\n"
                     + clip(payload, limit) + "\n```\n")
    body = (tool["output"] or "").strip()
    if body:
        parts.append("\n**" + t("result") + "**\n\n```text\n"
                     + clip(body, limit) + "\n```\n")
    parts.append("</details>\n")
    return "".join(parts)


def render_markdown(session, turns, with_tools, with_narration,
                    tool_limit, header=None,
                    stats=None, app_version="") -> str:
    meta = session_meta(session, turns, header)
    out = [f"# {meta['title']}\n\n", "---\n"]
    # р60 (я2): шапка — обычные строки, БЕЗ списка «- **…:**»;
    # р63 (я1): без пустой строки после «Чат:»; р63 (я3): тип чата
    if meta["harness"]:
        out.append(f"{t('harness')}: {meta['harness']}\n")
        out.append(f"{t('project')}: {meta['project'] or t('none')}\n")
        out.append(f"{t('chat')}: {meta['title']}\n")
        out.append(f"{t('chat_type')}: {meta['chat_type'] or t('none')}\n")
    out.append(f"{t('session')}: {meta['id']}\n")
    if meta["directory"]:
        out.append(f"{t('directory')}: {meta['directory']}\n")
    out.append(f"{t('created')}: {meta['created_local']}\n")
    out.append(f"{t('updated')}: {meta['updated_local']}\n")
    out.append(f"{t('messages')}: {meta['requests']} / "
               f"{meta['answers']}{t('messages_qa')}\n")
    files_line = (t("files_attached", n=meta["files_attached"])
                  if meta["files_attached"] else t("none"))
    out.append(f"{t('files_line')}: {files_line}\n")
    out.append(f"{t('models')}: {', '.join(meta['models']) or t('none')}\n")
    for line in token_header_lines(stats):  # р62 (я2)
        out.append(line + "\n")
    out.append(f"{t('exported')}: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
    out.append(exporter_header("md", app_version))  # р62 (я8)
    out.append("\n---\n")

    # р63 (я6): ходы — «###» (самый мелкий заголовок); ответ: сменился
    # источник — «###», повтор того же — жирной строкой.
    # р64 (E1): любой ход-промпт меняет источник (человек/харнесс/копия
    # контекста → ИИ) — после каждого хода ответ снова «###»;
    # жирным — только повтор без промежуточного сообщения
    last_source = None
    for index, turn in enumerate(turns, 1):
        last_source = None
        if turn.get("summary_history"):
            out.append(f"\n### ⟪{t('ctx_summary')}⟫\n\n")
            out.append(turn["request"] + "\n")
            continue
        # р60 (я7): selchat-копия контекста — «Контекст», не «Вы»
        speaker = (t("context_copy") if turn.get("context_copy")
                   else t("system") if turn.get("system") else t("you"))
        out.append(f"\n### {index}. {speaker} — "
                   f"{local_time(turn['request_at'])}\n\n")
        if turn.get("compaction_before"):
            line = t("ctx_boundary") + (
                t("ctx_boundary_tokens", n=turn["compaction_tokens"])
                if turn.get("compaction_tokens") else "")
            out.append(f"> ⟪{line}⟫\n\n")
        if turn.get("fork_note"):
            out.append(f"> ✂ {turn['fork_note']['line']}\n\n")
        out.append((turn["request"] or f"_{t('empty_request')}_") + "\n")
        # р81 (п.4): блоки вложений — всегда (no_files удалён)
        if turn["attachments"]:
            out.append(f"\n**{t('attached')}**\n")
            for item in turn["attachments"]:
                note = ", ".join(x for x in (item["media"],
                                             fmt_size(item.get("size")))
                                 if x)
                out.append(f'- "{item["name"]}"'
                           + (f" ({note})" if note else "") + "\n")
        if with_tools and turn["tools"]:
            out.append(f"\n**{t('tools')}: {len(turn['tools'])}**\n\n")
            for tool in turn["tools"]:
                out.append(render_tool_md(tool, tool_limit) + "\n")
        if with_narration and turn["narration"]:
            # р60 (я4): заголовок как в txt + КАЖДАЯ строка с «> »
            out.append(f"\n**{t('reasoning')}:**\n\n")
            quoted = "\n".join(
                "> " + line if line.strip() else ">"
                for piece in turn["narration"] for line in piece.split("\n"))
            out.append(quoted + "\n")
        for answer in turn["answers"]:
            stamp = local_time(answer["at"])
            suffix = f" — {stamp}" if stamp else ""
            # р60 (я3): время работы модели у ответа (duration_ms)
            secs = turn.get("work_secs")
            if secs:
                suffix += f" ({fmt_duration(secs)})"
            # р50: автор ответа — конкретная модель «GLM-5.3-Flash Max»
            # (субагент — « · Explore»); нет данных — «LLM»;
            # р63 (я6): повтор источника — жирным, не заголовок
            source = turn.get("model") or t("llm_unknown")
            if source == last_source:
                out.append(f"\n**{source}{suffix}**\n\n")
            else:
                out.append(f"\n### {source}{suffix}\n\n")
            last_source = source
            out.append(answer["text"] + "\n")
    return "".join(out)


def render_text(session, turns, with_tools, with_narration,
                tool_limit, header=None,
                stats=None, app_version="") -> str:
    meta = session_meta(session, turns, header)
    out = [f"{meta['title']}\n", underline(meta['title'])]  # р62 (я4)
    if meta["harness"]:
        out.append(f"{t('harness')}: {meta['harness']}\n")
        out.append(f"{t('project')}: {meta['project'] or t('none')}\n")
        out.append(f"{t('chat')}: {meta['title']}\n")
        # р63 (я3): тип чата; пустой — «—»
        out.append(f"{t('chat_type')}: {meta['chat_type'] or t('none')}\n")
    out.append(f"{t('session')}: {meta['id']}\n")
    if meta["directory"]:
        out.append(f"{t('directory')}: {meta['directory']}\n")
    out.append(f"{t('created')}: {meta['created_local']}\n")
    out.append(f"{t('updated')}: {meta['updated_local']}\n")
    out.append(f"{t('messages')}: {meta['requests']} / "
               f"{meta['answers']}{t('messages_qa')}\n")
    files_line = (t("files_attached", n=meta["files_attached"])
                  if meta["files_attached"] else t("none"))
    out.append(f"{t('files_line')}: {files_line}\n")
    out.append(f"{t('models')}: {', '.join(meta['models']) or t('none')}\n")
    for line in token_header_lines(stats):  # р62 (я2)
        out.append(line + "\n")
    # р62 (я7): «Экспорт:» и в txt — как в md; р62 (я8) — строка экспортёра;
    # р63 (я1-я2): рамка из черт завершает шапку
    out.append(f"{t('exported')}: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
    out.append(exporter_header("txt", app_version))
    for index, turn in enumerate(turns, 1):
        if turn.get("summary_history"):
            out.append(f"\n⟪{t('ctx_summary')}⟫\n")
            out.append(underline(f"⟪{t('ctx_summary')}⟫"))  # р62 (я3)
            out.append(md_to_text(turn["request"]) + "\n")
            continue
        speaker = (t("context_copy") if turn.get("context_copy")
                   else t("system") if turn.get("system")
                   else t("you")).upper()
        head = f"[{index}] {speaker} — {local_time(turn['request_at'])}"
        out.append(f"\n{head}\n")
        out.append(underline(head))  # р62 (я3)
        if turn.get("compaction_before"):
            line = t("ctx_boundary") + (
                t("ctx_boundary_tokens", n=turn["compaction_tokens"])
                if turn.get("compaction_tokens") else "")
            out.append(f"  ⟪{line}⟫\n")
        if turn.get("fork_note"):
            out.append(f"  ✂ {turn['fork_note']['line']}\n")
        out.append((md_to_text(turn["request"]) or t("empty_request")) + "\n")
        # р81 (п.4): блоки вложений — всегда (no_files удалён)
        if turn["attachments"]:
            out.append(f"\n{t('attached')}\n")
            for item in turn["attachments"]:
                size_note = fmt_size(item.get("size"))
                out.append(f'  - "{item["name"]}"'
                           + (f" ({size_note})" if size_note else "") + "\n")
        if with_tools and turn["tools"]:
            out.append(f"\n{t('tools')}: {len(turn['tools'])}\n")
            for tool in turn["tools"]:
                out.append(f"  🔧 {tool['name']} — {tool['status']}\n")
                if tool["input"] not in (None, {}, []):
                    # р63 (я4): вызов обрезается тем же лимитом
                    payload = json.dumps(tool["input"], ensure_ascii=False, indent=2)
                    out.append("  " + clip(payload, tool_limit).replace("\n", "\n  ") + "\n")
                if (tool["output"] or "").strip():
                    out.append("  " + clip(tool["output"], tool_limit).replace("\n", "\n  ") + "\n")
        if with_narration and turn["narration"]:
            # р62 (я6): метка «Промежуточные реплики:» — как в txt AutoClaw
            out.append("\n" + t("reasoning") + ":\n")
            narration = [md_to_text(piece) for piece in turn["narration"]]
            out.append("  › " + "\n  › ".join(narration) + "\n")
        for answer in turn["answers"]:
            # р50: имя модели — собственное имя, без КАПСА (как в GUI);
            # фолбэк «LLM» уже верхним регистром
            secs = turn.get("work_secs")  # р60 (я3); р62 (я5): «сек/мин/час»
            time_note = f" ({fmt_duration(secs)})" if secs else ""
            head = (f"{turn.get('model') or t('llm_unknown')} — "
                    f"{local_time(answer['at'])}{time_note}")
            out.append(f"\n{head}\n")
            out.append(underline(head))  # р62 (я3)
            out.append(md_to_text(answer["text"]) + "\n")
    return "".join(out)


def session_payload(session, turns, with_tools, with_narration,
                    tool_limit, header=None,
                    stats=None) -> dict:
    meta = session_meta(session, turns, header)
    # р62 (я2): токены шапки — те же данные, что в строках md/txt
    if stats:
        for key, src in (("context_tokens", "context"),
                         ("total_spent_tokens", "total_spent")):
            value = stats.get(src)
            if value is not None:
                meta[key] = value
    payload_turns = []
    for index, turn in enumerate(turns, 1):
        tools = []
        if with_tools:
            for tool in turn["tools"]:
                tools.append({
                    "name": tool["name"],
                    "status": tool["status"],
                    "input": tool["input"],
                    "output": clip(tool["output"], tool_limit),
                })
        payload_turns.append({
            "index": index,
            "request": {
                "text": turn["request"],
                "at": iso_time(turn["request_at"]),
                "at_local": local_time(turn["request_at"]),
            },
            # р50: автор запроса (человек/харнесс) и модели ответов
            "author": "system" if turn.get("system") else "user",
            "model": turn.get("model") or ("LLM" if turn["answers"] else None),
            "summary_history": bool(turn.get("summary_history")),
            "compaction_before": bool(turn.get("compaction_before")),
            "fork": turn["fork_note"]["line"] if turn.get("fork_note") else "",
            # р81 (п.4): вложения в json — всегда (no_files удалён)
            "attachments": turn["attachments"],
            "answers": [
                {"text": a["text"], "at": iso_time(a["at"]),
                 "at_local": local_time(a["at"])}
                for a in turn["answers"]
            ],
            "tools": tools,
            "narration": turn["narration"] if with_narration else [],
        })
    return {"session": meta, "turns": payload_turns}


def render_json(session, turns, with_tools, with_narration,
                tool_limit, header=None,
                app_version: str = "", stats=None) -> str:
    payload = session_payload(session, turns, with_tools, with_narration,
                              tool_limit, header, stats)
    payload["exported_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    if app_version:  # р60 (я1): подпись экспортёра в json
        payload["exporter"] = {"name": "Z.ai Chats Exporter",
                               "author": "Vadim R.M.",
                               "version": app_version,
                               "url": EXPORTER_URL}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# ------------------------------------------------------------- экспорт

def render_body(session, turns, options: ExportOptions,
                header: dict | None = None,
                stats: dict | None = None) -> str:
    # р81 (п.4): параметр with_files убран — файловые блоки всегда
    if options.fmt == "json":
        return render_json(session, turns, options.tools, options.narration,
                           options.tool_limit, header,
                           options.app_version, stats)
    if options.fmt == "txt":
        return render_text(session, turns, options.tools, options.narration,
                           options.tool_limit, header,
                           stats, options.app_version)
    return render_markdown(session, turns, options.tools, options.narration,
                           options.tool_limit, header,
                           stats, options.app_version)


def use_bom(fmt: str, bom: bool) -> bool:
    """BOM в md/txt по флагу опций (в json невозможен — ER-3, раунд 19)."""
    return bool(bom) and fmt != "json"


def write_export(path: Path, body: str, fmt: str, bom: bool) -> Path:
    path = unique_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8-sig" if use_bom(fmt, bom) else "utf-8")
    return path


def export_one(con, session, out_path: Path,
               options: ExportOptions, header: dict | None = None
               ) -> tuple[Path, int]:
    note = None
    if "fork_note_info" in session.keys():
        note = session["fork_note_info"]
    # р60 (я7): selchat — копия контекста главного чата (не «Вы»)
    is_copy = _is_context_copy(session)  # р60 я7 + р64 E5b (wfchld)
    turns = build_turns(con, session["id"], note,
                        ctx_mode=options.context_view,
                        context_copy=is_copy)
    # р60 (я7): пустой чат (все ходы отфильтрованы чекбоксами) — файл
    # с одной шапкой, БЕЗ ошибки; р60 (я1): футер экспортёра;
    # р62 (я2): токены шапки
    stats = token_stats_zc(con, session["id"]).get(session["id"])
    body = render_body(session, turns, options, header, stats)
    if options.fmt != "json":
        body += exporter_footer(options.fmt, options.app_version)
    path = write_export(out_path, body, options.fmt, options.bom)
    return path, len(turns)


def export_single_file(con, sessions, out_dir: Path,
                       options: ExportOptions, selected: bool = False,
                       project_of=None) -> dict:
    """ER-2: диалоги в ОДИН файл данного формата (пустые пропускаются).

    Я5: между диалогами — двойной разделитель на соседних строках; перед
    каждым диалогом — строка «Новый диалог <проект\\файл>» (Я6).
    selected=True — в файле заголовок «Выбранные диалоги» (раунд 20).
    project_of(session) — резолвер имени проекта (раунд 29); None —
    по директории (project_subdir).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    day = file_date(sessions[0]["time_updated"]) if sessions else "0000-00-00"
    path = unique_path(out_dir / f"ZC-ALL-{day}.{options.fmt}")
    total = 0
    packed = 0
    if options.fmt == "json":
        items = []
        for session in sessions:
            note = session.get("fork_note_info") if isinstance(session, dict) else None
            turns = build_turns(con, session["id"], note,
                                ctx_mode=options.context_view,
                                context_copy=_is_context_copy(session))
            # р64 (E4): пустые чаты тоже попадают в пак (шапка)
            total += len(turns)
            packed += 1
            header = {"harness": "ZCode",
                      "version": session_version(con, session["id"]),
                      "project": (project_of(session) if project_of
                                  else project_subdir(session)),
                      "chat_type": chat_type_of(session)}  # р63 (я3)
            items.append(session_payload(session, turns, options.tools,
                                         options.narration, options.tool_limit,
                                         header,
                                         token_stats_zc(con, session["id"]).get(  # р62
                                             session["id"])))
        payload = {
            "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "sessions": items,
        }
        if options.app_version:  # р60 (я1)
            payload["exporter"] = {"name": "Z.ai Chats Exporter",
                                   "author": "Vadim R.M.",
                                   "version": options.app_version,
                                   "url": EXPORTER_URL}
        body = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    else:
        chunks = []
        for session in sessions:
            note = session.get("fork_note_info") if isinstance(session, dict) else None
            turns = build_turns(con, session["id"], note,
                                ctx_mode=options.context_view,
                                context_copy=_is_context_copy(session))
            # р64 (E4): пустые чаты тоже попадают в пак (шапка)
            total += len(turns)
            packed += 1
            name = build_filename(session, options.fmt)
            # раунд 29: имя проекта — из tasks-index (если резолвер передан)
            raw_sub = (project_of(session) if project_of
                       else project_subdir(session))
            sub = safe_filename(raw_sub) if raw_sub else ""
            rel = f"{sub}\\{name}" if sub else name
            header = t("new_dialog", path=rel) + "\n\n"
            chat_header = {"harness": "ZCode",
                           "version": session_version(con, session["id"]),
                           "project": raw_sub,
                           "chat_type": chat_type_of(session)}  # р63 (я3)
            chat_stats = token_stats_zc(con, session["id"]).get(  # р62 (я2)
                session["id"])
            if options.fmt == "txt":
                chunks.append(header + render_text(session, turns, options.tools,
                                                   options.narration, options.tool_limit,
                                                   chat_header,
                                                   chat_stats, options.app_version))
            else:
                chunks.append(header + render_markdown(session, turns, options.tools,
                                                       options.narration, options.tool_limit,
                                                       chat_header,
                                                       chat_stats, options.app_version))
        if options.fmt == "txt":
            body = ("\n\n" + "=" * 60 + "\n" + "=" * 60 + "\n\n").join(chunks) + "\n"
        else:
            label = t("selected_chats") if selected else t("all_chats")
            body = (f"# {label} ({packed})\n\n"
                    + "\n\n---\n---\n\n".join(chunks)) + "\n"
        body += exporter_footer(options.fmt, options.app_version)  # р60 (я1)
    path.write_text(body,
                    encoding="utf-8-sig" if use_bom(options.fmt, options.bom) else "utf-8")
    return {"path": str(path.resolve()), "sessions": packed, "requests": total}


# ------------------------------------------------------------- адаптер

class ZCodeAdapter:
    """Режим «Zcode Chats»: db.sqlite (таблицы session/message/part).

    Временная копия заблокированной базы (если создавалась) удаляется
    в close(). Язык подписей задаётся на вызов (ExportOptions.lang).
    """

    def __init__(self) -> None:
        self._tmp_dirs: list[Path] = []

    def open(self, db_path) -> sqlite3.Connection:
        db = Path(str(db_path)).expanduser() if db_path else None
        if db is None:
            raise AdapterError(t("err_no_db"))
        if not db.is_file():
            raise AdapterError(t("err_db_missing", p=db))
        con, tmp = connect_ro(db)
        if tmp is not None:
            self._tmp_dirs.append(tmp)
        return con

    def close(self, con: sqlite3.Connection) -> None:
        con.close()
        for tmp in self._tmp_dirs:
            shutil.rmtree(tmp, ignore_errors=True)
        self._tmp_dirs.clear()

    def list_chats(self, con: sqlite3.Connection, index_db=None) -> list[dict]:
        # раунд 29/31: имена проектов — из индекса (путь — «SQL база 2»);
        # раунд 37: скрытость/метка «Тип»; раунд 40: суффиксы форков;
        # раунд 41: архив UI ZCode — tasks.archived из 2-й базы
        info = load_project_index(index_db)
        auto_ids = info.get("auto_sessions") or frozenset()
        archived_ids = info.get("archived_ids") or frozenset()
        deleted_ids = info.get("deleted_ids") or frozenset()  # р48
        session_rows = load_sessions(con)
        fmap = fork_map(con, session_rows)
        usage = usage_tokens(con)  # р43: контекст в токенах (model_usage)
        rows = []
        for s in session_rows:
            label, hidden = session_state(s, auto_ids, archived_ids, deleted_ids)
            row = {
                "id": s["id"],
                "title": s["title"] or "",
                "directory": s["directory"] or "",
                # раунд 24/29/39: проект — прямая связь/корни/tasks-index
                "project": project_for(s, info),
                # раунд 37: скрытые чаты (видны только с чекбоксом) и метка
                "hidden": hidden,
                "type": label,
                "created_at": iso_time(s["time_created"]),
                "updated_at": iso_time(s["time_updated"]),
                "created_local": local_time(s["time_created"]),
                "updated_local": local_time(s["time_updated"]),
                "requests": count_requests(con, s["id"]),
                # р43 (A): последний input_tokens из model_usage
                "tokens": usage.get(s["id"]),
            }
            note = fmap.get(s["id"])
            if note:
                # раунд 40: суффикс форка ВЕЗДЕ (решение владельца)
                row["title"] = row["title"] + note["tag"]
                row["fork_note_info"] = note
            rows.append(row)
        return rows

    def export_chat(self, con: sqlite3.Connection, chat_id: str,
                    out_dir, options: ExportOptions,
                    index_db=None) -> dict:
        global LANG
        LANG = options.lang
        info = load_project_index(index_db)
        session_rows = load_sessions(con)
        session = with_fork_tag(
            pick_session(session_rows, chat_id), fork_map(con, session_rows))
        raw_sub = project_for(session, info)
        sub = safe_filename(raw_sub) if raw_sub else ""
        name = build_filename(session, options.fmt)
        out_path = Path(out_dir) / (Path(sub) / name if sub else name)
        # р51: шапка — харнесс + версия сессии (отдельный запрос), проект;
        # р63 (я3): тип чата (с данными tasks-index)
        header = {"harness": "ZCode",
                  "version": session_version(con, session["id"]),
                  "project": raw_sub,
                  "chat_type": chat_type_of(session, info)}
        path, count = export_one(con, session, out_path, options, header)
        return {"path": str(path.resolve()), "requests": count}

    def export_single_file(self, con: sqlite3.Connection, out_dir,
                           options: ExportOptions, chat_ids=None,
                           include_subagents: bool = False,
                           index_db=None) -> dict:
        """chat_ids=None — все диалоги; список id — только выбранные,
        в порядке передачи (раунд 20: чекбокс «Экспорт в один файл»).
        include_subagents — включать ли СКРЫТЫЕ чаты (раунд 37: del/arch/
        wfchld/selchat/auto; по умолчанию исключены, как в таблице)."""
        global LANG
        LANG = options.lang
        info = load_project_index(index_db)
        auto_ids = info.get("auto_sessions") or frozenset()
        archived_ids = info.get("archived_ids") or frozenset()
        deleted_ids = info.get("deleted_ids") or frozenset()  # р48
        sessions = load_sessions(con)
        fmap = fork_map(con, sessions)
        sessions = [with_fork_tag(s, fmap) for s in sessions]
        if not include_subagents:
            sessions = [s for s in sessions
                        if not is_hidden(s, auto_ids, archived_ids, deleted_ids)]
        if chat_ids is not None:
            by_id = {s["id"]: s for s in sessions}
            sessions = [by_id[cid] for cid in chat_ids if cid in by_id]
        if not sessions:
            raise AdapterError(t("err_no_sessions"))
        return export_single_file(con, sessions, Path(out_dir), options,
                                  chat_ids is not None,
                                  project_of=lambda s: project_for(s, info))
