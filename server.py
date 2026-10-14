# -*- coding: utf-8 -*-
"""启动本地网页服务。

    python server.py
    python server.py --port 9000 --no-browser

浏览器会自动打开 http://127.0.0.1:8765/
"""

import argparse
import sys
from typing import List, Optional

from poetry_checker import __version__
from poetry_checker.server import serve


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="诗词格律校验器 · 网页服务",
        description="在本机启动校验器的网页界面。",
    )
    p.add_argument("--host", default="127.0.0.1",
                   help="监听地址（默认只绑本机，局域网内他人访问不到）")
    p.add_argument("--port", type=int, default=8765,
                   help="监听端口（默认 8765；被占用时会自动往后试）")
    p.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    p.add_argument("--quiet", action="store_true", help="不打印启动横幅")
    p.add_argument("-v", "--version", action="version",
                   version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)

    return serve(
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    sys.exit(main())
