# SPDX-License-Identifier: MIT
"""多 agent provider 抽象。

不同 AI 编程工具(Claude Code / Codex 等)把会话存成不同格式、不同位置。
每个 provider 负责三件事:
  1. 会话文件在哪(scan_paths)
  2. 怎么从一个文件解析出统一信息(parse)
  3. 用什么命令 resume(resume_cmd)

其余逻辑(回收站/搜索/排序/收藏/导出/UI)全部作用在统一的 Session 上,与 provider 无关。
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path


def _env_dir(var: str, default: Path) -> Path:
    v = os.environ.get(var)
    return Path(v).expanduser() if v else default


# ---- 文本提取(各家 content 结构不同) ----
def _claude_text(content) -> str:
    if isinstance(content, list):
        return " ".join(
            x.get("text", "") for x in content
            if isinstance(x, dict) and x.get("type") == "text"
        )
    return content or ""


def _codex_text(content) -> str:
    if isinstance(content, list):
        parts = []
        for x in content:
            if isinstance(x, dict) and x.get("type") in ("input_text", "output_text", "text"):
                parts.append(x.get("text", ""))
        return " ".join(parts)
    return content or ""


def _is_real_user_text(txt: str) -> bool:
    """过滤系统注入,只留真实用户输入。"""
    txt = txt.strip()
    if not txt:
        return False
    if txt.startswith("<") or txt.startswith("Caveat:"):
        return False
    if "<command-" in txt or "<local-command" in txt:
        return False
    # Codex 的环境/权限/技能注入
    if txt.startswith("<environment_context") or txt.startswith("<permissions") \
            or txt.startswith("<collaboration_mode") or txt.startswith("<skills_instructions"):
        return False
    return True


# ---- 解析结果:一个中性的字典,core 据此构造 Session ----
def _parse_claude(path: str) -> dict:
    cwd = first = last_user = last_assistant = ""
    user_turns = assistant_turns = 0
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not cwd and d.get("cwd"):
                cwd = d["cwd"]
            t = d.get("type")
            if t == "user":
                txt = _claude_text(d.get("message", {}).get("content")).strip().replace("\n", " ")
                if _is_real_user_text(txt):
                    user_turns += 1
                    if not first:
                        first = txt
                    last_user = txt
            elif t == "assistant":
                txt = _claude_text(d.get("message", {}).get("content")).strip().replace("\n", " ")
                if txt:
                    assistant_turns += 1
                    last_assistant = txt
    return dict(cwd=cwd, first=first, last_user=last_user, last_assistant=last_assistant,
                user_turns=user_turns, assistant_turns=assistant_turns)


def _parse_codex(path: str) -> dict:
    cwd = first = last_user = last_assistant = ""
    user_turns = assistant_turns = 0
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = d.get("type")
            payload = d.get("payload", {})
            if t == "session_meta" and not cwd:
                cwd = payload.get("cwd", "")
            elif t == "turn_context" and not cwd:
                cwd = payload.get("cwd", "")
            elif t == "response_item" and payload.get("type") == "message":
                role = payload.get("role")
                txt = _codex_text(payload.get("content")).strip().replace("\n", " ")
                if role == "user":
                    if _is_real_user_text(txt):
                        user_turns += 1
                        if not first:
                            first = txt
                        last_user = txt
                elif role == "assistant":
                    if txt:
                        assistant_turns += 1
                        last_assistant = txt
    return dict(cwd=cwd, first=first, last_user=last_user, last_assistant=last_assistant,
                user_turns=user_turns, assistant_turns=assistant_turns)


def _transcript_claude(path: str, limit: int):
    msgs = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = d.get("type")
            if t not in ("user", "assistant"):
                continue
            txt = _claude_text(d.get("message", {}).get("content")).strip()
            if not txt or (t == "user" and not _is_real_user_text(txt)):
                continue
            msgs.append({"role": t, "text": txt, "ts": d.get("timestamp", "")})
            if len(msgs) >= limit:
                break
    return msgs


def _transcript_codex(path: str, limit: int):
    msgs = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "response_item":
                continue
            payload = d.get("payload", {})
            if payload.get("type") != "message":
                continue
            role = payload.get("role")
            if role not in ("user", "assistant"):
                continue
            txt = _codex_text(payload.get("content")).strip()
            if not txt or (role == "user" and not _is_real_user_text(txt)):
                continue
            msgs.append({"role": role, "text": txt, "ts": d.get("timestamp", "")})
            if len(msgs) >= limit:
                break
    return msgs


class Provider:
    """一个 AI 编程工具的会话适配器。"""

    def __init__(self, name, label, root_fn, scan_fn, parse_fn, transcript_fn, resume_fn, available_fn):
        self.name = name              # 内部标识,如 "claude"
        self.label = label            # 展示名,如 "Claude Code"
        self._root = root_fn
        self._scan = scan_fn
        self._parse = parse_fn
        self._transcript = transcript_fn
        self._resume = resume_fn
        self._available = available_fn

    def root(self) -> Path:
        return self._root()

    def available(self) -> bool:
        """该工具的数据目录是否存在(不存在就跳过,不报错)。"""
        return self._available()

    def scan(self) -> list:
        return self._scan() if self.available() else []

    def parse(self, path: str) -> dict:
        return self._parse(path)

    def transcript(self, path: str, limit: int = 500) -> list:
        return self._transcript(path, limit)

    def resume_cmd(self, cwd: str, session_id: str) -> list:
        """返回 resume 用的命令 argv 列表。"""
        return self._resume(cwd, session_id)


# ---- Claude Code ----
def _claude_root() -> Path:
    return _env_dir("CLAUDE_CONFIG_DIR", Path.home() / ".claude")


def _claude_scan() -> list:
    return glob.glob(os.path.join(str(_claude_root() / "projects"), "*", "*.jsonl"))


# ---- Codex ----
def _codex_root() -> Path:
    return _env_dir("CODEX_HOME", Path.home() / ".codex")


def _codex_scan() -> list:
    # ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
    return glob.glob(os.path.join(str(_codex_root() / "sessions"), "*", "*", "*", "rollout-*.jsonl"))


CLAUDE = Provider(
    name="claude", label="Claude Code",
    root_fn=_claude_root,
    scan_fn=_claude_scan,
    parse_fn=_parse_claude,
    transcript_fn=_transcript_claude,
    resume_fn=lambda cwd, sid: ["claude", "--resume", sid],
    available_fn=lambda: (_claude_root() / "projects").is_dir(),
)

CODEX = Provider(
    name="codex", label="Codex",
    root_fn=_codex_root,
    scan_fn=_codex_scan,
    parse_fn=_parse_codex,
    transcript_fn=_transcript_codex,
    resume_fn=lambda cwd, sid: ["codex", "resume", sid],
    available_fn=lambda: (_codex_root() / "sessions").is_dir(),
)

ALL = [CLAUDE, CODEX]


def get(name: str) -> Provider:
    for p in ALL:
        if p.name == name:
            return p
    return CLAUDE
