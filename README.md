# Z.ai Chats Exporter by Vadim R.M. ver. 2.00

Export local **AutoClaw** and **ZCode (Z.ai)** chats to Markdown, TXT and JSON — including **deleted and hidden** dialogs.

A Windows desktop program: it reads the local AutoClaw and ZCode chat databases and saves conversations to files. A single exe, no Python required. The program works only with **local copies** of the databases — you don't need to close AutoClaw/ZCode; the source databases are opened read-only.

An unofficial tool. Not affiliated with Z.ai; never touches the network.

**English** · [Русский](README.ru.md) · [中文](README.zh.md)

Copyright © 2026 by Vadim Madgazin

![Screenshot](screenshots/ZAICHEXP-ver-2.00.png)

## Features

- two modes — **Zcode Chats** (db.sqlite) and **AutoClaw Chats** (runtime.sqlite); the first launch starts in Zcode Chats;
- chat table: checkmark selection, sorting by any column, search; columns "Project", "Type", "Count", "Tokens" (context size), dates;
- **hidden and deleted chats**: the "Show hidden chats" checkbox reveals dialogs marked `del` (deleted), `arch` (archived), `wfchld`, `selchat`, `auto` — see "Deleted chats" below;
- export the selected chats × the MD / TXT / JSON formats (N×M files per run) or everything into one file;
- a detailed header in every export: project, type, session, dates, "Messages: N / M (prompts/answers)", files, models, **context tokens with the share of the model window** ("Chat context: 28,019 tokens (2.8%/1M)"), auto-compact threshold, total tokens spent;
- file blocks are always shown: user attachments and "Ready to download" (files delivered by the agent); for AutoClaw there is a "Show service files" option (scripts and drafts created along the way);
- tool calls and intermediate replies — via checkboxes with a length limit; the "Current context only" preset exports what the model actually sees after auto-compaction (a compacted-history summary plus the live tail);
- safe database import: the local copy is refreshed via the SQLite backup API (works while AutoClaw/ZCode are running); before replacement it is verified, and the **three previous versions** are kept (ZCodeData / AutoClawData next to the exe);
- every text in the program can be copied: custom dialogs with selectable text, right-click anywhere in the GUI (fields, table rows and header, status line, window title);
- interface and export language: Russian, English, Chinese; all strings live in editable `lang_*.cfg` files next to the exe;
- fully portable: no installation, no registry, no %APPDATA%; the icon is the Tk "quill feather".

## Deleted chats and recovery

The exporter shows even **deleted** chats: until the local database copy is refreshed, the dialog is still alive in it.

> **Deleted a chat by accident?** Don't close ZCode (AutoClaw). Run the exporter and search for the chat by name — most likely it is still intact in your local database copy. If it isn't there, refresh the local SQL database with the "Refresh SQL database" button, enable "Show hidden chats" and look for a dialog marked `del`.
>
> **General recommendation:** refresh the local SQL database at the end of your workday. The exporter keeps the three previous database versions in the `ZCodeData` (`AutoClawData`) folders next to `ExportChat.exe`, so a chat deleted yesterday can be restored from the previous copy (`.bak1`–`.bak3`).

## Requirements

- Windows 8.1 or newer, 64-bit (tested on 8.1, 10 and 11);
- Python, AutoClaw and ZCode are not required on the machine: databases are ordinary files — bring them on a flash drive and point the program at them with the "SQL database path" button.

## Install and run

Download `ExportChat.exe` from the [release](release/) folder (or from [Releases](https://github.com/vadimrm/Z.ai-ChatsExporter/releases)), put `db_profiles.cfg` and `lang_*.cfg` from the same folder next to it — and double-click. Settings (`ExportChat.cfg`) are created next to the exe on first launch.

From sources (Python 3.10+): `python frontend\main.py`. Rebuilding the exe — `src\build\build.bat` (PyInstaller).

A detailed description of every interface element is in [MANUAL.md](MANUAL.md); changes since version 1.27 — in [CHANGES.md](CHANGES.md).

## Formats

| Format | Contents |
| --- | --- |
| `md` | Markup is preserved as is: headings, lists, tables, code |
| `txt` | Plain text: markup is stripped, lists become `•`, links — "text (address)" |
| `json` | Structure: `session` (header) + `turns[]` with requests, answers, attachments, tools |

File names: `AC-date-name.ext` / `ZC-date-name.ext`; re-exporting never overwrites (suffix ` (1)`, ` (2)`…). BOM in `.md`/`.txt` — via a checkbox (on by default); never in JSON.

## How it works

The program reads **local copies** of the databases: AutoClaw — `%APPDATA%\AutoClaw*\accounts\<id>\runtime\runtime.sqlite`, ZCode — `~/.zcode/cli/db/db.sqlite` (+ `tasks-index.sqlite`). The copy is created/refreshed with the "Refresh SQL database" button via the SQLite backup API — consistent even while AutoClaw/ZCode are running; the source databases are never modified. Database paths are configured in the human-editable `db_profiles.cfg` (v3) next to the exe — if storage moves, just edit the text; no rebuild needed.

## Repository layout

- `release/` — the ready package: `ExportChat.exe`, `db_profiles.cfg`, `lang_*.cfg`, a quick guide;
- `src/` — sources (backend — export engines, frontend — GUI and tests, build — packaging);
- `screenshots/` — screenshots;
- `docs/dev/` — historical project documents.

## Limitations

- The database schemas are internal and undocumented: an AutoClaw/ZCode update may change them (the program will then report the error honestly and won't touch the data).
- Images and binary attachments are not exported — only names, types and sizes.
- With tool calls enabled, files grow quickly.

## Troubleshooting

Open a bug report on GitHub:

1. go to <https://github.com/vadimrm/Z.ai-ChatsExporter/issues> and press **New issue**;
2. describe the problem and the steps that lead to it;
3. attach the status line or error window text — it is copyable via right-click or Ctrl+C — and mention the program version (shown in the window title).

## License

MIT — see the [LICENSE](LICENSE) file.
