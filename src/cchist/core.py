# SPDX-License-Identifier: MIT
"""cchist 数据层:扫描 / 解析 / 管理 Claude Code 对话记录。

只依赖标准库。TUI 与 Web 前端共用本模块,是整个工具的单一数据源。
路径来自 config 模块,支持 CLAUDE_CONFIG_DIR 覆盖(见 config.py)。
"""
from __future__ import annotations

import glob
import json
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime

from . import config, providers


def _decode_project_dir(name: str) -> str:
    """把 -home-zwb-workspace-PCIE 这类目录名尽量还原成可读路径。仅用于兜底显示。"""
    if name.startswith("-"):
        return "/" + name[1:].replace("-", "/")
    return name


@dataclass
class Session:
    path: str
    session_id: str
    project_dir: str          # projects 下的目录名
    cwd: str                  # 会话真实工作目录(用于 resume 切目录)
    first_msg: str
    last_user_msg: str
    last_assistant_msg: str
    user_turns: int
    assistant_turns: int
    size: int
    mtime: float
    ctime: float
    provider: str = "claude"  # 来自哪个 AI 工具:claude / codex ...
    in_trash: bool = False

    @property
    def total_turns(self) -> int:
        return self.user_turns + self.assistant_turns

    @property
    def is_trivial(self) -> bool:
        """真正的空对话才标记:没有任何真实用户消息,或用户提问了但助手完全没回。
        不因"轮次少"就标,避免误伤简短但有效的对话。"""
        if self.user_turns == 0:
            return True
        if self.user_turns >= 1 and self.assistant_turns == 0:
            return True
        return False

    @property
    def cwd_exists(self) -> bool:
        return bool(self.cwd) and os.path.isdir(self.cwd)

    @property
    def is_orphan(self) -> bool:
        """会话记录的工作目录已不存在(resume 会退回家目录)。"""
        return bool(self.cwd) and not os.path.isdir(self.cwd)

    @property
    def project_label(self) -> str:
        """短标签用于列表显示。"""
        c = self.cwd or _decode_project_dir(self.project_dir)
        parts = [p for p in c.replace("\\", "/").split("/") if p]
        if not parts:
            return "~"
        home_parts = [p for p in str(config.claude_dir().parent).replace("\\", "/").split("/") if p]
        if parts == home_parts:
            return "~"
        return parts[-1]

    @property
    def short_path(self) -> str:
        """家目录缩写为 ~ 的路径,用于展示。"""
        home = os.path.expanduser("~")
        p = self.cwd or "(未知)"
        if p.startswith(home):
            p = "~" + p[len(home):]
        return p

    @property
    def mtime_str(self) -> str:
        return datetime.fromtimestamp(self.mtime).strftime("%m-%d %H:%M")

    @property
    def mtime_full(self) -> str:
        return datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M")

    @property
    def size_str(self) -> str:
        s = float(self.size)
        for unit in ("B", "K", "M", "G"):
            if s < 1024:
                return f"{s:.0f}{unit}" if unit == "B" else f"{s:.1f}{unit}"
            s /= 1024
        return f"{s:.1f}T"

    @property
    def provider_label(self) -> str:
        return providers.get(self.provider).label

    def to_dict(self) -> dict:
        """给 Web 前端用的序列化,附带派生字段。"""
        d = asdict(self)
        d.update(
            total_turns=self.total_turns,
            is_trivial=self.is_trivial,
            is_orphan=self.is_orphan,
            cwd_exists=self.cwd_exists,
            project_label=self.project_label,
            provider_label=self.provider_label,
            short_path=self.short_path,
            mtime_str=self.mtime_str,
            mtime_full=self.mtime_full,
            size_str=self.size_str,
        )
        return d


def _extract_text(content) -> str:
    """(兼容保留)从 Claude message.content 提取纯文本。新代码走 providers。"""
    if isinstance(content, list):
        parts = []
        for x in content:
            if isinstance(x, dict) and x.get("type") == "text":
                parts.append(x.get("text", ""))
        return " ".join(parts)
    return content or ""


def _is_real_user_text(txt: str) -> bool:
    return providers._is_real_user_text(txt)


def _session_id_from_path(path: str, provider_name: str) -> str:
    """从文件名取会话 id。Codex 文件名 rollout-<时间>-<uuid>.jsonl,取末尾 uuid(5 段)。"""
    base = os.path.basename(path)
    if base.endswith(".jsonl"):
        base = base[:-6]
    if provider_name == "codex" and base.startswith("rollout-"):
        parts = base.split("-")
        if len(parts) >= 5:
            return "-".join(parts[-5:])
    return base


# 解析结果缓存:path -> Session。避免重复扫描时反复读大文件。
# 内存层(_parse_cache)在单进程内生效;磁盘层(cache_file)让缓存跨进程存活——
# 这是性能关键:每次启动 cchist 都是新进程,没有磁盘缓存就得把全部(可能数 GB)
# 会话文件重新逐行解析一遍。缓存按 path 存,失效判据是 mtime 或 size 变化。
_CACHE_VERSION = 1
_parse_cache: dict = {}     # path -> Session
_disk_loaded = False        # 磁盘缓存是否已载入本进程(懒加载,只载一次)
_cache_dirty = False        # 有新解析/变更待落盘


def _load_disk_cache():
    """把磁盘缓存载入内存,只在本进程首次需要时执行一次。容错:文件缺失/损坏/版本不符都当空缓存。"""
    global _disk_loaded
    if _disk_loaded:
        return
    _disk_loaded = True
    cf = config.cache_file()
    try:
        data = json.loads(cf.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(data, dict) or data.get("version") != _CACHE_VERSION:
        return
    for path, fields in data.get("entries", {}).items():
        if path in _parse_cache:
            continue
        try:
            _parse_cache[path] = Session(**fields)
        except (TypeError, ValueError):
            continue


def _flush_disk_cache():
    """把内存缓存原子写回磁盘(仅在有变更时)。回收站条目与已不存在的文件不落盘。"""
    global _cache_dirty
    if not _cache_dirty:
        return
    entries = {}
    for path, sess in _parse_cache.items():
        if sess.in_trash:
            continue
        if not os.path.exists(path):   # 顺带清理已删除文件的陈旧条目,防止缓存无限膨胀
            continue
        entries[path] = asdict(sess)
    cf = config.cache_file()
    tmp = cf.with_name(cf.name + ".tmp")
    try:
        tmp.write_text(json.dumps({"version": _CACHE_VERSION, "entries": entries},
                                  ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(cf))
        _cache_dirty = False
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def reset_cache():
    """清空内存缓存并重置懒加载标志(测试隔离用;不动磁盘文件)。"""
    global _disk_loaded, _cache_dirty
    _parse_cache.clear()
    _disk_loaded = False
    _cache_dirty = False


def rebuild_cache():
    """删除磁盘缓存并清空内存,使下次扫描全量重解析。缓存疑似陈旧/损坏时用。"""
    global _disk_loaded, _cache_dirty
    _parse_cache.clear()
    try:
        config.cache_file().unlink()
    except OSError:
        pass
    _disk_loaded = True   # 已知磁盘为空,无需再尝试载入
    _cache_dirty = False


def _peek_cwd(path: str, provider_name: str, max_lines: int = 200) -> str:
    """只读文件开头若干行,尽快取出 cwd。用于"忽略目录跳过解析":
    避免为判断归属而通读一个可能几十 MB 的大文件。取不到就返回 ""(交给完整解析)。"""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if provider_name == "codex":
                    payload = d.get("payload", {})
                    if d.get("type") in ("session_meta", "turn_context") and payload.get("cwd"):
                        return payload["cwd"]
                else:
                    if d.get("cwd"):
                        return d["cwd"]
    except OSError:
        return ""
    return ""


def parse_session(path: str, in_trash: bool = False, provider_name: str = "claude") -> Session | None:
    global _cache_dirty
    try:
        st = os.stat(path)
    except OSError:
        return None
    _load_disk_cache()
    cached = _parse_cache.get(path)
    if (cached and cached.mtime == st.st_mtime and cached.size == st.st_size
            and cached.in_trash == in_trash):
        return cached

    prov = providers.get(provider_name)
    session_id = _session_id_from_path(path, provider_name)
    project_dir = os.path.basename(os.path.dirname(path))
    try:
        info = prov.parse(path)
    except OSError:
        return None

    session = Session(
        path=path,
        session_id=session_id,
        project_dir=project_dir,
        cwd=info.get("cwd", ""),
        first_msg=info.get("first") or "(无用户消息)",
        last_user_msg=info.get("last_user", ""),
        last_assistant_msg=info.get("last_assistant", ""),
        user_turns=info.get("user_turns", 0),
        assistant_turns=info.get("assistant_turns", 0),
        size=st.st_size,
        mtime=st.st_mtime,
        ctime=st.st_ctime,
        provider=provider_name,
        in_trash=in_trash,
    )
    _parse_cache[path] = session
    _cache_dirty = True
    return session


# ---- 收藏 ----
def load_favorites() -> set:
    fav = config.favorites_file()
    if fav.exists():
        try:
            return set(json.loads(fav.read_text()))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def save_favorites(favs: set):
    try:
        config.favorites_file().write_text(json.dumps(sorted(favs)))
    except OSError:
        pass


def toggle_favorite(session_id: str) -> bool:
    favs = load_favorites()
    if session_id in favs:
        favs.discard(session_id)
        result = False
    else:
        favs.add(session_id)
        result = True
    save_favorites(favs)
    return result


# 向后兼容别名(旧代码/测试可能引用下划线版本)
_load_favorites = load_favorites
_save_favorites = save_favorites


# ---- 忽略目录(按文件夹过滤会话,持久化且可恢复) ----
# 忽略清单存 ~/.claude/.cchist_config.json 的 "ignored_dirs",退出重开仍生效;
# 只是"不显示",从不删文件,随时可从忽略列表移除以恢复显示。
def _load_config() -> dict:
    cf = config.config_file()
    if cf.exists():
        try:
            data = json.loads(cf.read_text())
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_config(data: dict):
    try:
        config.config_file().write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except OSError:
        pass


def load_ignored() -> list:
    """已忽略的文件夹列表(规范化后的绝对路径)。"""
    dirs = _load_config().get("ignored_dirs", [])
    if not isinstance(dirs, list):
        return []
    return [str(d) for d in dirs]


def save_ignored(dirs):
    """去重 + 规范化 + 排序后写回,保持文件稳定、可读。"""
    data = _load_config()
    norm = sorted({os.path.normpath(os.path.expanduser(str(d)))
                   for d in dirs if str(d).strip()})
    data["ignored_dirs"] = norm
    _save_config(data)


def add_ignored(path: str) -> list:
    dirs = load_ignored()
    p = os.path.normpath(os.path.expanduser(path))
    if p not in dirs:
        dirs.append(p)
    save_ignored(dirs)
    return load_ignored()


def remove_ignored(path: str) -> list:
    p = os.path.normpath(os.path.expanduser(path))
    save_ignored([d for d in load_ignored() if d != p])
    return load_ignored()


def _within(child: str, parent: str) -> bool:
    """child 等于 parent 或在其之下(按路径前缀比较,不解析符号链接,兼容已删目录)。"""
    if not child or not parent:
        return False
    child = os.path.normpath(child)
    parent = os.path.normpath(parent)
    return child == parent or child.startswith(parent + os.sep)


def is_ignored(session: Session, ignored: list = None) -> bool:
    if ignored is None:
        ignored = load_ignored()
    if not ignored or not session.cwd:
        return False
    return any(_within(session.cwd, d) for d in ignored)


def filter_ignored(sessions: list, ignored: list = None) -> list:
    """去掉落在被忽略文件夹内的会话。"""
    if ignored is None:
        ignored = load_ignored()
    if not ignored:
        return list(sessions)
    return [s for s in sessions if not is_ignored(s, ignored)]


# ---- 扫描 ----
def _should_skip_ignored(path: str, provider_name: str, ignored: list) -> bool:
    """在完整解析前判断该文件是否落在被忽略目录内,用真实 cwd 判断(不误伤)。
    命中则可跳过通读大文件。注意:目录名 slug 有歧义且有时非路径编码,所以必须读 cwd,不能反推目录名。"""
    try:
        st = os.stat(path)
    except OSError:
        return False
    cached = _parse_cache.get(path)
    if cached and cached.mtime == st.st_mtime and cached.size == st.st_size and cached.cwd:
        return is_ignored(cached, ignored)
    cwd = _peek_cwd(path, provider_name)
    if not cwd:
        return False   # 取不到 cwd 就别跳过,留给完整解析,保证正确性
    return any(_within(cwd, d) for d in ignored)


def scan_sessions(include_trash: bool = False, skip_ignored_dirs: list = None,
                  on_progress=None) -> list[Session]:
    """扫描全部会话。
    - skip_ignored_dirs: 传入忽略目录清单时,落在其中的会话在解析前就跳过(省去通读大文件);
      调用方仍应对结果再跑一次 filter_ignored 作为权威过滤(覆盖缓存命中的忽略项)。
    - on_progress(done, total): 冷扫描进度回调,供 UI 显示,避免看起来卡死。
    """
    _load_disk_cache()
    ignored = skip_ignored_dirs or []
    all_paths = [(prov, p) for prov in providers.ALL for p in prov.scan()]
    total = len(all_paths)
    sessions = []
    for i, (prov, path) in enumerate(all_paths):
        if ignored and _should_skip_ignored(path, prov.name, ignored):
            if on_progress and (i % 50 == 0 or i == total - 1):
                on_progress(i + 1, total)
            continue
        s = parse_session(path, provider_name=prov.name)
        if s:
            sessions.append(s)
        if on_progress and (i % 50 == 0 or i == total - 1):
            on_progress(i + 1, total)
    _flush_disk_cache()
    if include_trash:
        sessions.extend(scan_trash())
    sessions.sort(key=lambda s: s.mtime, reverse=True)
    return sessions


def scan_trash() -> list[Session]:
    sessions = []
    td = config.trash_dir()
    if td.exists():
        for path in glob.glob(os.path.join(str(td), "*.jsonl")):
            # 回收站里存了 .provider 旁文件记录来源工具
            pv_file = td / (os.path.basename(path)[:-6] + ".provider")
            pname = pv_file.read_text().strip() if pv_file.exists() else "claude"
            s = parse_session(path, in_trash=True, provider_name=pname)
            if s:
                sessions.append(s)
    sessions.sort(key=lambda s: s.mtime, reverse=True)
    return sessions


def find_session(session_id: str, include_trash: bool = True) -> Session | None:
    for s in scan_sessions(include_trash=include_trash):
        if s.session_id == session_id:
            return s
    return None


# ---- 回收站 ----
def move_to_trash(session: Session) -> str:
    """把会话移入回收站,记录原始路径与来源工具以便恢复。返回回收站中的新路径。"""
    global _cache_dirty
    td = config.trash_dir()
    td.mkdir(parents=True, exist_ok=True)
    dest = td / f"{session.session_id}.jsonl"
    meta = td / f"{session.session_id}.origin"
    pv = td / f"{session.session_id}.provider"
    try:
        meta.write_text(session.path)
        pv.write_text(session.provider)
        shutil.move(session.path, str(dest))
    except (OSError, shutil.Error) as e:
        raise RuntimeError(f"移入回收站失败: {e}")
    _parse_cache.pop(session.path, None)
    _cache_dirty = True   # 让下次落盘清理该文件的陈旧缓存条目
    return str(dest)


def restore_from_trash(session: Session) -> str:
    """从回收站恢复到原始位置。"""
    global _cache_dirty
    td = config.trash_dir()
    meta = td / f"{session.session_id}.origin"
    pv = td / f"{session.session_id}.provider"
    if meta.exists():
        origin = meta.read_text().strip()
    else:
        origin = str(providers.get(session.provider).root() / session.project_dir / f"{session.session_id}.jsonl")
    os.makedirs(os.path.dirname(origin), exist_ok=True)
    try:
        shutil.move(session.path, origin)
        if meta.exists():
            meta.unlink()
        if pv.exists():
            pv.unlink()
    except (OSError, shutil.Error) as e:
        raise RuntimeError(f"恢复失败: {e}")
    _parse_cache.pop(session.path, None)
    _cache_dirty = True
    return origin


def delete_permanently(session: Session):
    """彻底删除(仅用于回收站内)。"""
    try:
        os.unlink(session.path)
        for suffix in (".origin", ".provider"):
            meta = config.trash_dir() / f"{session.session_id}{suffix}"
            if meta.exists():
                meta.unlink()
    except OSError as e:
        raise RuntimeError(f"删除失败: {e}")
    _parse_cache.pop(session.path, None)


def empty_trash() -> int:
    n = 0
    for s in scan_trash():
        delete_permanently(s)
        n += 1
    return n


# ---- 排序 / 搜索 ----
SORT_KEYS = {
    "time": (lambda s: s.mtime, True),        # (取值函数, 默认降序)
    "provider": (lambda s: s.provider, False),
    "project": (lambda s: s.project_label.lower(), False),
    "turns": (lambda s: s.total_turns, True),
    "size": (lambda s: s.size, True),
}


def sort_sessions(sessions: list, key: str, reverse: bool) -> list:
    fn = SORT_KEYS.get(key, SORT_KEYS["time"])[0]
    return sorted(sessions, key=fn, reverse=reverse)


def matches(session: Session, query: str) -> bool:
    """轻量搜索:命中标签 / 首末句 / 路径 / session_id。"""
    if not query:
        return True
    q = query.lower()
    haystack = " ".join([
        session.project_label,
        session.cwd,
        session.first_msg,
        session.last_user_msg,
        session.last_assistant_msg,
        session.session_id,
    ]).lower()
    return q in haystack


def full_text_search(query: str, session: Session) -> bool:
    """在整个 jsonl 文件里搜(慢,按需触发)。"""
    if not query:
        return True
    q = query.lower()
    try:
        with open(session.path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if q in line.lower():
                    return True
    except OSError:
        return False
    return False


def read_transcript(session: Session, limit: int = 500) -> list[dict]:
    """读出完整对话消息列表(供 Web 端展示)。返回 [{role, text, ts}]。"""
    try:
        return providers.get(session.provider).transcript(session.path, limit)
    except OSError:
        return []


# ---- 导出 ----
def export_markdown(session: Session) -> str:
    """把一个会话渲染成 Markdown 文本。"""
    lines = [
        f"# {session.first_msg[:80]}",
        "",
        f"- 项目路径:`{session.cwd or '(未知)'}`",
        f"- 会话 ID:`{session.session_id}`",
        f"- 轮数:用户 {session.user_turns} · 助手 {session.assistant_turns}",
        f"- 更新时间:{session.mtime_full}",
        "",
        "---",
        "",
    ]
    for m in read_transcript(session, limit=10000):
        who = "🧑 用户" if m["role"] == "user" else "🤖 Claude"
        lines.append(f"## {who}")
        lines.append("")
        lines.append(m["text"])
        lines.append("")
    return "\n".join(lines)


def export_to_file(session: Session, dest_dir: str = "") -> str:
    """把会话导出为 .md 文件,返回写入的路径。默认导出到 ~/cchist-exports/。"""
    if not dest_dir:
        dest_dir = os.path.join(os.path.expanduser("~"), "cchist-exports")
    os.makedirs(dest_dir, exist_ok=True)
    # 文件名:项目_首句片段_短id,清掉非法字符
    snippet = "".join(c for c in session.first_msg[:20] if c not in '/\\:*?"<>|\n\r\t').strip()
    fname = f"{session.project_label}_{snippet}_{session.session_id[:8]}.md"
    fname = fname.replace(" ", "_")
    path = os.path.join(dest_dir, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(export_markdown(session))
    return path


# ---- 批量清理 ----
def cleanup_targets(sessions: list = None) -> list:
    """返回可清理的会话(空对话 + 孤儿会话)。不传则扫描全部。"""
    if sessions is None:
        sessions = scan_sessions(include_trash=False)
    return [s for s in sessions if s.is_trivial or s.is_orphan]


def batch_move_to_trash(sessions: list) -> tuple:
    """批量移入回收站。返回 (成功数, 失败列表[(session_id, 错误)])。"""
    ok = 0
    errors = []
    for s in sessions:
        try:
            move_to_trash(s)
            ok += 1
        except RuntimeError as e:
            errors.append((s.session_id, str(e)))
    return ok, errors


# ---- 统计(供 Web 概览页) ----
def daily_counts(sessions: list = None) -> list:
    """按日期统计对话数。返回 [{date, count}](按日期升序,便于画趋势)。"""
    from collections import Counter
    if sessions is None:
        sessions = scan_sessions(include_trash=False)
    c = Counter()
    for s in sessions:
        day = datetime.fromtimestamp(s.mtime).strftime("%Y-%m-%d")
        c[day] += 1
    return [{"date": d, "count": c[d]} for d in sorted(c)]

