# API_CONTRACT — контракт между GUI и движками экспорта

> **АРХИВ (раунд 19, 2026-11-15).** Движки слились с GUI в один процесс
> (один exe без CLI) — контракт subprocess+/api больше не действует.
> Текущий внутренний интерфейс — `backend/adapter.py` (AdapterError,
> ExportOptions, adapter_for); места баз — секция `db_profiles` в
> config.json (`frontend/db_profiles.py`). Файл сохранён как история
> решений ER-1..ER-5 (BOM-политика, суффиксы « (1)», /single-file —
> всё это живёт в адаптерах).

Версия контракта: 1.1 (AutoClaw-движок 1.4+, ZCode-движок 1.4+).
Статус: стабильный. Изменения — аддитивные, по согласованию
с владельцем проекта. Изменения 1.0 → 1.1: `/single-file`, `/no-bom md|txt|all`,
суффиксы « (1)» вместо перезаписи, ошибки аргументов — JSON + код 2,
добавлен ZCode-движок (права на доработку движков — AGREEMENTS.md, раунд 3).

Расположение движков в репозитории:
- `backend/export_chat.py` — AutoClaw-движок (режим «AutoClaw Chats»);
- `backend/zcode_export.py` — ZCode-движок (режим «Zcode Chats»).

Рабочая копия AutoClaw: `C:\zcode_prj\z5_autoclaw_dir\export_chat.py`
(только чтение; новые версии кладёт AutoClaw).

## Общие правила (для обоих движков)

1. Запуск: `python backend/<движок>.py <ключи>` (из корня репозитория); все ключи
   начинаются с `/`.
2. stdout/stderr — UTF-8. Файлы: md/txt — с BOM по умолчанию, json — без BOM.
3. Коды выхода: `0` — успех; `1` — ошибка выполнения; `2` — ошибка аргументов.
   В режиме `/api` любая ошибка уходит в stderr как JSON
   `{"ok": false, "error": "failed", "message": "..."}` (включая ошибки
   аргументов — ER-1).
4. Ключи с `-` или `--` запрещены и дают код 2.
5. Пути с пробелами передавать одним элементом списка аргументов.
6. Файлы никогда не перезаписываются (ER-5): если имя занято, добавляется
   суффикс ` (1)`, ` (2)`, ` (3)`… Путь фактического файла возвращается в JSON.

## Ключи

| Ключ | Минимум | Назначение |
|---|---|---|
| /list | /l | список диалогов |
| /chat <id\|title> | /c | какой диалог экспортировать |
| /out <file> | /o | имя файла результата |
| /all | /a | экспортировать все диалоги по отдельности |
| /single-file | /s | упаковать все диалоги в ОДИН файл (ER-2; с /dir) |
| /dir <folder> | /d | папка для /all и /single-file |
| /format md\|txt\|json | /f | формат |
| /lang ru\|en\|zh | /la | язык подписей |
| /tools | /t | включить вызовы инструментов (действует для md/txt/json — ER-4) |
| /narration | /n | промежуточные реплики (для md/txt/json — ER-4) |
| /no-files | /no-f | скрыть блоки файлов |
| /all-files | /all-f | показать служебные файлы (только AutoClaw-движок) |
| /tool-limit <N> | /tool-l | лимит символов результата инструмента |
| /no-bom [md\|txt\|all] | /no-b | без BOM: без значения — md и txt; можно по-форматно (ER-3) |
| /db <path> | /db | путь к базе |
| /ver | /v | версия |
| /help | /h, /? | справка |
| /api | /api | машинный режим: JSON в stdout |

## Команды (AutoClaw-движок)

```
python export_chat.py /list /api                     -> JSON-массив диалогов
python export_chat.py /chat <id|title> /out <файл> /api
                                                     -> {"ok":true,"path":...,"requests":N}
python export_chat.py /all /dir <папка> /api         -> {"ok":true,"dir":...,"exported":[...]}
python export_chat.py /single-file /dir <папка> /api -> {"ok":true,"path":...,"sessions":N,"requests":N}
python export_chat.py /ver                           -> AutoClaw.Z.ai-ExportChat 1.4
```

База: `%APPDATA%\AutoClaw*\accounts\<id>\runtime\runtime.sqlite` (mode=ro).
Имена: `AC-ГГГГ-ММ-ДД-<название>.<ext>` + суффиксы ` (1)`… при совпадениях
(ER-5); суффиксы `-2`, `-3` остались только внутри одного запуска `/all`.

## Команды (ZCode-движок)

```
python zcode_export.py /list /api                      -> JSON-массив диалогов
python zcode_export.py /chat <id|title> /out <файл> /api
                                                       -> {"ok":true,"path":...,"requests":N}
python zcode_export.py /single-file /dir <папка> /api  -> {"ok":true,"path":...,"sessions":N}
python zcode_export.py /ver                            -> AutoClaw.Z.ai-ExportChat zcode 1.4
```

База: `~/.zcode/cli/db/db.sqlite` (таблицы session/message/part; mode=ro,
при блокировке приложением — временная копия). Имена: `ZC-ГГГГ-ММ-ДД-<название>.<ext>`,
упаковка — `ZC-ALL-ГГГГ-ММ-ДД.<ext>`. Отличия от AutoClaw-движка: нет
`/all-files`; вложения — из `file`-частей (имя/путь/mime); в json turns есть
`tools` и `narration`. Замороженный exe один на оба движка: флаг запуска
`--zcode` выбирает ZCode-движок (см. `build/engine_shim.py`).

## Гарантии движков

- Базы читаются только на чтение (mode=ro).
- md/txt пишутся с BOM по умолчанию; json — никогда; `/no-bom md|txt|all`
  управляет по-форматно (ER-3).
- Имена файлов: `AC-…` / `ZC-…`; запрещённые символы -> `_`, обрезка до 80,
  без перезаписи — суффиксы ` (1)`, ` (2)`… (ER-5).
- Служебные директивы `:zwork-file-citation{...}` в текст не попадают
  (AutoClaw-движок).
