# SPDX-License-Identifier: MIT
"""cchist TUI:浏览/搜索/预览/resume/删除 Claude Code 对话记录。"""
from __future__ import annotations

import os

from textual.app import App, ComposeResult, SystemCommand
from textual.command import CommandPalette
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Header, Input, Static
from textual.screen import ModalScreen, Screen
from rich.text import Text

from . import config, core, resume
from .i18n import t, lang


class ConfirmScreen(ModalScreen):
    """通用确认弹窗。y 或 enter 确认,n / Esc 取消。"""

    def __init__(self, message: str, on_confirm):
        super().__init__()
        self.message = message
        self.on_confirm = on_confirm

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(self.message, id="confirm-msg"),
            Static("[bold green]y / Enter[/bold green] 确认        [bold]n / Esc[/bold] 取消", id="confirm-hint"),
            id="confirm-box",
        )

    def on_key(self, event):
        # 在模态里独占按键,吞掉事件避免冒泡到全局快捷键
        event.stop()
        event.prevent_default()
        if event.key in ("y", "enter"):
            self.dismiss(True)
            self.on_confirm()
        elif event.key in ("n", "escape"):
            self.dismiss(False)


class PreviewPanel(Static):
    """右侧预览面板。"""

    def show(self, s: core.Session | None):
        if s is None:
            self.update("")
            return
        favs = core.load_favorites()
        t = Text()
        badges = []
        if s.session_id in favs:
            badges.append(("★ 收藏", "yellow"))
        if s.is_trivial:
            badges.append(("空对话", "yellow"))
        if s.is_orphan:
            badges.append(("目录已删除", "red"))
        if s.in_trash:
            badges.append(("回收站", "red"))
        for i, (b, st) in enumerate(badges):
            if i:
                t.append("  ")
            t.append(f" {b} ", style=f"reverse {st}")
        if badges:
            t.append("\n\n")

        t.append("项目目录\n", style="bold cyan")
        t.append(f"{s.cwd or '(未知)'}\n\n")
        t.append("会话 ID\n", style="bold cyan")
        t.append(f"{s.session_id}\n\n")
        t.append("轮数 / 大小 / 更新\n", style="bold cyan")
        t.append(f"用户 {s.user_turns} · 助手 {s.assistant_turns} · {s.size_str} · {s.mtime_str}\n\n")
        t.append("首句(用户)\n", style="bold green")
        t.append(f"{s.first_msg[:300]}\n\n")
        if s.last_user_msg and s.last_user_msg != s.first_msg:
            t.append("末句(用户)\n", style="bold green")
            t.append(f"{s.last_user_msg[:300]}\n\n")
        if s.last_assistant_msg:
            t.append("末句(助手)\n", style="bold magenta")
            t.append(f"{s.last_assistant_msg[:300]}\n")
        self.update(t)


class CChistApp(App):
    CSS = """
    Screen { layout: vertical; }
    #main { height: 1fr; }
    #left { width: 3fr; min-width: 30; }
    #right { width: 2fr; min-width: 24; border-left: solid $primary; padding: 0 1; }
    DataTable { height: 1fr; }
    Input { dock: top; }
    #confirm-box {
        width: 64; height: auto; padding: 1 2;
        border: thick $warning; background: $surface;
    }
    #confirm-msg { height: auto; margin-bottom: 1; }
    #confirm-hint { height: auto; }
    #status { dock: bottom; height: 1; background: $panel; color: $text-muted; padding: 0 1; }
    """

    # 注意:resume 不再用 priority 绑定,改由行选中(enter/双击)触发,避免抢占模态弹窗的 enter
    BINDINGS = [
        Binding("o", "open_terminal", "新终端打开"),
        Binding("d", "delete", "删除"),
        Binding("e", "export", "导出"),
        Binding("c", "cleanup", "批量清理"),
        Binding("f", "favorite", "收藏"),
        Binding("t", "toggle_trash", "回收站"),
        Binding("r", "restore", "恢复"),
        Binding("g", "full_text", "全文搜索"),
        Binding("s", "cycle_sort", "排序"),
        Binding("ctrl+d", "empty_trash", "清空回收站"),
        Binding("/", "focus_search", "搜索"),
        Binding("escape", "clear_search", "清除搜索"),
        Binding("q", "quit", "退出"),
    ]

    view_trash = reactive(False)
    query = reactive("")
    fulltext_mode = reactive(False)

    # 排序状态
    COLUMN_SORT = {1: "time", 2: "provider", 3: "project", 4: "turns", 5: "size"}  # 列索引 -> 排序键

    def __init__(self):
        super().__init__()
        self.all_sessions: list[core.Session] = []
        self.filtered: list[core.Session] = []
        self.sort_key = "time"
        self.sort_reverse = True

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder=t("search_placeholder"), id="search")
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
            preview = PreviewPanel(id="right")
            preview.border_title = "预览" if lang() == "zh" else "Preview"
            yield preview
        yield Static("", id="status")
        yield Footer()

    def on_mount(self):
        table = self.query_one("#table", DataTable)
        table.add_column("", key="mark", width=2)
        table.add_column(t("col_time") + " ▼", key="time", width=11)
        table.add_column(t("col_provider"), key="provider", width=7)
        table.add_column(t("col_project"), key="project", width=16)
        table.add_column(t("col_turns"), key="turns", width=7)
        table.add_column(t("col_size"), key="size", width=6)
        table.add_column(t("col_path"), key="path")
        self.reload()
        table.focus()

    # ---- 数据 ----
    def reload(self):
        if self.view_trash:
            self.all_sessions = core.scan_trash()
        else:
            self.all_sessions = core.scan_sessions(include_trash=False)
        self.apply_filter()

    def apply_filter(self):
        q = self.query.strip()
        if not q:
            base = list(self.all_sessions)
        elif self.fulltext_mode:
            base = [s for s in self.all_sessions if core.full_text_search(q, s)]
        else:
            base = [s for s in self.all_sessions if core.matches(s, q)]
        self.filtered = core.sort_sessions(base, self.sort_key, self.sort_reverse)
        self.refresh_table()

    def _update_headers(self):
        """在表头显示当前排序列和方向箭头。"""
        table = self.query_one("#table", DataTable)
        arrow = "▼" if self.sort_reverse else "▲"
        labels = {"time": t("col_time"), "provider": t("col_provider"),
                  "project": t("col_project"), "turns": t("col_turns"), "size": t("col_size")}
        for col_key, name in labels.items():
            col = table.columns.get(col_key)
            if col is not None:
                col.label = Text(f"{name} {arrow}" if col_key == self.sort_key else name)

    def refresh_table(self):
        table = self.query_one("#table", DataTable)
        saved = table.cursor_row
        table.clear()
        favs = core.load_favorites()
        home = os.path.expanduser("~")
        for s in self.filtered:
            if s.session_id in favs:
                mark = Text("★", style="yellow")
            elif s.is_trivial:
                mark = Text("🗑", style="yellow")
            elif s.is_orphan:
                mark = Text("⚠", style="red")
            else:
                mark = Text(" ")
            turns = Text(f"{s.user_turns}/{s.assistant_turns}", style="cyan")
            # 路径:家目录缩写为 ~,孤儿(目录已删)用红色标出
            path = s.cwd or "(未知)"
            if path.startswith(home):
                path = "~" + path[len(home):]
            if s.is_orphan:
                path_cell = Text(path, style="red")
            else:
                dim = "dim" if (s.is_trivial and not self.view_trash) else ""
                path_cell = Text(path, style=dim)
            style = "dim" if (s.is_trivial and not self.view_trash) else ""
            prov_color = {"claude": "#d97757", "codex": "#10a37f"}.get(s.provider, "white")
            table.add_row(
                mark,
                Text(s.mtime_str, style=style),
                Text(s.provider_label, style=style or prov_color),
                Text(s.project_label[:16], style=style or "green"),
                turns,
                Text(s.size_str, style=style),
                path_cell,
            )
        self._update_headers()
        if self.filtered:
            row = min(saved if saved is not None else 0, len(self.filtered) - 1)
            table.move_cursor(row=max(0, row))
        self.update_status()
        self.update_preview()

    def update_status(self):
        status = self.query_one("#status", Static)
        mode = "🗑 回收站" if self.view_trash else "会话列表"
        ft = " · 全文搜索" if self.fulltext_mode else ""
        sort_name = {"time": "时间", "provider": "来源", "project": "项目", "turns": "轮数", "size": "大小"}[self.sort_key]
        arrow = "↓" if self.sort_reverse else "↑"
        n = len(self.filtered)
        total = len(self.all_sessions)
        if self.view_trash:
            extra = "enter=恢复  ctrl+d=清空"
        else:
            extra = f"回收站 {len(core.scan_trash())} 项"
        filt = f"  过滤 {n}/{total}" if self.query else f"  共 {total}"
        status.update(f" {mode}{ft}{filt}  ·  排序:{sort_name}{arrow}  ·  {extra}")

    def current_session(self) -> core.Session | None:
        table = self.query_one("#table", DataTable)
        row = table.cursor_row
        if row is None or row < 0 or row >= len(self.filtered):
            return None
        return self.filtered[row]

    def update_preview(self):
        panel = self.query_one("#right", PreviewPanel)
        if not self.filtered:
            # 空列表友好提示
            if self.query:
                panel.update(Text("没有匹配的对话。\n\n试试:\n· 清除搜索(Esc)\n· 按 g 开启全文搜索", style="dim"))
            elif self.view_trash:
                panel.update(Text("回收站是空的。", style="dim"))
            else:
                t = Text()
                t.append("未找到任何对话记录。\n\n", style="bold yellow")
                t.append("cchist 读取的目录:\n", style="bold")
                t.append(f"{config.projects_dir()}\n\n")
                t.append("可能原因:\n", style="bold")
                t.append("· 你还没用过 Claude Code(用过才会有记录)\n")
                t.append("· 配置目录不在默认位置——可设环境变量:\n")
                t.append("  export CLAUDE_CONFIG_DIR=/你的/.claude\n", style="cyan")
                panel.update(t)
            return
        panel.show(self.current_session())

    # ---- 命令面板(全中文,不调 super 以去掉英文默认项) ----
    def get_system_commands(self, screen: Screen):
        # 排序不放进来——直接点表头即可,避免冗余
        yield SystemCommand("切换全文搜索", "在整段对话正文里查关键词", self.action_full_text)
        yield SystemCommand("打开 / 恢复选中项", "进入对话,或从回收站恢复(等同回车)", self.action_resume)
        yield SystemCommand("新终端打开选中项", "弹独立终端窗口 resume,cchist 列表保持打开", self.action_open_terminal)
        yield SystemCommand("导出选中对话", "导出为 Markdown 到 ~/cchist-exports/", self.action_export)
        yield SystemCommand("删除选中项", "移入回收站,可恢复", self.action_delete)
        yield SystemCommand("批量清理空/孤儿对话", "一次把所有空对话和孤儿会话移入回收站", self.action_cleanup)
        yield SystemCommand("收藏 / 取消收藏", "收藏项用 ★ 标记并置顶", self.action_favorite)
        if self.view_trash:
            yield SystemCommand("清空回收站", "彻底删除回收站内所有会话", self.action_empty_trash)
            yield SystemCommand("返回会话列表", "退出回收站视图", self.action_toggle_trash)
        else:
            yield SystemCommand("查看回收站", "浏览已删除的会话并可恢复", self.action_toggle_trash)
        yield SystemCommand("回收站目录位置", f"{config.trash_dir()}", self._show_trash_path)
        # 中文版的通用命令(替代 super 的英文 Theme/Quit/Screenshot)
        yield SystemCommand("切换主题", "更换界面配色主题", self.action_change_theme)
        yield SystemCommand("退出", "关闭 cchist", self.action_quit)

    def action_command_palette(self):
        # 覆盖默认入口,把搜索框提示文案改为中文
        if self.use_command_palette and not CommandPalette.is_open(self):
            self.push_screen(CommandPalette(placeholder="搜索命令…", id="--command-palette"))

    def _set_sort(self, key: str):
        self.sort_key = key
        self.sort_reverse = core.SORT_KEYS[key][1]
        self.apply_filter()

    def _show_trash_path(self):
        self.notify(f"回收站位置:\n{config.trash_dir()}", timeout=6)

    # ---- 事件 ----
    def on_data_table_row_highlighted(self, event):
        self.update_preview()

    def on_data_table_row_selected(self, event):
        # 回车或点击行 -> 打开/恢复
        self.action_resume()

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        # 点击表头 -> 按该列排序;再次点同一列 -> 翻转方向
        key = self.COLUMN_SORT.get(event.column_index)
        if not key:
            return
        if self.sort_key == key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_key = key
            self.sort_reverse = core.SORT_KEYS[key][1]
        self.apply_filter()

    def on_input_changed(self, event: Input.Changed):
        if event.input.id == "search":
            self.query = event.value
            self.apply_filter()

    def on_input_submitted(self, event: Input.Submitted):
        self.query_one("#table", DataTable).focus()

    # ---- 动作 ----
    def action_cycle_sort(self):
        order = ["time", "project", "turns", "size"]
        i = order.index(self.sort_key)
        self._set_sort(order[(i + 1) % len(order)])

    def action_focus_search(self):
        self.query_one("#search", Input).focus()

    def action_clear_search(self):
        inp = self.query_one("#search", Input)
        if inp.value:
            inp.value = ""
            self.query = ""
            self.apply_filter()
        self.query_one("#table", DataTable).focus()

    def action_full_text(self):
        self.fulltext_mode = not self.fulltext_mode
        self.apply_filter()
        self.notify(f"全文搜索:{'开' if self.fulltext_mode else '关'}")

    def action_toggle_trash(self):
        self.view_trash = not self.view_trash
        self.reload()

    def action_favorite(self):
        s = self.current_session()
        if s:
            now = core.toggle_favorite(s.session_id)
            self.notify(f"{'★ 已收藏' if now else '取消收藏'}:{s.project_label}")
            self.refresh_table()

    def action_delete(self):
        s = self.current_session()
        if not s:
            return
        if self.view_trash:
            def do():
                try:
                    core.delete_permanently(s)
                    self.notify("已彻底删除")
                    self.reload()
                except RuntimeError as e:
                    self.notify(str(e), severity="error")
            self.push_screen(ConfirmScreen(
                f"[bold red]彻底删除?此操作不可恢复![/bold red]\n\n{s.first_msg[:60]}", do))
        else:
            def do():
                try:
                    core.move_to_trash(s)
                    self.notify(f"已移入回收站(按 t 查看/恢复)")
                    self.reload()
                except RuntimeError as e:
                    self.notify(str(e), severity="error")
            self.push_screen(ConfirmScreen(
                f"移入回收站?\n\n{s.project_label} · {s.user_turns}/{s.assistant_turns} 轮\n{s.first_msg[:60]}", do))

    def action_restore(self):
        if not self.view_trash:
            self.notify("只有回收站里能恢复(按 t 进入)")
            return
        s = self.current_session()
        if s:
            try:
                origin = core.restore_from_trash(s)
                self.notify(f"已恢复")
                self.reload()
            except RuntimeError as e:
                self.notify(str(e), severity="error")

    def action_empty_trash(self):
        if not self.view_trash:
            self.notify("请先按 t 进入回收站")
            return
        def do():
            n = core.empty_trash()
            self.notify(f"已清空回收站({n} 个)")
            self.reload()
        self.push_screen(ConfirmScreen("[bold red]清空回收站?所有文件将被彻底删除![/bold red]", do))

    def action_resume(self):
        s = self.current_session()
        if not s:
            return
        if self.view_trash:
            self.action_restore()
            return
        target_dir = s.cwd if s.cwd_exists else os.path.expanduser("~")
        resume.write_signal(target_dir, s.session_id, s.provider)
        self.exit(message="resume")

    def action_open_terminal(self):
        # 与 action_resume 的区别:不退出 cchist,另开一个终端窗口跑 resume
        s = self.current_session()
        if not s:
            return
        if self.view_trash:
            self.notify("回收站里的会话不能打开,先按 r 恢复", severity="warning")
            return
        target_dir = s.cwd if s.cwd_exists else os.path.expanduser("~")
        ok, msg = resume.open_in_new_terminal(target_dir, s.session_id, s.provider)
        self.notify(msg, timeout=6, severity="information" if ok else "error")

    def action_export(self):
        s = self.current_session()
        if not s:
            return
        try:
            path = core.export_to_file(s)
            self.notify(f"已导出 Markdown:\n{path}", timeout=6)
        except OSError as e:
            self.notify(f"导出失败:{e}", severity="error")

    def action_cleanup(self):
        if self.view_trash:
            self.notify("回收站视图下不清理,请先按 t 返回列表")
            return
        targets = core.cleanup_targets(self.all_sessions)
        if not targets:
            self.notify("没有可清理的空/孤儿对话 ✓")
            return
        n_trivial = sum(1 for s in targets if s.is_trivial)
        n_orphan = sum(1 for s in targets if s.is_orphan and not s.is_trivial)

        def do():
            ok, errors = core.batch_move_to_trash(targets)
            if errors:
                self.notify(f"清理 {ok} 个,{len(errors)} 个失败", severity="warning")
            else:
                self.notify(f"已把 {ok} 个对话移入回收站(可恢复)")
            self.reload()
        self.push_screen(ConfirmScreen(
            f"批量清理?将把以下会话移入回收站(可恢复):\n\n"
            f"· 空对话 {n_trivial} 个\n· 孤儿会话(目录已删) {n_orphan} 个\n共 {len(targets)} 个", do))

