# -*- coding: utf-8 -*-
"""诗词格律校验器 —— 程序入口。

    python main.py 示例/01-五言绝句-登鹳雀楼.txt
    python main.py -t "国破山河在，城春草木深。"
    python main.py --serve             启动本地网页服务
    python main.py --help
"""

import sys

from poetry_checker.cli import main

if __name__ == "__main__":
    sys.exit(main())
