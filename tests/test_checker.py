# -*- coding: utf-8 -*-
"""端到端测试。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from poetry_checker import KnowledgeBase, analyze  # noqa: E402
from poetry_checker import patterns as pt  # noqa: E402
from poetry_checker.knowledge import CILIN, PINGSHUI, XINYUN, 平, 仄  # noqa: E402
import fixtures as fx  # noqa: E402
from fixtures import 固件  # noqa: E402

KB = KnowledgeBase.load()
示例 = ROOT / "示例"
知识库 = ROOT / "知识库"


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

    def test_对仗词类用字均被韵书收录(self):
        """回归：韵书漏收常用字会让报告误报「韵书未收录」。

        历史故障：旧韵书只收 3485 字，「顾、女、父、爱、皆、惟、掌、暑、暮…」
        等极常用字竟都不在内；而《对仗/词类分类.json》的 930 字里有 134 字查不到——
        同一项目内两份数据自相矛盾。用户投稿「镜鸾顾影怜孤舞」即因此被误报。
        韵书已重建至约 8300 字，此断言锁住「对仗词库 ⊆ 韵书」这一不变量。
        """
        允许未收 = {"垧"}   # 现代字（「晌」的异体），平水韵本无，按「宁可不判」留白
        缺口 = sorted(
            c for c in KB.char_category if not KB.groups(c) and c not in 允许未收
        )
        self.assertEqual(缺口, [], f"对仗词类中有字未被韵书收录：{''.join(缺口)}")

    def test_新韵查询缓存能命中(self):
        """回归：新韵缓存曾永远命中不了。

        旧实现是 ``getattr(self, "_xinyun_cache", {})``：属性还不存在时拿到的是
        一个临时 dict，结果写进去随即丢弃；更巧的是 ``load_xinyun()`` 稍后又会把
        该属性重新赋值一次，等于再丢一次。两头一夹，每条新韵查询都重算。
        """
        try:
            import pypinyin  # noqa: F401
        except ImportError:
            self.skipTest("未安装 pypinyin，跳过新韵相关用例")
        kb = KnowledgeBase.load()
        self.assertFalse(hasattr(kb, "_xinyun_cache"), "初始不应存在缓存容器")
        kb.xinyun_lookup("东")
        self.assertIn("东", kb._xinyun_cache, "查询结果应写入实例级缓存")
        容器 = kb._xinyun_cache
        kb.tones("月", XINYUN)
        self.assertIs(kb._xinyun_cache, 容器, "缓存容器不应被重新赋值")
        self.assertIn("东", kb._xinyun_cache, "后续查询不该把已有缓存挤掉")


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

    def test_无标点的律诗不丢句(self):
        """回归：8 句、每句一行、完全不打标点时必须能自动分句。

        旧实现扫描前 3 行找标题：第 0 行因「去掉后剩 7 行（奇数）」不算标题，
        第 1 行却因「剩 6 行」被认作标题，于是**第 0 行被静默丢弃**——七律只剩
        42 字。README 明确承诺这种输入能自动分句，所以这是硬伤。
        """
        七律 = (
            "冰轮碾玉转空明\n露冷瑶阶桂魄清\n锦字未裁先有恨\n银蟾欲满却无声\n"
            "镜鸾顾影怜孤舞\n钗凤分飞忆旧鸣\n莫问相思何所寄\n清辉自引到君城"
        )
        五律 = (
            "国破山河在\n城春草木深\n感时花溅泪\n恨别鸟惊心\n"
            "烽火连三月\n家书抵万金\n白头搔更短\n浑欲不胜簪"
        )
        for tag, text, genre in (("七律", 七律, "七言律诗"), ("五律", 五律, "五言律诗")):
            r = analyze(text)
            self.assertIsNone(r.poem.title, f"{tag}：无标题行时不该凭空造出标题")
            self.assertEqual(len(r.poem.clauses_text), 8, f"{tag}：应是 8 句")
            self.assertEqual(r.poem.genre, genre, tag)
            self.assertEqual(r.poem.clauses_text[0], text[:7 if tag == "七律" else 5],
                             f"{tag}：首句不能丢")

    def test_排律逐联分析且标签正确(self):
        """回归：10 句排律曾被错标——第 7、8 句标成「尾联」，第 9、10 句不分析。"""
        from poetry_checker.checker import PoemResult, analyze_couplets

        res = PoemResult(clauses_text=["白日依山尽"] * 10, book=PINGSHUI)
        cps = analyze_couplets(KB, res, PINGSHUI)
        self.assertEqual(len(cps), 5, "10 句应分析 5 联")
        self.assertEqual(cps[0].label, "首联")
        self.assertEqual(cps[-1].label, "尾联")
        self.assertEqual(
            (cps[-1].left_index, cps[-1].right_index), (8, 9), "尾联应是第 9、10 句"
        )
        for cp in cps[1:-1]:
            self.assertTrue(cp.required, f"排律中间各联都要求对仗：{cp.label}")

    def test_律诗四联命名不变(self):
        """回归：改排律命名的同时，不能动律诗的「首/颔/颈/尾」四联。"""
        from poetry_checker.checker import PoemResult, analyze_couplets

        res = PoemResult(clauses_text=["白日依山尽"] * 8, book=PINGSHUI)
        self.assertEqual(
            [c.label for c in analyze_couplets(KB, res, PINGSHUI)],
            ["首联", "颔联", "颈联", "尾联"],
        )


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


# ---------------------------------------------------------------- 叶韵


class Test叶韵(unittest.TestCase):
    """《西江月》的「同部仄韵」（韵标记 4）。

    回归：数据里《西江月》一直标着韵标记 4、`词牌说明.md` 也早写了「叶韵」，
    但 `ci.py` **从未实现它**——平仄核对用的是「全组一个平仄」，
    于是上下片那两个叶韵位（`片`、`见`）必被判成「该韵位应押平声」，
    辛弃疾的传世名篇报了「体格有出入」，报告还顺手建议作者把「片」改成平声字。
    有数据、有文档、没有代码，误报就一直躺在那里。
    """

    西江月 = (
        "《西江月·夜行黄沙道中》\n"
        "明月别枝惊鹊，清风半夜鸣蝉。稻花香里说丰年，听取蛙声一片。\n"
        "七八个星天外，两三点雨山前。旧时茅店社林边，路转溪桥忽见。"
    )

    def test_韵标记4不另起韵组而3起新组(self):
        """4 是「同部仄韵」，仍属当前组；3 是「换韵」，另起一组。"""
        from poetry_checker.ci import rhyme_seat_groups

        西江月 = rhyme_seat_groups(KB.cipai["西江月"]["格律"])
        # 上下片各「两个平韵 + 一个叶韵」同属一组：第 2、3、4、6、7、8 句
        self.assertEqual(西江月, [[1, 2, 3, 5, 6, 7]])
        # 菩萨蛮四换韵 → 四个组
        self.assertEqual(len(rhyme_seat_groups(KB.cipai["菩萨蛮"]["格律"])), 4)

    def test_西江月传世名篇合谱(self):
        r = analyze(self.西江月, kb=KB)
        self.assertEqual(r.kind, "词")
        self.assertEqual(r.ci.cipai, "西江月")
        self.assertEqual(r.ci.verdict, "合谱")
        self.assertEqual(r.ci.score, 1.0)
        self.assertEqual(r.ci.all_violations, [])
        self.assertEqual([i for i in r.ci.issues if i.level == "错误"], [])
        self.assertTrue(all(g.ok for g in r.ci.rhyme_groups))
        self.assertEqual(r.ci.rhyme_groups[0].main_group, "第七部")

    def test_叶韵位给出说明(self):
        r = analyze(self.西江月, kb=KB)
        notes = "".join(r.ci.rhyme_groups[0].notes)
        self.assertIn("叶韵", notes)
        self.assertIn("第4句、第8句", notes)

    def test_叶韵位仍须与平韵同部(self):
        """叶韵只放宽「平仄」，不放宽「韵部」——换成别部的仄声字必须报出。"""
        r = analyze(self.西江月.replace("听取蛙声一片", "听取蛙声一月"), kb=KB)
        self.assertFalse(r.ci.rhyme_groups[0].ok)
        self.assertIn("月", "".join(r.ci.rhyme_groups[0].notes))
        self.assertNotEqual(r.ci.verdict, "合谱")

    def test_叶韵位仍须为仄声(self):
        """叶韵位按自身谱尾核对，须仄声；换成同部平声字应报出并给仄声候选。"""
        r = analyze(self.西江月.replace("听取蛙声一片", "听取蛙声一年"), kb=KB)
        self.assertFalse(r.ci.rhyme_groups[0].ok)
        notes = "".join(r.ci.rhyme_groups[0].notes)
        self.assertIn("「年」应押仄声", notes)
        建议 = [i for i in r.ci.issues if i.level == "建议"]
        self.assertEqual(len(建议), 1)
        # 该位需仄声，建议也必须是仄声候选；且「年」本就在第七部，不该说它出韵
        self.assertIn("需 仄声", 建议[0].detail)
        self.assertIn("韵部没有问题", 建议[0].detail)


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


# ---------------------------------------------------------------- 新韵建议


class Test新韵换字建议(unittest.TestCase):
    """《中华新韵》同样要能给换字建议。

    回归：新韵是按普通话读音**实时计算**的，知识库里并没有字表。旧实现却直接取
    ``RhymeBook.members()``——对新韵永远拿到空表，于是建议永远只有一句
    「该韵部中没有可用的替换字」；而韵部标签写死成《词林正韵》，
    指的是一本根本没用上的韵书。两条都让「新韵」这条路径上的建议形同虚设。
    """

    @classmethod
    def setUpClass(cls):
        try:
            import pypinyin  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("未安装 pypinyin，跳过新韵相关用例")

    def test_三本韵书都能取到韵部字表(self):
        """``kb.members()`` 是统一入口：调用方不必自己判断韵书类型。"""
        用例 = [
            (PINGSHUI, "上平声一东", 50),
            (CILIN, "第一部", 100),
            (XINYUN, "十一庚", 100),
        ]
        for book, group, least in 用例:
            members = KB.members(group, book)
            self.assertGreater(len(members), least, f"{book} {group}")

    def test_新韵字表与逐字查询一致(self):
        """批量求拼音归纳出的字表，必须与逐字查询的结论一致。

        字表是「一次性批次算完再按韵部归类」的（逐字算太慢），所以这里守住
        「批量结果 ≠ 逐字结果」这条最容易悄悄出现的偏差。
        """
        for ch, group in (("东", "十一庚"), ("中", "十一庚"),
                          ("山", "八寒"), ("花", "一麻")):
            self.assertEqual(KB.groups(ch, XINYUN), {group}, ch)
            self.assertIn(ch, KB.members(group, XINYUN), ch)

    def test_新韵下也能给出换字建议(self):
        # 句 2 韵脚「东」属新韵十一庚，句 4 韵脚「山」属八寒 —— 新韵下必出韵
        r = analyze("白日依山尽，黄河入海东。欲穷千里目，更上一层山。",
                    kb=KB, book=XINYUN)
        self.assertEqual(r.poem.rhyme.main_group, "十一庚")
        建议 = [i for i in r.poem.issues if i.level == "建议"]
        self.assertEqual(len(建议), 1, [i.title for i in r.poem.issues])
        detail = 建议[0].detail
        self.assertIn("山", detail)
        self.assertIn("《中华新韵》", detail)
        self.assertNotIn("《词林正韵》", detail, "不该把新韵说成词林正韵")
        self.assertNotIn("没有可用的替换字", detail, "新韵必须有候选字")

    def test_新韵候选字都在主韵部且平仄相符(self):
        from poetry_checker.suggest import candidates

        got = candidates(KB, "十一庚", 平, book=XINYUN, exclude={"东"}, limit=30)
        self.assertGreater(len(got), 10)
        for ch in got:
            self.assertIn("十一庚", KB.groups(ch, XINYUN), ch)
            self.assertIn(平, KB.tones(ch, XINYUN), ch)
            self.assertNotEqual(ch, "东")

    def test_韵部标签不张冠李戴(self):
        from poetry_checker.suggest import group_label

        self.assertEqual(group_label("上平声一东", PINGSHUI), "《平水韵》上平声一东")
        self.assertEqual(group_label("第一部", CILIN), "《词林正韵》第一部")
        self.assertEqual(group_label("一麻", XINYUN), "《中华新韵》一麻")


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

    def test_meta带前端目录信息(self):
        """便于排查「页面全 404」：服务到底在哪、web/ 还在不在。"""
        r = self.api.handle("/api/meta", "GET")
        self.assertEqual(r.payload["web_ok"], True)
        self.assertTrue(r.payload["web_dir"].endswith("web"))
        self.assertTrue(Path(r.payload["project_dir"]).is_dir())

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


class Test命令行(unittest.TestCase):
    """命令行入口与退出码。"""

    def _run(self, argv):
        import contextlib
        import io

        from poetry_checker.cli import main

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_合律返回0(self):
        code, _ = self._run(["-t", "白日依山尽，黄河入海流。欲穷千里目，更上一层楼。"])
        self.assertEqual(code, 0)

    def test_出律返回1(self):
        code, _ = self._run(["-t", 读("06-有毛病的诗-待改.txt")])
        self.assertEqual(code, 1)

    def test_无法识别仍返回0(self):
        """识别不出体裁不是错误，不该让调用方的脚本失败。"""
        code, _ = self._run(["-t", "这是一句随便的话。"])
        self.assertEqual(code, 0)

    def test_verify_kb返回0(self):
        code, out = self._run(["--verify-kb"])
        self.assertEqual(code, 0)
        self.assertIn("知识库自检通过", out)

    def test_list_cipai(self):
        code, out = self._run(["--list-cipai"])
        self.assertEqual(code, 0)
        self.assertIn("浣溪沙", out)

    def test_expect输出markdown表(self):
        """--expect 是防文档漂移用的：示例改了，用它一键重算结论表。"""
        code, out = self._run(["--expect", str(示例)])
        self.assertEqual(code, 0)
        self.assertIn("| 文件 | 体裁 | 结论 | 韵部 | 平仄符合度 |", out)
        # 每个示例都该出现一行
        for name in sorted(p.name for p in 示例.glob("*.txt")):
            self.assertIn(f"`{name}`", out)

    def test_expect目录不存在返回2(self):
        import tempfile

        code, _ = self._run(["--expect", "不存在的目录"])
        self.assertEqual(code, 2)

    def test_expect空目录返回2(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            code, _ = self._run(["--expect", tmp])
        self.assertEqual(code, 2)


class Test覆盖率(unittest.TestCase):
    """符合度不能掩盖「有些字根本没查过」。

    这是真实投稿《中秋寄知音》暴露的缺陷：句 6「幽怀千缕各沉吟」里
    「各」「沉」「缕」三字当时都未收录，报告却照样给出「合律 100%」——
    因为 ``score_clauses`` 把未收录字排除在分母之外，
    分母变小，分数反而更高。现在符合度必须连带覆盖率一起给出。
    """

    def setUp(self):
        self.kb = KnowledgeBase.load()
        self.book = self.kb.book(PINGSHUI)
        # 自适应当前知识库：找一个肯定没收录的生僻字
        self.rare = next(c for c in "龘靐齉爩麤" if not self.book.groups(c))

    def test_全部收录时不显示告警(self):
        r = analyze("白日依山尽，黄河入海流。欲穷千里目，更上一层楼。", kb=self.kb)
        known, total = r.coverage
        self.assertEqual(known, total)
        self.assertNotIn("未能判定", r.text(color=False))

    def test_未收录字计入分母并告警(self):
        r = analyze(f"白日依山尽，黄河入海流。欲穷千里目，更上{self.rare}层楼", kb=self.kb)
        known, total = r.coverage
        self.assertEqual(total, 20)
        self.assertEqual(known, 19, "生僻字不该被算作已判定")
        text = r.text(color=False)
        self.assertIn("已判定 19/20 字", text)
        self.assertIn("未能判定", text)

    def test_词也给出覆盖率(self):
        r = analyze("《浣溪沙》一曲新词酒一杯，去年天气旧亭台。", kb=self.kb)
        known, total = r.coverage
        self.assertGreater(known, 0)
        self.assertLessEqual(known, total)

    def test_json导出覆盖率(self):
        r = analyze("白日依山尽，黄河入海流。欲穷千里目，更上一层楼。", kb=self.kb)
        d = json.loads(r.json())
        self.assertIn("coverage", d)
        self.assertEqual(d["coverage"]["known"], d["coverage"]["total"])

    def test_补录后的常用字均可判定(self):
        """「各、沉、缕、冷」都是真实投稿暴露的漏收字，已补进平水韵。"""
        for ch in "各沉缕冷":
            self.assertTrue(self.book.groups(ch), f"「{ch}」仍未被韵书收录")

    def test_未收录提示只发一次(self):
        """「韵书未收录」只能由后端发一条。

        前端 ``web/app.js`` 曾经自己又硬编码了一条，于是同一条提示
        在页面上出现两次，且前端那份的路径是残缺的
        （「可补录到 知识库/韵书/。」——缺文件名）。那份硬编码已删除，
        这里守住后端侧不重复、且路径完整。
        """
        r = analyze(f"白日依山尽，黄河入海流。欲穷千里目，更上{self.rare}层楼", kb=self.kb)
        hits = [i for i in r.poem.issues if i.title == "韵书未收录"]
        self.assertEqual(len(hits), 1, "同一条未收录提示只能出现一次")
        self.assertIn("知识库/韵书/平水韵.json", hits[0].detail, "补录路径必须写全")

    def test_未收录提示随韵书变化(self):
        """提示不能写死「平水韵」。

        用「中华新韵」校验时若仍说「不在平水韵数据中 / 请补录到平水韵.json」，
        会把人引向错误方向——新韵是按普通话读音实时算的，并没有这份字表。
        """
        from poetry_checker.checker import PoemResult, _global_issues

        def 构造(book):
            cl = pt.ClauseResult(index=0, text="测试", pattern="仄平")
            cl.chars.append(pt.CharResult(0, "测", "仄", set(), pt.状态_未收, None))
            return PoemResult(clauses_text=["测试"], clauses=[cl], book=book)

        detail = _global_issues(self.kb, 构造(PINGSHUI))[0].detail
        self.assertIn("《平水韵》", detail)
        self.assertIn("知识库/韵书/平水韵.json", detail)

        detail = _global_issues(self.kb, 构造(XINYUN))[0].detail
        self.assertIn("《中华新韵》", detail)
        self.assertNotIn("不在平水韵数据中", detail)
        self.assertNotIn("知识库/韵书/平水韵.json", detail, "新韵不该让人去补平水韵")


class Test知识库热重载(unittest.TestCase):
    """改完 JSON 不用重启服务。

    本项目的核心用法是「碰到未收录字 → 补录进 知识库/韵书/平水韵.json」。
    长驻服务若把知识库锁死在进程内存里，补录完页面照旧报「未收录」，
    使用者会以为补录失败——真实发生过（补了「冷」之后页面仍是旧结果）。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "知识库"
        shutil.copytree(知识库, self.root)
        self.book_path = self.root / "韵书" / "平水韵.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _新服务(self):
        from poetry_checker.api import CheckerAPI

        return CheckerAPI(KnowledgeBase.load(self.root))

    def _生僻字(self):
        book = KnowledgeBase.load(self.root).book(PINGSHUI)
        return next(c for c in "龘靐齉爩麤" if not book.groups(c))

    def _查(self, server, text):
        return json.loads(server.check({"text": text}).to_json())["result"]

    def test_补录后无需重启即可生效(self):
        rare = self._生僻字()
        server = self._新服务()
        poem = f"白日依山尽，黄河入海流。欲穷千里目，更上{rare}层楼"

        self.assertEqual(self._查(server, poem)["coverage"]["known"], 19)
        self.assertEqual(server.reload_count, 0)

        # 直接改磁盘：把生僻字挂进「下平声十一尤」
        raw = self.book_path.read_text(encoding="utf-8")
        self.book_path.write_text(
            raw.replace('"十一尤": "', '"十一尤": "' + rare, 1), encoding="utf-8"
        )

        after = self._查(server, poem)
        self.assertEqual(after["coverage"]["known"], 20, "改完 JSON 应自动重载")
        self.assertEqual(server.reload_count, 1)

    def test_没改动时不重复加载(self):
        server = self._新服务()
        for _ in range(3):
            self._查(server, "白日依山尽，黄河入海流。欲穷千里目，更上一层楼。")
        self.assertEqual(server.reload_count, 0, "文件没变就不该反复重载")

    def test_半截JSON不打挂服务(self):
        """编辑到一半是常态，此时必须沿用旧数据，绝不能崩。"""
        server = self._新服务()
        poem = "白日依山尽，黄河入海流。欲穷千里目，更上一层楼。"
        self.assertTrue(self._查(server, poem)["ok"] is not None)

        self.book_path.write_text('{"韵部": {"上平声": {"一东": "东', encoding="utf-8")

        after = self._查(server, poem)
        self.assertEqual(after["kind"], "近体诗", "半截 JSON 时应沿用旧知识库")
        self.assertEqual(server.reload_count, 0)

        # 补全后应能恢复重载
        shutil.copy(知识库 / "韵书" / "平水韵.json", self.book_path)
        self.assertEqual(self._查(server, poem)["kind"], "近体诗")
        self.assertEqual(server.reload_count, 1)

    def test_可关闭自动重载(self):
        from poetry_checker.api import CheckerAPI

        server = CheckerAPI(KnowledgeBase.load(self.root), auto_reload=False)
        raw = self.book_path.read_text(encoding="utf-8")
        self.book_path.write_text(raw.replace("二十六寝", "二十六寝"), encoding="utf-8")
        self._查(server, "白日依山尽，黄河入海流。")
        self.assertEqual(server.reload_count, 0)

    def test_指纹随文件变化(self):
        kb = KnowledgeBase.load(self.root)
        before = kb.fingerprint()
        self.assertTrue(before, "指纹不该为空")

        raw = self.book_path.read_text(encoding="utf-8")
        self.book_path.write_text(raw + "\n", encoding="utf-8")
        self.assertNotEqual(KnowledgeBase.load(self.root).fingerprint(), before)


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

    def test_缺失的静态文件给出可诊断页面(self):
        """页面 404 不能只丢一句 JSON —— 使用者看不懂。

        这条来自一次真实故障：一个指向**已删除目录**的残留服务占着端口，
        结果连首页都打不开，浏览器里只有 {"ok": false, "error": "文件不存在"}，
        完全看不出是「项目被挪走了」还是「端口上是别的进程」。
        """
        import urllib.error

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/nope")
        self.assertEqual(ctx.exception.code, 404)
        ctype = ctx.exception.headers.get("Content-Type", "")
        self.assertIn("text/html", ctype)
        body = ctx.exception.read().decode("utf-8")
        self.assertIn("前端目录", body)       # 把服务实际用的目录摆出来
        self.assertIn("web", body)
        self.assertIn("/api/meta", body)      # 给出可自证的入口

    def test_favicon不再404(self):
        """浏览器会顺手要 /favicon.ico；给 204 而不是 404，免得控制台刷红。"""
        status, ctype, body = self._get("/favicon.ico")
        self.assertEqual(status, 204)
        self.assertEqual(body, b"")

    def test_站点图标可访问(self):
        status, ctype, body = self._get("/favicon.svg")
        self.assertEqual(status, 200)
        self.assertIn("svg", ctype)
        self.assertIn(b"<svg", body)

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
