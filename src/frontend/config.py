# -*- coding: utf-8 -*-
"""Настройки GUI: ExportChat.cfg рядом с exe (портативно, раунды 12–13;
имя и BOM — раунд 19). При запуске из исходников — в корне репозитория.
%APPDATA% и реестр НЕ используются вообще (решение владельца, раунд 13):
нет конфига — создаётся с нуля на месте.

Файл — UTF-8 С BOM (решение владельца, раунд 19): Блокнот старых Windows
(8.1) без BOM не распознаёт UTF-8; читатель (utf-8-sig) терпит и файл
без BOM. Внутри — обычный JSON.

ВАЖНО: пути баз AutoClaw/ZCode здесь — пути МАСТЕР-ИСТОЧНИКОВ (р46):
программа читает их только при импорте локальной копии и работает
исключительно со своими копиями в подпапках AutoClawData/ZCodeData
(config.data_dir; имена фиксированы, в конфиг не записываются).
Версия 7 формата настроек (р81: удалён ключ no_files; v6 читается
с миграцией — просто выкинуть no_files). Прежняя история: раунд 19 —
начали с чистого листа; р36 — db_path → db_path_autoclaw; р44 —
last_mode: GUI открывается в режиме последней сессии; р46 —
db_path_zcode_index удалён (tasks-index выводится из пути мастера и
копируется при импорте), ключ last_mode при мусоре не сбрасывается —
решает App).
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

FORMATS = ("md", "txt", "json")
# р81 (п.4): no_files («Скрыть блоки файлов») удалён — файловые блоки
# показываются всегда; cfg v7; v6 читается с миграцией (см. load)
OPTION_KEYS = ("tools", "narration", "all_files", "bom",
               "ctx")  # ctx — р43: «Только актуальный контекст» (только ZCode)

# р83 (п.2, владелец): строки из конфигов/языковых файлов длиннее
# LONG_STRING_LIMIT литер обрезаются (хвост отбрасывается); имена файлов
# фиксируются здесь — App показывает жёлтую ноту «Слишком длинные строки
# в файле: …». Единый реестр для config/i18n/db_profiles.
LONG_STRING_LIMIT = 500
LONG_STRING_FILES: list[str] = []


def clip_long(value, filename: str):
    """Обрезать строку до LONG_STRING_LIMIT; не-строки проходят как есть.
    Имя файла попадает в LONG_STRING_FILES (без дублей)."""
    if not isinstance(value, str) or len(value) <= LONG_STRING_LIMIT:
        return value
    if filename not in LONG_STRING_FILES:
        LONG_STRING_FILES.append(filename)
    return value[:LONG_STRING_LIMIT]


def clip_tree(node, filename: str):
    """Рекурсивная обрезка всех СТРОК-значений (ключи не трогаем)."""
    if isinstance(node, dict):
        return {k: clip_tree(v, filename) for k, v in node.items()}
    if isinstance(node, list):
        return [clip_tree(v, filename) for v in node]
    return clip_long(node, filename)

# BOM в JSON невозможен (гарантия адаптеров) — в GUI ячейка серая, значение False.
DEFAULTS: dict = {
    "_version": 7,
    "lang": "ru",                       # ru | en | zh
    "output_dir": "",                   # пусто → default_output_dir()
    "db_path_autoclaw": "",             # AutoClaw runtime.sqlite; пусто → авто-поиск
    "db_path_zcode": "",                # ZCode db.sqlite; пусто → авто-поиск
    "export_formats": ["md", "txt"],    # какие форматы производить
    "options": {                        # поформатная матрица опций
        fmt: {"tools": False, "narration": False, "all_files": False,
              "bom": fmt != "json", "ctx": False}
        for fmt in FORMATS
    },
    "tool_limit": 1000,                 # обрезка результата инструмента
    "window_geometry": "",              # "ШИРИНАxВЫСОТА+X+Y"
    "single_file": False,               # чекбокс «Экспорт в один файл» (р20)
    "show_subagents": False,            # показывать чаты субагентов (р26)
    # р44 (v5): режим последней сессии — GUI открывается в нём
    "last_mode": "zcode",              # р76 (владелец): первый запуск
                                      # — режим ZCode; далее — последняя сессия
}


def config_dir() -> Path:
    """Папка переносимых файлов: тестовое окружение / папка exe / корень репо.

    Её же использует db_profiles.cfg — оба файла рядом (решение владельца:
    «конфиг путей должен лежать снаружи в поставке»).
    """
    override = os.environ.get("EXPORTCHAT_CONFIG_DIR")
    if override:
        return Path(override)
    # Раунды 12–13: портативно — в папке самого exe (поставка, «for tests»);
    # из исходников — в корне репозитория.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def default_output_dir() -> Path:
    """Раунд 13: папка вывода по умолчанию — там же, где лежит exe
    (портативно); из исходников — корень репозитория."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def config_path() -> Path:
    return config_dir() / "ExportChat.cfg"


def validate(raw) -> bool:
    """р63 (я7): строгая проверка структуры ExportChat.cfg — любое
    отклонение = повреждение (владелец: удаление/переименование ключа
    или чужой _version не должны «молча исправляться», стирая файл):
    не словарь; _version ≠ текущей; набор ключей верхнего уровня не тот
    (лишний/пропущенный); неверные типы значений; options не по всем
    форматам или с чужими/пропущенными ключами. Валидный файл → True.
    Значение last_mode проверяет App (мусор → режим AutoClaw, р46)."""
    if not isinstance(raw, dict):
        return False
    if raw.get("_version") != DEFAULTS["_version"]:
        return False
    if set(raw.keys()) != set(DEFAULTS.keys()):
        return False
    for key in ("lang", "output_dir", "db_path_autoclaw",
                "db_path_zcode", "window_geometry", "last_mode"):
        if not isinstance(raw[key], str):
            return False
    if (not isinstance(raw["tool_limit"], int)
            or isinstance(raw["tool_limit"], bool)):
        return False
    if (not isinstance(raw["export_formats"], list)
            or not all(f in FORMATS for f in raw["export_formats"])):
        return False
    if not isinstance(raw["single_file"], bool):
        return False
    if not isinstance(raw["show_subagents"], bool):
        return False
    opts = raw["options"]
    if not isinstance(opts, dict) or set(opts.keys()) != set(FORMATS):
        return False
    for fmt in FORMATS:
        sub = opts[fmt]
        if not isinstance(sub, dict) or set(sub.keys()) != set(OPTION_KEYS):
            return False
        if not all(isinstance(sub[key], bool) for key in OPTION_KEYS):
            return False
    return True


def load() -> dict:
    """Чтение настроек; повреждённый/отсутствующий файл → значения по умолчанию.

    Раунд 13: никаких обращений к %APPDATA% — нет конфига на месте, значит
    программа запускается впервые и создаёт настройки с нуля.
    р63 (я7): строго — файл с чужой структурой (удалённый/переименованный
    ключ, неверный _version) считается повреждённым → дефолты (App
    переименовывает его в .err с сообщением). Прежде такие файлы молча
    «исправлялись», стирая содержимое.
    """
    values = copy.deepcopy(DEFAULTS)
    try:
        raw = json.loads(config_path().read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return values
    # р81 (п.4): миграция v6 → v7 — просто убрать no_files из options.
    # Прочее — по-прежнему строго (чужие версии/ключи = повреждение).
    if isinstance(raw, dict) and raw.get("_version") == 6:
        raw["_version"] = 7
        if isinstance(raw.get("options"), dict):
            for sub in raw["options"].values():
                if isinstance(sub, dict):
                    sub.pop("no_files", None)
    if not validate(raw):  # р63 (я7)
        return values
    for key in ("lang", "output_dir", "db_path_autoclaw", "db_path_zcode",
                "tool_limit", "window_geometry", "last_mode"):
        if key in raw:
            # р83 (п.2): строки длиннее 500 литер — обрезка + нота
            values[key] = (clip_long(raw[key], config_path().name)
                           if isinstance(raw[key], str) else raw[key])
    # р46: мусорный last_mode НЕ сбрасывается здесь — решает App
    # (AutoClaw + сообщение об ошибке конфига)
    if "single_file" in raw:
        values["single_file"] = bool(raw["single_file"])
    if "show_subagents" in raw:
        values["show_subagents"] = bool(raw["show_subagents"])
    if isinstance(raw.get("export_formats"), list):
        formats = [f for f in raw["export_formats"] if f in FORMATS]
        if formats:
            values["export_formats"] = formats
    if isinstance(raw.get("options"), dict):
        for fmt in FORMATS:
            source = raw["options"].get(fmt)
            if isinstance(source, dict):
                for key in OPTION_KEYS:
                    if isinstance(source.get(key), bool):
                        values["options"][fmt][key] = source[key]
    return values


def save(values: dict) -> None:
    """Атомарная запись только известных ключей (tmp + os.replace); UTF-8 c BOM."""
    merged = copy.deepcopy(DEFAULTS)
    for key in ("lang", "output_dir", "db_path_autoclaw", "db_path_zcode",
                "tool_limit", "window_geometry", "last_mode"):
        if key in values:
            merged[key] = values[key]
    merged["single_file"] = bool(values.get("single_file", False))
    merged["show_subagents"] = bool(values.get("show_subagents", False))
    if isinstance(values.get("export_formats"), list):
        merged["export_formats"] = [f for f in values["export_formats"] if f in FORMATS]
    if isinstance(values.get("options"), dict):
        for fmt in FORMATS:
            source = values["options"].get(fmt, {})
            if isinstance(source, dict):
                for key in OPTION_KEYS:
                    if isinstance(source.get(key), bool):
                        merged["options"][fmt][key] = source[key]
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8-sig")
    os.replace(tmp, path)

# ---- р46: локальные копии мастер-данных (работа только с копиями) ----

DATA_DIR_NAMES = {"autoclaw": "AutoClawData", "zcode": "ZCodeData"}
DATA_FILE = {"autoclaw": "runtime.sqlite", "zcode": "db.sqlite"}
INDEX_FILE = "tasks-index.sqlite"      # 2-я база ZCode (tasks-index)


def data_dir(mode: str) -> Path:
    """Папка локальных копий режима: рядом с exe (конфиг-директория),
    фиксированное имя — в ExportChat.cfg НЕ записывается (р46)."""
    return config_dir() / DATA_DIR_NAMES[mode]


def local_db_path(mode: str) -> Path:
    """Локальная копия основной базы режима."""
    return data_dir(mode) / DATA_FILE[mode]


def local_index_path() -> Path:
    """Локальная копия 2-й базы ZCode (tasks-index)."""
    return data_dir("zcode") / INDEX_FILE
