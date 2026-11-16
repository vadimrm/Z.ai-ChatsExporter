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
    check("roundtrip db_path_zcode",
          again["db_path_zcode"] == "C:\\z\\db.sqlite")
    check("roundtrip single_file (чекбокс, р20)",
          again["single_file"] is True)
    check("json BOM всегда False", again["options"]["json"]["bom"] is False)
    check("неизвестный ключ не сохранён", "чужой_ключ" not in again)
    check("версия конфига 3", again["_version"] == 3)

    # старый формат v1 не мигрирует (чистый лист, решение владельца р19):
    # неизвестные ключи молча игнорируются, известные читаются
    v1 = {"_version": 1, "lang": "en", "tool_limit": 4000,
          "format": "json", "tools": True, "no_bom": True}
    config.config_path().write_text(json.dumps(v1), encoding="utf-8-sig")
    old = config.load()
    check("старый v1: известные ключи читаются (lang/tool_limit)",
          old["lang"] == "en" and old["tool_limit"] == 4000)
    check("старый v1: неизвестные ключи → дефолты (без миграции)",
          old["export_formats"] == ["md", "txt"]
          and old["options"]["md"]["tools"] is False)

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
    broken["zcode"]["filename"] = ""
    check("normalize: пустое filename → дефолты",
          db_profiles.normalize(broken) == db_profiles.DEFAULT_PROFILES)
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
        {"_about": "мои пути", **custom}, ensure_ascii=False, indent=2),
        encoding="utf-8-sig")
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

    # 4) валидный по JSON, но битый по смыслу → тоже .err + заводской
    bad = {"autoclaw": {"filename": ""}, "zcode": "мусор"}
    path.write_text(json.dumps(bad), encoding="utf-8-sig")
    profiles, note = db_profiles.load()
    check("невалидная структура → dbp_corrupt", note == "dbp_corrupt", str(note))
    check("невалидная структура → заводской восстановлен",
          profiles == db_profiles.DEFAULT_PROFILES
          and db_profiles.is_valid(json.loads(path.read_text(encoding="utf-8-sig"))))

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


def test_i18n() -> None:
    print("i18n")
    keys = set(i18n.STRINGS["ru"])
    check("ключи ru=en", keys == set(i18n.STRINGS["en"]),
          f"разница: {keys ^ set(i18n.STRINGS['en'])}")
    check("ключи ru=zh", keys == set(i18n.STRINGS["zh"]),
          f"разница: {keys ^ set(i18n.STRINGS['zh'])}")
    check("словари непустые", len(keys) >= 40, f"ключей: {len(keys)}")

    i18n.set_lang("ru")
    check("tr ru", i18n.tr("refresh") == "Обновить чаты")
    i18n.set_lang("en")
    check("tr en", i18n.tr("refresh") == "Refresh chats")
    i18n.set_lang("zh")
    check("tr zh", i18n.tr("refresh") == "刷新对话")

    i18n.set_lang("en")
    check("title_explain en", i18n.tr("title_explain") == "AutoClaw and ZCode chat export")
    check("подстановка batch", i18n.tr("status_batch", done=2, total=5) == "Exporting: 2 of 5…")
    i18n.set_lang("ru")
    check("row_bom одинаков", i18n.tr("row_bom") == "UTF-8 Byte Order Mark")
    check("dbp-сообщения есть на трёх языках (паритет — см. выше)",
          "db_profiles.cfg" in i18n.tr("dbp_missing")
          and "db_profiles.cfg.err" in i18n.tr("dbp_corrupt"))
    i18n.set_lang("несуществующий")
    check("неизвестный язык → ru", i18n.tr("refresh") == "Обновить чаты")
    i18n.set_lang("ru")


def test_job_runner(tmp_base: Path) -> None:
    print("job_runner")
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
                         "all_files": False, "no_files": False, "bom": True,
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
    # те же фразы (это же наши чаты) — наивный count ненадёжен
    check("single/chat_ids: 1 диалог внутри + заголовок «Выбранные» (р20)",
          len(re.findall(r"^Новый диалог AC-.*\.md$", text, re.M)) == 1
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


def main() -> int:
    tmp_base = Path(tempfile.mkdtemp(prefix="z5_units_"))
    real_appdata = os.environ.get("APPDATA")
    try:
        test_config(tmp_base, real_appdata)
        test_db_profiles(tmp_base, real_appdata)
        test_i18n()
        test_job_runner(tmp_base)
    finally:
        os.environ.pop("EXPORTCHAT_CONFIG_DIR", None)
        if real_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = real_appdata
        shutil.rmtree(tmp_base, ignore_errors=True)
    print("-" * 60)
    print(f"Итого: PASS={PASS_COUNT}, FAIL={FAIL_COUNT}")
    for line in FAILURES:
        print(f"  провал: {line}")
    return 1 if FAIL_COUNT else 0


if __name__ == "__main__":
    sys.exit(main())
