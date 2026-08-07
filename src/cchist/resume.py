# SPDX-License-Identifier: MIT
"""跨平台 resume:切到会话工作目录并接管终端进入对应工具的 resume。

机制:TUI 无法从自身进程干净地 exec(会破坏终端状态),所以 TUI 选中后
把目标写入信号文件并退出,由 CLI 包装层读取信号并执行真正的 resume。
支持多 provider:claude → `claude --resume`,codex → `codex resume`。
"""
from __future__ import annotations

import os
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
