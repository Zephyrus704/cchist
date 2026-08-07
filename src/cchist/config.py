"""集中管理路径配置。支持环境变量覆盖,保证跨机器/跨平台可移植。"""
import os
from pathlib import Path


def claude_dir() -> Path:
    """Claude Code 配置根目录。

    优先读环境变量 CLAUDE_CONFIG_DIR(官方也用这个变量),
    否则回退到 ~/.claude。这样在任何机器/任何用户下都能正确定位。
    """
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".claude"


def projects_dir() -> Path:
    return claude_dir() / "projects"


def trash_dir() -> Path:
    return claude_dir() / ".cchist_trash"


def favorites_file() -> Path:
    return claude_dir() / ".cchist_favorites.json"


def config_file() -> Path:
    return claude_dir() / ".cchist_config.json"
