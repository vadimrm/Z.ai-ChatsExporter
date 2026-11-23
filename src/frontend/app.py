# Copyright © 2026 by Vadim Madgazin
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

from datetime import datetime
import json
import os
import re
import subprocess
import sys
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
# Номер беты/релиза называет владелец (последняя бета — 1.34b; беты
# 1.28b…1.34b, релиз 1.27); обновляется вручную при выпуске сборки.
APP_VERSION = "2.00"
SITE_URL = "https://www.vmgames.com"
DONATE_URL = "https://www.paypal.me/vmgames/5"
DEFAULT_TOOL_LIMIT = 1000
# р44: лимит инструмента для пресета «актуальный контекст» — кап ZCode
# (MIDDLE_TRUNCATION_MAX_CHARS = 10_000 в исходниках ZCode)
TOOL_LIMIT_MODEL_VIEW = 10000
ERROR_FG = "#b00020"
WARN_FG = "#a05a00"  # р65: предупреждения (не ошибка) — «минимальный состав»
OK_FG = "#0a7a0a"
GRAY_FG = "#777777"
CHECK_ON = "☑"
CHECK_OFF = "☐"
_GEOMETRY_RE = re.compile(r"^\d+x\d+\+\-?\d+\+\-?\d+$")

# колонки таблицы: (имя, ключ i18n или None для служебной); порядок —
# раунд 24 + р37: ☑, Проект, Чат, Тип, Число, Обновлён, Создан
COLUMNS = (("check", None), ("project", "col_project"), ("title", "col_title"),
           ("type", "col_type"), ("requests", "col_requests"),
           ("tokens", "col_tokens"), ("updated", "col_updated"),
           ("created", "col_created"))
# р48: «Тип» сортируемая (А→Я; одинаковый тип — по «Обновлён» по умолчанию)
SORTABLE = ("title", "project", "updated", "created", "requests", "tokens",
            "type")
# р81 (п.4): «Скрыть блоки файлов» (no_files) удалён — файловые блоки
# показываются всегда; «Показать служебные файлы» (all_files) остался
MATRIX_ROWS = (("tools", "row_tools"), ("narration", "row_narration"),
               ("all_files", "row_all_files"),
               ("bom", "row_bom"), ("ctx", "row_ctx"))
# р46: «Экспорт SQL базы» удалён — юзер копирует из папки exe вручную
# Субпапки экспорта чатов (раунд 13): папка вывода — общая материнская.
CHAT_SUBDIRS = {"autoclaw": "AutoClaw Chats", "zcode": "ZCode Chats"}
MODE_LABELS = {"autoclaw": "AutoClaw", "zcode": "ZCode"}


def _iso_ts(value) -> float:
    """р48: ISO-строка → epoch-секунды (0.0 для пустого/битого) —
    вторичный ключ сортировки по «Тип»."""
    try:
        return datetime.fromisoformat(
            (value or "").replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _fmt_tokens(n) -> str:
    """р43 (A): сокращение токенов для узкой колонки: 911520 -> 912K."""
    if not isinstance(n, int) or n < 0:
        return ""
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{round(n / 1000)}K"
    return f"{n / 1_000_000:.1f}M"


def _ui_width(text: str) -> int:
    """Текстовая ширина для формул кнопок: CJK-глифы считаются двойными
    (раунд 21: иначе кнопки на китайском обрезаются — ширина Tk считается
    по средней ширине латиницы, а китайский глиф вдвое шире)."""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


class App:
    def __init__(self, root: tk.Tk, persist_config: bool = True) -> None:
        self.root = root
        self.persist_config = persist_config
        self.cfg = config.load()
        # р69/р72: предупреждения-заметки, которые должны пережить первую
        # загрузку списка (жёлтый статус вместо окна/затирания)
        self._notes: list[str] = []
        # Раунд 23: set_lang читает внешний языковый файл (если есть) и
        # возвращает имя битого файла — предупреждение при старте.
        lang_note = i18n.set_lang(self.cfg.get("lang", "ru"))
        # Раунд 37: показывать скрытые чаты (del/arch/wfchld/selchat/auto;
        # ключ настроек show_subagents сохранён — без миграции)
        self.show_hidden_var = tk.BooleanVar(
            value=bool(self.cfg.get("show_subagents", False)))
        if lang_note:
            self.root.after(400, lambda: self._dialog(
                "warn", tr("lang_corrupt", file=lang_note)))
        # Раунд 19 (дополнение): пути баз — из отдельного db_profiles.cfg рядом
        # с exe (лежит в поставке); если файла не было/он битый — программа
        # записала заводской и сообщит об этом предупреждением.
        # р46: повреждённый ExportChat.cfg — как db_profiles: .err + заново;
        # р63 (я7): строго — не только мусорный JSON, но и чужая структура
        # (удалённый/переименованный ключ, неверный _version; прежде такие
        # файлы молча «исправлялись», стирая содержимое)
        cfg_path = config.config_path()
        if cfg_path.is_file():
            try:
                raw_cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
                cfg_damaged = not config.validate(raw_cfg)
            except (json.JSONDecodeError, UnicodeDecodeError):
                cfg_damaged = True
            if cfg_damaged:
                os.replace(cfg_path, Path(str(cfg_path) + ".err"))
                self.root.after(400, lambda: self._dialog(
                    "warn", tr("msg_cfg_corrupt")))
        self.cfg = config.load()
        self.db_profiles, self.db_profiles_note = db_profiles.load()
        # р72/р73 (владелец): не пугать окном — жёлтый статус СРАЗУ при
        # определении (до диалога импорта); показывается сразу после
        # создания статус-строки ниже; рабочие статусы («Загрузка…»,
        # «Загружено N») затем сменяют его как обычно
        self._dbp_note = (tr(self.db_profiles_note)
                          if self.db_profiles_note else "")
        # р83 (п.2): сверхдлинные строки (config/i18n/db_profiles уже
        # прочитаны к этому моменту; set_lang тоже успел прочитать lang) —
        # жёлтая нота одним статусом с dbp-нотой
        self._long_note = self._long_strings_note()
        # первое создание ExportChat.cfg: пути мастеров = автопоиск
        # db_profiles («пути в обоих файлах совпадают», решение владельца)
        if not cfg_path.is_file():
            for m in ("autoclaw", "zcode"):
                found = db_profiles.find_db(m, self.db_profiles)
                if found:
                    self.cfg[f"db_path_{m}"] = str(found)
        # р46: мусор в last_mode → AutoClaw + сообщение об ошибке конфига
        raw_mode = self.cfg.get("last_mode", "autoclaw")
        self._mode = (raw_mode
                      if raw_mode in ("autoclaw", "zcode")
                      else "autoclaw")
        if raw_mode not in ("autoclaw", "zcode"):
            self.root.after(400, lambda: self._dialog(
                "warn", tr("msg_last_mode_err")))
        self.runner = jr.JobRunner()
        self._mode_state: dict[str, dict] = {}
        self.rows: list[dict] = []
        self.rows_by_id: dict[str, dict] = {}
        self.checked: set[str] = set()
        self.visible_ids: list[str] = []
        self.last_file: Path | None = None
        self._batch: dict | None = None
        self._sort_col = "updated"
        self._sort_desc = True

        # р47 (исправление 1.42b): старт в режиме last_mode. Раньше
        # mode_var всегда был "autoclaw": при last_mode=zcode список грузился
        # из AutoClawData, а клик по «Zcode Chats» отбрасывался проверкой
        # new_mode == self._mode — список менялся только по кнопке обновления.
        self.mode_var = tk.StringVar(value=self._mode)
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
        # р36: ключ настроек переименован db_path → db_path_autoclaw
        self.db_var = tk.StringVar(value=self.cfg.get(
            "db_path_zcode" if self._mode == "zcode" else "db_path_autoclaw",
            ""))
        # Раунд 31: 2-я база ZCode (tasks-index — названия проектов)
        # Раунд 17: поле базы тоже заполняется при старте (раунд 17)
        self._autofill_db_var()

        self._build()
        # р43: ряд «Только актуальный контекст» — только в ZCode
        self._set_ctx_visible(self._mode == "zcode")
        # р44: all_files — только AutoClaw (актуально при старте в ZCode)
        self._set_all_files_visible(self._mode != "zcode")
        self._apply_language()
        self._update_headings()
        self._update_limit_state()
        self._restore_geometry()
        # р75: правый клик по любому элементу — «Копировать текст»
        self.root.bind_all("<Button-3>", self._any_text_menu)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll)
        self.root.after(600, self._startup_data_check)
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
        # р53: отступы краевых фреймов = толщине канта 20px, чтобы полосы-
        # захваты лежали в поле и не накрывали виджеты
        top = ttk.Frame(self.root, padding=(20, 20, 20, 4))
        top.grid(row=0, column=0, sticky="ew")

        # р76 (владелец): Zcode Chats — первым слева, AutoClaw — правее
        self.radio_zcode = ttk.Radiobutton(
            top, value="zcode", variable=self.mode_var, text="Zcode Chats",
            command=self._on_mode_change)
        self.radio_zcode.grid(row=0, column=0, sticky="w")
        self.radio_autoclaw = ttk.Radiobutton(
            top, value="autoclaw", variable=self.mode_var, text="AutoClaw Chats",
            command=self._on_mode_change)
        self.radio_autoclaw.grid(row=0, column=1, sticky="w", padx=(4, 14))

        self.lbl_lang = ttk.Label(top)
        self.lbl_lang.grid(row=0, column=2, sticky="w")
        self.lang_box = ttk.Combobox(top, textvariable=self.lang_var,
                                     values=list(i18n.LANGS), state="readonly", width=5)
        self.lang_box.grid(row=0, column=3, sticky="w", padx=(4, 12))
        self.lang_box.bind("<<ComboboxSelected>>", self._on_lang_change)

        # раунд 26: чекбокс «Показывать чаты субагентов» — правее языка
        self.chk_hidden = ttk.Checkbutton(
            top, variable=self.show_hidden_var,
            command=self._on_hidden_toggle)
        self.chk_hidden.grid(row=0, column=4, sticky="w", padx=(8, 0))

        # р49 (решение владельца): поиск — сразу правее чекбокса скрытых
        # чатов (прежде был у правого края); «Обновить SQL базу» переехала
        # в блок базы (ряд кнопки «Путь к SQL базе»)
        self.lbl_search = ttk.Label(top)
        self.lbl_search.grid(row=0, column=5, sticky="w", padx=(10, 0))
        self.search_entry = ttk.Entry(top, textvariable=self.search_var, width=30)
        self.search_entry.bind("<Button-3>", self._entry_menu)  # р71
        self.search_entry.grid(row=0, column=6, sticky="w", padx=(4, 0))
        top.columnconfigure(7, weight=1)

        # --- таблица + матрица опций ---
        main = ttk.Frame(self.root, padding=(20, 0, 20, 0))
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
        # раунд 24: «Проект» слева от «Чат»; р37: добавлена «Тип», чтобы
        # инвариант «все колонки видимы при минимальной ширине» (Я2) жил,
        # фиксированные ширины ужаты: Проект 130→110, даты 120→104
        self.tree.column("project", width=100, minwidth=90, anchor="w", stretch=False)
        self.tree.column("title", width=340, stretch=True)
        # р37: метка типа чата (del/arch/fork/wfprnt/wfchld/selchat/auto)
        self.tree.column("type", width=52, minwidth=44, anchor="center",
                         stretch=False)
        self.tree.column("requests", width=60, minwidth=40, anchor="e", stretch=False)
        # р43 (A): контекст в токенах (последний input_tokens, сокр.)
        self.tree.column("tokens", width=44, minwidth=36, anchor="e",
                         stretch=False)
        self.tree.column("updated", width=104, anchor="center", stretch=False)
        self.tree.column("created", width=104, anchor="center", stretch=False)
        for name, _key in COLUMNS:
            if name in SORTABLE:
                self.tree.heading(name, command=lambda c=name: self._on_heading_click(c))
        self.tree.bind("<Button-1>", self._on_tree_click)
        # Подгонка ширины «Названия», чтобы «Запросов» не уходила за границу.
        self.tree.bind("<Configure>", lambda *_e: self._fit_columns())
        # Раунд 36/37: скрытые чаты (показаны чекбоксом) — светло-серый фон.
        self.tree.tag_configure("svc", background="#e8e8e8")

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
                self.tool_limit_box.bind("<Button-3>", self._entry_menu)  # р71
                self.tool_limit_box.grid(row=row_index, column=1, columnspan=3,
                                         sticky="ew", padx=(7, 3), pady=2)
                self.tool_limit_box.bind("<FocusOut>", self._normalize_limit)
            row_index += 1

        # Релиз 1.27 (раунд 22): текст подсказки удалён по требованию
        # владельца; виджет-пустышка оставлен на своей ячейке, чтобы НИ
        # один элемент (блок «SQL база» ниже) не сдвинулся.
        # р22: серая подсказка удалена, пустышка держала ячейку;
        # р44 (решение владельца): ячейку заняла кнопка пресета —
        # непосредственно под чекбоксами, которые она меняет
        self.btn_as_model = ttk.Button(opts, command=self._apply_model_view)
        self.btn_as_model.grid(row=row_index, column=0, columnspan=4,
                               sticky="w", pady=(6, 0))

        # Строка базы (раунд 14; р49 по решению владельца): ряд 0 — кнопка
        # «Путь к SQL базе», справа — «Обновить SQL базу» (на освободив-
        # шемся месте поля); ряд 1 — поле пути НА ВСЮ ширину, его левый
        # край по левому краю кнопки (прежде поле стояло справа от
        # кнопки в один ряд).
        dbf = ttk.Frame(right, padding=(8, 12, 8, 2))
        dbf.grid(row=1, column=0, sticky="ew")

        self.btn_sql_db = ttk.Button(dbf, command=self._browse_db)
        self.btn_sql_db.grid(row=0, column=0, sticky="w")
        # р47: «Обновить SQL базу» — переимпорт копии с мастера, не чтение
        # р49: переехала из верхней строки сюда — справа от кнопки пути
        # р50: прижата к ПРАВОМУ краю поля пути (правые края совпадают)
        self.btn_refresh = ttk.Button(dbf, command=self._refresh_db)
        self.btn_refresh.grid(row=0, column=1, sticky="e")
        self.db_entry = ttk.Entry(dbf, textvariable=self.db_var, width=20)
        self.db_entry.bind("<Button-3>", self._entry_menu)  # р71
        self.db_entry.grid(row=1, column=0, columnspan=2, sticky="ew",
                           pady=(4, 0))
        # р46: кнопки «Экспорт SQL базы» и «SQL база 2» удалены
        # (импорт сам находит 2-ю базу; юзер копирует из папки exe)
        dbf.columnconfigure(0, weight=1)
        dbf.columnconfigure(1, weight=1)

        # --- строка действий (раунд 17): ОДИН фрейм на оба нижних ряда,
        # без пустых ячеек: ряд 0 — «Выбрать всё»/«Снять выбор»/«Формат»/
        # «Экспортировать выбранные чаты» + «Открыть папку экспорта» в том
        # же ряду; ряд 1 — «Папка экспорта»+поле (заполняют слот слева),
        # «Экспортировать всё в один файл» + «Donate» справа. Кнопка
        # «Экспортировать выбранные чаты» стоит на одной линии с «Открыть
        # папку экспорта» (требование владельца, раунд 17) ---
        actions = ttk.Frame(self.root, padding=(20, 20))  # р53: низ = кант 20px
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
        self.output_entry.bind("<Button-3>", self._entry_menu)  # р71
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

        # --- ряд 2: статус (прогресс, текст ошибок, сайт автора) ---
        # р55 (решение владельца): нижняя строка больше НЕ отдельный фрейм
        # у самой границы (8px) — третий ряд actions: прогресс ТОЧНО под
        # кнопкой «Папка экспорта», «Vadim R.M. …» ТОЧНО под «Donate»,
        # зазор по вертикали тот же, что между рядами 0 и 1; контент
        # остаётся внутри поля канта
        self.progress = ttk.Progressbar(actions, mode="indeterminate",
                                        length=130)
        self.progress.grid(row=2, column=0, sticky="w")
        self.status_lbl = ttk.Label(actions, anchor="w")
        # р73: сразу, до диалога/списка; р83: рядом — нота длинных строк
        if self._dbp_note or self._long_note:
            self._set_status(self._startup_note(), WARN_FG)
        self.status_lbl.grid(row=2, column=1, columnspan=6, sticky="ew",
                             padx=8)
        self.btn_site = ttk.Button(actions,
                                   command=lambda: webbrowser.open(SITE_URL))
        self.btn_site.grid(row=2, column=8, sticky="e")
        # р77 (владелец): старое меню статуса «Copy / Copy window title»
        # УДАЛЕНО — правый клик по статусу открывает единое меню
        # «Копировать текст: …» (bind_all из р75); Ctrl+C по-прежнему
        # копирует статус (или выделение в поле ввода)
        self.root.bind("<Control-c>", self._copy_status)
        self.root.bind("<Control-C>", self._copy_status)

        self._busy_widgets = [self.btn_refresh, self.btn_select_all, self.btn_clear_all,
                              self.btn_export_selected, self.tool_limit_box,
                              self.search_entry, self.db_entry, self.btn_sql_db,
                              self.btn_output_folder,
                              self.chk_single, self.chk_hidden,
                              self.btn_as_model]
        self._busy_widgets += list(self.fmt_checks.values())
        self._busy_widgets += list(self.matrix_checks.values())
        # Я3/AGREEMENTS раунд 2 №3: JSON BOM всегда серый — исключаем из «оживляемых»
        self._busy_widgets.remove(self.matrix_checks[("bom", "json")])
        # р51: видимая рамка — в самом конце _build, поверх краёв окна
        self._make_resize_handles()

    def _make_resize_handles(self) -> None:
        """р51 (решение владельца): тонкую границу Windows трудно поймать
        курсором — по краям окна накладываются 4 полосы и 4 угла (place,
        сетку не трогают), цветной кант виден, тащить можно за весь кант.
        Drag через grab_set: курсор не срывается с полосы при быстром
        движении."""
        self._resize_handles: dict[str, tk.Frame] = {}
        # р54 (решение владельца — resize работает): толщина 8px везде
        # (полосы и углы), кант светлый #e2e2e2; отступы контента
        # оставлены 20px (р53) — полосы лежат в поле, виджеты не накрыты
        EDGE = 8
        CORNER = 8
        HANDLE_BG = "#e2e2e2"
        for side, cursor in (
                ("n", "top_side"), ("s", "bottom_side"),
                ("w", "left_side"), ("e", "right_side"),
                ("nw", "top_left_corner"), ("ne", "top_right_corner"),
                ("sw", "bottom_left_corner"), ("se", "bottom_right_corner")):
            frame = tk.Frame(self.root, bg=HANDLE_BG, cursor=cursor)
            if side == "n":
                frame.place(relx=0, rely=0, relwidth=1, height=EDGE)
            elif side == "s":
                frame.place(relx=0, rely=1, y=-EDGE, relwidth=1, height=EDGE)
            elif side == "w":
                frame.place(x=0, rely=0, relheight=1, width=EDGE)
            elif side == "e":
                frame.place(relx=1, x=-EDGE, rely=0, relheight=1, width=EDGE)
            elif side == "nw":
                frame.place(x=0, y=0, width=CORNER, height=CORNER)
            elif side == "ne":
                frame.place(relx=1, x=-CORNER, y=0, width=CORNER, height=CORNER)
            elif side == "sw":
                frame.place(x=0, rely=1, y=-CORNER, width=CORNER, height=CORNER)
            else:
                frame.place(relx=1, x=-CORNER, rely=1, y=-CORNER,
                            width=CORNER, height=CORNER)
            frame.bind("<ButtonPress-1>",
                       lambda e, s=side, f=frame: self._resize_press(e, s, f))
            frame.bind("<B1-Motion>",
                       lambda e: self._resize_drag(e))  # сторона в _resize_state
            frame.bind("<ButtonRelease-1>",
                       lambda e, f=frame: self._resize_release(f))
            self._resize_handles[side] = frame
        for frame in self._resize_handles.values():
            frame.lift()  # углы и полосы поверх остальных детей root

    def _resize_press(self, event, side: str, frame: tk.Frame) -> None:
        self._resize_state = (side, event.x_root, event.y_root,
                              self.root.winfo_rootx(), self.root.winfo_rooty(),
                              self.root.winfo_width(), self.root.winfo_height())
        # р55: во время тяги колонки не пересчитывать (тяжёлый вложенный
        # ре-лейаут — источник «искажений») — один раз при отпускании
        self._resize_skip_fit = True
        self._resize_target = None
        self._resize_scheduled = False
        # р53: только ГЛОБАЛЬНЫЙ захват. Локальный grab_set теряет
        # <B1-Motion>, как только курсор выходит за пределы окна (тяга
        # южного/восточного края НАРУЖУ = рост окна) — события уходили
        # в никуда, и окно «не двигало». Глобальный захват доставляет
        # события полосе при любом положении курсора.
        try:
            frame.grab_set_global()
        except tk.TclError:  # не виден (тестовое скрытое окно) и т.п.
            try:
                frame.grab_set()
            except tk.TclError:
                pass

    def _resize_drag(self, event) -> None:
        """р55: БЫСТРАЯ тяга — цель только ЗАПОМИНАЕТСЯ, geometry()
        применяется ОДИН раз за цикл отрисовки (after_idle): потоки
        <B1-Motion> приходят быстрее перерисовки, и дёргать geometry()
        на каждый — источник рывков и «искажённого» промежуточного
        вида (наблюдение владельца на фоне плавной родной рамки)."""
        side, x0, y0, rx, ry, w0, h0 = getattr(self, "_resize_state",
                                               (None,) * 7)
        if side is None:
            return
        try:
            min_w, min_h = self.root.minsize()
            min_w, min_h = int(min_w) or 940, int(min_h) or 560
        except (TypeError, ValueError):
            min_w, min_h = 940, 560
        dx, dy = event.x_root - x0, event.y_root - y0
        x, y, w, h = rx, ry, w0, h0
        if "e" in side:
            w = max(min_w, w0 + dx)
        if "w" in side:
            w = max(min_w, w0 - dx)
            x = rx + (w0 - w)
        if "s" in side:
            h = max(min_h, h0 + dy)
        if "n" in side:
            h = max(min_h, h0 - dy)
            y = ry + (h0 - h)
        self._resize_target = f"{w}x{h}+{x}+{y}"
        if not self._resize_scheduled:
            self._resize_scheduled = True
            # р58: after_idle вернули (проба 20 мс владельцу не помогла —
            # надёжнее стандартный вариант «когда очередь рассосётся»)
            self.root.after_idle(self._apply_resize)

    def _apply_resize(self) -> None:
        """р55: применить последнюю накопленную геометрию (один раз за
        цикл отрисовки — очередь <B1-Motion> успевает рассосаться)."""
        self._resize_scheduled = False
        target = getattr(self, "_resize_target", None)
        if target:
            self._resize_target = None
            self.root.geometry(target)

    def _resize_release(self, frame: tk.Frame) -> None:
        """р55: финал тяги — последняя цель применяется немедленно,
        колонки пересчитываются один раз."""
        frame.grab_release()
        self._resize_skip_fit = False
        target = getattr(self, "_resize_target", None)
        self._resize_target = None
        if target:
            self.root.geometry(target)
        self._fit_columns()

    def _fit_columns(self, width: int | None = None) -> None:
        """Ширина «Чата» = остаток ширины таблицы после фиксированных
        колонок — все колонки видимы и при старте, и при изменении размера."""
        if getattr(self, "_resize_skip_fit", False):
            return  # р55: тяга за кант — колонки после отпускания
        if width is None:
            width = self.tree.winfo_width()
        if width <= 1:
            return  # окно ещё не отрисовано
        fixed = sum(self.tree.column(c)["width"]
                    for c in ("check", "project", "type", "requests",
                              "tokens", "updated", "created"))
        title = max(96, width - fixed - 6)
        self.tree.column("title", width=title, minwidth=96, stretch=True)

    def _startup_note(self) -> str:
        """р83: стартовые жёлтые ноты одним текстом — dbp-нота (р72/р73)
        + «Слишком длинные строки в файле: …» (р83), склеенные « · »."""
        parts = [note for note in (self._dbp_note, self._long_note) if note]
        return " · ".join(parts)

    def _long_strings_note(self) -> str:
        """р83 (п.2): жёлтая нота о сверхдлинных строках в конфигах
        (config.LONG_STRING_FILES заполняют config/i18n/db_profiles)."""
        files = ", ".join(dict.fromkeys(config.LONG_STRING_FILES))
        return tr("msg_long_strings", files=files) if files else ""

    def _apply_language(self) -> None:
        self.root.title(f"{BRAND} ver. {APP_VERSION} - {tr('title_explain')}")
        # р77 (владелец): текст статуса — на новом языке (прежде
        # оставался староязычным); список уже грузился — пересобрать
        # «Диалогов: N · копия от …», иначе — пусто
        if getattr(self, "rows", None):
            self._set_status(tr("status_loaded", n=self._chat_count())
                             + self._copy_tail(), OK_FG)
        elif self._startup_note():
            self._set_status(self._startup_note(), WARN_FG)  # ноты — переведённые
        else:
            self._set_status("")
        self.lbl_lang.config(text=tr("lang_label"))
        self.lbl_search.config(text=tr("search"))
        self.btn_refresh.config(text=tr("refresh"))
        self.chk_hidden.config(text=tr("chk_hidden"))
        self.btn_as_model.config(text=tr("btn_as_model"))
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
        self.btn_donate.config(text=tr("btn_donate"))
        # Раунд 21: контекстное меню статуса создаётся один раз при старте —
        # подписи обязаны обновляться при смене языка (иначе «Копировать»
        # остаётся русским на всех языках)
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
            # названия/проекты/тип — А→Я, остальное — по убыванию
            self._sort_desc = column not in ("title", "project", "type")
        self._update_headings()
        self._apply_filter()

    def _group_and_sort(self, rows: list[dict]):
        """Группировка по проектам (раунд 24): чаты одного проекта идут
        подряд, внутри проекта — по активному правилу; «топовый» чат
        проекта передаёт ему свои параметры, и проекты сортируются вместе
        с одиночными чатами по этим параметрам. Одиночный чат (без
        проекта) — группа из одного. Возвращает пары (row, текст графы
        «Проект»: имя на верхней строке блока, «+++» — продолжение,
        пусто — вне проекта)."""
        project_chats: dict[str, list[dict]] = {}
        singles: list[dict] = []
        for row in rows:
            project = row.get("project") or ""
            if project:
                project_chats.setdefault(project, []).append(row)
            else:
                singles.append(row)

        def chat_key(row: dict):
            column = self._sort_col
            if column == "title":
                return (row.get("title") or "").casefold()
            if column == "project":
                # раунд 28: по имени проекта; внутри проекта и у одиночных
                # — вторичный ключ по названию чата
                return ((row.get("project") or "").casefold(),
                        (row.get("title") or "").casefold())
            if column == "type":
                # р49: отсутствие типа (обычный чат) — КАК ПОСЛЕДНЯЯ
                # литера алфавита (прежде пустое шло первым, обычные чаты
                # вставали выше arch); одинаковый тип — по дате обновления
                # как «по умолчанию» (свежие сверху). Вторичный ключ
                # отрицательный: при том же reverse-флаге даёт ↓
                return ((row.get("type") or "\uffff"),
                        -_iso_ts(row.get("updated_at")))
            if column in ("requests", "tokens"):
                try:
                    return int(row.get(column) or 0)
                except (TypeError, ValueError):
                    return 0
            return row.get(f"{column}_at") or ""  # updated_at / created_at (ISO)

        groups: list[tuple[str, list[dict]]] = (
            [(p, chats) for p, chats in project_chats.items()]
            + [("", [chat]) for chat in singles])

        def group_key(group: tuple[str, list[dict]]):
            project, chats = group
            top = sorted(chats, key=chat_key, reverse=self._sort_desc)[0]
            # тай-брейк при равных параметрах — по имени (проекта или чата)
            name = project or (top.get("title") or "")
            return (chat_key(top), name.casefold())

        more = tr("col_project_more")
        for project, chats in sorted(groups, key=group_key,
                                     reverse=self._sort_desc):
            chats = sorted(chats, key=chat_key, reverse=self._sort_desc)
            for index, row in enumerate(chats):
                yield row, (project if project and index == 0 else
                            (more if project else ""))

    def _apply_filter(self, *_args) -> None:
        needle = self.search_var.get().strip().casefold()
        self.tree.delete(*self.tree.get_children())
        self.visible_ids = []
        show_hidden = self.show_hidden_var.get()
        rows = [row for row in self.rows
                if (not needle or needle in (row.get("title") or "").casefold())
                and (show_hidden or not row.get("hidden"))]
        for row, project_display in self._group_and_sort(rows):
            dialog_id = row["id"]
            self.visible_ids.append(dialog_id)
            mark = CHECK_ON if dialog_id in self.checked else CHECK_OFF
            # р37: скрытые чаты — тег svc (серый фон); метка типа в графе
            tokens = row.get("tokens")
            values = (mark, project_display,
                      row.get("title") or "",
                      row.get("type") or "",
                      row.get("requests", 0),
                      _fmt_tokens(tokens) if tokens else "",
                      row.get("updated_local", ""),
                      row.get("created_local", ""))
            if row.get("hidden"):
                self.tree.insert("", "end", iid=dialog_id, tags=("svc",),
                                 values=values)
            else:
                self.tree.insert("", "end", iid=dialog_id, values=values)

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
                "db": str(config.local_db_path(self.mode_var.get())),
                "index_db": self._index_db_path()}

    def refresh_list(self) -> None:
        if self.runner.busy():
            return
        mode = self.mode_var.get()
        if not config.local_db_path(mode).is_file():
            # р46: локальной копии нет — диалог импорта/сообщение
            self._ensure_local(mode)
            return
        self._begin_busy()
        self._set_status(tr("status_loading"))
        self.runner.submit(self._list_job())

    def _refresh_db(self) -> None:
        """р47 (исправление 1.42b): кнопка «Обновить SQL базу» — заново
        снять снапшот мастера в локальную копию (kind=import); по
        завершении import_done перезагружает список и обновляет «копия от».
        Раньше кнопка только перечитывала старую копию — изменения мастера
        (архив, новые чаты) не попадали в список. Копии нет → путь
        _ensure_local (вопрос импорта), мастера нет → «нужен Путь…»."""
        if self.runner.busy():
            return
        mode = self.mode_var.get()
        if not config.local_db_path(mode).is_file():
            self.refresh_list()
            return
        master = self._resolve_master(mode)
        if master is None:
            # р70: копия есть, мастер не найден — прошлый текст врал
            # («Отсутствует копия данных»); чаты продолжают работать
            self._set_status(
                tr("msg_master_missing", mode=MODE_LABELS[mode]), ERROR_FG)
            return
        self._start_import(mode, master)

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
            self._dialog("error", str(exc))
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
                "db": str(config.local_db_path(self.mode_var.get())),
                "items": items,
                "out_dir": str(out_dir),
                "index_db": self._index_db_path(),
                "options": self._options_map(formats)}

    def _single_job(self, formats: list[str], out_dir: Path,
                    chat_ids: list[str]) -> dict:
        return {"kind": "single", "mode": self.mode_var.get(),
                "db": str(config.local_db_path(self.mode_var.get())),
                "formats": formats,
                "out_dir": str(out_dir), "chat_ids": chat_ids,
                "include_subagents": self.show_hidden_var.get(),
                "index_db": self._index_db_path(),
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
            # раунд 31: результат чужого режима (режим переключили, пока
            # задание бежало) — отбрасываем, строки текущего режима не трогаем
            if len(event) > 2 and event[2] != self.mode_var.get():
                return
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
        elif name == "import_done":
            # р46: локальная копия готова — перезагрузить список;
            # р65: minimal (нет 2-й базы ZCode) — предупреждение статусом.
            # р69: статус списка (в _on_list_ready) перетирал предупреждение
            # через мгновение — поэтому minimal показывается ПОСЛЕ загрузки
            self._end_busy()
            minimal = len(event) > 3 and bool(event[3])
            if minimal and event[1] == self.mode_var.get():
                self._notes.append(tr("status_import_minimal"))
            else:
                self._set_status(tr("status_import_done"), OK_FG)
            if event[1] == self.mode_var.get():
                self.refresh_list()
        elif name == "import_error":
            self._end_busy()
            self._set_status(tr("err_import", msg=event[2]), ERROR_FG)
            self._dialog("error", tr("err_import", msg=event[2]))
        elif name == "list_error":
            self._end_busy()
            # раунд 31: ошибка чужого режима не показывается
            if len(event) > 2 and event[2] != self.mode_var.get():
                return
            self._set_status(event[1], ERROR_FG)
        elif name == "job_error" or name.endswith("_error"):
            # фатально для задания (база не открылась и т.п.) — как раньше
            self._end_busy()
            self._batch = None
            self._set_status(event[1], ERROR_FG)
            self._dialog("error", event[1])

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
        if self._notes:
            # р69/р72: предупреждения (minimal, восстановление db_profiles)
            # переживают загрузку списка — жёлтым, склеенные через « · »
            notes = " · ".join(self._notes)
            self._notes = []
            self._set_status(notes + self._copy_tail(), WARN_FG)
            return
        self._set_status(tr("status_loaded", n=self._chat_count())
                         + self._copy_tail(), OK_FG)
        # раунд 11: имя/версию движка в статусе не печатаем (просьба владельца)

    def _copy_tail(self) -> str:
        """р46: «копия от ДД.ММ ЧЧ:ММ» по mtime локальной копии (без
        обращения к мастер-базам — решение владельца)."""
        local_db = config.local_db_path(self.mode_var.get())
        if not local_db.is_file():
            return ""
        when = datetime.fromtimestamp(
            local_db.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
        return " · " + tr("status_copy_of", when=when)

    def _chat_count(self) -> int:
        """Раунд 37 (решение владельца): число в статусе — обычные чаты,
        а с чекбоксом «Показывать скрытые чаты» — ОДНО число N+M (все)."""
        if self.show_hidden_var.get():
            return len(self.rows)
        return sum(1 for row in self.rows if not row.get("hidden"))

    # ------------------------------------------------------------ helpers

    def _set_status(self, text: str, color: str | None = None) -> None:
        self.status_lbl.config(text=text, foreground=color or "black")

    def _dialog(self, kind: str, text: str, yes_no: bool = False) -> bool:
        """р72 (владелец): собственные диалоги вместо messagebox — текст
        лежит в Text-виджете, ВЫДЕЛЯЕТСЯ и копируется (Ctrl+C / правая
        кнопка), в отличие от системных окон. kind: info/warn/error/ask;
        yes_no — кнопки Да/Нет (возврат bool), иначе ОК."""
        top, result, _tw = self._build_dialog(kind, text, yes_no)
        top.grab_set()
        top.wait_window(top)
        return bool(result["choice"])

    def _build_dialog(self, kind: str, text: str, yes_no: bool):
        """Построить окно диалога (без показа) — для _dialog и тестов.
        Возвращает (Toplevel, {'choice': …}, Text-виджет)."""
        top = tk.Toplevel(self.root)
        top.title(BRAND)
        top.transient(self.root)
        top.resizable(False, False)
        icon = {"warn": "⚠", "error": "✖", "ask": "?"}.get(kind, "ℹ")
        box = tk.Frame(top, padx=16, pady=12)
        box.pack(fill="both", expand=True)
        row = tk.Frame(box)
        row.pack(fill="x")
        tk.Label(row, text=icon, font=("", 14, "bold"),
                 foreground={"error": "#b00020"}.get(kind, "#a05a00")
                 ).pack(side="left", padx=(0, 10))
        text_widget = tk.Text(row, width=52, height=min(10, max(2,
                          text.count("\n") + 1)), wrap="word", borderwidth=0,
                          background=top.cget("background"), font=("Segoe UI", 9))
        text_widget.insert("1.0", text)
        text_widget.configure(state="disabled")
        text_widget.pack(side="left", fill="both", expand=True)
        # выделение в disabled Text работает; Ctrl+C — класс Text; правый
        # клик — копировать всё (если нет выделения — весь текст)
        def copy_text(_event=None):
            try:
                sel = text_widget.get("sel.first", "sel.last")
            except tk.TclError:
                sel = text_widget.get("1.0", "end").strip()
            if sel:
                self.root.clipboard_clear()
                self.root.clipboard_append(sel)
        text_widget.bind("<Button-3>", lambda e: (copy_text(e), "break")[1])

        result = {"choice": None}

        def choose(value):
            result["choice"] = value
            top.destroy()

        buttons = tk.Frame(box)
        buttons.pack(pady=(10, 0))
        if yes_no:
            mk = tk.Button(buttons, text=tr("dlg_yes"), width=10,
                           command=lambda: choose(1))
            mk.pack(side="left", padx=6)
            tk.Button(buttons, text=tr("dlg_no"), width=10,
                      command=lambda: choose(0)).pack(side="left", padx=6)
            mk.focus_set()
            top.bind("<Return>", lambda e: choose(1))
            top.bind("<Escape>", lambda e: choose(0))
        else:
            only = tk.Button(buttons, text=tr("dlg_ok"), width=10,
                             command=lambda: choose(1))
            only.pack()
            only.focus_set()
            top.bind("<Return>", lambda e: choose(1))
            top.bind("<Escape>", lambda e: choose(1))
        top.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width()
                                       - top.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height()
                                       - top.winfo_height()) // 2
        top.geometry(f"+{max(0, x)}+{max(0, y)}")
        return top, result, text_widget

    def _any_text_menu(self, event) -> str:
        """р75 (владелец): правый клик по ЛЮБОМУ элементу GUI — меню
        «Копировать текст: …» (этот элемент) и «Копировать все надписи
        окна». Поля ввода и статус сюда не попадают — их собственные
        биндинги срабатывают раньше и прерывают обработку."""
        widget = event.widget
        text = self._widget_text(widget)
        menu = tk.Menu(self.root, tearoff=0)
        if not text and isinstance(widget, ttk.Treeview):
            # р79 (владелец): клик на ЗАГОЛОВКЕ таблицы — два пункта:
            # копировать заголовок колонки и «заголовок + список чатов»
            if widget.identify_region(event.x, event.y) == "heading":
                # р80 (владелец): копируются заголовки ВСЕХ колонок,
                # а не только той, на которой кликнули
                heading = self._tree_headings_text(widget)
                menu.add_command(
                    label=tr("m_copy_item", text=heading),
                    command=lambda: self._to_clipboard(heading))
                menu.add_command(
                    label=tr("m_copy_chatlist"),
                    command=lambda: self._to_clipboard(
                        self._chat_list_text()))
                menu.tk_popup(event.x_root, event.y_root)
                return "break"
            # р78: текст СТРОКИ ПОД КЛИКОМ (не синего выделения);
            # клик мимо строк → пусто → меню заголовка окна
            text = self._tree_row_text(widget, event.y)
        if text:
            short = text if len(text) <= 40 else text[:40] + "…"
            menu.add_command(label=tr("m_copy_item", text=short),
                             command=lambda: self._to_clipboard(text))
        else:
            # р77 (владелец): клик вне элементов GUI — заголовок окна
            title = self.root.title()
            short = title if len(title) <= 40 else title[:40] + "…"
            menu.add_command(label=tr("m_copy_title", text=short),
                             command=lambda: self._to_clipboard(title))
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _tree_headings_text(self, tree) -> str:
        """р80: заголовки ВСЕХ колонок таблицы через « | »."""
        return " | ".join(
            tree.heading(column, "text")
            for column in (tree["columns"] or ())
            if tree.heading(column, "text"))

    def _chat_list_text(self) -> str:
        """р79 (владелец): шапка всех колонок + все чаты, выведенные в
        окне (текущий фильтр), СКРЫТЫЕ не включаются — текстом, как
        таблица: колонки через « | », чаты построчно."""
        tree = self.tree
        lines = [self._tree_headings_text(tree)]
        for iid in tree.get_children(""):
            row = self.rows_by_id.get(iid) or {}
            if row.get("hidden"):
                continue  # скрытые чаты не копируем (владелец)
            values = [str(v) for v in tree.item(iid, "values") if v]
            if values:
                lines.append(" | ".join(values))
        return "\n".join(lines)

    def _tree_row_text(self, tree, y: int) -> str:
        """р78: строка таблицы под координатой клика — все колонки через
        « | »; мимо строк (заголовок/пустая зона) — пусто."""
        row = tree.identify_row(y)
        if not row:
            return ""
        return " | ".join(
            str(v) for v in tree.item(row, "values") if v)

    def _widget_text(self, widget) -> str:
        """р75: текст виджета (подписи/кнопки/чекбоксы), если есть."""
        try:
            value = widget.cget("text")
        except tk.TclError:
            return ""
        return str(value or "").strip()

    def _to_clipboard(self, text: str) -> None:
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)

    def _entry_copy_cut(self, widget, cut: bool) -> None:
        """р81 (п.6): Копировать/Вырезать в поле ввода — с выделением
        только выделенное (как прежде), БЕЗ выделения — весь текст поля
        (прежде пункты были недоступны). Вырезать — только editable."""
        try:
            has_sel = widget.selection_present()
            editable = str(widget.cget("state")) == "normal"
        except (tk.TclError, AttributeError):
            return
        if has_sel:
            widget.event_generate("<<Cut>>" if cut else "<<Copy>>")
            widget.focus_set()
            return
        text = widget.get()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        if cut and editable:
            widget.delete(0, "end")
        widget.focus_set()

    def _entry_menu(self, event) -> str:
        """р71 (владелец): правая кнопка в любом поле ввода — меню
        Копировать/Вставить/Выделить всё (Ctrl+C в полях и так работает,
        меню делает это очевидным; readonly-поля — только копирование).
        р81 (п.6): Копировать/Вырезать доступны и без выделения —
        действуют на весь текст поля (см. _entry_copy_cut)."""
        widget = event.widget
        menu = tk.Menu(self.root, tearoff=0)
        try:
            editable = str(widget.cget("state")) == "normal"
        except (tk.TclError, AttributeError):
            editable = False

        def run(what: str) -> None:
            widget.event_generate(what)
            widget.focus_set()

        menu.add_command(label=tr("m_copy"),
                         command=lambda: self._entry_copy_cut(widget, False))
        if editable:
            menu.add_command(label=tr("m_paste"),
                             command=lambda: run("<<Paste>>"))
            menu.add_command(label=tr("m_cut"),
                             command=lambda: self._entry_copy_cut(widget, True))
        menu.add_command(
            label=tr("m_select_all"),
            command=lambda: (widget.focus_set(),
                             widget.selection_range(0, "end")))
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _copy_status(self, *_args) -> None:
        """Раунды 12–14: копировать текст статус-строки; пустой статус —
        копируется заголовок окна (с версией); р71 — и правой кнопкой."""
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

    def _apply_model_view(self) -> None:
        """Раунды 43/44 (решение владельца — пресет вместо подавления):
        одним действием выставляет матрицу под реплей контекста:
        «Только актуальный контекст» вкл (срез после уплотнения + model-only),
        инструменты вкл (они в контексте), реплики выкл, лимит
        инструментов 10000 литер — кап ZCode (truncateMiddleForModel,
        исходники; больше в контекст инструмента не попадает)."""
        for fmt in FORMATS:
            self.opt_vars[fmt]["ctx"].set(True)
            self.opt_vars[fmt]["tools"].set(True)
            self.opt_vars[fmt]["narration"].set(False)
        self.tool_limit_var.set(str(TOOL_LIMIT_MODEL_VIEW))
        self._persist()
        self._update_limit_state()
        self._set_status(tr("status_preset_applied"), OK_FG)

    def _options_for(self, fmt: str) -> dict:
        """Поля ExportOptions для колонки формата (fmt добавит job_runner).

        all_files — только у AutoClaw-адаптера (строка матрицы прячется в
        ZCode-режиме); BOM в json невозможен — всегда False.
        р81 (п.4): no_files («Скрыть блоки файлов») удалён — файловые
        блоки показываются всегда.
        """
        opts = self.opt_vars[fmt]
        return {
            "tools": opts["tools"].get(),
            "narration": opts["narration"].get(),
            "tool_limit": self._tool_limit_int(),
            "all_files": (opts["all_files"].get()
                          and self.mode_var.get() == "autoclaw"),
            "bom": fmt != "json" and bool(opts["bom"].get()),
            "lang": i18n.current_lang(),
            # р43: актуальный контекст — только ZCode (в AutoClaw ряд скрыт)
            "context_view": (opts["ctx"].get()
                             and self.mode_var.get() == "zcode"),
            # р60 (я1): версия для футера «Z.ai Chats Exporter …»
            "app_version": APP_VERSION,
        }

    def _options_map(self, formats: list[str]) -> dict[str, dict]:
        return {fmt: self._options_for(fmt) for fmt in formats}

    def _browse_output(self) -> None:
        # р63 (я5): несуществующий путь в поле — диалог открывается в
        # папке самого exe (на W8.1 Tk прежде уводил в «Документы»)
        current = (self.output_var.get() or "").strip()
        if current and Path(current).exists():
            initial = current
        elif getattr(sys, "frozen", False):
            initial = str(Path(sys.executable).resolve().parent)
        else:
            initial = str(config.default_output_dir())
        chosen = filedialog.askdirectory(
            parent=self.root, title=tr("dlg_pick_folder"), initialdir=initial)
        if chosen:
            self.output_var.set(chosen)
            self._persist()
            # р82 (п.3): выбрана корректная папка — снять ошибку р81,
            # если она висела в статусе после «Открыть папку экспорта»
            if self.status_lbl.cget("text") == tr("msg_bad_outdir"):
                self._set_status("")

    def _browse_db(self) -> None:
        # Раунд 17: диалог открывает папку из поля «SQL база» (файл → его
        # папка), а не «любую по выбору Windows» (жалоба с 8.1)
        # р75 (владелец, W8.1): путь из cfg существует → его папка;
        # НЕТ (другой компьютер) → папка самого exe, а не «какая попало»
        raw = self.db_var.get().strip()
        current = Path(raw) if raw else None
        if current and current.is_file():
            initial = current.parent
        elif getattr(sys, "frozen", False):
            initial = Path(sys.executable).resolve().parent
        else:
            initial = config.default_output_dir()
        # р65: в диалоге — ТОЛЬКО главное имя базы режима (db.sqlite /
        # runtime.sqlite из db_profiles); tasks-index и прочие .sqlite
        # не видны (владелец); вручную чужой файл отсечёт _start_import
        main_name = db_profiles.main_file_of(
            self.mode_var.get(), self.db_profiles)  # р67: v3
        chosen = filedialog.askopenfilename(
            parent=self.root, title=tr("dlg_pick_db"), initialdir=str(initial),
            filetypes=[(f"{MODE_LABELS[self.mode_var.get()]} {main_name}",
                        main_name)])
        if chosen:
            self.db_var.set(chosen)
            self._persist()
            # р46/р47 (решение владельца): путь найден — импорт сразу
            # (раньше только перечитывалась старая копия), без поиска
            # дополнительных путей
            self._refresh_db()

    def _startup_data_check(self) -> None:
        """р46: при старте — есть ли локальная копия стартового режима.
        Есть — сразу грузим список из неё; нет → диалог импорта (или
        сообщение «нужен Путь к SQL базе»)."""
        if config.local_db_path(self._mode).is_file():
            self.refresh_list()  # копия есть — список из неё (после 1.42b
            return               # стартовая загрузка живёт здесь)
        self._ensure_local(self._mode)

    def _ensure_local(self, mode: str) -> None:
        """р46: локальной копии нет → мастер из cfg → вопрос импорта;
        мастера нет → сообщение «нужен Путь к SQL базе»; путь cfg битый →
        откат обоих конфигов к начальной («откат к самому началу»)."""
        if config.local_db_path(mode).is_file():
            return
        master = self._resolve_master(mode)
        if master is None:
            self._set_status(
                tr("msg_import_missing", mode=MODE_LABELS[mode]), ERROR_FG)
            return
        if self._dialog(
                "ask", tr("msg_import_ask", mode=MODE_LABELS[mode]),
                yes_no=True):
            self._start_import(mode, master)
        else:
            self._set_status(
                tr("msg_import_missing", mode=MODE_LABELS[mode]), ERROR_FG)

    def _resolve_master(self, mode: str):
        """р46/р70: мастер режима — путь из cfg, если файл существует.
        р70 (владелец): битый путь ≠ битый конфиг — перенесённая на
        другую ОС программа прежде СТИРАЛА оба конфига (.err); теперь
        мёртвый путь просто игнорируется и работает автопоиск по
        db_profiles (найденное пишется ТОЛЬКО в ExportChat.cfg).
        .err — только для действительно повреждённых файлов или чужой
        версии формата (проверяется при старте)."""
        master = self._master_db_path(mode)
        if master and Path(master).is_file():
            return Path(master)
        found = db_profiles.find_db(mode, self.db_profiles)
        if found:
            if mode == self._mode:
                self.db_var.set(str(found))
            self.cfg[f"db_path_{mode}"] = str(found)
            self._persist()
            return found
        return None

    def _master_db_path(self, mode: str) -> str:
        """Мастер-путь режима: текущий — из поля (оно персистится),
        другой — из cfg."""
        if mode == self._mode:
            return self.db_var.get().strip()
        return str(self.cfg.get(f"db_path_{mode}", "") or "").strip()

    def _reset_configs(self) -> None:
        """р46: «откат к самому началу» — оба конфига в .err, заново."""
        for path in (config.config_path(), db_profiles.profiles_path()):
            if path.is_file():
                os.replace(path, Path(str(path) + ".err"))
        self.cfg = config.load()
        self.db_profiles, self.db_profiles_note = db_profiles.load()
        self.db_var.set(self.cfg.get(
            "db_path_zcode" if self._mode == "zcode"
            else "db_path_autoclaw", ""))
        self._set_status(tr("msg_cfg_reset"), ERROR_FG)

    def _start_import(self, mode: str, master) -> None:
        """р46: импорт фоном (job_runner, kind=import) с бегающим
        индикатором; по завершении — перезагрузка списка."""
        if self.runner.busy():
            return
        # р65: выбран не главный файл (вписан вручную tasks-index и
        # т.п.) — только статус-ошибка, импорт не начинаем
        main_name = db_profiles.main_file_of(mode, self.db_profiles)
        if main_name and Path(str(master)).name.lower() != main_name.lower():
            self._set_status(tr("err_not_main_file", name=main_name),
                             ERROR_FG)
            return
        # р64 (E3): мастер = локальная копия — копировать нечего (на
        # W8.1 такое «обновление» могло ПОВРЕДИТЬ базу); только статус
        try:
            same = (Path(str(master)).resolve()
                    == config.local_db_path(mode).resolve())
        except OSError:
            same = False
        if same:
            self._set_status(tr("status_import_self"), ERROR_FG)
            return
        self._begin_busy()
        self._set_status(tr("status_loading"))
        self.runner.submit({"kind": "import", "mode": mode,
                            "master": str(master),
                            "profiles": self.db_profiles})  # р65

    def _autofill_db_var(self) -> None:
        """Раунд 17: поле «SQL база» при старте/первом визите режима не
        пустое: автопоиск нашёл базу — в поле её путь; не нашёл — путь к
        exe (диалог откроет эту папку, а не «любую» Windows)."""
        if self.db_var.get().strip():
            return
        found = self._db_source_path()
        self.db_var.set(str(found) if found
                        else str(config.default_output_dir()))

    def _index_db_path(self) -> str:
        """р46: 2-я база читается из ЛОКАЛЬНОЙ копии (ZCodeData)."""
        local = config.local_index_path()
        return str(local) if local.is_file() else ""

    def _db_source_path(self) -> Path | None:
        """Файл текущей базы: из поля, иначе автопоиск по db_profiles.cfg
        (раунд 19: пути — в отдельном человеко-редактируемом файле)."""
        text = self.db_var.get().strip()
        if text:
            return Path(text)
        return db_profiles.find_db(self._mode, self.db_profiles)

    def _open_folder(self) -> None:
        out_dir = self._resolve_output_dir()
        # р81 (п.5): несуществующий путь (или файл вместо папки) — раньше
        # os.startfile молча падал; теперь честный статус и ничего не открываем
        if not out_dir.is_dir():
            self._set_status(tr("msg_bad_outdir"), ERROR_FG)
            return
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
        # раунд 23: внешний файл нового языка перечитывается при каждом
        # переключении; битый файл — предупреждение
        # р83 (п.2): реестр длинных строк пересобирается по этому чтению
        config.LONG_STRING_FILES.clear()
        lang_note = i18n.set_lang(self.lang_var.get())
        self._long_note = self._long_strings_note()
        self._apply_language()
        if self._long_note:  # р83: жёлтым поверх, следующий статус сменит
            self._set_status(self._long_note, WARN_FG)
        if lang_note:
            self._dialog("warn", tr("lang_corrupt", file=lang_note))

    def _on_hidden_toggle(self, *_args) -> None:
        """Раунд 37: показать/скрыть скрытые чаты (del/arch/wfchld/selchat/auto)."""
        self._persist()
        self._apply_filter()
        if self.rows and not self._batch:
            self._set_status(tr("status_loaded", n=self._chat_count())
                             + self._copy_tail(), OK_FG)
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
        self._set_ctx_visible(new_mode == "zcode")  # р43: контекст — ZCode
        self._apply_language()  # подписи от режима больше не зависят — безвредно
        state = self._mode_state.get(new_mode)
        if state and state.get("rows"):
            self._restore_state(state)
            self._set_status(tr("status_loaded", n=self._chat_count())
                             + self._copy_tail(), OK_FG)
        else:
            # первое посещение режима: своё значение поля «База»
            self.db_var.set(self.cfg.get(
                "db_path_zcode" if new_mode == "zcode"
                else "db_path_autoclaw", ""))
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

    def _set_ctx_visible(self, visible: bool) -> None:
        """Раунд 43: «Только актуальный контекст» — только в ZCode (у AutoClaw
        model_usage нет)."""
        widgets = [self.matrix_labels["ctx"]] + [
            self.matrix_checks[("ctx", fmt)] for fmt in FORMATS]
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
            "show_subagents": self.show_hidden_var.get(),
            "last_mode": self._mode,  # р44 (v5): режим этой сессии
            "output_dir": self.output_var.get().strip(),
            "db_path_autoclaw": self.db_var.get().strip() if self._mode == "autoclaw"
                                else self.cfg.get("db_path_autoclaw", ""),
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
            if not self._dialog(
                    "ask", tr("confirm_exit_title") + ": "
                    + tr("confirm_exit_msg"), yes_no=True):
                return
            self.runner.cancel()
        self._persist()
        self.root.destroy()
