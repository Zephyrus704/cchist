# Changelog

## [0.3.0] - 2026-08-07

Multi-agent support and public release.

### Added
- **Codex support** — scans `~/.codex/sessions`, parses transcripts, resumes via `codex resume`
- `Provider` abstraction (`providers.py`) so more tools can be added later
- **Bilingual UI** (English / 中文), auto-detected or via `CCHIST_LANG`
- Provider column in TUI, provider badge in the web UI
- GitHub Actions CI across Python 3.9 / 3.11 / 3.13

### Changed
- English README as the primary doc; Chinese README at `README.zh-CN.md`
- Packaging metadata prepared for PyPI

## [0.2.0] - 2026-08-06

新增导出、批量清理、统计与网页停止能力，并提升跨平台健壮性。

### 新增
- **导出对话**：TUI 按 `e`、网页点「导出」把对话存为 Markdown
- **批量清理**：TUI 按 `c`、网页点「🧹 清理」一键把空/孤儿会话移入回收站
- **网页统计页**：每日对话量趋势 + 项目分布图（纯 CSS/SVG，无图表库）
- **网页优雅停止**：右上角「⏻ 停止服务器」按钮；启动横幅明确提示停止方式
- **空列表友好提示**：扫不到会话时提示扫描目录与 `CLAUDE_CONFIG_DIR` 设置

### 改进
- 跨平台/版本健壮性：显式支持 Python 3.9–3.13，补 `from __future__ import annotations`
- README 加「快速开始」一行安装、PATH 提示、网页停止说明
- 测试增至 28 个

## [0.1.0] - 2026-08-06

首个版本。

### 新增
- 终端 TUI:跨项目统一列表、搜索(含全文)、首末句+轮数+大小+路径展示
- 无缝 resume:回车自动切回原工作目录并进入 `claude --resume`
- 回收站:删除先进回收站,可恢复/彻底删除/清空;空对话与孤儿会话自动标记
- 收藏、点击表头排序、全中文命令面板
- 网页端(`cchist web`):FastAPI 后端 + 免构建前端,完整对话正文阅读、一键复制 resume 命令、统计概览
- 支持 `CLAUDE_CONFIG_DIR` 环境变量,跨平台
