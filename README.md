# Z.ai Chats Exporter by Vadim R.M. ver. 1.27

Project **AutoClaw.Z.ai-ExportChat**: export AutoClaw and ZCode chats to Markdown, TXT and JSON

A Windows desktop app: reads the local AutoClaw and ZCode chat databases and saves conversations to files — Markdown, plain text or JSON. One exe, no Python installation needed: the database adapters run in the same process as the window (AGREEMENTS.md, round 19 — the engines merged into the GUI, the command line is gone).

Unofficial tool. Not affiliated with Z.ai, works only with the local databases and never goes online.

**English** · [Русский](README.ru.md) · [中文](README.zh.md)

Copyright © 2026 by Vadim Madgazin & ZCode (Z.ai)

## Features

- two modes: **AutoClaw Chats** (runtime.sqlite) and **Zcode Chats** (db.sqlite) — each with its own list, selection and database path;
- conversation table: per-row tick boxes (the first chat is ticked by default), sorting by any column — a click toggles direction (▲/▼), search by title;
- export selected chats × selected formats (MD / TXT / JSON) — N×M files in one run, with "k of N" progress and an error summary; one failed chat does not stop the others;
- "Export to one file" checkbox: off — every selected chat is written to its own file; on — all SELECTED chats are packed into one file per format (header "Selected … chats", names AC-ALL-/ZC-ALL-date); "Select all" + checkbox = the whole mode in one file;
- per-format options matrix (each column configures its own format): tool calls (+ shared result-length limit), intermediate replies, service files (AutoClaw only), hidden file blocks, UTF-8 BOM;
- labels of the exported files in Russian (default), English or Chinese; the interface switches on the fly;
- the database is opened read-only (mode=ro), so AutoClaw/ZCode can keep running; if the ZCode database is locked, a temporary copy is read;
- files are never overwritten: a repeat export gets a ` (1)`, ` (2)`… suffix;
- file names: `AC-YYYY-MM-DD-<chat title>.<ext>` / `ZC-YYYY-MM-DD-<chat title>.<ext>`; in the ZCode mode chats are additionally sorted into project folders.

## Install and run

The ready-made build needs no Python: download **ExportChat.exe** from Releases and double-click it.

Settings live in `ExportChat.cfg` next to the exe (created on first start; portable; the registry and %APPDATA% are never touched; UTF-8 with BOM — easy to edit even in old Notepad). The standard file names and all standard locations of both databases live in a separate human-editable **db_profiles.cfg** (shipped next to the exe; with a note on which AutoClaw/ZCode versions the paths were verified against): the program reads it at startup and never overwrites it — if an app changes where it keeps its database, just fix the paths with a text editor, no exe rebuild needed. If the file is deleted or corrupted, the program tells you, keeps the broken file as `db_profiles.cfg.err` and writes the factory one.

From sources (Python 3.10+):

```bat
python frontend\main.py
```

Rebuild the exe with `build\build.bat` (PyInstaller). Architecture and work plan: `GUI_PLAN.md`; variant analysis: `GUI_VARIANTS.md`; change log: `AGREEMENTS.md`.

## Interface (short)

- "Export folder" + path field — the common parent output folder (by default, the exe folder); chats go into `AutoClaw Chats` / `ZCode Chats` subfolders, database copies ("Export SQL database" button) — into `AutoClaw SQL` / `ZCode SQL`;
- "SQL database" — pick the database file: the chat list loads immediately; "Refresh chats" re-reads it; autodetect checks only the standard locations from `db_profiles.cfg` — no registry, no disk scan;
- "Open export folder" — Explorer (after an export, with the last file selected);
- status bar texts and the window title are copyable: Ctrl+C in the window or a right-click on the status line; the export-errors dialog has a Copy button;
- a second launch does not create a copy: the existing window is brought to the front;
- "Donate" and the author-site button — <https://www.vmgames.com/>.

## Files in the export

- **Attached** — taken from the `Attached workspace files` block in the request text: name, type, size. The block itself is removed from the message body (AutoClaw).
- **Created** — read from the `governed_tool_artifacts` table and linked by `tool_call_id`, so a file lands in the turn where it appeared (AutoClaw).
- **"Ready to download"** — files the agent handed over through `deliver_file` (AutoClaw).
- **"Show service files"** — additionally shows everything created along the way: scripts, drafts, patches (AutoClaw).
- ZCode attachments — from the `file` parts of a message: name, path, MIME.

File names are printed in double quotes; service directives such as `:zwork-file-citation{...}` never reach the output.

## Formats

| Format | Content |
| --- | --- |
| `md` | Markdown kept as is: headings, lists, tables, code |
| `txt` | Markdown stripped to plain text: no `**`, backticks, `#`, table pipes; lists become `•`, links become `text (url)` |
| `json` | Structure: `session` plus `turns[]`, each turn holds `request`, `attachments`, `answers`, `tools`, `narration` |

A UTF-8 BOM (three bytes `EF BB BF`) is written by default to `.md` and `.txt` (the "UTF-8 Byte Order Mark" checkbox in the matrix, per format). JSON files never get a BOM — strict parsers reject it.

## How it works

AutoClaw — `%APPDATA%\AutoClaw*\accounts\<id>\runtime\runtime.sqlite`, tables:

- `work_sessions` — the list of conversations;
- `neutral_session_entries` — messages (requests, answers, tool calls);
- `governed_tool_artifacts` — created files.

ZCode — `~/.zcode/cli/db/db.sqlite`, tables `session` / `message` / `part`; subagent sessions are filtered out, and if the database is locked by the app, a temporary copy is read.

The connection is opened in `mode=ro`; nothing is ever written to the databases. Adapters — `backend/adapter.py` (`AutoClawAdapter`, `ZCodeAdapter`); database locations — `frontend/db_profiles.py` + the `db_profiles.cfg` file next to the exe.

## Limitations

- The database schemas are internal and undocumented: an AutoClaw/ZCode update may change them. When that happens the app reports the problem instead of damaging data; database locations can be fixed in db_profiles.cfg without a rebuild.
- `txt` loses formatting — that is its purpose.
- With tool calls enabled files grow quickly: a single turn can hold 60+ calls.
- Images and binaries are not exported — only names, types and sizes.
- The tool is not affiliated with Z.ai and is not an official export feature.

## Troubleshooting

Copy the error text (Ctrl+C in the window, or the "Copy" button in the export-errors dialog) and send it to the author — without the exact text the cause cannot be found.

## Links

Repository: <https://github.com/vadimrm/AutoClaw.Z.ai-ExportChat>

## License

MIT — see the `LICENSE` file.

Authors: Vadim Madgazin, AutoClaw.Z.ai
