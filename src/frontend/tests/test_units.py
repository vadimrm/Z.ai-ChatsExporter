# -*- coding: utf-8 -*-
"""Модульные тесты: ExportChat.cfg + db_profiles.cfg, i18n, job_runner.

Запуск из корня репозитория:  python frontend\\tests\\test_units.py
Конфиг-тесты пишут только во временную папку (EXPORTCHAT_CONFIG_DIR).
Базы (если найдены) читаются только на чтение.
"""
from __future__ import annotations

import copy
import glob
import json
import os
import sqlite3
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "frontend"))
sys.path.insert(0, str(ROOT / "backend"))

import config  # noqa: E402
import db_profiles  # noqa: E402
import i18n  # noqa: E402
import job_runner as jr  # noqa: E402
from adapter import ExportOptions, adapter_for  # noqa: E402

PASS_COUNT = 0
FAIL_COUNT = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print(f"  PASS  {name}")
    else:
        FAIL_COUNT += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def drain_until(runner: jr.JobRunner, predicate, timeout: float = 60.0):
    """Собирать события, пока predicate(event) не сработает; вернуть всё.

    Возврат — только когда предикат совпал И рабочий поток освободился:
    событие кладётся в очередь чуть раньше сброса busy, и поспешный
    следующий submit был бы молча проигнорирован (гонка, ловилась редко).
    """
    events: list[tuple] = []
    matched = False
    deadline = time.time() + timeout
    while time.time() < deadline:
        for event in runner.drain():
            events.append(event)
            if predicate(event):
                matched = True
        if matched and not runner.busy():
            return events
        time.sleep(0.02)
    return events


def find_ac_db() -> Path | None:
    appdata = os.environ.get("APPDATA", "")
    cands = glob.glob(os.path.join(
        appdata, "AutoClaw*", "accounts", "*", "runtime", "runtime.sqlite"))
    return Path(max(cands, key=os.path.getmtime)) if cands else None


def test_config(tmp_base: Path, real_appdata: str | None) -> None:
    print("config (ExportChat.cfg)")
    # путь по умолчанию (запуск из исходников) — корень репозитория
    os.environ.pop("EXPORTCHAT_CONFIG_DIR", None)
    check("ExportChat.cfg из исходников — в корне репо",
          config.config_path() == ROOT / "ExportChat.cfg",
          str(config.config_path()))

    cfg_dir = tmp_base / "cfg"
    os.environ["EXPORTCHAT_CONFIG_DIR"] = str(cfg_dir)
    shutil.rmtree(cfg_dir, ignore_errors=True)
    empty_appdata = tmp_base / "empty_appdata"
    empty_appdata.mkdir(parents=True, exist_ok=True)
    os.environ["APPDATA"] = str(empty_appdata)

    values = config.load()
    check("load без файла → дефолты", values == copy.deepcopy(config.DEFAULTS))
    check("дефолт форматов MD+TXT", values["export_formats"] == ["md", "txt"])
    check("дефолт BOM: md/txt вкл, json выкл",
          values["options"]["md"]["bom"] and values["options"]["txt"]["bom"]
          and not values["options"]["json"]["bom"])
    check("в настройках НЕТ секции db_profiles (отдельный файл, раунд 19)",
          "db_profiles" not in values and "db_profiles" not in config.DEFAULTS)

    values["options"]["md"]["tools"] = True
    values["options"]["txt"]["bom"] = False
    values["export_formats"] = ["json"]
    values["tool_limit"] = 500
    values["single_file"] = True
    values["db_path_autoclaw"] = "C:\\a\\runtime.sqlite"
    values["db_path_zcode"] = "C:\\z\\db.sqlite"
    values["чужой_ключ"] = 1
    config.save(values)
    check("save создал файл", config.config_path().is_file())
    check("ExportChat.cfg записан с BOM",
          config.config_path().read_bytes()[:3] == b"\xef\xbb\xbf")

    again = config.load()
    check("roundtrip матрицы", again["options"]["md"]["tools"] is True
          and again["options"]["txt"]["bom"] is False)
    check("roundtrip форматов", again["export_formats"] == ["json"])
    check("roundtrip db_path_autoclaw (переименован из db_path, р36)",
          again["db_path_autoclaw"] == "C:\\a\\runtime.sqlite")
    check("roundtrip db_path_zcode",
          again["db_path_zcode"] == "C:\\z\\db.sqlite")
    check("roundtrip single_file (чекбокс, р20)",
          again["single_file"] is True)
    check("json BOM всегда False", again["options"]["json"]["bom"] is False)
    check("неизвестный ключ не сохранён", "чужой_ключ" not in again)
    check("версия конфига 7 (р81: no_files удалён)",
          again["_version"] == 7)
    values["last_mode"] = "zcode"
    config.save(values)
    check("roundtrip last_mode (р44)", config.load()["last_mode"] == "zcode")
    values["last_mode"] = "мусор"
    config.save(values)
    check("р46: мусорный last_mode хранится как есть — решает App",
          config.load()["last_mode"] == "мусор", "")
    check("р46: data_dir/local_db_path рядом с конфигом",
          config.data_dir("zcode").name == "ZCodeData"
          and config.data_dir("autoclaw").name == "AutoClawData"
          and config.local_db_path("zcode").parent
          == config.data_dir("zcode")
          and config.local_db_path("zcode").name == "db.sqlite"
          and config.local_db_path("autoclaw").name == "runtime.sqlite"
          and config.local_index_path().name == "tasks-index.sqlite",
          str(config.local_db_path("zcode")))

    # р63 (я7): старый формат v1 — ПОВРЕЖДЁННЫЙ (строгая валидация):
    # прежде известные ключи молча читались; владелец потребовал считать
    # любую чужую структуру повреждением → дефолты, .err делает App
    v1 = {"_version": 1, "lang": "en", "tool_limit": 4000,
          "format": "json", "tools": True, "no_bom": True}
    config.config_path().write_text(json.dumps(v1), encoding="utf-8-sig")
    old = config.load()
    check("р63 (я7): старый v1 — повреждён → дефолты",
          old == copy.deepcopy(config.DEFAULTS), str(old))
    check("р63 (я7): validate(v1) = False", config.validate(v1) is False)

    # р81 (п.4): миграция v6 → v7 — v6 валиден, no_files просто выбрасывается;
    # прочие настройки сохраняются; v5 — по-прежнему повреждён
    v6 = copy.deepcopy(config.DEFAULTS)
    v6["_version"] = 6
    v6["lang"] = "en"
    for fmt in config.FORMATS:
        v6["options"][fmt]["no_files"] = fmt == "md"
    config.config_path().write_text(json.dumps(v6), encoding="utf-8-sig")
    migrated = config.load()
    check("р81: v6 (с no_files) мигрирует, а не портится",
          migrated["_version"] == 7 and migrated["lang"] == "en"
          and all("no_files" not in migrated["options"][f]
                  for f in config.FORMATS), str(migrated["options"]["md"]))
    v5 = copy.deepcopy(v6)
    v5["_version"] = 5
    config.config_path().write_text(json.dumps(v5), encoding="utf-8-sig")
    check("р81: v5 — повреждён → дефолты",
          config.load() == copy.deepcopy(config.DEFAULTS))

    # р83 (п.2): строки конфигов длиннее 500 литер — обрезка + реестр
    config.LONG_STRING_FILES.clear()
    long_cfg = copy.deepcopy(config.DEFAULTS)
    long_cfg["output_dir"] = "Я" * 600
    long_cfg["db_path_zcode"] = "Z" * 501
    config.config_path().write_text(json.dumps(long_cfg),
                                    encoding="utf-8-sig")
    clipped_cfg = config.load()
    check("р83: cfg-строки обрезаны до 500 (короткая 501 — тоже)",
          len(clipped_cfg["output_dir"]) == 500
          and clipped_cfg["output_dir"] == "Я" * 500
          and len(clipped_cfg["db_path_zcode"]) == 500,
          (len(clipped_cfg["output_dir"]),
           len(clipped_cfg["db_path_zcode"])))
    check("р83: имя файла в реестре длинных строк",
          config.LONG_STRING_FILES == ["ExportChat.cfg"],
          str(config.LONG_STRING_FILES))
    check("р83: clip_long — не-строки и короткие проходят",
          config.clip_long(7, "x.cfg") == 7
          and config.clip_long("abc", "x.cfg") == "abc")

    # р83: внешний lang-файл — значения обрезаются
    import i18n as i18n_mod
    config.LONG_STRING_FILES.clear()
    (config.config_dir() / "lang_ru.cfg").write_text(
        json.dumps({"btn_donate": "D" * 600}), encoding="utf-8-sig")
    i18n_mod.set_lang("ru")
    check("р83: lang-значение обрезано до 500, файл в реестре",
          len(i18n_mod.tr("btn_donate")) == 500
          and config.LONG_STRING_FILES == ["lang_ru.cfg"],
          (len(i18n_mod.tr("btn_donate")), str(config.LONG_STRING_FILES)))
    (config.config_dir() / "lang_ru.cfg").unlink()
    i18n_mod.set_lang("ru")

    # %APPDATA% НЕ читается никогда — даже если там лежит конфиг
    (empty_appdata / "ExportChat.cfg").write_text(
        json.dumps({"_version": 3, "lang": "en", "tool_limit": 777}),
        encoding="utf-8-sig")
    os.remove(config.config_path())
    check("конфиг из %APPDATA% не подхватывается (портативность, раунд 13)",
          config.load() == copy.deepcopy(config.DEFAULTS))
    shutil.rmtree(empty_appdata, ignore_errors=True)
    empty_appdata.mkdir(parents=True, exist_ok=True)
    check("папка вывода по умолчанию (исходники) — корень репо (раунд 13)",
          config.default_output_dir() == ROOT, str(config.default_output_dir()))

    config.config_path().write_text("{ это не json", encoding="utf-8")
    check("повреждённый файл → дефолты",
          config.load() == copy.deepcopy(config.DEFAULTS))

    # мутации загруженного словаря не портят ни DEFAULTS, ни следующий load
    values = config.load()
    values["lang"] = "en"
    values["options"]["md"]["bom"] = False
    fresh = config.load()
    check("DEFAULTS не мутируются: lang", fresh["lang"] == "ru")
    check("DEFAULTS не мутируются: options",
          fresh["options"]["md"]["bom"] is True)
    check("DEFAULTS не мутируются на месте",
          config.DEFAULTS["lang"] == "ru")

    if real_appdata is None:
        os.environ.pop("APPDATA", None)
    else:
        os.environ["APPDATA"] = real_appdata


def test_db_profiles(tmp_base: Path, real_appdata: str | None) -> None:
    print("db_profiles (db_profiles.cfg — источник правды)")
    check("normalize(None) → дефолты",
          db_profiles.normalize(None) == db_profiles.DEFAULT_PROFILES)
    check("normalize(мусор) → дефолты",
          db_profiles.normalize([1, 2]) == db_profiles.DEFAULT_PROFILES)

    # битые поля одного профиля → секция целиком из умолчаний (раунд 19)
    broken = copy.deepcopy(db_profiles.DEFAULT_PROFILES)
    broken["zcode"]["main_file"] = ""
    check("normalize: пустое main_file → дефолты",
          db_profiles.normalize(broken) == db_profiles.DEFAULT_PROFILES)
    broken = copy.deepcopy(db_profiles.DEFAULT_PROFILES)
    broken["autoclaw"]["paths"] = []
    check("normalize: paths=[] → дефолты",
          db_profiles.normalize(broken) == db_profiles.DEFAULT_PROFILES)
    broken = copy.deepcopy(db_profiles.DEFAULT_PROFILES)
    del broken["autoclaw"]["validated_with"]
    check("normalize: нет validated_with → дефолты",
          db_profiles.normalize(broken) == db_profiles.DEFAULT_PROFILES)

    # --- р67: формат v3 — полный список файлов, пути относительно
    # главного, проверка _version ---
    zc3 = db_profiles.DEFAULT_PROFILES["zcode"]
    ac3 = db_profiles.DEFAULT_PROFILES["autoclaw"]
    check("р67: заводские комплекты — AC 3 файла, ZC 6",
          len(ac3["files"]) == 3 and len(zc3["files"]) == 6
          and set(ac3["files"]) == {"runtime.sqlite",
                                    "runtime.sqlite-wal",
                                    "runtime.sqlite-shm"}
          and set(zc3["files"]) == {
              "db.sqlite", "db.sqlite-wal", "db.sqlite-shm",
              "tasks-index.sqlite", "tasks-index.sqlite-wal",
              "tasks-index.sqlite-shm"},
          str(sorted(zc3["files"])))
    check("р67: _version = 3 в заводском; is_valid требует её",
          db_profiles.DEFAULT_PROFILES.get("_version") == 3
          and db_profiles.is_valid(db_profiles.DEFAULT_PROFILES))
    no_ver = copy.deepcopy(db_profiles.DEFAULT_PROFILES)
    no_ver.pop("_version")
    check("р67: без _version → битый (дефолты)",
          db_profiles.is_valid(no_ver) is False
          and db_profiles.normalize(no_ver) == db_profiles.DEFAULT_PROFILES)
    old_ver = copy.deepcopy(db_profiles.DEFAULT_PROFILES)
    old_ver["_version"] = 2
    check("р67: _version 2 → битый",
          db_profiles.is_valid(old_ver) is False)
    broken = copy.deepcopy(db_profiles.DEFAULT_PROFILES)
    del broken["zcode"]["files"]["db.sqlite-shm"]
    check("р67: неполный комплект (5 файлов) → дефолты",
          db_profiles.normalize(broken) == db_profiles.DEFAULT_PROFILES)
    broken = copy.deepcopy(db_profiles.DEFAULT_PROFILES)
    del broken["zcode"]["second_file"]
    check("р67: zcode без second_file → дефолты",
          db_profiles.normalize(broken) == db_profiles.DEFAULT_PROFILES)
    broken = copy.deepcopy(db_profiles.DEFAULT_PROFILES)
    broken["zcode"]["main_file"] = "other.sqlite"
    check("р67: main_file != стандартного локального имени → дефолты",
          db_profiles.normalize(broken) == db_profiles.DEFAULT_PROFILES)
    check("р67: main_file_of / second_file_of / files_of",
          db_profiles.main_file_of("zcode") == "db.sqlite"
          and db_profiles.main_file_of("autoclaw") == "runtime.sqlite"
          and db_profiles.second_file_of("zcode") == "tasks-index.sqlite"
          and db_profiles.second_file_of("autoclaw") is None
          and db_profiles.files_of("autoclaw")["runtime.sqlite-wal"] == ".")
    check("р67: companion_path — относительно главного (v2-раскладка)",
          db_profiles.companion_path(
              "zcode", Path("C:/u/.zcode/cli/db/db.sqlite"),
              "tasks-index.sqlite").as_posix()
          == "C:/u/.zcode/cli/db/../../v2/tasks-index.sqlite",
          db_profiles.companion_path(
              "zcode", Path("C:/u/.zcode/cli/db/db.sqlite"),
              "tasks-index.sqlite").as_posix())
    check("р67: companion_path wal — рядом с главным",
          db_profiles.companion_path(
              "autoclaw", Path("C:/x/runtime.sqlite"),
              "runtime.sqlite-wal") == Path("C:/x/runtime.sqlite-wal"))

    # %APPDATA% НЕ читается никогда — даже если там лежит конфиг
    (empty_appdata / "ExportChat.cfg").write_text(
        json.dumps({"_version": 3, "lang": "en", "tool_limit": 777}),
        encoding="utf-8-sig")
    os.remove(config.config_path())
    check("конфиг из %APPDATA% не подхватывается (портативность, раунд 13)",
          config.load() == copy.deepcopy(config.DEFAULTS))
    shutil.rmtree(empty_appdata, ignore_errors=True)
    empty_appdata.mkdir(parents=True, exist_ok=True)
    check("папка вывода по умолчанию (исходники) — корень репо (раунд 13)",
          config.default_output_dir() == ROOT, str(config.default_output_dir()))

    config.config_path().write_text("{ это не json", encoding="utf-8")
    check("повреждённый файл → дефолты",
          config.load() == copy.deepcopy(config.DEFAULTS))

    # мутации загруженного словаря не портят ни DEFAULTS, ни следующий load
    values = config.load()
    values["lang"] = "en"
    values["options"]["md"]["bom"] = False
    fresh = config.load()
    check("DEFAULTS не мутируются: lang", fresh["lang"] == "ru")
    check("DEFAULTS не мутируются: options",
          fresh["options"]["md"]["bom"] is True)
    check("DEFAULTS не мутируются на месте",
          config.DEFAULTS["lang"] == "ru")

    if real_appdata is None:
        os.environ.pop("APPDATA", None)
    else:
        os.environ["APPDATA"] = real_appdata


def test_db_profiles(tmp_base: Path, real_appdata: str | None) -> None:
    print("db_profiles (db_profiles.cfg — источник правды)")
    check("normalize(None) → дефолты",
          db_profiles.normalize(None) == db_profiles.DEFAULT_PROFILES)
    check("normalize(мусор) → дефолты",
          db_profiles.normalize([1, 2]) == db_profiles.DEFAULT_PROFILES)

    # битые поля одного профиля → секция целиком из умолчаний (раунд 19)
    broken = copy.deepcopy(db_profiles.DEFAULT_PROFILES)
    broken["autoclaw"]["paths"] = []
    check("normalize: paths=[] → дефолты",
          db_profiles.normalize(broken) == db_profiles.DEFAULT_PROFILES)
    broken = copy.deepcopy(db_profiles.DEFAULT_PROFILES)
    del broken["autoclaw"]["validated_with"]
    check("normalize: нет validated_with → дефолты",
          db_profiles.normalize(broken) == db_profiles.DEFAULT_PROFILES)


    # --- жизненный цикл файла db_profiles.cfg (решение владельца р19) ---
    cfg_dir = tmp_base / "dbp"
    shutil.rmtree(cfg_dir, ignore_errors=True)
    os.environ["EXPORTCHAT_CONFIG_DIR"] = str(cfg_dir)

    # 1) файла нет → записать заводской + СООБЩИТЬ
    profiles, note = db_profiles.load()
    path = cfg_dir / "db_profiles.cfg"
    check("нет файла → заводской записан", path.is_file(), str(path))
    check("нет файла → сообщение dbp_missing", note == "dbp_missing", str(note))
    check("нет файла → профили по умолчанию",
          profiles == db_profiles.DEFAULT_PROFILES)
    check("заводской файл — UTF-8 с BOM",
          path.read_bytes()[:3] == b"\xef\xbb\xbf")
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    check("заводской файл — валидный JSON с подсказками человеку",
          db_profiles.is_valid(doc) and "_about" in doc and "_substitutions" in doc)

    # 2) валидный файл → читается как есть, программой не трогается
    before = path.read_bytes()
    custom = copy.deepcopy(db_profiles.DEFAULT_PROFILES)
    custom["autoclaw"]["paths"] = ["%APPDATA%/NewClaw/accounts/*/db.sqlite"]
    path.write_text(json.dumps(
        {"_version": 3, "_about": "мои пути", **custom},
        ensure_ascii=False, indent=2), encoding="utf-8-sig")
    profiles, note = db_profiles.load()
    check("валидный файл → без сообщения", note is None, str(note))
    check("валидный файл → СВОИ пути возвращены",
          profiles["autoclaw"]["paths"]
          == ["%APPDATA%/NewClaw/accounts/*/db.sqlite"])
    check("подсказки (_about) в данные не попадают", "_about" not in profiles)
    stamp = path.stat().st_mtime_ns
    db_profiles.load()
    check("повторный load не трогает валидный файл (mtime тот же)",
          path.stat().st_mtime_ns == stamp)

    # р83 (п.2): строки db_profiles.cfg длиннее 500 — обрезка + реестр
    config.LONG_STRING_FILES.clear()
    custom["zcode"]["validated_with"] = "V" * 600
    path.write_text(json.dumps(
        {"_version": 3, "_about": "мои пути", **custom},
        ensure_ascii=False, indent=2), encoding="utf-8-sig")
    profiles, note = db_profiles.load()
    check("р83: dbp validated_with обрезан до 500, файл в реестре",
          len(profiles["zcode"]["validated_with"]) == 500
          and profiles["zcode"]["validated_with"] == "V" * 500
          and config.LONG_STRING_FILES == ["db_profiles.cfg"],
          (len(profiles["zcode"]["validated_with"]),
           str(config.LONG_STRING_FILES)))
    custom["zcode"]["validated_with"] = "ZCode 3.17.2.9661"
    path.write_text(json.dumps(
        {"_version": 3, "_about": "мои пути", **custom},
        ensure_ascii=False, indent=2), encoding="utf-8-sig")

    # 3) битый файл → переименован в .err, записан заводской, СООБЩИТЬ
    path.write_text("{ это не json", encoding="utf-8")
    profiles, note = db_profiles.load()
    check("битый файл → сообщение dbp_corrupt", note == "dbp_corrupt", str(note))
    err = cfg_dir / "db_profiles.cfg.err"
    check("битый файл переименован в .err",
          err.is_file() and err.read_text(encoding="utf-8") == "{ это не json")
    check("битый файл → заводской записан заново",
          path.is_file() and db_profiles.is_valid(
              json.loads(path.read_text(encoding="utf-8-sig"))))

    # 4) валидный по JSON, но битый по смыслу → тоже .err + заводской;
    #    р67: и файл с НЕВЕРНОЙ версией формата — тоже
    bad = {"_version": 3, "autoclaw": {"main_file": ""},
           "zcode": "мусор"}
    path.write_text(json.dumps(bad), encoding="utf-8-sig")
    profiles, note = db_profiles.load()
    check("невалидная структура → dbp_corrupt", note == "dbp_corrupt", str(note))
    check("невалидная структура → заводской восстановлен",
          profiles == db_profiles.DEFAULT_PROFILES
          and db_profiles.is_valid(json.loads(path.read_text(encoding="utf-8-sig"))))
    path.write_text(json.dumps({"_version": 2, **custom},
                               ensure_ascii=False), encoding="utf-8-sig")
    profiles, note = db_profiles.load()
    check("р67: _version 2 в файле → dbp_corrupt + заводской",
          note == "dbp_corrupt"
          and profiles == db_profiles.DEFAULT_PROFILES)

    # 5) wildcard + свежесть по mtime во временной структуре
    fake_appdata = tmp_base / "fake_appdata"
    acc = fake_appdata / "AutoClaw-official" / "accounts" / "a1" / "runtime"
    acc2 = fake_appdata / "AutoClaw-official" / "accounts" / "a2" / "runtime"
    for d in (acc, acc2):
        d.mkdir(parents=True, exist_ok=True)
    (acc / "runtime.sqlite").write_bytes(b"old")
    time.sleep(0.02)
    (acc2 / "runtime.sqlite").write_bytes(b"new")
    os.environ["APPDATA"] = str(fake_appdata)
    try:
        found = db_profiles.find_db("autoclaw", profiles)
        check("find_db: wildcard находит свежую базу",
              found == acc2 / "runtime.sqlite", str(found))
        check("find_db: неизвестный режим → None",
              db_profiles.find_db("nope") is None)
        custom_fake = copy.deepcopy(db_profiles.DEFAULT_PROFILES)
        custom_fake["autoclaw"]["paths"] = ["%APPDATA%/Нету/нигде.sqlite"]
        check("find_db: своих путей нет → None",
              db_profiles.find_db("autoclaw", custom_fake) is None)
    finally:
        if real_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = real_appdata

    # точный путь без wildcard: есть → возвращается; нет → None (раунд 19)
    exact_dir = tmp_base / "exact"
    exact_dir.mkdir(parents=True, exist_ok=True)
    (exact_dir / "runtime.sqlite").write_bytes(b"x")
    exact = copy.deepcopy(db_profiles.DEFAULT_PROFILES)
    exact["autoclaw"]["paths"] = [str(exact_dir / "runtime.sqlite")]
    check("find_db: точный путь без wildcard находит",
          db_profiles.find_db("autoclaw", exact) == exact_dir / "runtime.sqlite")
    exact["autoclaw"]["paths"] = [str(exact_dir / "нет-такого.sqlite")]
    check("find_db: точный путь отсутствует → None",
          db_profiles.find_db("autoclaw", exact) is None)

    zc = db_profiles.find_db("zcode", db_profiles.DEFAULT_PROFILES)
    if zc is not None:
        check("find_db zcode: реальная база найдена по ~",
              zc.name == "db.sqlite", str(zc))
    else:
        print("      (ZCode база не найдена — проверка пропущена)")

def test_i18n(tmp_base: Path) -> None:
    print("i18n")
    keys = set(i18n.STRINGS["ru"])
    check("ключи ru=en", keys == set(i18n.STRINGS["en"]),
          f"разница: {keys ^ set(i18n.STRINGS['en'])}")
    check("ключи ru=zh", keys == set(i18n.STRINGS["zh"]),
          f"разница: {keys ^ set(i18n.STRINGS['zh'])}")
    check("словари непустые", len(keys) >= 40, f"ключей: {len(keys)}")

    i18n.set_lang("ru")
    check("tr ru", i18n.tr("refresh") == "Обновить SQL базу")
    i18n.set_lang("en")
    check("tr en", i18n.tr("refresh") == "Update SQL database")
    i18n.set_lang("zh")
    check("tr zh", i18n.tr("refresh") == "更新SQL数据库")

    i18n.set_lang("en")
    check("title_explain en", i18n.tr("title_explain") == "AutoClaw and ZCode chat export")
    check("подстановка batch", i18n.tr("status_batch", done=2, total=5) == "Exporting: 2 of 5…")
    i18n.set_lang("ru")
    check("row_bom одинаков", i18n.tr("row_bom") == "UTF-8 Byte Order Mark")
    check("dbp-сообщения есть на трёх языках (паритет — см. выше)",
          "db_profiles.cfg" in i18n.tr("dbp_missing")
          and "db_profiles.cfg.err" in i18n.tr("dbp_corrupt"))
    check("lang_corrupt есть на трёх языках (раунд 23)",
          all("lang_corrupt" in i18n.STRINGS[l] for l in i18n.LANGS))
    i18n.set_lang("несуществующий")
    check("неизвестный язык → ru", i18n.tr("refresh") == "Обновить SQL базу")
    i18n.set_lang("ru")

    # --- раунд 23: внешние языковые файлы ---
    print("i18n: внешние файлы lang_<язык>.cfg")
    for lang in i18n.LANGS:
        doc = json.loads(i18n.factory_text(lang))
        check(f"заводской lang_{lang}.cfg — точная копия STRINGS",
              doc == i18n.STRINGS[lang])
    i18n_dir = tmp_base / "i18n"
    shutil.rmtree(i18n_dir, ignore_errors=True)
    i18n_dir.mkdir(parents=True, exist_ok=True)
    os.environ["EXPORTCHAT_CONFIG_DIR"] = str(i18n_dir)

    note = i18n.set_lang("ru")
    check("нет внешнего файла → без предупреждения, внутренние строки",
          note is None and i18n.tr("refresh") == "Обновить SQL базу")

    (i18n_dir / "lang_ru.cfg").write_text(json.dumps(
        {"refresh": "Тест-обновить", "лишний_ключ": "х"}, ensure_ascii=False),
        encoding="utf-8-sig")
    note = i18n.set_lang("ru")
    check("внешний файл: перекрытие по ключу (раунд 23)",
          note is None and i18n.tr("refresh") == "Тест-обновить")
    check("внешний файл: недостающие ключи из внутренних",
          i18n.tr("search") == "Поиск чата:")

    (i18n_dir / "lang_ru.cfg").write_text("{ это не json", encoding="utf-8")
    note = i18n.set_lang("ru")
    check("битый файл → предупреждение с именем файла",
          note == "lang_ru.cfg", str(note))
    check("битый файл → внутренние строки",
          i18n.tr("refresh") == "Обновить SQL базу")

    (i18n_dir / "lang_ru.cfg").write_text(json.dumps(
        {"refresh": "Тест-обновить-2"}, ensure_ascii=False), encoding="utf-8-sig")
    i18n.set_lang("en")
    i18n.set_lang("ru")
    check("переключение языка перечитывает внешний файл (без перезапуска)",
          i18n.tr("refresh") == "Тест-обновить-2")

    (i18n_dir / "lang_en.cfg").write_text(
        "строка со скобкой {без закрытия", encoding="utf-8-sig")
    i18n.set_lang("en")
    check("битые скобки в правленом тексте не роняют tr (р23)",
          isinstance(i18n.tr("refresh", n=1), str))
    i18n.set_lang("ru")
    os.environ.pop("EXPORTCHAT_CONFIG_DIR", None)


def test_job_runner(tmp_base: Path) -> None:
    print("job_runner")
    # --- раунд 26: Tasks ZCode — маркер в строке пути, машина не важна ---
    import zcode_export as ze
    check("р26: Tasks (.zcode/workspace в пути) — без проекта",
          ze.project_subdir({"directory":
              "C:" + chr(92) + "Users" + chr(92) + "КтоТо" + chr(92)
              + ".zcode" + chr(92) + "workspace" + chr(92) + "draft-abc"}) == "")
    check("р26: обычный проект не задет новым правилом",
          ze.project_subdir({"directory":
              "C:" + chr(92) + "proj" + chr(92) + "my_project"}) == "my_project")
    # --- раунды 29/31/39: project_for — имена проектов из tasks-index ---
    bs = chr(92)
    info = {"missing": False,
            "root_order": [(os.path.normcase("c:" + bs + "proj" + bs + "alpha"),
                            "Корневой проект")]}
    check("р39: прямая связь session_project сильнее корней",
          ze.project_for({"id": "sess_d", "directory":
                          "c:" + bs + "proj" + bs + "alpha"},
                         {**info, "session_project": {"sess_d": "Прямой"}})
          == "Прямой")
    check("р31: rename-safe — имена резолвятся по ДИРЕКТОРИИ (не по tasks): "
          "сессии переименованного проекта получают актуальное имя",
          ze.project_for({"id": "sess_x", "directory":
                          "c:" + bs + "proj" + bs + "alpha"},
                         info) == "Корневой проект")
    check("р29: проект по корню директории (project_roots), включая подпапки",
          ze.project_for({"id": "sess_y",
                          "directory": "c:" + bs + "proj" + bs + "alpha" + bs + "sub"},
                         info) == "Корневой проект")
    check("р29: unmapped при живом индексе → пусто (имя не выдумываем)",
          ze.project_for({"id": "sess_z", "directory": "c:" + bs + "nowhere"},
                         info) == "")
    check("р29: Task при живом индексе → пусто",
          ze.project_for({"id": "sess_t", "directory":
                          "c:" + bs + "users" + bs + "x" + bs + ".zcode" + bs
                          + "workspace" + bs + "draft-1"}, info) == "")
    check("р29: индекс отсутствует → лист директории (старое поведение)",
          ze.project_for({"id": "s5", "directory": "c:" + bs + "proj" + bs + "alpha"},
                         {"missing": True}) == "alpha")
    check("р29: индекс отсутствует, Task → пусто",
          ze.project_for({"id": "s6", "directory":
                          "c:" + bs + "users" + bs + "x" + bs + ".zcode" + bs
                          + "workspace" + bs + "draft-1"}, {"missing": True}) == "")
    ac_db = find_ac_db()
    if ac_db is None:
        print("      (AutoClaw база не найдена — прогон на живой базе пропущен)")
        return

    check("adapter_for('autoclaw') — класс адаптера",
          type(adapter_for("autoclaw")).__name__ == "AutoClawAdapter")
    check("adapter_for('zcode') — класс адаптера",
          type(adapter_for("zcode")).__name__ == "ZCodeAdapter")
    opts = ExportOptions(fmt="md", lang="en")
    check("ExportOptions поля", opts.fmt == "md" and opts.lang == "en"
          and opts.tools is False and opts.bom is True)

    out_dir = tmp_base / "job_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    runner = jr.JobRunner()

    # --- список ---
    runner.submit({"kind": "list", "mode": "autoclaw", "db": str(ac_db)})
    check("busy после submit", runner.busy())
    events = drain_until(runner, lambda e: e[0] == "list")
    rows = next((e[1] for e in events if e[0] == "list"), None)
    check("list: строки получены", isinstance(rows, list) and len(rows) > 0)
    check("runner свободен после list", not runner.busy())

    # --- серия 1 чат × 1 формат ---
    chat_id = rows[0]["id"]
    options_md = {"md": {"tools": False, "narration": False, "tool_limit": 1000,
                         "all_files": False, "bom": True,
                         "lang": "ru"}}
    runner.submit({"kind": "batch", "mode": "autoclaw", "db": str(ac_db),
                   "items": [(chat_id, "md")], "out_dir": str(out_dir),
                   "options": options_md})
    events = drain_until(runner, lambda e: e[0] == "batch_done")
    done = next(e for e in events if e[0] == "batch_done")
    check("batch: ok=1, ошибок 0", done[1] == 1 and done[2] == [], str(done))
    item = next(e for e in events if e[0] == "item_done")
    check("batch: файл создан (AC-*.md)",
          Path(item[3]["path"]).is_file()
          and Path(item[3]["path"]).name.startswith("AC-"))
    if rows[0].get("project"):
        check("batch: файл в субпапке проекта (р25: workspace)",
              Path(item[3]["path"]).parent.name == rows[0]["project"],
              str(Path(item[3]["path"]).parent))
    progress = [e for e in events if e[0] == "progress"]
    check("batch: события прогресса были", len(progress) >= 1)

    # --- серия с ошибкой: неудачный элемент не роняет задание ---
    runner.submit({"kind": "batch", "mode": "autoclaw", "db": str(ac_db),
                   "items": [("zzz-нет-такого", "md"), (chat_id, "md")],
                   "out_dir": str(out_dir), "options": options_md})
    events = drain_until(runner, lambda e: e[0] == "batch_done")
    done = next(e for e in events if e[0] == "batch_done")
    check("batch: ошибка элемента учтена, серия дожила до конца",
          done[1] == 1 and len(done[2]) == 1
          and done[2][0][0] == "zzz-нет-такого", str(done))

    # --- single по ВЫБРАННЫМ чатам (раунд 20) ---
    runner.submit({"kind": "single", "mode": "autoclaw", "db": str(ac_db),
                   "formats": ["md"], "out_dir": str(out_dir),
                   "chat_ids": [chat_id], "options": options_md})
    events = drain_until(runner, lambda e: e[0] == "batch_done")
    done = next(e for e in events if e[0] == "batch_done")
    check("single/chat_ids: ok=1, ошибок 0", done[1] == 1 and done[2] == [],
          str(done))
    sitem = next(e for e in events if e[0] == "item_done")
    spath = Path(sitem[3]["path"])
    check("single/chat_ids: файл AC-ALL-*.md", spath.name.startswith("AC-ALL-"),
          spath.name)
    text = spath.read_text(encoding="utf-8-sig")
    # подсчёт якорем строки-метки: контент реальных чатов может содержать
    # те же фразы (это же наши чаты) — наивный count ненадёжен; метка может
    # иметь префикс проекта «проект\» (раунд 25)
    check("single/chat_ids: 1 диалог внутри + заголовок «Выбранные» (р20/25)",
          len(re.findall(r"^Новый диалог (?:[^\\\r\n]+\\)?AC-.*\.md$",
                         text, re.M)) == 1
          and "# Выбранные диалоги AutoClaw (1)" in text)

    # все chat_ids мимо → понятная ошибка в элементе, задание завершено
    # (ошибка приписывается элементу «__single__», не id чата)
    runner.submit({"kind": "single", "mode": "autoclaw", "db": str(ac_db),
                   "formats": ["md"], "out_dir": str(out_dir),
                   "chat_ids": ["zzz-нет-такого"], "options": options_md})
    events = drain_until(runner, lambda e: e[0] == "batch_done")
    done = next(e for e in events if e[0] == "batch_done")
    check("single/chat_ids: id не найден → ошибка элемента",
          done[1] == 0 and len(done[2]) == 1
          and done[2][0][0] == "__single__"
          and "нет ни одного диалога" in done[2][0][2], str(done))

    # --- открытие несуществующей базы ---
    runner.submit({"kind": "list", "mode": "autoclaw",
                   "db": str(tmp_base / "no-such-db.sqlite")})
    events = drain_until(runner, lambda e: e[0] == "list_error")
    err = next(e for e in events if e[0] == "list_error")
    check("list_error: понятное сообщение", "не найден" in err[1], err[1])

    check("runner свободен в конце", not runner.busy())

    # --- р65: безопасный импорт мастер-базы (tmp → проверка → бэкапы) ---
    # ВАЖНО: блок работает ТОЛЬКО во временном окружении конфигов —
    # иначе config.data_dir() укажет на реальные папки проекта
    print("р65: безопасный импорт (tmp/бэкапы/minimal)")
    from job_runner import _rotate_backup  # noqa: E402
    imp = tmp_base / "imp65"
    imp.mkdir(exist_ok=True)
    os.environ["EXPORTCHAT_CONFIG_DIR"] = str(tmp_base)
    local_zc = config.local_db_path("zcode")

    def make_db(path: Path, table: str, marker: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(path)
        try:
            c.execute(f"drop table if exists {table}")
            c.execute(f"create table {table} (x text)")
            c.execute(f"insert into {table} values ('{marker}')")
            c.commit()
        finally:
            c.close()

    def marker_of(path: Path, table: str) -> str:
        c = sqlite3.connect(path)
        try:
            return c.execute(f"select x from {table}").fetchone()[0]
        finally:
            c.close()

    # локальная копия уже есть (маркер LOCAL-1); мастер — мусор
    make_db(local_zc, "session", "LOCAL-1")
    bad_text = imp / "db.sqlite"
    bad_text.write_text("not a sqlite file at all", encoding="utf-8")
    try:
        jr.import_master("zcode", bad_text)
        ok65 = False
    except jr.AdapterError:
        ok65 = True
    check("р65: мусор-мастер → AdapterError, локальная база ЦЕЛА",
          ok65 and marker_of(local_zc, "session") == "LOCAL-1",
          "локальная копия потеряна")
    check("р65: tmp после мусора удалён",
          not local_zc.with_suffix(".tmp").exists())

    # мастер = tasks-index (валидный sqlite БЕЗ session) — случай владельца
    make_db(imp / "tasks-index.sqlite", "tasks", "IDX")
    try:
        jr.import_master("zcode", imp / "tasks-index.sqlite")
        ok65b = False
    except jr.AdapterError as exc:
        ok65b = "нет таблиц диалогов" in str(exc)
    check("р65: tasks-index как мастер → ошибка, локальная ЦЕЛА",
          ok65b and marker_of(local_zc, "session") == "LOCAL-1")

    # валидный мастер без индекса рядом → minimal=True; локальная → .bak1
    make_db(imp / "noidx" / "good.sqlite", "session", "GOOD-1")
    # р67: путь 2-й базы задаётся ОТНОСИТЕЛЬНО главного (files),
    # НЕ абсолютным index_paths (формат v2 упразднён)
    profiles_none = {"zcode": dict(
        db_profiles.DEFAULT_PROFILES["zcode"],
        files=dict(db_profiles.DEFAULT_PROFILES["zcode"]["files"],
                   **{"tasks-index.sqlite": "no-v2",
                      "tasks-index.sqlite-wal": "no-v2",
                      "tasks-index.sqlite-shm": "no-v2"}))}
    dst65, minimal = jr.import_master(
        "zcode", imp / "noidx" / "good.sqlite", profiles_none)
    bak1 = dst65.with_name(dst65.name + ".bak1")
    check("р65: валидный импорт без индекса → minimal=True",
          minimal is True and dst65 == local_zc)
    check("р65: прежняя база стала .bak1 (содержимое живо)",
          bak1.is_file() and marker_of(bak1, "session") == "LOCAL-1"
          and marker_of(dst65, "session") == "GOOD-1")

    # повторные импорты: bak2, bak3, при 4-м bak1 исчезает (лимит 3)
    for i, marker in enumerate(("GOOD-2", "GOOD-3", "GOOD-4"), start=2):
        make_db(imp / "noidx" / f"good{i}.sqlite", "session", marker)
        jr.import_master("zcode", imp / "noidx" / f"good{i}.sqlite",
                         profiles_none)
    names65 = sorted(p.name for p in config.data_dir("zcode").iterdir())
    check("р65: ротация — ровно 3 бэкапа (bak1 свежий, bak4 нет)",
          f"{config.DATA_FILE['zcode']}.bak1" in names65
          and f"{config.DATA_FILE['zcode']}.bak3" in names65
          and f"{config.DATA_FILE['zcode']}.bak4" not in names65
          and marker_of(dst65, "session") == "GOOD-4"
          and marker_of(dst65.with_name(dst65.name + ".bak1"), "session")
          == "GOOD-3",
          str(names65))

    # комплект «рядом» (db + tasks-index в одной папке) — rel "."
    # в files конфига (v3: путь однозначен, эвристик нет)
    idx_src = imp / "db" / "db.sqlite"
    idx_src.parent.mkdir(exist_ok=True)
    make_db(idx_src, "session", "GOOD-5")
    make_db(imp / "db" / "tasks-index.sqlite", "tasks", "IDX-NEW")
    profiles_beside = {"zcode": dict(
        db_profiles.DEFAULT_PROFILES["zcode"],
        files=dict(db_profiles.DEFAULT_PROFILES["zcode"]["files"],
                   **{"tasks-index.sqlite": ".",
                      "tasks-index.sqlite-wal": ".",
                      "tasks-index.sqlite-shm": "."}))}
    dst65b, minimal_b = jr.import_master("zcode", idx_src,
                                         profiles_beside)
    check("р65: tasks-index рядом с мастером → minimal=False",
          minimal_b is False
          and marker_of(config.local_index_path(), "tasks") == "IDX-NEW")
    # первый импорт индекса бэкапа не создаёт (старого не было);
    # повторный — создаёт .bak1 с прежним содержимым
    idx_bak1 = config.local_index_path().with_name(
        config.local_index_path().name + ".bak1")
    check("р65: первый импорт индекса — без .bak1",
          not idx_bak1.exists())
    jr.import_master("zcode", idx_src, profiles_beside)
    check("р65: повторный импорт — у индекса свой .bak1 (IDX-NEW)",
          idx_bak1.is_file()
          and marker_of(idx_bak1, "tasks") == "IDX-NEW")

    # р67: 2-я база по относительному пути из конфига: мастер в p6/db,
    # индекс — в p6/v2 (rel "../v2" от папки мастера)
    v2dir = imp / "p6" / "v2"
    v2dir.mkdir(parents=True, exist_ok=True)
    make_db(v2dir / "tasks-index.sqlite", "tasks", "IDX-V2")
    make_db(imp / "p6" / "db" / "good6.sqlite", "session", "GOOD-6")
    profiles65 = {"zcode": dict(
        db_profiles.DEFAULT_PROFILES["zcode"],
        files=dict(db_profiles.DEFAULT_PROFILES["zcode"]["files"],
                   **{"tasks-index.sqlite": "../v2",
                      "tasks-index.sqlite-wal": "../v2",
                      "tasks-index.sqlite-shm": "../v2"}))}
    dst65c, minimal_c = jr.import_master(
        "zcode", imp / "p6" / "db" / "good6.sqlite", profiles65)
    check("р67: 2-я база по относительному пути конфига → найдена",
          minimal_c is False
          and marker_of(config.local_index_path(), "tasks") == "IDX-V2")

    # битый индекс (не sqlite) рядом → не блокирует: minimal=True
    make_db(imp / "p7" / "good7.sqlite", "session", "GOOD-7")
    bad_idx = imp / "v2bad"
    bad_idx.mkdir(exist_ok=True)
    (bad_idx / "tasks-index.sqlite").write_text("broken", encoding="utf-8")
    profiles_bad = {"zcode": dict(
        db_profiles.DEFAULT_PROFILES["zcode"],
        files=dict(db_profiles.DEFAULT_PROFILES["zcode"]["files"],
                   **{"tasks-index.sqlite": str(bad_idx),
                      "tasks-index.sqlite-wal": str(bad_idx),
                      "tasks-index.sqlite-shm": str(bad_idx)}))}
    dst65d, minimal_d = jr.import_master(
        "zcode", imp / "p7" / "good7.sqlite", profiles_bad)
    check("р65: битый индекс → импорт прошёл, minimal=True",
          minimal_d is True and marker_of(dst65d, "session") == "GOOD-7")

    # _rotate_backup напрямую: файла нет — молча
    _rotate_backup(config.data_dir("zcode") / "no-such.sqlite")
    check("р65: _rotate_backup без файла — без ошибок", True)

    # --- р66: бэкапится ВСЁ семейство (-wal/-shm), не только база ---
    print("р66: бэкап семейства (-wal/-shm)")
    d66 = config.data_dir("zcode")
    for suffix in ("-wal", "-shm"):
        (d66 / (config.DATA_FILE["zcode"] + suffix)).write_bytes(
            b"side-" + suffix.encode())
    (d66 / (config.INDEX_FILE + "-wal")).write_bytes(b"idx-wal")
    make_db(imp / "p66" / "db.sqlite", "session", "S66")
    make_db(imp / "p66" / "tasks-index.sqlite", "tasks", "I66")
    dst66, minimal66 = jr.import_master("zcode", imp / "p66" / "db.sqlite",
                                        profiles_beside)
    check("р66: db.sqlite-wal/-shm ушли в свои .bak1 (рабочих нет)",
          (d66 / (config.DATA_FILE["zcode"] + "-wal.bak1")).is_file()
          and (d66 / (config.DATA_FILE["zcode"] + "-shm.bak1")).is_file()
          and not (d66 / (config.DATA_FILE["zcode"] + "-wal")).exists()
          and not (d66 / (config.DATA_FILE["zcode"] + "-shm")).exists())
    check("р66: tasks-index-wal тоже в .bak1; рабочий wal удалён",
          (d66 / (config.INDEX_FILE + "-wal.bak1")).is_file()
          and not (d66 / (config.INDEX_FILE + "-wal")).exists())
    check("р66: новый импорт жив (маркеры)",
          marker_of(dst66, "session") == "S66"
          and marker_of(config.local_index_path(), "tasks") == "I66")
    os.environ.pop("EXPORTCHAT_CONFIG_DIR", None)


def main() -> int:
    tmp_base = Path(tempfile.mkdtemp(prefix="z5_units_"))
    real_appdata = os.environ.get("APPDATA")
    try:
        test_config(tmp_base, real_appdata)
        test_db_profiles(tmp_base, real_appdata)
        test_i18n(tmp_base)
        test_job_runner(tmp_base)
    finally:
        os.environ.pop("EXPORTCHAT_CONFIG_DIR", None)
        if real_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = real_appdata
        shutil.rmtree(tmp_base, ignore_errors=True)

    # --- р50: авторы (synthetic + модель из model_usage); сортировка ---
    print("р50: авторы (synthetic / model_usage) / _iso_ts")
    import zcode_export as ze
    import export_chat as ec
    from app import _iso_ts
    check("р50: харнесс = «ZCode» в трёх языках, нет «Система»",
          ze.LABELS["ru"]["system"] == "ZCode"
          and ze.LABELS["en"]["system"] == "ZCode"
          and ze.LABELS["zh"]["system"] == "ZCode"
          and ze.LABELS["ru"]["llm_unknown"] == "LLM")
    check("р64 (E5a): model_label — workflow-агент = «· Субагент»",
          ze.model_label("GLM-5.3", "max", "zcode-workflow")
          == "GLM-5.3 Max · Субагент",
          ze.model_label("GLM-5.3", "max", "zcode-workflow"))
    check("р50: model_label — GUI-стиль, субагент, фолбэк LLM",
          ze.model_label("GLM-5.3-Flash", "max", "zcode-agent")
          == "GLM-5.3-Flash Max"
          and ze.model_label("GLM-5.3-Flash", "high", "zcode-Explore")
          == "GLM-5.3-Flash High · Explore"
          and ze.model_label(None, None, None) == "LLM")
    check("р50: ac_model_label — Auto/Auto-Fast/GLM/фолбэк",
          ec.ac_model_label({"model": "zai_auto"}) == "Auto"
          and ec.ac_model_label({"model": "zai_auto-fast"}) == "Auto-Fast"
          and ec.ac_model_label({"model": "zai_glm-5.3-flash"})
          == "GLM-5.3-Flash"
          and ec.ac_model_label({"model": "zaicoding_glm-5.3"}) == "GLM-5.3"
          and ec.ac_model_label(None) == "LLM"
          and ec.ac_model_label("") == "LLM")
    # минибаза: synthetic=true → ход-харнесс «ZCode»; человек → «Вы»;
    # ответ — модель из model_usage; без строки → «LLM»
    mini = TMP_UNIT / "mini50.sqlite" if (TMP_UNIT := Path(tempfile.mkdtemp())) else None
    mc = sqlite3.connect(mini)
    mc.executescript("""
        create table session (id text primary key, title text, directory text,
            time_created int, time_updated int, time_deleted int,
            time_archived int, task_type text, parent_id text,
            version text);
        create table message (id text primary key, session_id text,
            sequence int, data text, time_created int);
        create table part (message_id text, sequence int, data text);
        create table session_purge (session_id text primary key, state text);
        create table model_usage (id text primary key, session_id text,
            input_tokens int, started_at int, assistant_message_id text,
            model_id text, variant text, agent text, duration_ms int);
    """)
    mc.execute("insert into session values ('s1','минибаза','C:/x',1,2,"
               "null,null,'interactive',null,'9.9.9-rc')")
    mc.executemany("insert into message values (?,?,?,?,?)", [
        ("h1", "s1", 1, json.dumps({"role": "user"}), 1),
        ("a1", "s1", 2, json.dumps({"role": "assistant"}), 2),
        ("sys1", "s1", 3, json.dumps({"role": "user", "synthetic": True,
                                      "visibility": "model-only"}), 3),
        ("hm1", "s1", 4, json.dumps({"role": "user",
                                     "visibility": "model-only"}), 4),
        ("a2", "s1", 5, json.dumps({"role": "assistant"}), 5),
    ])
    mc.executemany("insert into part values (?,?,?)", [
        ("h1", 1, json.dumps({"type": "text", "text": "ЧЕЛОВЕК-МАРК"})),
        ("a1", 1, json.dumps({"type": "text", "text": "ОТВЕТ-МАРК"})),
        ("sys1", 1, json.dumps({"type": "text", "text":
            "You are powered by the model named x."})),
        ("hm1", 1, json.dumps({"type": "text", "text":
            "ЧЕЛОВЕК-MODEL-ONLY-МАРК"})),
        ("a2", 1, json.dumps({"type": "text", "text": "ОТВЕТ-2-МАРК"})),
    ])
    mc.executemany("insert into model_usage values (?,?,?,?,?,?,?,?,?)", [
        # только a1 задокументирован — a2 остаётся без модели → «LLM»
        ("mu1", "s1", 5000, 20, "a1", "GLM-5.3-Flash", "max", "zcode-agent", 2130),
    ])
    mc.commit()
    zc = adapter_for("zcode")
    zcon = zc.open(mini)
    turns = ze.build_turns(zcon, "s1", ctx_mode=True)
    check("р50: три user-хода в ctx-режиме", len(turns) == 3, str(len(turns)))
    check("р50: человек — system=False; synthetic=true — system=True",
          turns[0]["system"] is False and turns[1]["system"] is True
          and turns[2]["system"] is False)
    check("р50: модель ответа привязана к assistant-сообщению",
          turns[0].get("model") == "GLM-5.3-Flash Max"
          and turns[2].get("model") == "LLM",
          f"{turns[0].get('model')!r} / {turns[2].get('model')!r}")
    ctx_opt = ExportOptions(fmt="txt", lang="ru", context_view=True)
    res = zc.export_chat(zcon, "s1", Path(tempfile.mkdtemp()), ctx_opt)
    body = Path(res["path"]).read_text(encoding="utf-8-sig")
    check("р50: подписи ZCODE (харнесс)/ВЫ×2/GLM-5.3-Flash Max/LLM в txt",
          body.count("ZCODE") == 1 and body.count("ВЫ") == 2
          and "GLM-5.3-Flash Max" in body and "LLM" in body
          and "СИСТЕМА" not in body
          and "ЧЕЛОВЕК-MODEL-ONLY-МАРК" in body, body[:400])
    # р51: шапка — харнесс с версией из session.version;
    # р81 (п.1): подпись «Харнесс-ядро» (версия встроенного ядра, не приложения)
    check("р51/р81: шапка «Харнесс-ядро: ZCode 9.9.9-rc» в txt",
          "Харнесс-ядро: ZCode 9.9.9-rc" in body, body[:200])
    check("р81 (п.2): «Сообщений: N / M (вопросы/ответы)»",
          "(вопросы/ответы)" in body, body[:200])
    zc.close(zcon)
    shutil.rmtree(mini, ignore_errors=True)
    check("р49: _iso_ts парсит ISO с Z и возвращает возрастающую величину",
          _iso_ts("2026-01-01T10:00:00Z") < _iso_ts("2026-01-05T10:00:00Z"))
    check("р49: _iso_ts пустое/битое → 0.0",
          _iso_ts("") == 0.0 and _iso_ts("мусор") == 0.0 and _iso_ts(None) == 0.0)

    # --- р62: форматтеры времени/токенов, fence txt, подчёркивания ---
    print("р62: форматтеры (я2/я5), fence txt (я9), underline (я3)")
    check("р62 (я5): fmt_duration — 0.8 сек / 15 сек / 1 мин / "
          "2 мин 12 сек / 1 час 5 мин",
          ec.fmt_duration(0.84) == "0.8 сек"
          and ec.fmt_duration(14.6) == "15 сек"
          and ec.fmt_duration(60) == "1 мин"
          and ec.fmt_duration(132) == "2 мин 12 сек"
          and ec.fmt_duration(3900) == "1 час 5 мин"
          and ec.fmt_duration(None) == ""
          and ze.fmt_duration(3900) == "1 час 5 мин",
          str([ec.fmt_duration(x) for x in (0.84, 14.6, 60, 132, 3900)]))
    old = ec.LANG
    ec.LANG = "en"
    check("р62 (я5): en — sec/min/hour", ec.fmt_duration(14.6) == "15 sec")
    ec.LANG = old
    check("р62 (я2): fmt_num/fmt_window/fmt_compact_k/fmt_pct",
          ec.fmt_num(16161) == "16 161"
          and ec.fmt_window(1048576) == "1М"
          and ec.fmt_window(524288) == "512К"
          and ec.fmt_compact_k(811622) == "812 К"
          and ec.fmt_compact_k(635494) == "635 К"
          and ec.fmt_pct(16161, 1048576) == "1.5%"
          and ec.fmt_pct(811622, 1048576) == "77%",
          str((ec.fmt_num(16161), ec.fmt_window(1048576),
               ec.fmt_compact_k(811622), ec.fmt_pct(16161, 1048576))))
    check("р62 (я2): n_tokens — падежи 1/3/5/7 токен…",
          ec.n_tokens(1) == "1 токен" and ec.n_tokens(32362) == "32 362 токена"
          and ec.n_tokens(255507) == "255 507 токенов",
          str((ec.n_tokens(1), ec.n_tokens(32362), ec.n_tokens(255507))))
    lines62 = ec.token_header_lines({"context": 16161, "window": 1048576,
                                     "compact": 811622, "total_spent": 32362})
    check("р62 (я2): token_header_lines — 3 строки формата владельца",
          lines62 == ["Контекст чата: 16 161 из 1М (1.5%)",
                      "Автосжатие при: 812 К (77%)",
                      "Всего израсходовано: 32 362 токена"],
          str(lines62))
    check("р62 (я2): token_header_lines — пусто/нет данных",
          ec.token_header_lines(None) == []
          and ec.token_header_lines({"context": None}) == []
          # р81 (п.3): «токенов» всегда; % — только по карте моделей
          and ze.token_header_lines({"context": 5}) ==
          ["Контекст чата: 5 токенов"]
          and ze.token_header_lines({"context": 28019,
                                     "model": "GLM-5.3"}) ==
          ["Контекст чата: 28 019 токенов (2.8%/1М)"]
          and ze.token_header_lines({"context": 28019,
                                     "model": "GLM-4"}) ==
          ["Контекст чата: 28 019 токенов"],
          str(ze.token_header_lines({"context": 28019,
                                     "model": "GLM-5.3"})))
    fence_in = ("до\n\n```python\ndef f():\n    # комм\n"
                "    return '```x'\n```\n\nпосле")
    out62 = ec.md_to_text(fence_in)
    check("р62 (я9): md_to_text — «python { … }», код нетронут",
          out62 == "до\n\npython\n{\ndef f():\n    # комм\n"
          "    return '```x'\n}\n\nпосле"
          and ze.md_to_text(fence_in) == out62,
          out62)
    check("р62 (я9): md_to_text — fence без языка",
          ec.md_to_text("```\nкод\n```") == "{\nкод\n}",
          ec.md_to_text("```\nкод\n```"))
    check("р62 (я3): underline — длина ровно в строку",
          ec.underline("[1] ВЫ — 20.11.2026 13:51")
          == "-" * len("[1] ВЫ — 20.11.2026 13:51") + "\n")
    check("р63 (я1/я2): exporter_header — пустая строка + txt-рамка",
          ec.exporter_header("md", "1.58 RC")
          == "\nZ.ai Chats Exporter by Vadim R.M. ver. 1.58 RC — "
             "[https://www.vmgames.com](https://www.vmgames.com)\n"
          and ec.exporter_header("txt", "1.58 RC")
          == "\n" + "-" * 71 + "\nZ.ai Chats Exporter by Vadim R.M."
             " ver. 1.58 RC  https://www.vmgames.com\n" + "-" * 71 + "\n"
          and ec.exporter_header("md", "") == ""
          and ze.exporter_header("txt", "1.58 RC") ==
          ec.exporter_header("txt", "1.58 RC"),
          repr(ec.exporter_header("txt", "1.58 RC")))
    check("р63 (я2): exporter_footer txt — рамка из черт",
          ec.exporter_footer("txt", "1.58 RC")
          == ec.exporter_header("txt", "1.58 RC")
          and ec.exporter_footer("md", "1.58 RC").endswith(
              "[https://www.vmgames.com](https://www.vmgames.com)\n"),
          repr(ec.exporter_footer("txt", "1.58 RC")))
    # р63 (я7): сценарии повреждения конфига (владелец: «сам проверь»)
    base_cfg = copy.deepcopy(config.DEFAULTS)
    check("р63 (я7): validate — валидный конфиг = True",
          config.validate(base_cfg) is True)
    bad = copy.deepcopy(base_cfg)
    bad["_version"] = 5
    check("р63 (я7): _version 5 → повреждён", config.validate(bad) is False)
    bad = copy.deepcopy(base_cfg)
    del bad["options"]["md"]["narration"]
    check("р63 (я7): удалён ключ narration → повреждён",
          config.validate(bad) is False)
    bad = copy.deepcopy(base_cfg)
    bad["options"]["md"]["nar"] = False
    check("р63 (я7): «nar» вместо «narration» → повреждён",
          config.validate(bad) is False)
    bad = copy.deepcopy(base_cfg)
    bad["extra_key"] = 1
    check("р63 (я7): лишний ключ → повреждён", config.validate(bad) is False)
    bad = copy.deepcopy(base_cfg)
    bad["tool_limit"] = "1000"
    check("р63 (я7): тип не тот (tool_limit строкой) → повреждён",
          config.validate(bad) is False)
    bad = copy.deepcopy(base_cfg)
    bad["single_file"] = "yes"
    check("р63 (я7): single_file строкой → повреждён",
          config.validate(bad) is False)
    check("р63 (я7): мусор (не словарь) → повреждён",
          config.validate([1, 2]) is False and config.validate("x") is False)

    print("-" * 60)
    print(f"Итого: PASS={PASS_COUNT}, FAIL={FAIL_COUNT}")
    for line in FAILURES:
        print(f"  провал: {line}")
    return 1 if FAIL_COUNT else 0


if __name__ == "__main__":
    sys.exit(main())
