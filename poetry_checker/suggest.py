# -*- coding: utf-8 -*-
"""改字建议。

**只做「韵脚换字」**，理由如下：

* 韵脚出韵/重韵时，替换目标的空间是**封闭**的——只需在该韵部里找一个平仄相符、
  且未被用过的字。这是可以穷举的问题，规则能给出可靠答案。
* 非韵脚的出律字则不然。一个位置该用平声还是仄声是确定的，但换成哪个字
  取决于句意、搭配、语感——**纯规则给出的候选必然词不达意**，
  不如老实告诉用户「此处需要仄声字」，由人自己斟酌。

宁可不建议，也不给一堆用不上的字。
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from .knowledge import CILIN, KnowledgeBase, PINGSHUI, 平, 仄

# 建议里最多列出多少个候选字
DEFAULT_LIMIT = 60
# 报告里实际打印多少个
DISPLAY_LIMIT = 28


def candidates(
    kb: KnowledgeBase,
    group: str,
    tone: Optional[str],
    book: str = PINGSHUI,
    exclude: Iterable[str] = (),
    limit: int = DEFAULT_LIMIT,
) -> List[str]:
    """从 ``group`` 韵部中取出可用于替换的字。

    参数
    ----
    group  : 韵部名（如「下平声一东」「第一部」）。
    tone   : 需要的平仄（平/仄）；None 表示不限。
    book   : 韵书名。
    exclude: 要排除的字（通常是已用过的韵脚）。
    limit  : 最多返回多少个。

    排序策略（依次）：
    1. **诗词常用字优先** —— 以对仗词类表所收的字为「常见的诗词用字」的近似；
       韵书里同音的生僻字（如「童」旁的僮、瞳、潼）就不会挤在前面。
    2. 其余字按韵书原本的排列次序。

    字表与平仄一律走 ``kb`` 的统一接口（``kb.members`` / ``kb.tones``），
    不直接摸 ``RhymeBook``。因为《中华新韵》没有现成字表，平仄也是现算的，
    直接取 ``RhymeBook`` 的话只会得到一个空表——曾经就这样悄悄失效过：
    用新韵校验时，换字建议永远回一句「该韵部中没有可用的替换字」。
    """
    used = set(exclude)
    common_known = getattr(kb, "char_category", {})

    members = kb.members(group, book)
    ordered = [ch for ch in members if ch in common_known]
    ordered += [ch for ch in members if ch not in common_known]

    out: List[str] = []
    for ch in ordered:
        if ch in used:
            continue
        if tone in (平, 仄) and tone not in kb.tones(ch, book):
            continue
        out.append(ch)
        if len(out) >= limit:
            break
    return out


def format_candidates(chars: Sequence[str], limit: int = DISPLAY_LIMIT) -> str:
    """把候选字排成一行，超出的截断并注明。"""
    if not chars:
        return ""
    shown = list(chars[:limit])
    text = "、".join(shown)
    if len(chars) > limit:
        text += f"……（共 {len(chars)} 字，此处只列前 {limit} 个）"
    return text


def tone_label(tone: Optional[str]) -> str:
    if tone == 平:
        return "平声"
    if tone == 仄:
        return "仄声"
    return "不限平仄"


def group_label(group: str, book: str) -> str:
    """给韵部名补上它所属的韵书，免得张冠李戴。

    曾经这里只区分「平水韵 / 其它」，于是用《中华新韵》校验时，
    建议里会写「不在主韵《词林正韵》十东」——指的是一本用不上的韵书。
    """
    if book == PINGSHUI:
        return f"《平水韵》{group}"
    if book == CILIN:
        return f"《词林正韵》{group}"
    return f"《{book}》{group}"


def rhyme_fix(
    kb: KnowledgeBase,
    char: str,
    main_group: Optional[str],
    tone: Optional[str],
    used: Iterable[str],
    book: str = PINGSHUI,
) -> str:
    """为「出韵」或「重韵」的韵脚字生成换字建议。"""
    if not main_group:
        return f"「{char}」未落在统一韵部中，无法给出换字建议。"

    # 两种情况要分开说：韵部不对，还是韵部没问题、只是平仄不合。
    # 早先一律写「不在主韵X」，于是把同部的字说成出韵——
    # 例如《西江月》叶韵位用了个同部平声字，报告却说它「不在第七部」。
    if main_group in kb.groups(char, book):
        head = (
            f"「{char}」属{group_label(main_group, book)}，韵部没有问题，"
            f"但该韵位需 {tone_label(tone)}"
        )
    else:
        head = (
            f"「{char}」不在主韵{group_label(main_group, book)}"
            f"（该韵位需 {tone_label(tone)}）"
        )
    cand = candidates(kb, main_group, tone, book=book, exclude=set(used) | {char})
    if not cand:
        return head + "，而该韵部中没有可用的替换字，建议改换整句。"
    return (
        f"{head}。可从主韵部中选{tone_label(tone)}字替换，例如："
        f"{format_candidates(cand)}"
        "（仅按韵部与平仄筛出，语义是否相合请自行斟酌）"
    )
