# cchist

![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-MIT-green)

> 一处浏览、搜索、**回溯**你所有的 AI 编程会话 —— 同时支持 Claude Code 和 Codex。

[English →](README.md)

Claude Code 和 Codex 会把每次对话散落在各自的项目目录里
（`~/.claude/projects/…`、`~/.codex/sessions/…`）。时间一长就无从翻起：
`--resume` 只显示自动生成的标题，会话又分散在十几个目录中。

**cchist** 把它们全部拉平到一个界面：按标题或全文搜索、看首末句和轮数、
一键回到任意会话（自动切回原目录并 resume）、安全清理临时对话。

一套核心，两种前端：

- **终端 TUI**（默认）—— 键盘操作，回车即无缝 resume
- **网页**（`cchist web`）—— 更适合阅读长对话、导出、看统计

---

## 特性

| | |
|---|---|
| 🔀 **多 agent** | 统一管理 **Claude Code** 和 **Codex** 的会话 |
| 🗂 **跨项目** | 所有目录拉平到一处，按时间/来源/项目/轮数/大小排序 |
| 🔍 **搜索** | 过滤标题/路径/首末句，或全文检索对话正文 |
| ↩️ **无缝回溯** | 回车在原目录执行 `claude --resume` / `codex resume` |
| 🗑 **安全删除** | 先进回收站可恢复；空对话/孤儿会话自动标记 |
| 🧹 **批量清理** | 一键把所有空/孤儿会话移入回收站 |
| ⬇️ **导出** | 把对话导出为 Markdown |
| 📊 **统计** | 网页端概览：每日对话量趋势、项目分布 |
| ⭐ **收藏** | 重要对话打星置顶 |
| 🌐 **中英双语** | 界面自动识别语言，或设 `CCHIST_LANG=zh/en` |
| 🔧 **可移植** | 路径可用环境变量覆盖；Linux/macOS/Windows；Python 3.9+ |

---

## 安装

```bash
pip install --user "cchist[web]"     # 从 PyPI 安装(含网页端)
# 或从源码:
git clone https://github.com/Zephyrus704/cchist.git && cd cchist && pip install --user ".[web]"
```

> 若提示 `cchist: command not found`，把 `~/.local/bin` 加入 PATH:
> `export PATH="$HOME/.local/bin:$PATH"`。

## 使用

```bash
cchist              # 终端界面(默认)
cchist web          # 网页界面(自动开浏览器)
cchist --help
```

### TUI 快捷键

| 键 | 功能 |
|---|---|
| `↑/↓` | 移动 |
| `Enter` | 打开(切目录 + resume) |
| `o` | 新终端窗口打开,列表保持打开 |
| `/` | 搜索 |
| `g` | 全文搜索 |
| 点表头 / `s` | 按列排序，再点翻转 |
| `e` | 导出为 Markdown |
| `f` | 收藏 |
| `d` | 删除(进回收站) |
| `c` | 批量清理空/孤儿 |
| `t` | 回收站 |
| `r` | 恢复 |
| `Ctrl+D` | 清空回收站 |
| `q` | 退出 |

### 网页端说明

`cchist web` 会在终端启动本地服务器（默认 `http://127.0.0.1:8770`）。

- **停止**：回终端按 `Ctrl+C`，或点右上角「⏻ 停止服务器」。
  ⚠️ 只关浏览器标签页不会停止服务器。
- 只绑定 `127.0.0.1`，请勿用 `--host 0.0.0.0` 对外暴露。

## 工作原理

各工具把会话存成 JSONL，记录工作目录和逐条消息：

- **Claude Code** — `~/.claude/projects/<目录>/<session-id>.jsonl`
- **Codex** — `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`

cchist 只读它们。`providers.py` 里的 `Provider` 抽象封装了每个工具的
存储位置、格式和 resume 命令，其余(回收站/搜索/排序/导出/UI)全部与工具无关。
可用 `CLAUDE_CONFIG_DIR`、`CODEX_HOME` 覆盖存储位置。

cchist **不修改**任何对话文件，只做移动/删除，且删除先进回收站。

## License

MIT
