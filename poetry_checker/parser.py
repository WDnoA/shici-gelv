# -*- coding: utf-8 -*-
"""诗词文本解析。

负责把用户粘进来的一段文字，拆成：

* 标题 / 词牌
* 一句一句的正文（保留标点信息）
* 全部汉字序列（供按词谱重新切句用）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

# 句读标点：用于切分句子
句读符 = "，。！？；：、,.;!?:"
# 整句结束符
句末符 = "。！？.!?"

# 全角/半角括号
左括号 = "《【[「『（("
右括号 = "》】]」』）)"

# 需要忽略的字符（空格、制表、换行由行处理）
忽略符 = " \t\u3000·•　"

# 汉字范围
_汉字 = re.compile(r"[\u4e00-\u9fff]")
_数字行 = re.compile(r"^\s*\d+[、.．)）]\s*")


@dataclass
class ParsedPoem:
    """解析结果。"""

    title: Optional[str] = None
    cipai: Optional[str] = None          # 从标题中识别出的词牌名
    lines: List[str] = field(default_factory=list)      # 原始正文行
    clauses: List[str] = field(default_factory=list)    # 按标点切出的句子
    chars: str = ""                       # 全部汉字（按顺序，去标点）
    clause_lengths: List[int] = field(default_factory=list)

    @property
    def total_chars(self) -> int:
        return len(self.chars)

    @property
    def clause_count(self) -> int:
        return len(self.clauses)

    def uniform_length(self) -> Optional[int]:
        """若所有句子等长，返回该长度；否则 None。"""
        lens = {len(c) for c in self.clauses if c}
        return lens.pop() if len(lens) == 1 else None


# ---------------------------------------------------------------- 公开接口


def parse(text: str, kb=None) -> ParsedPoem:
    """解析一段诗词文本。

    参数
    ----
    text: 用户输入。
    kb:   KnowledgeBase，用于识别标题中的词牌名（可为 None）。
    """
    result = ParsedPoem()

    raw_lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    # 去掉注释行与空行
    raw_lines = [ln for ln in raw_lines if ln.strip() and not ln.lstrip().startswith("#")]
    if not raw_lines:
        return result

    # ---- 1. 找出标题行
    title_idx = -1
    for i, ln in enumerate(raw_lines[:3]):
        if _looks_like_title(ln, kb, raw_lines[i + 1 :]):
            title_idx = i
            break

    if title_idx >= 0:
        result.title = raw_lines[title_idx].strip()
        result.cipai = _extract_cipai(result.title, kb)
        body_lines = raw_lines[title_idx + 1 :]
    else:
        body_lines = raw_lines
        # 没有独立标题行时，仍尝试从首行前缀识别词牌
        result.cipai = _extract_cipai(body_lines[0], kb) if body_lines else None
        if result.cipai:
            result.title = result.cipai

    # ---- 2. 正文
    result.lines = [_数字行.sub("", ln) for ln in body_lines]

    full = "".join(result.lines)
    result.clauses = split_clauses(full)
    result.clause_lengths = [len(c) for c in result.clauses]
    result.chars = "".join(_汉字.findall(full))
    return result


def split_clauses(text: str) -> List[str]:
    """按标点切句，返回去掉标点的句子列表。"""
    out: List[str] = []
    buf: List[str] = []
    for ch in text:
        if ch in 忽略符:
            continue
        if ch in 句读符:
            if buf:
                out.append("".join(buf))
                buf = []
        elif ch in 左括号 or ch in 右括号:
            # 括号一般属标题或注释，此处按分隔处理
            if buf:
                out.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        out.append("".join(buf))
    return [s for s in out if s]


def segment_by_lengths(chars: str, lengths: Sequence[int]) -> Optional[List[str]]:
    """按给定的每句字数，把汉字序列重新切分成句。

    切分不上（长度总和不等）时返回 None。
    """
    if sum(lengths) != len(chars):
        return None
    out: List[str] = []
    pos = 0
    for n in lengths:
        out.append(chars[pos : pos + n])
        pos += n
    return out


def strip_rhyme_punct(text: str) -> str:
    return "".join(c for c in text if _汉字.match(c))


# ---------------------------------------------------------------- 内部


def _looks_like_title(line: str, kb, rest_lines: Sequence[str] = ()) -> bool:
    """判断一行是否是标题行。

    ``rest_lines`` 是本行之后的内容，用于消解「5 字／7 字的无标点短行到底是标题
    还是诗句」这一歧义：若去掉本行后剩下的内容仍能构成合法体制，则本行是标题。
    """
    s = line.strip()
    if not s:
        return False
    # 明显是正文：含句末标点且较长
    if any(c in s for c in 句末符) and len(_汉字.findall(s)) >= 5:
        return False
    # 《xxx》 形式
    if s[0] in 左括号 and s[-1] in 右括号:
        return True
    # 含间隔号：词牌·题目
    if "·" in s or "•" in s:
        return True
    # 显式声明
    if re.match(r"^\s*(词牌|調|调|题目|题)\s*[:：]", s):
        return True
    han = _汉字.findall(s)
    if len(han) > 24:
        return False
    # 能在里面找到词牌名 → 视为标题
    if kb is not None and _extract_cipai(s, kb):
        return True
    # 短行且没有任何标点 → 可能是标题
    if len(han) <= 12 and not any(c in s for c in 句读符):
        if len(han) in (5, 7):
            # 恰好五言／七言字数：用户「每句一行、不打标点」时极易误判，
            # 故只有在「去掉本行后剩下的内容仍能构成合法体制」时才认作标题。
            return _rest_is_regular_poem(rest_lines)
        return True
    return False


def _rest_is_regular_poem(lines: Sequence[str]) -> bool:
    """剩余内容是否能构成「等长的五言/七言、偶数句」的体制。"""
    text = "".join(lines)
    clauses = split_clauses(text)
    if clauses:
        lens = {len(c) for c in clauses}
        if len(lens) == 1:
            n = len(clauses)
            if n >= 4 and n % 2 == 0 and next(iter(lens)) in (5, 7):
                return True
    han = _汉字.findall(text)
    for size in (5, 7):
        if han and len(han) % size == 0:
            n = len(han) // size
            if n >= 4 and n % 2 == 0:
                return True
    return False


def _extract_cipai(title_text: str, kb) -> Optional[str]:
    """从标题中识别词牌名，返回正名。"""
    if kb is None or not title_text:
        return None
    s = title_text.strip()
    s = s.strip(左括号 + 右括号)
    s = re.sub(r"^\s*(词牌|調|调)\s*[:：]\s*", "", s)
    # 取 · • 之前的部分
    head = re.split(r"[·•]", s)[0]
    head = head.strip(左括号 + 右括号).strip()
    # 先全字匹配
    real = kb.cipai_real_name(head)
    if real:
        return real
    # 头部前缀匹配（如「忆江南江南好」）
    for length in range(min(len(head), 6), 1, -1):
        real = kb.cipai_real_name(head[:length])
        if real:
            return real
    # 整串里搜
    for name in sorted(kb.cipai_alias, key=len, reverse=True):
        if name in s:
            return kb.cipai_alias[name]
    return None
