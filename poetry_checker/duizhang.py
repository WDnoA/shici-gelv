# -*- coding: utf-8 -*-
"""对仗辅助分析。

程序**无法**判断「合掌」「流水对」「意境高下」，这些必须人工判断。
它能做的是：按节奏点切分、标出每位的词类、检查平仄是否相对、找出重字。
结论一律标为「参考」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set

from .knowledge import KnowledgeBase, 平, 仄


def rhythm_segments(n: int) -> List[int]:
    """按传统节奏切分：五言 2-2-1，七言 2-2-2-1，九言 2-2-2-2-1。"""
    if n <= 1:
        return [n]
    if n % 2 == 0:
        return [2] * (n // 2)
    segs = [2] * ((n - 1) // 2)
    segs.append(1)
    return segs


@dataclass
class SegmentPair:
    index: int
    left: str
    right: str
    left_cats: Set[str]
    right_cats: Set[str]

    @property
    def shared(self) -> Set[str]:
        return self.left_cats & self.right_cats

    def describe(self) -> str:
        def label(cats: Set[str]) -> str:
            return "/".join(sorted(cats)) if cats else "（未归类）"

        mark = "○" if self.shared else "×"
        return f"{mark} {self.left}〔{label(self.left_cats)}〕 — {self.right}〔{label(self.right_cats)}〕"


@dataclass
class DuiZhangResult:
    left: str
    right: str
    segments: List[SegmentPair] = field(default_factory=list)
    repeated: List[str] = field(default_factory=list)
    tone_opposite: Optional[bool] = None
    verdict: str = "参考"
    notes: List[str] = field(default_factory=list)

    @property
    def matched(self) -> int:
        return sum(1 for s in self.segments if s.shared)

    @property
    def total(self) -> int:
        return len(self.segments)


def analyze(
    kb: KnowledgeBase,
    left: str,
    right: str,
    book: str = "平水韵",
    strict_tone: bool = True,
) -> Optional[DuiZhangResult]:
    """分析两句是否构成对仗。字数不等时返回 None。"""
    if not left or not right or len(left) != len(right):
        return None

    res = DuiZhangResult(left=left, right=right)

    segs = rhythm_segments(len(left))
    pos = 0
    for si, size in enumerate(segs):
        lseg = left[pos : pos + size]
        rseg = right[pos : pos + size]
        pos += size
        res.segments.append(
            SegmentPair(
                index=si,
                left=lseg,
                right=rseg,
                left_cats=_cats(kb, lseg),
                right_cats=_cats(kb, rseg),
            )
        )

    # ---- 重字
    common = sorted(set(left) & set(right))
    res.repeated = common

    # ---- 平仄相对（以第二字为准）
    if len(left) >= 2:
        lt = _tone_of(kb, left[1], book)
        rt = _tone_of(kb, right[1], book)
        if lt and rt:
            res.tone_opposite = lt != rt

    # ---- 结论
    if strict_tone and res.tone_opposite is False:
        res.verdict = "平仄失对"
    elif res.repeated:
        res.verdict = "有重字"
    elif res.total and res.matched == res.total:
        res.verdict = "工对"
    elif res.total and res.matched >= max(1, res.total // 2):
        res.verdict = "宽对"
    else:
        res.verdict = "参考"

    if res.verdict in ("工对", "宽对"):
        res.notes.append("词类相同/相近，平仄相对，可视为对仗。")
    if res.repeated:
        res.notes.append(
            f"出句与对句共用字：{'、'.join(res.repeated)}（对仗一般忌重字，"
            "但叠字、顶真等修辞除外）"
        )
    res.notes.append("「合掌」「流水对」「意境高下」须人工判断，程序不作结论。")
    return res


def _cats(kb: KnowledgeBase, text: str) -> Set[str]:
    cats: Set[str] = set()
    for ch in text:
        cats |= kb.categories_of(ch)
    return cats


def _tone_of(kb: KnowledgeBase, ch: str, book: str) -> Optional[str]:
    tones = kb.tones(ch, book)
    if len(tones) == 1:
        return next(iter(tones))
    if not tones:
        return None
    # 多音字：无法确定，返回 None 表示「不判」
    return None
