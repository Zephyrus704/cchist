"""pytest 夹具:构造一个隔离的假 CLAUDE_CONFIG_DIR,含若干会话文件。"""
import json
import os

import pytest


def _write_session(projects_dir, project, session_id, cwd, messages):
    """写一个 jsonl 会话文件。messages: [(type, text)]。"""
    d = projects_dir / project
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{session_id}.jsonl"
    lines = []
    for i, (typ, text) in enumerate(messages):
        rec = {"type": typ, "cwd": cwd,
               "message": {"content": text}, "timestamp": f"2026-08-06T0{i}:00:00Z"}
        lines.append(json.dumps(rec, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """构造隔离的 ~/.claude,并把 Codex 指向空目录,重置解析缓存。"""
    claude = tmp_path / ".claude"
    projects = claude / "projects"
    projects.mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude))
    # 隔离 Codex:指向一个不存在会话的临时目录,避免扫到真实机器上的 Codex 会话
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex-empty"))

    from cchist import core
    core._parse_cache.clear()

    # 正常对话
    _write_session(projects, "-home-u-proj-a", "aaaa1111-0000-0000-0000-000000000001",
                   str(tmp_path / "proj-a"),
                   [("user", "如何实现快速排序"), ("assistant", "可以用分治..."),
                    ("user", "谢谢"), ("assistant", "不客气")])
    (tmp_path / "proj-a").mkdir()

    # 空对话(只有 assistant,无 user)
    _write_session(projects, "-home-u-proj-b", "bbbb2222-0000-0000-0000-000000000002",
                   str(tmp_path / "proj-b"),
                   [("assistant", "系统消息")])
    (tmp_path / "proj-b").mkdir()

    # 孤儿对话(cwd 不存在)
    _write_session(projects, "-home-u-gone", "cccc3333-0000-0000-0000-000000000003",
                   str(tmp_path / "deleted-dir"),
                   [("user", "关于 PCIE 调试"), ("assistant", "检查链路...")])

    return {"claude": claude, "projects": projects, "tmp": tmp_path}


def _write_codex_session(sessions_dir, session_id, cwd, records):
    """写一个 Codex rollout jsonl。records: [(role, text)],role=user/assistant/developer。"""
    day = sessions_dir / "2026" / "08" / "06"
    day.mkdir(parents=True, exist_ok=True)
    path = day / f"rollout-2026-08-06T10-00-00-{session_id}.jsonl"
    lines = [json.dumps({"timestamp": "2026-08-06T10:00:00Z", "type": "session_meta",
                         "payload": {"session_id": session_id, "cwd": cwd}}, ensure_ascii=False)]
    for role, text in records:
        lines.append(json.dumps({
            "timestamp": "2026-08-06T10:00:01Z", "type": "response_item",
            "payload": {"type": "message", "role": role,
                        "content": [{"type": "input_text" if role != "assistant" else "output_text", "text": text}]},
        }, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    """构造隔离的 ~/.codex,并把 Claude 指向空目录。"""
    codex = tmp_path / ".codex"
    sessions = codex / "sessions"
    sessions.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude-empty"))

    from cchist import core
    core._parse_cache.clear()

    _write_codex_session(sessions, "019fd096-cbef-73a3-a24a-000000000001",
                         str(tmp_path / "proj-x"),
                         [("developer", "系统指令"), ("user", "how to sort in python"),
                          ("assistant", "use sorted()"), ("user", "thanks")])
    (tmp_path / "proj-x").mkdir()

    return {"codex": codex, "sessions": sessions, "tmp": tmp_path}
