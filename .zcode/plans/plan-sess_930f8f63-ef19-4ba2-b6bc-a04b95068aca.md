## Context

Приёмка v4 выявила три вопроса пользователя. Пункты 1–2 (BOM, скрытие /all-files) — объяснены в чате, кода не требуют. Пункт 3 вскрыл реальный дефект: поле «База» в GUI **одно на оба режима** — путь, заданный для AutoClaw, при переключении на Zcode Chats передаётся zcode-движку (и наоборот), который падает с необработанным traceback («no such table»), вместо понятного сообщения. Плюс подготовка инструкции «чистая машина» (Windows 8.1) для ACCEPTANCE. Ветка main, последний коммит a74e4dd; после реализации — коммит.

## Изменения

### 1. GUI: путь базы отдельно на каждый режим (frontend/app.py, frontend/config.py)
- `config.py` DEFAULTS: добавить ключ `"db_path_zcode": ""` (версия 3 сохраняется — load и так доливает недостающие ключи из DEFAULTS).
- `app.py`: `_stash_state()` / `_restore_state()` — хранить и восстанавливать `db` (значение db_var) в `_mode_state` наравне с rows/checked; при переключении режима поле подменяется значением своего режима.
- `_persist()`: писать `db_path` при `self._mode == "autoclaw"`, `db_path_zcode` при zcode (значение из db_var).
- `_apply_language()`: подпись поля по режиму — новый i18n-ключ `lbl_db_zcode` («База (db.sqlite):») для zcode; вызывать `_apply_language()` в `_on_mode_change()` (обновит и подпись).

### 2. Движки: чистая ошибка «это не база» (backend/zcode_export.py, backend/export_chat.py)
- zcode: в `connect_ro()` после открытия (и прямой ветки, и ветки копии) проверять наличие таблицы `session` через sqlite_master; нет → `SystemExit((t("err_db_invalid", p=db), 1))`.
- autoclaw: в `main()` после `connect(db)` проверять таблицу `work_sessions`; нет → `SystemExit(t("err_db_invalid", p=db))` (код 1; в /api уйдёт JSON).
- i18n оба движка + GUI: ключ `err_db_invalid` («В файле нет таблиц диалогов — это не база ZCode/AutoClaw: {p}») и `lbl_db_zcode` (только GUI).
- `__version__` обоих движков 1.5 → 1.6.

### 3. Тесты
- `test_zcode_smoke.py`: Z-db — `/db <путь к runtime.sqlite AutoClaw>` (реальный файл с машины) → rc=1 + stderr JSON с «не база ZCode».
- `test_engine_smoke.py`: симметрично — `/db <C:\Users\Вадим\.zcode\cli\db\db.sqlite>` → rc=1 + JSON.
- `test_units.py`: DEFAULTS содержит `db_path_zcode`; roundtrip сохраняет оба ключа.
- `gui_selftest.py`: переключение режимов сохраняет/восстанавливает разные значения поля «База»; подпись поля меняется с режимом.

### 4. Документы
- `ACCEPTANCE.md`: раздел «Проверка на чистой машине (Windows 8.1)» — таблица путей баз, копирование при закрытом приложении, использование «База (Обзор)» в каждом режиме, ожидания (списки загружаются, экспорт работает); пункт про /all-files в zcode-режиме пояснён.
- `AGREEMENTS.md`: раунд 6 — вопросы 1–3 (BOM-объяснение, /all-files объяснение, db-поле фикс).
- `README.ru.md`/`README.md`/`README.zh.md`: в GUI-разделе одна строка про то, что путь базы хранится отдельно для каждого режима.

## Проверка (end-to-end)
1. Прогон всех наборов: `test_zcode_smoke`, `test_engine_smoke`, `test_units`, `gui_selftest`, `test_release` — все зелёные.
2. Пересборка `build\build.bat` (через powershell — Git Bash искажает cmd /c), повторный `test_release`.
3. Ручная логика: в AutoClaw Chats задать путь runtime.sqlite → переключиться на Zcode Chats → поле пустое/своё; указать db.sqlite → экспорт работает; обратно — путь runtime.sqlite вернулся.
4. Коммит в main (по образцу прошлых раундов), отчёт с хешем и статусом.