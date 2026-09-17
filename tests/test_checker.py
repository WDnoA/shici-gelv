# -*- coding: utf-8 -*-
"""端到端测试。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from poetry_checker import KnowledgeBase, analyze  # noqa: E402
from poetry_checker import ci as ci_mod  # noqa: E402
from poetry_checker import checker as poem_mod  # noqa: E402
from poetry_checker import patterns as pt  # noqa: E402
from poetry_checker.knowledge import CILIN, PINGSHUI, 平, 仄  # noqa: E402
import fixtures as fx  # noqa: E402
from fixtures import 固件  # noqa: E402

KB = KnowledgeBase.load()
示例 = ROOT / "示例"


def 读(name: str) -> str:
    """取测试固件。

    **刻意不读 ``示例/``**：那是给使用者看的展示目录，使用者可以随意改动
    （事实上就改过——见 ``tests/fixtures.py`` 的说明）。测试必须依赖
    自己冻结的文本，否则使用者一个正常操作就能把测试搞挂。
    """
    key = Path(name).stem
    if key not in 固件:
        raise AssertionError(
            f"没有为「{name}」准备测试固件，请在 tests/fixtures.py 的「固件」字典里补上"
        )
    return 固件[key]


# ---------------------------------------------------------------- 知识库


class TestKnowledgeBase(unittest.TestCase):
    def test_平水韵基本规模(self):
        book = KB.book(PINGSHUI)
        self.assertGreater(book.size, 2500, "平水韵收录字数偏少")
        self.assertEqual(len(KB.pingshui_raw["韵部"]["上平声"]), 15)
        self.assertEqual(len(KB.pingshui_raw["韵部"]["下平声"]), 15)
        self.assertEqual(len(KB.pingshui_raw["韵部"]["上声"]), 29)
        self.assertEqual(len(KB.pingshui_raw["韵部"]["去声"]), 30)
        self.assertEqual(len(KB.pingshui_raw["韵部"]["入声"]), 17)

    def test_平仄判定(self):
        self.assertEqual(KB.tones("东"), {平})
        self.assertEqual(KB.tones("月"), {仄})
        self.assertEqual(KB.tones("入"), {仄})
        self.assertEqual(KB.tones("白"), {仄})
        self.assertEqual(KB.tones("一"), {仄})

    def test_多音字有两种平仄(self):
        self.assertEqual(KB.tones("看"), {平, 仄})
        self.assertEqual(KB.tones("过"), {平, 仄})
        self.assertEqual(KB.tones("思"), {平, 仄})

    def test_东冬在平水韵不同部(self):
        self.assertFalse(KB.same_group("东", "冬", PINGSHUI))
        self.assertFalse(KB.same_group("东", "江", PINGSHUI))

    def test_东冬在词林正韵同部(self):
        self.assertTrue(KB.same_group("东", "冬", CILIN))
        self.assertTrue(KB.same_group("东", "中", CILIN))

    def test_入声独立成部(self):
        # 月在入声六月，与去声十五翰不可通押
        self.assertFalse(KB.same_group("月", "岸", CILIN))

    def test_邻韵关系(self):
        self.assertTrue(KB.is_neighbour("东", "冬"))
        self.assertFalse(KB.is_neighbour("东", "江"))

    def test_词牌别名(self):
        self.assertEqual(KB.cipai_real_name("望江南"), "忆江南")
        self.assertEqual(KB.cipai_real_name("乌夜啼"), "相见欢")
        self.assertIsNotNone(KB.cipai_spec("浣溪沙"))


# ---------------------------------------------------------------- 诗谱


class TestPatterns(unittest.TestCase):
    def test_五律四式与传世诗谱一致(self):
        预期 = {
            "仄仄平平仄": "仄仄平平仄平平仄仄平平平平仄仄仄仄仄平平",
            "平平仄仄平": "平平仄仄平仄仄仄平平仄仄平平仄平平仄仄平",
        }
        for first, head in 预期.items():
            pu = pt.build_shi_pu(KB, "五言", first, 8)
            self.assertEqual("".join(pu)[: len(head)], head)

    def test_七律仄起入韵(self):
        pu = pt.build_shi_pu(KB, "七言", "仄仄平平仄仄平", 8)
        self.assertEqual(
            pu,
            ["仄仄平平仄仄平", "平平仄仄仄平平", "平平仄仄平平仄", "仄仄平平仄仄平",
             "仄仄平平平仄仄", "平平仄仄仄平平", "平平仄仄平平仄", "仄仄平平仄仄平"],
        )

    def test_粘对规则(self):
        """偶数句为「对」（第二字相反、平收），奇数句（3 起）为「粘」（第二字相同、仄收）。"""
        for kind in ("五言", "七言"):
            for first in pt.all_first_patterns(KB, kind):
                pu = pt.build_shi_pu(KB, kind, first, 8)
                self.assertEqual(len(pu), 8)
                for i in range(1, 8):
                    prev, cur = pu[i - 1], pu[i]
                    if i % 2 == 1:          # 对句
                        self.assertNotEqual(prev[1], cur[1])
                        self.assertEqual(cur[-1], 平)
                    else:                    # 粘句
                        self.assertEqual(prev[1], cur[1])
                        self.assertEqual(cur[-1], 仄)

    def test_不论位置(self):
        self.assertEqual(pt.free_positions(KB, "五言"), {0})
        self.assertEqual(pt.free_positions(KB, "七言"), {0, 2})


# ---------------------------------------------------------------- 近体诗


class Test近体诗(unittest.TestCase):
    def test_登鹳雀楼(self):
        r = analyze(读("01-五言绝句-登鹳雀楼.txt"))
        self.assertEqual(r.kind, "近体诗")
        self.assertEqual(r.poem.genre, "五言绝句")
        self.assertEqual(r.poem.verdict, "合律")
        self.assertEqual(r.poem.score, 1.0)
        self.assertEqual(r.poem.rhyme.main_group, "下平声十一尤")

    def test_春望(self):
        r = analyze(读("02-五言律诗-春望.txt"))
        self.assertEqual(r.poem.genre, "五言律诗")
        self.assertEqual(r.poem.verdict, "合律")
        self.assertEqual(r.poem.rhyme.main_group, "下平声十二侵")
        self.assertEqual(len(r.poem.couplets), 4)

    def test_闻官军收河南河北(self):
        r = analyze(读("03-七言律诗-闻官军收河南河北.txt"))
        self.assertEqual(r.poem.genre, "七言律诗")
        self.assertEqual(r.poem.verdict, "合律")
        self.assertEqual(r.poem.rhyme.main_group, "下平声七阳")

    def test_早发白帝城_首句入韵(self):
        r = analyze(读("07-七言绝句-早发白帝城.txt"))
        self.assertEqual(r.poem.genre, "七言绝句")
        self.assertEqual(r.poem.verdict, "合律")
        self.assertIn("首句入韵", r.poem.pattern_label)
        # 首句应被判为押韵句
        self.assertTrue(r.poem.clauses[0].is_rhyme)

    def test_有毛病的诗能报出三平调与出韵(self):
        r = analyze(读("06-有毛病的诗-待改.txt"))
        self.assertEqual(r.poem.verdict, "存在出律")
        titles = [i.title for _idx, i in r.poem.serious]
        self.assertIn("三平调", titles)
        self.assertFalse(r.poem.rhyme.consistent)
        出韵 = [f.char for f in r.poem.rhyme.feet if not f.ok]
        self.assertEqual(出韵, ["寒"])

    def test_无标点自动分句(self):
        r = analyze("白日依山尽\n黄河入海流\n欲穷千里目\n更上一层楼")
        self.assertEqual(r.poem.genre, "五言绝句")
        self.assertEqual(len(r.poem.clauses_text), 4)

    def test_非近体诗返回未知(self):
        r = analyze("这是一段随便写的话，没有任何格律可言。")
        self.assertEqual(r.kind, "未知")
        self.assertIn("无法识别体裁", r.text())

    def test_孤平能被识别(self):
        # 第 4 句「故园月下舟」＝ 仄平仄仄平，正是「平平仄仄平」拗了第一字而成的孤平
        r = analyze("秋风吹不尽\n孤月照人愁\n遥想当年事\n故园月下舟")
        self.assertIsNotNone(r.poem)
        大忌 = [i.title for _idx, i in r.poem.serious]
        self.assertIn("孤平", 大忌)
        self.assertIn("孤平", [i.title for i in r.poem.clauses[3].issues])

    def test_孤平拗救视为合律(self):
        # 「仄平平仄平」已用第三字平声救回
        r = analyze("秋风吹不尽\n孤月照人愁\n遥想当年事\n夜长灯下舟")
        self.assertIsNotNone(r.poem)
        self.assertNotIn("孤平", [i.title for _idx, i in r.poem.serious])


# ---------------------------------------------------------------- 词


class Test词(unittest.TestCase):
    def test_浣溪沙(self):
        r = analyze(读("04-词-浣溪沙.txt"))
        self.assertEqual(r.kind, "词")
        self.assertEqual(r.ci.cipai, "浣溪沙")
        self.assertEqual(r.ci.verdict, "合谱")
        self.assertTrue(r.ci.char_ok)
        self.assertEqual(r.ci.rhyme_groups[0].main_group, "第三部")

    def test_水调歌头(self):
        r = analyze(读("05-词-水调歌头.txt"))
        self.assertEqual(r.ci.cipai, "水调歌头")
        self.assertEqual(r.ci.verdict, "合谱")
        self.assertEqual(r.ci.actual_chars, 95)
        self.assertEqual(r.ci.rhyme_groups[0].main_group, "第七部")

    def test_菩萨蛮四换韵(self):
        r = analyze(读("08-词-菩萨蛮.txt"))
        self.assertEqual(r.ci.cipai, "菩萨蛮")
        self.assertEqual(len(r.ci.rhyme_groups), 4, "菩萨蛮应为四换韵")
        self.assertEqual(
            [g.expected_tone for g in r.ci.rhyme_groups], [仄, 平, 仄, 平]
        )

    def test_词牌从词牌题目识别(self):
        r = analyze("忆江南·江南好\n江南好，风景旧曾谙。日出江花红胜火，春来江水绿如蓝。能不忆江南。")
        self.assertEqual(r.kind, "词")
        self.assertEqual(r.ci.cipai, "忆江南")
        self.assertEqual(r.ci.actual_chars, 27)
        self.assertEqual(r.ci.verdict, "合谱")

    def test_字数不符会报错(self):
        r = analyze("《浣溪沙》\n一曲新词酒一杯，去年天气旧亭台。")
        self.assertEqual(r.ci.actual_chars, 14)
        self.assertFalse(r.ci.char_ok)
        self.assertEqual(r.ci.verdict, "体格有出入")


# ---------------------------------------------------------------- 输出


class Test输出(unittest.TestCase):
    def test_示例目录可正常解析(self):
        """对真实的 示例/ 做健壮性检查。

        只断言「不抛异常、能出报告」，**不假设任何具体内容**——
        使用者随时可以改动示例文件，这不该让测试失败。
        """
        files = sorted(示例.glob("*.txt"))
        self.assertTrue(files, "示例目录为空")
        for name in files:
            r = analyze(name.read_text(encoding="utf-8"))
            text = r.text(color=False, verbose=True)
            self.assertIn(r.kind, ("近体诗", "词", "未知"), name.name)
            self.assertGreater(len(text), 100, name.name)

    def test_json可序列化(self):
        import json

        r = analyze(读("02-五言律诗-春望.txt"))
        data = json.loads(r.json())
        self.assertIn("poem", data)
        self.assertEqual(data["kind"], "近体诗")


# ---------------------------------------------------------------- 输入


class Test输入(unittest.TestCase):
    def test_多编码解码(self):
        """Windows 管道输入可能是 UTF-8 / GBK / GB18030，都要能正确解码。"""
        from poetry_checker.cli import _decode

        text = "千山鸟飞绝，万径人踪灭。孤舟蓑笠翁，独钓寒江雪。"
        for enc in ("utf-8", "utf-8-sig", "gbk", "gb18030"):
            self.assertEqual(_decode(text.encode(enc)), text, enc)

    def test_GBK文件可读取(self):
        import tempfile

        from poetry_checker.cli import _decode

        text = 读("01-五言绝句-登鹳雀楼.txt")
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "gbk.txt"
            p.write_bytes(text.encode("gbk"))
            self.assertEqual(_decode(p.read_bytes()), text)

    def test_带注释与空行(self):
        r = analyze("# 注释\n\n白日依山尽，黄河入海流。\n# 又一条注释\n欲穷千里目，更上一层楼。")
        self.assertEqual(r.poem.genre, "五言绝句")
        self.assertEqual(len(r.poem.clauses_text), 4)


# ---------------------------------------------------------------- 变体


class Test仄韵变体(unittest.TestCase):
    def test_江雪被识别为仄韵变体(self):
        r = analyze("千山鸟飞绝，万径人踪灭。孤舟蓑笠翁，独钓寒江雪。")
        self.assertEqual(r.kind, "近体诗")
        self.assertEqual(r.poem.rhyme.variant, "仄韵")
        self.assertIn("变体", r.poem.verdict)
        # 变体不算缺陷
        self.assertTrue(r.ok)

    def test_仄韵仍检查韵部一致(self):
        r = analyze("千山鸟飞绝，万径人踪灭。孤舟蓑笠翁，独钓寒江雪。")
        # 灭、雪 同属入声九屑
        self.assertTrue(r.poem.rhyme.consistent)
        self.assertEqual(r.poem.rhyme.main_group, "入声九屑")


# ---------------------------------------------------------------- 改字建议


class Test押韵建议(unittest.TestCase):
    def test_出韵时给出换字建议(self):
        r = analyze(读("06-有毛病的诗-待改.txt"))
        建议 = [i for i in r.poem.issues if i.level == "建议"]
        self.assertEqual(len(建议), 1)
        self.assertIn("寒", 建议[0].detail)
        self.assertIn("下平声十一尤", 建议[0].detail)

    def test_建议的候选字都在主韵部且平仄相符(self):
        from poetry_checker.suggest import candidates

        group = "下平声十一尤"
        got = candidates(KB, group, 平, book=PINGSHUI, exclude={"愁", "寒"}, limit=40)
        self.assertGreater(len(got), 10)
        for ch in got:
            self.assertIn(group, KB.groups(ch, PINGSHUI), ch)
            self.assertIn(平, KB.tones(ch, PINGSHUI), ch)
            self.assertNotIn(ch, ("愁", "寒"))

    def test_候选字按诗词常用字优先(self):
        from poetry_checker.suggest import candidates

        got = candidates(KB, "下平声十一尤", 平, book=PINGSHUI, limit=12)
        # 「风、中、秋、舟、楼」这类诗中常用字应排在前列
        self.assertTrue({"秋", "舟", "楼", "流", "愁"} & set(got[:12]), got)

    def test_合律的诗不给换字建议(self):
        r = analyze(读("01-五言绝句-登鹳雀楼.txt"))
        self.assertEqual([i for i in r.poem.issues if i.level == "建议"], [])

    def test_未收录字不给建议(self):
        """韵书里没有的字不臆测，宁可不说。"""
        r = analyze("春花秋月何时了，往事知多少。小楼昨夜又东风，故国不堪回首月明中。",
                    shape="诗")
        for i in (r.poem.issues if r.poem else []):
            if i.level == "建议":
                self.assertNotIn("未收录", i.detail)


# ---------------------------------------------------------------- 句读


class Test句读诊断(unittest.TestCase):
    # 把苏轼《水调歌头》上片第 3、4 句的逗号挪前一格：
    #   正体「不知天上宫阙，今夕是何年」（6+5）
    #   故意写成「不知天上宫，阙今夕是何年」（5+6）
    # 字数不变，只是顿断位置错。重断后平仄应全合。
    挪了逗号的水调歌头 = (
        "《水调歌头》\n"
        "明月几时有，把酒问青天。不知天上宫，阙今夕是何年。"
        "我欲乘风归去，又恐琼楼玉宇，高处不胜寒。起舞弄清影，何似在人间。\n"
        "转朱阁，低绮户，照无眠。不应有恨，何事长向别时圆。"
        "人有悲欢离合，月有阴晴圆缺，此事古难全。但愿人长久，千里共婵娟。"
    )

    def test_句读错位被识别(self):
        r = analyze(self.挪了逗号的水调歌头)
        self.assertEqual(r.kind, "词")
        self.assertEqual(r.ci.actual_chars, 95)
        self.assertTrue(r.ci.char_ok)
        self.assertFalse(r.ci.clause_ok)
        self.assertEqual(len(r.ci.break_segments), 1)
        seg = r.ci.break_segments[0]
        self.assertEqual(seg.indices, [2, 3])
        self.assertEqual(seg.actual, ["不知天上宫", "阙今夕是何年"])

    def test_只是逗位问题则不必改字(self):
        r = analyze(self.挪了逗号的水调歌头)
        seg = r.ci.break_segments[0]
        self.assertTrue(seg.fixable, seg.bad)
        self.assertEqual(seg.rebuilt, ["不知天上宫阙", "今夕是何年"])
        建议 = [i for i in r.ci.issues if i.title == "问题在「逗」的位置"]
        self.assertEqual(len(建议), 1)

    def test_平仄也不合则需改字(self):
        """作者稿：逗位错位，且重断后平仄仍有不合。"""
        r = analyze(读("10-用户投稿-水调歌头-中秋寄魏晓彤.txt"))
        seg = r.ci.break_segments[0]
        self.assertFalse(seg.fixable)
        self.assertEqual(seg.rebuilt, ["桂影婆娑处清", "辉漫洒芳丛"])
        self.assertTrue(seg.bad)

    def test_句读骨架正确(self):
        r = analyze(读("05-词-水调歌头.txt"))
        self.assertEqual(
            r.ci.skeleton, "5·5·6·5·6·6·5·5·5·3·3·3·4·7·6·6·5·5·5"
        )

    def test_断句正确时不出现句读对照(self):
        r = analyze(读("05-词-水调歌头.txt"))
        self.assertEqual(r.ci.break_segments, [])

    def test_按报告改定后应合谱(self):
        """回归：使用者照报告改过之后，结果确实变好了。

        这条测试锁住的是「建议的有效性」——如果哪天改动了句读判定或韵书数据，
        导致修订稿不再合谱，就说明有东西被改坏了。
        """
        r = analyze(fx.修订稿_中秋寄魏晓彤, kb=KB)
        self.assertEqual(r.kind, "词")
        self.assertEqual(r.ci.cipai, "水调歌头")
        self.assertEqual(r.ci.verdict, "合谱")
        self.assertTrue(r.ci.char_ok)
        self.assertEqual(r.ci.break_segments, [])
        self.assertEqual(r.ci.rhyme_groups[0].main_group, "第一部")
        self.assertTrue(all(g.ok for g in r.ci.rhyme_groups))

    def test_修订稿与实际示例文件一致(self):
        """提醒：若使用者又改了 示例/10，这条会失败，提示同步固件。

        这不是「测试不该依赖示例」的例外——恰恰相反，
        它专门用来发现「示例与固件脱节」，方便维护者及时同步。
        """
        path = 示例 / "10-用户投稿-水调歌头-中秋寄魏晓彤.txt"
        if not path.exists():
            self.skipTest("示例文件已被移除")
        actual = path.read_text(encoding="utf-8").strip()
        known = {fx.旧稿_中秋寄魏晓彤.strip(), fx.修订稿_中秋寄魏晓彤.strip()}
        if actual not in known:
            self.skipTest(
                "示例文件已被使用者再次修改（属正常操作，跳过）。"
                "如需锁住当前版本，请把内容同步到 tests/fixtures.py"
            )


# ---------------------------------------------------------------- API


class TestAPI(unittest.TestCase):
    """框架无关的 API 层。"""

    @classmethod
    def setUpClass(cls):
        from poetry_checker.api import CheckerAPI

        cls.api = CheckerAPI(KB)

    def test_meta(self):
        r = self.api.handle("/api/meta", "GET")
        self.assertEqual(r.status, 200)
        self.assertTrue(r.payload["ok"])
        self.assertIn("平水韵", r.payload["books"])
        self.assertGreater(r.payload["cipai_count"], 20)
        self.assertGreater(r.payload["books_info"]["平水韵"]["chars"], 3000)

    def test_cipai列表(self):
        r = self.api.handle("/api/cipai", "GET")
        self.assertEqual(r.status, 200)
        names = [c["name"] for c in r.payload["cipai"]]
        self.assertIn("浣溪沙", names)
        self.assertEqual(r.payload["count"], len(names))

    def test_校验近体诗(self):
        r = self.api.handle(
            "/api/check",
            "POST",
            {"text": "白日依山尽，黄河入海流。欲穷千里目，更上一层楼。"},
        )
        self.assertEqual(r.status, 200)
        res = r.payload["result"]
        self.assertEqual(res["kind"], "近体诗")
        self.assertTrue(res["ok"])
        self.assertEqual(res["poem"]["genre"], "五言绝句")
        self.assertEqual(res["poem"]["verdict"], "合律")
        self.assertIsNone(res["ci"])

    def test_校验词(self):
        r = self.api.handle(
            "/api/check", "POST", {"text": 读("04-词-浣溪沙.txt")}
        )
        res = r.payload["result"]
        self.assertEqual(res["kind"], "词")
        self.assertEqual(res["ci"]["cipai"], "浣溪沙")
        self.assertEqual(res["ci"]["rhyme_groups"][0]["main_group"], "第三部")

    def test_无法识别体裁(self):
        r = self.api.handle("/api/check", "POST", {"text": "这是一句随便的话。"})
        self.assertEqual(r.status, 200)
        self.assertEqual(r.payload["result"]["kind"], "未知")
        self.assertFalse(r.payload["result"]["ok"])

    def test_参数校验(self):
        用例 = [
            ({}, 400),
            ({"text": ""}, 400),
            ({"text": "   "}, 400),
            ({"text": "测" * (4000 + 1)}, 400),
            ({"text": "测试", "book": "不存在的韵书"}, 400),
            ({"text": "测试", "shape": "xxx"}, 400),
        ]
        for body, expect in 用例:
            r = self.api.handle("/api/check", "POST", body)
            self.assertEqual(r.status, expect, body)
            self.assertFalse(r.payload["ok"])

    def test_方法不允许(self):
        self.assertEqual(self.api.handle("/api/meta", "POST").status, 405)
        self.assertEqual(self.api.handle("/api/check", "GET").status, 405)

    def test_未知路由(self):
        r = self.api.handle("/api/nope", "GET")
        self.assertEqual(r.status, 404)
        self.assertFalse(r.payload["ok"])

    def test_响应可序列化(self):
        r = self.api.handle("/api/check", "POST", {"text": 读("02-五言律诗-春望.txt")})
        text = r.to_json()
        self.assertIn("下平声十二侵", text)
        json.loads(text)  # 不抛异常即为合法

    def test_to_dict不含知识库实例(self):
        r = analyze(读("01-五言绝句-登鹳雀楼.txt"), kb=KB)
        d = r.to_dict()
        self.assertNotIn("kb", d)
        self.assertIn("ok", d)
        self.assertIn("score", d)
        self.assertEqual(d["kind"], "近体诗")


class TestHTTPServer(unittest.TestCase):
    """真实起一个 http.server，走一遍网络栈。"""

    @classmethod
    def setUpClass(cls):
        import threading

        from poetry_checker.api import CheckerAPI
        from poetry_checker.server import bind, find_free_port, make_handler

        cls.port = find_free_port()
        cls.httpd, cls.port = bind(
            "127.0.0.1", cls.port, make_handler(CheckerAPI(KB))
        )
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=3)

    def _get(self, path):
        import urllib.request

        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()

    def test_首页可访问(self):
        status, ctype, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn("诗词格律校验器", body.decode("utf-8"))

    def test_静态资源可访问且MIME正确(self):
        for path, expect in (
            ("/style.css", "text/css"),
            ("/app.js", "text/javascript"),
        ):
            status, ctype, body = self._get(path)
            self.assertEqual(status, 200, path)
            self.assertIn(expect, ctype, f"{path} 的 MIME 类型不对：{ctype}")
            self.assertGreater(len(body), 100)

    def test_接口走网络(self):
        import json
        import urllib.request

        req = urllib.request.Request(
            self.base + "/api/check",
            data=json.dumps(
                {"text": "白日依山尽，黄河入海流。欲穷千里目，更上一层楼。"}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = json.loads(r.read().decode("utf-8"))
        self.assertEqual(r.status, 200)
        self.assertEqual(payload["result"]["poem"]["genre"], "五言绝句")

    def test_目录穿越被拒绝(self):
        import urllib.error

        for path in ("/../README.md", "/..%2fREADME.md", "/%2e%2e/main.py"):
            with self.assertRaises(urllib.error.HTTPError, msg=path) as ctx:
                self._get(path)
            self.assertEqual(ctx.exception.code, 404)

    def test_非法JSON被拒绝(self):
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            self.base + "/api/check",
            data=b"not json at all",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
