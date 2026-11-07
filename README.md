# DevLauncher

[中文](#中文) · [English](#english)

Windows 上的本地服务启动器。把项目目录关联进来后，按该项目自己的 VS Code 或 IntelliJ IDEA 启动配置启动、重启和关闭，不用每次手敲命令。也可以把当前窗口交给 AI，由正在运行的这个窗口执行操作。

## 中文

### 环境

- Windows
- Python 3.8 或更高版本，并且能找到 `pythonw.exe`

### 启动

双击 `start.bat`。脚本会选择本机符合版本要求的 Python，并用 `pythonw` 打开窗口，不留一个额外的控制台。

### 关联项目

- 点「关联项目」选择目录，或把文件夹、文件、桌面快捷方式拖进窗口。
- 文件夹使用该目录。文件使用它所在的目录。快捷方式会先解析到目标，再按同样规则处理。
- 点「保存」后，这些项目才会写入本机的 `launcher.json`，下次打开仍然在。

每个项目卡片可以在 **VS Code** 和 **IDEA** 之间切换：

- VS Code 读取该目录下的 `.vscode/launch.json`
- IDEA 读取 `.idea/runConfigurations`、`.run` 和 `.idea/workspace.xml` 里的运行配置

只显示当前这一侧的启动项。

启动器只登记项目、配置名称和配置文件引用。每次启动或重启前都会重新读取对应配置文件中的命令、工作目录、环境变量和参数；修改 VS Code 配置后不需要重新登记启动器。

### 启动、重启、关闭

每一项都有「启动」「重启」「关闭」。

「一键启动」在项目卡片顶边中间，只启动**当前这一侧**列出的全部配置。已经在运行的会跳过。

状态为「已启动」时，后面的数字是该 cmd 的进程号。

### 设置

窗口右上角是一枚齿轮图标，点它打开设置。

- **关闭启动器时**：每次询问、关闭正在运行的服务，或只关窗口、服务继续留着。
- **启动时的 cmd 窗口**：弹出，或最小化到任务栏。最小化后窗口还在，可以从任务栏再打开。

没有服务在跑时，关闭启动器不会询问。

### 交给 AI

勾选某一项的「AI 托管」后，AI 才能通过这个窗口启动、重启或关闭该项。手动点按钮不受这个勾选限制。

点「复制给 Agent」，会按 `复制提示词.txt` 生成一段说明。`{目录}` 和 `{窗口句柄}` 在复制时填入。把复制结果贴给 AI 即可。提示词正文可以改 `复制提示词.txt`，程序会在复制时套上中文引号。

AI 应读取该目录里的 `launcher.json`，并让**正在运行的这个窗口**执行操作，不要自己结束进程或另起命令。同一个工作目录有多项时，只勾选其中一项「AI 托管」。

### 本机配置

`launcher.json` 保存在程序目录，不包含在仓库里。它只保存项目/配置登记、AI 托管权限和界面设置，不保存 VS Code 启动命令的副本。第一次保存或修改设置时会自动生成。别人克隆仓库后可以直接运行，项目列表一开始是空的。

`run\` 是窗口打开期间的运行记录，关闭窗口后删除，也不包含在仓库里。

### 文件

| 文件 | 作用 |
| --- | --- |
| `start.bat` | 启动窗口 |
| `start.py` | 程序本体 |
| `复制提示词.txt` | 复制给 AI 的说明模板 |
| `launcher.json` | 本机项目与设置，不提交 |

## English

A local service launcher for Windows. Associate a project directory, then start, restart, and stop it from that project's own VS Code or IntelliJ IDEA run configurations. The running window can also carry out those actions for an AI assistant.

### Requirements

- Windows
- Python 3.8 or newer, with `pythonw.exe` available

### Start

Double-click `start.bat`. It picks a suitable Python and opens the window with `pythonw`, so no extra console is left behind.

### Associate a project

- Click **关联项目** and choose a directory, or drop a folder, a file, or a desktop shortcut onto the window.
- A folder is used as itself. A file uses its parent directory. A shortcut is resolved to its target first.
- Click **保存** to write the list into the local `launcher.json`. Otherwise the associations are discarded when the window closes.

Each project card switches between **VS Code** and **IDEA**:

- VS Code reads `.vscode/launch.json` directly under the directory
- IDEA reads `.idea/runConfigurations`, `.run`, and the run configurations in `.idea/workspace.xml`

Only the selected side is listed.

The launcher stores only project/configuration registrations. It rereads the selected configuration's command, working directory, environment, and arguments before every start or restart, so editing the VS Code configuration does not require re-registering it.

### Start, restart, and stop

Each item has **启动**, **重启**, and **关闭**.

**一键启动**, centered on the project card, starts every configuration on the **current side**. Items that are already running are skipped.

While an item is running, the number after **已启动** is the cmd process id.

### Settings

The gear at the top right opens settings.

- **When closing the launcher**: ask every time, stop running services, or close the window and leave the services running.
- **Cmd window on start**: show it, or minimize it to the taskbar. A minimized window is still there and can be opened from the taskbar.

If nothing is running, closing the launcher does not ask.

### Handing work to an AI

Check **AI 托管** on an item to let an AI start, restart, or stop it through this window. Buttons clicked by hand do not depend on that checkbox.

**复制给 Agent** fills `复制提示词.txt`, replacing `{目录}` and `{窗口句柄}`, and copies one quoted block. Paste that block to the AI. Edit `复制提示词.txt` to change the wording.

The AI should read `launcher.json` in that directory and let **this running window** perform the action. It should not kill processes or start its own command. If several items share a working directory, check **AI 托管** on only one of them.

### Local configuration

`launcher.json` lives next to the program and is not part of the repository. It stores project/configuration registrations, AI permissions, and UI settings, but not a second copy of VS Code's launch command. It is created on the first save or settings change. After a clone, the project list starts empty.

`run\` holds per-window runtime state while the launcher is open. It is removed when the window closes and is not part of the repository.

### Files

| File | Role |
| --- | --- |
| `start.bat` | Opens the window |
| `start.py` | The program |
| `复制提示词.txt` | Template copied to an AI |
| `launcher.json` | Local projects and settings; not committed |
