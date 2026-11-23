# -*- coding: utf-8 -*-
"""Матричный тест комбинаций опций (раунд 27) на ФИКСТУРНЫХ базах.

Проверяет автоматизированно то, что раньше проверял владелец руками:
для каждого режима (AutoClaw/ZCode) × всех комбинаций опций
(tools/narration/all_files/bom — 16 с р81: no_files удалён) × 3 форматов выполняется
экспорт одного известного чата и проверяются инварианты содержимого
(наличие/отсутствие блоков инструментов/реплик/файлов, BOM по-форматно).
Затем — инварианты списка чатов по фикстуре ZCode: проект, Tasks без
проекта, флаг субагентов (раунд 26), и паковки «в один файл».

Фикстуры — маленькие sqlite с той же схемой, которую читают адаптеры;
содержимое помечено маркерами (REQUEST-/ANSWER-/TOOLMARK-/NARRATION-/
ATTACH-/CRE-), поэтому утверждения точные. Реальные базы не используются.
Запуск: python frontend\\tests\\test_matrix.py
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from adapter import ExportOptions, adapter_for  # noqa: E402

PASS_COUNT = 0
FAIL_COUNT = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  FAIL  {name} — {detail}")


def combo_check(name: str, issues: list[str]) -> None:
    global PASS_COUNT, FAIL_COUNT
    if issues:
        FAIL_COUNT += 1
        FAILURES.append(f"{name}: " + "; ".join(issues))
        print(f"  FAIL  {name} — {'; '.join(issues[:4])}")
    else:
        PASS_COUNT += 1


# ------------------------------------------------------------- фикстуры

def make_autoclaw_fixture(db: Path) -> None:
    con = sqlite3.connect(db)
    con.executescript("""
        create table work_sessions (
            session_id text primary key, title text, created_at text,
            updated_at text, deleted_at text, workspace_id text,
            archived_at text);
        create table work_workspaces (
            workspace_id text primary key, display_name text, is_default int);
        create table neutral_session_entries (
            session_id text, session_seq int, entry_type text,
            payload text, committed_at text);
        create table governed_tool_artifacts (
            artifact_id text primary key, session_id text, tool_call_id text,
            tool_id text, display_name text, source_path text,
            media_type text, byte_length int, created_at text,
            artifact_presentation text);
        create table work_runs (
            session_id text, status text, created_at text, usage_json text);
    """)
    con.execute("insert into work_workspaces values ('wsdef', '默认项目', 1)")
    con.execute("insert into work_workspaces values ('wsproj', 'Материнский проект', 0)")
    # три чата: не-дефолтный воркспейс, дефолтный, архивный (р48)
    con.execute("insert into work_sessions values ('fmain', 'Фикстура чат', "
                "'2026-01-01T10:00:00Z', '2026-01-02T10:00:00Z', NULL, "
                "'wsproj', NULL)")
    # р63 (я6): чат с повторами источника ответа
    con.execute("insert into work_sessions values ('frep', 'Фикстура повтор', "
                "'2026-01-06T10:00:00Z', '2026-01-06T10:02:00Z', NULL, "
                "'wsdef', NULL)")
    con.execute("insert into work_sessions values ('fdef', 'Фикстура дефолт', "
                "'2026-01-01T10:00:00Z', '2026-01-03T10:00:00Z', NULL, "
                "'wsdef', NULL)")
    con.execute("insert into work_sessions values ('farch', 'Фикстура архив', "
                "'2026-01-01T10:00:00Z', '2026-01-04T10:00:00Z', NULL, "
                "'wsproj', '2026-01-04T12:00:00Z')")
    # р49: удалённый чат AutoClaw (на базе владельца их 2)
    con.execute("insert into work_sessions values ('fdel', 'Фикстура удалён', "
                "'2026-01-01T10:00:00Z', '2026-01-05T10:00:00Z', "
                "'2026-01-05T11:00:00Z', 'wsproj', NULL)")
    entries = [
        ("fmain", 1, "request", json.dumps({"data": {
            "effectivePrompt": "REQUEST-MARK\nAttached workspace files\n"
                               "- ATTACH-NAME.txt: C:/x/ATTACH-NAME.txt "
                               "(text/plain, 10 bytes)"}}),
         "2026-01-02T10:00:00Z"),
        ("fmain", 2, "tool_call", json.dumps({"data": {
            "toolName": "TOOLMARK-tool", "toolCallId": "call1",
            "input": {"cmd": "x"}}}), "2026-01-02T10:00:01Z"),
        ("fmain", 3, "tool_result", json.dumps({"data": {
            "content": "TOOL-RESULT-MARK"}}), "2026-01-02T10:00:02Z"),
        ("fmain", 4, "assistant", json.dumps({"data": {"content": [
            {"type": "text", "text": "NARRATION-MARK"}]}}),
         "2026-01-02T10:00:03Z"),
        # р50: model в answer-данных → подпись «GLM-5.3-Flash»;
        # р61: usage.totalTokens → графа «Ток»
        ("fmain", 5, "answer", json.dumps({"data": {
            "text": "ANSWER-MARK",
            "model": {"model": "zai_glm-5.3-flash"},
            "usage": {"inputTokens": 13492, "outputTokens": 3407,
                      "totalTokens": 165507}}}),
         "2026-01-02T10:00:04Z"),
        ("fdef", 1, "request", json.dumps({"data": {
            "effectivePrompt": "DEF-REQUEST-MARK"}}), "2026-01-03T10:00:00Z"),
        # р50: роутер → «Auto» (как в GUI AutoClaw); р61: usage
        ("fdef", 2, "answer", json.dumps({"data": {
            "text": "DEF-ANSWER-MARK",
            "model": {"model": "zai_auto"},
            "usage": {"inputTokens": 500, "outputTokens": 60,
                      "totalTokens": 560}}}), "2026-01-03T10:00:01Z"),
        # р63 (я6): повторы источника — Auto, Auto (повтор), Flash
        ("frep", 1, "request", json.dumps({"data": {
            "effectivePrompt": "REP-REQ-1"}}), "2026-01-06T10:00:00Z"),
        ("frep", 2, "answer", json.dumps({"data": {
            "text": "REP-ANS-1", "model": {"model": "zai_auto"},
            "usage": {"totalTokens": 100}}}), "2026-01-06T10:00:01Z"),
        ("frep", 3, "request", json.dumps({"data": {
            "effectivePrompt": "REP-REQ-2"}}), "2026-01-06T10:01:00Z"),
        ("frep", 4, "answer", json.dumps({"data": {
            "text": "REP-ANS-2", "model": {"model": "zai_auto"},
            "usage": {"totalTokens": 100}}}), "2026-01-06T10:01:01Z"),
        ("frep", 5, "request", json.dumps({"data": {
            "effectivePrompt": "REP-REQ-3"}}), "2026-01-06T10:02:00Z"),
        ("frep", 6, "answer", json.dumps({"data": {
            "text": "REP-ANS-3", "model": {"model": "zai_glm-5.3-flash"},
            "usage": {"totalTokens": 100}}}), "2026-01-06T10:02:01Z"),
        # р64 (E1): два ответа ПОДРЯД в одном ходе — второй жирный
        ("frep", 7, "request", json.dumps({"data": {
            "effectivePrompt": "REP-REQ-4"}}), "2026-01-06T10:03:00Z"),
        ("frep", 8, "answer", json.dumps({"data": {
            "text": "REP-ANS-4", "model": {"model": "zai_auto"},
            "usage": {"totalTokens": 100}}}), "2026-01-06T10:03:01Z"),
        ("frep", 9, "answer", json.dumps({"data": {
            "text": "REP-ANS-5", "model": {"model": "zai_auto"},
            "usage": {"totalTokens": 100}}}), "2026-01-06T10:03:02Z"),
    ]
    con.executemany("insert into neutral_session_entries values (?,?,?,?,?)",
                    entries)
    # р62 (я2): work_runs.usage_json — источник «Ток»/строк шапки.
    # fmain: ход 1 без contextTokens (старые данные), ход 2 полный;
    # fdef: порог автосжатия кодинг-модели (635 К); fdel — без ходов;
    # fmain run со статусом stopped — игнорируется.
    con.executemany("insert into work_runs values (?,?,?,?)", [
        ("fmain", "completed", "2026-01-02T10:00:03Z",
         json.dumps({"totalTokens": 90000})),
        ("fmain", "stopped", "2026-01-02T10:00:03Z",
         json.dumps({"contextTokens": 1, "totalTokens": 777777})),
        ("fmain", "completed", "2026-01-02T10:00:04Z",
         json.dumps({"contextTokens": 16161, "windowTokens": 1048576,
                     "compactAtTokens": 811622, "totalTokens": 165507})),
        ("fdef", "completed", "2026-01-03T10:00:01Z",
         json.dumps({"contextTokens": 555, "windowTokens": 1048576,
                     "compactAtTokens": 635494, "totalTokens": 560})),
    ])
    con.executemany(
        "insert into governed_tool_artifacts values (?,?,?,?,?,?,?,?,?,?)", [
            ("a1", "fmain", "call1", "filesystem.deliver", "CRE-READY-MARK.txt",
             "CRE-READY-MARK.txt", "text/plain", 100,
             "2026-01-02T10:00:05Z", "card"),
            ("a2", "fmain", "call1", "filesystem.write", "CRE-SERVICE-MARK.txt",
             "CRE-SERVICE-MARK.txt", "text/plain", 50,
             "2026-01-02T10:00:06Z", "card"),
        ])
    con.commit()
    con.close()


def make_index_fixture(db: Path) -> None:
    """Фикстура 2-й базы (tasks-index, р39): прямая связь tasks.project_id,
    фильтры deleted/archived, дубли task_id, приоритет корней
    is_primary → position → длина."""
    con = sqlite3.connect(db)
    con.executescript("""
        create table projects (project_id text primary key, name text,
            deleted int default 0);
        create table tasks (workspace_key text, task_id text,
            project_id text, deleted int default 0, archived int default 0,
            updated_at int);
        create table project_roots (project_id text, root_path text,
            position int, is_primary int);
    """)
    con.executemany("insert into projects values (?,?,?)", [
        ("P1", "Прямой проект", 0),
        ("P2", "Длинный", 0),
        ("P3", "Главный", 0),
        ("P6", "Проект удалён", 1),
    ])
    con.executemany("insert into tasks values (?,?,?,?,?,?)", [
        ("wk1", "zmain", "P1", 0, 0, 10),   # прямая связь — сильнее корней
        ("wk1", "ztask", "P1", 1, 0, 10),   # задача deleted → имя не выдаётся
        ("wk1", "zarch", "P1", 0, 1, 10),   # задача archived → имя не выдаётся
        ("wk1", "zdup", "P2", 0, 0, 10),    # дубль task_id, старее
        ("wk2", "zdup", "P1", 0, 0, 20),    # дубль task_id, свежее — выигрывает
        ("wk1", "zov", "P6", 0, 0, 10),     # проект deleted → связь пропускается
        ("wk1", "zf1b", "P1", 0, 1, 10),    # р41: архив UI — форк скрыт (arch)
        # р48 (база владельца): UI удалил задачу — deleted=1 И archived=1
        ("wk1", "zdelidx", "P1", 1, 1, 10),
    ])
    con.executemany("insert into project_roots values (?,?,?,?)", [
        ("P2", "C:\\proj\\alpha\\sub\\deep", 0, 0),  # длинный, НЕ primary
        ("P3", "C:\\proj\\alpha", 0, 1),             # короткий, primary
    ])
    con.commit()
    con.close()


def make_zcode_fixture(db: Path) -> None:
    con = sqlite3.connect(db)
    con.executescript("""
        create table session (
            id text primary key, title text, directory text,
            time_created int, time_updated int, time_deleted int,
            time_archived int, task_type text, parent_id text);
        create table message (
            id text primary key, session_id text, sequence int,
            data text, time_created int);
        create table part (
            message_id text, sequence int, data text);
        create table session_purge (session_id text primary key, state text);
        create table model_usage (id text primary key, session_id text,
            input_tokens int, started_at int, assistant_message_id text,
            model_id text, variant text, agent text, duration_ms int,
            provider_total_tokens int, computed_total_tokens int);
    """)
    t0 = 1767225600000  # фиксированный epoch-ms
    # (id, title, directory, created, updated, time_deleted, time_archived,
    #  task_type, parent_id) — р37: del/arch; р40: fork-цепочка
    rows = [
        ("zmain", "Фикстура ZC чат", "C:\\proj\\alpha", t0, t0 + 1000,
         None, None, "interactive", None),
        ("ztask", "Фикстура Task", "C:\\Users\\Anyone\\.zcode\\workspace\\draft-x",
         t0, t0 + 2000, None, None, "interactive", None),
        ("zsub", "Фикстура субагент", "C:\\proj\\alpha", t0, t0 + 3000,
         None, None, "workflow_child", None),
        ("zdel", "Фикстура удалённая", "C:\\proj\\alpha", t0, t0 + 4000,
         t0 + 5000, None, "interactive", None),
        ("zpurge", "Фикстура в purge", "C:\\proj\\alpha", t0, t0 + 4500,
         None, None, "interactive", None),
        ("zarch", "Фикстура архивная", "C:\\proj\\alpha", t0, t0 + 6000,
         None, t0 + 7000, "interactive", None),
        ("zfork", "Фикстура форк", "C:\\proj\\alpha", t0, t0 + 8000,
         None, None, "fork", None),
        ("zwfprnt", "Фикстура wf-родитель", "C:\\proj\\alpha", t0, t0 + 9000,
         None, None, "workflow_parent", None),
        # р39: для индексной фикстуры (прямая связь/корни/дубли)
        ("zdup", "Фикстура дубль", "C:\\proj\\alpha", t0, t0 + 10000,
         None, None, "interactive", None),
        ("zov", "Фикстура корни", "C:\\proj\\alpha\\sub\\deep", t0,
         t0 + 11000, None, None, "interactive", None),
        # р40: форки — zf1/zf1b братья zmain, zf2 — форк форка
        ("zf1", "Фикстура форк1", "C:\\proj\\alpha", t0, t0 + 12000,
         None, None, "fork", "zmain"),
        ("zf1b", "Фикстура форк1б", "C:\\proj\\alpha", t0, t0 + 13000,
         None, None, "fork", "zmain"),
        ("zf2", "Фикстура форк2", "C:\\proj\\alpha", t0, t0 + 14000,
         None, None, "fork", "zf1"),
        # р60: selchat-копия контекста (user model-only БЕЗ synthetic)
        ("zsel", "Фикстура selchat", "C:\\proj\\alpha", t0, t0 + 16000,
         None, None, "selection_side_chat", None),
        # р48: удаление ТОЛЬКО в tasks-index (time_deleted ещё не доехал)
        ("zdelidx", "Фикстура удалена в индексе", "C:\\proj\\alpha",
         t0, t0 + 15000, None, None, "interactive", None),
        # р62 (я10): смена effort по ходу чата — две записи в «Модели»
        ("zeffort", "Фикстура effort", "C:\\proj\\alpha", t0, t0 + 17000,
         None, None, "interactive", None),
    ]
    con.executemany("insert into session values (?,?,?,?,?,?,?,?,?)", rows)
    con.execute("insert into session_purge values ('zpurge', 'pending')")
    msgs = [
        ("m1", "zmain", 1, json.dumps({"role": "user"}), t0),
        ("m2", "zmain", 2, json.dumps({"role": "assistant"}), t0 + 500),
        ("m3", "ztask", 1, json.dumps({"role": "user"}), t0),
        ("m4", "ztask", 2, json.dumps({"role": "assistant"}), t0 + 500),
        ("m5", "zsub", 1, json.dumps({"role": "user"}), t0),
        ("m6", "zsub", 2, json.dumps({"role": "assistant"}), t0 + 500),
        # р40: форки — скопированная история zf1, контент zf2, уведомления
        ("m7", "zf1", 1, json.dumps({"role": "user"}), t0 + 100),
        ("m8", "zf1", 2, json.dumps({"role": "assistant"}), t0 + 200),
        ("m9", "zf2", 2, json.dumps({"role": "user"}), t0 + 300),
        ("m10", "zf1", 3, json.dumps({
            "role": "user", "synthetic": True, "source": "fork",
            "metadata": {"forkContext": {"kind": "session_fork",
                                         "parentSessionId": "zmain",
                                         "targetMessageId": "m1"}}}), t0 + 400),
        ("m11", "zf1b", 1, json.dumps({
            "role": "user", "synthetic": True, "source": "fork"}), t0 + 500),
        ("m12", "zf2", 1, json.dumps({
            "role": "user", "synthetic": True, "source": "fork",
            "metadata": {"forkContext": {"kind": "session_fork",
                                         "parentSessionId": "zf1",
                                         "targetMessageId": "m7"}}}), t0 + 600),
        # р43: модельный контекст zmain — model-only, хвост, сводка
        ("m13", "zmain", 4, json.dumps({
            "role": "user", "synthetic": True, "source": "todo_reminder",
            "visibility": "model-only"}), t0 + 700),
        ("m14", "zmain", 3, json.dumps({"role": "user"}), t0 + 800),
        ("mS", "zmain", 5, json.dumps({"role": "user"}), t0 + 900),
        # р49: автор по флагу synthetic — системная вставка харнесса
        ("m15", "ztask", 2, json.dumps({
            "role": "user", "synthetic": True,
            "visibility": "model-only"}), t0 + 1600),
        # р49: человеческая model-only реплика (без synthetic — как в
        # базе владельца: русский текст владельца с visibility=model-only)
        ("m16", "ztask", 3, json.dumps({
            "role": "user", "visibility": "model-only"}),
         t0 + 1700),
        # р60: selchat — копия запроса человека из главного чата
        # (model-only, synthetic НЕТ) + ответ + вставка харнесса
        ("ms1", "zsel", 1, json.dumps({"role": "user",
                                     "visibility": "model-only"}), t0 + 16100),
        ("ms2", "zsel", 2, json.dumps({"role": "assistant"}), t0 + 16200),
        ("ms3", "zsel", 3, json.dumps({"role": "user", "synthetic": True,
                                     "visibility": "model-only"}), t0 + 16300),
        # р50: ответ zf2 БЕЗ строки model_usage → подпись «LLM»
        ("ma9", "zf2", 3, json.dumps({"role": "assistant"}), t0 + 350),
        # р62 (я10): два хода zeffort — ответ max, потом high
        ("me1", "zeffort", 1, json.dumps({"role": "user"}), t0 + 17100),
        ("me2", "zeffort", 2, json.dumps({"role": "assistant"}), t0 + 17200),
        ("me3", "zeffort", 3, json.dumps({"role": "user"}), t0 + 17300),
        ("me4", "zeffort", 4, json.dumps({"role": "assistant"}), t0 + 17400),
        # р63 (я6): третий ход — та же модель/effort (high) → повтор
        ("me5", "zeffort", 5, json.dumps({"role": "user"}), t0 + 17500),
        ("me6", "zeffort", 6, json.dumps({"role": "assistant"}), t0 + 17600),
    ]
    con.executemany("insert into message values (?,?,?,?,?)", msgs)
    parts = [
        ("m1", 1, json.dumps({"type": "text", "text": "REQUEST-MARK-Z"})),
        # р49: размер вложения — metadata.sizeBytes (62464 → «61 КБ»)
        ("m1", 2, json.dumps({"type": "file", "filename": "ATTACH-NAME-Z.txt",
                              "url": "C:/x/ATTACH-NAME-Z.txt",
                              "mime": "text/plain",
                              "metadata": {"sizeBytes": 62464}})),
        ("m2", 1, json.dumps({"type": "reasoning", "text":
            "NARRATION-MARK-Z\n```js\nvar x = 1;\n```"})),
        ("ms1", 1, json.dumps({"type": "text", "text": "SEL-COPY-MARK"})),
        ("ms2", 1, json.dumps({"type": "text", "text": "SEL-ANSWER-MARK"})),
        ("ms3", 1, json.dumps({"type": "text", "text": "SEL-SYS-MARK"})),
        ("m2", 2, json.dumps({"type": "tool", "tool": "TOOLMARK-Z",
                              "state": {"status": "done", "input": {"a": 1},
                                        "output": "TOOL-RESULT-MARK-Z"}})),
        ("m2", 3, json.dumps({"type": "text", "text": "ANSWER-MARK-Z"})),
        # р43: compaction-граница в zmain — хвост с m2, сводка в mS
        ("m2", 4, json.dumps({"type": "compaction",
                              "tail_start_id": "m14",
                              "summaryMessageId": "mS",
                              "preCompactTokenCount": 150000})),
        ("m13", 1, json.dumps({"type": "text", "text": "CTX-ONLY-MARK"})),
        ("m14", 1, json.dumps({"type": "text", "text": "POST-COMPACT-MARK"})),
        ("mS", 1, json.dumps({"type": "text", "text": "SUMMARY-MARK-ZC"})),
        ("m3", 1, json.dumps({"type": "text", "text": "TASK-REQUEST-MARK"})),
        ("m4", 1, json.dumps({"type": "text", "text": "TASK-ANSWER-MARK"})),
        # р49: системная вставка + человеческая model-only реплика
        ("m15", 1, json.dumps({"type": "text", "text":
            "You are powered by the model named account:zai-test/model-1."})),
        ("m16", 1, json.dumps({"type": "text", "text": "HUMAN-MODEL-ONLY-MARK"})),
        ("m5", 1, json.dumps({"type": "text", "text": "SUB-REQUEST-MARK"})),
        ("m6", 1, json.dumps({"type": "text", "text": "SUB-ANSWER-MARK"})),
        # р40: контент форков; m11 — уведомление БЕЗ metadata (fallback
        # по строкам текста parentSessionId/targetMessageId)
        ("m7", 1, json.dumps({"type": "text", "text": "ZF1-COPIED-MARK"})),
        ("m8", 1, json.dumps({"type": "text", "text": "ZF1-ANSWER-MARK"})),
        ("m9", 1, json.dumps({"type": "text", "text": "FORK2-REQUEST-MARK"})),
        ("m11", 1, json.dumps({"type": "text", "text":
            "This session was forked from a previous session message.\n"
            "parentSessionId: zmain\ntargetMessageId: m2"})),
        ("ma9", 1, json.dumps({"type": "text", "text": "ZF2-ANSWER-MARK"})),
        # р62 (я10): реплики zeffort
        ("me1", 1, json.dumps({"type": "text", "text": "EFFORT-REQ-1"})),
        ("me2", 1, json.dumps({"type": "text", "text": "EFFORT-ANS-MAX"})),
        ("me3", 1, json.dumps({"type": "text", "text": "EFFORT-REQ-2"})),
        ("me4", 1, json.dumps({"type": "text", "text": "EFFORT-ANS-HIGH"})),
        ("me5", 1, json.dumps({"type": "text", "text": "EFFORT-REQ-3"})),
        ("me6", 1, json.dumps({"type": "text", "text": "EFFORT-ANS-HIGH-2"})),
    ]
    con.executemany("insert into part values (?,?,?)", parts)
    # р62 (я2): +2 колонки (provider_total_tokens / computed_total_tokens):
    # u4 — provider NULL, computed 999 → проверка fallback при суммировании
    con.executemany(
        "insert into model_usage values (?,?,?,?,?,?,?,?,?,?,?)", [
        # р43: «Ток» — последний input_tokens; р50: модель ответа
        ("u1", "zmain", 123456, t0 + 5000, None, "GLM-5.3-Flash", "max",
         "zcode-agent", 2100, 124000, 124000),
        ("u2", "zmain", 234567, t0 + 6000, None, "GLM-5.3-Flash", "max",
         "zcode-agent", 2100, 245000, 245000),   # свежее — побеждает
        ("u3", "zf1", 63000, t0 + 7000, None, "GLM-5.3-Flash", "high",
         "zcode-agent", 2100, 64000, 64000),
        ("u4", "zmain", None, t0 + 8000, None, "GLM-5.3-Flash", "max",
         "zcode-agent", 2100, None, 999),        # без токенов — пропуск «Ток»
        # р50: привязка к assistant-сообщениям (ответы zmain/ztask/zsub);
        # input_tokens=None — «Ток» (р43) эти строки не трогают
        ("u5", "zmain", None, t0 + 510, "m2", "GLM-5.3-Flash", "max",
         "zcode-agent", 2100, 36000, 36000),
        ("u6", "ztask", None, t0 + 510, "m4", "GLM-5.3-Flash", "max",
         "zcode-agent", 2100, 1000, 1000),
        ("u7", "zsub", None, t0 + 510, "m6", "GLM-5.3-Flash", "max",
         "zcode-Explore", 4300, 5000, 5000),     # субагент — « · Explore»
        ("u8", "zf2", None, t0 + 310, "ma9", None, None, None, None,
         None, None),
        # р62 (я10): zeffort — смена effort max → high по ходу чата;
        # р63 (я6): me6 — повтор high
        ("u9", "zeffort", 40000, t0 + 17200, "me2", "GLM-5.3-Flash", "max",
         "zcode-agent", 2100, 41000, 41000),
        ("u10", "zeffort", 42000, t0 + 17400, "me4", "GLM-5.3", "high",
         "zcode-agent", 2100, 43000, 43000),
        ("u11", "zeffort", 44000, t0 + 17600, "me6", "GLM-5.3", "high",
         "zcode-agent", 2100, 45000, 45000),
    ])
    con.commit()
    con.close()


# ------------------------------------------------------------- инварианты

def check_body(fmt: str, raw: bytes, opts: dict, mode: str) -> list[str]:
    """Инварианты содержимого одного экспорта для комбинации opts."""
    issues: list[str] = []
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig", "replace")

    # --- BOM (ER-3): md/txt по флагу, json — никогда ---
    want_bom = bool(opts["bom"]) and fmt in ("md", "txt")
    if fmt == "json":
        if bom:
            issues.append("json с BOM")
    elif bom != want_bom:
        issues.append(f"BOM={bom}, ожидалось {want_bom}")

    if fmt == "json":
        payload = json.loads(text)
        turn = payload["turns"][0]
        tools = turn.get("tools", [])
        if opts["tools"]:
            if not tools or "TOOLMARK" not in json.dumps(tools, ensure_ascii=False):
                issues.append("tools on: блок инструментов пуст")
        elif tools:
            issues.append("tools off: блок инструментов есть")
        narr = turn.get("narration", [])
        if opts["narration"]:
            if not any("NARRATION-MARK" in n for n in narr):
                issues.append("narration on: реплик нет")
        elif narr:
            issues.append("narration off: реплики есть")
        attach = turn.get("attachments", [])
        files = turn.get("files", [])
        # р81 (п.4): no_files удалён — файловые блоки всегда
        if not any("ATTACH-NAME" in a.get("name", "") for a in attach):
            issues.append("вложение не показано")
        if mode == "autoclaw":
            # созданные/доставленные файлы — только у AutoClaw;
            # ZCode их в базе не хранит (р25)
            if not any("CRE-READY-MARK" in f.get("name", "") for f in files):
                issues.append("готовый файл не показан")
            has_service = any("CRE-SERVICE-MARK" in f.get("name", "")
                              for f in files)
            if bool(opts["all_files"]) != has_service:
                issues.append(f"all_files={opts['all_files']}, "
                              f"служебный файл {'есть' if has_service else 'нет'}")
        if "ANSWER-MARK" not in text:
            issues.append("нет финального ответа")
        return issues

    # --- md / txt ---
    if opts["tools"]:
        if "🔧" not in text or "TOOLMARK" not in text:
            issues.append("tools on: блока инструментов нет")
        if "TOOL-RESULT-MARK" not in text:
            issues.append("tools on: результата инструмента нет")
    elif "🔧" in text:
        issues.append("tools off: блок инструментов есть")
    if opts["narration"]:
        if "NARRATION-MARK" not in text:
            issues.append("narration on: реплик нет")
    elif "NARRATION-MARK" in text:
        issues.append("narration off: реплики есть")
    # р81 (п.4): no_files удалён — файловые блоки всегда
    if "ATTACH-NAME" not in text:
        issues.append("вложение не показано")
    if mode == "autoclaw":
        # созданные/доставленные файлы — только у AutoClaw (р25)
        if "CRE-READY-MARK" not in text:
            issues.append("готовый файл не показан")
        has_service = "CRE-SERVICE-MARK" in text
        if bool(opts["all_files"]) != has_service:
            issues.append(f"all_files={opts['all_files']}, "
                          f"служебный файл {'есть' if has_service else 'нет'}")
    if "ANSWER-MARK" not in text:
        issues.append("нет финального ответа")
    return issues


def option_combos():
    # р81 (п.4): no_files удалён — файловые блоки всегда; комбинаций 16
    keys = ("tools", "narration", "all_files", "bom")
    for mask in range(16):
        yield {key: bool(mask >> i & 1) for i, key in enumerate(keys)}


# ------------------------------------------------------------- прогон

def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="z5_matrix_"))
    try:
        ac_db = tmp / "autoclaw.sqlite"
        zc_db = tmp / "zcode.sqlite"
        make_autoclaw_fixture(ac_db)
        make_zcode_fixture(zc_db)

        # --- список чатов ZCode: проект, Tasks, флаг субагентов (р24/26) ---
        adz = adapter_for("zcode")
        conz = adz.open(zc_db)
        rowsz = {r["id"]: r for r in adz.list_chats(conz)}
        check("матрица: фикстурная сессия не в реальном индексе → пусто (р29)",
              rowsz["zmain"].get("project") == "",
              str(rowsz["zmain"].get("project")))
        check("матрица: Task (.zcode/workspace) — без проекта (р26)",
              rowsz["ztask"].get("project") == "",
              str(rowsz["ztask"].get("project")))
        check("матрица: workflow_child скрыт, метка wfchld (р37)",
              rowsz["zsub"].get("hidden") is True
              and rowsz["zsub"].get("type") == "wfchld",
              str((rowsz["zsub"].get("hidden"), rowsz["zsub"].get("type"))))
        check("матрица: обычный чат — видим, без метки",
              rowsz["zmain"].get("hidden") is False
              and rowsz["zmain"].get("type") == "")
        check("матрица: time_deleted — скрыт, метка del (р37)",
              rowsz["zdel"].get("hidden") is True
              and rowsz["zdel"].get("type") == "del",
              str((rowsz["zdel"].get("hidden"), rowsz["zdel"].get("type"))))
        check("матрица: session_purge — скрыт, метка del (р37)",
              rowsz["zpurge"].get("hidden") is True
              and rowsz["zpurge"].get("type") == "del",
              str((rowsz["zpurge"].get("hidden"), rowsz["zpurge"].get("type"))))
        check("матрица: архив — скрыт, метка arch (р37)",
              rowsz["zarch"].get("hidden") is True
              and rowsz["zarch"].get("type") == "arch",
              str((rowsz["zarch"].get("hidden"), rowsz["zarch"].get("type"))))
        check("матрица: fork — ОБЫЧНЫЙ белый чат (р37)",
              rowsz["zfork"].get("hidden") is False
              and rowsz["zfork"].get("type") == "fork",
              str((rowsz["zfork"].get("hidden"), rowsz["zfork"].get("type"))))
        check("матрица: workflow_parent — обычный wfprnt (р37)",
              rowsz["zwfprnt"].get("hidden") is False
              and rowsz["zwfprnt"].get("type") == "wfprnt",
              str((rowsz["zwfprnt"].get("hidden"), rowsz["zwfprnt"].get("type"))))
        # --- р43 (A): контекст в токенах из model_usage ---
        check("матрица: р43 tokens — последний input_tokens сессии",
              rowsz["zmain"].get("tokens") == 234567,
              str(rowsz["zmain"].get("tokens")))
        check("матрица: р43 tokens у другой сессии",
              rowsz["zf1"].get("tokens") == 63000,
              str(rowsz["zf1"].get("tokens")))
        check("матрица: р43 tokens отсутствуют → None",
              rowsz["ztask"].get("tokens") is None,
              str(rowsz["ztask"].get("tokens")))
        # --- р40: суффиксы форков (frkN по границе в родителе, цепочки) ---
        check("матрица: р40 первый форк (граница m1) — « frk1» в названии",
              rowsz["zf1"].get("title", "").endswith(" frk1"),
              str(rowsz["zf1"].get("title")))
        check("матрица: р40 второй форк (граница m2, fallback по тексту) — « frk2»",
              rowsz["zf1b"].get("title", "").endswith(" frk2"),
              str(rowsz["zf1b"].get("title")))
        check("матрица: р40 вложенный форк — цепочка « frk1 frk1»",
              rowsz["zf2"].get("title", "").endswith(" frk1 frk1"),
              str(rowsz["zf2"].get("title")))
        check("матрица: р40 обычный чат — без суффикса",
              " frk" not in (rowsz["zmain"].get("title") or ""),
              str(rowsz["zmain"].get("title")))
        # --- р39: прямая связь tasks.project_id, фильтры, приоритет корней ---
        idx_fixture = tmp / "index_fixture.sqlite"
        make_index_fixture(idx_fixture)
        rows_ix = {r["id"]: r
                   for r in adz.list_chats(conz, index_db=str(idx_fixture))}
        check("матрица: р39 прямая связь session→project сильнее корней",
              rows_ix["zmain"].get("project") == "Прямой проект",
              str(rows_ix["zmain"].get("project")))
        check("матрица: р39 задача deleted=1 не выдаёт имя (Task-папка вне корней)",
              rows_ix["ztask"].get("project") == "",
              str(rows_ix["ztask"].get("project")))
        check("матрица: р39 задача archived=1 не выдаёт имя → fallback по корню",
              rows_ix["zarch"].get("project") == "Главный",
              str(rows_ix["zarch"].get("project")))
        check("матрица: р39 дубль task_id — побеждает свежая запись",
              rows_ix["zdup"].get("project") == "Прямой проект",
              str(rows_ix["zdup"].get("project")))
        check("матрица: р39 is_primary бьёт более длинный корень",
              rows_ix["zov"].get("project") == "Главный",
              str(rows_ix["zov"].get("project")))
        check("матрица: р41 tasks.archived=1 — форк скрыт, метка arch",
              rows_ix["zf1b"].get("hidden") is True
              and rows_ix["zf1b"].get("type") == "arch",
              str((rows_ix["zf1b"].get("hidden"), rows_ix["zf1b"].get("type"))))
        check("матрица: р41 архив не сбивает нумерацию форков ( frk2)",
              rows_ix["zf1b"].get("title", "").endswith(" frk2"),
              str(rows_ix["zf1b"].get("title")))
        # --- р48: удаление по tasks-index (сильнее arch), системные вставки ---
        check("матрица: р48 tasks.deleted=1 (даже с archived=1) — del, не arch",
              rows_ix["zdelidx"].get("hidden") is True
              and rows_ix["zdelidx"].get("type") == "del",
              str((rows_ix["zdelidx"].get("hidden"),
                   rows_ix["zdelidx"].get("type"))))
        out48 = tmp / "sys_out"
        # р49/р50: автор по synthetic — в ctx-режиме; харнесс = «ZCODE»
        res48 = adz.export_chat(conz, "ztask", out48,
                                ExportOptions(fmt="txt", lang="ru",
                                              context_view=True))
        sys_txt = Path(res48["path"]).read_text(encoding="utf-8-sig")
        check("матрица: р50 ctx — харнесс ZCODE, человек (в т.ч. model-only) ВЫ",
              "[1] ВЫ" in sys_txt and "[2] ZCODE" in sys_txt
              and "[3] ВЫ" in sys_txt and "СИСТЕМА" not in sys_txt
              and "HUMAN-MODEL-ONLY-MARK" in sys_txt,
              sys_txt[:400])
        # р50: автор ответа — модель из model_usage (GUI-стиль)
        check("матрица: р50 ответ ztask — «GLM-5.3-Flash Max»",
              "GLM-5.3-Flash Max" in sys_txt, sys_txt[:200])
        res48m = adz.export_chat(conz, "ztask", out48,
                                 ExportOptions(fmt="md", lang="ru",
                                               context_view=True))
        sys_md = Path(res48m["path"]).read_text(encoding="utf-8-sig")
        check("матрица: р50 ctx md — «## 2. ZCode», человек — «## 1./3. Вы»",
              "## 1. Вы" in sys_md and "## 2. ZCode" in sys_md
              and "## 3. Вы" in sys_md and "Система" not in sys_md,
              sys_md[:400])
        check("матрица: р50 md-ответ — «### GLM-5.3-Flash Max»",
              "### GLM-5.3-Flash Max" in sys_md, sys_md[:200])
        res48n = adz.export_chat(conz, "ztask", out48,
                                 ExportOptions(fmt="txt", lang="ru"))
        plain_txt = Path(res48n["path"]).read_text(encoding="utf-8-sig")
        check("матрица: р49 обычный экспорт — synthetic/model-only пропущены",
              "ZCODE" not in plain_txt
              and "HUMAN-MODEL-ONLY-MARK" not in plain_txt
              and "[1] ВЫ" in plain_txt and "TASK-REQUEST-MARK" in plain_txt,
              plain_txt[:300])
        # р50: субагентный ответ — «GLM-5.3-Flash Max · Explore»
        res50 = adz.export_chat(conz, "zsub", out48,
                                ExportOptions(fmt="txt", lang="ru"))
        sub_txt = Path(res50["path"]).read_text(encoding="utf-8-sig")
        check("матрица: р50 субагент — «GLM-5.3-Flash Max · Explore»",
              "GLM-5.3-Flash Max · Explore" in sub_txt, sub_txt[:200])
        # р50: ответ без строки model_usage → «LLM»
        res50b = adz.export_chat(conz, "zf2", out48,
                                 ExportOptions(fmt="txt", lang="ru"))
        llm_txt = Path(res50b["path"]).read_text(encoding="utf-8-sig")
        check("матрица: р50 модель неизвестна → «LLM»",
              "ZF2-ANSWER-MARK" in llm_txt and "LLM — " in llm_txt
              and "GLM" not in llm_txt,
              llm_txt[:200])
        # р49 (я4-доп): размер вложения — metadata.sizeBytes → «61 КБ»
        res48s = adz.export_chat(conz, "zmain", out48,
                                 ExportOptions(fmt="txt", lang="ru"))
        size_txt = Path(res48s["path"]).read_text(encoding="utf-8-sig")
        check("матрица: р49 размер вложения «61 КБ» рядом с именем",
              "ATTACH-NAME-Z.txt" in size_txt
              and '"ATTACH-NAME-Z.txt" (61 КБ)' in size_txt,
              [line for line in size_txt.splitlines()
               if "ATTACH-NAME-Z" in line][:1])
        # --- р51: шапка чата ZCode (харнесс/проект/чат/файлы/модели) ---
        # р63 (я3): «нет» → «—»; в шапке «Тип: —»
        zhead = size_txt.split("-" * 60)[0]
        check("матрица: р51 шапка ZCode — харнесс/проект/чат/файлы/модели",
              "Харнесс-ядро: ZCode" in zhead and "Проект: —" in zhead
              and "Чат: Фикстура ZC чат" in zhead
              and "Тип: —" in zhead
              and "Файлы: вложено 1" in zhead
              and "Модели: GLM-5.3-Flash Max" in zhead,
              zhead[:400])
        # --- р43 (B/C): актуальный контекст и маркер уплотнения ---
        out_c = tmp / "ctx_out"
        res_n = adz.export_chat(conz, "zmain", out_c,
                                ExportOptions(fmt="md", lang="ru"))
        n_text = Path(res_n["path"]).read_text(encoding="utf-8-sig")
        check("матрица: р43 (C) маркер уплотнения в обычном экспорте",
              "Уплотнение" in n_text and "150000" in n_text, n_text[:200])
        check("матрица: р43 (C) обычный экспорт — всё на месте",
              "REQUEST-MARK-Z" in n_text and "POST-COMPACT-MARK" in n_text
              and "CTX-ONLY-MARK" not in n_text, "контент сломан")
        res_c = adz.export_chat(conz, "zmain", out_c,
                                ExportOptions(fmt="md", lang="ru",
                                              context_view=True))
        c_text = Path(res_c["path"]).read_text(encoding="utf-8-sig")
        check("матрица: р43 (B) сводка уплотнённой истории в ctx-экспорте",
              "Сводка уплотнённой истории" in c_text
              and "SUMMARY-MARK-ZC" in c_text, c_text[:200])
        check("матрица: р43 (B) модель-only сообщение включено",
              "CTX-ONLY-MARK" in c_text, "нет model-only")
        check("матрица: р43 (B) ход до границы отрезан",
              "REQUEST-MARK-Z" not in c_text, "старый ход остался")
        check("матрица: р43 (B) хвост после границы на месте, до границы — нет",
              "POST-COMPACT-MARK" in c_text and "ANSWER-MARK-Z" not in c_text,
              f"POST={'POST-COMPACT-MARK' in c_text}, "
              f"ANSWER={'ANSWER-MARK-Z' in c_text}")
        # --- р40: экспорт форка — суффиксы, точка расхождения, синтетика ---
        out_f = tmp / "fork_out"
        res_f2 = adz.export_chat(conz, "zf2", out_f,
                                 ExportOptions(fmt="md", lang="ru"))
        f2_path = Path(res_f2["path"])
        check("матрица: р40 имя файла вложенного форка — « frk1 frk1»",
              " frk1 frk1" in f2_path.name, f2_path.name)
        f2_text = f2_path.read_text(encoding="utf-8-sig")
        check("матрица: р40 заголовок внутри файла — суффикс",
              "# Фикстура форк2 frk1 frk1" in f2_text, f2_text[:100])
        check("матрица: р40 точка расхождения — родитель и снippet истории",
              "Форк от «Фикстура форк1 frk1»" in f2_text
              and "точка расхождения" in f2_text
              and "ZF1-COPIED-MARK" in f2_text,
              f2_text[:300])
        check("матрица: р40 синтетическое уведомление НЕ в экспорте",
              "This session was forked" not in f2_text,
              "протёк текст уведомления")
        check("матрица: р40 запрос форка на месте",
              "FORK2-REQUEST-MARK" in f2_text, "нет нового запроса")
        res_f1 = adz.export_chat(conz, "zf1", out_f,
                                 ExportOptions(fmt="md", lang="ru"))
        f1_path = Path(res_f1["path"])
        check("матрица: р40 файл первого форка — « frk1.md»",
              "Фикстура форк1 frk1.md" in f1_path.name, f1_path.name)
        f1_text = f1_path.read_text(encoding="utf-8-sig")
        check("матрица: р40 точка расхождения — снippет родителя (m1)",
              "Форк от «Фикстура ZC чат»" in f1_text
              and "REQUEST-MARK-Z" in f1_text,
              f1_text[:300])
        # --- список AutoClaw: default workspace — не проект (р26) ---
        ada = adapter_for("autoclaw")
        cona = ada.open(ac_db)
        rowsa = {r["id"]: r for r in ada.list_chats(cona)}
        check("матрица: не-дефолтный workspace — проект (р26)",
              rowsa["fmain"].get("project") == "Материнский проект",
              str(rowsa["fmain"].get("project")))
        check("матрица: default workspace («默认项目») — НЕ проект (р26)",
              rowsa["fdef"].get("project") == "",
              str(rowsa["fdef"].get("project")))
        # --- р48: архив AutoClaw (archived_at) — скрыт, метка arch ---
        check("матрица: р48 archived_at — скрыт, метка arch",
              rowsa["farch"].get("hidden") is True
              and rowsa["farch"].get("type") == "arch",
              str((rowsa["farch"].get("hidden"), rowsa["farch"].get("type"))))
        # --- р49: удалённый AutoClaw (deleted_at) — скрыт, метка del ---
        check("матрица: р49 deleted_at — скрыт, метка del",
              rowsa["fdel"].get("hidden") is True
              and rowsa["fdel"].get("type") == "del",
              str((rowsa["fdel"].get("hidden"), rowsa["fdel"].get("type"))))
        check("матрица: р48 обычные чаты AutoClaw — видимы, без метки",
              rowsa["fmain"].get("hidden") is False
              and rowsa["fmain"].get("type") == ""
              and rowsa["fdef"].get("hidden") is False
              and rowsa["fdef"].get("type") == "")
        # --- р51: шапка чата AutoClaw (харнесс/проект/чат/файлы/модели) ---
        res51 = ada.export_chat(cona, "fmain", out48,
                                ExportOptions(fmt="txt", lang="ru"))
        ahead = Path(res51["path"]).read_text(encoding="utf-8-sig")
        # р62 (я2): графа «Ток» у AutoClaw = contextTokens последнего
        # completed-хода (размер контекста; run без contextTokens и
        # stopped-ход не влияют; прежде ошибочно totalTokens)
        check("матрица: р62 «Ток» AutoClaw — contextTokens последнего хода",
              rowsa["fmain"].get("tokens") == 16161
              and rowsa["fdef"].get("tokens") == 555
              and rowsa["fdel"].get("tokens") is None,
              str((rowsa["fmain"].get("tokens"),
                   rowsa["fdef"].get("tokens"),
                   rowsa["fdel"].get("tokens"))))
        check("матрица: р51 шапка AutoClaw — харнесс/проект/чат/файлы/модели",
              "Харнесс: AutoClaw" in ahead
              and "Проект: Материнский проект" in ahead
              and "Чат: Фикстура чат" in ahead
              and "вложено 1 · готово к скачиванию 1" in ahead
              and "Модели: GLM-5.3-Flash" in ahead,
              ahead[:400])

        # --- р60 (я6): КРОСС-ТЕСТ — один чат × 3 формата × оба движка:
        # одни и те же факты обязаны присутствовать везде; структура
        # шапки AC и ZC совпадает ---
        print("р60: кросс-сравнение форматов и движков")
        FULL = dict(tools=True, narration=True, app_version="1.55 RC")
        cross = {}
        for label, ad, con, sid in (("ac", ada, cona, "fmain"),
                                    ("zc", adz, conz, "zmain")):
            for fmt in ("md", "txt", "json"):
                r = ad.export_chat(con, sid, out48,
                                   ExportOptions(fmt=fmt, lang="ru", **FULL))
                cross[(label, fmt)] = Path(r["path"]).read_text(
                    encoding="utf-8-sig")
        # 1) шапка одинаковой структуры в txt обоих движков
        # р81 (п.1): у ZCode подпись «Харнесс-ядро:», у AutoClaw «Харнесс:»
        fields = ("Проект:", "Чат:", "Сессия:", "Создана:",
                  "Обновлена:", "Сообщений:", "Файлы:", "Модели:")
        for label in ("ac", "zc"):
            head = cross[(label, "txt")].split("-" * 60)[0]
            harness_lbl = "Харнесс:" if label == "ac" else "Харнесс-ядро:"
            check(f"р60 кросс: {label}-txt шапка — все 9 полей",
                  harness_lbl in head and all(f in head for f in fields),
                  [f for f in (harness_lbl,) + fields if f not in head])
        # 2) ключевые факты во всех 3 форматах каждого движка
        import json as _json
        for label, sid_mark in (("ac", "3e07"), ("zc", "zmain")):
            for fmt in ("md", "txt"):
                check(f"р60 кросс: {label} {fmt} — ход 1 и модель ответа",
                      ("## 1. Вы" if fmt == "md" else "[1] ВЫ")
                      in cross[(label, fmt)]
                      and "GLM-5.3-Flash" in cross[(label, fmt)],
                      cross[(label, fmt)][:200])
            payload = _json.loads(cross[(label, "json")])
            t1 = payload["turns"][0]
            want = "GLM-5.3-Flash" if label == "ac" else "GLM-5.3-Flash Max"
            check(f"р60 кросс: {label} json — модель хода 1 = md/txt",
                  t1.get("model") == want
                  and payload["session"].get("harness") in ("AutoClaw",
                                                            "ZCode"),
                  str(t1.get("model")))
        # 3) футер экспортёра во всех файлах, exporter в json
        for label in ("ac", "zc"):
            for fmt in ("md", "txt"):
                check(f"р60 кросс: {label} {fmt} — футер экспортёра",
                      "Z.ai Chats Exporter by Vadim R.M. ver. 1.55 RC"
                      in cross[(label, fmt)],
                      "нет строки")
        check("р60 кросс: кликабельный линк в md",
              "[https://www.vmgames.com](https://www.vmgames.com)"
              in cross[("ac", "md")]
              and "[https://www.vmgames.com](https://www.vmgames.com)"
              in cross[("zc", "md")], "нет линка")
        # 4) время работы у ответов (я3; р62/я5 — «сек/мин/час», целые
        # секунды, десятые только <1 сек)
        import re as _re
        time_re = _re.compile(r"\(\d+([.,]\d+)? сек\)"
                              r"|\(\d+ мин( \d+ сек)?\)"
                              r"|\(\d+ час( \d+ мин)?\)")
        for label in ("ac", "zc"):
            for fmt in ("md", "txt"):
                check(f"р62 кросс: {label} {fmt} — время у ответа «(…сек)»",
                      time_re.search(cross[(label, fmt)]) is not None,
                      "нет времени")
                check(f"р62 кросс: {label} {fmt} — нет старых единиц « с)»",
                      _re.search(r"\(\d+([.,]\d+)? с\)", cross[(label, fmt)])
                      is None,
                      "осталась «с»")
        # 5) р60 (я7): пустой чат — файл с шапкой, без ошибки
        r_empty = adz.export_chat(conz, "zpurge", out48,
                                  ExportOptions(fmt="txt", lang="ru",
                                                app_version="1.55 RC"))
        empty_txt = Path(r_empty["path"]).read_text(encoding="utf-8-sig")
        check("р60: пустой чат — файл с шапкой (без err_empty)",
              "Харнесс-ядро: ZCode" in empty_txt and "ВЫ" not in empty_txt
              and "Z.ai Chats Exporter" in empty_txt,
              empty_txt[:200])
        # 6) р60 (я7): selchat — ходы-копии подписаны «КОНТЕКСТ», не «ВЫ»
        r_sel = adz.export_chat(conz, "zsel", out48,
                                ExportOptions(fmt="txt", lang="ru",
                                              app_version="1.55 RC",
                                              context_view=True))
        sel_txt = Path(r_sel["path"]).read_text(encoding="utf-8-sig")
        check("р60: selchat — копии контекста «КОНТЕКСТ», не «ВЫ»",
              "[1] КОНТЕКСТ" in sel_txt and "[1] ВЫ" not in sel_txt,
              sel_txt[:300])
        # 7) р62 (я9): блок кода в txt — язык строкой + код в { };
        # бэктиков больше нет; # и код не тронуты чистками
        r_fn = adz.export_chat(conz, "zmain", out48,
                               ExportOptions(fmt="txt", lang="ru",
                                             narration=True))
        fn_txt = Path(r_fn["path"]).read_text(encoding="utf-8-sig")
        check("р62: txt — блок кода «язык { … }» (реплика с ```js)",
              "js\n{\nvar x = 1;\n}" in fn_txt,
              fn_txt[:300])
        check("р62: txt — бэктиков fence не осталось",
              "```" not in fn_txt, "есть ```")

        # --- р62 (я7): кросс-тест форматов и движков — расширение р60 ---
        print("р62: кросс-сравнение форматов и движков (я7)")
        # a) я2: строки токенов в шапке — формат владельца
        check("р62 кросс: ac txt — «Контекст чата: 16 161 из 1М (1.5%)»",
              "Контекст чата: 16 161 из 1М (1.5%)" in ahead, ahead[:400])
        check("р62 кросс: ac txt — «Автосжатие при: 812 К (77%)»",
              "Автосжатие при: 812 К (77%)" in ahead, ahead[:400])
        check("р62 кросс: ac txt — «Всего израсходовано: 255 507 токенов»",
              "Всего израсходовано: 255 507 токенов" in ahead, ahead[:400])
        r_fdef = ada.export_chat(cona, "fdef", out48,
                                 ExportOptions(fmt="txt", lang="ru"))
        fdef_txt = Path(r_fdef["path"]).read_text(encoding="utf-8-sig")
        check("р62 кросс: ac txt (fdef) — порог кодинг-модели 635 К (61%)",
              "Автосжатие при: 635 К (61%)" in fdef_txt,
              fdef_txt[:400])
        # zmain: контекст 234 567; расход 124000+245000+999+36000=405 999;
        # окна/автосжатия у ZCode нет — строк быть не должно
        check("р62 кросс: zc txt — «Контекст чата: 234 567»",
              "Контекст чата: 234 567" in cross[("zc", "txt")], "нет строки")
        check("р62 кросс: zc txt — «Всего израсходовано: 405 999 токенов»",
              "Всего израсходовано: 405 999 токенов" in cross[("zc", "txt")],
              "нет строки")
        check("р62 кросс: zc txt — строки автосжатия НЕТ (нет данных)",
              "Автосжатие при:" not in cross[("zc", "txt")], "лишняя строка")
        # json: те же числа в session (оба движка)
        ac_json = _json.loads(cross[("ac", "json")])["session"]
        zc_json = _json.loads(cross[("zc", "json")])["session"]
        check("р62 кросс: ac json — поля токенов session",
              ac_json.get("context_tokens") == 16161
              and ac_json.get("context_window") == 1048576
              and ac_json.get("compact_at_tokens") == 811622
              and ac_json.get("total_spent_tokens") == 255507,
              str({k: ac_json.get(k) for k in
                   ("context_tokens", "context_window",
                    "compact_at_tokens", "total_spent_tokens")}))
        check("р62 кросс: zc json — поля токенов session",
              zc_json.get("context_tokens") == 234567
              and zc_json.get("total_spent_tokens") == 405999,
              str({k: zc_json.get(k) for k in
                   ("context_tokens", "total_spent_tokens")}))
        # b) я3/я4: подчёркивания в txt = длина строки заголовка
        for label, title in (("ac", "Фикстура чат"), ("zc", "Фикстура ZC чат")):
            lines = cross[(label, "txt")].splitlines()
            ok_title = (lines[0] == title
                        and lines[1] == "-" * len(title))
            i_you = next(i for i, l in enumerate(lines)
                         if l.startswith("[1] ВЫ — "))
            ok_you = lines[i_you + 1] == "-" * len(lines[i_you])
            i_ans = next(i for i, l in enumerate(lines)
                         if _re.match(r"^GLM[^\n]* — \d{2}\.\d{2}", l))
            ok_ans = lines[i_ans + 1] == "-" * len(lines[i_ans])
            check(f"р62 кросс: {label} txt — подчёркивания (заголовок/ход/ответ)",
                  ok_title and ok_you and ok_ans,
                  str((ok_title, ok_you, ok_ans)))
        # c) я6: метка «Промежуточные реплики:» — md обоих движков + txt ZC
        check("р62 кросс: ac md — метка «Промежуточные реплики:»",
              "**Промежуточные реплики:**" in cross[("ac", "md")], "нет метки")
        check("р62 кросс: zc md — метка «Промежуточные реплики:»",
              "**Промежуточные реплики:**" in cross[("zc", "md")], "нет метки")
        check("р62 кросс: zc txt — метка «Промежуточные реплики:»",
              "Промежуточные реплики:" in cross[("zc", "txt")], "нет метки")
        # d) я8: строка экспортёра — в шапке И в футере (2 раза)
        for label in ("ac", "zc"):
            for fmt in ("md", "txt"):
                check(f"р62 кросс: {label} {fmt} — экспортёр в шапке и футере",
                      cross[(label, fmt)].count(
                          "Z.ai Chats Exporter by Vadim R.M. ver. 1.55 RC")
                      >= 2, "меньше двух")
        check("р62 кросс: шапка md — линк экспортёра кликабельный",
              "Z.ai Chats Exporter by Vadim R.M. ver. 1.55 RC — "
              "[https://www.vmgames.com](https://www.vmgames.com)"
              in cross[("ac", "md")]
              and "Z.ai Chats Exporter by Vadim R.M. ver. 1.55 RC — "
              "[https://www.vmgames.com](https://www.vmgames.com)"
              in cross[("zc", "md")], "нет линка в шапке")
        # e) я7: md↔txt одного чата — каждая строка шапки md есть в txt
        # р81 (п.1): у ZCode подпись «Харнесс-ядро:», у AutoClaw «Харнесс:»
        base_fields = ("Проект:", "Чат:", "Сессия:", "Создана:",
                       "Обновлена:", "Сообщений:", "Файлы:", "Модели:",
                       "Контекст чата:", "Всего израсходовано:", "Экспорт:")
        for label in ("ac", "zc"):
            harness_lbl = "Харнесс:" if label == "ac" else "Харнесс-ядро:"
            for fmt in ("md", "txt"):
                head = cross[(label, fmt)].split("-" * 60)[0]
                check(f"р62 кросс: {label} {fmt} шапка — все 12 полей (я7)",
                      harness_lbl in head and all(f in head for f in base_fields),
                      [f for f in (harness_lbl,) + base_fields if f not in head])
        # f) я7: AC↔ZC — одинаковые форматы однотипных данных
        date_re = _re.compile(r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}")
        sig_re = _re.compile(r"^GLM[^\n]* — \d{2}\.\d{2}\.\d{4} \d{2}:\d{2}"
                             r"( \([^)]+\))?$", _re.M)
        for label in ("ac", "zc"):
            body_txt = cross[(label, "txt")]
            check(f"р62 кросс: {label} txt — формат даты/времени единый",
                  date_re.search(body_txt) is not None, "нет даты")
            check(f"р62 кросс: {label} txt — подпись ответа «Модель — дата (время)»",
                  sig_re.search(body_txt) is not None, "нет подписи")
            check(f"р62 кросс: {label} txt — «Инструменты: 1»",
                  "Инструменты: 1" in body_txt, "нет блока")
            # р63 (я1): пустой строки после «Чат:» больше нет; шапка
            # сплошная, «Тип:» сразу после «Чат:» (р63 я3)
            check(f"р63 кросс: {label} txt — шапка без пустых строк",
                  "\n\nСессия:" not in body_txt.split("-" * 60)[0]
                  and "Тип: —\nСессия:" in body_txt, "есть пустая строка")
        # g) я10: смена effort по ходу чата — обе записи в «Модели»
        r_eff = adz.export_chat(conz, "zeffort", out48,
                                ExportOptions(fmt="md", lang="ru"))
        eff_md = Path(r_eff["path"]).read_text(encoding="utf-8-sig")
        check("р62 (я10): «Модели:» с effort; смена — две записи",
              "Модели: GLM-5.3-Flash Max, GLM-5.3 High" in eff_md
              and "### GLM-5.3-Flash Max — " in eff_md
              and "### GLM-5.3 High — " in eff_md,
              [l for l in eff_md.splitlines() if l.startswith("Модели:")]
              + [l for l in eff_md.splitlines() if l.startswith("### GLM")])
        # р64 (E1): после КАЖДОГО промпта ответ снова «###» (источник
        # сменился человек→ИИ); жирный — только повтор подряд
        check("р64 (E1): все ответы zeffort «###», жирных нет",
              eff_md.count("### GLM-5.3 High — ") == 2
              and "**GLM" not in eff_md
              and "EFFORT-ANS-HIGH-2" in eff_md,
              [l for l in eff_md.splitlines() if "GLM-5.3 High" in l])

        # --- р63: заголовки ###, повторы, рамка txt, тип, клип вызова ---
        print("р63: ###, повторы, рамка, тип, клип вызова")
        # a) я6: ходы человека — «###», не «##»
        for label in ("ac", "zc"):
            body_md = cross[(label, "md")]
            check(f"р63 (я6): {label} md — ходы «### N. Вы», не «##»",
                  f"### 1. {'Вы' if label == 'ac' else 'Вы'} — " in body_md
                  and "\n## 1. " not in body_md
                  and body_md.count("\n### ") >= 2,
                  [l for l in body_md.splitlines() if l.startswith("##")][:4])
        # AC frep: Auto (###), Auto-повтор (жирный), Flash (###)
        r_rep = ada.export_chat(cona, "frep", out48,
                                ExportOptions(fmt="md", lang="ru"))
        rep_md = Path(r_rep["path"]).read_text(encoding="utf-8-sig")
        check("р64 (E1): AC — каждый ответ после промпта «###»",
              rep_md.count("### Auto — ") == 3
              and rep_md.count("### GLM-5.3-Flash — ") == 1,
              [l for l in rep_md.splitlines()
               if l.startswith("###") and " — " in l])
        check("р64 (E1): жирный — только 2-й ответ ПОДРЯД (REP-ANS-5)",
              rep_md.count("**Auto — ") == 1
              and "REP-ANS-5" in rep_md.split("**Auto — ")[1][:200],
              [l for l in rep_md.splitlines() if l.startswith("**")])
        # b) я2: рамка txt — черта длиной в строку экспортёра (шапка+футер)
        frame_line = ("Z.ai Chats Exporter by Vadim R.M. ver. 1.55 RC"
                      "  https://www.vmgames.com")
        frame = ("-" * len(frame_line) + "\n" + frame_line + "\n"
                 + "-" * len(frame_line))
        for label in ("ac", "zc"):
            check(f"р63 (я2): {label} txt — рамка экспортёра ×2 (шапка/футер)",
                  cross[(label, "txt")].count(frame) == 2, "нет рамки")
        check("р63 (я1): md — пустая строка перед строкой экспортёра шапки",
              "\n\nZ.ai Chats Exporter by Vadim R.M. ver. 1.55 RC — "
              "[https://www.vmgames.com](https://www.vmgames.com)"
              in cross[("ac", "md")]
              and "\n\nZ.ai Chats Exporter by Vadim R.M. ver. 1.55 RC — "
              "[https://www.vmgames.com](https://www.vmgames.com)"
              in cross[("zc", "md")], "нет пустой строки")
        # c) я3: тип чата — del/arch в шапке (скрытые чаты)
        r_fd = ada.export_chat(cona, "fdel", out48,
                               ExportOptions(fmt="txt", lang="ru"))
        fd_txt = Path(r_fd["path"]).read_text(encoding="utf-8-sig")
        check("р63 (я3): AC del-чат — «Тип: del» в шапке",
              "Тип: del" in fd_txt, fd_txt[:200])
        r_zd = adz.export_chat(conz, "zdel", out48,
                               ExportOptions(fmt="txt", lang="ru"))
        zd_txt = Path(r_zd["path"]).read_text(encoding="utf-8-sig")
        check("р63 (я3): ZC del-чат — «Тип: del» в шапке",
              "Тип: del" in zd_txt, zd_txt[:200])
        # d) я4: «Максимальная длина» клипает и ВЫЗОВ инструмента
        r_lim = ada.export_chat(cona, "fmain", out48,
                                ExportOptions(fmt="txt", lang="ru",
                                              tools=True, tool_limit=5))
        lim_txt = Path(r_lim["path"]).read_text(encoding="utf-8-sig")
        tool_block = lim_txt.split("🔧 exec", 1)[-1][:600]
        check("р63 (я4): AC txt — вызов обрезан лимитом (5 литер)",
              "обрезано, всего" in tool_block, tool_block[:300])
        r_lz = adz.export_chat(conz, "zmain", out48,
                               ExportOptions(fmt="md", lang="ru",
                                             tools=True, tool_limit=5))
        lz_md = Path(r_lz["path"]).read_text(encoding="utf-8-sig")
        check("р63 (я4): ZC md — вызов обрезан лимитом (5 литер)",
              lz_md.count("обрезано, всего") >= 2,  # вызов + результат
              [l for l in lz_md.splitlines() if "обрезано" in l][:3])
        # e) я3: «—» вместо «нет» в пустых полях обоих движков
        # (fmain с проектом; «Проект: —» у zmain — в проверке р51 выше)
        for label in ("ac", "zc"):
            head = cross[(label, "txt")].split(frame_line)[0]
            check(f"р63 (я3): {label} txt — «—» вместо «нет» в шапке",
                  ": нет" not in head, "нашлось «нет»")

        # --- матрица export_chat: 2 режима × 32 комбинации × 3 формата ---
        out = tmp / "matrix_out"
        for mode, ad, con, chat_id in (
                ("autoclaw", ada, cona, "fmain"),
                ("zcode", adz, conz, "zmain")):
            for opts in option_combos():
                for fmt in ("md", "txt", "json"):
                    res = ad.export_chat(con, chat_id, out,
                                         ExportOptions(
                                             fmt=fmt,
                                             tools=opts["tools"],
                                             narration=opts["narration"],
                                             all_files=opts["all_files"],
                                             bom=opts["bom"],
                                             lang="ru"))
                    raw = Path(res["path"]).read_bytes()
                    issues = check_body(fmt, raw, opts, mode)
                    combo_check(f"{mode} {'+'.join(k for k, v in opts.items() if v)}"
                                f" [{fmt}]",
                                issues)
        # --- р29: чат дефолтного воркспейса — в КОРНЕ, без заглушки «chat» ---
        res_d = ada.export_chat(cona, "fdef", out, ExportOptions(fmt="md", lang="ru"))
        # tempfile может вернуть короткий путь (7C77~1) — сравниваем resolve()
        check("матрица: default workspace — файл в КОРНЕ (р29)",
              Path(res_d["path"]).parent.resolve() == out.resolve(),
              str(Path(res_d["path"]).parent))
        check("матрица: папка-заглушка «chat» не создаётся (р29)",
              not (out / "chat").exists())
        shutil.rmtree(out, ignore_errors=True)

        # --- паковка «в один файл» с субпапками и метками (р25) ---
        res = adz.export_single_file(conz, tmp / "pack_zc",
                                     ExportOptions(fmt="md", lang="ru"))
        pack = Path(res["path"]).read_text(encoding="utf-8-sig")
        check("матрица: пак ZCode — двойной разделитель",
              "---\n---" in pack)
        check("матрица: метка фикстурного чата без префикса (индекс не знает его)",
              re.search(r"^Новый диалог ZC-.*Фикстура ZC чат\.md$", pack, re.M))
        check("матрица: Task в паке без префикса проекта (р25/26)",
              re.search(r"^Новый диалог ZC-.*Фикстура Task\.md$", pack, re.M),
              "метки Task нет")

        res_a = ada.export_single_file(cona, tmp / "pack_ac",
                                       ExportOptions(fmt="md", lang="ru"))
        pack_a = Path(res_a["path"]).read_text(encoding="utf-8-sig")
        check("матрица: пак AutoClaw — метка с проектом (р25)",
              "Новый диалог Материнский проект\\" in pack_a)
        # р64 (E4): пустые чаты (fdel — 0 ходов, скрытый del) попадают
        # в пак при include_subagents (чекбокс «Показывать скрытые»)
        res_a2 = ada.export_single_file(cona, tmp / "pack_ac2",
                                        ExportOptions(fmt="md", lang="ru"),
                                        include_subagents=True)
        pack_a2 = Path(res_a2["path"]).read_text(encoding="utf-8-sig")
        check("р64 (E4): пак AutoClaw — пустой чат с шапкой",
              "Чат: Фикстура удалён" in pack_a2
              and "Тип: del" in pack_a2,
              [l for l in pack_a2.splitlines() if "Фикстура удалён" in l][:2])
        # р64 (E5b): wfchld (zsub) — user-ход «КОНТЕКСТ», не «ВЫ»
        r_sub = adz.export_chat(conz, "zsub", out48,
                                ExportOptions(fmt="txt", lang="ru"))
        sub_txt = Path(r_sub["path"]).read_text(encoding="utf-8-sig")
        check("р64 (E5b): wfchld — ход «КОНТЕКСТ», не «ВЫ»",
              "[1] КОНТЕКСТ" in sub_txt and "ВЫ —" not in sub_txt,
              sub_txt[:300])

        # --- include_subagents=False: скрытые чаты не попадают в пак (р37) ---
        res2 = adz.export_single_file(conz, tmp / "pack_nosub",
                                      ExportOptions(fmt="json", lang="ru"))
        payload = json.loads(Path(res2["path"]).read_text(encoding="utf-8-sig"))
        ids = [s["session"]["id"] for s in payload["sessions"]]
        check("матрица: паковка без скрытых (р37, по умолчанию)",
              "zsub" not in ids and "zdel" not in ids and "zarch" not in ids
              and {"zmain", "ztask"} <= set(ids), str(ids))
        res3 = adz.export_single_file(conz, tmp / "pack_sub",
                                      ExportOptions(fmt="json", lang="ru"),
                                      include_subagents=True)
        payload3 = json.loads(Path(res3["path"]).read_text(encoding="utf-8-sig"))
        ids3 = [s["session"]["id"] for s in payload3["sessions"]]
        check("матрица: паковка со скрытыми при include (р26/37)",
              "zsub" in ids3 and "zf1" in ids3 and "zf2" in ids3, str(ids3))

        ada.close(cona)
        adz.close(conz)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("-" * 60)
    print(f"Итого: PASS={PASS_COUNT}, FAIL={FAIL_COUNT}")
    for line in FAILURES:
        print(f"  провал: {line}")
    return 1 if FAIL_COUNT else 0


if __name__ == "__main__":
    sys.exit(main())
