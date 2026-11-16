# -*- coding: utf-8 -*-
"""Главное окно приложения (Tkinter/ttk, тема «vista»).

Версия 2 (GUI_SPEC_V2 + AGREEMENTS.md):
- брендинг в заголовке; режимы AutoClaw Chats / Zcode Chats (радиокнопки);
- таблица с ☑-колонкой выбора чатов и сортировкой по заголовкам (▲/▼);
- поформатная матрица опций (MD/TXT/JSON) + общее поле «Максимальная длина, литер»;
- серия экспорта «выбранные чаты × отмеченные форматы» с прогрессом «k из N»;
- «Экспортировать всё в один файл» — заглушка до обновления движка (ER-2);
- кнопка сайта автора; папка вывода внизу, рядом с «Открыть папку вывода».

Раунды 7–11 (v4.2–v4.6): надпись «SQL база:» едина для обоих режимов; кнопки
«Экспорт SQL базы» (копия db+wal+shm, SQLite GUI не читает) и «Donate» —
столбиком над нижним «Обзор…» (в пустом углу панели; вниз под ним места нет —
строка действий), «Обзор…» — в строке «Папка вывода» как в v4.1, вся колонка
на 5px левее (place x=-5); имя движка в статусе не печатается; копии баз —
в субпапки «AutoClaw SQL» / «ZCode SQL» папки вывода.

Все обращения к движкам — in-process через job_runner (раунд 19: один exe,
адаптеры backend/ вместо внешнего процесса engine exe); из фонового потока
Tk не трогается: события идут через очередь и _poll().
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import config
import db_profiles
import i18n
import job_runner as jr
from config import FORMATS
from i18n import tr

BRAND = "Z.ai Chats Exporter by Vadim R.M."
# Раунд 19–22: версия = номер релизного коммита (без RC с релиза 1.27);
# обновляется вручную при выпуске сборки.
APP_VERSION = "1.27"
SITE_URL = "https://www.vmgames.com/"
DONATE_URL = "https://www.paypal.me/vmgames/5"
DEFAULT_TOOL_LIMIT = 1000
ERROR_FG = "#b00020"
OK_FG = "#0a7a0a"
GRAY_FG = "#777777"
CHECK_ON = "☑"
CHECK_OFF = "☐"
_GEOMETRY_RE = re.compile(r"^\d+x\d+\+\-?\d+\+\-?\d+$")

# колонки таблицы: (имя, ключ i18n или None для служебной)
COLUMNS = (("check", None), ("title", "col_title"), ("updated", "col_updated"),
           ("created", "col_created"), ("requests", "col_requests"))
SORTABLE = ("title", "updated", "created", "requests")
MATRIX_ROWS = (("tools", "row_tools"), ("narration", "row_narration"),
               ("all_files", "row_all_files"), ("no_files", "row_no_files"),
               ("bom", "row_bom"))
# Субпапки для копий SQL-баз в папке вывода (раунд 8; имена заданы владельцем).
SQL_SUBDIRS = {"autoclaw": "AutoClaw SQL", "zcode": "ZCode SQL"}
# Субпапки экспорта чатов (раунд 13): папка вывода — общая материнская.
CHAT_SUBDIRS = {"autoclaw": "AutoClaw Chats", "zcode": "ZCode Chats"}


def _ui_width(text: str) -> int:
    """Текстовая ширина для формул кнопок: CJK-глифы считаются двойными
    (раунд 21: иначе кнопки на китайском обрезаются — ширина Tk считается
    по средней ширине латиницы, а китайский глиф вдвое шире)."""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


def copy_db_files(src: Path, dst: Path) -> list[Path]:
    """Копия SQL-базы (раунд 7): главный файл + -wal/-shm, если есть.

    Файлы копируются как есть (shutil.copy2), без чтения SQLite из GUI —
    та же процедура переноса, что в ACCEPTANCE.md (проверка на 8.1) и в
    движке ZCode при блокировке базы.
    """
    shutil.copy2(src, dst)
    copied = [src]
    for suffix in ("-wal", "-shm"):
        side = Path(str(src) + suffix)
        if side.is_file():
            shutil.copy2(side, Path(str(dst) + suffix))
            copied.append(side)
    return copied


class App:
    def __init__(self, root: tk.Tk, persist_config: bool = True) -> None:
        self.root = root
        self.persist_config = persist_config
        self.cfg = config.load()
        i18n.set_lang(self.cfg.get("lang", "ru"))
        # Раунд 19 (дополнение): пути баз — из отдельного db_profiles.cfg рядом
        # с exe (лежит в поставке); если файла не было/он битый — программа
        # записала заводской и сообщит об этом предупреждением.
        self.db_profiles, self.db_profiles_note = db_profiles.load()
        if self.db_profiles_note:
            self.root.after(400, lambda: messagebox.showwarning(
                BRAND, tr(self.db_profiles_note), parent=self.root))
        self.runner = jr.JobRunner()
        self._mode = "autoclaw"
        self._mode_state: dict[str, dict] = {}
        self.rows: list[dict] = []
        self.rows_by_id: dict[str, dict] = {}
        self.checked: set[str] = set()
        self.visible_ids: list[str] = []
        self.last_file: Path | None = None
        self._batch: dict | None = None
        self._sort_col = "updated"
        self._sort_desc = True

        self.mode_var = tk.StringVar(value="autoclaw")
        self.lang_var = tk.StringVar(value=i18n.current_lang())
        self.search_var = tk.StringVar()
        self.fmt_vars = {fmt: tk.BooleanVar(value=fmt in self.cfg.get("export_formats", ["md", "txt"]))
                         for fmt in FORMATS}
        self.opt_vars = {fmt: {key: tk.BooleanVar(value=bool(self.cfg["options"][fmt][key]))
                               for key in config.OPTION_KEYS}
                         for fmt in FORMATS}
        self.tool_limit_var = tk.StringVar(
            value=str(self.cfg.get("tool_limit", DEFAULT_TOOL_LIMIT)))
        # Раунд 20: чекбокс «Экспорт в один файл» вместо кнопки «…всё в один
        # файл» — пакует в один файл ВЫБРАННЫЕ чаты («Выбрать всё» = прежнее).
        self.single_var = tk.BooleanVar(value=bool(self.cfg.get("single_file", False)))
        self.output_var = tk.StringVar(value=self.cfg.get("output_dir", ""))
        # Раунд 16: папка экспорта НИКОГДА не пуста — при первом запуске
        # (без config.json) сразу заполняется папкой exe; иначе «Открыть
        # папку экспорта» на 8.1 открывала «Документы» (выбор Windows).
        if not self.output_var.get().strip():
            self.output_var.set(str(config.default_output_dir()))
        self.db_var = tk.StringVar(value=self.cfg.get("db_path", ""))
        # Раунд 17: поле базы тоже заполняется при старте (раунд 17)
        self._autofill_db_var()

        self._build()
        self._apply_language()
        self._update_headings()
        self._update_limit_state()
        self._restore_geometry()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll)
        self.root.after(250, self.refresh_list)
        self.search_var.trace_add("write", lambda *_: self._apply_filter())
        # Раунд 16: config.json создаётся при ПЕРВОМ старте (не при первом
        # изменении) — на 8.1 первый запуск полностью детерминирован
        if self.persist_config:
            self._persist()

    # ------------------------------------------------------------------ UI

    def _build(self) -> None:
        try:
            ttk.Style().theme_use("vista")
        except tk.TclError:
            pass
        self.root.minsize(940, 560)

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        # --- верхняя строка: режимы, язык, поиск, обновить ---
        top = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        top.grid(row=0, column=0, sticky="ew")

        self.radio_autoclaw = ttk.Radiobutton(
            top, value="autoclaw", variable=self.mode_var, text="AutoClaw Chats",
            command=self._on_mode_change)
        self.radio_autoclaw.grid(row=0, column=0, sticky="w")
        self.radio_zcode = ttk.Radiobutton(
            top, value="zcode", variable=self.mode_var, text="Zcode Chats",
            command=self._on_mode_change)
        self.radio_zcode.grid(row=0, column=1, sticky="w", padx=(4, 14))

        self.lbl_lang = ttk.Label(top)
        self.lbl_lang.grid(row=0, column=2, sticky="w")
        self.lang_box = ttk.Combobox(top, textvariable=self.lang_var,
                                     values=list(i18n.LANGS), state="readonly", width=5)
        self.lang_box.grid(row=0, column=3, sticky="w", padx=(4, 16))
        self.lang_box.bind("<<ComboboxSelected>>", self._on_lang_change)

        top.columnconfigure(4, weight=1)
        self.lbl_search = ttk.Label(top)
        self.lbl_search.grid(row=0, column=4, sticky="e")
        self.search_entry = ttk.Entry(top, textvariable=self.search_var, width=30)
        self.search_entry.grid(row=0, column=5, sticky="w", padx=(4, 12))
        self.btn_refresh = ttk.Button(top, command=self.refresh_list)
        self.btn_refresh.grid(row=0, column=6, sticky="e")

        # --- таблица + матрица опций ---
        main = ttk.Frame(self.root, padding=(8, 0, 8, 0))
        main.grid(row=1, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)

        table_frame = ttk.Frame(main)
        table_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(1, weight=1)

        self.tree = ttk.Treeview(
            table_frame,
            columns=[name for name, _key in COLUMNS],
            show="headings", selectmode="browse")
        self.tree.grid(row=0, column=1, sticky="nsew")
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=2, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.column("check", width=36, minwidth=36, anchor="center", stretch=False)
        self.tree.column("title", width=340, stretch=True)
        self.tree.column("updated", width=120, anchor="center", stretch=False)
        self.tree.column("created", width=120, anchor="center", stretch=False)
        self.tree.column("requests", width=80, anchor="e", stretch=False)
        for name, _key in COLUMNS:
            if name in SORTABLE:
                self.tree.heading(name, command=lambda c=name: self._on_heading_click(c))
        self.tree.bind("<Button-1>", self._on_tree_click)
        # Подгонка ширины «Названия», чтобы «Запросов» не уходила за границу.
        self.tree.bind("<Configure>", lambda *_e: self._fit_columns())

        # Правая панель: постоянная ширина (все дети фиксированной ширины —
        # не зависит от режима/языка, AGREEMENTS раунд 6); матрица опций
        # и строка базы в отдельных фреймах — поле базы не распирает столбцы.
        right = ttk.Frame(main)
        right.grid(row=0, column=2, sticky="nsew")
        right.columnconfigure(0, weight=1)

        opts = ttk.LabelFrame(right, padding=(8, 6))
        opts.grid(row=0, column=0, sticky="new")
        opts.columnconfigure(0, minsize=210, weight=1)
        opts.columnconfigure(1, uniform="fmt")
        opts.columnconfigure(2, uniform="fmt")
        opts.columnconfigure(3, uniform="fmt")

        self.matrix_headers: dict[str, ttk.Label] = {}
        for index, fmt in enumerate(FORMATS, start=1):
            label = ttk.Label(opts, text=fmt.upper(), font=("Segoe UI", 7, "bold"))
            label.grid(row=0, column=index, sticky="e", padx=(3, 3), pady=(0, 4))
            self.matrix_headers[fmt] = label

        self.matrix_labels: dict[str, ttk.Label] = {}
        self.matrix_checks: dict[tuple[str, str], ttk.Checkbutton] = {}
        row_index = 1
        for key, i18n_key in MATRIX_ROWS:
            label = ttk.Label(opts, wraplength=200)
            label.grid(row=row_index, column=0, sticky="w", pady=2)
            self.matrix_labels[key] = label
            for col_index, fmt in enumerate(FORMATS, start=1):
                var = self.opt_vars[fmt][key]
                if key == "bom" and fmt == "json":
                    var.set(False)
                    widget = ttk.Checkbutton(opts, variable=var, state="disabled")
                else:
                    command = (self._update_limit_state if key == "tools"
                               else self._persist)
                    widget = ttk.Checkbutton(opts, variable=var, command=command)
                # sticky="e": правые края чекбоксов на одной линии, зазор ~9px
                # («1 2 3», Я1); край поля лимита = край чекбокса (Я2).
                widget.grid(row=row_index, column=col_index, sticky="e",
                            padx=(3, 3), pady=2)
                self.matrix_checks[(key, fmt)] = widget
            if key == "tools":
                row_index += 1
                self.lbl_tool_limit = ttk.Label(opts)
                self.lbl_tool_limit.grid(row=row_index, column=0, sticky="w", pady=2)
                self.tool_limit_box = ttk.Spinbox(opts, textvariable=self.tool_limit_var,
                                                  from_=0, to=1000000, increment=100,
                                                  width=6)
                self.tool_limit_box.grid(row=row_index, column=1, columnspan=3,
                                         sticky="ew", padx=(7, 3), pady=2)
                self.tool_limit_box.bind("<FocusOut>", self._normalize_limit)
            row_index += 1

        # Релиз 1.27 (раунд 22): текст подсказки удалён по требованию
        # владельца; виджет-пустышка оставлен на своей ячейке, чтобы НИ
        # один элемент (блок «SQL база» ниже) не сдвинулся.
        self.hint_bom = ttk.Label(opts, text="", foreground=GRAY_FG,
                                  wraplength=290)
        self.hint_bom.grid(row=row_index, column=0, columnspan=4, sticky="w",
                           pady=(6, 0))

        # Строка базы (раунд 14): кнопка «SQL база» (выбор файла базы) +
        # поле пути до правого края панели; ПОД полем — кнопка
        # «Экспорт SQL базы» (на месте прежней подсказки «пусто —
        # авто-поиск»). Плавающая колонка кнопок упразднена (раунды 8–13).
        dbf = ttk.Frame(right, padding=(8, 12, 8, 2))
        dbf.grid(row=1, column=0, sticky="ew")

        self.btn_sql_db = ttk.Button(dbf, command=self._browse_db)
        self.btn_sql_db.grid(row=0, column=0, sticky="w")
        self.db_entry = ttk.Entry(dbf, textvariable=self.db_var, width=20)
        self.db_entry.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.btn_export_db = ttk.Button(dbf, command=self._export_db)
        self.btn_export_db.grid(row=1, column=1, sticky="w", pady=(6, 0))
        dbf.columnconfigure(1, weight=1)

        # --- строка действий (раунд 17): ОДИН фрейм на оба нижних ряда,
        # без пустых ячеек: ряд 0 — «Выбрать всё»/«Снять выбор»/«Формат»/
        # «Экспортировать выбранные чаты» + «Открыть папку экспорта» в том
        # же ряду; ряд 1 — «Папка экспорта»+поле (заполняют слот слева),
        # «Экспортировать всё в один файл» + «Donate» справа. Кнопка
        # «Экспортировать выбранные чаты» стоит на одной линии с «Открыть
        # папку экспорта» (требование владельца, раунд 17) ---
        actions = ttk.Frame(self.root, padding=(8, 6))
        actions.grid(row=2, column=0, sticky="ew")
        self.btn_select_all = ttk.Button(actions, command=self._select_all_visible)
        self.btn_select_all.grid(row=0, column=0, sticky="w")
        self.btn_clear_all = ttk.Button(actions, command=self._clear_all_visible)
        self.btn_clear_all.grid(row=0, column=1, sticky="w", padx=(6, 16))

        self.lbl_format = ttk.Label(actions)
        self.lbl_format.grid(row=0, column=2, sticky="w")
        self.fmt_checks: dict[str, ttk.Checkbutton] = {}
        for col_index, fmt in enumerate(FORMATS, start=3):
            widget = ttk.Checkbutton(actions, variable=self.fmt_vars[fmt],
                                     text=fmt.upper(), command=self._persist)
            widget.grid(row=0, column=col_index, sticky="w", padx=(6, 6))
            self.fmt_checks[fmt] = widget

        self.btn_export_selected = ttk.Button(actions, command=self.export_selected)
        self.btn_export_selected.grid(row=0, column=6, sticky="w", padx=(16, 0))
        actions.columnconfigure(7, weight=1)
        self.btn_open_folder = ttk.Button(actions, command=self._open_folder)
        self.btn_open_folder.grid(row=0, column=8, sticky="e")

        self.btn_output_folder = ttk.Button(actions, command=self._browse_output)
        self.btn_output_folder.grid(row=1, column=0, sticky="w")
        self.output_entry = ttk.Entry(actions, textvariable=self.output_var)
        self.output_entry.grid(row=1, column=1, columnspan=5, sticky="ew",
                               padx=(4, 0))
        actions.columnconfigure(5, weight=1)
        # Раунд 20: чекбокс на месте прежней кнопки «…всё в один файл»:
        # включён — «Экспортировать выбранные чаты» пакует ВЫБРАННЫЕ чаты
        # в один файл каждого формата; выключен — каждый чат в свой файл.
        self.chk_single = ttk.Checkbutton(actions, variable=self.single_var,
                                          command=self._persist)
        self.chk_single.grid(row=1, column=6, sticky="w", padx=(16, 0))
        self.btn_donate = ttk.Button(actions,
                                     command=lambda: webbrowser.open(DONATE_URL))
        self.btn_donate.grid(row=1, column=8, sticky="e", pady=(0, 0))

        # --- статус: прогресс, текст, сайт автора ---
        status = ttk.Frame(self.root, padding=(8, 2, 8, 8))
        status.grid(row=3, column=0, sticky="ew")
        status.columnconfigure(1, weight=1)
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=130)
        self.progress.grid(row=0, column=0, sticky="w")
        self.status_lbl = ttk.Label(status, anchor="w")
        self.status_lbl.grid(row=0, column=1, sticky="ew", padx=8)
        self.btn_site = ttk.Button(status, command=lambda: webbrowser.open(SITE_URL))
        self.btn_site.grid(row=0, column=2, sticky="e")
        # Раунды 12–14: текст статуса (ошибки движка) и заголовок окна
        # копируются — Ctrl+C по окну или правый клик по строке статуса.
        # Если фокус в поле ввода с выделением — Ctrl+C работает по
        # назначению (копируется выделение).
        self.status_menu = tk.Menu(self.root, tearoff=0)
        self.status_menu.add_command(label=tr("copy"), command=self._copy_status)
        self.status_menu.add_command(label=tr("copy_title"),
                                     command=self._copy_title)
        self.status_lbl.bind("<Button-3>",
                             lambda e: self.status_menu.tk_popup(e.x_root, e.y_root))
        self.root.bind("<Control-c>", self._copy_status)
        self.root.bind("<Control-C>", self._copy_status)

        self._busy_widgets = [self.btn_refresh, self.btn_select_all, self.btn_clear_all,
                              self.btn_export_selected, self.tool_limit_box,
                              self.search_entry, self.db_entry, self.btn_sql_db,
                              self.btn_output_folder, self.btn_export_db,
                              self.chk_single]
        self._busy_widgets += list(self.fmt_checks.values())
        self._busy_widgets += list(self.matrix_checks.values())
        # Я3/AGREEMENTS раунд 2 №3: JSON BOM всегда серый — исключаем из «оживляемых»
        self._busy_widgets.remove(self.matrix_checks[("bom", "json")])

    def _fit_columns(self, width: int | None = None) -> None:
        """Ширина «Названия» = остаток ширины таблицы после фиксированных
        колонок — все колонки видимы и при старте, и при изменении размера."""
        if width is None:
            width = self.tree.winfo_width()
        if width <= 1:
            return  # окно ещё не отрисовано
        fixed = sum(self.tree.column(c)["width"]
                    for c in ("check", "updated", "created", "requests"))
        title = max(120, width - fixed - 6)
        self.tree.column("title", width=title, minwidth=120, stretch=True)

    def _apply_language(self) -> None:
        self.root.title(f"{BRAND} ver. {APP_VERSION} - {tr('title_explain')}")
        self.lbl_lang.config(text=tr("lang_label"))
        self.lbl_search.config(text=tr("search"))
        self.btn_refresh.config(text=tr("refresh"))
        for name, key in COLUMNS:
            if key:
                self.tree.heading(name, text=tr(key))
        self._update_headings()
        self.lbl_format.config(text=tr("lbl_format"))
        for key, i18n_key in MATRIX_ROWS:
            self.matrix_labels[key].config(text=tr(i18n_key))
        self.lbl_tool_limit.config(text=tr("lbl_tool_limit"))
        self.btn_output_folder.config(text=tr("btn_output_folder"))
        self.btn_sql_db.config(text=tr("btn_db"))
        self.btn_export_db.config(text=tr("btn_export_db"))
        self.btn_donate.config(text=tr("btn_donate"))
        # Раунд 21: контекстное меню статуса создаётся один раз при старте —
        # подписи обязаны обновляться при смене языка (иначе «Копировать»
        # остаётся русским на всех языках)
        self.status_menu.entryconfig(0, label=tr("copy"))
        self.status_menu.entryconfig(1, label=tr("copy_title"))
        self.btn_select_all.config(text=tr("btn_select_all"))
        self.btn_clear_all.config(text=tr("btn_clear_all"))
        self.btn_export_selected.config(text=tr("btn_export_selected"))
        self.chk_single.config(text=tr("chk_single"))
        self.btn_open_folder.config(text=tr("btn_open_folder"))
        self.btn_site.config(text=tr("btn_site"))
        # Я4 (раунды 17–18; раунд 20: кнопка «…в один файл» стала чекбоксом,
        # тройка правых кнопок сохраняет единую ширину; раунд 21: ширины
        # в CJK-единицах — китайские глифы двойные, иначе обрезаются)
        wide = _ui_width(tr("btn_site")) + 2
        self.btn_site.config(width=wide)
        self.btn_donate.config(width=wide)
        self.btn_open_folder.config(width=wide)
        # раунд 16: «Выбрать всё»/«Снять выбор» — шириной с «Папку экспорта»
        # (элементы правее сдвигаются grid'ом сами)
        wide_left = max(_ui_width(tr("btn_output_folder")),
                        _ui_width(tr("btn_select_all")),
                        _ui_width(tr("btn_clear_all"))) + 2
        self.btn_select_all.config(width=wide_left)
        self.btn_clear_all.config(width=wide_left)
        self.btn_output_folder.config(width=wide_left)
        # раунд 20/21: кнопка не уже чекбокса под ней («записать в один
        # файл» — продолжение предложения кнопки)
        wide_export = max(_ui_width(tr("btn_export_selected")),
                          _ui_width(tr("chk_single"))) + 2
        self.btn_export_selected.config(width=wide_export)
        # раунд 14: ширина прогресс-бара = ширине кнопки «Выбрать всё»
        # (после установки текста и ширины — reqwidth уже по факту)
        self.progress.config(length=self.btn_select_all.winfo_reqwidth())

    def _restore_geometry(self) -> None:
        geometry = self.cfg.get("window_geometry", "")
        if geometry and _GEOMETRY_RE.match(geometry):
            self.root.geometry(geometry)

    # ------------------------------------------------------------- таблица

    def _update_headings(self) -> None:
        for name, key in COLUMNS:
            if name not in SORTABLE:
                continue
            text = tr(key)
            if name == self._sort_col:
                text += " ↓" if self._sort_desc else " ↑"
            self.tree.heading(name, text=text)

    def _on_heading_click(self, column: str) -> None:
        if self._sort_col == column:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = column
            self._sort_desc = column != "title"  # названия — А→Я, остальное — по убыванию
        self._update_headings()
        self._apply_filter()

    def _sorted_rows(self) -> list[dict]:
        column = self._sort_col

        def key(row: dict):
            if column == "title":
                return (row.get("title") or "").casefold()
            if column == "requests":
                try:
                    return int(row.get("requests") or 0)
                except (TypeError, ValueError):
                    return 0
            return row.get(f"{column}_at") or ""  # updated_at / created_at (ISO)

        return sorted(self.rows, key=key, reverse=self._sort_desc)

    def _apply_filter(self, *_args) -> None:
        needle = self.search_var.get().strip().casefold()
        self.tree.delete(*self.tree.get_children())
        self.visible_ids = []
        for row in self._sorted_rows():
            title = row.get("title") or ""
            if needle and needle not in title.casefold():
                continue
            dialog_id = row["id"]
            self.visible_ids.append(dialog_id)
            mark = CHECK_ON if dialog_id in self.checked else CHECK_OFF
            self.tree.insert("", "end", iid=dialog_id,
                             values=(mark, title, row.get("updated_local", ""),
                                     row.get("created_local", ""), row.get("requests", 0)))

    def _on_tree_click(self, event) -> None:
        """Я8: клик в любом месте строки — переключить ☑ и выделить строку."""
        iid = self.tree.identify_row(event.y)
        if iid:
            self._set_checked(iid, iid not in self.checked)
            self.tree.selection_set(iid)
        return None

    def _set_checked(self, dialog_id: str, on: bool) -> None:
        if on:
            self.checked.add(dialog_id)
        else:
            self.checked.discard(dialog_id)
        if self.tree.exists(dialog_id):
            values = list(self.tree.item(dialog_id, "values"))
            values[0] = CHECK_ON if on else CHECK_OFF
            self.tree.item(dialog_id, values=values)

    def _select_all_visible(self) -> None:
        for dialog_id in self.visible_ids:
            self._set_checked(dialog_id, True)

    def _clear_all_visible(self) -> None:
        for dialog_id in self.visible_ids:
            self._set_checked(dialog_id, False)

    # ------------------------------------------------------------- задачи

    def _list_job(self) -> dict:
        """Задание «загрузить список»: база — из поля «SQL база:» (раунд 12 —
        выбранный «Обзором» файл действует сразу, без перезапуска)."""
        return {"kind": "list", "mode": self.mode_var.get(),
                "db": self.db_var.get().strip()}

    def refresh_list(self) -> None:
        if self.runner.busy():
            return
        self._begin_busy()
        self._set_status(tr("status_loading"))
        self.runner.submit(self._list_job())

    def export_selected(self) -> None:
        if self.runner.busy():
            return
        selected = [dialog_id for dialog_id in self.visible_ids if dialog_id in self.checked]
        formats = [fmt for fmt in FORMATS if self.fmt_vars[fmt].get()]
        if not selected or not formats:
            self._set_status(tr("status_select_row"), ERROR_FG)
            return
        try:
            out_dir = self._chat_output_dir()
        except OSError as exc:
            messagebox.showerror(f"{BRAND}", str(exc), parent=self.root)
            return
        # Раунд 19/20: вся работа — ОДНО задание в ОДНОМ рабочем потоке.
        # Чекбокс «Экспорт в один файл»: выбранные чаты пакуются в один
        # файл каждого формата; иначе — каждый чат в свой файл.
        items = [(dialog_id, fmt) for dialog_id in selected for fmt in formats]
        self._batch = {"total": len(formats) if self.single_var.get()
                       else len(items), "ok": 0, "errors": []}
        self._begin_busy()
        if self.single_var.get():
            self.runner.submit(self._single_job(formats, out_dir, selected))
        else:
            self.runner.submit(self._batch_job(items, formats, out_dir))

    def _batch_job(self, items: list[tuple], formats: list[str],
                   out_dir: Path) -> dict:
        return {"kind": "batch", "mode": self.mode_var.get(),
                "db": self.db_var.get().strip(), "items": items,
                "out_dir": str(out_dir),
                "options": self._options_map(formats)}

    def _single_job(self, formats: list[str], out_dir: Path,
                    chat_ids: list[str]) -> dict:
        return {"kind": "single", "mode": self.mode_var.get(),
                "db": self.db_var.get().strip(), "formats": formats,
                "out_dir": str(out_dir), "chat_ids": chat_ids,
                "options": self._options_map(formats)}

    def _finish_batch(self, cancelled: bool = False) -> None:
        batch, self._batch = self._batch, None
        self._end_busy()
        if cancelled:
            return  # окно закрывается/режим меняется — статус покажет новое
        errors = batch["errors"]
        color = OK_FG if not errors else ERROR_FG
        self._set_status(tr("status_batch_done", ok=batch["ok"], err=len(errors)), color)
        self._persist()
        if errors:
            lines = [f"«{self._error_title(dialog_id)}» [{fmt}]: {message}"
                     for dialog_id, fmt, message in errors[:8]]
            if len(errors) > 8:
                lines.append("…")
            self._show_error_window(tr("err_batch", n=len(errors)),
                                    "\n".join(lines))

    def _show_error_window(self, title: str, text: str) -> None:
        """Раунд 13: окно ошибок с копируемым текстом (Text + Ctrl+C,
        кнопка «Копировать» — как в статус-строке)."""
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.grab_set()
        box = tk.Text(win, wrap="word", width=72, height=12,
                      font=("Segoe UI", 9))
        box.insert("1.0", text)
        box.config(state="disabled")
        box.pack(fill="both", expand=True, padx=10, pady=(10, 6))
        buttons = ttk.Frame(win)
        buttons.pack(fill="x", padx=10, pady=(0, 10))

        def _copy_all() -> None:
            win.clipboard_clear()
            win.clipboard_append(text)

        ttk.Button(buttons, text=tr("copy"), command=_copy_all)\
            .pack(side="left")
        ttk.Button(buttons, text=tr("btn_close"), command=win.destroy)\
            .pack(side="right")
        win.bind("<Escape>", lambda *_e: win.destroy())

    def _begin_busy(self) -> None:
        for widget in self._busy_widgets:
            widget.state(["disabled"])
        self.progress.start(60)

    def _end_busy(self) -> None:
        self.progress.stop()
        for widget in self._busy_widgets:
            widget.state(["!disabled"])
        self._update_limit_state()

    def _poll(self) -> None:
        for event in self.runner.drain():
            try:
                self._handle_event(event)
            except Exception as exc:  # баг обработчика не должен вешать UI
                self._end_busy()
                self._batch = None
                self._set_status(f"{type(exc).__name__}: {exc}", ERROR_FG)
        self.root.after(100, self._poll)

    def _handle_event(self, event: tuple) -> None:
        name = event[0]
        if name == "list":
            self._end_busy()
            self._on_list_ready(event[1])
        elif name == "progress":
            self._set_status(tr("status_batch", done=event[1], total=event[2]))
        elif name == "item_done":
            self._on_item_done(event[1], event[3])
        elif name == "item_error":
            if self._batch is not None:
                self._batch["errors"].append((event[1], event[2], event[3]))
        elif name == "batch_done":
            self._finish_batch(cancelled=event[3])
        elif name == "list_error":
            self._end_busy()
            self._set_status(event[1], ERROR_FG)
        elif name == "job_error" or name.endswith("_error"):
            # фатально для задания (база не открылась и т.п.) — как раньше
            self._end_busy()
            self._batch = None
            self._set_status(event[1], ERROR_FG)
            messagebox.showerror(BRAND, event[1], parent=self.root)

    def _on_item_done(self, dialog_id: str, result: dict) -> None:
        if self._batch is not None:
            self._batch["ok"] += 1
        path = Path(result.get("path", ""))
        if path.is_file():
            self.last_file = path

    def _error_title(self, dialog_id: str) -> str:
        if dialog_id == "__single__":
            return "всё в один файл"
        return (self.rows_by_id.get(dialog_id) or {}).get("title", dialog_id)

    def _on_list_ready(self, rows: list[dict]) -> None:
        self.rows = rows
        self.rows_by_id = {row["id"]: row for row in rows}
        self.checked &= set(self.rows_by_id)  # убираем исчезнувшие диалоги
        self._apply_filter()
        if self.visible_ids and not any(d in self.checked for d in self.visible_ids):
            self._set_checked(self.visible_ids[0], True)  # по умолчанию первый чат
        self._set_status(tr("status_loaded", n=len(rows)), OK_FG)
        # раунд 11: имя/версию движка в статусе не печатаем (просьба владельца)

    # ------------------------------------------------------------ helpers

    def _set_status(self, text: str, color: str | None = None) -> None:
        self.status_lbl.config(text=text, foreground=color or "black")

    def _copy_status(self, *_args) -> None:
        """Раунды 12–14: копировать текст статус-строки; пустой статус —
        копируется заголовок окна (с версией)."""
        try:
            focus = self.root.focus_get()
            if focus is not None and focus.selection_present():
                return  # в поле ввода есть выделение — Ctrl+C копирует его
        except (tk.TclError, AttributeError):
            pass
        text = self.status_lbl.cget("text") or self.root.title()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)

    def _copy_title(self, *_args) -> None:
        """Раунд 14: копировать заголовок окна (название + версия)."""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.root.title())

    def _resolve_output_dir(self) -> Path:
        text = self.output_var.get().strip()
        if not text:
            text = str(config.default_output_dir())
            self.output_var.set(text)
        return Path(text)

    def _chat_output_dir(self) -> Path:
        """Раунд 13: чаты пишутся в субпапки «AutoClaw Chats»/«ZCode Chats»
        общей папки вывода (она же материнская для «… SQL»)."""
        target = self._resolve_output_dir() / CHAT_SUBDIRS[self._mode]
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _tool_limit_int(self) -> int:
        """Я4: пустое/нечисловое поле = 0; отрицательное тоже приводится к 0."""
        try:
            value = int(self.tool_limit_var.get())
        except ValueError:
            return 0
        return max(value, 0)

    def _normalize_limit(self, *_args) -> None:
        """При потере фокуса пустое/нечисловое поле становится 0 (Я4)."""
        text = self.tool_limit_var.get().strip()
        try:
            value = int(text)
            if value < 0:
                value = 0
        except ValueError:
            value = 0
        self.tool_limit_var.set(str(value))

    def _update_limit_state(self) -> None:
        any_tools = any(self.opt_vars[fmt]["tools"].get() for fmt in FORMATS)
        if any_tools:
            self.tool_limit_box.state(["!disabled"])
        else:
            self.tool_limit_box.state(["disabled"])

    def _options_for(self, fmt: str) -> dict:
        """Поля ExportOptions для колонки формата (fmt добавит job_runner).

        all_files — только у AutoClaw-адаптера (строка матрицы прячется в
        ZCode-режиме); BOM в json невозможен — всегда False.
        """
        opts = self.opt_vars[fmt]
        return {
            "tools": opts["tools"].get(),
            "narration": opts["narration"].get(),
            "tool_limit": self._tool_limit_int(),
            "all_files": (opts["all_files"].get()
                          and self.mode_var.get() == "autoclaw"),
            "no_files": opts["no_files"].get(),
            "bom": fmt != "json" and bool(opts["bom"].get()),
            "lang": i18n.current_lang(),
        }

    def _options_map(self, formats: list[str]) -> dict[str, dict]:
        return {fmt: self._options_for(fmt) for fmt in formats}

    def _browse_output(self) -> None:
        chosen = filedialog.askdirectory(
            parent=self.root, title=tr("dlg_pick_folder"),
            initialdir=self.output_var.get() or str(config.default_output_dir()))
        if chosen:
            self.output_var.set(chosen)
            self._persist()

    def _browse_db(self) -> None:
        # Раунд 17: диалог открывает папку из поля «SQL база» (файл → его
        # папка), а не «любую по выбору Windows» (жалоба с 8.1)
        current = Path(self.db_var.get().strip()
                       or str(config.default_output_dir()))
        initial = current.parent if current.is_file() else current
        chosen = filedialog.askopenfilename(
            parent=self.root, title=tr("dlg_pick_db"), initialdir=str(initial),
            filetypes=[("SQLite", "*.sqlite"), ("All files", "*.*")])
        if chosen:
            self.db_var.set(chosen)
            self._persist()
            self.refresh_list()  # раунд 12: выбрал базу — список грузится сразу

    def _autofill_db_var(self) -> None:
        """Раунд 17: поле «SQL база» при старте/первом визите режима не
        пустое: автопоиск нашёл базу — в поле её путь; не нашёл — путь к
        exe (диалог откроет эту папку, а не «любую» Windows)."""
        if self.db_var.get().strip():
            return
        found = self._db_source_path()
        self.db_var.set(str(found) if found
                        else str(config.default_output_dir()))

    def _db_source_path(self) -> Path | None:
        """Файл текущей базы: из поля, иначе автопоиск по db_profiles.cfg
        (раунд 19: пути — в отдельном человеко-редактируемом файле)."""
        text = self.db_var.get().strip()
        if text:
            return Path(text)
        return db_profiles.find_db(self._mode, self.db_profiles)

    def _export_db(self) -> None:
        """Раунды 8/16: копия SQL-базы текущего режима — ВСЕГДА в субпапку
        «… SQL» папки вывода, БЕЗ диалога (на 8.1 диалог сохранения уводил
        файлы в другие папки). Имя = имя базы; дубликаты — « (1)», « (2)»…."""
        source = self._db_source_path()
        if source is None:
            messagebox.showerror(BRAND, tr("err_db_none"), parent=self.root)
            return
        if not source.is_file():
            messagebox.showerror(BRAND, tr("err_db_missing", path=source),
                                 parent=self.root)
            return
        subdir = self._resolve_output_dir() / SQL_SUBDIRS[self._mode]
        try:
            subdir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(BRAND, str(exc), parent=self.root)
            return
        target = subdir / source.name
        counter = 1
        while target.exists():
            target = subdir / f"{source.stem} ({counter}){source.suffix}"
            counter += 1
        try:
            copy_db_files(source, target)
        except OSError as exc:
            messagebox.showerror(BRAND, tr("err_db_copy", msg=exc),
                                 parent=self.root)
            return
        self._set_status(tr("status_db_exported", path=target), OK_FG)

    def _open_folder(self) -> None:
        out_dir = self._resolve_output_dir()
        # раунд 13: файлы теперь в субпапках — выделять последний, если он
        # где-то внутри папки вывода
        if self.last_file is not None and self.last_file.exists() \
                and (self.last_file.parent == out_dir
                     or out_dir in self.last_file.parents):
            subprocess.Popen(["explorer", f"/select,{self.last_file}"])
        else:
            # раунд 16: os.startfile вместо explorer <путь> — без сюрпризов
            # аргументной строки explorer на 8.1 (первый запуск, пустой конфиг)
            os.startfile(str(out_dir))

    def _on_lang_change(self, *_args) -> None:
        i18n.set_lang(self.lang_var.get())
        self._apply_language()
        if self.rows and not self._batch:
            self._set_status(tr("status_loaded", n=len(self.rows)), OK_FG)
        self._persist()

    def _on_mode_change(self) -> None:
        """Переключение AutoClaw Chats / Zcode Chats с сохранением состояния."""
        new_mode = self.mode_var.get()
        if new_mode == self._mode:
            return
        if self.runner.busy():
            self.runner.cancel()
        self._batch = None
        self._stash_state()
        self._mode = new_mode
        self.rows = []
        self.rows_by_id = {}
        self.checked = set()
        self.last_file = None
        self._apply_filter()
        self._set_all_files_visible(new_mode == "autoclaw")
        self._apply_language()  # подписи от режима больше не зависят — безвредно
        state = self._mode_state.get(new_mode)
        if state and state.get("rows"):
            self._restore_state(state)
            self._set_status(tr("status_loaded", n=len(self.rows)), OK_FG)
        else:
            # первое посещение режима: своё значение поля «База»
            self.db_var.set(self.cfg.get(
                "db_path_zcode" if new_mode == "zcode" else "db_path", ""))
            self._autofill_db_var()  # раунд 17: поле не остаётся пустым
            self.refresh_list()

    def _stash_state(self) -> None:
        self._mode_state[self._mode] = {
            "rows": self.rows,
            "rows_by_id": self.rows_by_id,
            "checked": set(self.checked),
            "last_file": self.last_file,
            "db": self.db_var.get(),
        }

    def _restore_state(self, state: dict) -> None:
        self.rows = state["rows"]
        self.rows_by_id = state["rows_by_id"]
        self.checked = set(state["checked"])
        self.last_file = state["last_file"]
        if "db" in state:
            self.db_var.set(state["db"])
        self._apply_filter()
        if self.visible_ids and not any(d in self.checked for d in self.visible_ids):
            self._set_checked(self.visible_ids[0], True)

    def _set_all_files_visible(self, visible: bool) -> None:
        """Ключ /all-files есть только у AutoClaw-движка — строка прячется."""
        widgets = [self.matrix_labels["all_files"]] + [
            self.matrix_checks[("all_files", fmt)] for fmt in FORMATS]
        for widget in widgets:
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

    def _persist(self, *_args) -> None:
        if not self.persist_config:
            return
        self.cfg.update({
            "lang": self.lang_var.get(),
            "export_formats": [fmt for fmt in FORMATS if self.fmt_vars[fmt].get()],
            "options": {fmt: {key: var.get() for key, var in row.items()}
                        for fmt, row in self.opt_vars.items()},
            "tool_limit": self._tool_limit_int(),
            "single_file": self.single_var.get(),
            "output_dir": self.output_var.get().strip(),
            "db_path": self.db_var.get().strip() if self._mode == "autoclaw"
                       else self.cfg.get("db_path", ""),
            "db_path_zcode": self.db_var.get().strip() if self._mode == "zcode"
                             else self.cfg.get("db_path_zcode", ""),
            "window_geometry": self.root.winfo_geometry(),
        })
        try:
            config.save(self.cfg)
        except OSError:
            pass  # каталог конфига недоступен для записи — настройки не критичны

    def _on_close(self) -> None:
        if self.runner.busy():
            if not messagebox.askyesno(tr("confirm_exit_title"),
                                       tr("confirm_exit_msg"), parent=self.root):
                return
            self.runner.cancel()
        self._persist()
        self.root.destroy()
