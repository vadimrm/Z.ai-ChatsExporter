# Z.ai Chats Exporter by Vadim R.M. ver. 2.00

将本地的 **AutoClaw** 和 **ZCode（Z.ai）**聊天记录导出为 Markdown、TXT 和 JSON — 包括**已删除和隐藏**的对话。

Windows 桌面程序：读取本地的 AutoClaw 和 ZCode 聊天数据库，把对话保存为文件。单个 exe，无需安装 Python。程序只使用数据库的**本地副本** — 无需关闭 AutoClaw/ZCode；源数据库始终以只读方式打开。

非官方工具，与 Z.ai 无关，不访问网络。

[English](README.md) · [Русский](README.ru.md) · **中文**

Copyright © 2026 by Vadim Madgazin

![程序截图](screenshots/ZAICHEXP-ver-2.00.png)

## 功能

- 两种模式 — **Zcode Chats**（db.sqlite）和 **AutoClaw Chats**（runtime.sqlite）；首次启动进入 Zcode Chats；
- 聊天列表：☑ 选择、任意列排序、搜索；列为「项目」「类型」「数量」「Token」（上下文大小）和日期；
- **隐藏和已删除的聊天**：勾选「显示隐藏的聊天」可看到标记为 `del`（已删除）、`arch`（归档）、`wfchld`、`selchat`、`auto` 的对话 — 见下文「已删除的聊天」；
- 选中的聊天 × MD / TXT / JSON 格式导出（一次 N×M 个文件），或全部打包为一个文件；
- 每个导出文件都有详细的头部：项目、类型、会话、日期、「消息：N / M（问题/回答）」、文件、模型、**带模型窗口占比的上下文 Token 数**（「聊天上下文：28 019 token（2.8%/1M）」）、自动压缩阈值、累计消耗 Token；
- 文件区块始终显示：用户附件和「可下载」（代理交付的文件）；AutoClaw 另有「显示服务文件」选项（工作过程中创建的脚本和草稿）；
- 工具调用和中间回复 — 通过复选框控制并带长度限制；「仅当前上下文」预设导出自动压缩后模型实际看到的内容（压缩历史摘要 + 存活尾部）；
- 安全的数据库导入：通过 SQLite backup API 刷新本地副本（AutoClaw/ZCode 运行时也可用）；替换前先校验，并保留**前三个版本**（exe 旁的 ZCodeData / AutoClawData）；
- 程序中的所有文本均可复制：自带对话框的文本可选择，在界面任何位置右键复制（输入框、表格行与表头、状态栏、窗口标题）；
- 界面与导出语言：俄语、英语、中文；全部字符串在 exe 旁可编辑的 `lang_*.cfg` 中；
- 完全便携：无需安装，不写注册表和 %APPDATA%；图标为 Tk「羽毛笔」。

## 已删除的聊天与恢复

导出器甚至能显示**已删除**的聊天：只要本地数据库副本尚未刷新，对话在其中仍然存在。

> **误删了聊天？** 不要关闭 ZCode（AutoClaw）。启动导出器并按名称搜索 — 它很可能还完整地留在你的本地数据库副本里。如果没有，请用「刷新 SQL 数据库」按钮刷新本地数据库，勾选「显示隐藏的聊天」，寻找标记为 `del` 的对话。
>
> **一般建议：** 在每个工作日结束时刷新本地 SQL 数据库。导出器在 `ExportChat.exe` 旁的 `ZCodeData`（`AutoClawData`）文件夹中保留数据库的前三个版本（`.bak1`–`.bak3`），因此昨天误删的聊天可以从旧副本中找回。

## 系统要求

- Windows 8.1 或更高版本，64 位（已在 8.1、10 和 11 上测试）；
- 本机无需 Python、AutoClaw 和 ZCode：数据库是普通文件，可以用 U 盘带来并通过「SQL 数据库路径」按钮指定。

## 安装与运行

从 [release](release/) 文件夹（或 [Releases](https://github.com/vadimrm/Z.ai-ChatsExporter/releases)）下载 `ExportChat.exe`，把同文件夹中的 `db_profiles.cfg` 和 `lang_*.cfg` 放在旁边 — 双击运行。设置（`ExportChat.cfg`）在首次启动时创建于 exe 旁。

从源码运行（Python 3.10+）：`python frontend\main.py`。重新打包 exe — `src\build\build.bat`（PyInstaller）。

界面各元素的详细说明见 [MANUAL.zh.md](MANUAL.zh.md)；相对 1.27 版的更改见 [CHANGES.zh.md](CHANGES.zh.md)。

## 格式

| 格式 | 内容 |
| --- | --- |
| `md` | 原样保留标记：标题、列表、表格、代码 |
| `txt` | 纯文本：去掉标记，列表变为 `•`，链接变为「文本 (地址)」 |
| `json` | 结构化：`session`（头部）+ `turns[]`（请求、回答、附件、工具） |

文件名：`AC-日期-名称.ext` / `ZC-日期-名称.ext`；重复导出不覆盖（后缀 ` (1)`、` (2)`…）。`.md`/`.txt` 的 BOM — 通过复选框（默认开启）；JSON 永不写 BOM。

## 工作原理

程序读取数据库的**本地副本**：AutoClaw — `%APPDATA%\AutoClaw*\accounts\<id>\runtime\runtime.sqlite`，ZCode — `~/.zcode/cli/db/db.sqlite`（含 `tasks-index.sqlite`）。副本通过「刷新 SQL 数据库」按钮以 SQLite backup API 创建/刷新 — 即使 AutoClaw/ZCode 正在运行也保持一致；源数据库从不被修改。数据库路径在 exe 旁人工可编辑的 `db_profiles.cfg`（v3）中配置 — 存储位置变化时直接改文本即可，无需重新打包。

## 仓库结构

- `release/` — 成品包：`ExportChat.exe`、`db_profiles.cfg`、`lang_*.cfg`、简要说明；
- `src/` — 源码（backend — 导出引擎，frontend — 界面与测试，build — 打包）；
- `screenshots/` — 截图；
- `docs/dev/` — 历史项目文档。

## 限制

- 数据库结构为内部格式且无文档：AutoClaw/ZCode 更新可能改变它（届时程序会如实报错，不会损坏数据）。
- 图片和二进制附件不导出 — 只有名称、类型和大小。
- 开启工具调用时文件增长很快。

## 故障排查

在 GitHub 上提交错误报告：

1. 打开 <https://github.com/vadimrm/Z.ai-ChatsExporter/issues> 并点击 **New issue**；
2. 描述问题以及触发问题的操作步骤；
3. 附上状态栏或错误窗口的文本（右键或 Ctrl+C 均可复制），并注明程序版本（显示在窗口标题中）。

## 许可证

MIT — 见 [LICENSE](LICENSE) 文件。
