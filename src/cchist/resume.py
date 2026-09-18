# SPDX-License-Identifier: MIT
"""跨平台 resume:切到会话工作目录并接管终端进入对应工具的 resume。

机制:TUI 无法从自身进程干净地 exec(会破坏终端状态),所以 TUI 选中后
把目标写入信号文件并退出,由 CLI 包装层读取信号并执行真正的 resume。
支持多 provider:claude → `claude --resume`,codex → `codex resume`。
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys

from . import config, providers


def signal_file() -> str:
    return str(config.claude_dir() / ".cchist_resume")


def write_signal(target_dir: str, session_id: str, provider_name: str = "claude"):
    with open(signal_file(), "w", encoding="utf-8") as f:
        f.write(f"{target_dir}\n{session_id}\n{provider_name}\n")


def clear_signal():
    sig = signal_file()
    if os.path.exists(sig):
        os.remove(sig)


def consume_signal():
    """读取并清除信号。返回 (目标目录, 会话ID, provider) 或 None。"""
    sig = signal_file()
    if not os.path.exists(sig):
        return None
    try:
        with open(sig, encoding="utf-8") as f:
            lines = f.read().splitlines()
        os.remove(sig)
    except OSError:
        return None
    if len(lines) >= 2 and lines[1].strip():
        pname = lines[2].strip() if len(lines) >= 3 and lines[2].strip() else "claude"
        return lines[0].strip(), lines[1].strip(), pname
    return None


def do_resume(target_dir: str, session_id: str, provider_name: str = "claude") -> int:
    """切目录并用对应工具 resume。跨平台:

    - POSIX: 用 os.execvp 把当前进程替换成目标命令,交互无缝。
    - Windows: os.execvp 对交互程序不可靠,改用 subprocess 并等待。
    """
    prov = providers.get(provider_name)
    argv = prov.resume_cmd(target_dir, session_id)
    exe = shutil.which(argv[0])
    if not exe:
        print(f"✗ 未找到 {argv[0]} 命令,请确认 {prov.label} 已安装并在 PATH 中。", file=sys.stderr)
        return 1

    if not target_dir or not os.path.isdir(target_dir):
        target_dir = os.path.expanduser("~")
    os.chdir(target_dir)
    print(f"→ 进入 {target_dir}")
    print(f"→ resume {prov.label} 会话 {session_id}")

    argv[0] = exe
    if os.name == "nt":
        return subprocess.call(argv)
    else:
        os.execvp(exe, argv)
        return 0  # execvp 成功不会返回到这


# ---- 在当前终端里直接打开(TUI 挂起后调用,退出对话即回到列表) ----
def run_here(target_dir: str, session_id: str, provider_name: str = "claude"):
    """在当前终端直接 resume。必须由 TUI 在 suspend 状态下调用。

    返回 (成功与否, 信息):成功时信息为子进程退出码,失败时为错误说明。
    适用于任何终端(VS Code / PyCharm / 原生终端),无需探测终端模拟器。
    """
    prov = providers.get(provider_name)
    argv = prov.resume_cmd(target_dir, session_id)
    exe = shutil.which(argv[0])
    if not exe:
        return False, f"未找到 {argv[0]} 命令,请确认 {prov.label} 已安装并在 PATH 中"
    argv[0] = exe
    if not target_dir or not os.path.isdir(target_dir):
        target_dir = os.path.expanduser("~")
    return True, subprocess.call(argv, cwd=target_dir)


# ---- 在新终端窗口里打开(当前 TUI 不退出) ----
# 常见终端模拟器探测顺序;$TERMINAL 可覆盖
_TERMINAL_CANDIDATES = [
    "gnome-terminal", "konsole", "xfce4-terminal", "alacritty", "kitty",
    "wezterm", "mate-terminal", "lxterminal", "tilix", "xterm",
]


def detect_terminal() -> str | None:
    """找到可用的终端模拟器可执行文件路径。优先 $TERMINAL 环境变量。"""
    env_term = os.environ.get("TERMINAL", "").strip()
    candidates = ([env_term] if env_term else []) + _TERMINAL_CANDIDATES
    for term in candidates:
        exe = shutil.which(term)
        if exe:
            return exe
    return None


def _terminal_argv(term: str, inner_cmd: str) -> list[str]:
    """不同终端模拟器的"跑一条 shell 命令"参数形式不一样。"""
    name = os.path.basename(term)
    if name == "gnome-terminal":
        return [term, "--", "bash", "-c", inner_cmd]
    if name == "wezterm":
        return [term, "start", "--", "bash", "-c", inner_cmd]
    if name == "xfce4-terminal":
        # -x = 把剩余参数整体当作命令执行(-e 只接单个字符串,容易踩坑)
        return [term, "-x", "bash", "-c", inner_cmd]
    # konsole / xterm / alacritty / kitty / mate-terminal / lxterminal / tilix
    return [term, "-e", "bash", "-c", inner_cmd]


def open_in_new_terminal(target_dir: str, session_id: str, provider_name: str = "claude"):
    """弹出一个独立终端窗口,在其中 resume 会话;cchist 自身保持运行。

    返回 (成功与否, 提示消息)。结束后窗口里留一个 bash,方便确认完再关。
    """
    prov = providers.get(provider_name)
    argv = prov.resume_cmd(target_dir, session_id)
    tool = shutil.which(argv[0])
    if not tool:
        return False, f"未找到 {argv[0]} 命令,请确认 {prov.label} 已安装并在 PATH 中"
    argv[0] = tool

    term = detect_terminal()
    if not term:
        return False, "未找到可用终端模拟器(可设 $TERMINAL 指定,如 export TERMINAL=gnome-terminal)"

    if not target_dir or not os.path.isdir(target_dir):
        target_dir = os.path.expanduser("~")

    inner = "cd {} && {} ; exec bash".format(shlex.quote(target_dir), shlex.join(argv))
    try:
        subprocess.Popen(
            _terminal_argv(term, inner),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,  # 脱离本进程,关掉 cchist 不影响新窗口
        )
    except OSError as e:
        return False, f"启动终端失败:{e}"
    return True, f"已在新终端打开({os.path.basename(term)}),本列表保持运行"
