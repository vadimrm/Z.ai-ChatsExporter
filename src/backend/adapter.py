# -*- coding: utf-8 -*-
"""Внутренний шов «адаптер базы» (AGREEMENTS.md, раунд 19).

После слияния движков в GUI (один exe, без CLI) оба движка — обычные
модули, а этот файл задаёт их общий интерфейс:

- AdapterError      — понятная пользователю ошибка (сообщение уже на нужном
                      языке; GUI показывает его как есть);
- ExportOptions     — параметры одного экспорта (формат + матрица опций GUI
                      + язык подписей файла);
- adapter_for(mode) — фабрика адаптеров: "autoclaw" | "zcode".

Интерфейс адаптера (обе реализации):
    open(db_path)                      -> соединение (проверка «та ли база»)
    list_chats(con)                    -> [{id, title, created_at, updated_at,
                                           created_local, updated_local, requests,
                                           directory? (ZCode)}]
    export_chat(con, chat_id, out_dir, options) -> {"path": str, "requests": int}
    export_single_file(con, out_dir, options)   -> {"path": str, "sessions": int,
                                                     "requests": int}
    close(con)                          -> закрыть соединение (ZCode — убрать
                                           временную копию, если создавалась)

Имена файлов (AC-/ZC-, суффиксы « (1)»), BOM-политика и содержимое рендеров
не меняются — см. таблицы LABELS и рендеры самих движков. Шов сознательно
узкий: если формат баз сменит AutoClaw/ZCode, правится только адаптер (или
добавляется новый) — это задел под возможные плагины (решение владельца:
плагины не закладываются, но шов обязан существовать).
"""
from __future__ import annotations

from dataclasses import dataclass


class AdapterError(Exception):
    """Ошибка адаптера с готовым человекочитаемым сообщением."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class ExportOptions:
    """Параметры одного экспорта (колонка матрицы формата в GUI)."""

    fmt: str = "md"            # md | txt | json
    tools: bool = False        # вызовы инструментов (md/txt/json)
    narration: bool = False    # промежуточные реплики
    tool_limit: int = 1000     # обрезка результата инструмента, символов
    all_files: bool = False    # служебные файлы (только AutoClaw; ZCode игнорирует)
    bom: bool = True           # BOM в md/txt (в json невозможен — всегда False)
    lang: str = "ru"           # язык подписей в экспортируемом файле
    context_view: bool = False  # р43: «как видит модель» — срез после
    # последнего уплотнения + сводка + model-only (только ZCode; AutoClaw
    # игнорирует)
    app_version: str = ""       # р60 (я1): версия экспортёра для футера


def adapter_for(mode: str):
    """Адаптер по имени режима GUI. Ленивый импорт — движки живут рядом."""
    if mode == "zcode":
        from zcode_export import ZCodeAdapter

        return ZCodeAdapter()
    from export_chat import AutoClawAdapter

    return AutoClawAdapter()
