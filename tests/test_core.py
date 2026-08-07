# SPDX-License-Identifier: MIT
"""core 数据层测试。"""
from cchist import core, config


def test_config_respects_env(fake_claude):
    assert config.claude_dir() == fake_claude["claude"]
    assert config.projects_dir() == fake_claude["projects"]


def test_scan_finds_all(fake_claude):
    sessions = core.scan_sessions()
    assert len(sessions) == 3


def test_parse_fields(fake_claude):
    s = next(x for x in core.scan_sessions() if x.session_id.startswith("aaaa"))
    assert s.first_msg == "如何实现快速排序"
    assert s.last_user_msg == "谢谢"
    assert s.user_turns == 2
    assert s.assistant_turns == 2
    assert s.total_turns == 4


def test_trivial_detection(fake_claude):
    sessions = {s.session_id[:4]: s for s in core.scan_sessions()}
    assert sessions["bbbb"].is_trivial      # 无用户消息
    assert not sessions["aaaa"].is_trivial   # 正常对话


def test_orphan_detection(fake_claude):
    sessions = {s.session_id[:4]: s for s in core.scan_sessions()}
    assert sessions["cccc"].is_orphan        # cwd 已删
    assert not sessions["aaaa"].is_orphan


def test_search_match(fake_claude):
    sessions = core.scan_sessions()
    hit = [s for s in sessions if core.matches(s, "快速排序")]
    assert len(hit) == 1


def test_fulltext_search(fake_claude):
    sessions = core.scan_sessions()
    # "分治" 只出现在 aaaa 会话的 assistant 正文里,轻量搜索搜不到,全文能搜到
    hit = [s for s in sessions if core.full_text_search("分治", s)]
    assert len(hit) == 1
    assert hit[0].session_id.startswith("aaaa")


def test_sort_by_project(fake_claude):
    sessions = core.sort_sessions(core.scan_sessions(), "project", reverse=False)
    labels = [s.project_label for s in sessions]
    assert labels == sorted(labels)


def test_favorite_toggle(fake_claude):
    sid = "aaaa1111-0000-0000-0000-000000000001"
    assert core.toggle_favorite(sid) is True
    assert sid in core.load_favorites()
    assert core.toggle_favorite(sid) is False
    assert sid not in core.load_favorites()


def test_trash_roundtrip(fake_claude):
    s = next(x for x in core.scan_sessions() if x.session_id.startswith("aaaa"))
    orig_path = s.path
    core.move_to_trash(s)
    assert len(core.scan_sessions()) == 2
    assert len(core.scan_trash()) == 1
    # 恢复
    ts = core.scan_trash()[0]
    restored = core.restore_from_trash(ts)
    assert restored == orig_path
    assert len(core.scan_sessions()) == 3
    assert len(core.scan_trash()) == 0


def test_permanent_delete(fake_claude):
    s = next(x for x in core.scan_sessions() if x.session_id.startswith("bbbb"))
    core.move_to_trash(s)
    ts = core.scan_trash()[0]
    core.delete_permanently(ts)
    assert len(core.scan_trash()) == 0
    assert len(core.scan_sessions()) == 2


def test_read_transcript(fake_claude):
    s = next(x for x in core.scan_sessions() if x.session_id.startswith("aaaa"))
    msgs = core.read_transcript(s)
    assert len(msgs) == 4
    assert msgs[0]["role"] == "user"
    assert msgs[0]["text"] == "如何实现快速排序"


def test_to_dict_serializable(fake_claude):
    import json
    s = core.scan_sessions()[0]
    json.dumps(s.to_dict(), ensure_ascii=False)  # 不抛异常即通过


def test_export_markdown(fake_claude):
    from cchist import core
    s = next(x for x in core.scan_sessions() if x.session_id.startswith("aaaa"))
    md = core.export_markdown(s)
    assert "如何实现快速排序" in md
    assert "🤖 Claude" in md and "🧑 用户" in md


def test_export_to_file(fake_claude, tmp_path):
    from cchist import core
    s = next(x for x in core.scan_sessions() if x.session_id.startswith("aaaa"))
    dest = tmp_path / "exports"
    path = core.export_to_file(s, str(dest))
    import os
    assert os.path.exists(path) and path.endswith(".md")


def test_cleanup_targets(fake_claude):
    from cchist import core
    targets = core.cleanup_targets()
    # bbbb(空) + cccc(孤儿) 应被选中,aaaa(正常)不选
    ids = {t.session_id[:4] for t in targets}
    assert "bbbb" in ids and "cccc" in ids and "aaaa" not in ids


def test_batch_move_to_trash(fake_claude):
    from cchist import core
    targets = core.cleanup_targets()
    n = len(targets)
    ok, errors = core.batch_move_to_trash(targets)
    assert ok == n and not errors
    assert len(core.scan_trash()) == n


def test_daily_counts(fake_claude):
    from cchist import core
    daily = core.daily_counts()
    assert isinstance(daily, list)
    assert all("date" in d and "count" in d for d in daily)


def test_codex_provider_scan(fake_codex):
    from cchist import core
    sessions = core.scan_sessions()
    assert len(sessions) == 1
    s = sessions[0]
    assert s.provider == "codex"
    assert s.provider_label == "Codex"


def test_codex_parsing(fake_codex):
    from cchist import core
    s = core.scan_sessions()[0]
    assert s.first_msg == "how to sort in python"   # developer 注入被过滤
    assert s.last_user_msg == "thanks"
    assert s.user_turns == 2
    assert s.assistant_turns == 1
    assert s.session_id == "019fd096-cbef-73a3-a24a-000000000001"


def test_codex_resume_cmd(fake_codex):
    from cchist import core, providers
    s = core.scan_sessions()[0]
    argv = providers.get(s.provider).resume_cmd(s.cwd, s.session_id)
    assert argv == ["codex", "resume", s.session_id]


def test_codex_transcript(fake_codex):
    from cchist import core
    s = core.scan_sessions()[0]
    msgs = core.read_transcript(s)
    # developer 消息应被过滤,只剩 user*2 + assistant*1
    assert len(msgs) == 3
    assert msgs[0]["text"] == "how to sort in python"


def test_codex_trash_roundtrip(fake_codex):
    from cchist import core
    s = core.scan_sessions()[0]
    core.move_to_trash(s)
    assert len(core.scan_sessions()) == 0
    assert len(core.scan_trash()) == 1
    ts = core.scan_trash()[0]
    assert ts.provider == "codex"   # 回收站保留了 provider
    core.restore_from_trash(ts)
    assert len(core.scan_sessions()) == 1
