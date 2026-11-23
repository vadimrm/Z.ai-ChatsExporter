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
# р76: как и db_profiles — ЧИСТЫЙ первый запуск: старый cfg из
# персистентной TMP нёс бы прошлый last_mode; создаём с дефолтами
cfg76 = TMP / "ExportChat.cfg"
if cfg76.exists():
    cfg76.unlink()
cfg76.write_text(
    json.dumps(config.DEFAULTS, ensure_ascii=False), encoding="utf-8-sig")
# р72: наоборот — ЧИСТЫЙ сценарий «нет файла» (как у владельца): убираем
# db_profiles.cfg (и .err) до прогона; App создаст заводской и отложит
# жёлтую заметку dbp_missing — самотест её проверяет (ниже, р72)
for leftover in ("db_profiles.cfg", "db_profiles.cfg.err"):
    path = TMP / leftover
    if path.exists():
        path.unlink()

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
    # р82 (фикс самотеста): стартовый диалог импорта («Отсутствует копия —
    # импортировать?») с р72 собственный (_dialog → wait_window) — без
    # mainloop его никто не закроет. Прежде проходило ВСЛЕПУЮ: в
    # персистентной _tmp оставалась AutoClawData прошлых прогонов и диалог
    # не возникал; после чистки _tmp юнитами — зависание. Отвечаем «Да»
    # на уровне класса (мок askyesno р46 умер вместе с messagebox в р72).
    app_module.App._dialog = (lambda self, kind, text,
                              yes_no=False: True)
    app = App(root, persist_config=False)
    first_mode = app.mode_var.get()  # р82: стартовый режим — до переключений

    # --- р72: dbp_missing — жёлтый СТАТУС (не окно), переживает список ---
    check("р72: db_profiles.cfg отсутствовал → заводской создан при старте",
          (TMP / "db_profiles.cfg").is_file())
    # р73 (владелец): нота видна СРАЗУ (до диалога/списка), жёлтым
    check("р73: dbp_missing — жёлтый статус СРАЗУ при старте",
          "записан заводской" in app.status_lbl.cget("text")
          and str(app.status_lbl.cget("foreground")).lower() == "#a05a00",
          f"{app.status_lbl.cget('foreground')} | "
          f"{app.status_lbl.cget('text')}")
    check("р73: dbp-нота НЕ в отложенных заметках (не повторится)",
          app._notes == [], str(app._notes))
    app._on_list_ready([])
    check("р73: после загрузки списка — обычный статус (нота не лезет)",
          "записан заводской" not in app.status_lbl.cget("text"),
          app.status_lbl.cget("text"))

    # --- р72: диалоги собственные — текст копируется, Да/Нет работают ---
    top, result, tw = app._build_dialog("warn", "DLG-MARK-72", yes_no=True)
    check("р72: _dialog — Text-виджет с текстом (выделяется/копируется)",
          tw.get("1.0", "end").strip() == "DLG-MARK-72"
          and tw.cget("state") == "disabled")
    def all_buttons(widget):
        found = []
        for child in widget.winfo_children():
            if isinstance(child, tk.Button):
                found.append(child)
            found += all_buttons(child)
        return found

    buttons72 = all_buttons(top)
    yes_btn = [b for b in buttons72 if b.cget("text") == "Да"]
    check("р72: кнопки диалога локализованы (Да/Нет)",
          sorted(b.cget("text") for b in buttons72) == ["Да", "Нет"],
          [b.cget("text") for b in buttons72])
    yes_btn[0].invoke()
    check("р72: «Да» возвращает True", result["choice"] == 1)
    top2, result2, _tw2 = app._build_dialog("error", "ERR-72", False)
    ok_btn = all_buttons(top2)[0]
    ok_btn.invoke()
    check("р72: ОК-диалог — одна кнопка, выбор 1",
          result2["choice"] == 1 and not top2.winfo_exists())

    # --- р75: «Копировать текст» по правому клику из любого элемента ---
    check("р75: _widget_text — текст кнопки/метки читается",
          app._widget_text(app.btn_refresh) != ""
          and app._widget_text(app.tree) == "",
          app._widget_text(app.btn_refresh))
    app._to_clipboard("MARK-75")
    check("р75: _to_clipboard кладёт в буфер",
          root.clipboard_get() == "MARK-75", root.clipboard_get())
    check("р76: пункт «все надписи окна» убран (метода нет)",
          not hasattr(app, "_copy_all_texts")
          and "m_copy_window" not in i18n.STRINGS["ru"])

    # --- р77: смена языка — статус переводится; старого меню нет ---
    check("р77: старое меню статуса удалено",
          not hasattr(app, "status_menu")
          and not hasattr(app, "_copy_title"))
    app._apply_language()
    check("р77: смена языка — dbp-нота остаётся (переведённой)",
          "заводской" in app.status_lbl.cget("text"),
          app.status_lbl.cget("text"))
    app._on_list_ready([])
    app._apply_language()
    check("р77: смена языка — статус списка на новом языке",
          app._chat_count() >= 0 and app.status_lbl.cget("text") != "",
          app.status_lbl.cget("text"))

    # --- р78: правый клик по таблице — строка ПОД КЛИКОМ ---
    iid1 = app.tree.insert("", "end", values=("T78-a", "x", "y"))
    root.deiconify()          # bbox требует отрисовки — показать на миг
    app.tree.update()
    bbox = app.tree.bbox(iid1)
    check("р78: _tree_row_text — текст строки под кликом",
          bbox and app._tree_row_text(app.tree, bbox[1] + 1) == "T78-a | x | y",
          str(bbox))
    check("р78: клик мимо строк — пусто (уйдёт в меню заголовка)",
          app._tree_row_text(app.tree, 4000) == "")
    # р79: клик на ЗАГОЛОВКЕ — текст колонки; список чатов без скрытых
    app.rows = [{"id": "r79a", "hidden": False},
                {"id": "r79h", "hidden": True}]
    app.rows_by_id = {r["id"]: r for r in app.rows}
    app.tree.delete(*app.tree.get_children(""))
    app.tree.insert("", "end", iid="r79a", values=("V79-a", "p", "t"))
    app.tree.insert("", "end", iid="r79h", values=("V79-hidden", "p", "del"))
    app.tree.update()
    head_y = 4
    check("р79: identify_region на заголовке — heading",
          app.tree.identify_region(30, head_y) == "heading",
          app.tree.identify_region(30, head_y))
    heads80 = app._tree_headings_text(app.tree)
    check("р80: заголовки ВСЕХ колонок через « | »",
          " | " in heads80 and len(heads80.split(" | ")) >= 2,
          heads80)
    list_text = app._chat_list_text()
    check("р79: _chat_list_text — шапка + чаты БЕЗ скрытых",
          "V79-a" in list_text and "V79-hidden" not in list_text
          and list_text.splitlines()[0].count(" | ") >= 2,
          list_text[:200])
    app.tree.delete(*app.tree.get_children(""))
    app.rows, app.rows_by_id = [], {}
    root.withdraw()

    # Детерминированность: не зависим от реального конфига пользователя.
    for fmt in config.FORMATS:
        for key in config.OPTION_KEYS:
            app.opt_vars[fmt][key].set(fmt != "json" if key == "bom" else False)
    app.fmt_vars["md"].set(True)
    app.fmt_vars["txt"].set(True)
    app.fmt_vars["json"].set(False)
    app.single_var.set(False)
    app.show_hidden_var.set(False)
    app.tool_limit_var.set("1000")
    app._update_limit_state()

    # --- р46: стартовый импорт локальной копии (диалоги auto-Да — мок
    # класса в начале main; мастер — реальный автоклава, автопоиск).
    # р82 (фикс): с р76 старт в Zcode и при ЧИСТОЙ _tmp копию AutoClaw
    # никто не создаёт — переключаем режим явно, как радиокнопка ---
    app.mode_var.set("autoclaw")
    app._on_mode_change()
    app._startup_data_check()      # локальной копии нет → вопрос → импорт
    ok = wait_idle(app, 600)       # импорт + автозагрузка списка из копии
    check("р46: локальная копия AutoClaw создана при старте",
          ok and config.local_db_path("autoclaw").is_file(),
          str(config.local_db_path("autoclaw")))

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
              and app.btn_donate.cget("text") == tr("btn_donate"))
        # р77: старое меню статуса удалено — статус переводится целиком
        check(f"язык {lang}: статус переводится (_apply_language)",
              app.status_lbl.cget("text") != "" or app._dbp_note == "",
              app.status_lbl.cget("text"))
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
    # р36: номер версии называет владелец — проверка без конкретного номера
    check("титул содержит версию (раунд 14/19–36)",
          root.title() == f"{BRAND} ver. {app_module.APP_VERSION}"
                          f" - {tr('title_explain')}"
          and bool(app_module.APP_VERSION) and " ver. " in root.title(),
          root.title())
    # --- релиз 1.27 (раунд 22): текст подсказки BOM удалён; виджет-пустышка
    # держит ячейку — блок «SQL база» не сдвинут ---
    check("р44: ячейка пустышки занята кнопкой пресета (под матрицей)",
          not hasattr(app, "hint_bom") and hasattr(app, "btn_as_model")
          and app.btn_as_model.master is app.matrix_labels["bom"].master
          and app.btn_as_model.cget("text") == tr("btn_as_model"),
          app.btn_as_model.cget("text"))
    check("кнопки базы (р46): «Путь к SQL базе»/«Обновить SQL базу», "
          "старые удалены",
          app.btn_output_folder.winfo_exists()
          and app.btn_sql_db.winfo_exists()
          and tr("btn_output_folder") == "Папка экспорта"
          and tr("btn_db") == "Путь к SQL базе"
          and tr("refresh") == "Обновить SQL базу"
          and not hasattr(app, "btn_export_db")
          and not hasattr(app, "btn_db2"))
    check("старые виджеты удалены (Обзор…/надписи/подсказка)",
          not hasattr(app, "btn_browse_output")
          and not hasattr(app, "btn_browse_db")
          and not hasattr(app, "lbl_db") and not hasattr(app, "lbl_output")
          and not hasattr(app, "hint_db"))
    dbe = app.db_entry.grid_info()
    # р49 (я5/я6): поле пути — ПОД кнопкой (левые края совпадают, вся
    # ширина), «Обновить SQL базу» — справа от «Путь к SQL базе»
    brf = app.btn_refresh.grid_info()
    check("р49: поле пути под кнопкой (row=1, colspan 2, ew, тот же фрейм)",
          dbe["row"] == 1 and dbe["column"] == 0
          and dbe["columnspan"] == 2 and dbe["sticky"] == "ew"
          and app.btn_sql_db.master is dbe["in"],
          str(dbe))
    check("р50: «Обновить SQL базу» справа от «Путь к SQL базе», правый край по полю (sticky e)",
          app.btn_sql_db.grid_info()["row"] == 0
          and app.btn_sql_db.grid_info()["column"] == 0
          and brf["row"] == 0 and brf["column"] == 1
          and brf["sticky"] == "e"
          and app.btn_refresh.master is app.btn_sql_db.master,
          str(brf))
    # р51–р54: видимая рамка — 8 зон захвата (р54: 8px везде, кант
    # #e2e2e2; отступы контента 20px — канты не накрывают виджеты)
    handles = getattr(app, "_resize_handles", {})
    n_h = int(handles["n"].place_info()["height"] or 0)
    se_w = int(handles["se"].place_info()["width"] or 0)
    check("р54: рамка окна — 8 зон по 8px, кант #e2e2e2",
          len(handles) == 8
          and str(handles["se"].cget("cursor")) == "bottom_right_corner"
          and str(handles["n"].cget("cursor")) == "top_side"
          and n_h == 8 and se_w == 8
          and str(handles["n"].cget("background")) == "#e2e2e2"
          and handles["se"].winfo_exists(),
          f"n_h={n_h}, se_w={se_w}, "
          f"bg={handles['n'].cget('background') if handles else '-'}")
    # р54: кант не перекрывает элементы GUI — отступы краевых фреймов
    # (top/main/actions, по 20px с р53) больше толщины полосы (8px)
    top_f = app.lbl_search.master            # верхняя строка
    main_f = app.tree.master.master          # таблица → main
    act_f = app.btn_select_all.master        # нижний ряд действий
    tp, mp, ap = (top_f.cget("padding"), main_f.cget("padding"),
                  act_f.cget("padding"))
    check("р54: кант 8px не перекрывает виджеты — отступы краёв ≥ 8px",
          tp[0] >= 8 and tp[1] >= 8 and tp[2] >= 8
          and mp[0] >= 8 and mp[2] >= 8
          and ap[0] >= 8 and ap[1] >= 8,
          f"top={tp}, main={mp}, actions={ap}")
    # р55: нижний ряд — в actions (не у границы отдельным фреймом):
    # прогресс под «Папка экспорта», «Vadim R.M. …» под «Donate»,
    # статус между ними
    pg, sg, site_g = (app.progress.grid_info(),
                      app.status_lbl.grid_info(),
                      app.btn_site.grid_info())
    check("р55: прогресс точно под «Папкой экспорта» (row2/col0, тот же фрейм)",
          pg["row"] == 2 and pg["column"] == 0
          and app.btn_output_folder.grid_info()["row"] == 1
          and app.btn_output_folder.grid_info()["column"] == 0
          and app.progress.master is app.btn_output_folder.master,
          str(pg))
    check("р55: «Vadim R.M. …» точно под «Donate» (row2/col8)",
          site_g["row"] == 2 and site_g["column"] == 8
          and app.btn_donate.grid_info()["row"] == 1
          and app.btn_donate.grid_info()["column"] == 8
          and app.btn_site.master is app.btn_donate.master,
          str(site_g))
    check("р55: статус-строка между ними (row2, cols1-6, тянется)",
          sg["row"] == 2 and sg["column"] == 1
          and (sg["columnspan"] or 0) >= 6 and sg["sticky"] == "ew",
          str(sg))
    # р53/р55: имитация захвата-перетаскивания за юго-восточный угол —
    # окно обязано увеличиться на дельту (клавиша регресса «не двигает»).
    # р55: motion только НАКАПЛИВАЕТ цель (geometry не дёргается на
    # каждый шаг), отпускание применяет финал сразу.
    # event_generate не доставляет события withdrawn-окну — показываем
    # (deiconify) на время пробы, затем прячем снова
    root.geometry("1000x700+100+100")
    root.deiconify()
    root.update()
    handles["se"].event_generate("<ButtonPress-1>", rootx=1100, rooty=800)
    handles["se"].event_generate("<B1-Motion>", rootx=1150, rooty=850)
    _t = getattr(app, "_resize_target", "") or ""
    check("р55: во время тяги geometry не дёргается (цель накоплена)",
          root.winfo_width() == 1000
          and _t.startswith("1050x750+")   # позиция не меняется (стороны e/s)
          and getattr(app, "_resize_scheduled", False) is True,
          f"target={_t or '-'}")
    for _ in range(5):  # поток событий — цель перезаписывается
        handles["se"].event_generate("<B1-Motion>", rootx=1160, rooty=860)
    handles["se"].event_generate("<ButtonRelease-1>", rootx=1160, rooty=860)
    root.update()
    check("р53: drag за угол меняет размер окна (финал применён)",
          root.winfo_width() == 1060 and root.winfo_height() == 760,
          f"{root.winfo_width()}x{root.winfo_height()}")
    check("р53: после отпускания состояние тянущего сброшено",
          getattr(app, "_resize_state", (None,))[0] == "se"
          and not handles["se"].grab_current()
          and getattr(app, "_resize_target", None) is None
          and getattr(app, "_resize_skip_fit", True) is False,
          f"state={getattr(app, '_resize_state', '-')}")
    root.withdraw()
    root.geometry("1000x700+100+100")  # вернуть, остальное не зависит
    check("р49: поиск сразу за чекбоксом скрытых (col 5/6), кнопки обновления вверху нет",
          app.lbl_search.grid_info()["column"] == 5
          and app.lbl_search.grid_info()["sticky"] == "w"
          and app.search_entry.grid_info()["column"] == 6
          and app.search_entry.master is app.lbl_search.master,
          str(app.lbl_search.grid_info()))
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
    # --- раунд 23: внешний языковой файл читается при переключении ---
    (TMP / "lang_en.cfg").write_text(json.dumps({"refresh": "Test-override"}),
                                     encoding="utf-8-sig")
    app.lang_var.set("en")
    app._on_lang_change()
    check("внешний lang_en.cfg перекрывает подпись кнопки (р23)",
          app.btn_refresh.cget("text") == "Test-override",
          app.btn_refresh.cget("text"))
    (TMP / "lang_en.cfg").unlink()
    app.lang_var.set("en")
    app._on_lang_change()
    check("файл удалён → встроенные строки возвращаются",
          app.btn_refresh.cget("text") == tr("refresh"),
          app.btn_refresh.cget("text"))
    app.lang_var.set("ru")
    app._on_lang_change()
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
    # р82 (фикс): стартовый режим фиксируем при создании App — ниже по
    # ходу теста р46 переключает режим для импорта AutoClaw
    check("р76: первый запуск — режим Zcode (дефолт last_mode)",
          first_mode == "zcode",
          first_mode)
    check("р76: Zcode Chats — радиобокс первый (слева)",
          int(app.radio_zcode.grid_info()["column"])
          < int(app.radio_autoclaw.grid_info()["column"]),
          (app.radio_zcode.grid_info()["column"],
           app.radio_autoclaw.grid_info()["column"]))
    check("db_profiles загружены (заводские)",
          app.db_profiles == db_profiles.DEFAULT_PROFILES)
    check("db_profiles.cfg существует рядом (в изолированной папке теста)",
          (TMP / "db_profiles.cfg").is_file())
    # р72: сценарий самотеста — файла НЕ было → note dbp_missing (ушёл
    # в жёлтые заметки, проверено блоком р72 выше)
    check("db_profiles_note = dbp_missing (файл создан при старте)",
          app.db_profiles_note == "dbp_missing", str(app.db_profiles_note))

    # --- р46: база в задании списка — ЛОКАЛЬНАЯ копия ---
    local_db = config.local_db_path(app._mode)  # р76: старт zcode
    list_job = app._list_job()
    check("задание списка получает ЛОКАЛЬНУЮ копию (р46)",
          list_job["kind"] == "list" and list_job["mode"] == app._mode
          and list_job["db"] == str(local_db), str(list_job))
    # р82 (фикс): грузим список ЯВНО — выше по тесту импорт старта мог
    # быть отменён переключением режима, и статус остался с нотой
    app.refresh_list()
    ok_list82 = wait_idle(app, 300)
    check("р46: статус содержит «копия от»",
          ok_list82 and "копия от" in app.status_lbl.cget("text"),
          app.status_lbl.cget("text"))
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
    check("подписи: «Обновить SQL базу» и «Поиск чата:» (ru, р46)",
          tr("refresh") == "Обновить SQL базу" and tr("search") == "Поиск чата:",
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
    check("Чат ↑ → Абрикос,Банан,Вишня",
          [app.tree.item(i, "values")[2] for i in app.tree.get_children()]
          == ["Абрикос", "Банан", "Вишня"])
    app._on_heading_click("requests")
    check("Число ↓ → 3,2,1 (р37: values[4] — «Число» за новой «Тип»)",
          [int(app.tree.item(i, "values")[4]) for i in app.tree.get_children()]
          == [3, 2, 1])

    # --- р48: сортировка по «Тип» (А→Я; одинаковый тип — «Обновлён» ↓) ---
    print("Сортировка по «Тип» (р48)")
    trows = [
        {"id": "td1", "title": "д1", "type": "del",
         "updated_at": "2026-01-01T10:00:00Z", "created_at": "",
         "updated_local": "01.01.2026 13:00", "created_local": "",
         "requests": 1},
        {"id": "ta1", "title": "а1", "type": "arch",
         "updated_at": "2026-01-02T10:00:00Z", "created_at": "",
         "updated_local": "02.01.2026 13:00", "created_local": "",
         "requests": 1},
        {"id": "tn1", "title": "б1", "type": "",
         "updated_at": "2026-01-03T10:00:00Z", "created_at": "",
         "updated_local": "03.01.2026 13:00", "created_local": "",
         "requests": 1},
        {"id": "ta2", "title": "а2", "type": "arch",
         "updated_at": "2026-01-05T10:00:00Z", "created_at": "",
         "updated_local": "05.01.2026 13:00", "created_local": "",
         "requests": 1},
        {"id": "td2", "title": "д2", "type": "del",
         "updated_at": "2026-01-04T10:00:00Z", "created_at": "",
         "updated_local": "04.01.2026 13:00", "created_local": "",
         "requests": 1},
    ]
    app.rows = trows
    app.rows_by_id = {r["id"]: r for r in trows}
    app.checked.clear()
    app._on_heading_click("type")   # первый клик: А→Я, пустое — ПОСЛЕДНЕЕ (р49)
    check("р49: «Тип» ↑ — arch, del… по алфавиту, обычные ПОСЛЕДНИЕ; внутри типа «Обновлён» ↓",
          list(app.tree.get_children()) == ["ta2", "ta1", "td2", "td1", "tn1"],
          str(list(app.tree.get_children())))
    app._on_heading_click("type")   # второй клик: пустое первым, далее обратно
    check("р49: «Тип» ↓ — обычные первыми, далее по убыванию",
          list(app.tree.get_children()) == ["tn1", "td1", "td2", "ta1", "ta2"],
          str(list(app.tree.get_children())))
    app._sort_col, app._sort_desc = "updated", True  # вернуть по умолчанию

    # --- раунд 24: группировка по проектам ---
    print("Группировка по проектам (р24)")
    prows = [
        {"id": "px", "project": "Альфа", "title": "X",
         "updated_at": "2026-01-05T10:00:00Z", "created_at": "2026-01-01T10:00:00Z",
         "updated_local": "05.01.2026 13:00", "created_local": "01.01.2026 13:00",
         "requests": 1},
        {"id": "py", "project": "Альфа", "title": "Y",
         "updated_at": "2026-01-02T10:00:00Z", "created_at": "2026-01-01T10:00:00Z",
         "updated_local": "02.01.2026 13:00", "created_local": "01.01.2026 13:00",
         "requests": 2},
        {"id": "pz", "project": "Бета", "title": "Z",
         "updated_at": "2026-01-04T10:00:00Z", "created_at": "2026-01-01T10:00:00Z",
         "updated_local": "04.01.2026 13:00", "created_local": "01.01.2026 13:00",
         "requests": 3},
        {"id": "pa", "title": "A", "updated_at": "2026-01-03T10:00:00Z",
         "created_at": "2026-01-01T10:00:00Z", "updated_local": "03.01.2026 13:00",
         "created_local": "01.01.2026 13:00", "requests": 4},
    ]
    app.rows = prows
    app._sort_col, app._sort_desc = "updated", True
    app._apply_filter()
    order = list(app.tree.get_children())
    check("р24: updated ↓ — проекты подряд, топовый передаёт параметры",
          order == ["px", "py", "pz", "pa"], str(order))
    check("р36: имя проекта на верхней строке, далее «++», одиночный — пусто",
          [app.tree.item(i, "values")[1] for i in order]
          == ["Альфа", "•", "Бета", ""],
          str([app.tree.item(i, "values")[1] for i in order]))
    app._sort_col, app._sort_desc = "updated", False
    app._apply_filter()
    order = list(app.tree.get_children())
    check("р24: updated ↑ — топовым стал Y, группы перепорядочились",
          order == ["py", "px", "pa", "pz"], str(order))
    check("р24: ↑ — Y показал имя Альфы, X — «++»",
          [app.tree.item(i, "values")[1] for i in order]
          == ["Альфа", "•", "", "Бета"],
          str([app.tree.item(i, "values")[1] for i in order]))

    # --- раунд 28: сортировка по графе «Проект» ---
    p2rows = [
        {"id": "ax", "project": "Альфа", "title": "X",
         "updated_at": "2026-01-05T10:00:00Z", "created_at": "2026-01-01T10:00:00Z",
         "updated_local": "05.01.2026 13:00", "created_local": "01.01.2026 13:00",
         "requests": 1},
        {"id": "ay", "project": "Альфа", "title": "Y",
         "updated_at": "2026-01-02T10:00:00Z", "created_at": "2026-01-01T10:00:00Z",
         "updated_local": "02.01.2026 13:00", "created_local": "01.01.2026 13:00",
         "requests": 2},
        {"id": "bz", "project": "Бета", "title": "Z",
         "updated_at": "2026-01-04T10:00:00Z", "created_at": "2026-01-01T10:00:00Z",
         "updated_local": "04.01.2026 13:00", "created_local": "01.01.2026 13:00",
         "requests": 3},
        {"id": "sa", "title": "A", "updated_at": "2026-01-03T10:00:00Z",
         "created_at": "2026-01-01T10:00:00Z", "updated_local": "03.01.2026 13:00",
         "created_local": "01.01.2026 13:00", "requests": 4},
        {"id": "sb", "title": "B", "updated_at": "2026-01-01T10:00:00Z",
         "created_at": "2026-01-01T10:00:00Z", "updated_local": "01.01.2026 13:00",
         "created_local": "01.01.2026 13:00", "requests": 5},
    ]
    app.rows = p2rows
    app._on_heading_click("project")  # первый клик → А→Я
    order = list(app.tree.get_children())
    check("р28: Проект ↑ — одиночные первыми, проекты А→Я",
          order == ["sa", "sb", "ax", "ay", "bz"], str(order))
    check("р28: Проект ↑ — имена/++ на местах",
          [app.tree.item(i, "values")[1] for i in order]
          == ["", "", "Альфа", "•", "Бета"],
          str([app.tree.item(i, "values")[1] for i in order]))
    check("р28: Проект ↑ — внутри Альфы чаты по названию",
          [app.tree.item(i, "values")[2] for i in order][2:4] == ["X", "Y"],
          str([app.tree.item(i, "values")[2] for i in order]))
    app._on_heading_click("project")  # второй клик → Я→А
    order = list(app.tree.get_children())
    check("р28: Проект ↓ — проекты Я→А, одиночные в конце",
          order == ["bz", "ay", "ax", "sb", "sa"], str(order))
    check("р28: Проект ↓ — стрелка на заголовке ↓",
          app.tree.heading("project")["text"].endswith("↓"))
    app._sort_col, app._sort_desc = "updated", True
    app._apply_filter()
    # вернуть строки a,b,c и сортировку «Число ↓» — так, как было до блока
    # (дальнейшие секции ☑/фильтр ждут эти строки в дереве)
    app.rows = rows
    app._sort_col, app._sort_desc = "requests", True
    app._apply_filter()

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

    # --- раунды 26/37: чекбокс «Показывать скрытые чаты» ---
    subrow = {"id": "sub1", "hidden": True, "type": "wfchld",
              "title": "workflow subagent actor#1@1",
              "updated_at": "2026-01-06T10:00:00Z", "created_at": "2026-01-01T10:00:00Z",
              "updated_local": "06.01.2026 13:00", "created_local": "01.01.2026 13:00",
              "requests": 1}
    app.rows = rows + [subrow]
    app._apply_filter()
    check("р37: скрытый чат по умолчанию невидим", "sub1" not in app.visible_ids)
    app.show_hidden_var.set(True)
    app._apply_filter()
    check("р37: чекбокс показывает скрытый чат", "sub1" in app.visible_ids)
    check("р37: графа «Тип» = wfchld у скрытого",
          app.tree.item("sub1", "values")[3] == "wfchld",
          str(app.tree.item("sub1", "values")[3]))
    check("р26/37: пометка «++»/имя проекта у скрытого корректна",
          app.tree.item("sub1", "values")[1] == "",
          str(app.tree.item("sub1", "values")[1]))
    check("р36/37: фон строки скрытого светло-серый (тег svc)",
          "svc" in app.tree.item("sub1", "tags")
          and str(app.tree.tag_configure("svc")["background"]) == "#e8e8e8",
          str(app.tree.item("sub1", "tags")))
    check("р37: счётчик с чекбоксом = все (N+M одним числом)",
          app._chat_count() == len(app.rows), str(app._chat_count()))
    app.show_hidden_var.set(False)
    app._apply_filter()
    check("р37: снова скрыт", "sub1" not in app.visible_ids)
    check("р37: счётчик без чекбокса — только обычные",
          app._chat_count() == len(rows), str(app._chat_count()))

    # --- р43: «Ток», пресет «как видит модель» ---
    check("р43: _fmt_tokens сокращает",
          app_module._fmt_tokens(911520) == "912K"
          and app_module._fmt_tokens(234567) == "235K"
          and app_module._fmt_tokens(1500000) == "1.5M"
          and app_module._fmt_tokens(999) == "999"
          and app_module._fmt_tokens(None) == "",
          f"{app_module._fmt_tokens(911520)},"
          f"{app_module._fmt_tokens(234567)}")
    check("р43: контекстный чекбокс по умолчанию выкл",
          app._options_for("md")["context_view"] is False,
          str(app._options_for("md")))
    app.mode_var.set("zcode")
    app.opt_vars["md"]["ctx"].set(True)
    check("р43: context_view=True в ZCode при вкл. ряде",
          app._options_for("md")["context_view"] is True, "")
    app.mode_var.set("autoclaw")
    check("р43: context_view=False в AutoClaw (ряд скрыт)",
          app._options_for("md")["context_view"] is False, "")
    app.opt_vars["md"]["ctx"].set(False)
    # invoke() на disabled-кнопке — no-op: дождаться простоя фоновых заданий
    for _ in range(200):
        if not app.runner.busy():
            break
        wait_idle(app, 25)
    app.btn_as_model.invoke()
    check("р43: пресет выставил матрицу (ctx/tools вкл, narration выкл)",
          all(app.opt_vars[f]["ctx"].get() and app.opt_vars[f]["tools"].get()
              and not app.opt_vars[f]["narration"].get()
              for f in ("md", "txt", "json")),
          str({f: dict(app.opt_vars[f]) for f in ("md",)}))
    check("р43/р82: статус пресета",
          "актуальный контекст" in app.status_lbl.cget("text"),
          app.status_lbl.cget("text"))
    for f in ("md", "txt", "json"):
        app.opt_vars[f]["ctx"].set(False)
        app.opt_vars[f]["tools"].set(False)

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

    # --- р81: no_files удалён; папка экспорта; копирование без выделения ---
    print("р81: no_files удалён; некорректная папка; копирование поля")
    check("р81 (п.4): строк no_files в матрице нет",
          {key for key, _i18n in app_module.MATRIX_ROWS}
          == {"tools", "narration", "all_files", "bom", "ctx"}
          and all("no_files" not in app.opt_vars[f] for f in ("md", "txt", "json")))
    old_out = app.output_var.get()
    app.last_file = None
    app.output_var.set(r"C:\__нет_такой_папки__")
    app._open_folder()
    check("р81 (п.5): несуществующая папка → статус, ничего не открыто",
          app.status_lbl.cget("text") == tr("msg_bad_outdir")
          and app_module.ERROR_FG in str(app.status_lbl.cget("foreground")),
          app.status_lbl.cget("text"))
    app.output_var.set(old_out)

    entry81 = tk.Entry(app.root)
    entry81.insert(0, "ABCDEF")
    entry81.selection_clear()
    app._entry_copy_cut(entry81, False)
    check("р81 (п.6): копирование без выделения — весь текст",
          root.clipboard_get() == "ABCDEF", root.clipboard_get())
    entry81.selection_range(2, 4)
    app._entry_copy_cut(entry81, False)
    check("р81 (п.6): копирование с выделением — только оно",
          root.clipboard_get() == "CD", root.clipboard_get())
    entry81.selection_clear()
    app._entry_copy_cut(entry81, True)
    check("р81 (п.6): вырезание без выделения — весь текст, поле пусто",
          root.clipboard_get() == "ABCDEF" and entry81.get() == "",
          f"{root.clipboard_get()!r}, поле={entry81.get()!r}")
    entry81.destroy()

    # --- р82: новые подписи пресета/кнопок; снятие ошибки папки ---
    print("р82: подписи пресета/кнопок; ошибка папки снимается")
    check("р82 (п.1): чекбокс «Только актуальный контекст»",
          tr("row_ctx") == "Только актуальный контекст")
    check("р82 (п.1): кнопка «Пресет: актуальный контекст модели»",
          app.btn_as_model.cget("text") == "Пресет: актуальный контекст модели",
          app.btn_as_model.cget("text"))
    check("р82 (п.2): сайт и Donate",
          app.btn_site.cget("text") == "Vadim R.M. - vmgames.com"
          and app.btn_donate.cget("text") == "Vadim R.M. - Donate",
          f"{app.btn_site.cget('text')!r} / {app.btn_donate.cget('text')!r}")
    good_dir82 = str(TMP)
    real_ask82 = app_module.filedialog.askdirectory
    app_module.filedialog.askdirectory = lambda **_k: good_dir82
    try:
        app._browse_output()
    finally:
        app_module.filedialog.askdirectory = real_ask82
    check("р82 (п.3): выбрана корректная папка → ошибка снята",
          app.output_var.get() == good_dir82
          and app.status_lbl.cget("text") != tr("msg_bad_outdir"),
          f"поле={app.output_var.get()!r}, статус={app.status_lbl.cget('text')!r}")
    app.output_var.set(old_out)

    # --- р83: сверхдлинные строки — обрезка 500 + жёлтая нота ---
    print("р83: длинные строки — обрезка 500 + жёлтая нота")
    lang_path83 = TMP / "lang_ru.cfg"
    backup83 = (lang_path83.read_text(encoding="utf-8-sig")
                if lang_path83.exists() else None)
    lang_path83.write_text(
        json.dumps({"btn_donate": "D" * 600}, ensure_ascii=False),
        encoding="utf-8-sig")
    app.lang_var.set("en")   # смена туда-обратно перечитает lang_ru.cfg
    app._on_lang_change()
    app.lang_var.set("ru")
    app._on_lang_change()
    check("р83: значение lang-файла обрезано до 500",
          len(tr("btn_donate")) == 500, len(tr("btn_donate")))
    check("р83: жёлтая нота «Слишком длинные строки в файле: lang_ru.cfg»",
          "Слишком длинные строки" in app.status_lbl.cget("text")
          and "lang_ru.cfg" in app.status_lbl.cget("text")
          and app_module.WARN_FG in str(app.status_lbl.cget("foreground")),
          app.status_lbl.cget("text"))
    if backup83 is None:
        lang_path83.unlink()
    else:
        lang_path83.write_text(backup83, encoding="utf-8-sig")
    app._on_lang_change()
    check("р83: восстановлено — ноты нет",
          "Слишком длинные строки" not in app.status_lbl.cget("text")
          and tr("btn_donate") == "Vadim R.M. - Donate",
          app.status_lbl.cget("text"))
    app.opt_vars["json"]["tools"].set(True)
    app._update_limit_state()
    check("лимит активен при tools on (json)", app.tool_limit_box.instate(["!disabled"]))
    app.opt_vars["json"]["tools"].set(False)
    app._update_limit_state()

    # --- single-задание (ER-2 + chat_ids раунда 20) ---
    print("single-задание")
    app.mode_var.set("autoclaw")  # р76: стартовый режим теперь zcode;
    app._mode = "autoclaw"        # блок проверяет субпапку AutoClaw
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
    check("single: options — поля ExportOptions (р43: +context_view; "
          "р81: no_files удалён)",
          set(single_job["options"]["md"])
          == {"tools", "narration", "tool_limit", "all_files",
              "bom", "lang", "context_view", "app_version"})

    # --- реальный список AutoClaw ---
    print("Список диалогов (AutoClaw)")
    # р49: список — из ЛОКАЛЬНОЙ копии (архитектура р46; экспорт-задания
    # тоже читают копию — раньше здесь был мастер, списки расходились)
    _ad = adapter_for("autoclaw")
    _con = _ad.open(config.local_db_path("autoclaw"))
    real_rows = _ad.list_chats(_con)
    _ad.close(_con)
    check("движок вернул диалоги", len(real_rows) > 0)
    # р48: для экспорта берём ВИДИМЫЕ чаты (архивные скрыты за чекбоксом)
    vis_rows = [r for r in real_rows if not r.get("hidden")] or real_rows
    app.rows = real_rows
    app.rows_by_id = {r["id"]: r for r in real_rows}
    app.checked.clear()
    app._apply_filter()
    # р48: в списке есть скрытые (архивные) чаты — таблица показывает
    # только видимые (равно visible_ids), скрытые ждут чекбокса
    check("таблица заполнена (р48: только видимые, скрытые за чекбоксом)",
          len(app.tree.get_children()) == len(app.visible_ids)
          == sum(1 for r in real_rows if not r.get("hidden")),
          f"дерево={len(app.tree.get_children())}, "
          f"видимые={len(app.visible_ids)}, всего={len(real_rows)}")
    app._on_list_ready(real_rows)
    check("по умолчанию отмечен первый видимый",
          len(app.checked) == 1 and app.visible_ids[0] in app.checked)
    # подгонка колонок: при ширине таблицы 598 все колонки видимы (Я-новое 2)
    app._fit_columns(598)
    total = sum(app.tree.column(c)["width"]
                for c in ("project", "title", "type", "requests", "tokens",
                          "updated", "created", "check"))
    check("колонки вписаны в 598px (р43: +«Ток»)", total <= 598, f"сумма={total}")
    check("«Чат» = минимум 96 при 598px (р43: +«Ток»)",
          app.tree.column("title")["width"] == 96,
          str(app.tree.column("title")["width"]))
    check("порядок колонок: ☑, Проект, Чат, Тип, Число, Ток, Обновлён, Создан (р43)",
          list(app.tree["columns"])
          == ["check", "project", "title", "type", "requests", "tokens",
              "updated", "created"],
          str(list(app.tree["columns"])))
    wait_idle(app, 60)

    # --- серия экспорта 2×2 ---
    print("Серия экспорта (AutoClaw)")
    TMP_OUT.mkdir(parents=True, exist_ok=True)
    for old in TMP_OUT.iterdir():
        # в _tmp могут остаться субпапки (экспорт SQL-базы раунда 8)
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    app.checked = {vis_rows[0]["id"], vis_rows[1]["id"]}
    app.fmt_vars["md"].set(True)
    app.fmt_vars["txt"].set(True)
    app.fmt_vars["json"].set(False)
    app.output_var.set(str(TMP_OUT))
    app.export_selected()
    check("серия запущена", app._batch is not None)
    ok = wait_idle(app, 180)
    check("серия завершилась", ok and app._batch is None)
    check("файлов 2×2 (md+txt) в «AutoClaw Chats» (субпапка workspace, р25)",
          len(list((TMP_OUT / "AutoClaw Chats").rglob("AC-*.md"))) == 2
          and len(list((TMP_OUT / "AutoClaw Chats").rglob("AC-*.txt"))) == 2)
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

    # --- р46: поле «Путь к SQL базе» хранит путь МАСТЕРА ---
    print("Путь к SQL базе (р46)")
    orig_db = app.db_var.get()
    db_src = TMP / "fake_db.sqlite"
    db_src.write_bytes(b"SQLite format 3 fake")
    Path(str(db_src) + "-wal").write_bytes(b"wal-part")
    app.db_var.set(str(db_src))
    check("источник базы из поля (мастер, р46)",
          app._db_source_path() == db_src)
    app.db_var.set(orig_db)  # вернуть поле как было — дальнейшие секции не меняются

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
    app.checked = {vis_rows[0]["id"], vis_rows[1]["id"]}
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
        check("single: внутри только 2 выбранных диалога (р20/25)",
              len(re.findall(r"^Новый диалог (?:[^\\\r\n]+\\)?AC-.*\.md$",
                             pack_text, re.M)) == 2,
              f"меток: {len(re.findall(r'^Новый диалог (?:[^\\\\\\r\\n]+\\\\)?AC-.*\\.md$', pack_text, re.M))}")
        check("single: заголовок «Выбранные диалоги AutoClaw (2)» (р20)",
              "# Выбранные диалоги AutoClaw (2)" in pack_text)
        check("single: двойной разделитель ---", "---\n---" in pack_text)
        check("single: оба выбранных названия присутствуют",
              (vis_rows[0]["title"] or "") in pack_text
              and (vis_rows[1]["title"] or "") in pack_text)
    app.single_var.set(False)  # дальше — обычная серия (zcode-блок)

    # --- р46: «SQL база 2»/«Экспорт SQL базы» удалены ---
    check("р46: кнопки «SQL база 2»/«Экспорт SQL базы» отсутствуют",
          not hasattr(app, "btn_db2") and not hasattr(app, "db2_entry")
          and not hasattr(app, "btn_export_db"))
    app.mode_var.set("zcode")
    app._on_mode_change()
    ok = wait_idle(app, 600)   # ensure-поток: импорт реального мастера ZCode
    check("р46: локальная копия ZCode создана при переключении режима",
          ok and config.local_db_path("zcode").is_file()
          and config.local_index_path().is_file(),
          f"db={config.local_db_path('zcode').is_file()}, "
          f"idx={config.local_index_path().is_file()}")
    # «Обновить SQL базу»: переимпорт + перезагрузка списка
    # р47 (исправление 1.42b): кнопка обязана ПЕРЕЗИМПОРТИРОВАТЬ копию
    # с мастера (mtime локальной базы меняется), а не перечитывать старую
    mtime_before = config.local_db_path("zcode").stat().st_mtime
    app.btn_refresh.invoke()
    ok = wait_idle(app, 600)
    mtime_after = config.local_db_path("zcode").stat().st_mtime
    check("р47: «Обновить SQL базу» переимпортирует копию (mtime) и "
          "перезагружает («копия от»)",
          ok and mtime_after != mtime_before
          and "копия от" in app.status_lbl.cget("text"),
          f"mtime {mtime_before}→{mtime_after}, "
          f"статус={app.status_lbl.cget('text')!r}")
    # р47: «Путь к SQL базе» — выбор файла мастера запускает импорт сразу
    master_zc = db_profiles.find_db("zcode", app.db_profiles)
    if master_zc:
        real_askopen = app_module.filedialog.askopenfilename
        app_module.filedialog.askopenfilename = (
            lambda *a, **k: str(master_zc))
        m0 = config.local_db_path("zcode").stat().st_mtime
        app.btn_sql_db.invoke()
        ok = wait_idle(app, 600)
        m1 = config.local_db_path("zcode").stat().st_mtime
        app_module.filedialog.askopenfilename = real_askopen
        check("р47: «Путь к SQL базе» — выбор = импорт сразу",
              ok and m1 != m0,
              f"mtime {m0}→{m1}, ok={ok}")
    app.mode_var.set("autoclaw")   # вернуться, как возвращал старый блок
    app._on_mode_change()
    wait_idle(app, 120)

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
    expected_leaf = (app.rows_by_id[zcode_first].get("project") or "")
    ok_leaf = (zc_files[0].parent.name == expected_leaf if expected_leaf
               else zc_files[0].parent == TMP_ZCODE / "ZCode Chats")
    check("zcode: файл в папке проекта — по ИМЕНИ проекта (р30)",
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

    # --- р47 (исправление 1.42b): старт при last_mode=zcode — окно
    # открывается в ZCode и грузит список ZCode. Раньше mode_var всегда
    # был "autoclaw": старт грузил AutoClaw, клик по «Zcode Chats»
    # отбрасывался (new_mode == self._mode), список менялся только
    # по кнопке обновления. Отдельный конфиг-каталог, второй скрытый root.
    print("Старт в last_mode=zcode (р47)")
    tmp2 = TMP / "selftest_zstart"
    tmp2.mkdir(parents=True, exist_ok=True)
    cfg2 = dict(config.DEFAULTS)
    cfg2["last_mode"] = "zcode"
    (tmp2 / "ExportChat.cfg").write_text(
        json.dumps(cfg2, ensure_ascii=False), encoding="utf-8-sig")
    db_profiles.write_factory(tmp2 / "db_profiles.cfg")
    old_env = os.environ.get("EXPORTCHAT_CONFIG_DIR")
    os.environ["EXPORTCHAT_CONFIG_DIR"] = str(tmp2)
    try:
        root2 = tk.Tk()
        root2.withdraw()
        app2 = App(root2, persist_config=False)
        check("р47: last_mode=zcode → радио и режим совпадают при старте",
              app2.mode_var.get() == "zcode" and app2._mode == "zcode",
              f"mode_var={app2.mode_var.get()}, _mode={app2._mode}")
        app2._startup_data_check()   # копии в tmp2 нет → вопрос → импорт
        ok = wait_idle(app2, 600)
        check("р47: старт в zcode грузит список ZCode (не AutoClaw)",
              ok and config.local_db_path("zcode").is_file()
              and len(app2.tree.get_children()) > 0
              and app2.status_lbl.cget("text").startswith("Диалогов:"),
              f"ok={ok}, строк={len(app2.tree.get_children())}, "
              f"статус={app2.status_lbl.cget('text')!r}")
        root2.destroy()
    finally:
        os.environ["EXPORTCHAT_CONFIG_DIR"] = old_env or str(TMP)

    root.destroy()
    print("-" * 60)
    print(f"Итого: PASS={PASS_COUNT}, FAIL={FAIL_COUNT}")
    for line in FAILURES:
        print(f"  провал: {line}")
    return 1 if FAIL_COUNT else 0


if __name__ == "__main__":
    sys.exit(main())
