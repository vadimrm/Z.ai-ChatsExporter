# Z.ai Chats Exporter by Vadim R.M. ver. 1.27

**AutoClaw.Z.ai-ExportChat** 项目的 GUI 分支（母项目为同名的 AutoClaw 对话导出命令行工具）：将 AutoClaw 和 ZCode 对话导出为 Markdown、TXT 和 JSON

Windows 桌面程序：读取 AutoClaw 与 ZCode 的本地对话数据库，把对话保存为文件——Markdown、纯文本或 JSON。单个 exe，无需安装 Python：数据库适配器与窗口在同一进程中运行（AGREEMENTS.md，第 19 轮——引擎已并入 GUI，命令行已移除）。

非官方工具，与 Z.ai 无关，只读取本地数据库，不联网。

[English](README.md) · [Русский](README.ru.md) · **中文**

Copyright © 2026 by Vadim Madgazin & ZCode (Z.ai)

## 功能

- 两种模式：**AutoClaw Chats**（runtime.sqlite）与 **Zcode Chats**（db.sqlite）——各自独立的列表、勾选与数据库路径；
- 对话表格：每行带勾选框（默认勾选第一个对话），点击任意列标题可排序并切换方向（▲/▼），按标题搜索；
- 导出所选对话 × 所选格式（MD / TXT / JSON）——一次运行生成 N×M 个文件，带「k/N」进度与错误汇总；单个对话失败不会中断其余导出；
- 「导出为一个文件」复选框：关闭——每个所选对话各自写成单独文件；开启——所有「所选」对话打包为每种格式一个文件（标题「所选对话…」，文件名 AC-ALL-/ZC-ALL-日期）；「全选」+ 复选框 = 整个模式打包为一个文件；
- 按格式划分的选项矩阵（每一列单独配置一种格式）：工具调用（+ 通用的结果长度上限）、中间回复、服务文件（仅 AutoClaw）、隐藏文件块、UTF-8 BOM；
- 导出文件中的标签语言：俄语（默认）、英语或中文；界面语言即时切换；
- 数据库以只读方式打开（mode=ro），AutoClaw/ZCode 无需关闭；ZCode 数据库被占用时自动读取临时副本；
- 文件永不覆盖：重复导出自动加 ` (1)`、` (2)`… 后缀；
- 文件名格式：`AC-YYYY-MM-DD-<对话标题>.<ext>` / `ZC-YYYY-MM-DD-<对话标题>.<ext>`；ZCode 模式下对话还会按项目文件夹归档。

## 环境要求

- Windows 8.1 或更新版本，64 位（已在 8.1、10、11 上验证；Windows 7 无法运行——Python 3.12 构建不再支持该系统）；
- 无需安装 Python；
- 本机无需安装 AutoClaw 和 ZCode：数据库就是普通文件，程序可使用它们的**本地副本**——把 `runtime.sqlite` / `db.sqlite` 拷贝到 U 盘，用「SQL 数据库」按钮指定；这样即使 AutoClaw/ZCode 无法在旧版 Windows 上运行，也能导出对话。

## 安装与运行

Windows 版本的发布包可在此下载：<https://github.com/vadimrm/Z.ai-ChatsExporter/releases>

成品版无需安装 Python：从最新 release 下载 `Z.ai-ChatsExporter-…-win64.zip`（内含 `ExportChat.exe`、出厂 `db_profiles.cfg` 和简短说明），解压后双击运行。

设置保存在 exe 旁的 `ExportChat.cfg`（首次启动时创建；便携式；从不使用注册表和 %APPDATA%；UTF-8 带 BOM——旧版记事本也能正常编辑）。两个数据库的标准文件名与全部标准位置保存在单独的可手动编辑的 **db_profiles.cfg**（随程序附在 exe 旁；注明针对哪些 AutoClaw/ZCode 版本验证过）：程序在启动时读取它且从不覆盖——如果应用更改了数据库位置，用文本编辑器修改即可，无需重新打包 exe。若文件被删除或损坏，程序会提示，损坏文件保存为 `db_profiles.cfg.err`，并写入出厂文件。

从源码运行（Python 3.10+）：

```bat
python frontend\main.py
```

重新打包 exe 用 `build\build.bat`（PyInstaller）。架构与工作计划见 `GUI_PLAN.md`，选型分析见 `GUI_VARIANTS.md`，变更日志见 `AGREEMENTS.md`。

## 界面（简介）

- 「导出文件夹」+ 路径字段——共同的母输出文件夹（默认为 exe 所在目录）；对话写入「AutoClaw Chats」/「ZCode Chats」子文件夹，数据库副本（「导出 SQL 数据库」按钮）写入「AutoClaw SQL」/「ZCode SQL」；
- 「SQL 数据库」——选择数据库文件：选定后立即加载对话列表；「刷新对话」重新读取；自动查找只检查 `db_profiles.cfg` 中的标准位置——不查注册表、不扫描磁盘；
- 「打开导出文件夹」——资源管理器（导出后定位并选中最后一个文件）；
- 状态栏文字与窗口标题可复制：窗口内 Ctrl+C 或右键状态栏；「导出错误」窗口带「复制」按钮；
- 重复启动不会创建副本：已有的窗口会被带到前台；
- 「Donate」与作者网站按钮——<https://www.vmgames.com/>。

## 导出中的文件

- **附件**——取自请求文本中的 `Attached workspace files` 区块（名称、类型、大小），该区块本身会从正文中移除（AutoClaw）。
- **生成的文件**——取自 `governed_tool_artifacts` 表，按 `tool_call_id` 关联，因此文件会落在它真正出现的那一轮（AutoClaw）。
- **「可下载」**——助手通过 `deliver_file` 交付的文件（AutoClaw）。
- **「显示服务文件」**——额外显示过程中产生的全部文件：脚本、草稿、补丁（AutoClaw）。
- ZCode 附件——来自消息的 `file` 部分：名称、路径、MIME。

文件名一律放在双引号中；`:zwork-file-citation{...}` 之类的内部指令不会出现在输出里。

## 格式

| 格式 | 内容 |
| --- | --- |
| `md` | 原样保留 Markdown：标题、列表、表格、代码 |
| `txt` | 去除标记转为纯文本：没有 `**`、反引号、`#`、表格竖线；列表变为 `•`，链接变为 `文本 (地址)` |
| `json` | 结构化：`session` 加 `turns[]`，每轮包含 `request`、`attachments`、`answers`、`tools`、`narration` |

`.md` 与 `.txt` 默认写入 UTF-8 BOM（三个字节 `EF BB BF`；矩阵中的「UTF-8 Byte Order Mark」复选框，按格式独立设置）。JSON 文件从不写入 BOM——严格的解析器会报错。

## 工作原理

AutoClaw——`%APPDATA%\AutoClaw*\accounts\<id>\runtime\runtime.sqlite`，三张表：

- `work_sessions`——对话列表；
- `neutral_session_entries`——消息（请求、回答、工具调用）；
- `governed_tool_artifacts`——生成的文件。

ZCode——`~/.zcode/cli/db/db.sqlite`，表 `session` / `message` / `part`；子代理会话会被过滤，数据库被应用占用时读取临时副本。

连接以 `mode=ro` 打开，不会向数据库写入任何内容。适配器见 `backend/adapter.py`（`AutoClawAdapter`、`ZCodeAdapter`）；数据库位置见 `frontend/db_profiles.py` 与 exe 旁的 `db_profiles.cfg` 文件。

## 限制

- 数据库结构属于内部实现且未公开文档化：AutoClaw/ZCode 更新后可能变化。出错时程序会说明原因，不会破坏数据；数据库位置可在 db_profiles.cfg 中修改，无需重新打包。
- `txt` 会丢失格式，这正是它的用途。
- 启用工具调用时文件体积增长很快：单轮可能有 60 次以上调用。
- 不导出图片和二进制文件，只记录名称、类型和大小。
- 本工具与 Z.ai 无关，不是官方导出功能。

## 常见问题

请复制错误文本（窗口内 Ctrl+C，或「导出错误」窗口中的「复制」按钮）并发送给作者——没有准确的错误文本就无法定位原因。

## 相关链接

Windows 发布包：<https://github.com/vadimrm/Z.ai-ChatsExporter/releases>

仓库（GUI）：<https://github.com/vadimrm/Z.ai-ChatsExporter>

母项目——AutoClaw 对话导出命令行工具：<https://github.com/vadimrm/AutoClaw.Z.ai-ExportChat>

## 许可证

MIT，详见 `LICENSE` 文件。

作者：Vadim Madgazin、AutoClaw.Z.ai
