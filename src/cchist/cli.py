"""cchist 命令行入口:分发 TUI / Web,并处理 resume 信号。"""
import argparse
import sys

from . import __version__, resume


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="cchist",
        description="Claude Code 对话记录管理器 —— 跨项目浏览、搜索、回溯、删除对话。",
    )
    parser.add_argument("-v", "--version", action="version", version=f"cchist {__version__}")
    parser.add_argument("--rebuild-cache", action="store_true",
                        help="清空并重建对话解析缓存(缓存疑似陈旧/损坏时用),然后退出")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("tui", help="启动终端界面(默认)")

    web = sub.add_parser("web", help="启动网页界面")
    web.add_argument("--host", default="127.0.0.1", help="监听地址(默认 127.0.0.1)")
    web.add_argument("--port", type=int, default=8770, help="端口(默认 8770)")
    web.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")

    args = parser.parse_args(argv)

    if args.rebuild_cache:
        from . import core
        core.rebuild_cache()
        print("已清空解析缓存,下次启动将重新扫描全部对话。")
        return 0

    if args.command == "web":
        from .web.server import run_web
        return run_web(host=args.host, port=args.port, open_browser=not args.no_browser)

    # 默认:TUI。TUI 退出后若写了 resume 信号,在这里执行(execvp 接管终端)。
    resume.clear_signal()
    from .tui import CChistApp
    app = CChistApp()
    app.run()

    sig = resume.consume_signal()
    if sig:
        return resume.do_resume(*sig)
    return 0


if __name__ == "__main__":
    sys.exit(main())
