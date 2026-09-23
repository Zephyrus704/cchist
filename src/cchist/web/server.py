# SPDX-License-Identifier: MIT
"""FastAPI 后端。复用 core 数据层,提供 REST API 与静态前端。

设计:Web 端不做终端式无缝 resume(浏览器进程与终端隔离),而是:
- 完整展示对话正文(终端里看不方便的长对话,网页更适合阅读)
- 一键复制 resume 命令
- 统计概览(项目分布、活跃度),这是终端不方便做的可视化
"""
from __future__ import annotations

import os
import threading
import webbrowser
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
except ImportError as e:  # 友好提示
    raise SystemExit(
        "缺少 Web 依赖。请安装:pip install 'cchist[web]'  或  pip install fastapi uvicorn"
    ) from e

from .. import config, core

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="cchist", docs_url="/api/docs")


def _sessions_payload(include_trash: bool = False):
    return [s.to_dict() for s in core.scan_sessions(include_trash=include_trash)]


@app.get("/api/sessions")
def api_sessions(q: str = "", fulltext: bool = False, sort: str = "time",
                 reverse: bool = True, trash: bool = False,
                 favorites_only: bool = False):
    if trash:
        sessions = core.scan_trash()
    else:
        sessions = core.filter_ignored(core.scan_sessions(include_trash=False))
    if q:
        if fulltext:
            sessions = [s for s in sessions if core.full_text_search(q, s)]
        else:
            sessions = [s for s in sessions if core.matches(s, q)]
    favs = core.load_favorites()
    if favorites_only and not trash:
        sessions = [s for s in sessions if s.session_id in favs]
    sessions = core.sort_sessions(sessions, sort, reverse)
    out = []
    for s in sessions:
        d = s.to_dict()
        d["favorite"] = s.session_id in favs
        out.append(d)
    return {"sessions": out, "count": len(out)}


@app.get("/api/lang")
def api_lang():
    """当前语言与 Web 端所需文案(供前端 i18n)。"""
    from .. import i18n
    lang = i18n.lang()
    zh = lang == "zh"
    return {
        "lang": lang,
        "strings": {
            "tagline": "Claude Code / Codex 对话记录管理" if zh else "Browse & resume your Claude Code / Codex sessions",
            "search": "搜索标题 / 路径 / 首末句…" if zh else "Search title / path / first & last…",
            "fulltext": "全文搜索" if zh else "Full-text",
            "sort_time": "按时间" if zh else "By time",
            "sort_project": "按项目" if zh else "By project",
            "sort_turns": "按轮数" if zh else "By turns",
            "sort_size": "按大小" if zh else "By size",
            "stats": "📊 统计" if zh else "📊 Stats",
            "cleanup": "🧹 清理" if zh else "🧹 Clean up",
            "shutdown": "⏻ 停止服务器" if zh else "⏻ Stop server",
            "trash": "🗑 回收站" if zh else "🗑 Trash",
            "back": "← 返回列表" if zh else "← Back",
            "total": "对话" if zh else "sessions",
            "projects": "项目" if zh else "projects",
            "used": "占用" if zh else "size",
            "no_match": "没有匹配的对话" if zh else "No matching sessions",
            "no_sessions": "未找到任何对话记录" if zh else "No sessions found",
            "empty_hint": ("清空搜索框，或勾选「全文搜索」再试。" if zh
                           else "Clear the search box, or enable full-text search."),
            "trash_empty": "回收站是空的" if zh else "Trash is empty",
            "export": "⬇ 导出 Markdown" if zh else "⬇ Export Markdown",
            "restore": "恢复" if zh else "Restore",
            "delete_perm": "彻底删除" if zh else "Delete permanently",
            "to_trash": "移入回收站" if zh else "Move to trash",
            "fav": "☆ 收藏" if zh else "☆ Favorite",
            "faved": "★ 已收藏" if zh else "★ Favorited",
            "copy": "复制" if zh else "Copy",
            "copied": "已复制" if zh else "Copied",
            "me": "我" if zh else "Me",
            "confirm_trash": ("移入回收站?可在回收站恢复。" if zh
                              else "Move to trash? Recoverable from trash."),
            "confirm_cleanup": ("把所有空对话和孤儿会话(目录已删)移入回收站?可恢复。" if zh
                                else "Move all empty & orphaned sessions to trash? Recoverable."),
            "confirm_delete": "彻底删除?不可恢复!" if zh else "Delete permanently? Cannot be undone!",
            "confirm_shutdown": ("停止 cchist Web 服务器?停止后此页面将失效。" if zh
                                 else "Stop the cchist web server? This page will stop working."),
            "stopped": "✓ cchist Web 已停止" if zh else "✓ cchist web stopped",
            "can_close": "可以关闭此标签页了" if zh else "You can close this tab now",
            "stats_title": "统计概览" if zh else "Overview",
            "daily_title": "每日对话量" if zh else "Sessions per day",
            "proj_title": "项目分布(Top 12)" if zh else "By project (Top 12)",
            "overview": "概览" if zh else "Summary",
            "empty_count": "空对话" if zh else "Empty",
            "orphan_count": "孤儿会话" if zh else "Orphaned",
            "select_hint": "选择左侧对话查看详情" if zh else "Select a session to view details",
            "favorites_only": "只看收藏" if zh else "Favorites only",
            "fav_on": "只看收藏:开" if zh else "Favorites: ON",
            "fav_off": "只看收藏:关" if zh else "Favorites: OFF",
            "no_favorites": "还没有收藏任何对话" if zh else "No favorites yet",
            "manage_ignored": "管理忽略的文件夹" if zh else "Manage ignored folders",
            "ignored_title": "被忽略的文件夹" if zh else "Ignored folders",
            "ignored_empty": "还没有忽略任何文件夹" if zh else "No ignored folders yet",
            "ignored_added": "已忽略" if zh else "Ignored",
            "ignored_removed": "已取消忽略" if zh else "Un-ignored",
            "confirm_ignore": ("忽略此文件夹?其下所有对话将被隐藏(不删除,可恢复)。" if zh
                               else "Ignore this folder? Sessions inside will be hidden (not deleted; recoverable)."),
        },
    }


@app.get("/api/stats")
def api_stats():
    """概览统计:总数、总大小、按项目分布、空对话/孤儿数。"""
    sessions = core.scan_sessions(include_trash=False)
    by_project: dict[str, int] = {}
    total_size = 0
    trivial = orphan = 0
    for s in sessions:
        by_project[s.project_label] = by_project.get(s.project_label, 0) + 1
        total_size += s.size
        if s.is_trivial:
            trivial += 1
        if s.is_orphan:
            orphan += 1
    projects = sorted(by_project.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "total": len(sessions),
        "total_size": total_size,
        "trivial": trivial,
        "orphan": orphan,
        "trash": len(core.scan_trash()),
        "projects": [{"name": n, "count": c} for n, c in projects],
    }


@app.get("/api/session/{session_id}")
def api_session_detail(session_id: str, trash: bool = False):
    s = core.find_session(session_id, include_trash=True)
    if not s:
        raise HTTPException(404, "会话不存在")
    d = s.to_dict()
    d["messages"] = core.read_transcript(s)
    d["favorite"] = session_id in core.load_favorites()
    # resume 命令(供网页复制),按 provider 生成
    target = s.cwd if s.cwd_exists else "~"
    from .. import providers
    argv = providers.get(s.provider).resume_cmd(target, session_id)
    d["resume_cmd"] = f'cd "{target}" && ' + " ".join(argv)
    return d


@app.post("/api/session/{session_id}/favorite")
def api_favorite(session_id: str):
    now = core.toggle_favorite(session_id)
    return {"favorite": now}


@app.post("/api/session/{session_id}/trash")
def api_trash(session_id: str):
    s = core.find_session(session_id, include_trash=False)
    if not s:
        raise HTTPException(404, "会话不存在")
    try:
        core.move_to_trash(s)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    return {"ok": True}


@app.post("/api/session/{session_id}/restore")
def api_restore(session_id: str):
    for s in core.scan_trash():
        if s.session_id == session_id:
            try:
                core.restore_from_trash(s)
            except RuntimeError as e:
                raise HTTPException(500, str(e))
            return {"ok": True}
    raise HTTPException(404, "回收站中无此会话")


@app.delete("/api/session/{session_id}")
def api_delete(session_id: str):
    for s in core.scan_trash():
        if s.session_id == session_id:
            try:
                core.delete_permanently(s)
            except RuntimeError as e:
                raise HTTPException(500, str(e))
            return {"ok": True}
    raise HTTPException(404, "回收站中无此会话")


@app.get("/api/session/{session_id}/export")
def api_export(session_id: str):
    """导出会话为 Markdown,直接作为下载返回。"""
    s = core.find_session(session_id, include_trash=True)
    if not s:
        raise HTTPException(404, "会话不存在")
    md = core.export_markdown(s)
    fname = f"{s.project_label}_{s.session_id[:8]}.md"
    return PlainTextResponse(
        md,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        media_type="text/markdown; charset=utf-8",
    )


@app.get("/api/daily")
def api_daily():
    """每日对话量,用于趋势图。"""
    return {"daily": core.daily_counts()}


@app.post("/api/cleanup")
def api_cleanup():
    """批量把空对话+孤儿会话移入回收站。"""
    targets = core.cleanup_targets()
    ok, errors = core.batch_move_to_trash(targets)
    return {"cleaned": ok, "errors": len(errors)}


@app.get("/api/ignored")
def api_ignored_list():
    """返回已忽略的文件夹列表。"""
    return {"dirs": core.load_ignored()}


@app.post("/api/ignored")
def api_ignored_add(path: str):
    """把一个文件夹加入忽略列表。"""
    import os
    p = os.path.normpath(os.path.expanduser(path))
    dirs = core.add_ignored(p)
    return {"dirs": dirs, "added": p}


@app.delete("/api/ignored/{path:path}")
def api_ignored_remove(path: str):
    """从忽略列表移除一个文件夹(会话重新可见)。"""
    dirs = core.remove_ignored(path)
    return {"dirs": dirs, "removed": path}


@app.post("/api/shutdown")
def api_shutdown():
    """从网页停止服务器(优雅退出)。"""
    def _stop():
        # 稍等让响应先返回,再退出进程
        import time
        time.sleep(0.3)
        os._exit(0)
    threading.Thread(target=_stop, daemon=True).start()
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def run_web(host: str = "127.0.0.1", port: int = 8770, open_browser: bool = True) -> int:
    url = f"http://{host}:{port}"
    print("=" * 46, flush=True)
    print(f"  cchist Web 已启动 → {url}", flush=True)
    print("  停止方式:回到本终端按 Ctrl+C", flush=True)
    print("           或点网页右上角「停止服务器」", flush=True)
    print("=" * 46, flush=True)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    except KeyboardInterrupt:
        print("\ncchist Web 已停止。")
    return 0
