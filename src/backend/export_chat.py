#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Адаптер AutoClaw: чтение runtime.sqlite (только mode=ro) и экспорт
диалогов в Markdown, TXT и JSON (AGREEMENTS.md, раунд 19).

Было CLI-движком с /api-контрактом; после слияния в один exe — модуль
с классом AutoClawAdapter (интерфейс — backend/adapter.py). Ядро
(загрузка сессий/артефактов, сборка ходов, рендеры, имена AC-*, суффиксы
« (1)») не менялось. Репозиторий (GUI): github.com/vadimrm/Z.ai-ChatsExporter; материнский
CLI-проект: github.com/vadimrm/AutoClaw.Z.ai-ExportChat
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from adapter import AdapterError, ExportOptions

LANG = "ru"

LABELS = {
    "ru": {
        "session": "Сессия",
        "created": "Создана",
        "updated": "Обновлена",
        "messages": "Сообщений",
        "files": "Файлы",
        "harness": "Харнесс",
        "project": "Проект",
        "chat": "Чат",
        "models": "Модели",
        "chat_type": "Тип",
        "none": "—",
        "exported": "Экспорт",
        "you": "Вы",
        "llm_unknown": "LLM",
        "attached": "📎 Вложено:",
        "ready": "📄 Готово к скачиванию:",
        "other": "🗂 Прочие файлы:",
        "attached_txt": "Вложено:",
        "ready_txt": "Готово к скачиванию:",
        "other_txt": "Прочие файлы:",
        "tools": "Инструменты",
        "call": "Вызов",
        "result": "Результат",
        "narration": "Промежуточные реплики",
        # р62 (я2): строки токенов в шапке — формат владельца
        "h_context": "Контекст чата",
        "h_compact": "Автосжатие при",
        "h_spent": "Всего израсходовано",
        "truncated": "… (обрезано, всего {size})",
        "empty_request": "[пустой запрос]",
        "db": "База:",
        "done": "Готово:",
        "conversation": "Диалог:",
        "all_chats": "Все диалоги AutoClaw",
        "selected_chats": "Выбранные диалоги AutoClaw",
        "new_dialog": "Новый диалог {path}",
        "err_db_missing": "Файл базы не найден: {p}",
        "err_no_db": "Не найдена база AutoClaw. Укажите файл runtime.sqlite в поле «SQL база».",
        "err_db_invalid": "В файле нет таблиц диалогов — это не база AutoClaw: {p}",
        "err_no_sessions": "В базе нет ни одного диалога.",
        "err_ambiguous": "Подходит несколько диалогов, уточните:\n{lines}",
        "err_not_found": "Диалог не найден: {needle}",
        "err_empty": "В диалоге нет сообщений: {id}",
        "lbl_done": "Готово: {path}",
        "lbl_conversation": "Диалог: {title}  ({count})",
    },
    "en": {
        "session": "Session",
        "created": "Created",
        "updated": "Updated",
        "messages": "Messages",
        "files": "Files",
        "harness": "Harness",
        "project": "Project",
        "chat": "Chat",
        "models": "Models",
        "none": "—",
        "exported": "Exported",
        "you": "You",
        "llm_unknown": "LLM",
        "attached": "📎 Attached:",
        "ready": "📄 Ready to download:",
        "other": "🗂 Other files:",
        "attached_txt": "Attached:",
        "ready_txt": "Ready to download:",
        "other_txt": "Other files:",
        "tools": "Tools",
        "call": "Call",
        "result": "Result",
        "narration": "Intermediate replies",
        "h_context": "Chat context",
        "h_compact": "Auto-compact at",
        "h_spent": "Total spent",
        "truncated": "… (truncated, {size} total)",
        "empty_request": "[empty request]",
        "db": "Database:",
        "done": "Done:",
        "conversation": "Conversation:",
        "all_chats": "All AutoClaw chats",
        "selected_chats": "Selected AutoClaw chats",
        "new_dialog": "New conversation {path}",
        "err_db_missing": "Database file not found: {p}",
        "err_no_db": "AutoClaw database not found. Set the runtime.sqlite file in the \"SQL database\" field.",
        "err_db_invalid": "No conversation tables in the file — this is not an AutoClaw database: {p}",
        "err_no_sessions": "No conversations found in the database.",
        "err_ambiguous": "Several conversations match, please specify:\n{lines}",
        "err_not_found": "Conversation not found: {needle}",
        "err_empty": "No messages in the conversation: {id}",
        "lbl_done": "Done: {path}",
        "lbl_conversation": "Conversation: {title}  ({count})",
    },
    "zh": {
        "session": "会话",
        "created": "创建时间",
        "updated": "更新时间",
        "messages": "消息",
        "files": "文件",
        "harness": "框架",
        "project": "项目",
        "chat": "对话",
        "models": "模型",
        "none": "—",
        "exported": "导出时间",
        "you": "你",
        "llm_unknown": "LLM",
        "attached": "📎 附件：",
        "ready": "📄 可下载：",
        "other": "🗂 其他文件：",
        "attached_txt": "附件：",
        "ready_txt": "可下载：",
        "other_txt": "其他文件：",
        "tools": "工具调用",
        "call": "调用",
        "result": "结果",
        "narration": "中间回复",
        "h_context": "聊天上下文",
        "h_compact": "自动压缩于",
        "h_spent": "总消耗",
        "truncated": "…（已截断，共 {size}）",
        "empty_request": "[空请求]",
        "db": "数据库：",
        "done": "完成：",
        "conversation": "对话：",
        "all_chats": "全部 AutoClaw 对话",
        "selected_chats": "所选 AutoClaw 对话",
        "new_dialog": "新对话 {path}",
        "err_db_missing": "找不到数据库文件：{p}",
        "err_no_db": "未找到 AutoClaw 数据库。请在“SQL 数据库”字段中指定 runtime.sqlite 文件。",
        "err_db_invalid": "文件中没有对话表——这不是 AutoClaw 数据库：{p}",
        "err_no_sessions": "数据库中没有对话。",
        "err_ambiguous": "匹配到多个对话，请明确指定：\n{lines}",
        "err_not_found": "找不到对话：{needle}",
        "err_empty": "该对话没有消息：{id}",
        "lbl_done": "完成：{path}",
        "lbl_conversation": "对话：{title}  ({count})",
    },
}


def t(key: str, **kwargs) -> str:
    table = LABELS.get(LANG) or LABELS["ru"]
    value = table.get(key) or LABELS["ru"].get(key, key)
    return value.format(**kwargs) if kwargs else value



def file_date(iso: str | None) -> str:
    """Дата создания в формате ГГГГ-ММ-ДД по локальному времени."""
    if not iso:
        return "0000-00-00"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return "0000-00-00"
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"


def safe_filename(title: str, limit: int = 80) -> str:
    """Оставляет название как есть, заменяя только запрещённые в Windows символы."""
    name = re.sub(r'[\\/:*?"<>|]', "_", title or "")
    name = name.replace("\r", " ").replace("\n", " ")
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    if len(name) > limit:
        name = name[:limit].rstrip(". ")
    return name or "chat"


def build_filename(session: sqlite3.Row, fmt: str, used: set[str] | None = None) -> str:
    """Имя вида «AC-2026-09-03 название чата.md» (р36: между датой и
    названием — пробел вместо тире, решение владельца)."""
    base = f"AC-{file_date(session['created_at'])} {safe_filename(session['title'])}"
    name = base
    counter = 2
    while used is not None and name in used:
        name = f"{base}-{counter}"
        counter += 1
    if used is not None:
        used.add(name)
    return f"{name}.{fmt}"


def unique_path(path: Path) -> Path:
    """ER-5: не перезаписывать существующее — суффиксы « (1)», « (2)», …"""
    if not path.exists():
        return path
    counter = 1
    while True:
        candidate = path.parent / f"{path.stem} ({counter}){path.suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def connect(db: Path) -> sqlite3.Connection:
    uri = "file:" + db.as_posix() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def local_time(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return dt.astimezone().strftime("%d.%m.%Y %H:%M")


def load_sessions(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """р48/р49: archived_at — архивные чаты скрыты за чекбоксом (как
    ZCode, р37); р49 — удалённые (deleted_at) ТОЖЕ включаются: скрыты,
    метка «del» (на базе владельца их 2). В старых схемах (нет
    workspace_id/archived_at/deleted_at) вместо колонки NULL —
    проекты/архив/удалённые просто недоступны, список живёт как прежде."""
    try:
        cols = {r[1] for r in con.execute("pragma table_info(work_sessions)")}
    except sqlite3.Error:
        cols = set()
    ws = "workspace_id" if "workspace_id" in cols else "NULL as workspace_id"
    arch = "archived_at" if "archived_at" in cols else "NULL as archived_at"
    delc = "deleted_at" if "deleted_at" in cols else "NULL as deleted_at"
    return list(
        con.execute(
            f"select session_id, title, created_at, updated_at, {ws}, {arch}, "
            f"{delc} from work_sessions "
            "order by updated_at desc"
        )
    )


def workspace_names(con: sqlite3.Connection) -> dict[str, str]:
    """Имена проектов AutoClaw (work_workspaces.display_name); нет таблицы
    или пустое имя — проект не показывается (раунд 24)."""
    names: dict[str, str] = {}
    try:
        for workspace_id, display_name, is_default in con.execute(
            "select workspace_id, display_name, is_default from work_workspaces"
        ):
            name = (display_name or "").strip()
            # раунд 26: воркспейс по умолчанию (is_default=1, «默认项目»)
            # НЕ проект — его чаты считаются одиночными (владелец подтвердил)
            if workspace_id and name and not is_default:
                names[workspace_id] = name
    except sqlite3.Error:
        pass
    return names


def pick_session(sessions: list[sqlite3.Row], needle: str | None) -> sqlite3.Row:
    if not sessions:
        raise AdapterError(t("err_no_sessions"))
    if not needle:
        return sessions[0]

    needle_l = needle.strip().lower()
    exact = [s for s in sessions if s["session_id"] == needle_l]
    if exact:
        return exact[0]
    by_id = [s for s in sessions if s["session_id"].lower().startswith(needle_l)]
    if len(by_id) == 1:
        return by_id[0]
    by_title = [s for s in sessions if needle_l in (s["title"] or "").lower()]
    if len(by_title) == 1:
        return by_title[0]
    if len(by_title) > 1:
        lines = "\n".join(f"  {s['session_id']}  {s['title']}" for s in by_title)
        raise AdapterError(t("err_ambiguous", lines=lines))
    raise AdapterError(t("err_not_found", needle=needle))


def parse_payload(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def text_of_request(data: dict) -> str:
    return (
        data.get("text")
        or strip_attachment_block(data.get("effectivePrompt") or "")
        or data.get("prompt")
        or ""
    ).strip()


ATTACH_MARKER = "Attached workspace files"

ATTACH_ITEM_RE = re.compile(
    r"^- (?P<name>.+?): (?P<path>.+?) \((?P<mime>[^,()]+), (?P<size>\d+) bytes\)\s*$"
)

DIRECTIVE_RE = re.compile(r":zwork-[a-z0-9\-]+\{([^{}]*)\}")
ATTR_RE = re.compile(r"(\w+)\s*=\s*\"([^\"]*)\"")


def extract_citations(text: str) -> tuple[str, list[dict]]:
    """Превращает :zwork-file-citation{...} в кавычки с именем файла."""
    if not text or ":zwork-" not in text:
        return text, []

    citations: list[dict] = []

    def replace(match: re.Match) -> str:
        attrs = dict(ATTR_RE.findall(match.group(1)))
        path = (attrs.get("path") or attrs.get("file") or "").strip()
        if not path:
            return ""
        citations.append(
            {
                "path": path,
                "purpose": attrs.get("purpose") or "",
                "kind": attrs.get("artifact_kind") or "",
            }
        )
        return f'"{path}"'

    lines: list[str] = []
    for line in text.split("\n"):
        if ":zwork-" in line:
            line = DIRECTIVE_RE.sub(replace, line)
            line = re.sub(r"[ \t]{2,}", " ", line).rstrip()
        lines.append(line)
    return "\n".join(lines), citations


def strip_attachment_block(prompt: str) -> str:
    index = prompt.find(ATTACH_MARKER)
    if index < 0:
        return prompt
    return prompt[:index].rstrip()


def parse_attachments(prompt: str) -> list[dict]:
    index = prompt.find(ATTACH_MARKER)
    if index < 0:
        return []
    attachments = []
    for line in prompt[index:].splitlines()[1:]:
        line = line.strip()
        if not line.startswith("- "):
            if attachments:
                break
            continue
        match = ATTACH_ITEM_RE.match(line)
        if not match:
            continue
        attachments.append(
            {
                "name": match.group("name").strip(),
                "path": match.group("path").strip(),
                "media": match.group("mime").strip(),
                "size": int(match.group("size")),
            }
        )
    return attachments


def format_size(size: int | None) -> str:
    if not size or size < 0:
        return ""
    units = {
        "ru": ("Б", "КБ", "МБ", ","),
        "en": ("B", "KB", "MB", "."),
        "zh": ("B", "KB", "MB", "."),
    }
    small, kilo, mega, dot = units.get(LANG, units["en"])
    if size < 1024:
        return f"{size} {small}"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} {kilo}".replace(".", dot)
    return f"{size / (1024 * 1024):.1f} {mega}".replace(".", dot)


def file_kind(name: str) -> str:
    suffix = Path(name).suffix.lower().lstrip(".")
    return suffix or "файл"


def dedupe_files(items: list[dict], key: str = "path") -> list[dict]:
    seen: dict[str, dict] = {}
    order: list[str] = []
    for item in items:
        value = item.get(key) or item.get("name") or ""
        if value not in seen:
            order.append(value)
        seen[value] = item
    return [seen[value] for value in order]


def load_artifacts(con: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = con.execute(
        """
        select artifact_id, tool_call_id, tool_id, display_name, source_path,
               media_type, byte_length, created_at
        from governed_tool_artifacts
        where session_id = ? and artifact_presentation = 'card'
        order by created_at
        """,
        (session_id,),
    )
    artifacts = []
    for row in rows:
        artifacts.append(
            {
                "id": row["artifact_id"],
                "call_id": row["tool_call_id"],
                "tool": row["tool_id"] or "",
                "name": (row["display_name"] or row["source_path"] or "файл").strip(),
                "path": (row["source_path"] or row["display_name"] or "").strip(),
                "media": row["media_type"] or "",
                "size": row["byte_length"] or 0,
                "at": row["created_at"],
                "delivered": (row["tool_id"] or "").endswith("deliver"),
            }
        )
    return artifacts


def build_turns(
    con: sqlite3.Connection, session_id: str, artifacts: list[dict]
) -> list[dict]:
    rows = con.execute(
        """
        select session_seq, entry_type, payload, committed_at
        from neutral_session_entries
        where session_id = ?
        order by session_seq
        """,
        (session_id,),
    )

    turns: list[dict] = []
    current: dict | None = None

    for row in rows:
        entry_type = row["entry_type"]
        payload = parse_payload(row["payload"])
        data = payload.get("data") or {}

        if entry_type == "request":
            prompt = data.get("effectivePrompt") or ""
            request_text, request_citations = extract_citations(text_of_request(data))
            current = {
                "request": request_text,
                "citations": request_citations,
                "request_at": row["committed_at"],
                "attachments": parse_attachments(prompt),
                "answers": [],
                "tools": [],
                "narration": [],
                "call_ids": [],
                "created": [],
            }
            turns.append(current)
            continue

        if current is None:
            continue

        if entry_type == "tool_call":
            call_id = data.get("toolCallId") or ""
            if call_id:
                current["call_ids"].append(call_id)
            current["tools"].append(
                {
                    "name": data.get("toolName") or "tool",
                    "input": data.get("input"),
                    "output": None,
                }
            )
        elif entry_type == "tool_result":
            content = data.get("content")
            if current["tools"] and current["tools"][-1]["output"] is None:
                current["tools"][-1]["output"] = content
        elif entry_type == "assistant":
            blocks = data.get("content")
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                text = ""
                if isinstance(block, str):
                    text = block
                elif isinstance(block, dict) and block.get("type") in (None, "text"):
                    text = block.get("text") or ""
                if text.strip():
                    clean, _ = extract_citations(text.strip())
                    current["narration"].append(clean)
        elif entry_type == "answer":
            text, citations = extract_citations((data.get("text") or "").strip())
            if text:
                current["answers"].append(
                    {"text": text, "at": row["committed_at"], "citations": citations}
                )
                # р50: автор ответа — data.model («zai_auto» → «Auto»,
                # «zai_glm-5.3-flash» → «GLM-5.3-Flash»); effort AutoClaw
                # в данных не пишет — не подписываем (решение владельца)
                current["model"] = ac_model_label(data.get("model"))

    turns = [t for t in turns if t["request"] or t["answers"]]
    assign_artifacts(turns, artifacts)
    return turns


def token_stats_ac(con: sqlite3.Connection,
                   session_id: str | None = None) -> dict[str, dict]:
    """р62 (я2): токен-статистика сессий AutoClaw из work_runs.usage_json
    (ход = run со статусом completed). Все три числа тултипа AC у промптом:
    context/window/compact — ПОСЛЕДНЕГО хода (contextTokens/windowTokens/
    compactAtTokens; напр. 16161/1048576/811622), total_spent — СУММА
    totalTokens по всем ходам («всего израсходовано»; totalTokens одного
    хода = «за этот ход» тултипа). Базы без work_runs → {}."""
    stats: dict[str, dict] = {}
    query = ("select session_id, usage_json from work_runs "
             "where status='completed' and usage_json is not null")
    params: tuple = ()
    if session_id:
        query += " and session_id=?"
        params = (session_id,)
    try:
        rows = con.execute(query + " order by created_at", params)
    except sqlite3.Error:
        return stats
    for sid, raw in rows:
        try:
            usage = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        st = stats.setdefault(sid, {"context": None, "window": None,
                                    "compact": None, "total_spent": 0})
        for key, src in (("context", "contextTokens"),
                         ("window", "windowTokens"),
                         ("compact", "compactAtTokens")):
            value = usage.get(src)
            if isinstance(value, int) and value >= 0:
                st[key] = value
        total = usage.get("totalTokens")
        if isinstance(total, int) and total >= 0:
            st["total_spent"] += total
    return stats


def usage_tokens_ac(con: sqlite3.Connection) -> dict[str, int]:
    """р62 (я2): графа «Ток» AutoClaw = contextTokens последнего
    completed-хода — размер контекста чата. Прежде (р61) ошибочно брали
    totalTokens последнего answer — это расход за ход, а не контекст
    (у тяжёлых чатов 2-30М; владелец указал). Чаты без ходов — пусто."""
    return {sid: st["context"]
            for sid, st in token_stats_ac(con).items()
            if st["context"] is not None}


def ac_answer_secs(turn: dict, answer: dict):
    """р60 (я3): время работы ИИ по answer-данным AutoClaw — от запроса
    хода до ответа (в answer.usage времени нет; проверено на базе).
    ISO-строки; нет/битое → None."""
    try:
        start = datetime.fromisoformat(
            (turn.get("request_at") or "").replace("Z", "+00:00"))
        end = datetime.fromisoformat(
            (answer.get("at") or "").replace("Z", "+00:00"))
        return (end - start).total_seconds()
    except (ValueError, TypeError):
        return None


def ac_model_label(model) -> str:
    """р50: имя модели из answer-данных AutoClaw для подписи — как в его
    GUI: «Auto» (роутер zai_auto, бывает Auto-Fast), «GLM-5.3-Flash».
    model приходит словарём {"model": "zai_auto"} или строкой; префикс
    аккаунта до "_" снимается, сегменты капитализируются (glm → GLM);
    пусто/нет поля → «LLM» (решение владельца)."""
    if isinstance(model, dict):
        model = model.get("model")
    text = str(model or "").strip()
    if not text:
        return "LLM"
    if "_" in text:
        text = text.split("_", 1)[1]
    parts = []
    for seg in text.split("-"):
        parts.append({"glm": "GLM"}.get(seg.lower())
                     or (seg[:1].upper() + seg[1:] if seg else seg))
    return "-".join(parts)


def assign_artifacts(turns: list[dict], artifacts: list[dict]) -> None:
    if not turns or not artifacts:
        return

    by_call: dict[str, list[dict]] = {}
    for artifact in artifacts:
        by_call.setdefault(artifact["call_id"], []).append(artifact)

    used: set[str] = set()
    for turn in turns:
        for call_id in turn["call_ids"]:
            for artifact in by_call.get(call_id, []):
                if artifact["id"] in used:
                    continue
                used.add(artifact["id"])
                turn["created"].append(artifact)

    for artifact in artifacts:
        if artifact["id"] in used:
            continue
        for index, turn in enumerate(turns):
            start = turn["request_at"]
            end = (
                turns[index + 1]["request_at"]
                if index + 1 < len(turns)
                else "9999"
            )
            if start <= artifact["at"] < end:
                turn["created"].append(artifact)
                used.add(artifact["id"])
                break

    for turn in turns:
        turn["created"] = dedupe_files(turn["created"])
        turn["attachments"] = dedupe_files(turn["attachments"])


def plural(n: int, one: str, few: str, many: str) -> str:
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many


def n_requests(n: int) -> str:
    if LANG == "ru":
        return f"{n} {plural(n, 'запрос', 'запроса', 'запросов')}"
    if LANG == "zh":
        return f"{n} 个请求"
    return f"{n} request" if n == 1 else f"{n} requests"


def n_answers(n: int) -> str:
    if LANG == "ru":
        return f"{n} {plural(n, 'ответ', 'ответа', 'ответов')}"
    if LANG == "zh":
        return f"{n} 个回答"
    return f"{n} answer" if n == 1 else f"{n} answers"


def messages_line(requests: int, answers: int) -> str:
    if LANG == "zh":
        return f"{requests} 个请求，{answers} 个回答"
    return f"{n_requests(requests)}, {n_answers(answers)}"


def files_line(attached: int, ready: int, other: int | None = None) -> str:
    # р51 (владелец): файлов нет вовсе — «нет»
    if not attached and not ready and not other:
        return t("none")
    if LANG == "ru":
        text = f"вложено {attached} · готово к скачиванию {ready}"
        if other is not None:
            text += f" · прочих созданных {other}"
        return text
    if LANG == "zh":
        text = f"附件 {attached} · 可下载 {ready}"
        if other is not None:
            text += f" · 其他文件 {other}"
        return text
    text = f"{attached} attached · {ready} ready to download"
    if other is not None:
        text += f" · {other} other files"
    return text




EXPORTER_URL = "https://www.vmgames.com"


def exporter_line(fmt: str, version: str) -> str:
    """р63 (я2): строка экспортёра — md с кликабельным линком,
    txt с URL текстом (через 2 пробела)."""
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
    (рамка завершает шапку — разделитель «-»×60 больше не нужен)."""
    if not version:
        return ""
    line = exporter_line(fmt, version)
    if fmt == "md":
        return "\n" + line + "\n"
    rule = "-" * len(line)
    return "\n" + rule + "\n" + line + "\n" + rule + "\n"


def fmt_num(n: int) -> str:
    """р62 (я2): тысячи с разделителем — «16 161» (ru/zh), «16,161» (en)."""
    if LANG == "en":
        return f"{n:,}"
    return f"{n:,}".replace(",", " ")


def fmt_window(n: int) -> str:
    """р62 (я2): окно контекста — «1М» (1048576), «512К»; en/zh — латиница."""
    unit_m, unit_k = ("М", "К") if LANG == "ru" else ("M", "K")
    if n >= 1048576:
        value = n / 1048576
        text = f"{value:.1f}".replace(".0", "")
        return f"{text}{unit_m}"
    return f"{round(n / 1024)}{unit_k}"


def fmt_compact_k(n: int) -> str:
    """р62 (я2): порог автосжатия в К с округлением — 811622 → «812 К»
    (формат владельца; К = 1000, как в GUI AutoClaw). Меньше 1000 — как есть."""
    if n < 1000:
        return fmt_num(n)
    unit = "К" if LANG == "ru" else "K"
    return f"{round(n / 1000)} {unit}"


def fmt_pct(part: int, whole: int) -> str:
    """р62 (я2): процент — одна десятая <10% («1.5%»), иначе целый («77%»)."""
    pct = part / whole * 100
    if pct < 10:
        return f"{pct:.1f}%"
    return f"{round(pct)}%"


def n_tokens(n: int) -> str:
    """р62 (я2): «32 362 токена» — с падежом (ru); en — token/tokens."""
    if LANG == "ru":
        return f"{fmt_num(n)} {plural(n, 'токен', 'токена', 'токенов')}"
    if LANG == "en":
        return f"{fmt_num(n)} token" if n == 1 else f"{fmt_num(n)} tokens"
    return fmt_num(n)


def token_header_lines(st: dict | None) -> list[str]:
    """р62 (я2): строки токенов шапки — формат владельца:
    «Контекст чата: 16 161 из 1М (1.5%)» / «Автосжатие при: 812 К (77%)» /
    «Всего израсходовано: 32 362 токена». Строка без данных опускается;
    st=None/пусто — нет строк. Для ZCode (окна/порога нет) — те же строки
    без «из NМ (...)» и без автосжатия — та же функция в его модуле."""
    if not st:
        return []
    lines: list[str] = []
    context = st.get("context")
    if context is not None:
        window = st.get("window")
        if window:
            if LANG == "zh":
                value = f"{fmt_num(context)} / {fmt_window(window)}（{fmt_pct(context, window)}）"
            elif LANG == "en":
                value = f"{fmt_num(context)} of {fmt_window(window)} ({fmt_pct(context, window)})"
            else:
                value = f"{fmt_num(context)} из {fmt_window(window)} ({fmt_pct(context, window)})"
        else:
            value = fmt_num(context)
        lines.append(f"{t('h_context')}: {value}")
    compact = st.get("compact")
    if compact is not None:
        window = st.get("window")
        pct = f" ({fmt_pct(compact, window)})" if window else ""
        lines.append(f"{t('h_compact')}: {fmt_compact_k(compact)}{pct}")
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


def human_size(text: str) -> str:
    return f"{len(text)} симв."


def render_tool(tool: dict, limit: int) -> str:
    head = f"<details><summary>🔧 {tool['name']}</summary>\n"
    parts = [head]
    if tool["input"] not in (None, {}, []):
        # р63 (я4): вызов обрезается тем же лимитом, что и результат
        payload = _clip(json.dumps(tool["input"], ensure_ascii=False,
                                   indent=2), limit)
        parts.append("\n**" + t("call") + "**\n\n```json\n" + payload + "\n```\n")
    output = tool["output"]
    if isinstance(output, str) and output.strip():
        body = output.strip()
    elif output is not None:
        body = json.dumps(output, ensure_ascii=False, indent=2)
    else:
        body = ""
    if body:
        parts.append("\n**" + t("result") + "**\n\n```text\n"
                     + _clip(body, limit) + "\n```\n")
    parts.append("</details>\n")
    return "".join(parts)


def session_meta(session: sqlite3.Row, turns: list[dict],
                 header: dict | None = None) -> dict:
    """р51: header — {"harness": "AutoClaw", "version": None,
    "project": имя}; модели — порядок появления по ходам."""
    header = header or {}
    version = (header.get("version") or "").strip()
    harness = header.get("harness") or ""
    models: list[str] = []
    for turn in turns:
        label = turn.get("model")
        if turn["answers"] and label and label not in models:
            models.append(label)
    attached = dedupe_files([a for t in turns for a in t["attachments"]])
    files = dedupe_files([f for t in turns for f in t["created"]])
    # р63 (я3): тип чата — как в графе «Тип» GUI (del/arch; обычный — "")
    chat_type = ("del" if session["deleted_at"] is not None
                 else "arch" if session["archived_at"] is not None else "")
    return {
        "id": session["session_id"],
        "title": (session["title"] or "").strip() or "AutoClaw",
        "harness": (f"{harness} {version}".strip() if harness else ""),
        "project": header.get("project") or "",
        "chat_type": chat_type,
        "models": models,
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "created_local": local_time(session["created_at"]),
        "updated_local": local_time(session["updated_at"]),
        "requests": len(turns),
        "answers": sum(len(t["answers"]) for t in turns),
        "attachments": attached,
        "files": files,
        "delivered": [f for f in files if f["delivered"]],
        # р60: для JSON-шапки (паритет с ZCode)
        "files_attached": len(attached),
    }


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


def text_file_row(item: dict) -> str:
    return (
        f'  - "{item["name"]}" ({file_kind(item["name"])}, '
        f"{format_size(item['size'])})\n"
    )


def md_file_row(item: dict) -> str:
    meta = ", ".join(
        part
        for part in (file_kind(item["name"]), format_size(item["size"]))
        if part
    )
    return f'- "{item["name"]}" — {meta}\n'


def _clip(body: str, limit: int) -> str:
    """р63 (я4): обрезка длинного текста с припиской «(обрезано, …)» —
    теперь и для ВЫЗОВА инструмента, не только результата."""
    cut = body[:limit]
    if len(body) > limit:
        cut += "\n" + t("truncated", size=human_size(body))
    return cut


def _tool_body(tool: dict, limit: int) -> str:
    """Текст результата инструмента с обрезкой (для txt/json, ER-4)."""
    output = tool["output"]
    if isinstance(output, str) and output.strip():
        body = output.strip()
    elif output is not None:
        body = json.dumps(output, ensure_ascii=False, indent=2)
    else:
        return ""
    return _clip(body, limit)


def underline(line: str) -> str:
    """р62 (я3/я4): строка из «-» длиной в заголовок — txt-замена
    крупного шрифта md-заголовков; длина по символам строки."""
    return "-" * len(line.rstrip()) + "\n"


def render_text(
    session: sqlite3.Row,
    turns: list[dict],
    with_tools: bool = False,
    with_narration: bool = False,
    tool_limit: int = 4000,
    all_files: bool = False,
    header: dict | None = None,
    stats: dict | None = None,
    app_version: str = "",
) -> str:
    meta = session_meta(session, turns, header)
    out: list[str] = []
    out.append(f"{meta['title']}\n")
    out.append(underline(meta['title']))  # р62 (я4)
    if meta["harness"]:
        out.append(f"{t('harness')}: {meta['harness']}\n")
        out.append(f"{t('project')}: {meta['project'] or t('none')}\n")
        out.append(f"{t('chat')}: {meta['title']}\n")
        # р63 (я3): тип чата; пустой — «—»
        out.append(f"{t('chat_type')}: {meta['chat_type'] or t('none')}\n")
    out.append(f"{t('session')}: {meta['id']}\n")
    out.append(f"{t('created')}: {meta['created_local']}\n")
    out.append(f"{t('updated')}: {meta['updated_local']}\n")
    out.append(
        f"{t('messages')}: {messages_line(meta['requests'], meta['answers'])}\n"
    )
    out.append(
        f"{t('files')}: "
        f"{files_line(len(meta['attachments']), len(meta['delivered']))}\n"
    )
    out.append(f"{t('models')}: {', '.join(meta['models']) or t('none')}\n")
    for line in token_header_lines(stats):  # р62 (я2)
        out.append(line + "\n")
    # р62 (я7): «Экспорт:» и в txt — как в md; р62 (я8) — строка экспортёра;
    # р63 (я1-я2): рамка из черт завершает шапку (без пустой строки после
    # «Чат:», с пустой перед строкой экспортёра)
    out.append(f"{t('exported')}: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
    out.append(exporter_header("txt", app_version))

    for index, turn in enumerate(turns, 1):
        head = f"[{index}] {t('you').upper()} — {local_time(turn['request_at'])}"
        out.append(f"\n{head}\n")
        out.append(underline(head))  # р62 (я3)
        out.append((md_to_text(turn["request"]) or t("empty_request")) + "\n")
        # р81 (п.4): блоки вложений — всегда (no_files удалён)
        if turn["attachments"]:
            out.append("\n" + t("attached_txt") + "\n")
            for item in turn["attachments"]:
                out.append(text_file_row(item))

        if with_tools and turn["tools"]:
            out.append("\n" + t("tools") + f": {len(turn['tools'])}\n")
            for tool in turn["tools"]:
                out.append(f"  🔧 {tool['name']}\n")
                if tool["input"] not in (None, {}, []):
                    # р63 (я4): вызов обрезается тем же лимитом
                    payload = _clip(json.dumps(tool["input"],
                                               ensure_ascii=False,
                                               indent=2), tool_limit)
                    out.append("  " + payload.replace("\n", "\n  ") + "\n")
                body = _tool_body(tool, tool_limit)
                if body:
                    out.append("  " + body.replace("\n", "\n  ") + "\n")

        if with_narration and turn["narration"]:
            out.append("\n" + t("narration") + ":\n")
            for piece in turn["narration"]:
                out.append("  › " + md_to_text(piece).replace("\n", "\n  › ") + "\n")

        for answer in turn["answers"]:
            stamp = local_time(answer["at"])
            # р50: автор ответа — модель («Auto», «GLM-5.3-Flash»); нет
            # поля — «LLM» (решение владельца)
            # р60 (я3): время работы ИИ у ответа; р62 (я5): «сек/мин/час»
            secs = ac_answer_secs(turn, answer)
            time_note = f" ({fmt_duration(secs)})" if secs else ""
            head = (f"{turn.get('model') or t('llm_unknown')} — "
                    f"{stamp}{time_note}")
            out.append(f"\n{head}\n")
            out.append(underline(head))  # р62 (я3)
            out.append(md_to_text(answer["text"]) + "\n")

        # р81 (п.4): созданные файлы — всегда (no_files удалён);
        # «Прочие» — по-прежнему только при all_files
        if turn["created"]:
            delivered = [f for f in turn["created"] if f["delivered"]]
            other = [f for f in turn["created"] if not f["delivered"]]
            if delivered:
                out.append("\n" + t("ready_txt") + "\n")
                for item in delivered:
                    out.append(text_file_row(item))
            if all_files and other:
                out.append("\n" + t("other_txt") + "\n")
                for item in other:
                    out.append(text_file_row(item))

    return "".join(out)


def session_payload(
    session: sqlite3.Row,
    turns: list[dict],
    with_tools: bool = False,
    with_narration: bool = False,
    tool_limit: int = 4000,
    all_files: bool = False,
    header: dict | None = None,
    stats: dict | None = None,
) -> dict:
    """Структура одного диалога для JSON (и упаковки /single-file, ER-2)."""
    meta = session_meta(session, turns, header)
    payload = {
        "session": {
            key: meta[key]
            for key in (
                "id",
                "title",
                # р51/р60: блок шапки — как в md/txt (прежде не попадал)
                "harness",
                "project",
                "chat_type",
                "models",
                "created_at",
                "updated_at",
                "created_local",
                "updated_local",
                "requests",
                "answers",
                "files_attached",
            )
            if key in meta
        },
        "turns": [],
    }
    # р62 (я2): токены шапки — те же данные, что в строках md/txt
    if stats:
        for key, src in (("context_tokens", "context"),
                         ("context_window", "window"),
                         ("compact_at_tokens", "compact"),
                         ("total_spent_tokens", "total_spent")):
            value = stats.get(src)
            if value is not None:
                payload["session"][key] = value
    for index, turn in enumerate(turns, 1):
        # р81 (п.4): вложения/созданные файлы — всегда (no_files удалён);
        # в json «Прочие» — только при all_files (как в md/txt)
        created = ([f for f in turn["created"] if f["delivered"]]
                   if not all_files else turn["created"])
        payload["turns"].append(
            {
                "index": index,
                "request": {
                    "text": turn["request"],
                    "at": turn["request_at"],
                    "at_local": local_time(turn["request_at"]),
                    "citations": turn.get("citations", []),
                },
                # р50: модель-автор ответа («Auto», «GLM-5.3-Flash», «LLM»)
                "model": turn.get("model") or ("LLM" if turn["answers"] else None),
                "attachments": turn["attachments"],
                "answers": [
                    {
                        "text": a["text"],
                        "at": a["at"],
                        "at_local": local_time(a["at"]),
                        "citations": a.get("citations", []),
                    }
                    for a in turn["answers"]
                ],
                "files": [
                    {
                        "name": f["name"],
                        "path": f["path"],
                        "kind": file_kind(f["name"]),
                        "size": f["size"],
                        "delivered": f["delivered"],
                        "at": f["at"],
                    }
                    for f in created
                ],
                "tools": [
                    {
                        "name": tool["name"],
                        "input": tool["input"],
                        "output": _tool_body(tool, tool_limit),
                    }
                    for tool in (turn["tools"] if with_tools else [])
                ],
                "narration": turn["narration"] if with_narration else [],
            }
        )
    return payload


def render_json(
    session: sqlite3.Row,
    turns: list[dict],
    with_tools: bool = False,
    with_narration: bool = False,
    tool_limit: int = 4000,
    all_files: bool = False,
    header: dict | None = None,
    app_version: str = "",
    stats: dict | None = None,
) -> str:
    payload = session_payload(session, turns, with_tools, with_narration,
                              tool_limit, all_files, header,
                              stats)
    payload["exported_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    if app_version:  # р60 (я1)
        payload["exporter"] = {"name": "Z.ai Chats Exporter",
                               "author": "Vadim R.M.",
                               "version": app_version,
                               "url": EXPORTER_URL}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_markdown(
    session: sqlite3.Row,
    turns: list[dict],
    with_tools: bool,
    with_narration: bool,
    tool_limit: int,
    all_files: bool = False,
    header: dict | None = None,
    stats: dict | None = None,
    app_version: str = "",
) -> str:
    title = (session["title"] or "").strip() or "AutoClaw"
    meta51 = session_meta(session, turns, header)
    answers = sum(len(t["answers"]) for t in turns)
    attached_all = dedupe_files([a for t in turns for a in t["attachments"]])
    created_all = dedupe_files([f for t in turns for f in t["created"]])
    delivered_all = [f for f in created_all if f["delivered"]]
    other_all = [f for f in created_all if not f["delivered"]]

    out: list[str] = []
    out.append(f"# {title}\n\n")
    out.append("---\n")
    # р60 (я2): шапка — обычные строки, БЕЗ списка «- **…:**»;
    # р63 (я1): без пустой строки после «Чат:»; р63 (я3): тип чата
    if meta51["harness"]:
        out.append(f"{t('harness')}: {meta51['harness']}\n")
        out.append(f"{t('project')}: {meta51['project'] or t('none')}\n")
        out.append(f"{t('chat')}: {title}\n")
        out.append(f"{t('chat_type')}: {meta51['chat_type'] or t('none')}\n")
    out.append(f"{t('session')}: {session['session_id']}\n")
    out.append(f"{t('created')}: {local_time(session['created_at'])}\n")
    out.append(f"{t('updated')}: {local_time(session['updated_at'])}\n")
    out.append(f"{t('messages')}: {messages_line(len(turns), answers)}\n")
    files_text = files_line(
        len(attached_all),
        len(delivered_all),
        len(other_all) if all_files else None,
    )
    out.append(f"{t('files')}: {files_text}\n")
    out.append(f"{t('models')}: {', '.join(meta51['models']) or t('none')}\n")
    for line in token_header_lines(stats):  # р62 (я2)
        out.append(line + "\n")
    out.append(
        f"{t('exported')}: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
    )
    out.append(exporter_header("md", app_version))  # р62 (я8)
    out.append("\n---\n")

    # р63 (я6): промпты человека — «###»; ответ: сменился источник —
    # «###», повтор того же (модель/effort) — жирной строкой.
    # р64 (E1): ЛЮБОЙ ход-промпт меняет источник (человек → ИИ) —
    # после каждого промпта ответ снова «###»; жирным — только
    # повтор БЕЗ промежуточного сообщения (несколько ответов подряд)
    last_source = None
    for index, turn in enumerate(turns, 1):
        last_source = None
        out.append(
            f"\n### {index}. {t('you')} — {local_time(turn['request_at'])}\n\n"
        )
        out.append((turn["request"] or f"_{t('empty_request')}_") + "\n")

        # р81 (п.4): блоки вложений — всегда (no_files удалён)
        if turn["attachments"]:
            out.append(f"\n**{t('attached')}**\n")
            for item in turn["attachments"]:
                out.append(md_file_row(item))

        if with_tools and turn["tools"]:
            out.append(f"\n**{t('tools')}: {len(turn['tools'])}**\n\n")
            for tool in turn["tools"]:
                out.append(render_tool(tool, tool_limit) + "\n")

        if with_narration and turn["narration"]:
            # р60 (я4): КАЖДАЯ строка реплик с «> »;
            # р62 (я6): метка «Промежуточные реплики:» — прежде её не было
            out.append(f"\n**{t('narration')}:**\n\n")
            quoted = "\n".join(
                "> " + line if line.strip() else ">"
                for piece in turn["narration"] for line in piece.split("\n"))
            out.append(quoted + "\n")

        for answer in turn["answers"]:
            stamp = local_time(answer["at"])
            suffix = f" — {stamp}" if stamp else ""
            # р60 (я3): время работы ИИ у ответа (ход: запрос → ответ);
            # р62 (я5): единицы «сек/мин/час»
            secs = ac_answer_secs(turn, answer)
            if secs:
                suffix += f" ({fmt_duration(secs)})"
            # р50/я4: модель из answer-данных; р63 (я6): первый ответ
            # источника — «###», повтор — жирным
            source = turn.get("model") or t("llm_unknown")
            if source == last_source:
                out.append(f"\n**{source}{suffix}**\n\n")
            else:
                out.append(f"\n### {source}{suffix}\n\n")
            last_source = source
            out.append(answer["text"] + "\n")

        # р81 (п.4): созданные файлы — всегда (no_files удалён);
        # «Прочие» — по-прежнему только при all_files
        if turn["created"]:
            delivered = [f for f in turn["created"] if f["delivered"]]
            other = [f for f in turn["created"] if not f["delivered"]]
            if delivered:
                out.append(f"\n**{t('ready')}**\n")
                for item in delivered:
                    out.append(md_file_row(item))
            if all_files and other:
                out.append(f"\n**{t('other')}**\n")
                for item in other:
                    out.append(md_file_row(item))

    return "".join(out)


def use_bom(fmt: str, bom: bool) -> bool:
    """BOM в md/txt по флагу опций (в json невозможен — ER-3, раунд 19)."""
    return bool(bom) and fmt != "json"


def export_one(
    con: sqlite3.Connection,
    session: sqlite3.Row,
    out_path: Path,
    with_tools: bool,
    with_narration: bool,
    tool_limit: int,
    all_files: bool = False,
    fmt: str = "md",
    bom: bool = True,
    header: dict | None = None,
    app_version: str = "",
) -> tuple[Path, int]:
    artifacts = load_artifacts(con, session["session_id"])
    turns = build_turns(con, session["session_id"], artifacts)
    stats = token_stats_ac(con, session["session_id"]).get(  # р62 (я2)
        session["session_id"])
    # р60 (я7): пустой чат — файл с одной шапкой, БЕЗ ошибки
    # р81 (п.4): параметр with_files убран — файловые блоки всегда
    if fmt == "json":
        body = render_json(session, turns, with_tools, with_narration,
                           tool_limit, all_files, header,
                           app_version, stats)
    elif fmt == "txt":
        body = render_text(session, turns, with_tools, with_narration,
                           tool_limit, all_files, header,
                           stats, app_version)
        body += exporter_footer(fmt, app_version)  # р60 (я1)
    else:
        body = render_markdown(
            session, turns, with_tools, with_narration, tool_limit,
            all_files, header, stats, app_version
        )
        body += exporter_footer(fmt, app_version)  # р60 (я1)
    out_path = unique_path(out_path)  # ER-5: не перезаписывать существующее
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        body,
        encoding="utf-8-sig" if use_bom(fmt, bom) else "utf-8",
    )
    return out_path, len(turns)


class AutoClawAdapter:
    """Режим «AutoClaw Chats»: runtime.sqlite (work_sessions + neutral_session_entries).

    Язык подписей экспортируемых файлов задаётся на каждый вызов
    (ExportOptions.lang устанавливает модульный LANG). Вызовы идут только
    из рабочего потока job_runner — гонок на LANG нет.
    """

    def open(self, db_path) -> sqlite3.Connection:
        db = Path(str(db_path)).expanduser() if db_path else None
        if db is None:
            raise AdapterError(t("err_no_db"))
        if not db.is_file():
            raise AdapterError(t("err_db_missing", p=db))
        con = connect(db)
        if con.execute(
            "select 1 from sqlite_master where type = 'table' and name = 'work_sessions'"
        ).fetchone() is None:
            # Чужой/сломанный файл: понятная ошибка вместо traceback «no such table».
            con.close()
            raise AdapterError(t("err_db_invalid", p=db))
        return con

    def close(self, con: sqlite3.Connection) -> None:
        con.close()

    def list_chats(self, con: sqlite3.Connection, index_db=None) -> list[dict]:
        names = workspace_names(con)
        ctx = usage_tokens_ac(con)  # р61: «Ток» — totalTokens ответов
        rows = []
        for s in load_sessions(con):
            turns = con.execute(
                "select count(*) from neutral_session_entries "
                "where session_id=? and entry_type='request'",
                (s["session_id"],),
            ).fetchone()[0]
            rows.append({
                "id": s["session_id"],
                "title": s["title"],
                # р61: контекст чата = usage.totalTokens последнего
                # answer (GUI AC: «Контекст 7.5%/1М»)
                "tokens": ctx.get(s["session_id"]),
                # раунд 24/26: проект = display_name НЕ-дефолтного
                # workspace; вне проекта — пустая строка; субагентов
                # в списке AutoClaw нет; р48/49: archived_at/deleted_at —
                # скрытый чат, метка «arch»/«del» (чекбокс «Показывать
                # скрытые»); иных типов у AutoClaw нет (visibility всегда
                # private, external_chat_type/draft пусты — р49)
                "project": names.get(s["workspace_id"], ""),
                "hidden": s["deleted_at"] is not None
                          or s["archived_at"] is not None,
                "type": ("del" if s["deleted_at"] is not None
                         else "arch" if s["archived_at"] is not None else ""),
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
                "created_local": local_time(s["created_at"]),
                "updated_local": local_time(s["updated_at"]),
                "requests": turns,
            })
        return rows

    def export_chat(self, con: sqlite3.Connection, chat_id: str,
                    out_dir, options: ExportOptions, index_db=None) -> dict:
        global LANG
        LANG = options.lang
        names = workspace_names(con)
        sessions = load_sessions(con)
        session = pick_session(sessions, chat_id)
        out_dir = Path(out_dir)
        # раунд 25/29: чат в workspace — субпапка проекта (как Я6 у ZCode);
        # вне workspace — корень папки экспорта. Пустое имя проекта НЕ
        # превращать в папку: safe_filename("") даёт заглушку «chat»
        # (баг 1.29b/1.30b — папка «chat» у одиночных чатов)
        raw_sub = names.get(session["workspace_id"], "")
        sub = safe_filename(raw_sub) if raw_sub else ""
        out_path = out_dir / (Path(sub) / build_filename(session, options.fmt)
                              if sub else build_filename(session, options.fmt))
        # р51: шапка — харнесс (версии в данных AutoClaw нет), проект
        header = {"harness": "AutoClaw", "version": None, "project": raw_sub}
        path, count = export_one(
            con,
            session,
            out_path,
            options.tools,
            options.narration,
            options.tool_limit,
            options.all_files,
            options.fmt,
            options.bom,
            header,
            options.app_version,  # р60 (я1): футер
        )
        return {"path": str(path.resolve()), "requests": count}

    def export_single_file(self, con: sqlite3.Connection, out_dir,
                           options: ExportOptions, chat_ids=None,
                           include_subagents: bool = False,
                           index_db=None) -> dict:
        """ER-2: диалоги в ОДИН файл формата (пустые пропускаются).

        chat_ids=None — все диалоги; список id — только выбранные, в порядке
        передачи (раунд 20: чекбокс «Экспорт в один файл» в GUI).
        """
        global LANG
        LANG = options.lang
        names = workspace_names(con)
        sessions = load_sessions(con)
        # р49: скрытые (del/arch) — как в ZCode: исключены, если не
        # попросили include_subagents
        if not include_subagents:
            sessions = [s for s in sessions
                        if s["deleted_at"] is None
                        and s["archived_at"] is None]
        if chat_ids is not None:
            by_id = {s["session_id"]: s for s in sessions}
            sessions = [by_id[cid] for cid in chat_ids if cid in by_id]
        if not sessions:
            raise AdapterError(t("err_no_sessions"))
        pack_label = t("selected_chats") if chat_ids is not None else t("all_chats")
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = unique_path(
            out_dir / f"AC-ALL-{file_date(sessions[0]['created_at'])}.{options.fmt}")
        total = 0
        packed = 0
        if options.fmt == "json":
            items = []
            for s in sessions:
                artifacts = load_artifacts(con, s["session_id"])
                turns = build_turns(con, s["session_id"], artifacts)
                # р64 (E4): пустые чаты тоже попадают в пак (шапка),
                # как в отдельном экспорте
                total += len(turns)
                packed += 1
                items.append(session_payload(
                    s, turns, options.tools, options.narration, options.tool_limit,
                    options.all_files,
                    {"harness": "AutoClaw", "version": None,
                     "project": names.get(s["workspace_id"], "")},
                    token_stats_ac(con, s["session_id"]).get(  # р62 (я2)
                        s["session_id"])))
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
            for s in sessions:
                artifacts = load_artifacts(con, s["session_id"])
                turns = build_turns(con, s["session_id"], artifacts)
                # р64 (E4): пустые чаты тоже попадают в пак (шапка),
                # как в отдельном экспорте
                total += len(turns)
                packed += 1
                # раунд 25/29: в метке — проект\\файл (паритет с ZCode,
                # Я5/Я6); пустое имя проекта — без префикса
                name = build_filename(s, options.fmt)
                raw_sub = names.get(s["workspace_id"], "")
                sub = safe_filename(raw_sub) if raw_sub else ""
                rel = f"{sub}\\{name}" if sub else name
                label = t("new_dialog", path=rel)
                chat_header = {"harness": "AutoClaw", "version": None,
                               "project": raw_sub}
                chat_stats = token_stats_ac(con, s["session_id"]).get(  # р62 (я2)
                    s["session_id"])
                if options.fmt == "txt":
                    chunks.append(label + "\n\n" + render_text(
                        s, turns, options.tools, options.narration, options.tool_limit,
                        options.all_files, chat_header,
                        chat_stats, options.app_version))
                else:
                    chunks.append(label + "\n\n" + render_markdown(
                        s, turns, options.tools, options.narration, options.tool_limit,
                        options.all_files, chat_header,
                        chat_stats, options.app_version))
            if options.fmt == "txt":
                body = ("\n\n" + "=" * 60 + "\n" + "=" * 60 + "\n\n").join(chunks) + "\n"
            else:
                # pack_label, а не label: внутри цикла label — метка чата
                body = (f"# {pack_label} ({packed})\n\n"
                        + "\n\n---\n---\n\n".join(chunks)) + "\n"
            body += exporter_footer(options.fmt, options.app_version)  # р60
        path.write_text(
            body,
            encoding="utf-8-sig" if use_bom(options.fmt, options.bom) else "utf-8",
        )
        return {"path": str(path.resolve()), "sessions": packed, "requests": total}
