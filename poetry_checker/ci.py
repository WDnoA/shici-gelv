# -*- coding: utf-8 -*-
"""词（长短句）校验引擎。

与近体诗不同，词的句读、字数、平仄、韵位全部由词牌决定，
因此校验方式是「按谱切句 → 逐字比对 → 按韵标记查韵」。
韵书用《词林正韵》。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Counter as CounterType
from typing import Dict, List, Optional, Sequence, Tuple

from . import patterns as pt
from . import suggest
from .knowledge import CILIN, KnowledgeBase, 平, 仄
from .parser import ParsedPoem, segment_by_lengths


def pattern_length(pu: str) -> int:
    """谱的有效字数（忽略顿号等分隔符）。"""
    return sum(1 for c in pu if c in (平, 仄, "中"))


def clean_pattern(pu: str) -> str:
    return "".join(c for c in pu if c in (平, 仄, "中"))


@dataclass
class CiClause:
    index: int
    text: str
    raw_pattern: str
    pattern: str
    rhyme_flag: int
    result: Optional[pt.ClauseResult] = None
    group_id: Optional[int] = None

    @property
    def size_ok(self) -> bool:
        return len(self.text) == len(self.pattern) and bool(self.text)

    @property
    def is_rhyme(self) -> bool:
        return self.rhyme_flag != 0


@dataclass
class RhymeGroup:
    group_id: int
    expected_tone: str = "中"
    feet: List[Tuple[int, str]] = field(default_factory=list)   # (句序 0-based, 汉字)
    main_group: Optional[str] = None
    ok: bool = True
    notes: List[str] = field(default_factory=list)

    @property
    def chars(self) -> str:
        return "、".join(ch for _i, ch in self.feet)


@dataclass
class BreakSegment:
    """一段「句读错位」的诊断结果。"""

    indices: List[int] = field(default_factory=list)   # 涉及的句（0-based）
    required: List[str] = field(default_factory=list)  # 词谱要求的断句
    actual: List[str] = field(default_factory=list)    # 作者自己的断句
    rebuilt: List[str] = field(default_factory=list)   # 按谱重新断句的结果
    bad: List[str] = field(default_factory=list)       # 重断后仍出律的位置
    fixable: bool = False                              # 是否只需挪逗号

    @property
    def span(self) -> str:
        return "、".join(f"第{i + 1}句" for i in self.indices)

    @property
    def needs(self) -> str:
        return " ｜ ".join(f"第{i + 1}句 {len(p)} 字" for i, p in zip(self.indices, self.required))


@dataclass
class CiResult:
    kind: str = "词"
    title: Optional[str] = None
    cipai: str = ""
    aliases: List[str] = field(default_factory=list)
    spec: dict = field(default_factory=dict)
    clauses: List[CiClause] = field(default_factory=list)
    expected_chars: int = 0
    actual_chars: int = 0
    rhyme_groups: List[RhymeGroup] = field(default_factory=list)
    break_segments: List[BreakSegment] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)
    issues: List[pt.Issue] = field(default_factory=list)
    score: float = 0.0
    verdict: str = ""
    book: str = CILIN

    @property
    def skeleton(self) -> str:
        """句读骨架：各句字数依次串起来，方便作者比对自己的断句。"""
        return "·".join(str(len(c.pattern)) for c in self.clauses)

    @property
    def char_ok(self) -> bool:
        return self.expected_chars == self.actual_chars

    @property
    def clause_ok(self) -> bool:
        return all(c.size_ok for c in self.clauses)

    @property
    def rhyme_ok(self) -> bool:
        return all(g.ok for g in self.rhyme_groups)

    @property
    def all_violations(self) -> List[Tuple[int, pt.CharResult]]:
        out: List[Tuple[int, pt.CharResult]] = []
        for c in self.clauses:
            if c.result:
                for ch in c.result.violations:
                    out.append((c.index, ch))
        return out

    @property
    def all_unknown(self) -> List[Tuple[int, pt.CharResult]]:
        out: List[Tuple[int, pt.CharResult]] = []
        for c in self.clauses:
            if c.result:
                for ch in c.result.unknown:
                    out.append((c.index, ch))
        return out

    @property
    def serious(self) -> List[Tuple[int, pt.Issue]]:
        out: List[Tuple[int, pt.Issue]] = []
        for c in self.clauses:
            if c.result:
                for i in c.result.serious_issues:
                    out.append((c.index, i))
        out.extend((0, i) for i in self.issues if i.level == "错误")
        return out


# ---------------------------------------------------------------- 主入口


def check(kb: KnowledgeBase, parsed: ParsedPoem, book: str = CILIN) -> Optional[CiResult]:
    """校验一首词。没有识别到词牌时返回 None。"""
    if not parsed.cipai:
        return None
    spec = kb.cipai_spec(parsed.cipai)
    if spec is None:
        return None

    real_name = kb.cipai_real_name(parsed.cipai) or parsed.cipai
    res = CiResult(
        title=parsed.title,
        cipai=real_name,
        aliases=list(spec.get("别名", [])),
        spec=spec,
        book=book,
    )

    grid = spec.get("格律", [])
    res.expected_chars = sum(pattern_length(g["谱"]) for g in grid)
    res.actual_chars = len(parsed.chars)

    texts = _segment(parsed, grid, res)

    for i, g in enumerate(grid):
        raw = g["谱"]
        pu = clean_pattern(raw)
        text = texts[i] if i < len(texts) else ""
        clause = pt.compare_clause(kb, text, pu, i, book, rhythm_friendly=False)
        res.clauses.append(
            CiClause(
                index=i,
                text=text,
                raw_pattern=raw,
                pattern=pu,
                rhyme_flag=int(g.get("韵", 0)),
                result=clause,
            )
        )

    res.rhyme_groups = _analyze_rhyme(kb, res)
    res.break_segments = _analyze_break(kb, res)
    res.hints = list(spec.get("对仗", []))
    res.score = pt.score_clauses([c.result for c in res.clauses if c.result])
    res.issues.extend(_global_issues(kb, res))
    res.verdict = _verdict(res)
    return res


# ---------------------------------------------------------------- 切句


def _segment(parsed: ParsedPoem, grid: Sequence[dict], res: CiResult) -> List[str]:
    """把正文切成与词谱一一对应的句子。

    优先**尊重作者自己的标点**：只要句数一致、总字数一致，就用标点分句。
    这样当「逗」（句中顿断）的位置与词谱不同时，报告能精确指出
    「第 3 句应 6 字、实 5 字」，而不是按谱长硬切出「桂影婆娑处清」
    这种跨句拼接的怪句——那种输出毫无意义，只会让人困惑。
    """
    lengths = [pattern_length(g["谱"]) for g in grid]
    chars = parsed.chars
    clauses = [c for c in parsed.clauses if c]

    if clauses and len(clauses) == len(lengths) and sum(map(len, clauses)) == len(chars):
        return clauses

    if sum(lengths) == len(chars):
        seg = segment_by_lengths(chars, lengths)
        if seg:
            return seg

    # 尽力而为：按谱长硬切；长度对不上时在报告中提示
    res.issues.append(
        pt.Issue(
            "错误",
            "字数不符",
            f"《{res.cipai}》正体为 {res.expected_chars} 字，实得 {res.actual_chars} 字；"
            "也可能该词牌存在别体。以下按谱长尽力切分，结论仅供参考。",
        )
    )
    out: List[str] = []
    pos = 0
    for n in lengths:
        out.append(chars[pos : pos + n])
        pos += n
    return out


# ---------------------------------------------------------------- 押韵


def _analyze_rhyme(kb: KnowledgeBase, res: CiResult) -> List[RhymeGroup]:
    # ---- 1. 归组：韵标记 3 起新组，其余延续当前组
    group_id = 0
    started = False
    groups: Dict[int, RhymeGroup] = {}
    for cl in res.clauses:
        if not cl.is_rhyme:
            continue
        if not started or cl.rhyme_flag == 3:
            group_id += 1
            started = True
            expected = cl.pattern[-1] if cl.pattern else "中"
            groups[group_id] = RhymeGroup(group_id=group_id, expected_tone=expected)
        cl.group_id = group_id
        if cl.text:
            groups[group_id].feet.append((cl.index, cl.text[-1]))

    # ---- 2. 逐组检查韵部与韵脚平仄
    for gid, group in sorted(groups.items()):
        if not group.feet:
            group.ok = False
            group.notes.append("该韵位没有取到字")
            continue

        counter: CounterType = Counter()
        for _idx, ch in group.feet:
            for g in kb.groups(ch, CILIN):
                counter[g] += 1
        group.main_group = counter.most_common(1)[0][0] if counter else None

        for _idx, ch in group.feet:
            gs = kb.groups(ch, CILIN)
            if not gs:
                group.ok = False
                group.notes.append(f"「{ch}」不在《词林正韵》中")
            elif group.main_group not in gs:
                compat = kb.cilin_compat.get(group.main_group, set())
                hit = gs & compat
                if hit:
                    group.notes.append(
                        f"「{ch}」属「{'／'.join(sorted(hit))}」，与主韵「{group.main_group}」"
                        "属半韵通押，宋词多可通融"
                    )
                else:
                    group.ok = False
                    group.notes.append(f"「{ch}」出韵（不在「{group.main_group}」）")

        if group.expected_tone in (平, 仄):
            label = "平" if group.expected_tone == 平 else "仄"
            bad = [ch for _i, ch in group.feet if group.expected_tone not in kb.tones(ch, CILIN)]
            if bad:
                group.ok = False
                group.notes.append(f"该韵位应押{label}声，以下字不合：{'、'.join(bad)}")

    # ---- 3. 叠韵检查（韵标记 2）
    prev_char: Optional[str] = None
    for cl in res.clauses:
        if not cl.is_rhyme or not cl.text:
            continue
        if cl.rhyme_flag == 2 and prev_char and cl.text[-1] != prev_char:
            gid = cl.group_id or 0
            if gid in groups:
                groups[gid].notes.append(
                    f"第 {cl.index + 1} 句标为叠韵，但末字「{cl.text[-1]}」"
                    f"与上一韵脚「{prev_char}」不同"
                )
        prev_char = cl.text[-1]

    return [groups[k] for k in sorted(groups)]


# ---------------------------------------------------------------- 全局问题


def _global_issues(kb: KnowledgeBase, res: CiResult) -> List[pt.Issue]:
    issues: List[pt.Issue] = []
    unknown = res.all_unknown
    if unknown:
        chars = "".join(sorted({c.char for _, c in unknown}))
        issues.append(
            pt.Issue(
                "提示",
                "韵书未收录",
                f"以下字不在《词林正韵》数据中，未参与平仄判定：{chars}。"
                "请查证后补充到 知识库/韵书/平水韵.json（词林正韵会自动同步）。",
            )
        )

    # ---- 押韵问题 + 换字建议
    bad = [g for g in res.rhyme_groups if not g.ok]
    if bad:
        issues.append(
            pt.Issue(
                "错误",
                "押韵问题",
                f"第 {'、'.join(str(g.group_id) for g in bad)} 个韵组存在问题，详见押韵分析。",
            )
        )
        for g in bad:
            if not g.main_group:
                continue
            used = [ch for _i, ch in g.feet]
            for _i, ch in g.feet:
                gs = kb.groups(ch, CILIN)
                if not gs:
                    continue  # 韵书未收录，不臆测
                wrong_group = g.main_group not in gs
                wrong_tone = (
                    g.expected_tone in (平, 仄)
                    and g.expected_tone not in kb.tones(ch, CILIN)
                )
                if wrong_group or wrong_tone:
                    issues.append(
                        pt.Issue(
                            "建议",
                            "押韵换字建议",
                            f"韵组 {g.group_id}："
                            + suggest.rhyme_fix(
                                kb, ch, g.main_group, g.expected_tone, used, CILIN
                            ),
                        )
                    )

    # ---- 句读问题
    bad_clauses = [c for c in res.clauses if not c.size_ok]
    if bad_clauses:
        detail = "、".join(
            f"第{c.index + 1}句（应{len(c.pattern)}字，实{len(c.text)}字）" for c in bad_clauses
        )
        if not res.char_ok:
            issues.append(pt.Issue("错误", "句读不符", f"以下句的字数与词谱不合：{detail}"))
        else:
            issues.append(
                pt.Issue(
                    "错误",
                    "句读与词谱不符",
                    f"总字数相符（{res.expected_chars} 字），仅逐句字数不同：{detail}。"
                    "这通常是「逗」（句中顿断）的位置与词谱不同，详见「句读对照」。",
                )
            )
        for seg in res.break_segments:
            if seg.fixable:
                issues.append(
                    pt.Issue(
                        "建议",
                        "问题在「逗」的位置",
                        f"{seg.span}按词谱重新断句后**平仄全部吻合**，说明用字本身没问题，"
                        f"只是句中顿断的位置不对。按谱应断为：「{'，'.join(seg.rebuilt)}」"
                        "——逗号挪过去即可，但请自行核对语义是否通顺。",
                    )
                )
            else:
                issues.append(
                    pt.Issue(
                        "错误",
                        "句读错位且平仄不合",
                        f"{seg.span}按词谱重新断句（「{'，'.join(seg.rebuilt)}」）后仍有出律："
                        f"{'、'.join(seg.bad)}。不只是逗号位置问题，还需调整用字。",
                    )
                )
    return issues


def _analyze_break(kb: KnowledgeBase, res: CiResult) -> List[BreakSegment]:
    """诊断「句读错位」。

    把字数不符的**连续若干句**视为一段：若该段的总字数正好等于词谱对应各句的
    总字数，就把这段文字按词谱的长度重新断句，再看平仄是否吻合。这样能明确区分：

    * **只是逗位放错** —— 重断后平仄全合，只需把逗号挪个位置，一个字都不用改；
    * **确实需要改字** —— 重断后仍有出律。
    """
    if not res.char_ok:
        return []
    bad = [c.index for c in res.clauses if not c.size_ok]
    if not bad:
        return []

    segs: List[List[int]] = []
    for i in bad:
        if segs and i == segs[-1][-1] + 1:
            segs[-1].append(i)
        else:
            segs.append([i])

    out: List[BreakSegment] = []
    for seg in segs:
        need = sum(len(res.clauses[i].pattern) for i in seg)
        got = sum(len(res.clauses[i].text) for i in seg)
        if need != got:
            continue

        merged = "".join(res.clauses[i].text for i in seg)
        pos = 0
        rebuilt: List[str] = []
        bad_positions: List[str] = []
        for i in seg:
            size = len(res.clauses[i].pattern)
            piece = merged[pos : pos + size]
            pos += size
            rebuilt.append(piece)
            check = pt.compare_clause(
                kb, piece, res.clauses[i].pattern, i, CILIN, rhythm_friendly=False
            )
            for ch in check.violations:
                bad_positions.append(f"第{i + 1}句第{ch.index + 1}字「{ch.char}」")

        out.append(
            BreakSegment(
                indices=seg,
                required=[res.clauses[i].pattern for i in seg],
                actual=[res.clauses[i].text for i in seg],
                rebuilt=rebuilt,
                bad=bad_positions,
                fixable=not bad_positions,
            )
        )
    return out


def _verdict(res: CiResult) -> str:
    viol = len(res.all_violations)
    serious = len(res.serious)
    base_ok = res.char_ok and res.clause_ok and res.rhyme_ok
    if base_ok and viol == 0 and serious == 0:
        return "合谱"
    if base_ok and viol <= 3 and serious == 0:
        return "基本合谱"
    if not base_ok:
        return "体格有出入"
    return "存在出律"
