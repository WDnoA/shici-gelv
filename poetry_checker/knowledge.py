# -*- coding: utf-8 -*-
"""知识库加载与查询。

设计原则
--------
代码中**不出现**任何「某个字是平是仄」「哪个词牌多少字」之类的知识。
一切判定都以 ``知识库/`` 目录下的 JSON 为准。改数据即改标准，无需改代码。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple

# ---------------------------------------------------------------- 常量

平 = "平"
仄 = "仄"
平声大类 = ("上平声", "下平声")

PINGSHUI = "平水韵"
CILIN = "词林正韵"
XINYUN = "中华新韵"

DEFAULT_KB_ROOT = Path(__file__).resolve().parent.parent / "知识库"

_空白 = re.compile(r"[\s\u3000]+")


class KnowledgeError(Exception):
    """知识库读取失败。"""


# ---------------------------------------------------------------- 韵书


@dataclass
class RhymeBook:
    """一本韵书：记录「字 → {(韵部, 平仄)}」，并保留韵部内的字序。

    ``group_members`` 保留**传统韵书的排列次序**（常用字多在前），
    因此可以作为「改字建议」的粗略优先级——不需要另建词频表。
    """

    name: str
    note: str = ""
    # 字 -> {(韵部名, 平/仄)}
    entries: Dict[str, Set[Tuple[str, str]]] = field(default_factory=dict)
    # 韵部 -> [字]（按传统韵书顺序）
    group_members: Dict[str, List[str]] = field(default_factory=dict)

    # ---- 构建

    def add(self, char: str, group: str, tone: str) -> None:
        self.entries.setdefault(char, set()).add((group, tone))

    def add_many(self, chars: Iterable[str], group: str, tone: str) -> None:
        for ch in chars:
            self.add(ch, group, tone)

    def index_members(self) -> None:
        """在 entries 全部写入后建立「韵部 → 有序字表」。

        依 entries 的插入顺序（即韵书原本的排列次序），
        常用字多在前，可当作改字建议的粗略优先级。
        """
        self.group_members.clear()
        for char, pairs in self.entries.items():
            for group, _tone in sorted(pairs):
                members = self.group_members.setdefault(group, [])
                if char not in members:
                    members.append(char)

    # ---- 查询

    def groups(self, char: str) -> Set[str]:
        """该字所属的全部韵部。"""
        return {g for g, _ in self.entries.get(char, ())}

    def tones(self, char: str) -> Set[str]:
        """该字的全部平仄读法。空集表示本韵书未收录。"""
        return {t for _, t in self.entries.get(char, ())}

    def tone_in(self, char: str, group: str) -> Set[str]:
        return {t for g, t in self.entries.get(char, ()) if g == group}

    def known(self, char: str) -> bool:
        return char in self.entries

    def members(self, group: str) -> List[str]:
        """该韵部的全部字，按传统韵书次序。"""
        return list(self.group_members.get(group, ()))

    def all_groups(self) -> List[str]:
        return list(self.group_members)

    @property
    def size(self) -> int:
        return len(self.entries)

    def __contains__(self, char: str) -> bool:
        return char in self.entries


# ---------------------------------------------------------------- 主类


class KnowledgeBase:
    """整个知识库的统一入口。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

        self.rhyme_books: Dict[str, RhymeBook] = {}

        # 近体诗格律（原始 JSON）
        self.jinti: dict = {}
        # 字数类别("五言"/"七言") -> {(第二字, 收尾) -> 句式 dict}
        self.pattern_index: Dict[str, Dict[Tuple[str, str], dict]] = {}

        # 词谱
        self.cipai: Dict[str, dict] = {}
        self.cipai_alias: Dict[str, str] = {}  # 别名 -> 正名

        # 对仗词类
        self.char_category: Dict[str, Set[str]] = {}
        self.categories: Dict[str, str] = {}

        # 邻韵（平水韵）
        self.rhyme_neighbours: Dict[str, Set[str]] = {}
        # 词林正韵的半韵通押关系
        self.cilin_compat: Dict[str, Set[str]] = {}

        # 实际读过的数据文件。由 ``_read_json`` 自动记录，
        # 这样将来新增数据文件时不必回来维护一份文件清单。
        self.loaded_files: Set[Path] = set()

    # ------------------------------------------------------------ 加载

    @classmethod
    def load(cls, root: Optional[Path] = None) -> "KnowledgeBase":
        kb = cls(Path(root) if root else DEFAULT_KB_ROOT)
        if not kb.root.exists():
            raise KnowledgeError(f"找不到知识库目录：{kb.root}")
        kb._load_pingshui()
        kb._load_cilin()
        kb._load_jinti()
        kb._load_cipai()
        kb._load_duizhang()
        return kb

    def fingerprint(self) -> Tuple[Tuple[str, int, int], ...]:
        """数据文件的「指纹」：每个文件的 (路径, 字节数, 修改时间)。

        拿来判断磁盘上的知识库是否被改过。补录一个字的正确流程是
        「改 JSON → 重新加载」，长驻服务若不重新加载就会一直拿旧数据回答，
        使用者会以为补录失败了。故有此指纹，见 ``api.CheckerAPI._sync_kb``。
        """
        out: List[Tuple[str, int, int]] = []
        for path in sorted(self.loaded_files):
            try:
                st = path.stat()
                out.append((str(path), st.st_size, st.st_mtime_ns))
            except OSError:
                out.append((str(path), -1, -1))
        return tuple(out)

    # ---- 内部工具

    def _read_json(self, *parts: str) -> dict:
        path = self.root.joinpath(*parts)
        self.loaded_files.add(path)
        if not path.exists():
            raise KnowledgeError(f"缺少知识库文件：{path}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover
            raise KnowledgeError(f"{path} 不是合法 JSON：{exc}") from exc

    @staticmethod
    def _chars(blob: str) -> Iterator[str]:
        """把「东同铜桐」这样的字串拆成单字迭代器（忽略空白与标点）。"""
        for ch in _空白.sub("", blob or ""):
            if ch.isalnum() or "\u4e00" <= ch <= "\u9fff":
                yield ch

    # ------------------------------------------------------------ 平水韵

    def _load_pingshui(self) -> None:
        data = self._read_json("韵书", "平水韵.json")
        book = RhymeBook(name=data.get("名称", PINGSHUI), note="近体诗用韵标准")
        for group_cls, groups in data.get("韵部", {}).items():
            tone = 平 if group_cls in 平声大类 else 仄
            for name, blob in groups.items():
                book.add_many(self._chars(blob), group_cls + name, tone)
        book.index_members()
        self.rhyme_books[PINGSHUI] = book
        self.pingshui_raw = data

        # 邻韵
        nxt = data.get("邻韵", {}).get("组", [])
        for group in nxt:
            for g in group:
                self.rhyme_neighbours.setdefault(g, set()).update(
                    x for x in group if x != g
                )

    # ------------------------------------------------------------ 词林正韵

    def _load_cilin(self) -> None:
        data = self._read_json("韵书", "词林正韵.json")
        ps = self.rhyme_books[PINGSHUI]

        # 平水韵部 -> 平/仄
        ps_tone: Dict[str, str] = {}
        for group_cls, groups in self.pingshui_raw.get("韵部", {}).items():
            tone = 平 if group_cls in 平声大类 else 仄
            for name in groups:
                ps_tone[group_cls + name] = tone

        # 平水韵部 -> 字表（反向索引，供归并使用）
        # 注意：必须保持顺序。若用 set 会丢掉韵书原有的字序，
        # 「改字建议」的候选字就会乱成一团。
        ps_members: Dict[str, List[str]] = {}
        ps_seen: Dict[str, Set[str]] = {}
        for char, pairs in ps.entries.items():
            for g, _ in pairs:
                seen = ps_seen.setdefault(g, set())
                if char not in seen:
                    seen.add(char)
                    ps_members.setdefault(g, []).append(char)

        # 默认映射：平水韵部 -> [词林部]
        default_map: Dict[str, List[str]] = {}
        for part, tone_map in data.get("部映射", {}).items():
            for _tone_key, groups in tone_map.items():
                for g in groups:
                    default_map.setdefault(g, []).append(part)

        # 半韵覆盖：(平水韵部, 字) -> 词林部
        override: Dict[Tuple[str, str], str] = {}
        for ps_group, parts in data.get("半韵字表", {}).items():
            if ps_group == "说明" or not isinstance(parts, dict):
                continue
            for part, blob in parts.items():
                for ch in self._chars(blob):
                    override[(ps_group, ch)] = part

        book = RhymeBook(name=data.get("名称", CILIN), note="填词用韵标准")
        for ps_group, members in ps_members.items():
            tone = ps_tone.get(ps_group, "")
            parts = default_map.get(ps_group)
            for ch in members:
                target = override.get((ps_group, ch))
                if target:
                    book.add(ch, target, tone)
                elif parts:
                    for part in parts:
                        book.add(ch, part, tone)
                else:  # 理论上不会发生
                    book.add(ch, "未归部", tone)

        book.index_members()
        self.rhyme_books[CILIN] = book

        # 半韵通押关系
        for group in data.get("半韵通押组", {}).get("组", []):
            for g in group:
                self.cilin_compat.setdefault(g, set()).update(x for x in group if x != g)

    # ------------------------------------------------------------ 中华新韵

    @property
    def xinyun_available(self) -> bool:
        try:
            import pypinyin  # noqa: F401
        except ImportError:
            return False
        return True

    def load_xinyun(self) -> RhymeBook:
        """按需加载中华新韵（依赖 pypinyin）。"""
        if XINYUN in self.rhyme_books:
            return self.rhyme_books[XINYUN]
        try:
            from pypinyin import Style, lazy_pinyin
        except ImportError as exc:
            raise KnowledgeError(
                "使用「中华新韵」需要安装 pypinyin：pip install pypinyin"
            ) from exc

        data = self._read_json("韵书", "中华新韵.json")
        final_to_group: Dict[str, str] = {}
        for group, finals in data.get("韵母归属", {}).items():
            for f in finals:
                final_to_group[_norm_final(f)] = group

        book = RhymeBook(name=data.get("名称", XINYUN), note="普通话用韵标准")
        # 只为已出现过的字建立索引太麻烦，这里采取惰性查表的做法：
        # 先缓存映射关系，字 → 韵通过 resolve_xinyun() 动态计算。
        self._xinyun_final_map = final_to_group
        self._xinyun_cache: Dict[str, Set[Tuple[str, str]]] = {}
        self.rhyme_books[XINYUN] = book
        return book

    def xinyun_lookup(self, char: str) -> Set[Tuple[str, str]]:
        """返回中华新韵下该字的 {(韵部, 平仄)}。"""
        from pypinyin import Style, lazy_pinyin

        cache: Dict[str, Set[Tuple[str, str]]] = getattr(self, "_xinyun_cache", {})
        if char in cache:
            return cache[char]

        result: Set[Tuple[str, str]] = set()
        try:
            finals = lazy_pinyin(char, style=Style.FINALS, strict=False)
            initials = lazy_pinyin(char, style=Style.INITIALS, strict=False)
            toned = lazy_pinyin(char, style=Style.TONE3, strict=False)
        except Exception:  # pragma: no cover
            finals = initials = toned = []

        for fin, ini, tn in zip(finals, initials, toned):
            group = self._xinyun_group(ini, fin)
            tone = _tone_from_number(tn)
            if group and tone:
                result.add((group, tone))
        cache[char] = result
        return result

    def _xinyun_group(self, initial: str, final: str) -> Optional[str]:
        mapping = getattr(self, "_xinyun_final_map", {})
        if not mapping:
            self.load_xinyun()
            mapping = self._xinyun_final_map
        f = _norm_final(final)
        if f == "i" and initial in ("zh", "ch", "sh", "r", "z", "c", "s"):
            return mapping.get("-i")
        return mapping.get(f)

    # ------------------------------------------------------------ 近体诗格律

    def _load_jinti(self) -> None:
        data = self._read_json("格律", "近体诗格律.json")
        self.jinti = data
        for kind, entries in data.get("基本句式", {}).items():
            index: Dict[Tuple[str, str], dict] = {}
            for entry in entries:
                index[(entry["第二字"], entry["收尾"])] = entry
            self.pattern_index[kind] = index

    # ------------------------------------------------------------ 词谱

    def _load_cipai(self) -> None:
        data = self._read_json("词谱", "词牌格律.json")
        self.cipai = data.get("词牌", {})
        for name, spec in self.cipai.items():
            self.cipai_alias[name] = name
            for alias in spec.get("别名", []):
                self.cipai_alias.setdefault(alias, name)

    # ------------------------------------------------------------ 对仗词类

    def _load_duizhang(self) -> None:
        data = self._read_json("对仗", "词类分类.json")
        self.categories = data.get("门类", {})
        for name, blob in self.categories.items():
            for ch in self._chars(blob):
                self.char_category.setdefault(ch, set()).add(name)

    # ------------------------------------------------------------ 查询接口

    def book(self, name: str = PINGSHUI) -> RhymeBook:
        if name == XINYUN and name not in self.rhyme_books:
            self.load_xinyun()
        if name not in self.rhyme_books:
            raise KnowledgeError(f"未知韵书：{name}")
        return self.rhyme_books[name]

    def tones(self, char: str, book: str = PINGSHUI) -> Set[str]:
        """返回该字在指定韵书中的平仄集合（空集＝未收录）。"""
        if book == XINYUN:
            self.load_xinyun()
            return {t for _, t in self.xinyun_lookup(char)}
        return self.book(book).tones(char)

    def groups(self, char: str, book: str = PINGSHUI) -> Set[str]:
        if book == XINYUN:
            self.load_xinyun()
            return {g for g, _ in self.xinyun_lookup(char)}
        return self.book(book).groups(char)

    def same_group(self, a: str, b: str, book: str = PINGSHUI) -> bool:
        return bool(self.groups(a, book) & self.groups(b, book))

    def is_neighbour(self, a: str, b: str) -> bool:
        """两字所属韵部是否互为邻韵。"""
        for ga in self.groups(a):
            for gb in self.groups(b):
                if gb in self.rhyme_neighbours.get(ga, ()):
                    return True
        return False

    def categories_of(self, char: str) -> Set[str]:
        return self.char_category.get(char, set())

    def cipai_spec(self, name: str) -> Optional[dict]:
        real = self.cipai_alias.get(name) or self.cipai_alias.get(name.strip())
        return self.cipai.get(real) if real else None

    def cipai_real_name(self, name: str) -> Optional[str]:
        return self.cipai_alias.get(name.strip())

    def total_chars(self) -> int:
        return sum(b.size for b in self.rhyme_books.values())


# ---------------------------------------------------------------- 工具函数


def _norm_final(final: str) -> str:
    """统一韵母写法：ü/yu → v，去声调数字，去掉首尾空白。"""
    f = (final or "").strip().lower()
    f = re.sub(r"\d$", "", f)
    f = f.replace("ü", "v").replace("yu", "v")
    f = f.replace("uei", "ui").replace("iou", "iu").replace("uen", "un")
    return f


def _tone_from_number(toned: str) -> Optional[str]:
    """从 pypinyin 的 TONE3 结果（如 'dong1'）取平仄。"""
    m = re.search(r"(\d)$", toned or "")
    if not m:
        return None
    num = int(m.group(1))
    if num in (1, 2):
        return 平
    if num in (3, 4):
        return 仄
    return None  # 5 = 轻声
