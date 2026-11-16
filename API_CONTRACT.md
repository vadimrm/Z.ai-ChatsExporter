# -*- coding: utf-8 -*-
"""Смоук-тесты адаптера ZCode (backend/zcode_export.py, раунд 19).

Запуск из корня репозитория:  python frontend\\tests\\test_zcode_smoke.py

Адаптер вызывается напрямую (без subprocess — CLI больше нет).
Читает реальную базу ZCode (~/.zcode/cli/db/db.sqlite) ТОЛЬКО на чтение;
при блокировке адаптер сам читает временную копию. Все создаваемые файлы —
только в frontend/tests/_tmp/zcode_smoke.
"""
from __future__ import annotations

import glob
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from adapter import AdapterError, ExportOptions, adapter_for  # noqa: E402

TMP = Path(__file__).resolve().parent / "_tmp" / "zcode_smoke"

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


def main() -> int:
    db = Path.home() / ".zcode" / "cli" / "db" / "db.sqlite"
    print(f"База: {db}")
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)

    ad = adapter_for("zcode")

    # --- Z1: список диалогов ---
    print("Z1. list_chats")
    rows: list = []
    try:
        con = ad.open(db)
        rows = ad.list_chats(con)
        check("Z1 список непустой", isinstance(rows, list) and len(rows) > 0,
              f"len={len(rows)}")
    except AdapterError as exc:
        check("Z1 список непустой", False, exc.message)
    if rows:
        expected = {"id", "title", "directory", "created_at", "updated_at",
                    "created_local", "updated_local", "requests"}
        check("Z1 поля строки (включая directory)", expected <= set(rows[0]),
              f"нет: {expected - set(rows[0])}")
        check("Z1 нет сабагентских сессий (Я7)",
              all("Search for ZCode" not in (r.get("title") or "") for r in rows))
        check("Z1 кириллица без искажений (U+FFFD)",
              "\ufffd" not in "".join(r.get("title") or "" for r in rows[:5]))

    # --- Z1b: открытие несуществующего файла ---
    print("Z1b. open <нет такого файла>")
    try:
        ad.open(TMP / "нет-такой-базы.sqlite")
        check("Z1b AdapterError «файл не найден»", False, "исключения не было")
    except AdapterError as exc:
        check("Z1b AdapterError «файл не найден»", "не найден" in exc.message,
              exc.message)

    if not rows:
        print("База ZCode недоступна — дальнейшие тесты невозможны.")
        return finish()

    dialog_id = rows[0]["id"]

    # --- Z2: экспорт md по умолчанию (BOM) ---
    print("Z2. export_chat md")
    out_md = TMP / "one"
    res = ad.export_chat(con, dialog_id, out_md, ExportOptions(fmt="md"))
    path = Path(res["path"])
    check("Z2 {path, requests}", path.is_file() and res.get("requests", 0) >= 1,
          f"res={res}")
    check("Z2 файл не пуст", path.stat().st_size > 0)
    check("Z2 md с BOM", path.read_bytes()[:3] == b"\xef\xbb\xbf")
    if path.is_file():
        text = path.read_text(encoding="utf-8-sig")
        check("Z2 заголовок и роли", text.startswith("# ")
              and "## 1. Вы" in text and "### ZCode" in text)

    # --- Z3: txt + en + narration (чистота от markdown, Я8) ---
    print("Z3. export_chat txt /lang en /narration")
    out_txt = TMP / "one_en"
    ad.export_chat(con, dialog_id, out_txt,
                   ExportOptions(fmt="txt", lang="en", narration=True))
    files_txt = sorted(out_txt.rglob("ZC-*.txt"))
    check("Z3 файл txt создан (папка проекта)", len(files_txt) == 1,
          str([p.name for p in files_txt]))
    if files_txt:
        text = files_txt[0].read_text(encoding="utf-8-sig")
        check("Z3 подписи en", "Session" in text and "YOU" in text)
        check("Z3 txt без markdown-разметки (Я8)", "```" not in text)

    # --- Z4: tools в txt (ER-4) ---
    print("Z4. export_chat txt /tools")
    out_txt_t = TMP / "one_tools"
    ad.export_chat(con, dialog_id, out_txt_t,
                   ExportOptions(fmt="txt", tools=True))
    files_tt = sorted(out_txt_t.rglob("ZC-*.txt"))
    check("Z4 файл txt создан", len(files_tt) == 1)
    if files_tt:
        check("Z4 блок инструментов", "🔧" in files_tt[0].read_text(encoding="utf-8-sig"))

    # --- Z5: json без BOM, структура turns ---
    print("Z5. export_chat json /tools")
    out_json = TMP / "one_json"
    ad.export_chat(con, dialog_id, out_json,
                   ExportOptions(fmt="json", tools=True))
    files_json = sorted(out_json.rglob("ZC-*.json"))
    check("Z5 файл json создан", len(files_json) == 1)
    if files_json:
        check("Z5 json без BOM", files_json[0].read_bytes()[:3] != b"\xef\xbb\xbf")
        payload = json_loads(files_json[0])
        turn_keys = set(payload.get("turns", [{}])[0]) if payload.get("turns") else set()
        check("Z5 turns с tools/narration",
              {"request", "answers", "tools", "narration"} <= turn_keys,
              f"keys={sorted(turn_keys)}")
        any_tools = any(t["tools"] for t in payload.get("turns", []))
        check("Z5 инструменты попали в json (в этом чате)", any_tools)

    # --- Z6: bom=False — только выбранный формат без BOM ---
    print("Z6. bom=False")
    nb = TMP / "bomless"
    ad.export_chat(con, dialog_id, nb, ExportOptions(fmt="md", bom=False))
    files_nb = sorted(nb.rglob("ZC-*.md"))
    check("Z6 md без BOM", files_nb
          and files_nb[0].read_bytes()[:3] != b"\xef\xbb\xbf")

    # --- Z7: суффикс (1) при повторном экспорте ---
    print("Z7. повторный экспорт -> суффикс (1)")
    first = Path(ad.export_chat(con, dialog_id, TMP / "twice",
                                ExportOptions(fmt="md"))["path"])
    second = Path(ad.export_chat(con, dialog_id, TMP / "twice",
                                 ExportOptions(fmt="md"))["path"])
    check("Z7 имя с (1)", second.stem.endswith(" (1)"), second.name)
    check("Z7 исходный файл не перезаписан",
          first.read_bytes()[:3] == b"\xef\xbb\xbf")

    # --- Z8: несуществующий диалог -> AdapterError ---
    print("Z8. export_chat <несуществующий>")
    try:
        ad.export_chat(con, "zzz-net-takogo", TMP / "nope", ExportOptions())
        check("Z8 AdapterError с message", False, "исключения не было")
    except AdapterError as exc:
        check("Z8 AdapterError с message", bool(exc.message.strip()), exc.message)

    # --- Z9: чужая база (AutoClaw runtime.sqlite) -> понятная ошибка ---
    print("Z9. open <AutoClaw runtime.sqlite>")
    appdata = os.environ.get("APPDATA", "")
    ac_candidates = glob.glob(os.path.join(
        appdata, "AutoClaw*", "accounts", "*", "runtime", "runtime.sqlite"))
    if ac_candidates:
        try:
            ad.open(ac_candidates[0])
            check("Z9 AdapterError «не база ZCode»", False, "исключения не было")
        except AdapterError as exc:
            check("Z9 AdapterError «не база ZCode»",
                  "не база ZCode" in exc.message, exc.message)
    else:
        print("      (AutoClaw runtime.sqlite не найден — Z9 пропущен)")

    # --- Z10: папки проектов (Я6): файл в субпапке последнего компонента directory ---
    print("Z10. папка проекта (Я6)")
    with_dir = next((r for r in rows if r.get("directory")), None)
    if with_dir is not None:
        out_proj = TMP / "project"
        res_p = ad.export_chat(con, with_dir["id"], out_proj, ExportOptions(fmt="md"))
        ppath = Path(res_p["path"])
        expected_leaf = with_dir["directory"].replace("/", "\\").split("\\")[-1]
        check("Z10 файл в папке проекта",
              ppath.parent.name == expected_leaf,
              f"parent={ppath.parent.name}, ожидался={expected_leaf!r}")
    else:
        print("      (все диалоги без directory — Z10 пропущен)")

    # --- Z11: всё в один файл (ER-2) ---
    print("Z11. export_single_file md")
    single_dir = TMP / "single"
    res = ad.export_single_file(con, single_dir, ExportOptions(fmt="md"))
    spath = Path(res["path"])
    check("Z11 один файл ZC-ALL-*.md",
          spath.is_file() and spath.name.startswith("ZC-ALL-"), str(res))
    check("Z11 sessions >= 1", res.get("sessions", 0) >= 1, str(res))
    if spath.is_file():
        text = spath.read_text(encoding="utf-8-sig")
        check("Z11 несколько чатов внутри", text.count("## 1. Вы") >= 1)
        check("Z11 двойной разделитель --- (Я5)", "---\n---" in text)
        check("Z11 метка «Новый диалог» (Я5)",
              text.count("Новый диалог ") >= res.get("sessions", 10**9))

    ad.close(con)
    return finish()


def json_loads(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def finish() -> int:
    print("-" * 60)
    print(f"Итого: PASS={PASS_COUNT}, FAIL={FAIL_COUNT}")
    for line in FAILURES:
        print(f"  провал: {line}")
    return 1 if FAIL_COUNT else 0


if __name__ == "__main__":
    sys.exit(main())
