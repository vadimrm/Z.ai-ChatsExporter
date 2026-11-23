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

MODES = ("autoclaw", "zcode")

# Заводское содержимое файла (то же, что лежит в корне репозитория).
FACTORY_DOC: dict = {
    "_version": 3,
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
        "на этом месте. Порядок путей не важен: берётся самая свежая база. "
        "Версия 3: paths ведут ТОЛЬКО к главному файлу базы; остальные "
        "файлы комплекта (files) — ОТНОСИТЕЛЬНО папки главного (значение — "
        "относительная папка, имя файла = ключ)."
    ),
    "autoclaw": {
        "main_file": "runtime.sqlite",
        "paths": [
            "%APPDATA%/AutoClaw-oversea-official/accounts/*/runtime/runtime.sqlite",
            "%APPDATA%/AutoClaw-official/accounts/*/runtime/runtime.sqlite",
            "%APPDATA%/AutoClaw/accounts/*/runtime/runtime.sqlite",
        ],
        # полный комплект файлов базы (р67): 3 файла
        "files": {
            "runtime.sqlite": ".",
            "runtime.sqlite-wal": ".",
            "runtime.sqlite-shm": "."
        },
        # Справочно: версии приложений, на которых имена/пути проверены.
        "validated_with": "AutoClaw 2.3.1.406",
    },
    "zcode": {
        "main_file": "db.sqlite",
        "paths": [
            "~/.zcode/cli/db/db.sqlite",
        ],
        # 2-я база ZCode — индекс (названия проектов; раунды 30/31):
        # полный комплект — 6 файлов (db + tasks-index с их -wal/-shm)
        "second_file": "tasks-index.sqlite",
        "files": {
            "db.sqlite": ".",
            "db.sqlite-wal": ".",
            "db.sqlite-shm": ".",
            "tasks-index.sqlite": "../../v2",
            "tasks-index.sqlite-wal": "../../v2",
            "tasks-index.sqlite-shm": "../../v2"
        },
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


def _profile_valid(mode: str, value: object) -> bool:
    """Секция одного режима формата v3 (р67): main_file (обязан совпадать
    со стандартным локальным именем — адаптеры пишут под него), paths
    только к главному файлу, files — ПОЛНЫЙ комплект файлов базы
    (значение — относительная папка от главного); у zcode обязателен
    second_file (2-я база) из files."""
    ok = (
        isinstance(value, dict)
        and value.get("main_file") == config.DATA_FILE[mode]
        and isinstance(value.get("paths"), list)
        and bool(value["paths"])
        and all(isinstance(p, str) and p for p in value["paths"])
        and isinstance(value.get("files"), dict)
        and bool(value["files"])
        and all(isinstance(k, str) and k
                and isinstance(v, str) and v
                for k, v in value["files"].items())
        and value["main_file"] in value["files"]
        and isinstance(value.get("validated_with"), str)
    )
    if mode == "zcode" and ok:
        second = value.get("second_file")
        ok = (isinstance(second, str) and second
              and second in value["files"])
    return ok


def is_valid(raw: object) -> bool:
    """Валидна ли секция целиком (оба профиля + версия формата).
    _version обязана быть ровно 3 (р67): старый файл без версии —
    битый → .err + заводской. Любое несоответствие — файл считается
    битым: чинить по частям опаснее, чем заменить."""
    return (isinstance(raw, dict)
            and raw.get("_version") == 3
            and all(_profile_valid(m, raw.get(m)) for m in MODES))


def normalize(raw: object) -> dict:
    """Валидные ПРОФИЛИ (в памяти или из файла) → как есть (копия);
    битые → заводские целиком. _version здесь НЕ проверяется — это
    формат файла (load); тесты и вызовы передают профили без него."""
    if (isinstance(raw, dict)
            and all(_profile_valid(m, raw.get(m)) for m in MODES)):
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
    # р67: версия формата проверяется при чтении ФАЙЛА (владелец);
    # старый файл без _version/с другой — битый → .err + заводской
    if not is_valid(raw):
        err = Path(str(path) + ".err")
        if err.exists():
            os.replace(path, err)  # прежний .err затирается новым битым
        else:
            path.rename(err)
        write_factory(path)
        return copy.deepcopy(DEFAULT_PROFILES), "dbp_corrupt"
    # р83 (п.2): строки-значения длиннее 500 литер — обрезка + нота
    return normalize(config.clip_tree(raw, path.name)), None


def _expand(pattern: str) -> str:
    text = os.path.expandvars(pattern)
    return os.path.expanduser(text)


def find_db(mode: str, profiles: dict | None = None) -> Path | None:
    """Свежая (по mtime) существующая ГЛАВНАЯ база режима по профилям;
    None — не нашли. (В v3 paths ведут только к главному файлу; 2-я база
    ZCode ищется относительно найденного мастера — companion_path.)

    %APPDATA% отсутствует/пуст → expandvars оставит шаблон как есть, glob
    ничего не найдёт — это корректное «не нашли».
    """
    if mode not in MODES:
        return None
    candidates: list[str] = []
    for pattern in normalize(profiles)[mode].get("paths") or []:
        expanded = _expand(pattern)
        if any(ch in expanded for ch in "*?["):
            candidates += [p for p in glob.glob(expanded) if os.path.isfile(p)]
        elif os.path.isfile(expanded):
            candidates.append(expanded)
    if not candidates:
        return None
    return Path(max(candidates, key=os.path.getmtime))


def _section(mode: str, profiles: dict | None) -> dict:
    return normalize(profiles).get(mode) or {}


def main_file_of(mode: str, profiles: dict | None = None) -> str:
    """р67: имя главного файла базы режима (проверка диалога/поля)."""
    return (_section(mode, profiles).get("main_file")
            or config.DATA_FILE[mode])


def second_file_of(mode: str, profiles: dict | None = None) -> str | None:
    """р67: имя 2-й базы режима (zcode: tasks-index) или None."""
    return _section(mode, profiles).get("second_file") or None


def files_of(mode: str, profiles: dict | None = None) -> dict[str, str]:
    """р67: ПОЛНЫЙ комплект файлов базы {имя: относительная папка от
    главного} — источник списка для бэкапов и поиска сопутствующих."""
    return dict(_section(mode, profiles).get("files") or {})


def companion_path(mode: str, master: Path, name: str,
                   profiles: dict | None = None) -> Path:
    """р67: абсолютный путь сопутствующего файла — ОДНОЗНАЧНО по
    относительной папке из files (путь только к главному в конфиге)."""
    relative = files_of(mode, profiles).get(name) or "."
    return master.parent / relative / name
