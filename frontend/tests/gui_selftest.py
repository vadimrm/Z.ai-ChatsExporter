# -*- coding: utf-8 -*-
"""Самопроверка GUI: языки, сортировка ↑/↓, ☑-колонка, матрица, серия
экспорта, «всё в один файл», режим Zcode Chats (реальный), правки раунда 2,
раунды 7–13 («SQL база:», копия db+wal+shm, колонка «Обзор…»/«Экспорт SQL
базы»/«Donate» в панели; субпапки «AutoClaw SQL»/«ZCode SQL»/«AutoClaw
Chats»/«ZCode Chats»; без имени движка в статусе; /db в /list; Ctrl+C
статуса; копируемое окно ошибок; «Обновить чаты»/«Поиск чата»).

Окно создаётся скрытым (withdraw) — на экране ничего не мигает.
Запуск: python frontend\\tests\\gui_selftest.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "frontend"))
sys.path.insert(0, str(ROOT / "backend"))

import tkinter as tk
from tkinter import messagebox as _real_messagebox

from adapter import adapter_for
import config
import db_profiles
import i18n
import app as app_module
from app import BRAND, CHECK_OFF, CHECK_ON, App
from i18n import tr

# Диалоги в скрытом окне никто не закроет — глушим.
app_module.messagebox.showwarning = lambda *a, **k: None
app_module.messagebox.showerror = lambda *a, **k: None
app_module.messagebox.askyesno = lambda *a, **k: True

# Окно ошибок (раунд 13) — Toplevel не должен всплывать в скрытом прогоне;
# записываем вызовы и проверяем содержимое.
ERROR_WINDOWS: list[tuple[str, str]] = []


def _fake_error_window(self, title: str, text: str) -> None:
    ERROR_WINDOWS.append((title, text))


app_module.App._show_error_window = _fake_error_window

TMP = ROOT / "frontend" / "tests" / "_tmp"
TMP_OUT = TMP / "selftest_out"
TMP_ZCODE = TMP / "selftest_zcode"

# Детерминированность (раунд 12/19: ExportChat.cfg портативный): изолируем
# от реальных файлов пользователя (ExportChat.cfg и db_profiles.cfg).
TMP.mkdir(parents=True, exist_ok=True)
os.environ["EXPORTCHAT_CONFIG_DIR"] = str(TMP)
if not (TMP / "ExportChat.cfg").is_file():
    (TMP / "ExportChat.cfg").write_text(
        json.dumps(config.DEFAULTS, ensure_ascii=False), encoding="utf-8-sig")
# db_profiles.cfg создаём ЗАРАНЕЕ (жизненный цикл «нет файла» проверяется
# в units) — иначе App при первом прогоне покажет dbp_missing-предупреждение
if not (TMP / "db_profiles.cfg").is_file():
    db_profiles.write_factory(TMP / "db_profiles.cfg")

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


def wait_idle(app: App, timeout: int = 180) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        app._poll()
        if app._batch is None and not app.runner.busy():
            return True
        time.sleep(0.05)
    return False


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    app = App(root, persist_config=False)

    # Детерминированность: не зависим от реального конфига пользователя.
    for fmt in config.FORMATS:
        for key in config.OPTION_KEYS:
            app.opt_vars[fmt][key].set(fmt != "json" if key == "bom" else False)
    app.fmt_vars["md"].set(True)
    app.fmt_vars["txt"].set(True)
    app.fmt_vars["json"].set(False)
    app.single_var.set(False)
    app.tool_limit_var.set("1000")
    app._update_limit_state()

    # --- языки: брендинг статичен, пояснение переводится ---
    print("Языки и заголовок")
    for lang in i18n.LANGS:
        i18n.set_lang(lang)
        app._apply_language()
        check(f"язык {lang}: заголовок с версией (раунд 14)",
              root.title() == f"{BRAND} ver. {app_module.APP_VERSION}"
                              f" - {tr('title_explain')}")
        check(f"язык {lang}: кнопки",
              app.btn_refresh.cget("text") == tr("refresh")
              and app.btn_export_selected.cget("text") == tr("btn_export_selected"))
        check(f"язык {lang}: база/donate",
              app.btn_sql_db.cget("text") == tr("btn_db")
              and app.btn_output_folder.cget("text") == tr("btn_output_folder")
              and app.btn_export_db.cget("text") == tr("btn_export_db")
              and app.btn_donate.cget("text") == tr("btn_donate"))
        # раунд 21: меню статуса создано при старте — подписи переводятся
        check(f"язык {lang}: меню статуса «Копировать» (р21)",
              app.status_menu.entrycget(0, "label") == tr("copy")
              and app.status_menu.entrycget(1, "label") == tr("copy_title"),
              str(app.status_menu.entrycget(0, "label")))
    i18n.set_lang("ru")
    app._apply_language()

    # --- Я4 (раунд 18; раунд 20: кнопка «…в один файл» стала чекбоксом) —
    # Сайт/Donate/Открыть папку экспорта — одной ширины на всех языках ---
    check("ширина Сайт/Donate/Открыть папку экспорта одинакова (р18/20)",
          app.btn_site.cget("width")
          == app.btn_donate.cget("width")
          == app.btn_open_folder.cget("width")
          and int(app.btn_site.cget("width") or 0) > 0,
          f"{app.btn_site.cget('width')} / {app.btn_donate.cget('width')} / "
          f"{app.btn_open_folder.cget('width')}")

    # --- раунды 7–14: блок базы и компоновка низа окна ---
    check("URL Donate", app_module.DONATE_URL == "https://www.paypal.me/vmgames/5")
    check("титул содержит версию (раунд 14/19–22: 1.27, без RC)",
          root.title() == f"{BRAND} ver. {app_module.APP_VERSION}"
                          f" - {tr('title_explain')}"
          and app_module.APP_VERSION == "1.27",
          root.title())
    # --- релиз 1.27 (раунд 22): текст подсказки BOM удалён; виджет-пустышка
    # держит ячейку — блок «SQL база» не сдвинут ---
    check("подсказка BOM: текст удалён, виджет на месте (р22)",
          not hasattr(app, "hint_db") and hasattr(app, "hint_bom")
          and app.hint_bom.cget("text") == ""
          and "hint_bom" not in i18n.STRINGS["ru"]
          and "hint_bom" not in i18n.STRINGS["en"]
          and "hint_bom" not in i18n.STRINGS["zh"],
          f"text={app.hint_bom.cget('text')!r}")
    check("кнопки «Папка экспорта»/«SQL база»/«Экспорт SQL базы» существуют",
          app.btn_output_folder.winfo_exists()
          and app.btn_sql_db.winfo_exists()
          and app.btn_export_db.winfo_exists()
          and tr("btn_output_folder") == "Папка экспорта"
          and tr("btn_db") == "SQL база")
    check("старые виджеты удалены (Обзор…/надписи/подсказка)",
          not hasattr(app, "btn_browse_output")
          and not hasattr(app, "btn_browse_db")
          and not hasattr(app, "lbl_db") and not hasattr(app, "lbl_output")
          and not hasattr(app, "hint_db"))
    dbe = app.db_entry.grid_info()
    check("строка базы: [btn SQL база][entry] в одном ряду, entry тянется",
          app.btn_sql_db.grid_info()["row"] == 0
          and dbe["row"] == 0 and dbe["column"] == 1
          and dbe["sticky"] == "ew"
          and app.btn_sql_db.master is dbe["in"],
          str(dbe))
    check("«Экспорт SQL базы» — под полем базы (row1 col1, место подсказки)",
          app.btn_export_db.grid_info()["row"] == 1
          and app.btn_export_db.grid_info()["column"] == 1
          and app.btn_export_db.master is app.btn_sql_db.master,
          str(app.btn_export_db.grid_info()))
    check("строка вывода — в actions (раунд 17): [btn Папка экспорта][entry span5]",
          app.btn_output_folder.master is app.btn_export_selected.master
          and app.btn_output_folder.grid_info()["row"] == 1
          and app.output_entry.grid_info()["columnspan"] == 5
          and app.output_entry.grid_info()["sticky"] == "ew",
          f"out={app.btn_output_folder.grid_info()}, "
          f"entry={app.output_entry.grid_info()}")
    asingle = app.chk_single.grid_info()
    aselected = app.btn_export_selected.grid_info()
    adonate = app.btn_donate.grid_info()
    aopen = app.btn_open_folder.grid_info()
    check("ряд 0: selected (col6) и Открыть папку экспорта (col8) — ОДНА линия "
          "(раунд 17)",
          aselected["row"] == 0 and aselected["column"] == 6
          and aopen["row"] == 0 and aopen["column"] == 8
          and aopen["sticky"] == "e"
          and aopen["in"] == aselected["in"],
          f"selected={aselected.get('row')},{aselected.get('column')}; "
          f"open={aopen.get('row')},{aopen.get('column')}")
    check("ряд 1: чекбокс single (col6) и Donate (col8); Donate над «Сайтом» (р20)",
          asingle["row"] == 1 and asingle["column"] == 6
          and adonate["row"] == 1 and adonate["column"] == 8
          and adonate["sticky"] == "e"
          and adonate["in"] == asingle["in"],
          f"single={asingle.get('row')},{asingle.get('column')}; "
          f"donate={adonate.get('row')},{adonate.get('column')}")
    check("«Снять выбор» и «Открыть папку экспорта» (переименования, раунд 15)",
          app.btn_clear_all.cget("text") == tr("btn_clear_all")
          == "Снять выбор"
          and app.btn_open_folder.cget("text") == tr("btn_open_folder")
          == "Открыть папку экспорта",
          f"{app.btn_clear_all.cget('text')!r} / "
          f"{app.btn_open_folder.cget('text')!r}")
    check("progress уже «Выбрать всё» (раунд 14)",
          int(app.progress.cget("length"))
          == app.btn_select_all.winfo_reqwidth(),
          f"{app.progress.cget('length')} vs {app.btn_select_all.winfo_reqwidth()}")
    check("«Выбрать всё»/«Снять выбор» = «Папка экспорта» по ширине (раунд 16)",
          app.btn_select_all.cget("width")
          == app.btn_clear_all.cget("width")
          == app.btn_output_folder.cget("width")
          == max(app_module._ui_width(tr("btn_output_folder")),
                 app_module._ui_width(tr("btn_select_all")),
                 app_module._ui_width(tr("btn_clear_all"))) + 2,
          f"{app.btn_select_all.cget('width')} / "
          f"{app.btn_clear_all.cget('width')} / "
          f"{app.btn_output_folder.cget('width')}")
    check("чекбокс «записать в один файл» на месте кнопки (р20/21), старой нет",
          not hasattr(app, "btn_export_single")
          and app.chk_single.cget("text") == tr("chk_single")
          and tr("chk_single") == "записать в один файл")
    # --- раунд 21: CJK-ширина — кнопка экспорта не уже чекбокса, zh не обрезан ---
    i18n.set_lang("zh")
    app._apply_language()
    check("zh: ширина кнопки экспорта = max(кнопка, чекбокс)+2 (р21)",
          app.btn_export_selected.cget("width")
          == max(app_module._ui_width(tr("btn_export_selected")),
                 app_module._ui_width(tr("chk_single"))) + 2
          and app.btn_export_selected.cget("width")
          >= app_module._ui_width(tr("btn_export_selected")),
          f"width={app.btn_export_selected.cget('width')}")
    i18n.set_lang("ru")
    app._apply_language()

    # --- раунд 19 (дополнение): db_profiles.cfg — источник путей баз ---
    check("db_profiles загружены (заводские)",
          app.db_profiles == db_profiles.DEFAULT_PROFILES)
    check("db_profiles.cfg существует рядом (в изолированной папке теста)",
          (TMP / "db_profiles.cfg").is_file())
    check("нет предупреждения о заводском файле (он был создан раньше)",
          app.db_profiles_note is None, str(app.db_profiles_note))

    # --- раунд 12/19: база в задании списка, копия статуса и титула ---
    orig_db = app.db_var.get()
    app.db_var.set("C:\\z\\my db\\db.sqlite")
    list_job = app._list_job()
    check("задание списка получает базу из поля (раунд 12)",
          list_job["kind"] == "list" and list_job["mode"] == "autoclaw"
          and list_job["db"] == "C:\\z\\my db\\db.sqlite", str(list_job))
    app.db_var.set("")
    check("пустое поле → db=\"\" в задании", app._list_job()["db"] == "")
    app.db_var.set(orig_db)
    app._set_status("текст ошибки для копии")
    app._copy_status()  # сразу: фоновая загрузка может сменить статус
    root.update()
    check("Ctrl+C копирует статус в буфер",
          root.clipboard_get() == "текст ошибки для копии",
          root.clipboard_get())
    app._set_status("")
    app._copy_status()
    check("пустой статус → копируется титул с версией (раунд 14)",
          root.clipboard_get() == root.title(), root.clipboard_get())
    check("подписи: «Обновить чаты» и «Поиск чата:» (ru)",
          tr("refresh") == "Обновить чаты" and tr("search") == "Поиск чата:",
          f"{tr('refresh')!r} / {tr('search')!r}")

    # --- сортировка: стрелки ↑/↓ (Я7) ---
    print("Сортировка")
    check("старт: Обновлён ↓", app.tree.heading("updated")["text"].endswith("↓"))
    app._on_heading_click("title")
    check("клик Название → ↑", app.tree.heading("title")["text"].endswith("↑"))
    app._on_heading_click("title")
    check("повторный клик Название → ↓", app.tree.heading("title")["text"].endswith("↓"))

    rows = [
        {"id": "c", "title": "Вишня", "updated_at": "2026-01-03T10:00:00Z",
         "created_at": "2026-01-01T10:00:00Z", "updated_local": "03.01.2026 13:00",
         "created_local": "01.01.2026 13:00", "requests": 1},
        {"id": "a", "title": "Абрикос", "updated_at": "2026-01-02T10:00:00Z",
         "created_at": "2026-01-02T10:00:00Z", "updated_local": "02.01.2026 13:00",
         "created_local": "02.01.2026 13:00", "requests": 3},
        {"id": "b", "title": "Банан", "updated_at": "2026-01-01T10:00:00Z",
         "created_at": "2026-01-03T10:00:00Z", "updated_local": "01.01.2026 13:00",
         "created_local": "03.01.2026 13:00", "requests": 2},
    ]
    app.rows = rows
    app.rows_by_id = {r["id"]: r for r in rows}
    app.checked.clear()
    app._sort_col, app._sort_desc = "updated", True
    app._apply_filter()
    check("updated ↓ → c,a,b", list(app.tree.get_children()) == ["c", "a", "b"])
    app._on_heading_click("title")
    check("Название ↑ → Абрикос,Банан,Вишня",
          [app.tree.item(i, "values")[1] for i in app.tree.get_children()]
          == ["Абрикос", "Банан", "Вишня"])
    app._on_heading_click("requests")
    check("Запросов ↓ → 3,2,1",
          [int(app.tree.item(i, "values")[4]) for i in app.tree.get_children()]
          == [3, 2, 1])

    # --- ☑-колонка ---
    print("Чекбоксы чатов")
    app._set_checked("a", True)
    check("☑ появился", app.tree.item("a", "values")[0] == CHECK_ON)
    app._set_checked("a", False)
    check("☐ после снятия", app.tree.item("a", "values")[0] == CHECK_OFF)
    app._select_all_visible()
    check("Выбрать всё — 3 отмечено", app.checked == {"a", "b", "c"})
    app._clear_all_visible()
    check("Стереть всё — пусто", not app.checked)
    app.search_var.set("бан")
    check("фильтр: виден только Банан", app.visible_ids == ["b"])
    app.search_var.set("")

    # --- матрица опций → ExportOptions по форматам ---
    print("Матрица опций → ExportOptions")
    app.opt_vars["md"]["tools"].set(True)
    app.opt_vars["md"]["bom"].set(False)
    check("BOM txt независим (остался True)", app.opt_vars["txt"]["bom"].get() is True)
    app.tool_limit_var.set("500")
    opts_md = app._options_for("md")
    check("md: tools=True", opts_md["tools"] is True, str(opts_md))
    check("md: tool_limit 500", opts_md["tool_limit"] == 500)
    check("md: bom=False (по-форматно, ER-3)", opts_md["bom"] is False)
    opts_txt = app._options_for("txt")
    check("txt: tools=False (матрица независима)", opts_txt["tools"] is False)
    check("txt: bom=True (BOM независим)", opts_txt["bom"] is True)
    opts_json = app._options_for("json")
    check("json: bom всегда False", opts_json["bom"] is False)
    app.opt_vars["md"]["all_files"].set(True)
    check("autoclaw: all_files передаётся",
          app._options_for("md")["all_files"] is True)
    app.mode_var.set("zcode")
    check("zcode: all_files не передаётся (раунд 19)",
          app._options_for("md")["all_files"] is False)
    app.mode_var.set("autoclaw")
    app.opt_vars["md"]["all_files"].set(False)

    app.opt_vars["md"]["bom"].set(True)
    check("md: bom=True при BOM on", app._options_for("md")["bom"] is True)

    app.opt_vars["md"]["tools"].set(False)
    app._update_limit_state()
    check("лимит серый при всех tools off", app.tool_limit_box.instate(["disabled"]))
    app.opt_vars["json"]["tools"].set(True)
    app._update_limit_state()
    check("лимит активен при tools on (json)", app.tool_limit_box.instate(["!disabled"]))
    app.opt_vars["json"]["tools"].set(False)
    app._update_limit_state()

    # --- single-задание (ER-2 + chat_ids раунда 20) ---
    print("single-задание")
    app.output_var.set(str(TMP_OUT))
    single_job = app._single_job(["md"], app._chat_output_dir(), ["a", "b"])
    check("single: kind=single, out_dir = субпапка режима, chat_ids (р13/20)",
          single_job["kind"] == "single"
          and single_job["out_dir"] == str(TMP_OUT / "AutoClaw Chats")
          and single_job["chat_ids"] == ["a", "b"],
          str(single_job))
    check("имена субпапок чатов (раунд 13)",
          app_module.CHAT_SUBDIRS == {"autoclaw": "AutoClaw Chats",
                                      "zcode": "ZCode Chats"})
    check("single: формат md", single_job["formats"] == ["md"])
    check("single: options — поля ExportOptions",
          set(single_job["options"]["md"])
          == {"tools", "narration", "tool_limit", "all_files",
              "no_files", "bom", "lang"})

    # --- реальный список AutoClaw ---
    print("Список диалогов (AutoClaw)")
    _ad = adapter_for("autoclaw")
    _con = _ad.open(app._db_source_path())
    real_rows = _ad.list_chats(_con)
    _ad.close(_con)
    check("движок вернул диалоги", len(real_rows) > 0)
    app.rows = real_rows
    app.rows_by_id = {r["id"]: r for r in real_rows}
    app.checked.clear()
    app._apply_filter()
    check("таблица заполнена", len(app.tree.get_children()) == len(real_rows))
    app._on_list_ready(real_rows)
    check("по умолчанию отмечен первый видимый",
          len(app.checked) == 1 and app.visible_ids[0] in app.checked)
    # подгонка колонок: при ширине таблицы 598 все колонки видимы (Я-новое 2)
    app._fit_columns(598)
    total = sum(app.tree.column(c)["width"]
                for c in ("title", "updated", "created", "requests", "check"))
    check("колонки вписаны в 598px", total <= 598, f"сумма={total}")
    check("«Название» = остаток ширины", app.tree.column("title")["width"] == 236)
    wait_idle(app, 60)

    # --- серия экспорта 2×2 ---
    print("Серия экспорта (AutoClaw)")
    TMP_OUT.mkdir(parents=True, exist_ok=True)
    for old in TMP_OUT.iterdir():
        # в _tmp могут остаться субпапки (экспорт SQL-базы раунда 8)
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    app.checked = {real_rows[0]["id"], real_rows[1]["id"]}
    app.fmt_vars["md"].set(True)
    app.fmt_vars["txt"].set(True)
    app.fmt_vars["json"].set(False)
    app.output_var.set(str(TMP_OUT))
    app.export_selected()
    check("серия запущена", app._batch is not None)
    ok = wait_idle(app, 180)
    check("серия завершилась", ok and app._batch is None)
    check("файлов 2×2 (md+txt) в субпапке «AutoClaw Chats»",
          len(list((TMP_OUT / "AutoClaw Chats").glob("AC-*.md"))) == 2
          and len(list((TMP_OUT / "AutoClaw Chats").glob("AC-*.txt"))) == 2)
    check("итоговый статус «Готово: …»", app.status_lbl.cget("text").startswith("Готово:"))
    check("кнопки снова активны", app.btn_export_selected.instate(["!disabled"]))
    check("JSON BOM остался серым после задач (Я3)",
          app.matrix_checks[("bom", "json")].instate(["disabled"]))

    # --- ошибка в серии не прерывает остальные ---
    fake = {"id": "zzz-fake", "title": "нет такого", "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z", "created_local": "01.01.2026 00:00",
            "updated_local": "01.01.2026 00:00", "requests": 0}
    app.rows = real_rows + [fake]
    app.rows_by_id[fake["id"]] = fake
    app._apply_filter()
    app.checked = {fake["id"]}
    app.export_selected()
    check("серия с ошибкой запущена", app._batch is not None)
    ok = wait_idle(app, 120)
    check("серия с ошибкой завершилась", ok and app._batch is None)
    check("итог: 0 файлов, 2 ошибки (фейк × 2 формата)",
          "0 файл(ов), ошибок: 2" in app.status_lbl.cget("text"))
    check("окно ошибок открылось с текстом (копируемый диалог, раунд 13)",
          len(ERROR_WINDOWS) == 1 and "нет такого" in ERROR_WINDOWS[0][1],
          str(ERROR_WINDOWS[:1]))

    # --- копия SQL-базы (раунд 7): главный файл + -wal, без -shm ---
    print("Копия SQL-базы (раунд 7)")
    db_src = TMP / "fake_db.sqlite"
    db_src.write_bytes(b"SQLite format 3 fake")
    Path(str(db_src) + "-wal").write_bytes(b"wal-part")
    db_dst = TMP / "fake_db_copy.sqlite"
    copied = app_module.copy_db_files(db_src, db_dst)
    check("копия: главный файл", db_dst.read_bytes() == b"SQLite format 3 fake")
    check("копия: -wal переносится",
          Path(str(db_dst) + "-wal").read_bytes() == b"wal-part")
    check("копия: -shm без источника не создаётся",
          not Path(str(db_dst) + "-shm").exists())
    check("copy_db_files вернул [db, -wal]", len(copied) == 2)
    orig_db = app.db_var.get()
    app.db_var.set(str(db_src))
    check("источник базы из поля", app._db_source_path() == db_src)

    # экспорт базы — всегда в субпапку «AutoClaw SQL», БЕЗ диалога (раунд 16)
    app.output_var.set(str(TMP_OUT))
    real_save = app_module.filedialog.asksaveasfilename
    app._export_db()
    copy1 = TMP_OUT / "AutoClaw SQL" / "fake_db.sqlite"
    check("копия базы в субпапке «AutoClaw SQL» (без диалога, раунд 16)",
          copy1.is_file() and Path(str(copy1) + "-wal").is_file(), str(copy1))
    check("диалог сохранения не вызывается (раунд 16)",
          app_module.filedialog.asksaveasfilename is real_save)
    app._export_db()
    copy2 = TMP_OUT / "AutoClaw SQL" / "fake_db (1).sqlite"
    check("повторный экспорт — суффикс « (1)», без перезаписи",
          copy2.is_file() and copy1.is_file(), str(copy2))
    check("статус экспорта базы",
          app.status_lbl.cget("text").startswith("SQL база экспортирована"),
          app.status_lbl.cget("text"))
    app.db_var.set(orig_db)  # вернуть поле как было — дальнейшие секции не меняются
    check("имена субпапек (раунд 8)",
          app_module.SQL_SUBDIRS == {"autoclaw": "AutoClaw SQL",
                                     "zcode": "ZCode SQL"})

    # --- чекбокс «Экспорт в один файл» (ER-2 + раунд 20) ---
    print("Экспорт в один файл (выбранные чаты)")
    app.fmt_vars["md"].set(True)
    app.fmt_vars["txt"].set(False)
    app.checked = set()
    app.export_selected()
    check("без отмеченных чатов экспорт не запускается, новый текст (р20)",
          app._batch is None
          and app.status_lbl.cget("text") == tr("status_select_row"),
          app.status_lbl.cget("text"))
    app.checked = {real_rows[0]["id"], real_rows[1]["id"]}
    app.single_var.set(True)
    app.export_selected()
    check("single запущен по чекбоксу", app._batch is not None)
    ok = wait_idle(app, 300)
    check("single завершился", ok and app._batch is None)
    all_files = list((TMP_OUT / "AutoClaw Chats").glob("AC-ALL-*.md"))
    check("файл AC-ALL-*.md создан (один)", len(all_files) == 1)
    check("итог single «Готово: 1 файл(ов), ошибок: 0»",
          "Готово: 1 файл(ов), ошибок: 0" in app.status_lbl.cget("text"),
          app.status_lbl.cget("text"))
    if all_files:
        pack_text = all_files[0].read_text(encoding="utf-8-sig")
        # подсчёт якорем строки-метки: контент реальных чатов содержит те же
        # фразы (это же наши чаты) — наивный count ненадёжен
        check("single: внутри только 2 выбранных диалога (р20)",
              len(re.findall(r"^Новый диалог AC-.*\.md$", pack_text, re.M)) == 2,
              f"меток: {len(re.findall(r'^Новый диалог AC-.*\\.md$', pack_text, re.M))}")
        check("single: заголовок «Выбранные диалоги AutoClaw (2)» (р20)",
              "# Выбранные диалоги AutoClaw (2)" in pack_text)
        check("single: двойной разделитель ---", "---\n---" in pack_text)
        check("single: оба выбранных названия присутствуют",
              (real_rows[0]["title"] or "") in pack_text
              and (real_rows[1]["title"] or "") in pack_text)
    app.single_var.set(False)  # дальше — обычная серия (zcode-блок)

    # --- режим Zcode Chats (реальный движок) ---
    print("Режим Zcode Chats")
    ac_db = app.db_var.get()  # значение поля AutoClaw до переключения
    TMP_ZCODE.mkdir(parents=True, exist_ok=True)
    for old in TMP_ZCODE.rglob("*"):
        if old.is_file():
            old.unlink()
    autoclaw_count = len(app.tree.get_children())  # как есть, вместе с фейком
    wait_idle(app, 60)  # дождаться фоновой ver-задачи перед переключением
    app.mode_var.set("zcode")
    app._on_mode_change()
    ok = wait_idle(app, 120)
    check("zcode: список загрузился", ok and len(app.tree.get_children()) > 0,
          f"ok={ok}, строк={len(app.rows)}, visible={len(app.visible_ids)}, "
          f"статус={app.status_lbl.cget('text')!r}")
    check("zcode: без сабагентских сессий (Я7)",
          all("Search for ZCode" not in (app.rows_by_id[i].get("title") or "")
              for i in app.visible_ids))
    zcode_first = app.visible_ids[0]
    check("zcode: первый чат отмечен", zcode_first in app.checked)
    app.checked = {zcode_first}
    app.fmt_vars["md"].set(True)
    app.fmt_vars["txt"].set(False)
    app.output_var.set(str(TMP_ZCODE))
    app.export_selected()
    ok = wait_idle(app, 180)
    check("zcode: экспорт завершился", ok and app._batch is None)
    zc_files = list(TMP_ZCODE.rglob("ZC-*.md"))
    check("zcode: файл ZC-*.md создан в субпапке «ZCode Chats»",
          len(zc_files) == 1
          and (TMP_ZCODE / "ZCode Chats") in (zc_files[0].parents if zc_files else []),
          str(zc_files[0].parent if zc_files else "-"))
    expected_leaf = ((app.rows_by_id[zcode_first].get("directory") or "")
                     .split("\\")[-1])
    ok_leaf = (zc_files[0].parent.name == expected_leaf if expected_leaf
               else zc_files[0].parent == TMP_ZCODE / "ZCode Chats")
    check("zcode: файл в папке проекта (Я6)",
          len(zc_files) == 1 and ok_leaf,
          f"parent={zc_files[0].parent if zc_files else '-'}, "
          f"ожидался={expected_leaf!r}")
    check("zcode: статус «Готово: …»", app.status_lbl.cget("text").startswith("Готово:"))
    check("zcode: all_files не передаётся (раунд 19)",
          app._options_for("md")["all_files"] is False)
    app.db_var.set("C:\\zcode_test\\db.sqlite")
    app._persist()

    # возврат в AutoClaw — состояние восстановлено
    app.mode_var.set("autoclaw")
    app._on_mode_change()
    ok = wait_idle(app, 60)
    check("autoclaw: состояние восстановлено",
          len(app.tree.get_children()) == autoclaw_count
          and app.status_lbl.cget("text").startswith("Диалогов:"))
    check("autoclaw: значение поля базы возвращено (раздельные пути)",
          app.db_var.get() == ac_db,
          f"db_var={app.db_var.get()!r}, ac_db={ac_db!r}")
    app._on_list_ready(real_rows)
    wait_idle(app, 60)

    root.destroy()
    print("-" * 60)
    print(f"Итого: PASS={PASS_COUNT}, FAIL={FAIL_COUNT}")
    for line in FAILURES:
        print(f"  провал: {line}")
    return 1 if FAIL_COUNT else 0


if __name__ == "__main__":
    sys.exit(main())
