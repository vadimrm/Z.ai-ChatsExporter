# -*- coding: utf-8 -*-
"""Локализация интерфейса: ru (источник), en, zh.

Брендинг «Z.ai Chats Exporter by Vadim R.M.» — константа в app.py, не
переводится (AGREEMENTS.md №10); пояснение в заголовке после дефиса — ключ
title_explain, переводится. Ключ row_bom — технический термин, одинаков
во всех языках. Смена языка — без перезапуска. Ключи всех трёх языков
обязаны совпадать (проверяется тестом).
"""
from __future__ import annotations

LANGS = ("ru", "en", "zh")

_current = "ru"

STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        "title_explain": "экспорт диалогов AutoClaw и ZCode",
        "lang_label": "Язык:",
        "search": "Поиск чата:",
        "refresh": "Обновить чаты",
        "col_title": "Название",
        "col_updated": "Обновлён",
        "col_created": "Создан",
        "col_requests": "Запросов",
        "group_options": "Параметры экспорта",
        "lbl_format": "Формат:",
        "row_tools": "Добавлять вызов инструментов",
        "row_narration": "Промежуточные реплики",
        "row_all_files": "Показать служебные файлы",
        "row_no_files": "Скрыть блоки файлов",
        "row_bom": "UTF-8 Byte Order Mark",
        "lbl_tool_limit": "Максимальная длина, литер",
        "btn_browse": "Обзор…",
        "btn_export_db": "Экспорт SQL базы",
        "btn_donate": "Donate",  # статично на всех языках (раунд 8)
        "btn_output_folder": "Папка экспорта",
        "btn_db": "SQL база",
        "copy_title": "Копировать заголовок окна",
        "copy": "Копировать",
        "btn_close": "Закрыть",
        "btn_select_all": "Выбрать всё",
        "btn_clear_all": "Снять выбор",
        "btn_export_selected": "Экспортировать выбранные чаты",
        "chk_single": "записать в один файл",
        "btn_open_folder": "Открыть папку экспорта",
        "btn_site": "Vadim R.M. - авторский сайт",
        "status_select_row": "Отметьте хотя бы один чат и один формат.",
        "status_loading": "Загрузка списка диалогов…",
        "status_batch": "Экспорт: {done} из {total}…",
        "status_batch_done": "Готово: {ok} файл(ов), ошибок: {err}",
        "status_loaded": "Диалогов: {n}",
        "status_mode_unsupported": "Режим «Zcode Chats» пока не поддерживается.",
        "err_batch": "Ошибки экспорта ({n}):",
        "err_db_none": "База не найдена — укажите путь в поле «SQL база:».",
        "err_db_missing": "Файл базы не найден: {path}",
        "err_db_copy": "Не удалось скопировать базу: {msg}",
        "status_db_exported": "SQL база экспортирована: {path}",
        "dbp_missing": "db_profiles.cfg не найден — рядом с программой записан заводской файл путей баз.",
        "dbp_corrupt": "db_profiles.cfg повреждён — битый файл сохранён как db_profiles.cfg.err, записан заводской.",
        "confirm_exit_title": "Экспорт выполняется",
        "confirm_exit_msg": "Экспорт ещё выполняется. Прервать и выйти?",
        "dlg_pick_folder": "Выберите папку для экспорта",
        "dlg_pick_db": "Укажите файл runtime.sqlite",
        "dlg_export_db": "Сохранить копию базы как",
    },
    "en": {
        "title_explain": "AutoClaw and ZCode chat export",
        "lang_label": "Language:",
        "search": "Search chat:",
        "refresh": "Refresh chats",
        "col_title": "Title",
        "col_updated": "Updated",
        "col_created": "Created",
        "col_requests": "Requests",
        "group_options": "Export options",
        "lbl_format": "Format:",
        "row_tools": "Include tool calls",
        "row_narration": "Intermediate replies",
        "row_all_files": "Show service files",
        "row_no_files": "Hide file blocks",
        "row_bom": "UTF-8 Byte Order Mark",
        "lbl_tool_limit": "Max result length, chars",
        "btn_browse": "Browse…",
        "btn_export_db": "Export SQL database",
        "btn_donate": "Donate",
        "btn_output_folder": "Export folder",
        "btn_db": "SQL database",
        "copy_title": "Copy window title",
        "copy": "Copy",
        "btn_close": "Close",
        "btn_select_all": "Select all",
        "btn_clear_all": "Clear selection",
        "btn_export_selected": "Export selected chats",
        "chk_single": "write to one file",
        "btn_open_folder": "Open export folder",
        "btn_site": "Vadim R.M. - author's site",
        "status_select_row": "Tick at least one chat and one format.",
        "status_loading": "Loading conversation list…",
        "status_batch": "Exporting: {done} of {total}…",
        "status_batch_done": "Done: {ok} file(s), {err} failed",
        "status_loaded": "Conversations: {n}",
        "status_mode_unsupported": "The «Zcode Chats» mode is not supported yet.",
        "err_batch": "Export errors ({n}):",
        "err_db_none": "Database not found — set the path in the \"SQL database\" field.",
        "err_db_missing": "Database file not found: {path}",
        "err_db_copy": "Failed to copy the database: {msg}",
        "status_db_exported": "SQL database exported: {path}",
        "dbp_missing": "db_profiles.cfg not found — the factory database-paths file has been written next to the program.",
        "dbp_corrupt": "db_profiles.cfg is corrupt — the broken file was saved as db_profiles.cfg.err and the factory file has been written.",
        "confirm_exit_title": "Export in progress",
        "confirm_exit_msg": "An export is still running. Interrupt and exit?",
        "dlg_pick_folder": "Choose export folder",
        "dlg_pick_db": "Locate runtime.sqlite",
        "dlg_export_db": "Save a copy of the database as",
    },
    "zh": {
        "title_explain": "导出 AutoClaw 和 ZCode 对话",
        "lang_label": "语言：",
        "search": "搜索对话：",
        "refresh": "刷新对话",
        "col_title": "名称",
        "col_updated": "更新时间",
        "col_created": "创建时间",
        "col_requests": "请求数",
        "group_options": "导出选项",
        "lbl_format": "格式：",
        "row_tools": "添加工具调用",
        "row_narration": "中间回复",
        "row_all_files": "显示服务文件",
        "row_no_files": "隐藏文件块",
        "row_bom": "UTF-8 Byte Order Mark",
        "lbl_tool_limit": "结果最大长度（字符）",
        "btn_browse": "选择…",
        "btn_export_db": "导出 SQL 数据库",
        "btn_donate": "Donate",  # статично на всех языках (раунд 8)
        "btn_output_folder": "导出文件夹",
        "btn_db": "SQL 数据库",
        "copy_title": "复制窗口标题",
        "copy": "复制",
        "btn_close": "关闭",
        "btn_select_all": "全选",
        "btn_clear_all": "取消选择",
        "btn_export_selected": "导出所选对话",
        "chk_single": "导出为一个文件",
        "btn_open_folder": "打开导出文件夹",
        "btn_site": "Vadim R.M. - 作者网站",
        "status_select_row": "请至少勾选一个对话和一个格式。",
        "status_loading": "正在加载对话列表…",
        "status_batch": "导出：{done}/{total}…",
        "status_batch_done": "完成：{ok} 个文件，{err} 个错误",
        "status_loaded": "对话数：{n}",
        "status_mode_unsupported": "「Zcode Chats」模式暂不支持。",
        "err_batch": "导出错误（{n}）：",
        "err_db_none": "未找到数据库——请在“SQL 数据库”字段中指定路径。",
        "err_db_missing": "未找到数据库文件：{path}",
        "err_db_copy": "复制数据库失败：{msg}",
        "status_db_exported": "SQL 数据库已导出：{path}",
        "dbp_missing": "未找到 db_profiles.cfg——已在程序旁写入出厂的数据库路径文件。",
        "dbp_corrupt": "db_profiles.cfg 已损坏——损坏文件已存为 db_profiles.cfg.err，并写入了出厂文件。",
        "confirm_exit_title": "导出正在进行",
        "confirm_exit_msg": "导出仍在进行。中断并退出？",
        "dlg_pick_folder": "选择导出文件夹",
        "dlg_pick_db": "选择 runtime.sqlite",
        "dlg_export_db": "将数据库副本另存为",
    },
}


def set_lang(lang: str) -> None:
    global _current
    _current = lang if lang in LANGS else "ru"


def current_lang() -> str:
    return _current


def tr(key: str, **kwargs) -> str:
    table = STRINGS.get(_current) or STRINGS["ru"]
    value = table.get(key) or STRINGS["ru"].get(key, key)
    return value.format(**kwargs) if kwargs else value
