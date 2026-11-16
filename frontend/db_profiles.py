# -*- coding: utf-8 -*-
"""db_profiles.cfg — человеко-редактируемый файл путей баз (раунд 19).

Решение владельца: стандартные имена и ВСЕ варианты стандартных путей баз
AutoClaw/ZCode хранятся НЕ в коде и не в настройках exe, а в отдельном
файле db_profiles.cfg рядом с exe (в поставке он лежит сразу; в исходниках
— в корне репозитория). Программа читает его при старте и НИКОГДА не
перезаписывает валидный файл:

- файла нет          → записать заводской и СООБЩИТЬ об этом;
- файл битый/невалидный → переименовать в «db_profiles.cfg.err», записать
  заводской и СООБЩИТЬ;
- файл валидный      → читать как есть (правки — вручную текстом;
  если AutoClaw/ZCode сменит место базы — правка файла, без пересборки exe).

Формат: JSON, UTF-8 С BOM (решение владельца — Блокнот 8.1 без BOM не
распознаёт UTF-8); расширение не .json, чтобы строгие JSON-инструменты не
отвергали BOM. Читатель (utf-8-sig) терпит и файл без BOM. Ключи "_about"
и "_substitutions" — подсказки человеку, программой игнорируются.

Поддерживаемые подстановки в путях: %ПЕРЕМЕННЫЕ% окружения (напр.
%APPDATA%), ~ (домашняя папка — раскрывается через USERPROFILE ОС), *
(любое имя папки на этом месте).
"""
from __future__ import annotations

import copy
import glob
import json
import os
from pathlib import Path

import config
import i18n

MODES = ("autoclaw", "zcode")

# Заводское содержимое файла (то же, что лежит в корне репозитория).
FACTORY_DOC: dict = {
    "_about": (
        "Стандартные места баз чатов AutoClaw и ZCode. Программа читает этот "
        "файл при старте и никогда не перезаписывает валидный файл. Если "
        "приложение сменит место или имя базы — просто исправьте пути здесь "
        "текстовым редактором, пересборка exe не нужна. Формат: JSON "
        "(UTF-8 с BOM), кодировка при сохранении — UTF-8."
    ),
    "_substitutions": (
        "В путях работают подстановки: %ПЕРЕМЕННЫЕ% окружения (например "
        "%APPDATA%), ~ — домашняя папка пользователя, * — любое имя папки "
        "на этом месте. Порядок путей не важен: берётся самая свежая база."
    ),
    "autoclaw": {
        "filename": "runtime.sqlite",
        "paths": [
            "%APPDATA%/AutoClaw-oversea-official/accounts/*/runtime/runtime.sqlite",
            "%APPDATA%/AutoClaw-official/accounts/*/runtime/runtime.sqlite",
            "%APPDATA%/AutoClaw/accounts/*/runtime/runtime.sqlite",
        ],
        # Справочно: версии приложений, на которых имена/пути проверены.
        "validated_with": "AutoClaw 2.3.1.406",
    },
    "zcode": {
        "filename": "db.sqlite",
        "paths": [
            "~/.zcode/cli/db/db.sqlite",
        ],
        "validated_with": "ZCode 3.17.2.9661",
    },
}

# Профили без подсказок-ключей (для тестов и внутренних сравнений).
DEFAULT_PROFILES: dict = {
    mode: copy.deepcopy(FACTORY_DOC[mode]) for mode in MODES
}


def profiles_path() -> Path:
    return config.config_dir() / "db_profiles.cfg"


def write_factory(path: Path) -> None:
    """Записать заводской файл (UTF-8 с BOM)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(FACTORY_DOC, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8-sig")


def _profile_valid(value: object) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("filename"), str)
        and bool(value.get("filename"))
        and isinstance(value.get("paths"), list)
        and bool(value["paths"])
        and all(isinstance(p, str) and p for p in value["paths"])
        and isinstance(value.get("validated_with"), str)
    )


def is_valid(raw: object) -> bool:
    """Валидна ли секция целиком (оба профиля). Любое несоответствие —
    файл считается битым: чинить по частям опаснее, чем заменить."""
    return isinstance(raw, dict) and all(_profile_valid(raw.get(m)) for m in MODES)


def normalize(raw: object) -> dict:
    """Валидное содержимое → как есть (копия); битое → заводское целиком."""
    if is_valid(raw):
        return copy.deepcopy({m: raw[m] for m in MODES})
    return copy.deepcopy(DEFAULT_PROFILES)


def load() -> tuple[dict, str | None]:
    """Прочитать db_profiles.cfg — источник правды о местах баз.

    Возвращает (профили, ключ i18n-сообщения | None). Сообщение — только
    когда файл пришлось создавать или восстанавливать; показывать его —
    забота приложения (App показывает предупреждение при старте).
    """
    path = profiles_path()
    if not path.is_file():
        write_factory(path)
        return copy.deepcopy(DEFAULT_PROFILES), "dbp_missing"
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raw = None  # битый файл → ветка восстановления ниже
    if not is_valid(raw):
        err = Path(str(path) + ".err")
        if err.exists():
            os.replace(path, err)  # прежний .err затирается новым битым
        else:
            path.rename(err)
        write_factory(path)
        return copy.deepcopy(DEFAULT_PROFILES), "dbp_corrupt"
    return normalize(raw), None


def _expand(pattern: str) -> str:
    text = os.path.expandvars(pattern)
    return os.path.expanduser(text)


def find_db(mode: str, profiles: dict | None = None) -> Path | None:
    """Свежая (по mtime) существующая база режима по профилям; None — не нашли.

    %APPDATA% отсутствует/пуст → expandvars оставит шаблон как есть, glob
    ничего не найдёт — это корректное «не нашли».
    """
    if mode not in MODES:
        return None
    candidates: list[str] = []
    for pattern in normalize(profiles)[mode]["paths"]:
        expanded = _expand(pattern)
        if any(ch in expanded for ch in "*?["):
            candidates += [p for p in glob.glob(expanded) if os.path.isfile(p)]
        elif os.path.isfile(expanded):
            candidates.append(expanded)
    if not candidates:
        return None
    return Path(max(candidates, key=os.path.getmtime))
