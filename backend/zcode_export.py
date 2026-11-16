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
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from adapter import AdapterError, ExportOptions

LANG = "ru"

TOOL_IN_MAX = 1200  # фиксированная обрезка входа инструмента (json-дамп)

LABELS = {
    "ru": {
        "session": "Сессия",
        "directory": "Каталог",
        "created": "Создана",
        "updated": "Обновлена",
        "messages": "Сообщений",
        "you": "Вы",
        "assistant": "ZCode",
        "attached": "📎 Вложено:",
        "tools": "Инструменты",
        "call": "Вызов",
        "result": "Результат",
        "reasoning": "Промежуточные реплики",
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
    },
    "en": {
        "session": "Session",
        "directory": "Directory",
        "created": "Created",
        "updated": "Updated",
        "messages": "Messages",
        "you": "You",
        "assistant": "ZCode",
        "attached": "📎 Attached:",
        "tools": "Tools",
        "call": "Call",
        "result": "Result",
        "reasoning": "Intermediate replies",
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
    },
    "zh": {
        "session": "会话",
        "directory": "目录",
        "created": "创建时间",
        "updated": "更新时间",
        "messages": "消息",
        "you": "你",
        "assistant": "ZCode",
        "attached": "📎 附件：",
        "tools": "工具调用",
        "call": "调用",
        "result": "结果",
        "reasoning": "中间回复",
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


def safe_filename(title: str, limit: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", title or "")
    name = name.replace("\r", " ").replace("\n", " ")
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    if len(name) > limit:
        name = name[:limit].rstrip(". ")
    return name or "chat"


def project_subdir(session: sqlite3.Row) -> str:
    """Я6: подпапка проекта — последний компонент session.directory."""
    directory = (session["directory"] or "").strip()
    if not directory:
        return ""
    return safe_filename(Path(directory).name)


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


def build_filename(session: sqlite3.Row, fmt: str, used: set[str] | None = None) -> str:
    base = f"ZC-{file_date(session['time_created'])}-{safe_filename(session['title'])}"
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
    """Диалоги пользователя: интерактивные сессии, без служебных сабагентов."""
    return list(
        con.execute(
            """
            select id, title, directory, time_created, time_updated
            from session
            where time_deleted is null
              and coalesce(task_type, '') <> 'subagent_child'
            order by time_updated desc
            """
        )
    )


def count_requests(con: sqlite3.Connection, session_id: str) -> int:
    return con.execute(
        "select count(*) from message where session_id = ? "
        "and json_extract(data, '$.role') = 'user'",
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


def build_turns(con: sqlite3.Connection, session_id: str) -> list[dict]:
    """Ходы: запрос пользователя -> ответы/инструменты/реплики до следующего."""
    messages = con.execute(
        "select id, data, time_created from message where session_id = ? "
        "order by sequence",
        (session_id,),
    )
    turns: list[dict] = []
    current: dict | None = None
    for mid, raw, created in messages:
        data = parse_payload(raw)
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
            }
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
                current["attachments"].append({
                    "name": part.get("filename") or part.get("url") or "file",
                    "path": part.get("url") or "",
                    "media": part.get("mime") or "",
                })
    turns = [turn for turn in turns if turn["request"] or turn["answers"]]
    return turns


def session_meta(session: sqlite3.Row, turns: list[dict]) -> dict:
    answers = sum(len(x["answers"]) for x in turns)
    return {
        "id": session["id"],
        "title": (session["title"] or "").strip() or "ZCode chat",
        "directory": session["directory"] or "",
        "created_at": iso_time(session["time_created"]),
        "updated_at": iso_time(session["time_updated"]),
        "created_local": local_time(session["time_created"]),
        "updated_local": local_time(session["time_updated"]),
        "requests": len(turns),
        "answers": answers,
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

    text = CODE_FENCE_RE.sub(lambda m: m.group(1).rstrip("\n"), text)

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
    return text.strip("\n")


def render_tool_md(tool: dict, limit: int) -> str:
    head = f"<details><summary>🔧 {tool['name']} — {tool['status']}</summary>\n"
    parts = [head]
    if tool["input"] not in (None, {}, []):
        payload = json.dumps(tool["input"], ensure_ascii=False, indent=2)
        parts.append("\n**" + t("call") + "**\n\n```json\n"
                     + clip(payload, TOOL_IN_MAX) + "\n```\n")
    body = (tool["output"] or "").strip()
    if body:
        parts.append("\n**" + t("result") + "**\n\n```text\n"
                     + clip(body, limit) + "\n```\n")
    parts.append("</details>\n")
    return "".join(parts)


def render_markdown(session, turns, with_tools, with_narration,
                    tool_limit, with_files=True) -> str:
    meta = session_meta(session, turns)
    out = [f"# {meta['title']}\n\n", "---\n"]
    out.append(f"- **{t('session')}:** `{meta['id']}`\n")
    if meta["directory"]:
        out.append(f"- **{t('directory')}:** `{meta['directory']}`\n")
    out.append(f"- **{t('created')}:** {meta['created_local']}\n")
    out.append(f"- **{t('updated')}:** {meta['updated_local']}\n")
    out.append(f"- **{t('messages')}:** {meta['requests']} / {meta['answers']}\n")
    out.append(f"- **Экспорт:** {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
    out.append("\n---\n")

    for index, turn in enumerate(turns, 1):
        out.append(f"\n## {index}. {t('you')} — "
                   f"{local_time(turn['request_at'])}\n\n")
        out.append((turn["request"] or f"_{t('empty_request')}_") + "\n")
        if with_files and turn["attachments"]:
            out.append(f"\n**{t('attached')}**\n")
            for item in turn["attachments"]:
                note = ", ".join(x for x in (item["media"],) if x)
                out.append(f'- "{item["name"]}"'
                           + (f" ({note})" if note else "") + "\n")
        if with_tools and turn["tools"]:
            out.append(f"\n**{t('tools')}: {len(turn['tools'])}**\n\n")
            for tool in turn["tools"]:
                out.append(render_tool_md(tool, tool_limit) + "\n")
        if with_narration and turn["narration"]:
            out.append("\n> " + "\n>\n> ".join(turn["narration"]) + "\n")
        for answer in turn["answers"]:
            stamp = local_time(answer["at"])
            suffix = f" — {stamp}" if stamp else ""
            out.append(f"\n### {t('assistant')}{suffix}\n\n")
            out.append(answer["text"] + "\n")
    return "".join(out)


def render_text(session, turns, with_tools, with_narration,
                tool_limit, with_files=True) -> str:
    meta = session_meta(session, turns)
    out = [f"{meta['title']}\n\n"]
    out.append(f"{t('session')}: {meta['id']}\n")
    if meta["directory"]:
        out.append(f"{t('directory')}: {meta['directory']}\n")
    out.append(f"{t('created')}: {meta['created_local']}\n")
    out.append(f"{t('updated')}: {meta['updated_local']}\n")
    out.append(f"{t('messages')}: {meta['requests']} / {meta['answers']}\n")
    out.append("\n" + "-" * 60 + "\n")
    for index, turn in enumerate(turns, 1):
        out.append(f"\n[{index}] {t('you').upper()} — {local_time(turn['request_at'])}\n")
        out.append((md_to_text(turn["request"]) or t("empty_request")) + "\n")
        if with_files and turn["attachments"]:
            out.append(f"\n{t('attached')}\n")
            for item in turn["attachments"]:
                out.append(f'  - "{item["name"]}"\n')
        if with_tools and turn["tools"]:
            out.append(f"\n{t('tools')}: {len(turn['tools'])}\n")
            for tool in turn["tools"]:
                out.append(f"  🔧 {tool['name']} — {tool['status']}\n")
                if tool["input"] not in (None, {}, []):
                    payload = json.dumps(tool["input"], ensure_ascii=False, indent=2)
                    out.append("  " + clip(payload, TOOL_IN_MAX).replace("\n", "\n  ") + "\n")
                if (tool["output"] or "").strip():
                    out.append("  " + clip(tool["output"], tool_limit).replace("\n", "\n  ") + "\n")
        if with_narration and turn["narration"]:
            narration = [md_to_text(piece) for piece in turn["narration"]]
            out.append("\n  › " + "\n  › ".join(narration) + "\n")
        for answer in turn["answers"]:
            out.append(f"\n{t('assistant').upper()} — {local_time(answer['at'])}\n")
            out.append(md_to_text(answer["text"]) + "\n")
    return "".join(out)


def session_payload(session, turns, with_tools, with_narration,
                    tool_limit, with_files=True) -> dict:
    meta = session_meta(session, turns)
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
            "attachments": turn["attachments"] if with_files else [],
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
                tool_limit, with_files=True) -> str:
    payload = session_payload(session, turns, with_tools, with_narration,
                              tool_limit, with_files)
    payload["exported_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# ------------------------------------------------------------- экспорт

def render_body(session, turns, options: ExportOptions) -> str:
    if options.fmt == "json":
        return render_json(session, turns, options.tools, options.narration,
                            options.tool_limit, not options.no_files)
    if options.fmt == "txt":
        return render_text(session, turns, options.tools, options.narration,
                           options.tool_limit, not options.no_files)
    return render_markdown(session, turns, options.tools, options.narration,
                           options.tool_limit, not options.no_files)


def use_bom(fmt: str, bom: bool) -> bool:
    """BOM в md/txt по флагу опций (в json невозможен — ER-3, раунд 19)."""
    return bool(bom) and fmt != "json"


def write_export(path: Path, body: str, fmt: str, bom: bool) -> Path:
    path = unique_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8-sig" if use_bom(fmt, bom) else "utf-8")
    return path


def load_turns(con, session) -> list[dict]:
    turns = build_turns(con, session["id"])
    if not turns:
        raise AdapterError(t("err_empty", id=session["id"]))
    return turns


def export_one(con, session, out_path: Path,
               options: ExportOptions) -> tuple[Path, int]:
    turns = load_turns(con, session)
    path = write_export(out_path, render_body(session, turns, options),
                        options.fmt, options.bom)
    return path, len(turns)


def export_single_file(con, sessions, out_dir: Path,
                       options: ExportOptions, selected: bool = False) -> dict:
    """ER-2: диалоги в ОДИН файл данного формата (пустые пропускаются).

    Я5: между диалогами — двойной разделитель на соседних строках; перед
    каждым диалогом — строка «Новый диалог <проект\\файл>» (Я6).
    selected=True — в файле заголовок «Выбранные диалоги» (раунд 20).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    day = file_date(sessions[0]["time_updated"]) if sessions else "0000-00-00"
    path = unique_path(out_dir / f"ZC-ALL-{day}.{options.fmt}")
    total = 0
    packed = 0
    if options.fmt == "json":
        items = []
        for session in sessions:
            turns = build_turns(con, session["id"])
            if not turns:
                continue
            total += len(turns)
            packed += 1
            items.append(session_payload(session, turns, options.tools,
                                         options.narration, options.tool_limit,
                                         not options.no_files))
        body = json.dumps({
            "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "sessions": items,
        }, ensure_ascii=False, indent=2) + "\n"
    else:
        chunks = []
        for session in sessions:
            turns = build_turns(con, session["id"])
            if not turns:
                continue
            total += len(turns)
            packed += 1
            name = build_filename(session, options.fmt)
            sub = project_subdir(session)
            rel = f"{sub}\\{name}" if sub else name
            header = t("new_dialog", path=rel) + "\n\n"
            if options.fmt == "txt":
                chunks.append(header + render_text(session, turns, options.tools,
                                                   options.narration, options.tool_limit,
                                                   not options.no_files))
            else:
                chunks.append(header + render_markdown(session, turns, options.tools,
                                                       options.narration, options.tool_limit,
                                                       not options.no_files))
        if options.fmt == "txt":
            body = ("\n\n" + "=" * 60 + "\n" + "=" * 60 + "\n\n").join(chunks) + "\n"
        else:
            label = t("selected_chats") if selected else t("all_chats")
            body = (f"# {label} ({packed})\n\n"
                    + "\n\n---\n---\n\n".join(chunks)) + "\n"
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

    def list_chats(self, con: sqlite3.Connection) -> list[dict]:
        return [{
            "id": s["id"],
            "title": s["title"],
            "directory": s["directory"] or "",
            "created_at": iso_time(s["time_created"]),
            "updated_at": iso_time(s["time_updated"]),
            "created_local": local_time(s["time_created"]),
            "updated_local": local_time(s["time_updated"]),
            "requests": count_requests(con, s["id"]),
        } for s in load_sessions(con)]

    def export_chat(self, con: sqlite3.Connection, chat_id: str,
                    out_dir, options: ExportOptions) -> dict:
        global LANG
        LANG = options.lang
        session = pick_session(load_sessions(con), chat_id)
        sub = project_subdir(session)
        name = build_filename(session, options.fmt)
        out_path = Path(out_dir) / (Path(sub) / name if sub else name)
        path, count = export_one(con, session, out_path, options)
        return {"path": str(path.resolve()), "requests": count}

    def export_single_file(self, con: sqlite3.Connection, out_dir,
                           options: ExportOptions, chat_ids=None) -> dict:
        """chat_ids=None — все диалоги; список id — только выбранные,
        в порядке передачи (раунд 20: чекбокс «Экспорт в один файл»)."""
        global LANG
        LANG = options.lang
        sessions = load_sessions(con)
        if chat_ids is not None:
            by_id = {s["id"]: s for s in sessions}
            sessions = [by_id[cid] for cid in chat_ids if cid in by_id]
        if not sessions:
            raise AdapterError(t("err_no_sessions"))
        return export_single_file(con, sessions, Path(out_dir), options,
                                  chat_ids is not None)
