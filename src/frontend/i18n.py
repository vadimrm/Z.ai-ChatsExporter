# -*- coding: utf-8 -*-
"""Локализация интерфейса: ru (источник), en, zh + внешние языковые файлы.

Две памяти строк (раунд 23):
- ПОСТОЯННАЯ — STRINGS ниже: 3 языка зашиты в программу, используются,
  если внешнего файла соответствующего языка нет;
- ОПЕРАТИВНАЯ — _runtime: таблица ТЕКУЩЕГО языка, собирается в set_lang()
  из STRINGS[lang] с перекрытием по ключам из внешнего файла
  lang_<язык>.cfg рядом с exe (config.config_dir(); UTF-8 с BOM, формат —
  обычный JSON, читается utf-8-sig — файл без BOM тоже допустим).

Нет внешнего файла — норма: работают внутренние строки. Битый файл —
внутренние строки + предупреждение (set_lang возвращает имя файла, App
показывает messagebox; текст предупреждения — ключ lang_corrupt из
внутренних строк). Неполный внешний файл безопасен: недостающие ключи
дополняются внутренними.

Заводские файлы lang_ru/lang_en/lang_zh.cfg — точные копии STRINGS (лежат
в корне репозитория, генерируются write_factory, копируются build.bat в
поставку); их можно править текстом — новые тексты подхватываются при
переключении языка, без перезапуска программы. Переключатель языка
фиксирован на 3 языках; добавление новых языков — позже (владелец,
раунд 23). Подписи ВНУТРИ экспортируемых файлов (LABELS движков) — не
интерфейс, остаются внутренними.

Брендинг «Z.ai Chats Exporter by Vadim R.M.» — константа в app.py, не
переводится (AGREEMENTS.md №10); пояснение в заголовке после дефиса — ключ
title_explain, переводится. Ключ row_bom — технический термин, одинаков
во всех языках. Ключи всех трёх языков STRINGS обязаны совпадать
(проверяется тестом).
"""
from __future__ import annotations

import json
from pathlib import Path

import config

LANGS = ("ru", "en", "zh")

_current = "ru"
_runtime: dict[str, str] | None = None

STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        "title_explain": "экспорт диалогов AutoClaw и ZCode",
        "lang_label": "Язык:",
        "search": "Поиск чата:",
        "refresh": "Обновить SQL базу",
        "col_project": "Проект",
        "col_title": "Чат",
        "col_updated": "Обновлён",
        "col_created": "Создан",
        "col_requests": "Число",
        "col_tokens": "Ток",
        "row_ctx": "Только актуальный контекст",
        "btn_as_model": "Пресет: актуальный контекст модели",
        "status_preset_applied": "Пресет «актуальный контекст модели» применен: контекстный срез, инструменты вкл., реплики выкл.",
        "col_type": "Тип",
        "col_project_more": "•",
        "group_options": "Параметры экспорта",
        "lbl_format": "Формат:",
        "row_tools": "Добавлять вызов инструментов",
        "row_narration": "Промежуточные реплики",
        "row_all_files": "Показать служебные файлы",
        "row_bom": "UTF-8 Byte Order Mark",
        "lbl_tool_limit": "Максимальная длина, литер",
        "btn_browse": "Обзор…",
        "btn_donate": "Vadim R.M. - Donate",  # статично на всех языках (раунд 8)
        "btn_output_folder": "Папка экспорта",
        "btn_db": "Путь к SQL базе",
        "msg_import_ask": "Отсутствует копия данных {mode}, импортировать их?",
        "msg_import_missing": "Отсутствует копия данных {mode} — не могу импортировать, нужен „Путь к SQL базе“!",
        "msg_master_missing": "Мастер-база {mode} не найдена — укажите „Путь к SQL базе“; чаты работают из локальной копии",
        "msg_bad_outdir": "Некорректная папка экспорта",
        "msg_long_strings": "Слишком длинные строки в файле: {files}",
        "m_copy": "Копировать",
        "m_paste": "Вставить",
        "m_cut": "Вырезать",
        "m_select_all": "Выделить всё",
        "dlg_ok": "ОК",
        "dlg_yes": "Да",
        "dlg_no": "Нет",
        "m_copy_item": "Копировать текст: {text}",
        "m_copy_title": "Копировать текст заголовка окна: {text}",
        "m_copy_chatlist": "Копировать заголовок и список чатов",
        "msg_only_main": "Найдена только одна (основная) база чатов ZCode",
        "msg_cfg_reset": "Конфигурация сброшена к начальной — укажите „Путь к SQL базе“",
        "msg_last_mode_err": "Настройка режима в конфиге повреждена — открыт режим AutoClaw",
        "msg_cfg_corrupt": "ExportChat.cfg повреждён — сохранён как .err, настройки созданы заново",
        "status_copy_of": "копия от {when}",
        "status_import_done": "Копия импортирована",
        "status_import_self": "Не могу копировать базу саму в себя",
        "status_import_minimal": "Копия импортирована; дополнительные файлы базы не найдены — прежние убраны в бэкапы, функционал будет неполным",
        "err_not_main_file": "Выбран не главный файл базы — нужен {name}",
        "err_import": "Импорт базы не удался: {msg}",
        "btn_close": "Закрыть",
        "btn_select_all": "Выбрать всё",
        "btn_clear_all": "Снять выбор",
        "btn_export_selected": "Экспортировать выбранные чаты",
        "chk_single": "записать в один файл",
        "chk_hidden": "Показывать скрытые чаты",
        "btn_open_folder": "Открыть папку экспорта",
        "btn_site": "Vadim R.M. - vmgames.com",
        "status_select_row": "Отметьте хотя бы один чат и один формат.",
        "status_loading": "Загрузка списка диалогов…",
        "status_batch": "Экспорт: {done} из {total}…",
        "status_batch_done": "Готово: {ok} файл(ов), ошибок: {err}",
        "status_loaded": "Диалогов: {n}",
        "status_mode_unsupported": "Режим «Zcode Chats» пока не поддерживается.",
        "err_batch": "Ошибки экспорта ({n}):",
        "err_db_none": "База не найдена — укажите путь в поле «SQL база:».",
        "err_db_missing": "Файл базы не найден: {path}",
        "dbp_missing": "db_profiles.cfg не найден — рядом с программой записан заводской файл путей баз.",
        "dbp_corrupt": "db_profiles.cfg повреждён — битый файл сохранён как db_profiles.cfg.err, записан заводской.",
        "status_db2_exported": "SQL базы экспортированы (2 шт.): {path}",
        "lang_corrupt": "Файл языка «{file}» повреждён — используются встроенные строки языка.",
        "confirm_exit_title": "Экспорт выполняется",
        "confirm_exit_msg": "Экспорт ещё выполняется. Прервать и выйти?",
        "dlg_pick_folder": "Выберите папку для экспорта",
        "dlg_pick_db": "Укажите файл runtime.sqlite",
    },
    "en": {
        "title_explain": "AutoClaw and ZCode chat export",
        "lang_label": "Language:",
        "search": "Search chat:",
        "refresh": "Update SQL database",
        "col_project": "Project",
        "col_title": "Chat",
        "col_updated": "Updated",
        "col_created": "Created",
        "col_requests": "Num.",
        "col_tokens": "Tok",
        "row_ctx": "Current context only",
        "btn_as_model": "Preset: model's current context",
        "status_preset_applied": "“Current context” preset applied: context slice, tools on, replies off.",
        "col_type": "Type",
        "col_project_more": "•",
        "group_options": "Export options",
        "lbl_format": "Format:",
        "row_tools": "Include tool calls",
        "row_narration": "Intermediate replies",
        "row_all_files": "Show service files",
        "row_bom": "UTF-8 Byte Order Mark",
        "lbl_tool_limit": "Max result length, chars",
        "btn_browse": "Browse…",
        "btn_donate": "Vadim R.M. - Donate",
        "btn_output_folder": "Export folder",
        "btn_db": "Master database path",
        "msg_import_ask": "No local copy of {mode} data — import it?",
        "msg_import_missing": "No local copy of {mode} data — cannot import, the „Master database path“ is needed!",
        "msg_master_missing": "Master database {mode} not found — set the „Master database path“; chats still work from the local copy",
        "msg_bad_outdir": "Invalid export folder",
        "msg_long_strings": "Too long strings in file: {files}",
        "m_copy": "Copy",
        "m_paste": "Paste",
        "m_cut": "Cut",
        "m_select_all": "Select all",
        "dlg_ok": "OK",
        "dlg_yes": "Yes",
        "dlg_no": "No",
        "m_copy_item": "Copy text: {text}",
        "m_copy_title": "Copy window title text: {text}",
        "m_copy_chatlist": "Copy header and chat list",
        "msg_only_main": "Only one (main) ZCode chat database was found",
        "msg_cfg_reset": "Configuration has been reset — set the „Master database path“",
        "msg_last_mode_err": "The mode setting in the config is corrupt — AutoClaw mode is opened",
        "msg_cfg_corrupt": "ExportChat.cfg is corrupt — saved as .err, settings recreated",
        "status_copy_of": "copy of {when}",
        "status_import_done": "Copy imported",
        "status_import_self": "Cannot copy the database into itself",
        "status_import_minimal": "Copy imported; companion files not found — old ones moved to backups, functionality will be limited",
        "err_not_main_file": "Not the main database file — {name} is required",
        "err_import": "Database import failed: {msg}",
        "btn_close": "Close",
        "btn_select_all": "Select all",
        "btn_clear_all": "Clear selection",
        "btn_export_selected": "Export selected chats",
        "chk_single": "write to one file",
        "chk_hidden": "Show hidden chats",
        "btn_open_folder": "Open export folder",
        "btn_site": "Vadim R.M. - vmgames.com",
        "status_select_row": "Tick at least one chat and one format.",
        "status_loading": "Loading conversation list…",
        "status_batch": "Exporting: {done} of {total}…",
        "status_batch_done": "Done: {ok} file(s), {err} failed",
        "status_loaded": "Conversations: {n}",
        "status_mode_unsupported": "The «Zcode Chats» mode is not supported yet.",
        "err_batch": "Export errors ({n}):",
        "err_db_none": "Database not found — set the path in the \"SQL database\" field.",
        "err_db_missing": "Database file not found: {path}",
        "dbp_missing": "db_profiles.cfg not found — the factory database-paths file has been written next to the program.",
        "dbp_corrupt": "db_profiles.cfg is corrupt — the broken file was saved as db_profiles.cfg.err and the factory file has been written.",
        "status_db2_exported": "SQL databases exported (2 files): {path}",
        "lang_corrupt": "The language file “{file}” is corrupt — the built-in strings are used instead.",
        "confirm_exit_title": "Export in progress",
        "confirm_exit_msg": "An export is still running. Interrupt and exit?",
        "dlg_pick_folder": "Choose export folder",
        "dlg_pick_db": "Locate runtime.sqlite",
    },
    "zh": {
        "title_explain": "导出 AutoClaw 和 ZCode 对话",
        "lang_label": "语言：",
        "search": "搜索对话：",
        "refresh": "更新SQL数据库",
        "col_project": "项目",
        "col_title": "对话",
        "col_updated": "更新时间",
        "col_created": "创建时间",
        "col_requests": "数",
        "col_tokens": "令牌",
        "row_ctx": "仅当前上下文",
        "btn_as_model": "预设：模型的当前上下文",
        "status_preset_applied": "已应用「模型的当前上下文」预设：上下文切片，工具开，回复关。",
        "col_type": "类型",
        "col_project_more": "•",
        "group_options": "导出选项",
        "lbl_format": "格式：",
        "row_tools": "添加工具调用",
        "row_narration": "中间回复",
        "row_all_files": "显示服务文件",
        "row_bom": "UTF-8 Byte Order Mark",
        "lbl_tool_limit": "结果最大长度（字符）",
        "btn_browse": "选择…",
        "btn_donate": "Vadim R.M. - Donate",  # статично на всех языках (раунд 8)
        "btn_output_folder": "导出文件夹",
        "btn_db": "SQL数据库路径",
        "msg_import_ask": "没有 {mode} 数据的本地副本，要导入吗？",
        "msg_import_missing": "没有 {mode} 数据的本地副本——无法导入，需要「SQL数据库路径」！",
        "msg_master_missing": "未找到 {mode} 主数据库——请指定「SQL数据库路径」；聊天仍可从本地副本使用",
        "msg_bad_outdir": "导出文件夹无效",
        "msg_long_strings": "文件中的字符串过长：{files}",
        "m_copy": "复制",
        "m_paste": "粘贴",
        "m_cut": "剪切",
        "m_select_all": "全选",
        "dlg_ok": "确定",
        "dlg_yes": "是",
        "dlg_no": "否",
        "m_copy_item": "复制文本：{text}",
        "m_copy_title": "复制窗口标题文本：{text}",
        "m_copy_chatlist": "复制标题和聊天列表",
        "msg_only_main": "仅找到一台（主）ZCode 聊天数据库",
        "msg_cfg_reset": "配置已重置为初始状态——请设置「SQL数据库路径」",
        "msg_last_mode_err": "配置中的模式设置已损坏——已打开 AutoClaw 模式",
        "msg_cfg_corrupt": "ExportChat.cfg 已损坏——已存为 .err，设置已重新创建",
        "status_copy_of": "副本来自 {when}",
        "status_import_done": "副本已导入",
        "status_import_self": "不能将数据库复制到自身",
        "status_import_minimal": "副本已导入；未找到附属文件——旧文件已移入备份，功能将受限",
        "err_not_main_file": "所选文件不是主数据库文件——需要 {name}",
        "err_import": "数据库导入失败：{msg}",
        "btn_close": "关闭",
        "btn_select_all": "全选",
        "btn_clear_all": "取消选择",
        "btn_export_selected": "导出所选对话",
        "chk_single": "导出为一个文件",
        "chk_hidden": "显示隐藏对话",
        "btn_open_folder": "打开导出文件夹",
        "btn_site": "Vadim R.M. - vmgames.com",
        "status_select_row": "请至少勾选一个对话和一个格式。",
        "status_loading": "正在加载对话列表…",
        "status_batch": "导出：{done}/{total}…",
        "status_batch_done": "完成：{ok} 个文件，{err} 个错误",
        "status_loaded": "对话数：{n}",
        "status_mode_unsupported": "「Zcode Chats」模式暂不支持。",
        "err_batch": "导出错误（{n}）：",
        "err_db_none": "未找到数据库——请在“SQL 数据库”字段中指定路径。",
        "err_db_missing": "未找到数据库文件：{path}",
        "dbp_missing": "未找到 db_profiles.cfg——已在程序旁写入出厂的数据库路径文件。",
        "dbp_corrupt": "db_profiles.cfg 已损坏——损坏文件已存为 db_profiles.cfg.err，并写入了出厂文件。",
        "status_db2_exported": "SQL 数据库已导出（2 个文件）：{path}",
        "lang_corrupt": "语言文件“{file}”已损坏——改用内置字符串。",
        "confirm_exit_title": "导出正在进行",
        "confirm_exit_msg": "导出仍在进行。中断并退出？",
        "dlg_pick_folder": "选择导出文件夹",
        "dlg_pick_db": "选择 runtime.sqlite",
    },
}


def external_path(lang: str) -> Path:
    """Внешний файл языка: рядом с exe (поставка) / в корне репо (исходники)."""
    return config.config_dir() / f"lang_{lang}.cfg"


def load_external(lang: str) -> tuple[dict[str, str] | None, str | None]:
    """Прочитать lang_<язык>.cfg. Возвращает (перекрытия | None, имя битого
    файла | None). Файла нет — (None, None), это норма (раунд 23)."""
    path = external_path(lang)
    if not path.is_file():
        return None, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, path.name
    if not isinstance(raw, dict):
        return None, path.name
    # р83 (п.2): значения длиннее 500 литер — обрезка + жёлтая нота
    # (имя файла фиксирует config.clip_long)
    return {k: config.clip_long(v, path.name)
            for k, v in raw.items()
            if isinstance(k, str) and isinstance(v, str)}, None


def set_lang(lang: str) -> str | None:
    """Сменить язык и пересобрать оперативную память строк: STRINGS[lang]
    + перекрытия из внешнего файла (если есть). Возвращает имя битого
    внешнего файла (предупреждение) или None."""
    global _current, _runtime
    _current = lang if lang in LANGS else "ru"
    ext, corrupt = load_external(_current)
    table = dict(STRINGS.get(_current) or STRINGS["ru"])
    if ext:
        table.update(ext)
    _runtime = table
    return corrupt


def current_lang() -> str:
    return _current


def tr(key: str, **kwargs) -> str:
    value = (_runtime or {}).get(key) or STRINGS["ru"].get(key, key)
    try:
        return value.format(**kwargs) if kwargs else value
    except (KeyError, IndexError, ValueError):
        # правленый внешний файл со «срезанными» скобками не должен
        # ронять программу — возвращаем строку как есть
        return value


def factory_text(lang: str) -> str:
    """Заводское содержимое внешнего файла языка — точная копия STRINGS[lang]."""
    return json.dumps(STRINGS[lang], ensure_ascii=False, indent=2) + "\n"


def write_factory(lang: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(factory_text(lang), encoding="utf-8-sig")


# Оперативная память до первого set_lang — внутренние строки русского
# (внешние файлы читаются только в set_lang, при старте и переключении).
_runtime = dict(STRINGS["ru"])
