# Z.ai Chats Exporter — detailed interface description (ver. 2.00)

English · [Русский](MANUAL.ru.md) · [中文](MANUAL.zh.md)

A companion to [README.md](README.md): every window element, status, configuration file and behavior detail. Where this document and the program disagree, trust the program.

![The program interface](screenshots/ZAICHEXP-ver-2.00.png)

## 1. General

- A single exe (`ExportChat.exe`), fully portable: settings, language files and local database copies live next to the exe; no registry, no %APPDATA%.
- The source AutoClaw/ZCode databases are never modified: the program works with its own copies (SQLite backup API, `mode=ro` reads).
- Launching again does not open a second window: the existing one is brought to the front.
- Minimum system: Windows 8.1 (64-bit).

## 2. Window title

"Z.ai Chats Exporter by Vadim R.M. ver. N.NN — …". The icon is the "quill feather" (the exe icon matches the window icon). A right-click on empty window space copies the full title.

## 3. Modes and the chat list

- Radio buttons **Zcode Chats** / **AutoClaw Chats** (Zcode on the left; the first launch opens in it; afterwards the last mode is remembered). Switching the mode changes the list, the database path and the option-matrix row visibility.
- The **"Show hidden chats"** checkbox reveals dialogs hidden by default. The "Type" column shows the reason: `del` — deleted, `arch` — archived, `wfchld` — a workflow agent's child session, `selchat` — a context copy (side-chat), `auto` — a service dialog; empty ("—") — a normal visible chat.
- **Search** — a case-insensitive chat-title filter.
- Table columns: ☑, "Project", "Chat", "Type", "Count" (prompts/answers), "Tokens" (the last request's context size), "Updated", "Created". Clicking a header sorts ascending/descending. The first chat is checked by default.
- **Right-click on a row** — "Copy text: …" copies the row **under the cursor** (all columns joined with " | "), regardless of the blue selection.
- **Right-click on the table header** — two items: copy all column headers, and "Copy header and chat list" (the header plus every chat shown by the current filter; hidden chats are not included).

## 4. Databases: path, local copy, refresh

- The **"SQL database path"** field + button: pick the master file (`runtime.sqlite` for AutoClaw, `db.sqlite` for ZCode). The dialog opens in a sensible folder: the config path if it exists, otherwise the exe folder.
- The program works with a **local copy** of the master (ZCodeData / AutoClawData next to the exe). If there is none, it asks at startup ("Local data copy is missing — import?") and copies the master; if the master is missing, an honest status with a hint is shown.
- The **"Refresh SQL database"** button — a safe import: the master is copied to a temporary file, verified against the expected tables, then the old copy rotates into backups (`.bak1`–`.bak3`, the three previous versions) and the new one takes its place. On failure everything rolls back to `.bak1`; a garbage file never touches the local copies.
- Copying uses the SQLite backup API — **you don't need to close AutoClaw/ZCode**. The "master = local copy" case is rejected with a status (it used to be able to damage the database).
- For ZCode the second database, `tasks-index.sqlite`, is copied too (needed for project names); if it is not found via the config, it is looked up next to the master; failing that, the import is "minimal" and a yellow note about reduced functionality appears.
- Import statuses: green "Copy imported", yellow "minimal set…", red on errors.

## 5. Export folder

- The **"Export folder"** field + "Browse…" — the parent folder; chats go into "ZCode Chats" / "AutoClaw Chats" subfolders, inside those — by project folders (ZCode).
- The **"Open export folder"** button opens the folder in Explorer, after an export — with the last file selected. If the path does not exist (or is a file) — the red status **"Invalid export folder"**; choosing a valid folder via "Browse…" clears it.
- Files are never overwritten: re-exporting the same chat adds ` (1)`, ` (2)`…

## 6. Formats and the option matrix

The **MD / TXT / JSON** checkboxes select the formats; the option matrix configures each format separately:

- **"Include tool calls"** — `🔧 Name — status` blocks with the JSON call and the result; the shared **"Max result length, chars"** limit clips both.
- **"Intermediate replies"** — the AI's reasoning/progress text between tool calls.
- **"Show service files"** (AutoClaw only) — "Other files:" blocks with scripts and drafts created along the way (delivered files — the "Ready to download:" block — and user attachments are always shown).
- **"UTF-8 Byte Order Mark"** — BOM in `.md`/`.txt` (for old Notepad); in JSON the cell is gray — BOM is impossible there.
- **"Current context only"** (ZCode only) — the slice the model sees **now**: everything before the last auto-compaction is replaced by a machine summary ("Compacted-history summary"), the live tail remains; service messages invisible in the GUI but present in the context are included. In normal mode compaction boundaries are only marked.
- The **"Preset: model's current context"** button — one click: current context on, tools on, replies off, limit 10000 (ZCode's hard cap).
- The **"export to one file"** checkbox — all selected chats pack into one file per selected format (names `AC-ALL-…` / `ZC-ALL-…`); "Select all" + the checkbox = the whole mode in one file. Empty chats are included (header only).

## 7. Status line

- Colors: green — success/info, yellow — warning, red — error. Examples: "Chats: 48 · copy from 2026-11-23 13:08", "Loading chat list…", "Done: N files, M errors".
- Yellow notes: "db_profiles.cfg not found/damaged — factory file written", "Too long strings in file: (name)" (config/language-file strings over 500 characters are trimmed), the "minimal set" note after an import without the second database. Notes appear immediately and don't resurface after the list loads.
- The status text is copied with Ctrl+C or right-click; an empty status copies the window title.

## 8. Copying text (right-click)

- **Input fields** (database path, folder, search, limit): Copy/Paste/Cut/Select all; without a selection the **whole** field text is copied/cut.
- **Any GUI element** (button, checkbox, label): "Copy text: …".
- **Table row** — under the click; **table header** — all columns (+ "header and chat list"); **empty window space** — the window title; **status line** — its text.
- Custom dialogs (questions, warnings, errors): the text sits in a selectable text widget — mouse selection, Ctrl+C, right-click.

## 9. Languages

The ru/en/zh switch changes the interface and the labels inside exported files. All strings live in `lang_ru.cfg`, `lang_en.cfg`, `lang_zh.cfg` next to the exe: edit them as text, the program re-reads the file on every language switch; a broken file triggers a warning and the built-in strings are used. Strings over 500 characters are trimmed with a yellow note.

## 10. Configuration files

- **`ExportChat.cfg`** (v7, UTF-8 BOM, JSON) — GUI settings: language, folder, master paths, the option matrix, limit, window geometry, mode. Created on first launch; older versions (v6 and up) migrate automatically; a foreign structure — the file is kept as `.err` and a factory one is created.
- **`db_profiles.cfg`** (v3, UTF-8 BOM, JSON with hints) — standard database names and paths, the file set of every database (relative to the main one, including wal/shm and ZCode's second database), a `_version` marker. Human-editable: the app moved its database — fix the text, leave the exe alone. Missing — a factory file is created (yellow note); damaged — `.err` + factory.
- **`lang_*.cfg`** — see section 9.

## 11. Exported files

- Names: `AC-YYYY-MM-DD title.ext` / `ZC-YYYY-MM-DD title.ext`.
- **Header** (md/txt/json): "Harness core: ZCode 0.17.1" (the ZCode built-in core version, not the app) or "Harness: AutoClaw"; Project; Chat; Type; Session; Directory (ZCode); Created/Updated; **Messages: N / M (prompts/answers)**; Files (attached/ready to download); Models (with effort for ZCode); **Chat context: 28,019 tokens (2.8%/1M)** — AutoClaw style: "16,161 of 1M (1.5%)" plus "Auto-compact at: 812 K (77%)"; Total spent; Exported; the exporter signature line (framed with dashes in txt, plus a footer after every chat).
- **Body**: turns "### N. You — date" → request text → "📎 Attached:" (always) → tools → answers with the author ("GLM-5.3 Max — date (3 min 58 sec)"); for AutoClaw after the answers — "📄 Ready to download:" and, with the option enabled, "Other files:".
- **TXT**: markup is parsed into plain text, code becomes "python { … }" blocks, headings get dash underlines.
- **JSON**: `session` (the same header) + `turns[]` with `request/attachments/answers/tools/narration`.

## 12. Deleted chats: practical scenarios

1. **Just deleted a chat, apps still open** — run the exporter without closing ZCode/AutoClaw: the local database copy still holds the chat "alive", listed as normal.
2. **The copy was refreshed, the chat is gone** — enable "Show hidden chats": in the database the chat usually remains flagged as deleted and shows with type `del`; it exports like any other.
3. **The deletion was long ago, the copy has been refreshed many times** — fewer chances: open the `ZCodeData` (`AutoClawData`) folder next to the exe; the three previous database versions live there (`.bak1` — the newest of the old). Close the exporter, rename the current `db.sqlite` (`runtime.sqlite`), rename `.bak1` back to it — and the chat is in the list again (hidden, `del`). This is why refreshing the copy at the end of the workday helps: three nights of backups in your pocket.

## 13. Known particulars

- The database schemas are internal: after a major AutoClaw/ZCode update the program may report an unknown structure — it never damages data, and the configs are fixed with a text editor.
- The "Tokens" column for ZCode is the last request's size (the whole context); for AutoClaw — the context of the last completed run.
- The context share (X%/1M) is shown for known models (GLM-5.3 / GLM-5.3-Flash); for others — just the token count.
- "Export to one file" with tools enabled can get very large.
- ZCode project names come from `tasks-index.sqlite`; without it chats group without names.
