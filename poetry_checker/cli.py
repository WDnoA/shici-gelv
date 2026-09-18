# -*- coding: utf-8 -*-
"""命令行入口。

    python main.py 示例/01-五言绝句-登鹳雀楼.txt
    python main.py -t "国破山河在，城春草木深。"
    type 诗.txt | python main.py
    python main.py --verify-kb
    python main.py --list-cipai
    python main.py --expect 示例
    python main.py --serve
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, analyze
from .knowledge import CILIN, PINGSHUI, XINYUN, KnowledgeBase, KnowledgeError
from . import report as rp


TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "cp936")


def _setup_streams() -> None:
    """把标准流切到 UTF-8，避免 Windows 控制台默认 GBK 造成乱码或崩溃。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def _decode(data: bytes) -> str:
    for enc in TEXT_ENCODINGS:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _read_input(args) -> str:
    if args.text:
        return args.text
    if args.path:
        p = Path(args.path)
        if not p.exists():
            raise SystemExit(f"找不到文件：{p}")
        return _decode(p.read_bytes())

    # 管道输入：必须读原始字节再自行解码。
    # 直接 sys.stdin.read() 在中文 Windows 下会按 GBK 解码，
    # 遇到 UTF-8 的中文就产生非法代理字符，print 时会崩。
    try:
        raw = sys.stdin.buffer.read()
    except AttributeError:  # pragma: no cover
        raw = sys.stdin.read().encode("utf-8")
    data = _decode(raw)
    if not data.strip():
        raise SystemExit("没有输入内容。用 -t 给出文本、给出文件路径，或通过管道输入。")
    return data


# ---------------------------------------------------------------- 自检


def verify_kb(kb: KnowledgeBase) -> int:
    problems: List[str] = []
    print(f"知识库目录：{kb.root}")
    print(rp.rule())

    for name, book in kb.rhyme_books.items():
        print(f"  《{name}》：收录 {book.size} 个单字")
        if book.size == 0:
            problems.append(f"{name} 为空")

    multi = sum(1 for ch, pairs in kb.book(PINGSHUI).entries.items() if len(pairs) > 1)
    print(f"  平水韵中一字多归属者：{multi} 字（多音字，属正常现象）")
    print(f"  词牌数：{len(kb.cipai)}（含别名 {len(kb.cipai_alias)} 条）")
    print(f"  对仗词类：{len(kb.categories)} 门，收录 {len(kb.char_category)} 字")
    print()

    # 1. 近体诗诗谱能否正常推导
    try:
        from . import patterns as pt

        for kind in ("五言", "七言"):
            for first in pt.all_first_patterns(kb, kind):
                pu = pt.build_shi_pu(kb, kind, first, 8)
                if len(pu) != 8:
                    problems.append(f"{kind} 诗谱长度异常：{first}")
        print("  ✔ 近体诗诗谱推导正常（五言/七言 × 4 式）")
    except Exception as exc:  # pragma: no cover
        problems.append(f"诗谱推导失败：{exc}")

    # 2. 各词牌的谱长度与标称字数是否一致
    for name, spec in kb.cipai.items():
        lengths = [sum(1 for c in g["谱"] if c in "平仄中") for g in spec.get("格律", [])]
        total = sum(lengths)
        declared = spec.get("字数")
        if declared and total != declared:
            problems.append(f"词牌《{name}》谱长 {total} ≠ 标称 {declared}")
        if spec.get("句数") and len(spec.get("格律", [])) != spec["句数"]:
            problems.append(
                f"词牌《{name}》句数 {len(spec.get('格律', []))} ≠ 标称 {spec['句数']}"
            )
    print(f"  ✔ 词牌谱长校验完毕（{len(kb.cipai)} 个）")

    # 3. 中华新韵可用性
    if kb.xinyun_available:
        print("  ✔ pypinyin 已安装，可使用「中华新韵」")
    else:
        print("  · 未安装 pypinyin，暂时无法使用「中华新韵」（pip install pypinyin）")

    print(rp.rule())
    if problems:
        print(f"发现 {len(problems)} 个问题：")
        for p in problems:
            print(f"  ✘ {p}")
        return 1
    print("知识库自检通过。")
    return 0


def list_cipai(kb: KnowledgeBase) -> int:
    print(f"{'词牌':<12}{'字数':>6}{'段':>4}{'句':>4}   别名")
    print(rp.rule())
    for name, spec in sorted(kb.cipai.items(), key=lambda kv: kv[1].get("字数", 0)):
        aliases = "、".join(spec.get("别名", [])[:4])
        print(
            f"{name:<12}{spec.get('字数', '?'):>6}{spec.get('段数', '?'):>4}"
            f"{len(spec.get('格律', [])):>4}   {aliases}"
        )
    print(rp.rule())
    print(f"共 {len(kb.cipai)} 个词牌。")
    return 0


def expect_table(kb: KnowledgeBase, directory: str = "示例") -> int:
    """扫描目录，打印一张 Markdown 结论表。

    这张表就是 ``示例/README.md`` 里的「预期结论」。示例文件一旦被改动，
    文档就会失真——本项目已经发生过一次（使用者把示例 10 改好了，
    文档却还写着「出韵」）。与其靠人记得同步，不如让文档可一键重算：

        python main.py --expect 示例

    把输出粘回文档即可。
    """
    folder = Path(directory)
    if not folder.is_dir():
        print(f"找不到目录：{folder}", file=sys.stderr)
        return 2

    files = sorted(folder.glob("*.txt"))
    if not files:
        print(f"{folder} 里没有 .txt 文件", file=sys.stderr)
        return 2

    print("| 文件 | 体裁 | 结论 | 韵部 | 平仄符合度 |")
    print("| --- | --- | --- | --- | --- |")
    for path in files:
        result = analyze(_decode(path.read_bytes()), kb=kb)
        obj = result.poem or result.ci
        genre = result.poem.genre if result.poem else (result.ci.cipai if result.ci else "—")
        verdict = obj.verdict if obj else "无法识别"

        group = ""
        if result.poem and result.poem.rhyme and result.poem.rhyme.main_group:
            group = result.poem.rhyme.main_group
        elif result.ci and result.ci.rhyme_groups:
            names = [g.main_group for g in result.ci.rhyme_groups if g.main_group]
            group = "／".join(dict.fromkeys(names))

        print(
            f"| `{path.name}` | {genre} | {verdict} | {group or '—'} "
            f"| {result.score * 100:.1f}% |"
        )
    return 0


# ---------------------------------------------------------------- 主函数


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="诗词格律校验器",
        description="以知识库为标准，校验诗词的平仄、押韵、对仗。本工具不含 AI，不生成内容。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python main.py 示例/01-五言绝句-登鹳雀楼.txt\n"
            "  python main.py -t \"国破山河在，城春草木深。感时花溅泪，恨别鸟惊心。\"\n"
            "  python main.py -t \"《浣溪沙》一曲新词酒一杯，去年天气旧亭台。\"\n"
            "  python main.py --verify-kb\n"
            "  python main.py --list-cipai\n"
            "  python main.py --expect 示例       扫描目录并打印结论表（Markdown）\n"
            "  python main.py --serve             启动网页界面\n"
        ),
    )
    p.add_argument("path", nargs="?", help="诗词文本文件路径（UTF-8）")
    p.add_argument("-t", "--text", help="直接给出诗词文本")
    p.add_argument(
        "-b", "--book",
        default=PINGSHUI,
        choices=[PINGSHUI, XINYUN, CILIN],
        help="近体诗所用韵书（默认平水韵）；填词固定使用词林正韵",
    )
    p.add_argument(
        "--shape", default="auto", choices=["auto", "诗", "词"],
        help="强制按近体诗或词解析",
    )
    p.add_argument("--json", action="store_true", help="输出 JSON（供程序调用）")
    p.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    p.add_argument("--brief", action="store_true", help="精简报告（不展开对仗细节）")
    p.add_argument("--verify-kb", action="store_true", help="自检知识库数据")
    p.add_argument("--list-cipai", action="store_true", help="列出知识库中的词牌")
    p.add_argument(
        "--expect", nargs="?", const="示例", metavar="目录",
        help="扫描目录并打印各示例的结论表（Markdown），用于同步文档",
    )
    p.add_argument("--serve", action="store_true", help="启动本地网页服务（浏览器界面）")
    p.add_argument("--port", type=int, default=8765, help="网页服务端口（默认 8765）")
    p.add_argument("--no-browser", action="store_true", help="启动服务时不自动打开浏览器")
    p.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    _setup_streams()
    args = build_parser().parse_args(argv)

    try:
        kb = KnowledgeBase.load()
    except KnowledgeError as exc:
        print(f"知识库加载失败：{exc}", file=sys.stderr)
        return 2

    if args.serve:
        from .server import serve

        return serve(port=args.port, open_browser=not args.no_browser)

    if args.verify_kb:
        return verify_kb(kb)
    if args.list_cipai:
        return list_cipai(kb)
    if args.expect:
        return expect_table(kb, args.expect)

    text = _read_input(args)
    result = analyze(text, kb=kb, book=args.book, shape=args.shape)

    if args.json:
        print(result.json())
    else:
        color = not args.no_color and sys.stdout.isatty()
        print(result.text(color=color, verbose=not args.brief))

    # 退出码：0 成功（合律/合谱/变体/无法识别），1 存在出律，2 知识库错误。
    # 「无法识别体裁」不算错误——程序正常跑完了，只是判不出体制，
    # 不该让调用方的脚本因为它而失败。--json 与文本模式必须给出相同的码。
    if result.kind == "未知":
        return 0
    return 0 if result.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
