# -*- coding: utf-8 -*-
"""诗词格律校验器（不含 AI）。

用法::

    from poetry_checker import analyze

    result = analyze("国破山河在，城春草木深。感时花溅泪，恨别鸟惊心。")
    print(result.text())          # 中文报告
    print(result.json())          # 结构化 JSON

本包只做一件事：把一段诗词拿知识库比对，指出平仄、押韵、对仗上的问题。
它不生成内容，也不评价意境。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from . import ci, checker, report
from .knowledge import CILIN, PINGSHUI, XINYUN, KnowledgeBase, KnowledgeError
from .parser import ParsedPoem, parse

__version__ = "1.4.0"

__all__ = [
    "analyze",
    "AnalysisResult",
    "KnowledgeBase",
    "KnowledgeError",
    "ParsedPoem",
    "PINGSHUI",
    "CILIN",
    "XINYUN",
]


@dataclass
class AnalysisResult:
    """一次完整的校验结果。"""

    kind: str                       # 近体诗 / 词 / 未知
    parsed: ParsedPoem
    poem: Optional[checker.PoemResult] = None
    ci: Optional[ci.CiResult] = None
    message: str = ""
    kb: Optional[KnowledgeBase] = None

    @property
    def ok(self) -> bool:
        """是否「无格律缺陷」。仄韵诗变体不算缺陷，故也返回 True。"""
        if self.poem:
            v = self.poem.verdict
            return v in ("合律", "基本合律") or "变体" in v
        if self.ci:
            return self.ci.verdict in ("合谱", "基本合谱")
        return False

    @property
    def score(self) -> float:
        if self.poem:
            return self.poem.score
        if self.ci:
            return self.ci.score
        return 0.0

    @property
    def coverage(self) -> Tuple[int, int]:
        """(已判定字数, 总字数)。``score`` 只在这些字上成立。"""
        if self.poem:
            return self.poem.coverage
        if self.ci:
            return self.ci.coverage
        return (0, 0)

    def text(self, color: bool = False, verbose: bool = True) -> str:
        if self.poem:
            return report.render_poem(self.poem, color=color, verbose=verbose)
        if self.ci:
            return report.render_ci(self.ci, color=color, verbose=verbose)
        head = "═" * report.WIDTH + "\n"
        return (
            f"{head}  无法识别体裁\n{head}\n\n"
            f"{self.message}\n\n"
            f"识别到的句子：{'／'.join(self.parsed.clauses) or '（空）'}\n"
        )

    def to_dict(self) -> dict:
        """结构化结果，供 HTTP API / 前端消费。

        刻意不包含 ``kb``（知识库实例不可序列化，前端也用不上）。
        """
        known, total = self.coverage
        return {
            "kind": self.kind,
            "ok": self.ok,
            "score": self.score,
            "coverage": {"known": known, "total": total},
            "message": self.message,
            "parsed": report._plain(self.parsed),
            "poem": report._plain(self.poem) if self.poem else None,
            "ci": report._plain(self.ci) if self.ci else None,
        }

    def json(self) -> str:
        import json as _json

        return _json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def analyze(
    text: str,
    kb: Optional[KnowledgeBase] = None,
    book: str = PINGSHUI,
    shape: str = "auto",
) -> AnalysisResult:
    """解析并校验一段诗词。

    参数
    ----
    text  : 诗词全文（可含标题、词牌）。
    kb    : 知识库实例，None 则自动加载。
    book  : 近体诗所用韵书，默认「平水韵」；可选「中华新韵」。词固定用「词林正韵」。
    shape : "auto" | "诗" | "词"，强制按某种体制解析。
    """
    own_kb = kb is None
    kb = kb or KnowledgeBase.load()
    parsed = parse(text, kb)

    if shape in ("auto", "词") and parsed.cipai:
        rr = ci.check(kb, parsed, book=CILIN)
        if rr is not None:
            return AnalysisResult("词", parsed, ci=rr, kb=kb)

    if shape in ("auto", "诗"):
        rr = checker.check(kb, parsed, book=book)
        if rr is not None:
            return AnalysisResult("近体诗", parsed, poem=rr, kb=kb)

    msg = (
        "未能在文本中识别出「词牌」，且句子不满足近体诗（五言/七言、偶数句）的形制。\n"
        "提示：\n"
        "  · 若是填词，请把词牌写在标题里，如「《浣溪沙》」或「浣溪沙·一曲新词酒一杯」。\n"
        "  · 若是近体诗，请确认每句五字或七字、句数为偶数（4/8/10…）。\n"
        "  · 古体诗、自由诗不在校验范围内。"
    )
    return AnalysisResult("未知", parsed, message=msg, kb=kb)
