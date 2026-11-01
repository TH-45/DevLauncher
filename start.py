import sys
import os

_CLI_FLAGS = {"--tell", "--console-tail", "--console-find", "--console-read-worker"}

if __name__ == "__main__" and "--launched" not in sys.argv and not any(flag in sys.argv for flag in _CLI_FLAGS):
    import ctypes
    pythonw_exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw_exe):
        print(f"[ERROR] pythonw.exe not found at {pythonw_exe}")
        print("Please check your Python installation.")
        sys.exit(1)
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "open", pythonw_exe,
        f'"{os.path.abspath(__file__)}" --launched',
        os.path.dirname(os.path.abspath(__file__)),
        1,
    )
    if result <= 32:
        print(f"[ERROR] Failed to launch pythonw (code={result})")
        sys.exit(1)
    sys.exit(0)

import argparse
import ctypes
import json
import random
import re
import shutil
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from ctypes import wintypes
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "launcher.json")
COPY_PROMPT_PATH = os.path.join(APP_DIR, "复制提示词.txt")
RUN_DIR = os.path.join(APP_DIR, "run")
CREATE_NEW_CONSOLE = 0x00000010
CREATE_NO_WINDOW = 0x08000000
_WM_CLOSE = 0x0010
_GA_ROOT = 2
_STD_OUTPUT_HANDLE = wintypes.DWORD(-11)
_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_DUPLICATE_SAME_ACCESS = 0x00000002
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_TAIL_LINES = 40
_TAIL_CHARS = 4000
_FIND_CONTEXT = 2
_FIND_MAX_LINES = 40
_FIND_MAX_CHARS = 4000
_AGENT_USAGE = """\
这是服务启动器的说明。启动、重启、关闭都由正在运行的那个窗口执行。不要自己结束进程，也不要另起启动命令。

窗口句柄和工具目录来自复制出来的文字。该窗口的运行记录在「目录\\run\\窗口句柄\\status.json」。
记录里 cmdPid 是这一项当前 cmd 的进程号，cmdTitle 是窗口标题。state 为 running 时才能读取输出。
error 有内容时，表示 cmd 还没弹出就失败了，例如找不到 JDK。这份记录不是启动日志。

选择启动项时，只根据本次改动文件的路径：
- 文件要落在该项的工作目录里。同时落在上下两级目录时，取最深的那一项。
- 恰好命中一项，并且该项 allowAgent 为 true，才可以操作。
- 同一个目录有多项时，只勾选其中一项「AI 托管」。勾了多项时不要操作。
- 界面上「已启动」后面的数字就是该 cmd 的进程号，可交给 AI 用 --console-tail 查看。
- 没有命中、命中多项，或命中的不是准备调用的那一项，都不要操作，先问用户。
- 不要根据代码内容猜测该启动哪一项。

启动、重启或关闭（action 写 start、restart 或 close；source 只能是 vscode 或 idea）：
python "<目录>\\start.py" --tell <窗口句柄> restart --project "<项目路径>" --source vscode --name "<配置名>" --file "<本次改动文件的绝对路径>"
程序会核对文件路径。对不上就拒绝，不会操作。

查看该项 cmd 的启动输出。程序只返回末尾 40 行，不会把整个窗口内容交出来：
python "<目录>\\start.py" --console-tail <cmdPid>

末尾不够时，按关键字再查。搜索在程序里完成，只返回命中行和前后各 2 行：
python "<目录>\\start.py" --console-find <cmdPid> <关键字>

窗口关掉之后，句柄和 cmdPid 都失效，需要用户从目标窗口重新复制。
"""
_SKIP_DIR_NAMES = {".git", "node_modules", "target", "dist", "build", ".idea"}
_SKIP_TYPES = {
    "javascriptdebugtype",
    "chrome",
    "pwa-chrome",
    "msedge",
    "edge",
    "firefox",
    "pwa-firefox",
}

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32.AttachConsole.argtypes = (wintypes.DWORD,)
_kernel32.AttachConsole.restype = wintypes.BOOL
_kernel32.FreeConsole.restype = wintypes.BOOL
_kernel32.GetConsoleWindow.restype = wintypes.HWND
_kernel32.GetStdHandle.argtypes = (wintypes.DWORD,)
_kernel32.GetStdHandle.restype = wintypes.HANDLE
_kernel32.GetCurrentProcess.restype = wintypes.HANDLE
_kernel32.DuplicateHandle.argtypes = (
    wintypes.HANDLE,
    wintypes.HANDLE,
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.HANDLE),
    wintypes.DWORD,
    wintypes.BOOL,
    wintypes.DWORD,
)
_kernel32.DuplicateHandle.restype = wintypes.BOOL
_kernel32.WriteFile.argtypes = (
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
)
_kernel32.WriteFile.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.CreateFileW.argtypes = (
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
)
_kernel32.CreateFileW.restype = wintypes.HANDLE
_user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_user32.PostMessageW.restype = wintypes.BOOL
_user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
_user32.GetAncestor.restype = wintypes.HWND


class LaunchItem:
    def __init__(self, key, name, command, cwd, env, source, jdk_error="", config_path=""):
        self.key = key
        self.name = name
        self.command = command
        self.cwd = cwd
        self.env = env
        self.source = source
        self.jdk_error = jdk_error
        self.config_path = config_path


class ToolTip:
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip = None
        self.after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event):
        self._hide()
        self.after_id = self.widget.after(self.delay, self._show)

    def _show(self):
        if self.tip is not None:
            return
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.tip,
            text=self.text,
            background="#fff8dc",
            relief="solid",
            borderwidth=1,
            padx=6,
            pady=3,
        ).pack()

    def _hide(self, _event=None):
        if self.after_id is not None:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


def _close_console_window(pid):
    """向该进程的控制台投递关闭，效果与鼠标点窗口 X 相同。"""
    if not _kernel32.AttachConsole(pid):
        if ctypes.get_last_error() != 5 or not _kernel32.FreeConsole():
            return False
        if not _kernel32.AttachConsole(pid):
            return False
    try:
        hwnd = _kernel32.GetConsoleWindow()
    finally:
        _kernel32.FreeConsole()
    if not hwnd:
        return False
    return bool(_user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0))


def _kill(proc):
    if not proc or proc.poll() is not None:
        return
    pid = proc.pid
    _close_console_window(pid)
    subprocess.Popen(
        ["taskkill", "/T", "/F", "/PID", str(pid)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )


def _norm(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _display_name(raw):
    text = (raw or "").strip()
    if text:
        return text
    return f"#{random.randint(0, 999):03d}"


def _load_text(path):
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            with open(path, "r", encoding=encoding) as fh:
                return fh.read()
        except UnicodeDecodeError:
            continue
        except OSError:
            return ""
    return ""


def render_copy_prompt(directory, hwnd):
    """读取复制模板，填入目录和窗口句柄，并在整段前后加上引号。"""
    template = _load_text(COPY_PROMPT_PATH).strip()
    if not template:
        return ""
    text = template.replace("{目录}", directory).replace("{窗口句柄}", hwnd).strip()
    return "“" + text + "”"


def _strip_json(text):
    out = []
    i = 0
    n = len(text)
    in_str = False
    esc = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i = min(n, i + 2)
            continue
        out.append(ch)
        i += 1
    cleaned = "".join(out)
    return re.sub(r",(\s*[}\]])", r"\1", cleaned)


def _read_json(path):
    text = _load_text(path)
    if not text.strip():
        return None
    try:
        return json.loads(_strip_json(text))
    except json.JSONDecodeError:
        return None


def _expand(value, project, module_dir=None):
    if value is None:
        return ""
    text = str(value)
    module = module_dir or project

    def env_of(match):
        return os.environ.get(match.group(1), "")

    text = text.replace("${workspaceFolder}", project)
    text = text.replace("${workspaceRoot}", project)
    text = re.sub(r"\$\{env:([^}]+)\}", env_of, text)
    text = text.replace("$PROJECT_DIR$", project)
    text = text.replace("$MODULE_DIR$", module)
    text = text.replace("$MODULE_WORKING_DIR$", module)
    if text.startswith("file://"):
        text = text[7:]
        if text.startswith("/") and len(text) > 2 and text[2] == ":":
            text = text[1:]
    return text


def _merge_env(extra):
    env = os.environ.copy()
    folded = {key.lower(): key for key in env}
    for key, value in extra.items():
        old = folded.get(key.lower())
        if old is not None and old != key:
            del env[old]
        env[key] = value
        folded[key.lower()] = key
    return env


def _walk_limited(root, depth=3):
    root = os.path.abspath(root)
    for current, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(current, root)
        level = 0 if rel == "." else rel.count(os.sep) + 1
        if level >= depth:
            dirnames[:] = []
        dirnames[:] = [name for name in dirnames if name not in _SKIP_DIR_NAMES and not name.startswith(".")]
        yield current, filenames


def _find_module_dir(project, module_name):
    if not module_name:
        return project
    direct = os.path.join(project, module_name)
    if os.path.isdir(direct):
        return direct
    wanted = module_name.lower()
    for current, filenames in _walk_limited(project):
        for filename in filenames:
            stem, ext = os.path.splitext(filename)
            if ext.lower() == ".iml" and stem.lower() == wanted:
                if os.path.basename(current).lower() == ".idea":
                    return project
                return current
            if filename.lower() == "pom.xml" and os.path.basename(current).lower() == wanted:
                return current
    return project


def _build_tool_command(directory, spring=False, main_class=None):
    if os.path.isfile(os.path.join(directory, "mvnw.cmd")):
        runner = "mvnw.cmd"
    elif os.path.isfile(os.path.join(directory, "mvnw")):
        runner = "mvnw"
    elif os.path.isfile(os.path.join(directory, "pom.xml")):
        runner = "mvn"
    else:
        runner = None
    if runner and spring:
        return f"{runner} spring-boot:run"
    if runner and main_class:
        return f"{runner} -Dexec.mainClass={main_class} org.codehaus.mojo:exec-maven-plugin:3.5.0:java"
    if os.path.isfile(os.path.join(directory, "gradlew.bat")):
        gradle = "gradlew.bat"
    elif os.path.isfile(os.path.join(directory, "gradlew")):
        gradle = "gradlew"
    elif os.path.isfile(os.path.join(directory, "build.gradle")) or os.path.isfile(os.path.join(directory, "build.gradle.kts")):
        gradle = "gradle"
    else:
        gradle = None
    if gradle and spring:
        return f"{gradle} bootRun"
    if gradle and main_class:
        return f"{gradle} bootRun"
    return None


def _pom_is_spring(directory):
    pom = os.path.join(directory, "pom.xml")
    if not os.path.isfile(pom):
        return False
    text = _load_text(pom).lower()
    return "spring-boot" in text


def _quote_cmd(args):
    parts = []
    for arg in args:
        text = str(arg)
        if text == "":
            parts.append('""')
        elif any(ch in text for ch in ' \t"&|<>^'):
            parts.append('"' + text.replace('"', '""') + '"')
        else:
            parts.append(text)
    return " ".join(parts)


def _console_command(name, command, token):
    """拼出 cmd /k 的命令行。VS Code 里的 cmd /c "..." 先拆掉外层，避免引号被当成程序名。"""
    safe = "".join(ch if ch not in '&|<>^"' else " " for ch in name).strip() or "service"
    safe = safe[:80]
    title = f"{safe} {token}"
    text = command.strip()
    wrapped = re.match(r'(?is)^cmd(?:\.exe)?\s+/[ck]\s+"(.*)"\s*$', text)
    if wrapped and '"' not in wrapped.group(1):
        text = wrapped.group(1)
    inner = f"chcp 65001 >nul & title {title} & {text}"
    return 'cmd.exe /k "' + inner + '"', title


def _option_values(node, name):
    values = []
    for opt in node.iter("option"):
        if opt.get("name") != name:
            continue
        if opt.get("value"):
            values.append(opt.get("value"))
        for child in list(opt):
            if child.get("value"):
                values.append(child.get("value"))
    return values


def _first_option(node, name):
    values = _option_values(node, name)
    return values[0] if values else ""


def _idea_jdk_tables():
    root = os.path.join(os.environ.get("APPDATA", ""), "JetBrains")
    if not os.path.isdir(root):
        return []
    found = []
    for name in os.listdir(root):
        if not name.startswith("IntelliJIdea"):
            continue
        path = os.path.join(root, name, "options", "jdk.table.xml")
        if os.path.isfile(path):
            found.append(path)
    found.sort(reverse=True)
    return found


def _expand_idea_path(value):
    text = (value or "").replace("$USER_HOME$", os.path.expanduser("~"))
    if "$" in text:
        return ""
    return os.path.normpath(text)


def _lookup_idea_jdk(jdk_name):
    if not jdk_name:
        return ""
    for path in _idea_jdk_tables():
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError):
            continue
        for jdk in root.iter("jdk"):
            name_node = jdk.find("name")
            type_node = jdk.find("type")
            home_node = jdk.find("homePath")
            if name_node is None or home_node is None:
                continue
            if (name_node.get("value") or "") != jdk_name:
                continue
            if type_node is not None and (type_node.get("value") or "") not in {"", "JavaSDK"}:
                continue
            home = _expand_idea_path(home_node.get("value") or "")
            if home and os.path.isfile(os.path.join(home, "bin", "java.exe")):
                return home
    return ""


def _project_jdk_name(project):
    misc = os.path.join(project, ".idea", "misc.xml")
    if not os.path.isfile(misc):
        return ""
    try:
        root = ET.parse(misc).getroot()
    except (ET.ParseError, OSError):
        return ""
    for comp in root.iter("component"):
        if comp.get("name") == "ProjectRootManager" and comp.get("project-jdk-name"):
            return comp.get("project-jdk-name")
    return ""


def _idea_jdk_env(conf, project):
    """按 IDEA 运行配置或项目 SDK 取 JDK。找不到时返回错误说明，不回落到系统 JDK。"""
    enabled = _first_option(conf, "ALTERNATIVE_JRE_PATH_ENABLED").lower() == "true"
    named = _first_option(conf, "ALTERNATIVE_JRE_PATH")
    if enabled and named:
        expanded = _expand_idea_path(named)
        home = expanded if expanded and os.path.isdir(expanded) else _lookup_idea_jdk(named)
        label = named
    else:
        label = _project_jdk_name(project)
        home = _lookup_idea_jdk(label)
    if not home:
        shown = label or "未填写"
        return {}, f"找不到 IDEA 的 JDK（{shown}）"
    env = {
        "JAVA_HOME": home,
        "PATH": os.path.join(home, "bin") + os.pathsep + os.environ.get("PATH", ""),
    }
    return env, ""


_IDEA_JDK_TYPES = {
    "SpringBootApplicationConfigurationType",
    "Application",
    "JarApplication",
    "MavenRunConfiguration",
    "GradleRunConfiguration",
}


def _envs(node, project, module_dir):
    env = {}
    for el in node.iter("env"):
        key = el.get("name")
        if key:
            env[key] = _expand(el.get("value") or "", project, module_dir)
    return env


def _resolve_vscode(cfg, project, index, config_path=""):
    if not isinstance(cfg, dict):
        return None
    if str(cfg.get("request") or "launch").lower() == "attach":
        return None
    kind = str(cfg.get("type") or "").lower()
    if kind in _SKIP_TYPES:
        return None
    name = _display_name(cfg.get("name"))
    cwd = os.path.normpath(_expand(cfg.get("cwd") or project, project))
    env = {str(k): _expand(v, project) for k, v in (cfg.get("env") or {}).items()}
    command = None
    if cfg.get("command"):
        command = _expand(cfg.get("command"), project)
    elif cfg.get("runtimeExecutable"):
        args = list(cfg.get("runtimeArgs") or [])
        if cfg.get("program"):
            args.append(_expand(cfg.get("program"), project))
        args.extend(cfg.get("args") or [])
        command = _quote_cmd([_expand(cfg.get("runtimeExecutable"), project), *[_expand(a, project) for a in args]])
    elif kind in {"node", "pwa-node"} and cfg.get("program"):
        args = [_expand(a, project) for a in (cfg.get("args") or [])]
        command = _quote_cmd(["node", _expand(cfg.get("program"), project), *args])
    elif kind in {"python", "debugpy"}:
        args = [_expand(a, project) for a in (cfg.get("args") or [])]
        if cfg.get("module"):
            command = _quote_cmd(["python", "-m", _expand(cfg.get("module"), project), *args])
        elif cfg.get("program"):
            command = _quote_cmd(["python", _expand(cfg.get("program"), project), *args])
    elif kind == "java" and cfg.get("mainClass"):
        directory = _find_module_dir(project, cfg.get("projectName") or "")
        cwd = os.path.normpath(_expand(cfg.get("cwd") or directory, project, directory))
        command = _build_tool_command(cwd, spring=_pom_is_spring(cwd), main_class=cfg.get("mainClass"))
    if not command:
        return None
    key = f"{_norm(project)}|vscode|{index}|{name}"
    return LaunchItem(key, name, command, cwd or project, env, "vscode", config_path=config_path)


def _resolve_idea(conf, project, index, config_path=""):
    if conf.get("temporary") == "true":
        return None
    kind = str(conf.get("type") or "")
    if kind.lower() in _SKIP_TYPES or kind == "CompoundRunConfigurationType":
        return None
    name = _display_name(conf.get("name"))
    module_name = ""
    module_node = conf.find("module")
    if module_node is not None and module_node.get("name"):
        module_name = module_node.get("name")
    module_dir = _find_module_dir(project, module_name)
    command = None
    cwd = module_dir
    if kind == "SpringBootApplicationConfigurationType":
        command = _build_tool_command(module_dir, spring=True)
    elif kind in {"Application", "JarApplication"}:
        main_class = _first_option(conf, "MAIN_CLASS_NAME")
        command = _build_tool_command(module_dir, spring=_pom_is_spring(module_dir), main_class=main_class)
    elif kind == "MavenRunConfiguration":
        goals = _option_values(conf, "goals")
        cwd = _expand(_first_option(conf, "workingDirPath") or module_dir, project, module_dir)
        if goals:
            if os.path.isfile(os.path.join(cwd, "mvnw.cmd")):
                runner = "mvnw.cmd"
            elif os.path.isfile(os.path.join(cwd, "mvnw")):
                runner = "mvnw"
            else:
                runner = "mvn"
            command = _quote_cmd([runner, *goals])
    elif kind == "GradleRunConfiguration":
        tasks = _option_values(conf, "taskNames")
        external = _first_option(conf, "externalProjectPath")
        cwd = _expand(external or module_dir, project, module_dir)
        if tasks:
            if os.path.isfile(os.path.join(cwd, "gradlew.bat")):
                runner = "gradlew.bat"
            elif os.path.isfile(os.path.join(cwd, "gradlew")):
                runner = "gradlew"
            else:
                runner = "gradle"
            command = _quote_cmd([runner, *tasks])
    elif kind == "js.build_tools.npm":
        package_json = conf.find("package-json")
        package_path = _expand(package_json.get("value") if package_json is not None else "", project, module_dir)
        cwd = os.path.dirname(package_path) if package_path else module_dir
        npm_command = conf.find("command")
        verb = (npm_command.get("value") if npm_command is not None else "") or "run"
        scripts = [node.get("value") for node in conf.findall(".//script") if node.get("value")]
        if scripts and verb == "run":
            command = _quote_cmd(["npm", "run", *scripts])
        elif verb:
            command = _quote_cmd(["npm", verb, *scripts])
    elif kind == "ShConfigurationType":
        script = _first_option(conf, "SCRIPT_TEXT") or _first_option(conf, "SCRIPT_PATH")
        options = _first_option(conf, "SCRIPT_OPTIONS")
        work = _first_option(conf, "SCRIPT_WORKING_DIRECTORY")
        cwd = _expand(work or module_dir, project, module_dir)
        if script:
            command = script if not options else f"{script} {options}"
    elif kind in {"PythonConfigurationType", "Python.FlaskServer", "Python.DjangoServer"}:
        script = _first_option(conf, "SCRIPT_NAME")
        params = _first_option(conf, "PARAMETERS")
        work = _first_option(conf, "WORKING_DIRECTORY")
        cwd = _expand(work or module_dir, project, module_dir)
        if script:
            command = _quote_cmd(["python", _expand(script, project, module_dir)])
            if params:
                command = f"{command} {params}"
    if not command:
        return None
    cwd = os.path.normpath(_expand(cwd or project, project, module_dir) or project)
    env = {}
    jdk_error = ""
    if kind in _IDEA_JDK_TYPES:
        env, jdk_error = _idea_jdk_env(conf, project)
    for key, value in _envs(conf, project, module_dir).items():
        env[key] = value
    item_key = f"{_norm(project)}|idea|{index}|{name}"
    return LaunchItem(item_key, name, command, cwd, env, "idea", jdk_error, config_path)


def _run_xml_files(folder):
    """`.run` 里只认 *.run.xml，其他 xml 不读。"""
    if not os.path.isdir(folder):
        return []
    return [
        os.path.join(folder, name)
        for name in sorted(os.listdir(folder))
        if name.lower().endswith(".run.xml")
    ]


def _idea_files(project):
    found = []
    run_dir = os.path.join(project, ".idea", "runConfigurations")
    if os.path.isdir(run_dir):
        found.extend(
            os.path.join(run_dir, name)
            for name in sorted(os.listdir(run_dir))
            if name.lower().endswith(".xml")
        )
    found.extend(_run_xml_files(os.path.join(project, ".run")))
    project_norm = os.path.normcase(os.path.abspath(project))
    for current, _filenames in _walk_limited(project):
        if os.path.normcase(os.path.abspath(current)) == project_norm:
            continue
        found.extend(_run_xml_files(os.path.join(current, ".run")))
    workspace = os.path.join(project, ".idea", "workspace.xml")
    if os.path.isfile(workspace):
        found.append(workspace)
    return found


def discover(project):
    items = []
    launch_path = os.path.join(project, ".vscode", "launch.json")
    data = _read_json(launch_path) if os.path.isfile(launch_path) else None
    if isinstance(data, dict):
        for index, cfg in enumerate(data.get("configurations") or []):
            item = _resolve_vscode(cfg, project, index, launch_path)
            if item is not None:
                items.append(item)
    seen = set()
    for path in _idea_files(project):
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError):
            continue
        nodes = root.findall("configuration") if os.path.basename(path).lower() == "workspace.xml" else list(root.iter("configuration"))
        if os.path.basename(path).lower() == "workspace.xml":
            manager = root.find("component[@name='RunManager']")
            nodes = [] if manager is None else list(manager.findall("configuration"))
        for index, conf in enumerate(nodes):
            marker = (conf.get("type") or "", conf.get("name") or "", index)
            if marker in seen:
                continue
            seen.add(marker)
            item = _resolve_idea(conf, project, len(items) + index, path)
            if item is not None:
                items.append(item)
    return items


class _COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class _SMALL_RECT(ctypes.Structure):
    _fields_ = [
        ("Left", ctypes.c_short),
        ("Top", ctypes.c_short),
        ("Right", ctypes.c_short),
        ("Bottom", ctypes.c_short),
    ]


class _CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", _COORD),
        ("dwCursorPosition", _COORD),
        ("wAttributes", wintypes.WORD),
        ("srWindow", _SMALL_RECT),
        ("dwMaximumWindowSize", _COORD),
    ]


_kernel32.GetConsoleScreenBufferInfo.argtypes = (
    wintypes.HANDLE,
    ctypes.POINTER(_CONSOLE_SCREEN_BUFFER_INFO),
)
_kernel32.GetConsoleScreenBufferInfo.restype = wintypes.BOOL
_kernel32.ReadConsoleOutputCharacterW.argtypes = (
    wintypes.HANDLE,
    wintypes.LPWSTR,
    wintypes.DWORD,
    _COORD,
    ctypes.POINTER(wintypes.DWORD),
)
_kernel32.ReadConsoleOutputCharacterW.restype = wintypes.BOOL


def _format_hwnd(hwnd):
    return f"0x{int(hwnd) & 0xFFFFFFFF:08X}"


def _parse_hwnd(text):
    raw = str(text or "").strip()
    if not re.fullmatch(r"0x[0-9A-Fa-f]{1,8}", raw):
        return None
    return int(raw, 16)


def _top_hwnd(widget):
    hwnd = _user32.GetAncestor(widget.winfo_id(), _GA_ROOT)
    if not hwnd:
        hwnd = widget.winfo_id()
    return int(hwnd)


def _run_folder(hwnd_text):
    return os.path.join(RUN_DIR, hwnd_text)


def _write_json(path, payload):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _pid_alive(pid):
    if not pid:
        return False
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    _kernel32.CloseHandle(handle)
    return True


def _window_alive(folder):
    path = os.path.join(folder, "status.json")
    data = _read_json(path) if os.path.isfile(path) else None
    if not isinstance(data, dict):
        return False
    return _pid_alive(data.get("launcherPid"))


def _sweep_dead_runs():
    if not os.path.isdir(RUN_DIR):
        return
    for name in os.listdir(RUN_DIR):
        folder = os.path.join(RUN_DIR, name)
        if os.path.isdir(folder) and not _window_alive(folder):
            shutil.rmtree(folder, ignore_errors=True)


def catalog_key(project, source, name):
    return (_norm(project), source, name)


def _under_cwd(file_path, cwd):
    file_norm = _norm(file_path)
    cwd_norm = _norm(cwd)
    return file_norm == cwd_norm or file_norm.startswith(cwd_norm + os.sep)


def _deepest(items, file_path):
    hits = [item for item in items if item.get("cwd") and _under_cwd(file_path, item["cwd"])]
    kept = []
    for item in hits:
        cwd = _norm(item["cwd"])
        shadowed = any(
            _norm(other["cwd"]) != cwd and _norm(other["cwd"]).startswith(cwd + os.sep)
            for other in hits
        )
        if not shadowed:
            kept.append(item)
    return kept


def check_agent_call(items, project, source, name, file_path):
    """返回 (命中的清单项, 拒绝原因)。拒绝时清单项为 None。"""
    if source not in {"vscode", "idea"}:
        return None, "来源只能是 vscode 或 idea，未操作。"
    if not str(file_path or "").strip():
        return None, "没有给出改动文件路径，未操作。"
    file_path = os.path.abspath(file_path)
    target = None
    for item in items:
        if catalog_key(item.get("project"), item.get("source"), item.get("name")) == catalog_key(project, source, name):
            target = item
            break
    if target is None:
        return None, "清单里没有这一项，未操作。"
    matches = _deepest(items, file_path)
    if not matches:
        return None, "文件不在任何启动项的工作目录里，未操作。"
    allowed = [item for item in matches if item.get("allowAgent")]
    if len(matches) > 1 and len(allowed) != 1:
        names = "、".join(item["name"] for item in matches)
        return None, f"文件同时命中多项（{names}），未操作。"
    hit = allowed[0] if len(allowed) == 1 else matches[0]
    if catalog_key(hit.get("project"), hit.get("source"), hit.get("name")) != catalog_key(target.get("project"), target.get("source"), target.get("name")):
        return None, f"文件落在「{hit.get('name')}」，与指定的「{target.get('name')}」不一致，未操作。"
    if not hit.get("allowAgent"):
        return None, "该项未勾选 AI 托管，未操作。"
    return hit, ""


def _clip_chars(text, limit):
    if len(text) <= limit:
        return text
    clipped = text[-limit:]
    cut = clipped.find("\n")
    if cut != -1 and cut < len(clipped) - 1:
        clipped = clipped[cut + 1 :]
    return clipped


def format_tail(text):
    parts = text.splitlines()
    body = _clip_chars("\n".join(parts[-_TAIL_LINES:]), _TAIL_CHARS)
    shown = body.splitlines() if body else []
    header = f"末尾 {len(shown)} 行，窗口里共 {len(parts)} 行。更早的内容用 --console-find 加关键字查看。\n"
    return header + body + ("\n" if body else "")


def format_find(text, keyword):
    parts = text.splitlines()
    needle = keyword.lower()
    ranges = []
    hit_count = 0
    for index, line in enumerate(parts):
        if needle in line.lower():
            hit_count += 1
            ranges.append((max(0, index - _FIND_CONTEXT), min(len(parts), index + _FIND_CONTEXT + 1)))
    if hit_count == 0:
        return f"关键字「{keyword}」没有命中。窗口里共 {len(parts)} 行。\n"
    merged = []
    for start, end in ranges:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    chosen = []
    for start, end in reversed(merged):
        block = parts[start:end]
        if chosen:
            block = block + ["…"]
        if len(chosen) + len(block) > _FIND_MAX_LINES:
            room = _FIND_MAX_LINES - len(chosen)
            if room > 0:
                chosen = block[-room:] + chosen
            break
        chosen = block + chosen
    truncated = len(chosen) < sum(end - start for start, end in merged)
    lines = chosen
    body = _clip_chars("\n".join(lines), _FIND_MAX_CHARS)
    note = "结果已截断。\n" if truncated else ""
    header = f"关键字「{keyword}」命中 {hit_count} 行，以下为命中行及前后各 {_FIND_CONTEXT} 行。\n{note}"
    return header + body + ("\n" if body else "")


def _dup_stdout():
    current = _kernel32.GetCurrentProcess()
    source = _kernel32.GetStdHandle(_STD_OUTPUT_HANDLE)
    duplicate = wintypes.HANDLE()
    ok = _kernel32.DuplicateHandle(
        current,
        source,
        current,
        ctypes.byref(duplicate),
        0,
        False,
        _DUPLICATE_SAME_ACCESS,
    )
    if not ok:
        return None
    return duplicate


def _emit(handle, text):
    if not handle:
        return
    data = text.encode("utf-8", errors="replace")
    written = wintypes.DWORD()
    buffer = ctypes.create_string_buffer(data)
    _kernel32.WriteFile(handle, buffer, len(data), ctypes.byref(written), None)


def _invalid_handle(handle):
    if not handle:
        return True
    return int(ctypes.cast(handle, ctypes.c_void_p).value or 0) in {0, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF}


def _read_attached_console():
    handle = _kernel32.CreateFileW(
        "CONOUT$",
        _GENERIC_READ,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        None,
        _OPEN_EXISTING,
        0,
        None,
    )
    if _invalid_handle(handle):
        return None
    try:
        info = _CONSOLE_SCREEN_BUFFER_INFO()
        if not _kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(info)):
            return None
        width = min(int(info.dwSize.X), 4096)
        height = int(info.dwSize.Y)
        if width <= 0 or height <= 0:
            return ""
        lines = []
        for top in range(height):
            buf = ctypes.create_unicode_buffer(width + 1)
            got = wintypes.DWORD()
            ok = _kernel32.ReadConsoleOutputCharacterW(handle, buf, width, _COORD(0, top), ctypes.byref(got))
            if not ok:
                break
            lines.append(buf.value[: int(got.value)].rstrip(" \t"))
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)
    finally:
        _kernel32.CloseHandle(handle)


def _attach_and_read(pid):
    if not _kernel32.AttachConsole(int(pid)):
        if ctypes.get_last_error() != 5 or not _kernel32.FreeConsole() or not _kernel32.AttachConsole(int(pid)):
            return None, f"读不到这个 cmd 窗口（进程 {pid}）。窗口可能已关闭。\n"
    try:
        text = _read_attached_console()
    finally:
        _kernel32.FreeConsole()
    if text is None:
        return None, "已连上 cmd，但没有读到屏幕缓冲。\n"
    return text, ""


def console_worker(pid, mode, keyword):
    saved = _dup_stdout()
    text, error = _attach_and_read(pid)
    if error:
        _emit(saved, error)
        return 1
    if mode == "find":
        output = format_find(text, keyword)
    else:
        output = format_tail(text)
    _emit(saved, output)
    return 0


def _python_exe():
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        sibling = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.isfile(sibling):
            return sibling
    return exe


def console_parent(pid, mode, keyword):
    args = [_python_exe(), os.path.abspath(__file__), "--console-read-worker", str(pid), mode]
    if mode == "find":
        args.append(keyword)
    proc = subprocess.run(args, capture_output=True, creationflags=CREATE_NO_WINDOW)
    text = (proc.stdout or b"").decode("utf-8", errors="replace")
    if not text and proc.stderr:
        text = proc.stderr.decode("utf-8", errors="replace")
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")
    return proc.returncode or (0 if text else 1)


def load_projects():
    data = _read_json(CONFIG_PATH) if os.path.isfile(CONFIG_PATH) else None
    paths = []
    if isinstance(data, dict):
        for entry in data.get("projects") or []:
            if isinstance(entry, str):
                paths.append(entry)
            elif isinstance(entry, dict) and entry.get("path"):
                paths.append(entry.get("path"))
    cleaned = []
    seen = set()
    for path in paths:
        norm = _norm(path)
        if norm in seen:
            continue
        seen.add(norm)
        cleaned.append(os.path.normpath(os.path.abspath(path)))
    return cleaned


def load_allow():
    data = _read_json(CONFIG_PATH) if os.path.isfile(CONFIG_PATH) else None
    allow = {}
    if isinstance(data, dict):
        for entry in data.get("items") or []:
            if not isinstance(entry, dict):
                continue
            if not entry.get("project") or not entry.get("source") or not entry.get("name"):
                continue
            allow[catalog_key(entry.get("project"), entry.get("source"), entry.get("name"))] = bool(entry.get("allowAgent"))
    return allow


def load_hidden():
    hidden = set()
    for entry in _load_config().get("hidden") or []:
        if not isinstance(entry, dict):
            continue
        if not entry.get("project") or not entry.get("source") or not entry.get("name"):
            continue
        hidden.add(catalog_key(entry.get("project"), entry.get("source"), entry.get("name")))
    return hidden


def _hidden_rows(hidden):
    rows = []
    for project, source, name in sorted(hidden):
        rows.append({"project": project, "source": source, "name": name})
    return rows


def build_items(projects, allow, hidden=None):
    if hidden is None:
        hidden = load_hidden()
    items = []
    seen = set()
    for path in projects:
        if not os.path.isdir(path):
            continue
        try:
            found = discover(path)
        except OSError:
            continue
        for item in found:
            key = catalog_key(path, item.source, item.name)
            if key in seen or key in hidden:
                continue
            seen.add(key)
            items.append({
                "project": os.path.normpath(os.path.abspath(path)),
                "source": item.source,
                "name": item.name,
                "cwd": os.path.normpath(os.path.abspath(item.cwd)),
                "allowAgent": bool(allow.get(key, True)),
            })
    return items


_CLOSE_ASK = "ask"
_CLOSE_STOP = "stop"
_CLOSE_LEAVE = "leave"
_CONSOLE_SHOW = "show"
_CONSOLE_MIN = "min"
_SW_SHOWMINNOACTIVE = 7


def _load_config():
    data = _read_json(CONFIG_PATH) if os.path.isfile(CONFIG_PATH) else None
    return data if isinstance(data, dict) else {}


def load_close_pref():
    value = _load_config().get("closeRunning")
    if value not in (_CLOSE_ASK, _CLOSE_STOP, _CLOSE_LEAVE):
        return _CLOSE_ASK
    return value


def load_console_pref():
    value = _load_config().get("showConsole")
    if value not in (_CONSOLE_SHOW, _CONSOLE_MIN):
        return _CONSOLE_SHOW
    return value


def save_ui_prefs(close_running=None, show_console=None):
    data = _load_config()
    if close_running is not None:
        data["closeRunning"] = close_running if close_running in (_CLOSE_ASK, _CLOSE_STOP, _CLOSE_LEAVE) else _CLOSE_ASK
    if show_console is not None:
        data["showConsole"] = show_console if show_console in (_CONSOLE_SHOW, _CONSOLE_MIN) else _CONSOLE_SHOW
    data.setdefault("projects", [])
    data.setdefault("items", [])
    data.setdefault("usage", _AGENT_USAGE)
    _write_json(CONFIG_PATH, data)


def _keep_pref(payload, data, key, allowed):
    if isinstance(data, dict) and data.get(key) in allowed:
        payload[key] = data[key]


def save_config(projects, items, hidden=None):
    data = _load_config()
    payload = {"projects": projects, "items": items, "usage": _AGENT_USAGE}
    _keep_pref(payload, data, "closeRunning", (_CLOSE_ASK, _CLOSE_STOP, _CLOSE_LEAVE))
    _keep_pref(payload, data, "showConsole", (_CONSOLE_SHOW, _CONSOLE_MIN))
    if hidden is None and isinstance(data.get("hidden"), list):
        payload["hidden"] = data["hidden"]
    elif hidden is not None:
        payload["hidden"] = _hidden_rows(hidden)
    _write_json(CONFIG_PATH, payload)


def _console_startupinfo():
    """最小化时收到任务栏，窗口还在，和点最小化一样。"""
    if load_console_pref() != _CONSOLE_MIN:
        return None
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = _SW_SHOWMINNOACTIVE
    return info


def save_projects(paths):
    save_config(paths, build_items(paths, load_allow()))


def _shortcut_target(path):
    """解析 Windows 快捷方式指向的路径。"""
    env = os.environ.copy()
    env["LAUNCHER_LNK"] = path
    command = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "$shell = New-Object -ComObject WScript.Shell; "
        "$shortcut = $shell.CreateShortcut($env:LAUNCHER_LNK); "
        "Write-Output $shortcut.TargetPath"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            env=env,
            creationflags=CREATE_NO_WINDOW,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.decode("utf-8", errors="replace").strip().strip("\ufeff")


def project_from_drop(path):
    """文件夹用自身，文件用它所在的目录，快捷方式先解析到目标。"""
    if not path:
        return ""
    path = os.path.abspath(path)
    if os.path.splitext(path)[1].lower() == ".lnk":
        path = _shortcut_target(path)
        if not path:
            return ""
        path = os.path.abspath(path)
    if os.path.isfile(path):
        path = os.path.dirname(path)
    if not os.path.isdir(path):
        return ""
    return os.path.normpath(path)


_ole32 = ctypes.WinDLL("ole32")
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_CF_HDROP = 15
_TYMED_HGLOBAL = 1
_DVASPECT_CONTENT = 1
_DROPEFFECT_NONE = 0
_DROPEFFECT_COPY = 1
_S_OK = 0
_E_NOINTERFACE = -2147467262
_DRAGDROP_HANDLES = []


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


def _guid(data1, data4):
    value = _GUID()
    value.Data1 = data1
    value.Data2 = 0
    value.Data3 = 0
    value.Data4 = (wintypes.BYTE * 8)(*data4)
    return value


_IID_IUNKNOWN = _guid(0x00000000, (0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))
_IID_IDROPTARGET = _guid(0x00000122, (0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))


class _FORMATETC(ctypes.Structure):
    _fields_ = [
        ("cfFormat", wintypes.WORD),
        ("ptd", ctypes.c_void_p),
        ("dwAspect", wintypes.DWORD),
        ("lindex", wintypes.LONG),
        ("tymed", wintypes.DWORD),
    ]


class _STGMEDIUM(ctypes.Structure):
    _fields_ = [
        ("tymed", wintypes.DWORD),
        ("hGlobal", ctypes.c_void_p),
        ("pUnkForRelease", ctypes.c_void_p),
    ]


_ole32.OleInitialize.argtypes = (ctypes.c_void_p,)
_ole32.OleInitialize.restype = ctypes.HRESULT
_ole32.OleUninitialize.argtypes = ()
_ole32.RegisterDragDrop.argtypes = (wintypes.HWND, ctypes.c_void_p)
_ole32.RegisterDragDrop.restype = ctypes.HRESULT
_ole32.RevokeDragDrop.argtypes = (wintypes.HWND,)
_ole32.RevokeDragDrop.restype = ctypes.HRESULT
_ole32.ReleaseStgMedium.argtypes = (ctypes.POINTER(_STGMEDIUM),)
_shell32.DragQueryFileW.argtypes = (ctypes.c_void_p, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT)
_shell32.DragQueryFileW.restype = wintypes.UINT

_QueryInterface = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
_AddRefRelease = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
_DragEnterDrop = ctypes.WINFUNCTYPE(
    ctypes.HRESULT,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_uint64,
    ctypes.POINTER(wintypes.DWORD),
)
_DragOver = ctypes.WINFUNCTYPE(
    ctypes.HRESULT,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_uint64,
    ctypes.POINTER(wintypes.DWORD),
)
_DragLeave = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)
_GetData = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(_FORMATETC), ctypes.POINTER(_STGMEDIUM))
_QueryGetData = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(_FORMATETC))


def _same_guid(left, right):
    return (
        left.Data1 == right.Data1
        and left.Data2 == right.Data2
        and left.Data3 == right.Data3
        and bytes(left.Data4) == bytes(right.Data4)
    )


def _hdrop_format():
    fmt = _FORMATETC()
    fmt.cfFormat = _CF_HDROP
    fmt.dwAspect = _DVASPECT_CONTENT
    fmt.lindex = -1
    fmt.tymed = _TYMED_HGLOBAL
    return fmt


def _com_vtbl(unk):
    return ctypes.cast(ctypes.cast(unk, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))


def _accepts_files(data_object):
    if not data_object:
        return False
    try:
        hr = _QueryGetData(_com_vtbl(data_object)[5])(data_object, ctypes.byref(_hdrop_format()))
    except Exception:
        return False
    return int(hr) == _S_OK


def _paths_from_data_object(data_object):
    medium = _STGMEDIUM()
    try:
        hr = _GetData(_com_vtbl(data_object)[3])(data_object, ctypes.byref(_hdrop_format()), ctypes.byref(medium))
    except Exception:
        return []
    if int(hr) != _S_OK or not medium.hGlobal:
        return []
    paths = []
    try:
        count = _shell32.DragQueryFileW(medium.hGlobal, 0xFFFFFFFF, None, 0)
        for index in range(count):
            size = _shell32.DragQueryFileW(medium.hGlobal, index, None, 0)
            buf = ctypes.create_unicode_buffer(size + 1)
            _shell32.DragQueryFileW(medium.hGlobal, index, buf, size + 1)
            if buf.value:
                paths.append(buf.value)
    finally:
        _ole32.ReleaseStgMedium(ctypes.byref(medium))
    return paths


def _set_effect(effect, value):
    if effect:
        effect[0] = value


class _DropTarget(ctypes.Structure):
    _fields_ = [("lpVtbl", ctypes.c_void_p), ("ref", ctypes.c_long)]


def install_drop_target(hwnds, on_enter, on_leave, on_drop):
    """把窗口登记成文件拖放目标。进入时 on_enter，离开时 on_leave，放下时 on_drop(路径列表)。"""
    init = _ole32.OleInitialize(None)
    started_ole = int(init) == _S_OK
    accepted = {"yes": False}
    targets = []

    def query_interface(this, riid, result):
        try:
            guid = riid.contents
            if _same_guid(guid, _IID_IUNKNOWN) or _same_guid(guid, _IID_IDROPTARGET):
                result[0] = this
                add_ref(this)
                return _S_OK
            result[0] = None
        except Exception:
            return _E_NOINTERFACE
        return _E_NOINTERFACE

    def add_ref(this):
        target = ctypes.cast(this, ctypes.POINTER(_DropTarget))
        target.contents.ref += 1
        return target.contents.ref

    def release(this):
        target = ctypes.cast(this, ctypes.POINTER(_DropTarget))
        target.contents.ref -= 1
        if target.contents.ref < 0:
            target.contents.ref = 0
        return target.contents.ref

    def drag_enter(this, data_object, _key, _point, effect):
        try:
            accepted["yes"] = _accepts_files(data_object)
            if accepted["yes"]:
                _set_effect(effect, _DROPEFFECT_COPY)
                on_enter()
            else:
                _set_effect(effect, _DROPEFFECT_NONE)
        except Exception:
            accepted["yes"] = False
            _set_effect(effect, _DROPEFFECT_NONE)
        return _S_OK

    def drag_over(this, _key, _point, effect):
        _set_effect(effect, _DROPEFFECT_COPY if accepted["yes"] else _DROPEFFECT_NONE)
        return _S_OK

    def drag_leave(this):
        try:
            on_leave()
        except Exception:
            pass
        return _S_OK

    def drop(this, data_object, _key, _point, effect):
        try:
            _set_effect(effect, _DROPEFFECT_COPY)
            on_drop(_paths_from_data_object(data_object))
        except Exception:
            try:
                on_leave()
            except Exception:
                pass
        return _S_OK

    callbacks = (
        _QueryInterface(query_interface),
        _AddRefRelease(add_ref),
        _AddRefRelease(release),
        _DragEnterDrop(drag_enter),
        _DragOver(drag_over),
        _DragLeave(drag_leave),
        _DragEnterDrop(drop),
    )
    vtable = (ctypes.c_void_p * len(callbacks))(*[ctypes.cast(item, ctypes.c_void_p) for item in callbacks])
    registered = []
    for hwnd in hwnds:
        if not hwnd:
            continue
        target = _DropTarget()
        target.lpVtbl = ctypes.cast(vtable, ctypes.c_void_p)
        target.ref = 1
        hr = _ole32.RegisterDragDrop(hwnd, ctypes.byref(target))
        if int(hr) == _S_OK:
            registered.append(int(hwnd))
            targets.append(target)
    if not registered:
        if started_ole:
            _ole32.OleUninitialize()
        return None
    _DRAGDROP_HANDLES.append((callbacks, vtable, targets, registered))

    def revoke():
        for hwnd in registered:
            _ole32.RevokeDragDrop(hwnd)
        registered.clear()
        if started_ole:
            _ole32.OleUninitialize()

    return revoke


class Launcher:
    def __init__(self, root):
        self.root = root
        root.title("服务启动器")
        root.minsize(640, 280)
        root.resizable(True, True)
        self.procs = {}
        self.labels = {}
        self.modes = {}
        self.run_meta = {}
        self.check_vars = []
        self.hwnd = 0
        self._drop_revoke = None
        self.projects = load_projects()
        self.saved = list(self.projects)
        self.allow = load_allow()
        self.hidden = load_hidden()
        self.cards = {}
        self.shown = {}

        bar = ttk.Frame(root)
        bar.pack(side="top", fill="x", padx=12, pady=(12, 4))
        ttk.Button(bar, text="关联项目", command=self.associate).pack(side="left")
        ttk.Button(bar, text="保存", command=self.save).pack(side="left", padx=8)
        ttk.Button(bar, text="复制给 Agent", command=self.copy_card).pack(side="left")
        self.hint = ttk.Label(bar, text="", foreground="gray")
        self.hint.pack(side="left", padx=8)
        gear_bg = ttk.Style(root).lookup("TFrame", "background") or root.cget("bg")
        settings = tk.Label(bar, text="⚙", font=("Segoe UI Symbol", 14), bg=gear_bg, cursor="hand2")
        settings.pack(side="right", padx=(8, 18))
        settings.bind("<Button-1>", lambda _event: self.open_settings())
        ToolTip(settings, "设置")
        ttk.Label(root, text="关闭会立刻关掉对应的 cmd 窗口", foreground="gray").pack(side="bottom", pady=8)

        self.canvas = tk.Canvas(root, highlightthickness=0)
        self.scroll = ttk.Scrollbar(root, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.window_id = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=4)
        self.scroll.pack(side="right", fill="y", padx=(0, 8), pady=4)
        self.canvas.bind("<Configure>", self._stretch)
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))
        self.drop_cover = tk.Frame(root, bg="#eef5ff", highlightthickness=3, highlightbackground="#4c8dff")
        drop_box = tk.Frame(self.drop_cover, bg="#eef5ff")
        drop_box.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(drop_box, text="拖入关联项目", bg="#eef5ff", font=("", 18)).pack()
        tk.Label(drop_box, text="文件夹或快捷方式关联其目录，文件关联它所在的目录", bg="#eef5ff", fg="#667085").pack(pady=(8, 0))
        tk.Label(drop_box, text="松开后加入列表，点保存才会保留", bg="#eef5ff", fg="#667085").pack(pady=(4, 0))
        self._render()
        self._place_center(760, 480)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(0, self._attach_window)
        self.root.after(800, self._poll)

    def _place_center(self, width, height):
        # 窗口第一次显示时，Windows 会丢掉事先写好的坐标，改用自己的默认位置。
        # 先隐藏，摆正后再显示，坐标才会留住。
        self.root.withdraw()
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.deiconify()
        self.root.update()
        rect = wintypes.RECT()
        hwnd = ctypes.windll.user32.GetAncestor(self.root.winfo_id(), _GA_ROOT)
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        actual_w = rect.right - rect.left
        actual_h = rect.bottom - rect.top
        target_x = max(0, (screen_w - actual_w) // 2)
        target_y = max(0, (screen_h - actual_h) // 2)
        x += target_x - rect.left
        y += target_y - rect.top
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _field_bg(self):
        if not hasattr(self, "_selectable_bg"):
            style = ttk.Style(self.root)
            self._selectable_bg = style.lookup("TFrame", "background") or self.root.cget("bg")
        return self._selectable_bg

    def _selectable(self, parent, text, width):
        bg = self._field_bg()
        widget = tk.Entry(
            parent,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            readonlybackground=bg,
            width=width,
            takefocus=0,
        )
        widget.insert(0, text)
        widget.configure(state="readonly")
        return widget

    def _set_selectable(self, widget, text, color):
        widget.configure(state="normal", fg=color)
        widget.delete(0, "end")
        widget.insert(0, text)
        widget.configure(state="readonly")

    def _stretch(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _refresh_hint(self):
        if [_norm(path) for path in self.projects] == [_norm(path) for path in self.saved]:
            self.hint.config(text="已保存，下次打开会直接出现这些项目")
        else:
            self.hint.config(text="未保存，关闭后这次关联不会保留")

    def associate(self):
        path = filedialog.askdirectory(title="关联项目", initialdir=self.projects[-1] if self.projects else APP_DIR)
        if not path:
            return
        self._add_project(path)

    def _add_project(self, path):
        path = project_from_drop(path)
        if not path:
            return "skip"
        if _norm(path) in {_norm(item) for item in self.projects}:
            return "duplicate"
        was_empty = not self.projects
        self.projects.append(path)
        if was_empty:
            self._clear_body()
        self._render_project(path)
        self._refresh_hint()
        return "added"

    def _show_drop_hint(self):
        if not self.drop_cover.winfo_ismapped():
            self.drop_cover.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.drop_cover.lift()
            self.root.update_idletasks()

    def _hide_drop_hint(self):
        if self.drop_cover.winfo_ismapped():
            self.drop_cover.place_forget()
            self.root.update_idletasks()

    def _drop_projects(self, paths):
        added = False
        duplicate = False
        seen = set()
        for raw in paths:
            path = project_from_drop(raw)
            if not path or _norm(path) in seen:
                continue
            seen.add(_norm(path))
            result = self._add_project(path)
            added = added or result == "added"
            duplicate = duplicate or result == "duplicate"
        self._hide_drop_hint()
        if not added and duplicate:
            self.hint.config(text="这个项目已经关联")

    def remove(self, path):
        norm = _norm(path)
        self.projects = [item for item in self.projects if _norm(item) != norm]
        self.modes.pop(norm, None)
        self.hidden = {key for key in self.hidden if key[0] != norm}
        self._drop_card(path)
        if not self.projects:
            self._clear_body()
            ttk.Label(
                self.body,
                text="尚未关联项目。选择目录后按该项目自己的启动配置显示按钮，点保存才会写入配置。",
                foreground="gray",
            ).pack(anchor="w", padx=8, pady=12)
        self._refresh_hint()

    def save(self):
        try:
            save_config(self.projects, build_items(self.projects, self.allow, self.hidden), self.hidden)
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        self.saved = list(self.projects)
        self._refresh_hint()

    def _persist_allow(self):
        self._persist_saved()

    def _persist_saved(self):
        if [_norm(path) for path in self.projects] != [_norm(path) for path in self.saved]:
            self._refresh_hint()
            return
        try:
            save_config(self.saved, build_items(self.saved, self.allow, self.hidden), self.hidden)
        except OSError as exc:
            self.hint.config(text=str(exc))

    def _hwnd_text(self):
        if not self.hwnd:
            self._attach_window()
        return _format_hwnd(self.hwnd) if self.hwnd else ""

    def _attach_window(self):
        hwnd = _top_hwnd(self.root)
        if not hwnd:
            self.root.after(100, self._attach_window)
            return
        self.hwnd = int(hwnd)
        _sweep_dead_runs()
        os.makedirs(_run_folder(self._hwnd_text()), exist_ok=True)
        self._write_runtime()
        if self._drop_revoke is None:
            client = int(self.root.winfo_id())
            self._drop_revoke = install_drop_target([client], self._show_drop_hint, self._hide_drop_hint, self._drop_projects)

    def _running_items(self):
        found = []
        for meta in self.run_meta.values():
            item = meta.get("item")
            if item is not None and self._running(item.key):
                found.append(item)
        return found

    def _center_dialog(self, dialog, width, height):
        self.root.update_idletasks()
        dialog.update_idletasks()
        width = max(int(width), dialog.winfo_reqwidth())
        height = max(int(height), dialog.winfo_reqheight())
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    def _ask_close_running(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("关闭启动器")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.withdraw()
        result = {"value": None}
        ttk.Label(dialog, text="是否关闭正在启动的服务").pack(anchor="w", padx=16, pady=(16, 8))
        remember = tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog, text="记住这次选择", variable=remember).pack(anchor="w", padx=16)
        buttons = ttk.Frame(dialog)
        buttons.pack(side="bottom", fill="x", padx=16, pady=16)

        def choose(stop):
            result["value"] = (bool(stop), bool(remember.get()))
            dialog.destroy()

        ttk.Button(buttons, text="否", width=8, command=lambda: choose(False)).pack(side="right")
        ttk.Button(buttons, text="是", width=8, command=lambda: choose(True)).pack(side="right", padx=(0, 8))
        self._center_dialog(dialog, 320, 140)
        dialog.deiconify()
        dialog.grab_set()
        dialog.wait_window()
        return result["value"]

    def open_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("设置")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.withdraw()
        choice = tk.StringVar(value=load_close_pref())
        console = tk.StringVar(value=load_console_pref())
        group = ttk.LabelFrame(dialog, text="关闭启动器时")
        group.pack(fill="x", padx=16, pady=(16, 8))
        ttk.Radiobutton(group, text="每次询问", value=_CLOSE_ASK, variable=choice).pack(anchor="w", padx=12, pady=(8, 2))
        ttk.Radiobutton(group, text="关闭正在运行的服务", value=_CLOSE_STOP, variable=choice).pack(anchor="w", padx=12, pady=2)
        ttk.Radiobutton(group, text="不关闭服务，只关窗口", value=_CLOSE_LEAVE, variable=choice).pack(anchor="w", padx=12, pady=(2, 10))
        console_group = ttk.LabelFrame(dialog, text="启动时的 cmd 窗口")
        console_group.pack(fill="x", padx=16, pady=(0, 8))
        ttk.Radiobutton(console_group, text="弹出", value=_CONSOLE_SHOW, variable=console).pack(anchor="w", padx=12, pady=(8, 2))
        ttk.Radiobutton(console_group, text="最小化到任务栏", value=_CONSOLE_MIN, variable=console).pack(anchor="w", padx=12, pady=(2, 10))
        ttk.Frame(dialog, height=36).pack(fill="x")
        buttons = ttk.Frame(dialog)
        buttons.pack(side="bottom", fill="x", padx=16, pady=16)

        def ok():
            try:
                save_ui_prefs(close_running=choice.get(), show_console=console.get())
            except OSError as exc:
                messagebox.showerror("保存失败", str(exc), parent=dialog)
                return
            dialog.destroy()

        ttk.Button(buttons, text="取消", width=8, command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="确定", width=8, command=ok).pack(side="right", padx=(0, 8))
        self._center_dialog(dialog, 340, 320)
        dialog.deiconify()
        dialog.grab_set()
        dialog.wait_window()

    def _on_close(self):
        running = self._running_items()
        if running:
            pref = load_close_pref()
            if pref == _CLOSE_ASK:
                answer = self._ask_close_running()
                if answer is None:
                    return
                stop, remember = answer
                if remember:
                    try:
                        save_ui_prefs(close_running=_CLOSE_STOP if stop else _CLOSE_LEAVE)
                    except OSError as exc:
                        messagebox.showerror("保存失败", str(exc))
                        return
                if stop:
                    for item in running:
                        self.close(item)
            elif pref == _CLOSE_STOP:
                for item in running:
                    self.close(item)
        if self._drop_revoke is not None:
            self._drop_revoke()
            self._drop_revoke = None
        if self.hwnd:
            shutil.rmtree(_run_folder(self._hwnd_text()), ignore_errors=True)
        self.root.destroy()

    def copy_card(self):
        hwnd = self._hwnd_text()
        if not hwnd:
            self.hint.config(text="窗口还没准备好，稍后再复制")
            return
        text = render_copy_prompt(APP_DIR, hwnd)
        if not text:
            self.hint.config(text="没有读到复制提示词.txt")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        self.hint.config(text="已复制，可贴给 Agent")

    def _clear_body(self):
        for child in self.body.winfo_children():
            child.destroy()
        self.labels = {}
        self.check_vars = []
        self.cards = {}
        self.shown = {}

    def _drop_card(self, path):
        norm = _norm(path)
        prefix = norm + "|"
        for key in list(self.labels):
            if key.startswith(prefix):
                self.labels.pop(key, None)
        self.shown.pop(norm, None)
        frame = self.cards.pop(norm, None)
        if frame is not None and frame.winfo_exists():
            frame.destroy()

    def _render(self):
        self._clear_body()
        self._refresh_hint()
        if not self.projects:
            ttk.Label(
                self.body,
                text="尚未关联项目。选择目录后按该项目自己的启动配置显示按钮，点保存才会写入配置。",
                foreground="gray",
            ).pack(anchor="w", padx=8, pady=12)
            return
        for path in self.projects:
            self._render_project(path)

    def _mode(self, path):
        return self.modes.get(_norm(path), "vscode")

    def _set_mode(self, path, mode):
        if self._mode(path) == mode:
            return
        self.modes[_norm(path)] = mode
        self._refresh_project(path)

    def _refresh_project(self, path):
        norm = _norm(path)
        old = self.cards.get(norm)
        before = None
        if old is not None and old.winfo_exists():
            slaves = list(old.master.pack_slaves())
            if old in slaves:
                index = slaves.index(old)
                if index + 1 < len(slaves):
                    before = slaves[index + 1]
        self._drop_card(path)
        self._render_project(path, before=before)

    def _project_items(self, path):
        mode = self._mode(path)
        try:
            found = discover(path)
        except OSError:
            found = []
        visible = []
        for item in found:
            if item.source != mode:
                continue
            if catalog_key(path, item.source, item.name) in self.hidden:
                continue
            visible.append(item)
        self._rekey_running(path, visible)
        return visible

    def _rekey_running(self, path, items):
        prefix = _norm(path) + "|"
        by_name = {}
        for key, proc in list(self.procs.items()):
            if not str(key).startswith(prefix):
                continue
            parts = str(key).split("|", 3)
            if len(parts) == 4:
                by_name[(parts[1], parts[3])] = key
        for item in items:
            old = by_name.get((item.source, item.name))
            if not old or old == item.key:
                continue
            proc = self.procs.pop(old, None)
            if proc is not None:
                self.procs[item.key] = proc
            meta = self.run_meta.pop(old, None)
            if meta is not None:
                meta["item"] = item
                self.run_meta[item.key] = meta

    def _fit_project_header(self, header, width):
        width = max(int(width) - 24, 280)
        height = 32
        if header.winfo_width() != width or header.winfo_height() != height:
            header.configure(width=width, height=height)

    def start_project(self, path):
        mode = self._mode(path)
        side = "VS Code" if mode == "vscode" else "IDEA"
        if not os.path.isdir(path):
            messagebox.showerror("无法启动", "路径不存在")
            return
        items = list(self.shown.get(_norm(path), []))
        if not items:
            self.hint.config(text="这一侧没有可启动的配置")
            return
        failures = []
        started = 0
        for item in items:
            if self._running(item.key):
                continue
            ok, message = self.start(item, interactive=False)
            if ok:
                started += 1
            else:
                failures.append(f"{item.name}：{message}")
        if failures:
            messagebox.showerror("有启动项没有启动", "\n".join(failures))
        elif started == 0:
            self.hint.config(text=f"{side} 这一侧已经都在运行")
        else:
            self.hint.config(text=f"已一键启动 {side} 的 {started} 项")

    def _bind_item_menu(self, row, path, item):
        menu = tk.Menu(row, tearoff=0)
        menu.add_command(label="配置文件夹", command=lambda spec=item: self.open_config_file(spec))
        menu.add_command(label="移除", command=lambda p=path, spec=item: self.hide_item(p, spec))

        def popup(event, menu=menu):
            menu.tk_popup(event.x_root, event.y_root)
            menu.grab_release()

        def bind_children(widget):
            widget.bind("<Button-3>", popup)
            for child in widget.winfo_children():
                bind_children(child)

        bind_children(row)

    def open_config_file(self, item):
        path = item.config_path or ""
        if not path or not os.path.isfile(path):
            self.hint.config(text="配置文件不存在")
            return
        subprocess.Popen(["explorer.exe", "/select,", os.path.normpath(path)])

    def hide_item(self, path, item):
        self.hidden.add(catalog_key(path, item.source, item.name))
        self._persist_saved()
        self._refresh_project(path)

    def _render_project(self, path, before=None):
        mode = self._mode(path)
        header = ttk.Frame(self.body)
        header.pack_propagate(False)
        left = ttk.Frame(header)
        left.pack(side="left", fill="y")
        title_text = os.path.basename(path) or path
        title = self._selectable(left, title_text, max(8, min(36, len(title_text))))
        title.pack(side="left")
        ToolTip(title, path)
        tk.Button(
            left,
            text="VS Code",
            relief="sunken" if mode == "vscode" else "raised",
            command=lambda p=path: self._set_mode(p, "vscode"),
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            left,
            text="IDEA",
            relief="sunken" if mode == "idea" else "raised",
            command=lambda p=path: self._set_mode(p, "idea"),
        ).pack(side="left", padx=(2, 0))
        ttk.Button(left, text="移除", width=4, command=lambda p=path: self.remove(p)).pack(side="left", padx=(8, 0))
        ttk.Button(header, text="一键启动", command=lambda p=path: self.start_project(p)).place(relx=0.5, rely=0.5, anchor="center")
        frame = ttk.LabelFrame(self.body, labelwidget=header)
        frame.bind("<Configure>", lambda event, box=header: self._fit_project_header(box, event.width), add="+")
        if before is not None:
            frame.pack(fill="x", padx=4, pady=6, before=before)
        else:
            frame.pack(fill="x", padx=4, pady=6)
        self.cards[_norm(path)] = frame
        if not os.path.isdir(path):
            self.shown[_norm(path)] = []
            ttk.Label(frame, text="路径不存在", foreground="gray").pack(anchor="w", padx=8, pady=6)
            return
        items = self._project_items(path)
        self.shown[_norm(path)] = items
        if not items:
            ttk.Label(frame, text="这一侧没有可启动的配置", foreground="gray").pack(anchor="w", padx=8, pady=6)
            return
        for item in items:
            row = ttk.Frame(frame)
            row.pack(fill="x", padx=8, pady=4)
            buttons = ttk.Frame(row)
            buttons.pack(side="right")
            ttk.Button(buttons, text="启动", width=6, command=lambda spec=item: self.start(spec)).pack(side="left", padx=2)
            ttk.Button(buttons, text="重启", width=6, command=lambda spec=item: self.restart(spec)).pack(side="left", padx=2)
            ttk.Button(buttons, text="关闭", width=6, command=lambda spec=item: self.close(spec)).pack(side="left", padx=2)
            allow_key = catalog_key(path, item.source, item.name)
            checked = tk.BooleanVar(value=self.allow.get(allow_key, True))
            self.check_vars.append(checked)

            def toggle(key=allow_key, var=checked):
                self.allow[key] = bool(var.get())
                self._persist_allow()

            agent = ttk.Checkbutton(row, text="AI 托管", variable=checked, command=toggle)
            agent.pack(side="left")
            ToolTip(agent, "勾选后，AI 才能启动、重启或关闭这一项")
            name = self._selectable(row, item.name, max(8, min(36, len(item.name))))
            name.pack(side="left", padx=(8, 0))
            status = self._selectable(row, "未启动", 16)
            self._set_selectable(status, "未启动", "gray")
            status.pack(side="left", padx=8)
            if item.jdk_error:
                ttk.Label(row, text=item.jdk_error, foreground="gray").pack(side="left")
            self.labels[item.key] = status
            self._bind_item_menu(row, path, item)
        self._paint()

    def _running(self, key):
        proc = self.procs.get(key)
        return proc is not None and proc.poll() is None

    def _paint(self):
        for key, label in self.labels.items():
            if self._running(key):
                self._set_selectable(label, f"已启动 {self.procs[key].pid}", "green")
            else:
                self._set_selectable(label, "未启动", "gray")

    def _remember(self, item, state, error="", pid=None, token="", title=""):
        self.run_meta[item.key] = {
            "item": item,
            "state": state,
            "error": error,
            "pid": pid,
            "token": token,
            "title": title,
        }
        self._write_runtime()

    def _project_of(self, item):
        prefix = item.key.split("|", 1)[0]
        for path in list(self.projects) + list(self.saved):
            if _norm(path) == prefix:
                return os.path.normpath(os.path.abspath(path))
        return prefix

    def _write_runtime(self):
        if not self.hwnd:
            return
        items = []
        for meta in self.run_meta.values():
            item = meta["item"]
            state = meta.get("state") or "stopped"
            pid = meta.get("pid") if state == "running" else None
            items.append({
                "project": self._project_of(item),
                "source": item.source,
                "name": item.name,
                "state": state,
                "cmdPid": pid,
                "cmdToken": meta.get("token") or "",
                "cmdTitle": meta.get("title") or "",
                "error": meta.get("error") or "",
            })
        try:
            _write_json(
                os.path.join(_run_folder(self._hwnd_text()), "status.json"),
                {"hwnd": self._hwnd_text(), "launcherPid": os.getpid(), "items": items},
            )
        except OSError:
            pass

    def start(self, item, interactive=True):
        if self._running(item.key):
            return True, "已在运行"
        if item.jdk_error:
            message = item.jdk_error + "\n没有改用系统 JDK。"
            self._remember(item, "error", error=item.jdk_error)
            if interactive:
                messagebox.showerror("无法启动", message)
            return False, message
        if not os.path.isdir(item.cwd):
            message = f"目录不存在：{item.cwd}"
            self._remember(item, "error", error=message)
            if interactive:
                messagebox.showerror("无法启动", message)
            return False, message
        token = uuid.uuid4().hex[:8]
        command, title = _console_command(item.name, item.command, token)
        proc = subprocess.Popen(
            command,
            cwd=item.cwd,
            env=_merge_env(item.env),
            creationflags=CREATE_NEW_CONSOLE,
            startupinfo=_console_startupinfo(),
        )
        self.procs[item.key] = proc
        self._remember(item, "running", pid=proc.pid, token=token, title=title)
        self._paint()
        return True, "已启动"

    def close(self, item):
        proc = self.procs.get(item.key)
        if proc and proc.poll() is None:
            _kill(proc)
        self.procs.pop(item.key, None)
        meta = self.run_meta.get(item.key)
        if meta:
            meta["state"] = "stopped"
            meta["pid"] = None
            meta["error"] = ""
            self._write_runtime()
        self._paint()

    def restart(self, item, interactive=True, on_done=None):
        old = self.procs.get(item.key)
        self.close(item)

        def go(tries=0):
            if old is not None and old.poll() is None and tries < 40:
                self.root.after(100, lambda: go(tries + 1))
                return
            ok, message = self.start(item, interactive=interactive)
            if on_done:
                on_done(ok, "已重启" if ok else message)

        go()

    def _sync_runtime(self):
        changed = False
        for key, meta in self.run_meta.items():
            if meta.get("state") != "running":
                continue
            proc = self.procs.get(key)
            if proc is None or proc.poll() is not None:
                meta["state"] = "exited"
                meta["pid"] = None
                changed = True
        if changed:
            self._write_runtime()

    def _finish_agent(self, request_id, ok, message):
        if not self.hwnd or not request_id:
            return
        try:
            _write_json(
                os.path.join(_run_folder(self._hwnd_text()), f"result-{request_id}.json"),
                {"id": request_id, "ok": bool(ok), "message": message},
            )
        except OSError as exc:
            self.hint.config(text=str(exc))

    def _find_spec(self, catalog_item):
        project = catalog_item.get("project")
        if not project or not os.path.isdir(project):
            return None
        try:
            found = discover(project)
        except OSError:
            return None
        fallback = None
        for item in found:
            if item.source != catalog_item.get("source") or item.name != catalog_item.get("name"):
                continue
            if fallback is None:
                fallback = item
            if _norm(item.cwd) == _norm(catalog_item.get("cwd") or ""):
                return item
        return fallback

    def _run_agent_command(self, data):
        request_id = str(data.get("id") or "")
        try:
            items = build_items(self.saved, self.allow)
            save_config(self.saved, items)
            hit, reason = check_agent_call(
                items,
                data.get("project"),
                data.get("source"),
                data.get("name"),
                data.get("file"),
            )
            if hit is None:
                self._finish_agent(request_id, False, reason)
                return
            spec = self._find_spec(hit)
            if spec is None:
                self._finish_agent(request_id, False, "窗口里已经没有这一项，未操作。")
                return
            action = data.get("action")
            if action == "start":
                ok, message = self.start(spec, interactive=False)
                self._finish_agent(request_id, ok, message)
            elif action == "close":
                self.close(spec)
                self._finish_agent(request_id, True, "已关闭")
            elif action == "restart":
                self.restart(
                    spec,
                    interactive=False,
                    on_done=lambda ok, message, ident=request_id: self._finish_agent(ident, ok, message),
                )
            else:
                self._finish_agent(request_id, False, "动作只能是 start、restart 或 close，未操作。")
        except Exception as exc:
            self._finish_agent(request_id, False, f"执行失败：{exc}")

    def _take_commands(self):
        if not self.hwnd:
            return
        folder = _run_folder(self._hwnd_text())
        if not os.path.isdir(folder):
            return
        for name in sorted(os.listdir(folder)):
            if not (name.startswith("cmd-") and name.endswith(".json")):
                continue
            path = os.path.join(folder, name)
            data = _read_json(path)
            try:
                os.remove(path)
            except OSError:
                continue
            if isinstance(data, dict):
                self._run_agent_command(data)

    def _poll(self):
        try:
            self._paint()
            self._sync_runtime()
            self._take_commands()
        except Exception as exc:
            self.hint.config(text=str(exc))
        self.root.after(800, self._poll)


def _print_cli_usage():
    print("查看输出：python start.py --console-tail <cmd进程号>")
    print("按关键字查：python start.py --console-find <cmd进程号> <关键字>")
    print("启停：python start.py --tell <窗口句柄> start|restart|close --project <项目> --source vscode|idea --name <配置名> --file <改动文件>")


def _cli_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def cli_main(argv):
    _cli_stdout()
    if "--console-read-worker" in argv:
        index = argv.index("--console-read-worker")
        pid = int(argv[index + 1])
        mode = argv[index + 2]
        keyword = " ".join(argv[index + 3 :])
        return console_worker(pid, mode, keyword)
    if "--console-tail" in argv:
        index = argv.index("--console-tail")
        if index + 1 >= len(argv):
            _print_cli_usage()
            return 2
        return console_parent(int(argv[index + 1]), "tail", "")
    if "--console-find" in argv:
        index = argv.index("--console-find")
        if index + 2 >= len(argv):
            _print_cli_usage()
            return 2
        keyword = " ".join(argv[index + 2 :]).strip()
        if not keyword:
            _print_cli_usage()
            return 2
        return console_parent(int(argv[index + 1]), "find", keyword)
    if "--tell" in argv:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--tell")
        parser.add_argument("--project")
        parser.add_argument("--source")
        parser.add_argument("--name")
        parser.add_argument("--file")
        parser.add_argument("action", nargs="?", choices=["start", "restart", "close"])
        try:
            args = parser.parse_args(argv[1:])
        except SystemExit:
            _print_cli_usage()
            return 2
        if not args.tell or not args.action or not args.project or not args.source or not args.name or not args.file:
            _print_cli_usage()
            return 2
        return tell_main(args.tell, args.action, args.project, args.source, args.name, args.file)
    _print_cli_usage()
    return 2


def tell_main(hwnd_text, action, project, source, name, file_path):
    if _parse_hwnd(hwnd_text) is None:
        print("窗口句柄无效。请从目标窗口重新复制。")
        return 1
    folder = _run_folder(_format_hwnd(_parse_hwnd(hwnd_text)))
    if not _window_alive(folder):
        print("窗口未打开。请先打开对应的服务启动器，并重新复制。")
        return 1
    items = build_items(load_projects(), load_allow())
    hit, reason = check_agent_call(items, project, source, name, file_path)
    if hit is None:
        print(reason)
        return 1
    request_id = uuid.uuid4().hex
    _write_json(
        os.path.join(folder, f"cmd-{request_id}.json"),
        {
            "id": request_id,
            "action": action,
            "project": project,
            "source": source,
            "name": name,
            "file": os.path.abspath(file_path),
        },
    )
    result_path = os.path.join(folder, f"result-{request_id}.json")
    deadline = time.time() + 30
    while time.time() < deadline:
        if os.path.isfile(result_path):
            data = _read_json(result_path)
            try:
                os.remove(result_path)
            except OSError:
                pass
            if not isinstance(data, dict):
                print("窗口返回的结果无法读取。")
                return 1
            print(data.get("message") or "")
            return 0 if data.get("ok") else 1
        time.sleep(0.2)
    print("窗口没有响应。请确认服务启动器仍打开着。")
    return 1


if __name__ == "__main__":
    if any(flag in sys.argv for flag in _CLI_FLAGS):
        sys.exit(cli_main(sys.argv))
    try:
        root = tk.Tk()
        Launcher(root)
        root.lift()
        hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), _GA_ROOT)
        _raise = 0x0001 | 0x0002 | 0x0040
        ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, _raise)
        root.after(500, lambda: ctypes.windll.user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, _raise))
        root.mainloop()
    except Exception:
        import traceback
        msg = traceback.format_exc()
        try:
            messagebox.showerror("启动失败", msg)
        except Exception:
            ctypes.windll.user32.MessageBoxW(0, msg, "启动失败", 0x10)
