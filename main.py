# -*- coding: utf-8 -*-
"""诗词格律校验器 —— 程序入口。

    python main.py 示例/静夜思.txt
    python main.py --serve             启动本地网页服务
    python main.py --help
"""

import sys

from poetry_checker.cli import main

if __name__ == "__main__":
    sys.exit(main())
