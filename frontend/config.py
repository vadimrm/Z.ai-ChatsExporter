# -*- coding: utf-8 -*-
"""Настройки GUI: ExportChat.cfg рядом с exe (портативно, раунды 12–13;
имя и BOM — раунд 19). При запуске из исходников — в корне репозитория.
%APPDATA% и реестр НЕ используются вообще (решение владельца, раунд 13):
нет конфига — создаётся с нуля на месте.

Файл — UTF-8 С BOM (решение владельца, раунд 19): Блокнот старых Windows
(8.1) без BOM не распознаёт UTF-8; читатель (utf-8-sig) терпит и файл
без BOM. Внутри — обычный JSON.

ВАЖНО: пути баз AutoClaw/ZCode здесь НЕ хранятся — они в отдельном
человеко-редактируемом db_profiles.cfg рядом с exe (см. db_profiles.py).
Версия 3 формата настроек; миграций нет — релиза ещё не было (решение
владельца, раунд 19: начинаем с чистого листа).
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

FORMATS = ("md", "txt", "json")
OPTION_KEYS = ("tools", "narration", "all_files", "no_files", "bom")

# BOM в JSON невозможен (гарантия адаптеров) — в GUI ячейка серая, значение False.
DEFAULTS: dict = {
    "_version": 3,
    "lang": "ru",                       # ru | en | zh
    "output_dir": "",                   # пусто → default_output_dir()
    "db_path": "",                      # AutoClaw runtime.sqlite; пусто → авто-поиск
    "db_path_zcode": "",                # ZCode db.sqlite; пусто → авто-поиск
    "export_formats": ["md", "txt"],    # какие форматы производить
    "options": {                        # поформатная матрица опций
        fmt: {"tools": False, "narration": False, "all_files": False,
              "no_files": False, "bom": fmt != "json"}
        for fmt in FORMATS
    },
    "tool_limit": 1000,                 # обрезка результата инструмента
    "window_geometry": "",              # "ШИРИНАxВЫСОТА+X+Y"
    "single_file": False,               # чекбокс «Экспорт в один файл» (р20)
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


def load() -> dict:
    """Чтение настроек; повреждённый/отсутствующий файл → значения по умолчанию.

    Раунд 13: никаких обращений к %APPDATA% — нет конфига на месте, значит
    программа запускается впервые и создаёт настройки с нуля.
    Неизвестные ключи (включая старые форматы) молча игнорируются —
    миграций нет, чистый лист (раунд 19).
    """
    values = copy.deepcopy(DEFAULTS)
    try:
        raw = json.loads(config_path().read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return values
    if not isinstance(raw, dict):
        return values
    for key in ("lang", "output_dir", "db_path", "db_path_zcode",
                "tool_limit", "window_geometry"):
        if key in raw:
            values[key] = raw[key]
    if "single_file" in raw:
        values["single_file"] = bool(raw["single_file"])
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
    for key in ("lang", "output_dir", "db_path", "db_path_zcode",
                "tool_limit", "window_geometry"):
        if key in values:
            merged[key] = values[key]
    merged["single_file"] = bool(values.get("single_file", False))
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
