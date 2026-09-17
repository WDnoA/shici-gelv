# -*- coding: utf-8 -*-
"""把校验结果渲染成可读的中文报告。

支持：
* 纯文本（默认）
* ANSI 彩色终端
* JSON（供 APP / 前端调用）
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import is_dataclass
from typing import Any, Dict, List, Optional

from . import ci as ci_mod
from . import checker as poem_mod
from . import patterns as pt
from .knowledge import KnowledgeBase, 平, 仄

WIDTH = 66


# ---------------------------------------------------------------- 颜色


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"


def _c(text: str, color: str, enabled: bool) -> str:
    return f"{color}{text}{C.RESET}" if enabled else text


def tone_color(tone: str) -> str:
    return C.CYAN if tone == 平 else C.YELLOW


# ---------------------------------------------------------------- 宽度工具


def wcwidth(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def pad(s: str, width: int, align: str = "left") -> str:
    gap = max(0, width - wcwidth(s))
    if align == "right":
        return " " * gap + s
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def rule(char: str = "─", width: int = WIDTH) -> str:
    return char * width


def section(title: str, color: bool = False) -> str:
    inner = f" {title} "
    half = max(0, (WIDTH - wcwidth(inner)) // 2)
    line = "─" * half + inner + "─" * (WIDTH - wcwidth(inner) - half)
    return _c(line, C.BOLD, color)


# ---------------------------------------------------------------- 小工具


def tone_text(kb: KnowledgeBase, ch: str, book: str) -> str:
    tones = kb.tones(ch, book)
    if not tones:
        return "?"
    return "".join(sorted(tones, key=lambda t: 0 if t == 平 else 1))


def mark(ok: bool, color: bool) -> str:
    return _c("✔", C.GREEN, color) if ok else _c("✘", C.RED, color)


def verdict_color(verdict: str) -> str:
    """合律为绿，变体为黄，出律为红。"""
    if verdict in ("合律", "基本合律", "合谱", "基本合谱"):
        return C.GREEN
    if "变体" in verdict:
        return C.YELLOW
    return C.RED


def level_color(level: str) -> str:
    return {
        "错误": C.RED,
        "警告": C.YELLOW,
        "建议": C.GREEN,
        "提示": C.GRAY,
    }.get(level, C.RESET)


STATUS_SHORT = {
    pt.状态_合律: "",
    pt.状态_从宽: "从宽",
    pt.状态_借读: "借读",
    pt.状态_未收: "未收录",
    pt.状态_未判: "未判",
    pt.状态_出律: "出律",
}


# ---------------------------------------------------------------- 入口


def render(result: Any, color: bool = False, verbose: bool = True) -> str:
    if isinstance(result, ci_mod.CiResult):
        return render_ci(result, color=color, verbose=verbose)
    return render_poem(result, color=color, verbose=verbose)


def to_json(result: Any, kb: Optional[KnowledgeBase] = None) -> str:
    """输出结构化 JSON，便于 APP 端消费。"""
    return json.dumps(_plain(result, kb), ensure_ascii=False, indent=2)


def _plain(obj: Any, kb: Optional[KnowledgeBase] = None) -> Any:
    """递归地把 dataclass / set 等转成可 JSON 序列化的结构。"""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {key: _plain(value, kb) for key, value in obj.__dict__.items()}
    if isinstance(obj, dict):
        return {k: _plain(v, kb) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v, kb) for v in obj]
    if isinstance(obj, set):
        return sorted(str(v) for v in obj)
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


# ---------------------------------------------------------------- 近体诗


def render_poem(res: poem_mod.PoemResult, color: bool = False, verbose: bool = True) -> str:
    lines: List[str] = []
    lines.append(_c("═" * WIDTH, C.BOLD, color))
    lines.append(_c(pad("诗 词 格 律 校 验 报 告", WIDTH, "center"), C.BOLD, color))
    lines.append(_c("═" * WIDTH, C.BOLD, color))
    lines.append("")

    # ---- 基本信息
    lines.append(section("基 本 信 息", color))
    if res.title:
        lines.append(f"  标题：{res.title}")
    lines.append(f"  体裁：{_c(res.genre, C.BOLD, color)}")
    lines.append(f"  格式：{res.pattern_label}")
    lines.append(f"  韵书：{res.book}")
    if res.shape_note:
        lines.append(_c(f"  {res.shape_note}", C.GRAY, color))
    v_color = verdict_color(res.verdict)
    lines.append(
        f"  结论：{_c(res.verdict, v_color, color)}   "
        f"平仄符合度 {_c(f'{res.score:.1%}', C.BOLD, color)}"
    )
    lines.append("")

    # ---- 平仄谱对照
    lines.append(section("平 仄 谱 对 照", color))
    for idx, (text, cl) in enumerate(zip(res.clauses_text, res.clauses)):
        line_no = pad(f"{idx + 1:>2}", 3)
        tones = "".join(c.chosen or "?" for c in cl.chars)
        tone_show = "".join(
            _c(c.chosen or "?", tone_color(c.chosen or "?"), color) for c in cl.chars
        )
        notes = []
        for iss in cl.issues:
            if iss.level == "提示":
                notes.append(_c(f"[{iss.title}]", C.GRAY, color))
        ok = cl.conforms
        lines.append(
            f"  {line_no}{pad(text, 9)}{'│'}{tone_show}{'│'}"
            f"{pad(' '.join(notes), 3)}{mark(ok, color)}"
        )
        lines.append(
            f"     {pad('', 9)} {_c('定式 ' + cl.pattern, C.GRAY, color)}"
        )
    lines.append("")

    # ---- 出律清单
    viol = res.all_violations
    serious = res.serious
    lines.append(section("出 律 清 单", color))
    if not viol and not serious:
        lines.append(_c("  无出律，全部合律。", C.GREEN, color))
    else:
        for cidx, ch in viol:
            exp = ch.expected
            act = "".join(sorted(ch.tones)) or "未知"
            hint = "（可从宽位置，但造成整句问题，见下）" if not ch.tones else ""
            lines.append(
                f"  {_c('✘', C.RED, color)} 第 {cidx + 1} 句第 {ch.index + 1} 字 "
                f"「{ch.char}」：定式要求 {_c(exp, tone_color(exp), color)}，"
                f"该字读作 {_c(act, C.YELLOW, color)} {hint}"
            )
        for cidx, iss in serious:
            lines.append(
                f"  {_c('✘', C.RED, color)} 第 {cidx + 1} 句 "
                f"【{_c(iss.title, C.RED, color)}】{iss.detail}"
            )
    lines.append("")

    # ---- 押韵分析
    if res.rhyme:
        lines.append(section(f"押 韵 分 析（{res.rhyme.book}）", color))
        if not res.rhyme.feet:
            lines.append("  未识别到押韵句。")
        else:
            if res.rhyme.main_group:
                lines.append(f"  主韵：{_c(res.rhyme.main_group, C.BOLD, color)}")
            for f in res.rhyme.feet:
                groups = "／".join(sorted(f.groups)) if f.groups else "未收录"
                tag = "（首句）" if f.is_first else ""
                note = _c(f"  ← {f.note}", C.YELLOW, color) if f.note else ""
                lines.append(
                    f"  句{f.clause_index + 1:>2}  "
                    f"{pad(f.char, 3)}{pad(groups, 26)}{mark(f.ok, color)}{tag}{note}"
                )
            for n in res.rhyme.notes:
                lines.append(_c(f"  ⚠ {n}", C.YELLOW, color))
        lines.append("")

    # ---- 对仗分析
    if res.couplets:
        lines.append(section("对 仗 分 析（仅供参考）", color))
        for cp in res.couplets:
            need = "必对" if cp.required else "可不对"
            head = f"{cp.label}（第 {cp.left_index + 1}、{cp.right_index + 1} 句，{need}）"
            if not cp.detail:
                lines.append(f"  {head}：字数不等，无法比较")
                continue
            good = cp.detail.verdict in ("工对", "宽对")
            lines.append(f"  {head}  →  {_c(cp.detail.verdict, C.GREEN if good else C.YELLOW, color)}")
            if verbose:
                for seg in cp.detail.segments:
                    lines.append(f"      {seg.describe()}")
                for n in cp.detail.notes:
                    lines.append(_c(f"      · {n}", C.GRAY, color))
        lines.append("")

    # ---- 提示
    lines.append(section("提 示 与 说 明", color))
    for iss in res.issues:
        lines.append(f"  {_c('●', level_color(iss.level), color)} [{iss.level}] {iss.title}：{iss.detail}")
    for cl in res.clauses:
        for iss in cl.issues:
            if iss.level != "提示":
                lines.append(
                    f"  {_c('●', level_color(iss.level), color)} 第 {cl.index + 1} 句 "
                    f"[{iss.level}] {iss.title}：{iss.detail}"
                )
    lines.append(_c("  · 本工具为格律辅助，不代替作者判断；意境、修辞请自行斟酌。", C.GRAY, color))
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- 词


def render_ci(res: ci_mod.CiResult, color: bool = False, verbose: bool = True) -> str:
    lines: List[str] = []
    lines.append(_c("═" * WIDTH, C.BOLD, color))
    lines.append(_c(pad("词 牌 格 律 校 验 报 告", WIDTH, "center"), C.BOLD, color))
    lines.append(_c("═" * WIDTH, C.BOLD, color))
    lines.append("")

    lines.append(section("基 本 信 息", color))
    if res.title:
        lines.append(f"  标题：{res.title}")
    lines.append(f"  词牌：{_c(res.cipai, C.BOLD, color)}")
    if res.aliases:
        lines.append(f"  别名：{'、'.join(res.aliases)}")
    lines.append(f"  韵书：{res.book}")
    lines.append(f"  段数：{res.spec.get('段数', '?')}   句数：{len(res.clauses)}")
    char_ok = res.char_ok
    lines.append(
        f"  字数：{res.actual_chars} / {res.expected_chars} "
        f"{mark(char_ok, color)}（正体 {res.spec.get('字数', '?')} 字）"
    )
    lines.append(_c(f"  句读骨架：{res.skeleton}", C.GRAY, color))
    lines.append(_c("  （骨架是各句字数依次排列，断句时照着对；谱中的「、」表示顿）", C.GRAY, color))
    v_color = verdict_color(res.verdict)
    lines.append(
        f"  结论：{_c(res.verdict, v_color, color)}   "
        f"平仄符合度 {_c(f'{res.score:.1%}', C.BOLD, color)}"
    )
    lines.append("")

    lines.append(section("逐 句 对 照", color))
    for c in res.clauses:
        no = pad(f"{c.index + 1:>2}", 3)
        rtext = "".join(
            _c(ch.chosen or "?", tone_color(ch.chosen or "?"), color)
            for ch in (c.result.chars if c.result else [])
        )
        flag = _c("韵", C.MAGENTA, color) if c.is_rhyme else " "
        if c.rhyme_flag == 2:
            flag = _c("叠", C.MAGENTA, color)
        elif c.rhyme_flag == 4:
            flag = _c("叶", C.MAGENTA, color)
        notes = ""
        if c.result:
            notes = " ".join(
                _c(f"[{i.title}]", C.GRAY, color)
                for i in c.result.issues
                if i.level == "提示"
            )
        lines.append(
            f"  {no}{pad(c.text, 12)}{'│'}{rtext}{'│'}{flag}{' '}{notes}"
            f"{mark(c.size_ok and (c.result.conforms if c.result else False), color)}"
        )
        lines.append(f"     {pad('', 12)} {_c('定式 ' + c.raw_pattern, C.GRAY, color)}")
    lines.append("")

    # ---- 句读对照（仅在断句与词谱不符时出现）
    if res.break_segments:
        lines.append(section("句 读 对 照", color))
        for seg in res.break_segments:
            lines.append(f"  词谱要求   {seg.needs}")
            lines.append(
                "  你的断句   "
                + " ｜ ".join(f"{t}{_c(f'（{len(t)}字）', C.YELLOW, color)}" for t in seg.actual)
            )
            lines.append("  按谱重断   " + " ｜ ".join(seg.rebuilt))
            if seg.fixable:
                lines.append(
                    _c(
                        "             ↑ 按谱重断后平仄全合 → 用字没问题，只是「逗」的位置不对，"
                        "照上面重断即可（语义请自行核对）",
                        C.GREEN,
                        color,
                    )
                )
            else:
                lines.append(
                    _c(
                        "             ↑ 按谱重断后仍有出律："
                        + "、".join(seg.bad)
                        + " —— 不只是逗号问题，需调整用字",
                        C.RED,
                        color,
                    )
                )
        lines.append("")

    viol = res.all_violations
    serious = res.serious
    lines.append(section("出 律 清 单", color))
    if not viol and not serious:
        lines.append(_c("  无出律，全部合谱。", C.GREEN, color))
    else:
        for cidx, ch in viol:
            lines.append(
                f"  {_c('✘', C.RED, color)} 第 {cidx + 1} 句第 {ch.index + 1} 字 "
                f"「{ch.char}」：定式要求 {_c(ch.expected, tone_color(ch.expected), color)}，"
                f"该字读作 {_c(''.join(sorted(ch.tones)) or '未知', C.YELLOW, color)}"
            )
        for cidx, iss in serious:
            lines.append(
                f"  {_c('✘', C.RED, color)} 第 {cidx + 1} 句 "
                f"【{_c(iss.title, C.RED, color)}】{iss.detail}"
            )
    lines.append("")

    if res.rhyme_groups:
        lines.append(section(f"押 韵 分 析（{res.book}）", color))
        for g in res.rhyme_groups:
            tone_label = g.expected_tone if g.expected_tone in (平, 仄) else "不限"
            head = f"  韵组 {g.group_id}（应押{tone_label}声）  {pad(g.chars, 20)}"
            lines.append(f"{head}{mark(g.ok, color)}")
            if g.main_group:
                lines.append(_c(f"      韵部：{g.main_group}", C.GRAY, color))
            for n in g.notes:
                lines.append(_c(f"      ⚠ {n}", C.YELLOW, color))
        lines.append("")

    if res.hints:
        lines.append(section("对 仗 提 示", color))
        for h in res.hints:
            lines.append(f"  · {h}")
        lines.append(_c("  （词的对仗较自由，不忌重字，是否用对仗由作者决定）", C.GRAY, color))
        lines.append("")

    lines.append(section("提 示 与 说 明", color))
    for iss in res.issues:
        lines.append(f"  {_c('●', level_color(iss.level), color)} [{iss.level}] {iss.title}：{iss.detail}")
    for c in res.clauses:
        if c.result:
            for iss in c.result.issues:
                if iss.level != "提示":
                    lines.append(
                        f"  {_c('●', level_color(iss.level), color)} 第 {c.index + 1} 句 "
                        f"[{iss.level}] {iss.title}：{iss.detail}"
                    )
    lines.append(_c("  · 本工具为格律辅助，不代替作者判断。", C.GRAY, color))
    lines.append("")
    return "\n".join(lines)
