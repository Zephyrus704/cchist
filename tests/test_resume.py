# SPDX-License-Identifier: MIT
"""resume 模块测试:信号文件 + 新终端打开。"""
import shutil
import subprocess

from cchist import resume


# ---- 信号文件 ----
def test_signal_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    resume.clear_signal()
    assert resume.consume_signal() is None
    resume.write_signal("/home/u/proj", "sid-1", "codex")
    assert resume.consume_signal() == ("/home/u/proj", "sid-1", "codex")
    # 消费后即清除
    assert resume.consume_signal() is None


def test_signal_default_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    sig = resume.signal_file()
    with open(sig, "w", encoding="utf-8") as f:
        f.write("/home/u/proj\nsid-2\n")  # 旧格式:无 provider 行
    assert resume.consume_signal() == ("/home/u/proj", "sid-2", "claude")


# ---- 终端探测 ----
def test_detect_terminal_prefers_env(monkeypatch):
    monkeypatch.setenv("TERMINAL", "my-term")
    monkeypatch.setattr(shutil, "which", lambda c: f"/usr/bin/{c}" if c == "my-term" else None)
    assert resume.detect_terminal() == "/usr/bin/my-term"


def test_detect_terminal_fallback(monkeypatch):
    monkeypatch.delenv("TERMINAL", raising=False)
    monkeypatch.setattr(shutil, "which",
                        lambda c: "/usr/bin/gnome-terminal" if c == "gnome-terminal" else None)
    assert resume.detect_terminal() == "/usr/bin/gnome-terminal"


def test_detect_terminal_none(monkeypatch):
    monkeypatch.delenv("TERMINAL", raising=False)
    monkeypatch.setattr(shutil, "which", lambda c: None)
    assert resume.detect_terminal() is None


# ---- 各终端参数形式 ----
def test_terminal_argv_gnome():
    argv = resume._terminal_argv("/usr/bin/gnome-terminal", "echo hi")
    assert argv == ["/usr/bin/gnome-terminal", "--", "bash", "-c", "echo hi"]


def test_terminal_argv_xfce4():
    argv = resume._terminal_argv("/usr/bin/xfce4-terminal", "echo hi")
    assert argv[1] == "-x"


def test_terminal_argv_generic():
    argv = resume._terminal_argv("/usr/bin/xterm", "echo hi")
    assert argv == ["/usr/bin/xterm", "-e", "bash", "-c", "echo hi"]


# ---- 新终端打开 ----
def _fake_popen(calls):
    class FakePopen:
        def __init__(self, argv, **kw):
            calls["argv"] = argv
            calls["kw"] = kw
    return FakePopen


def test_open_in_new_terminal_ok(monkeypatch, tmp_path):
    calls = {}
    monkeypatch.setenv("TERMINAL", "gnome-terminal")
    monkeypatch.setattr(shutil, "which", lambda c: f"/usr/bin/{c}")
    monkeypatch.setattr(subprocess, "Popen", _fake_popen(calls))

    ok, msg = resume.open_in_new_terminal(str(tmp_path), "sid-123", "claude")
    assert ok, msg
    argv = calls["argv"]
    assert argv[:4] == ["/usr/bin/gnome-terminal", "--", "bash", "-c"]
    inner = argv[4]
    assert str(tmp_path) in inner
    assert "claude" in inner and "--resume" in inner and "sid-123" in inner
    assert calls["kw"]["start_new_session"] is True


def test_open_in_new_terminal_codex_cmd(monkeypatch, tmp_path):
    calls = {}
    monkeypatch.setenv("TERMINAL", "xterm")
    monkeypatch.setattr(shutil, "which", lambda c: f"/usr/bin/{c}")
    monkeypatch.setattr(subprocess, "Popen", _fake_popen(calls))

    ok, _ = resume.open_in_new_terminal(str(tmp_path), "sid-9", "codex")
    assert ok
    inner = calls["argv"][-1]
    assert "codex resume sid-9" in inner


def test_open_in_new_terminal_missing_tool(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda c: None)
    ok, msg = resume.open_in_new_terminal(str(tmp_path), "sid", "claude")
    assert not ok
    assert "claude" in msg


def test_open_in_new_terminal_no_terminal(monkeypatch, tmp_path):
    monkeypatch.delenv("TERMINAL", raising=False)
    monkeypatch.setattr(shutil, "which",
                        lambda c: "/usr/bin/claude" if c == "claude" else None)
    ok, msg = resume.open_in_new_terminal(str(tmp_path), "sid", "claude")
    assert not ok
    assert "TERMINAL" in msg


def test_open_in_new_terminal_orphan_dir_falls_home(monkeypatch):
    calls = {}
    monkeypatch.setenv("TERMINAL", "xterm")
    monkeypatch.setattr(shutil, "which", lambda c: f"/usr/bin/{c}")
    monkeypatch.setattr(subprocess, "Popen", _fake_popen(calls))

    ok, _ = resume.open_in_new_terminal("/nonexistent/dir-xyz", "sid", "claude")
    assert ok
    inner = calls["argv"][-1]
    assert "/nonexistent/dir-xyz" not in inner
