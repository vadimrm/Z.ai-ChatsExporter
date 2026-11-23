# -*- coding: utf-8 -*-
"""Смоук-тесты адаптера AutoClaw (backend/export_chat.py, раунд 19).

Запуск из корня репозитория:  python frontend\\tests\\test_engine_smoke.py

Адаптер вызывается напрямую (без subprocess — CLI больше нет).
Все файлы, созданные тестами, лежат только в frontend/tests/_tmp.
База AutoClaw используется только на чтение (mode=ro).
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from adapter import AdapterError, ExportOptions, adapter_for  # noqa: E402

TMP = Path(__file__).resolve().parent / "_tmp"

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


def find_ac_db() -> Path | None:
    appdata = os.environ.get("APPDATA", "")
    cands = glob.glob(os.path.join(
        appdata, "AutoClaw*", "accounts", "*", "runtime", "runtime.sqlite"))
    return Path(max(cands, key=os.path.getmtime)) if cands else None


def main() -> int:
    db = find_ac_db()
    print(f"База: {db}")
    print(f"Временная папка: {TMP}")
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)

    ad = adapter_for("autoclaw")

    # --- T1: список диалогов ---
    print("T1. list_chats")
    rows: list = []
    try:
        con = ad.open(db)
        rows = ad.list_chats(con)
        check("T1 список непустой", isinstance(rows, list) and len(rows) > 0,
              f"len={len(rows)}")
    except AdapterError as exc:
        check("T1 список непустой", False, exc.message)
    if rows:
        expected = {"id", "title", "created_at", "updated_at",
                    "created_local", "updated_local", "requests",
                    "tokens"}  # р61: «Ток» у AutoClaw
        check("T1 поля первой строки", expected <= set(rows[0]),
              f"нет: {expected - set(rows[0])}")
        # р62 (я2): живая база — «Ток» = contextTokens последнего хода
        # (размер контекста; прежде totalTokens — расход за ход)
        check("T1e: «Ток» у AutoClaw (contextTokens, р62)",
              any(isinstance(r.get("tokens"), int) for r in rows),
              str([r.get("tokens") for r in rows[:5]]))
        check("T1 кириллица без искажений (U+FFFD)",
              "\ufffd" not in "".join(r.get("title") or "" for r in rows[:5]))
        check("T1b: default workspace — НЕ проект (р26)",
              all(r.get("project") != "默认项目" for r in rows))
        # р48: архивные чаты AutoClaw — скрыты, метка arch
        arch_rows = [r for r in rows if r.get("type") == "arch"]
        if arch_rows:
            check("T1c: archived_at — скрыт, метка arch (р48)",
                  all(r.get("hidden") is True for r in arch_rows),
                  str(len(arch_rows)))
        else:
            print("      (архивных чатов AutoClaw в базе нет — T1c пропущен)")
        # р49: удалённые чаты AutoClaw — скрыты, метка del
        del_rows = [r for r in rows if r.get("type") == "del"]
        if del_rows:
            check("T1d: deleted_at — скрыт, метка del (р49)",
                  all(r.get("hidden") is True for r in del_rows),
                  str(len(del_rows)))
        else:
            print("      (удалённых чатов AutoClaw в базе нет — T1d пропущен)")

    # --- T1b: открытие несуществующего файла ---
    print("T1b. open <нет такого файла>")
    try:
        ad.open(TMP / "нет-такой-базы.sqlite")
        check("T1b AdapterError «файл не найден»", False, "исключения не было")
    except AdapterError as exc:
        check("T1b AdapterError «файл не найден»",
              "не найден" in exc.message.lower() or "не найден" in exc.message,
              exc.message)

    if not rows:
        print("Список пуст — дальнейшие экспорт-тесты невозможны.")
        ad.close(con)
        return finish()

    dialog_id = rows[0]["id"]

    # --- T2: экспорт одного диалога в md (BOM по умолчанию) ---
    print("T2. export_chat md")
    out_dir = TMP / "one"
    res = ad.export_chat(con, dialog_id, out_dir, ExportOptions(fmt="md"))
    path = Path(res["path"])
    check("T2 {path, requests}", path.is_file() and res.get("requests", 0) >= 1,
          f"res={res}")
    check("T2 имя AC-*.md", path.name.startswith("AC-") and path.suffix == ".md",
          path.name)
    project = rows[0].get("project", "")
    if project:
        check("T2 файл в субпапке проекта (р25: workspace)",
              path.parent == out_dir / project, str(path.parent))
    proj_row = next((r for r in rows if r.get("project")), None)
    if proj_row:
        res_p = ad.export_chat(con, proj_row["id"], out_dir,
                               ExportOptions(fmt="md"))
        check("T2b файл в субпапке проекта (р25/26)",
              Path(res_p["path"]).parent == out_dir / proj_row["project"],
              str(Path(res_p["path"]).parent))
    else:
        print("      (не-дефолтных проектов в базе нет — T2b пропущен)")
    check("T2 файл не пуст", path.stat().st_size > 0)
    check("T2 md с BOM", path.read_bytes()[:3] == b"\xef\xbb\xbf",
          f"первые байты: {path.read_bytes()[:3]!r}")

    # --- T3: en, формат txt ---
    print("T3. export_chat txt /lang en")
    out_txt = TMP / "one_en"
    ad.export_chat(con, dialog_id, out_txt, ExportOptions(fmt="txt", lang="en"))
    files_txt = sorted(out_txt.rglob("AC-*.txt"))
    check("T3 файл txt создан", len(files_txt) == 1, str([p.name for p in files_txt]))
    if files_txt:
        text = files_txt[0].read_text(encoding="utf-8-sig")
        check("T3 подписи на английском", "Session" in text, "нет 'Session' в тексте")
        check("T3 txt с BOM", files_txt[0].read_bytes()[:3] == b"\xef\xbb\xbf")

    # --- T4: zh, формат md ---
    print("T4. export_chat md /lang zh")
    out_zh = TMP / "one_zh"
    ad.export_chat(con, dialog_id, out_zh, ExportOptions(fmt="md", lang="zh"))
    files_zh = sorted(out_zh.rglob("AC-*.md"))
    check("T4 файл md создан", len(files_zh) == 1)
    if files_zh:
        text = files_zh[0].read_text(encoding="utf-8-sig")
        check("T4 подписи на китайском", "会话" in text, "нет '会话' в тексте")

    # --- T5: несуществующий диалог -> AdapterError ---
    print("T5. export_chat <несуществующий>")
    try:
        ad.export_chat(con, "zzz-нет-такого-диалога", TMP / "nope",
                       ExportOptions())
        check("T5 AdapterError с message", False, "исключения не было")
    except AdapterError as exc:
        check("T5 AdapterError с message", bool(exc.message.strip()), exc.message)

    # --- T6: всё в один файл (ER-2) ---
    print("T6. export_single_file md")
    single_dir = TMP / "single"
    res = ad.export_single_file(con, single_dir, ExportOptions(fmt="md"))
    spath = Path(res["path"])
    check("T6 один файл AC-ALL-*.md",
          spath.is_file() and spath.name.startswith("AC-ALL-"), str(res))
    check("T6 sessions >= 1", res.get("sessions", 0) >= 1, str(res))
    if spath.is_file():
        text = spath.read_text(encoding="utf-8-sig")
        if rows[0].get("project"):
            check("T6 метка с проектом «Новый диалог <проект>\…» (р25)",
                  f"Новый диалог {rows[0]['project']}" in text)
        check("T6 несколько ходов внутри", text.count("## 1. Вы") >= 1)
        check("T6 двойной разделитель --- (Я5)", "---\n---" in text)
        # подсчёт якорем строки-метки: контент чатов может содержать те же фразы
        check("T6 метка «Новый диалог» с проектом (Я5/р25)",
              len(re.findall(r"^Новый диалог (?:[^\\\r\n]+\\)?AC-.*\.md$",
                             text, re.M))
              == res.get("sessions", -1))

    # --- T7: флаг BOM по-форматно (ER-3) ---
    print("T7. bom False/True")
    nb = TMP / "bomless"
    ad.export_chat(con, dialog_id, nb, ExportOptions(fmt="md", bom=False))
    files_nb = sorted(nb.rglob("AC-*.md"))
    check("T7 md без BOM при bom=False",
          files_nb and files_nb[0].read_bytes()[:3] != b"\xef\xbb\xbf")
    wb = TMP / "withbom"
    ad.export_chat(con, dialog_id, wb, ExportOptions(fmt="md", bom=True))
    files_wb = sorted(wb.rglob("AC-*.md"))
    check("T7 BOM на месте при bom=True",
          files_wb and files_wb[0].read_bytes()[:3] == b"\xef\xbb\xbf")
    jb = TMP / "jsonbom"
    ad.export_chat(con, dialog_id, jb, ExportOptions(fmt="json", bom=True))
    files_jb = sorted(jb.rglob("AC-*.json"))
    check("T7 json всегда без BOM",
          files_jb and files_jb[0].read_bytes()[:3] != b"\xef\xbb\xbf")

    # --- T8: повторный экспорт -> суффикс (1), без перезаписи (ER-5) ---
    print("T8. повторный экспорт -> суффикс (1)")
    first = Path(ad.export_chat(con, dialog_id, TMP / "twice",
                                ExportOptions(fmt="md"))["path"])
    second = Path(ad.export_chat(con, dialog_id, TMP / "twice",
                                 ExportOptions(fmt="md"))["path"])
    check("T8 имя с (1)",
          second.stem.endswith(" (1)"), second.name)
    check("T8 исходник цел", first.is_file())

    # --- T9: паритет tools md <-> txt (ER-4) ---
    print("T9. паритет tools md и txt")
    md_t = TMP / "parity_md"
    txt_t = TMP / "parity_txt"
    ad.export_chat(con, dialog_id, md_t, ExportOptions(fmt="md", tools=True))
    ad.export_chat(con, dialog_id, txt_t, ExportOptions(fmt="txt", tools=True))
    files_mt = sorted(md_t.glob("AC-*.md"))
    files_tt = sorted(txt_t.glob("AC-*.txt"))
    md_has = (files_mt and "🔧" in files_mt[0].read_text(encoding="utf-8-sig"))
    txt_text = files_tt[0].read_text(encoding="utf-8-sig") if files_tt else ""
    check("T9 tools в txt при наличии в md",
          (not md_has) or "🔧" in txt_text, f"md_has={md_has}")

    # --- T10: чужая база (ZCode db.sqlite) -> понятная ошибка ---
    print("T10. open <ZCode db.sqlite>")
    zcode_db = Path.home() / ".zcode" / "cli" / "db" / "db.sqlite"
    if zcode_db.is_file():
        try:
            ad.open(zcode_db)
            check("T10 AdapterError «не база AutoClaw»", False, "исключения не было")
        except AdapterError as exc:
            check("T10 AdapterError «не база AutoClaw»",
                  "не база AutoClaw" in exc.message, exc.message)
    else:
        print("      (ZCode db.sqlite не найден — T10 пропущен)")

    # --- T11: блок инструментов с обрезкой в txt (ER-4; как T9 — паритет с md) ---
    print("T11. tools в txt (tool_limit=200)")
    tt2 = TMP / "tools_txt"
    ad.export_chat(con, dialog_id, tt2,
                   ExportOptions(fmt="txt", tools=True, tool_limit=200))
    files_t11 = sorted(tt2.glob("AC-*.txt"))
    text11 = files_t11[0].read_text(encoding="utf-8-sig") if files_t11 else ""
    check("T11 tools в txt при наличии в md",
          (not md_has) or ("Инструменты" in text11 and "🔧" in text11),
          f"md_has={md_has}")

    ad.close(con)
    return finish()


def finish() -> int:
    print("-" * 60)
    print(f"Итого: PASS={PASS_COUNT}, FAIL={FAIL_COUNT}")
    for line in FAILURES:
        print(f"  провал: {line}")
    return 1 if FAIL_COUNT else 0


if __name__ == "__main__":
    sys.exit(main())
