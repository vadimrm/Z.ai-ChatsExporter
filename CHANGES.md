# What's new in ver. 2.00 (compared to 1.27)

English · [Русский](CHANGES.ru.md) · [中文](CHANGES.zh.md)

Since 1.27 there have been 49 intermediate versions (18 betas and 31 RCs). Below are the highlights from the user's point of view.

## Data safety

- **Local database copies**: the program reads only its own copies (ZCodeData / AutoClawData next to the exe); the source AutoClaw/ZCode databases are never modified.
- **Safe import**: refreshing a copy goes through the SQLite backup API — AutoClaw/ZCode can stay open; the file is verified before replacement and everything rolls back on failure.
- **Three backup copies** of every database (including -wal/-shm): `.bak1` (newest) through `.bak3` in the ZCodeData / AutoClawData folders.
- **Deleted chat recovery**: until the copy is refreshed, a deleted dialog is still visible; see the README ("Deleted chats and recovery").

## Working with chats

- **Hidden chats**: the "Show hidden chats" checkbox; types `del` (deleted), `arch`, `wfchld`, `selchat`, `auto` appear in the "Type" column.
- The **"Tokens"** column — the chat's context size; sorting and search kept.
- "Export to one file" and the per-format option matrix — as before, but file blocks are now **always shown** (previously a checkbox could hide them).
- "Show service files" (AutoClaw) — scripts and drafts the agent created along the way.

## Export header

A full header in md/txt/json for both engines: harness core (the ZCode built-in core version), project, type, session, directory, dates, **"Messages: N / M (prompts/answers)"**, files, models with effort, **tokens**: "Chat context: 28,019 tokens (2.8%/1M)" (AutoClaw: "16,161 of 1M (1.5%)"), "Auto-compact at", "Total spent"; the exporter signature line and footer. Answers carry the author model and the working time.

## The new "current context" mode

- The **"Current context only"** checkbox (ZCode) and the **"Preset: model's current context"** button: the export shows what the model actually sees after the last auto-compaction — the compacted-history summary as a separate block, the "live tail", and service messages invisible to the user.
- Auto-compaction boundary markers in regular exports.

## Interface

- **All dialogs are custom** — their text is selectable and copyable (Ctrl+C / right-click).
- **Right-click copying from any element**: input fields (without a selection — the whole text), the table row under the click (not the selection), the table header (all columns; a separate "Copy header and chat list" item), the status line, the window title.
- Status line: green/yellow/red; yellow notes ("db_profiles.cfg not found", "Too long strings in file…", the "minimal set" note after import) survive list loading; switching the language translates the status.
- "Open export folder": with an invalid path — the "Invalid export folder" status (cleared once a valid folder is chosen); file dialogs open in sensible folders (matters on Windows 8.1).
- The first launch starts in Zcode Chats mode.
- The exe icon is the "quill feather" (same as the program window).

## Configuration

- **db_profiles.cfg v3**: the full file list of every database with relative paths; the format version is checked on read; when storage moves, just edit the text.
- **ExportChat.cfg v7** with automatic migration of older versions; strict structure validation (a damaged file is kept as `.err`, a factory one is created).
- **Protection against overly long strings**: any string from cfg/lang files longer than 500 characters is trimmed, and the file name is shown as a yellow note.
- The `lang_ru/en/zh.cfg` language files are plain-editable and re-read on the fly.

## Misc

- Empty chats export (a header, no error); a database cannot be copied "into itself" (previously this could damage it); a failing file doesn't abort the batch.
- Service messages (forks, rewinds) no longer leak as fake replies; context copies are labeled "Context".
- Three interface and export languages; the number of automated checks grew from ~230 to 633.
