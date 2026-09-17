# -*- coding: utf-8 -*-
"""近体诗诗谱推导、平仄比对与拗救判定。

诗谱不是抄来的，而是由知识库中的四种「基本句式」按「对」「粘」规则推导出来的。
这样知识库里只有 4 条数据，却能生成全部 16 种诗谱。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .knowledge import KnowledgeBase, 平, 仄

# 字 -> 结果状态
状态_合律 = "合律"
状态_从宽 = "从宽"
状态_借读 = "借读"       # 多音字，取可满足定式的读法
状态_未收 = "未收录"     # 韵书里没有这个字
状态_未判 = "未判"       # 整句字数与定式不符，无从逐字比对
状态_出律 = "出律"

# 不参与平仄符合度统计的状态
状态_不计分 = (状态_未收, 状态_未判)


# ---------------------------------------------------------------- 诗谱推导


def flip(tone: str) -> str:
    return 仄 if tone == 平 else 平


def entry_of(kb: KnowledgeBase, kind: str, pu: str) -> dict:
    for e in kb.jinti["基本句式"][kind]:
        if e["谱"] == pu:
            return e
    raise KeyError(f"{kind} 中没有句式 {pu}")


def dui_ju(kb: KnowledgeBase, kind: str, prev: str) -> str:
    """对句：第二字与上一句相反，且平收。"""
    e = entry_of(kb, kind, prev)
    return kb.pattern_index[kind][(flip(e["第二字"]), 平)]["谱"]


def nian_ju(kb: KnowledgeBase, kind: str, prev: str) -> str:
    """粘句：第二字与上一句相同，且仄收。"""
    e = entry_of(kb, kind, prev)
    return kb.pattern_index[kind][(e["第二字"], 仄)]["谱"]


def build_shi_pu(kb: KnowledgeBase, kind: str, first: str, lines: int) -> List[str]:
    """由首句式推导整首诗的平仄谱。"""
    pu = [first]
    for i in range(1, lines):
        prev = pu[-1]
        pu.append(dui_ju(kb, kind, prev) if i % 2 == 1 else nian_ju(kb, kind, prev))
    return pu


def all_first_patterns(kb: KnowledgeBase, kind: str) -> List[str]:
    return [e["谱"] for e in kb.jinti["基本句式"][kind]]


def free_positions(kb: KnowledgeBase, kind: str) -> Set[int]:
    """返回可「不论」的 0-based 位置集合。"""
    key = "七言不论位置" if kind == "七言" else "五言不论位置"
    positions = kb.jinti["变通规则"]["一三五不论"].get(key, [])
    return {int(p) - 1 for p in positions}


# ---------------------------------------------------------------- 结果结构


@dataclass
class CharResult:
    index: int          # 0-based 句内位置
    char: str
    expected: str       # 定式要求的平仄
    tones: Set[str]     # 韵书中该字的平仄
    status: str
    chosen: Optional[str] = None   # 比对时采用的读法


@dataclass
class Issue:
    level: str          # 错误 / 警告 / 提示
    title: str
    detail: str


@dataclass
class ClauseResult:
    index: int                 # 0-based 句序
    text: str
    pattern: str
    chars: List[CharResult] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
    is_rhyme: bool = False     # 是否押韵句（平收）
    lenient: Set[int] = field(default_factory=set)

    @property
    def violations(self) -> List[CharResult]:
        return [c for c in self.chars if c.status == 状态_出律]

    @property
    def unknown(self) -> List[CharResult]:
        return [c for c in self.chars if c.status == 状态_未收]

    @property
    def unjudged(self) -> List[CharResult]:
        """因整句字数不符而未能逐字判定的字。"""
        return [c for c in self.chars if c.status == 状态_未判]

    @property
    def serious_issues(self) -> List[Issue]:
        return [i for i in self.issues if i.level == "错误"]

    @property
    def conforms(self) -> bool:
        return not self.violations and not self.serious_issues

    @property
    def rhyme_char(self) -> str:
        return self.text[-1] if self.text else ""

    def tone_string(self) -> str:
        return "".join(c.chosen or "?" for c in self.chars)


# ---------------------------------------------------------------- 比对


def compare_clause(
    kb: KnowledgeBase,
    text: str,
    pattern: str,
    index: int,
    book: str,
    rhythm_friendly: bool = False,
) -> ClauseResult:
    """把一句诗与给定的平仄定式比对。

    rhythm_friendly=True 时启用「一三五不论」等从宽规则（近体诗用）；
    词谱校验时用 False，因为词谱已经用「中」显式标出了不论之处。
    """
    kind = "五言" if len(pattern) == 5 else "七言"
    result = ClauseResult(index=index, text=text, pattern=pattern)

    if len(text) != len(pattern):
        # 整句字数与定式不符，无从逐字比对。此时**不逐个报出律**（那只会刷屏），
        # 只记一条「字数不符」，但仍算出每个字的平仄，供报告展示。
        result.issues.append(
            Issue(
                "错误",
                "字数不符",
                f"应为 {len(pattern)} 字，实为 {len(text)} 字，无法逐字比对",
            )
        )
        for i, ch in enumerate(text):
            tones = kb.tones(ch, book)
            result.chars.append(
                CharResult(
                    i, ch, "", tones, 状态_未判,
                    sorted(tones)[0] if tones else None,
                )
            )
        result.is_rhyme = pattern[-1] == 平
        return result

    lenient = free_positions(kb, kind) if rhythm_friendly else set()
    result.lenient = lenient

    for i, (ch, exp) in enumerate(zip(text, pattern)):
        if exp == "中":                    # 词谱的不论位
            result.chars.append(
                CharResult(i, ch, exp, kb.tones(ch, book), 状态_从宽, _pick(kb, ch, book, None))
            )
            continue
        tones = kb.tones(ch, book)
        res = _match(i, ch, exp, tones, lenient)
        result.chars.append(res)

    # ---- 整句层面的特殊句式
    _apply_special(kb, result)

    # 韵脚句标记
    result.is_rhyme = pattern[-1] == 平
    return result


def _match(i: int, ch: str, exp: str, tones: Set[str], lenient: Set[int]) -> CharResult:
    if not tones:
        return CharResult(i, ch, exp, tones, 状态_未收, None)
    if exp in tones:
        return CharResult(i, ch, exp, tones, 状态_合律, exp)
    if len(tones) > 1:                     # 多音字，可借读
        return CharResult(i, ch, exp, tones, 状态_借读, exp)
    if i in lenient:
        return CharResult(i, ch, exp, tones, 状态_从宽, next(iter(tones)))
    return CharResult(i, ch, exp, tones, 状态_出律, next(iter(tones)))


def _pick(kb: KnowledgeBase, ch: str, book: str, prefer: Optional[str]) -> Optional[str]:
    tones = kb.tones(ch, book)
    if not tones:
        return None
    if prefer in tones:
        return prefer
    return sorted(tones)[0]


# ---------------------------------------------------------------- 拗救

def _apply_special(kb: KnowledgeBase, clause: ClauseResult) -> None:
    """整句层面识别：特拗句、半拗、孤平、三平调、三仄尾。"""
    pattern = clause.pattern
    if len(pattern) not in (5, 7) or "中" in pattern:
        return
    actual = clause.tone_string()
    if "?" in actual:
        return
    n = len(pattern)

    # ---- 特拗句（鲤鱼翻波）：视为合律
    if _is_teao(pattern, actual):
        for c in clause.chars:
            if c.status in (状态_出律, 状态_从宽):
                c.status = 状态_合律
        clause.issues.append(
            Issue("提示", "特拗句", "本句为「特拗」变体（平平仄平仄），唐人常用，视为合律")
        )
        return

    # ---- 半拗：「仄仄平平仄」第三字作仄 →「仄仄仄平仄」，只拗不忌，可不救
    if pattern == "仄仄平平仄" and actual[1:] == "仄仄平仄":
        for c in clause.chars:
            if c.status == 状态_出律:
                c.status = 状态_合律
        clause.issues.append(Issue("提示", "半拗", "只拗不犯禁忌，可不救"))
        return

    # ---- 三平调
    if pattern[-1] == 平 and actual[-3:] == "平平平":
        clause.issues.append(
            Issue("错误", "三平调", "押韵句末尾三字全平，是近体诗大忌，必须改字")
        )

    # ---- 三仄尾
    if pattern[-1] == 仄 and actual[-3:] == "仄仄仄":
        clause.issues.append(
            Issue("警告", "三仄尾", "仄收句末尾三字全仄，属小病，能避则避")
        )

    # ---- 孤平
    # 只发生在「…仄仄平」结尾的押韵句（即「平平仄仄平」「仄仄平平仄仄平」），
    # 其余句式（如「仄仄仄平平」）本身就只有少数平声，不算孤平。
    if pattern[-1] == 平 and actual[-2] == 仄:
        ping_count = actual[:-1].count(平)
        if ping_count <= 1:
            saved = actual[n - 3] == 平   # 第三字（五言）/第五字（七言）用平声救
            if saved:
                clause.issues.append(
                    Issue("提示", "孤平拗救", "本句犯孤平，已在第三/五字用平声救回，合律")
                )
            else:
                clause.issues.append(
                    Issue("错误", "孤平",
                          "押韵句除韵脚外只有一个平声字，是近体诗大忌；"
                          "可将第三字（五言）/第五字（七言）改为平声以救")
                )


def _is_teao(pattern: str, actual: str) -> bool:
    """是否为特拗句变体「平平仄平仄」（七言「仄仄平平仄平仄」）。

    首字位属「一三五不论」，故只核对后四字的关键特征「平仄平仄」。
    """
    if len(pattern) == 5:
        return pattern == "平平平仄仄" and actual[1:] == "平仄平仄"
    if len(pattern) == 7:
        return pattern == "仄仄平平平仄仄" and actual[3:] == "平仄平仄"
    return False


# ---------------------------------------------------------------- 评分


def score_clauses(clauses: Sequence[ClauseResult]) -> float:
    """返回「平仄符合度」0~1。未收录字不计入分母。"""
    total = 0
    ok = 0
    for cl in clauses:
        for c in cl.chars:
            if c.status in 状态_不计分:
                continue
            total += 1
            if c.status in (状态_合律, 状态_从宽, 状态_借读):
                ok += 1
    return ok / total if total else 0.0
