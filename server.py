# -*- coding: utf-8 -*-
"""启动本地网页服务。

    python server.py

浏览器会自动打开 http://127.0.0.1:8765/
"""

import sys

from poetry_checker.server import serve

if __name__ == "__main__":
    sys.exit(serve(port=8765, open_browser=True))
