# -*- coding: utf-8 -*-
"""近体诗校验引擎。

流程
----
1. 推断体例（五言／七言、绝句／律诗／排律）
2. 四种首句式各生成一套诗谱，挑最贴合的一套
3. 逐句比对平仄（含拗救判定）
4. 分析押韵（平水韵）
5. 分析对仗（颔联／颈联）
6. 汇总评分与结论
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from . import duizhang as dz
from . import patterns as pt
from . import suggest
from .knowledge import KnowledgeBase, 平, 仄, PINGSHUI
from .parser import ParsedPoem, segment_by_lengths


# ---------------------------------------------------------------- 数据结构


@dataclass
class RhymeFoot:
    clause_index: int
    char: str
    groups: Set[str]
    tones: Set[str]
    is_first: bool
    ok: bool = True
    note: str = ""


@dataclass
class RhymeAnalysis:
    book: str
    feet: List[RhymeFoot] = field(default_factory=list)
    main_group: Optional[str] = None
    consistent: bool = True
    notes: List[str] = field(default_factory=list)
    variant: Optional[str] = None   # 例如「仄韵」：全篇押仄声韵，属变体


@dataclass
class CoupletResult:
    label: str            # 首联 / 颔联 / 颈联 / 尾联
    required: bool
    left_index: int
    right_index: int
    detail: Optional[dz.DuiZhangResult] = None


@dataclass
class PoemResult:
    kind: str = "近体诗"
    title: Optional[str] = None
    genre: str = ""
    pattern_label: str = ""
    pattern: List[str] = field(default_factory=list)
    clauses_text: List[str] = field(default_factory=list)
    clauses: List[pt.ClauseResult] = field(default_factory=list)
    rhyme: Optional[RhymeAnalysis] = None
    couplets: List[CoupletResult] = field(default_factory=list)
    issues: List[pt.Issue] = field(default_factory=list)
    score: float = 0.0
    verdict: str = ""
    book: str = PINGSHUI
    shape_note: str = ""

    @property
    def all_violations(self) -> List[Tuple[int, pt.CharResult]]:
        out = []
        for cl in self.clauses:
            for c in cl.violations:
                out.append((cl.index, c))
        return out

    @property
    def all_unknown(self) -> List[Tuple[int, pt.CharResult]]:
        out = []
        for cl in self.clauses:
            for c in cl.unknown:
                out.append((cl.index, c))
        return out

    @property
    def coverage(self) -> Tuple[int, int]:
        """(已判定字数, 总字数)。符合度只在这些字上成立。"""
        return pt.coverage_stats(self.clauses)

    @property
    def serious(self) -> List[Tuple[int, pt.Issue]]:
        out = []
        for cl in self.clauses:
            for i in cl.serious_issues:
                out.append((cl.index, i))
        out.extend((0, i) for i in self.issues if i.level == "错误")
        return out


# ---------------------------------------------------------------- 体例推断


def _genre_name(kind: str, n: int) -> str:
    if n == 4:
        return f"{kind}绝句"
    if n == 8:
        return f"{kind}律诗"
    if n >= 10 and n % 2 == 0:
        return f"{kind}排律"
    return f"{kind}（{n} 句，非常规体制）"


def infer_shape(parsed: ParsedPoem) -> Optional[Tuple[str, List[str], int]]:
    """推断 (五言/七言, 分句列表, 句数)。无法判断时返回 None。"""
    L = parsed.uniform_length()
    clauses = parsed.clauses
    if L in (5, 7) and clauses and len(clauses) >= 4 and len(clauses) % 2 == 0:
        kind = "五言" if L == 5 else "七言"
        return kind, list(clauses), len(clauses)

    # 回退：按总字数重切（用户在行内漏打标点时的兜底）
    text = parsed.chars
    for cand_kind, cand_len in (("七言", 7), ("五言", 5)):
        if text and len(text) % cand_len == 0:
            n = len(text) // cand_len
            if n >= 4 and n % 2 == 0:
                seg = segment_by_lengths(text, [cand_len] * n)
                if seg:
                    return cand_kind, seg, n
    return None


# ---------------------------------------------------------------- 主入口


def check(kb: KnowledgeBase, parsed: ParsedPoem, book: str = PINGSHUI) -> Optional[PoemResult]:
    """校验一首近体诗。若不像近体诗则返回 None（交由词校验器处理）。"""
    shape = infer_shape(parsed)
    if shape is None:
        return None
    kind, clauses_text, n = shape

    if kb.rhyme_books.get(book) is None:
        kb.book(book)

    res = PoemResult(
        title=parsed.title,
        genre=_genre_name(kind, n),
        clauses_text=clauses_text,
        book=book,
        shape_note="（正文缺少标点，已按每句 %d 字自动分句）" % len(clauses_text[0])
        if not parsed.clauses or len(parsed.clauses) != n
        else "",
    )

    # ---- 1. 四种首句式各试一遍，取最贴合者
    best: Optional[Tuple[float, str, List[str], List[pt.ClauseResult]]] = None
    for first in pt.all_first_patterns(kb, kind):
        pu = pt.build_shi_pu(kb, kind, first, n)
        cl = [
            pt.compare_clause(kb, t, p, i, book, rhythm_friendly=True)
            for i, (t, p) in enumerate(zip(clauses_text, pu))
        ]
        s = pt.score_clauses(cl)
        # 平手时优先「首句不入韵」的常见格式
        tiebreak = 0.001 if first.endswith(仄) else 0.0
        cand = (s + tiebreak, first, pu, cl)
        if best is None or cand[0] > best[0]:
            best = cand

    assert best is not None
    _, first_pattern, pattern, clause_results = best
    res.pattern = pattern
    res.clauses = clause_results

    entry = pt.entry_of(kb, kind, first_pattern)
    押 = "首句入韵" if entry.get("入韵") else "首句不入韵"
    res.pattern_label = f"{entry['名']}·{押}"

    # ---- 2. 韵脚与押韵
    res.rhyme = analyze_rhyme(kb, res, book)

    # ---- 3. 对仗
    res.couplets = analyze_couplets(kb, res, book)

    # ---- 4. 评分与结论
    res.score = pt.score_clauses(clause_results)
    res.issues.extend(_global_issues(kb, res))
    res.verdict = _verdict(res)
    return res


# ---------------------------------------------------------------- 押韵


def analyze_rhyme(kb: KnowledgeBase, res: PoemResult, book: str) -> RhymeAnalysis:
    ra = RhymeAnalysis(book=book)
    for idx, (text, cl) in enumerate(zip(res.clauses_text, res.clauses)):
        if not cl.is_rhyme or not text:
            continue
        ch = text[-1]
        ra.feet.append(
            RhymeFoot(
                clause_index=idx,
                char=ch,
                groups=kb.groups(ch, book),
                tones=kb.tones(ch, book),
                is_first=(idx == 0),
            )
        )

    if not ra.feet:
        ra.consistent = False
        ra.notes.append("未找到押韵句（平收句），请确认是否为押仄韵的变体诗。")
        return ra

    if len(ra.feet) == 1:
        ra.notes.append("全诗只有一个韵脚，无法判断押韵是否一致。")
        return ra

    # ---- 主韵：从非首句的韵脚中统计
    counter: Counter = Counter()
    for f in ra.feet:
        if f.is_first:
            continue
        for g in f.groups:
            counter[g] += 1
    if not counter:                       # 首句是唯一可用样本
        for g in ra.feet[0].groups:
            counter[g] += 1
    ra.main_group = counter.most_common(1)[0][0] if counter else None

    # ---- 逐韵脚检查
    seen: Dict[str, int] = {}
    for f in ra.feet:
        if not f.groups:
            f.ok = False
            f.note = f"「{f.char}」不在韵书（{book}）中，请人工核对"
            ra.consistent = False
            continue
        if ra.main_group and ra.main_group in f.groups:
            f.ok = True
        elif f.is_first and any(
            kb.rhyme_neighbours.get(ra.main_group, set()) & f.groups for _ in (0,)
        ):
            f.ok = True
            f.note = "首句借邻韵（借韵），传统允许"
        else:
            f.ok = False
            f.note = "出韵"
            ra.consistent = False
        seen[f.char] = seen.get(f.char, 0) + 1

    repeats = [c for c, k in seen.items() if k > 1]
    if repeats:
        ra.consistent = False
        ra.notes.append(f"韵脚重字：{'、'.join(repeats)}（近体诗忌重韵）")

    # ---- 仄韵变体提示
    ping_feet = sum(1 for f in ra.feet if 平 in f.tones and 仄 not in f.tones)
    if ping_feet == 0 and all(仄 in f.tones for f in ra.feet):
        ra.variant = "仄韵"
        ra.notes.append(
            "全诗韵脚均为仄声，属「仄韵诗」变体（如柳宗元《江雪》）。"
            "近体诗以押平声韵为正，本工具按平韵体制套谱，"
            "故下面的平仄对照与符合度仅供参考，请以「是否押同一仄声韵部」为准。"
        )
    return ra


# ---------------------------------------------------------------- 对仗


def analyze_couplets(kb: KnowledgeBase, res: PoemResult, book: str) -> List[CoupletResult]:
    n = len(res.clauses_text)
    out: List[CoupletResult] = []
    if n >= 8:
        spec = [(0, "首联", False), (2, "颔联", True), (4, "颈联", True), (6, "尾联", False)]
    else:
        spec = [(0, "首联", False), (2, "次联", False)]
    for start, label, required in spec:
        if start + 1 >= n:
            continue
        cr = CoupletResult(
            label=label, required=required, left_index=start, right_index=start + 1
        )
        cr.detail = dz.analyze(
            kb,
            res.clauses_text[start],
            res.clauses_text[start + 1],
            book=book,
            strict_tone=True,
        )
        out.append(cr)
    return out


# ---------------------------------------------------------------- 全局问题


def _global_issues(kb: KnowledgeBase, res: PoemResult) -> List[pt.Issue]:
    issues: List[pt.Issue] = []
    unknown = res.all_unknown
    if unknown:
        chars = "".join(sorted({c.char for _, c in unknown}))
        issues.append(
            pt.Issue(
                "提示",
                "韵书未收录",
                f"以下字不在平水韵数据中，未参与平仄判定：{chars}。"
                "请查证后补充到 知识库/韵书/平水韵.json。",
            )
        )

    ra = res.rhyme
    if ra and not ra.consistent:
        issues.append(pt.Issue("错误", "押韵问题", "韵脚未全部落在同一韵部，详见押韵分析。"))
        # 换字建议：只在「押平韵的正体」下给，仄韵变体不知目标韵部，不臆测
        if ra.variant is None and ra.main_group:
            need_tone = 平
            used = [f.char for f in ra.feet]
            for f in ra.feet:
                if f.ok or not f.groups:
                    continue
                issues.append(
                    pt.Issue(
                        "建议",
                        "押韵换字建议",
                        suggest.rhyme_fix(kb, f.char, ra.main_group, need_tone, used, res.book),
                    )
                )

    bad_couplets = [c for c in res.couplets if c.required and c.detail and c.detail.verdict == "平仄失对"]
    if bad_couplets:
        names = "、".join(c.label for c in bad_couplets)
        issues.append(pt.Issue("错误", "对仗失对", f"{names}要求对仗，但出句与对句平仄不相对。"))
    return issues


def _verdict(res: PoemResult) -> str:
    rhythm = res.rhyme
    # 仄韵诗是变体，本工具的平韵诗谱套不上，不宜按「出律」苛责
    if rhythm and rhythm.variant == "仄韵":
        return "仄韵诗体（变体）· 平仄仅供参考"
    serious = len(res.serious)
    viol = len(res.all_violations)
    rhyme_ok = rhythm.consistent if rhythm else False
    if viol == 0 and serious == 0 and rhyme_ok:
        return "合律"
    if viol <= 2 and serious == 0 and rhyme_ok:
        return "基本合律"
    if viol == 0 and serious == 0:
        return "平仄合律，押韵待酌"
    return "存在出律"
