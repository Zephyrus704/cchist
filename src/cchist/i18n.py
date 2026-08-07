# SPDX-License-Identifier: MIT
"""轻量国际化(中/英)。

语言选择优先级:
  1. 环境变量 CCHIST_LANG(zh / en)
  2. 系统 locale(以 zh 开头 → 中文,否则英文)
  3. 默认英文(面向 GitHub 全球用户)

用法:from .i18n import t;  t("resume")  → 当前语言的文案。
"""
from __future__ import annotations

import locale
import os

STRINGS = {
    # key: (中文, English)
    "tagline": ("Claude Code / Codex 对话记录管理", "Browse & resume your Claude Code / Codex sessions"),
    "search_placeholder": (
        "🔍 关键词过滤(标题/首末句/目录)  ·  按 g 全文搜索  ·  按 s 切换排序",
        "🔍 Filter (title / first & last / path)  ·  g: full-text  ·  s: sort",
    ),
    # 列
    "col_time": ("时间", "Time"),
    "col_provider": ("来源", "Source"),
    "col_project": ("项目", "Project"),
    "col_turns": ("轮", "Turns"),
    "col_size": ("大小", "Size"),
    "col_path": ("路径", "Path"),
    # 动作
    "delete": ("删除", "Delete"),
    "export": ("导出", "Export"),
    "cleanup": ("批量清理", "Cleanup"),
    "favorite": ("收藏", "Favorite"),
    "trash": ("回收站", "Trash"),
    "restore": ("恢复", "Restore"),
    "fulltext": ("全文搜索", "Full-text"),
    "sort": ("排序", "Sort"),
    "empty_trash": ("清空回收站", "Empty trash"),
    "search": ("搜索", "Search"),
    "clear_search": ("清除搜索", "Clear"),
    "quit": ("退出", "Quit"),
    "open_resume": ("打开 / 恢复", "Open / Resume"),
    # 预览面板
    "pv_project_dir": ("项目目录", "Working directory"),
    "pv_session_id": ("会话 ID", "Session ID"),
    "pv_turns_size": ("轮数 / 大小 / 更新", "Turns / Size / Updated"),
    "pv_user": ("用户", "user"),
    "pv_assistant": ("助手", "assistant"),
    "pv_first_user": ("首句(用户)", "First (user)"),
    "pv_last_user": ("末句(用户)", "Last (user)"),
    "pv_last_assistant": ("末句(助手)", "Last (assistant)"),
    "badge_fav": ("★ 收藏", "★ Favorite"),
    "badge_empty": ("空对话", "Empty"),
    "badge_orphan": ("目录已删除", "Dir deleted"),
    "badge_trash": ("回收站", "Trashed"),
    # 空状态
    "empty_no_match": ("没有匹配的对话。", "No matching sessions."),
    "empty_hint_search": (
        "试试:\n· 清除搜索(Esc)\n· 按 g 开启全文搜索",
        "Try:\n· Clear search (Esc)\n· Press g for full-text search",
    ),
    "empty_trash_empty": ("回收站是空的。", "Trash is empty."),
    "empty_none_title": ("未找到任何对话记录。", "No sessions found."),
    "empty_scan_dirs": ("cchist 扫描的目录:", "cchist scans:"),
    "empty_reasons": (
        "可能原因:\n· 你还没用过 Claude Code / Codex\n· 配置目录不在默认位置,可设环境变量:",
        "Possible reasons:\n· You haven't used Claude Code / Codex yet\n· Config dir is not default; set env vars:",
    ),
    # 通知
    "exported_to": ("已导出 Markdown:", "Exported to Markdown:"),
    "no_cleanup": ("没有可清理的空/孤儿对话 ✓", "Nothing to clean up ✓"),
    "cleaned_n": ("已把 {n} 个对话移入回收站(可恢复)", "Moved {n} session(s) to trash (recoverable)"),
    "restored": ("已恢复", "Restored"),
    "moved_to_trash": ("已移入回收站(按 t 查看/恢复)", "Moved to trash (press t to view/restore)"),
    # 确认框
    "confirm_yes": ("y / Enter 确认        n / Esc 取消", "y / Enter: confirm     n / Esc: cancel"),
    "confirm_trash": ("移入回收站?", "Move to trash?"),
    "confirm_delete": ("彻底删除?此操作不可恢复!", "Delete permanently? This cannot be undone!"),
    "confirm_cleanup": (
        "批量清理?将把以下会话移入回收站(可恢复):",
        "Clean up? These sessions will be moved to trash (recoverable):",
    ),
    "confirm_empty_trash": ("清空回收站?所有文件将被彻底删除!", "Empty trash? All files permanently deleted!"),
    "n_empty": ("空对话 {n} 个", "{n} empty"),
    "n_orphan": ("孤儿会话(目录已删) {n} 个", "{n} orphaned (dir deleted)"),
    "n_total": ("共 {n} 个", "{n} total"),
}

_lang = None


def _detect() -> str:
    env = os.environ.get("CCHIST_LANG", "").lower()
    if env in ("zh", "cn", "zh_cn", "zh-cn"):
        return "zh"
    if env in ("en", "en_us", "en-us"):
        return "en"
    try:
        loc = locale.getlocale()[0] or ""
    except (ValueError, TypeError):
        loc = ""
    if not loc:
        loc = os.environ.get("LANG", "") or os.environ.get("LC_ALL", "")
    return "zh" if loc.lower().startswith("zh") else "en"


def lang() -> str:
    global _lang
    if _lang is None:
        _lang = _detect()
    return _lang


def set_lang(code: str):
    global _lang
    _lang = "zh" if code == "zh" else "en"


def t(key: str, **kw) -> str:
    pair = STRINGS.get(key)
    if not pair:
        return key
    s = pair[0] if lang() == "zh" else pair[1]
    return s.format(**kw) if kw else s
