# -*- coding: utf-8 -*-
"""HTTP 无关的 API 层。

这一层把「请求 → 校验 → 响应」的逻辑与具体的 Web 框架解耦：
:meth:`CheckerAPI.handle` 只吃 dict、吐 dict，因此可以直接挂在
``http.server``、FastAPI、Flask 或任何一个框架上。

这样做的理由：核心校验逻辑不应该被 Web 框架绑架。
将来若要把服务换成 FastAPI，只需新写一个十几行的适配器，本文件一行不用改。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from . import __version__, analyze
from .knowledge import CILIN, PINGSHUI, XINYUN, KnowledgeBase, KnowledgeError

# 单次请求允许的最大字数（防止有人贴一整本诗集进来）
MAX_TEXT_CHARS = 4000

SUPPORTED_BOOKS = (PINGSHUI, XINYUN)
SUPPORTED_SHAPES = ("auto", "诗", "词")


class ApiError(Exception):
    """带 HTTP 状态码的业务错误。"""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class Response:
    """框架无关的响应：一个状态码 + 一个可 JSON 序列化的字典。"""

    __slots__ = ("status", "payload")

    def __init__(self, status: int, payload: Dict[str, Any]) -> None:
        self.status = status
        self.payload = payload

    def to_json(self) -> str:
        return json.dumps(self.payload, ensure_ascii=False)


class CheckerAPI:
    """把知识库与校验器包成一组 HTTP 友好的方法。"""

    def __init__(self, kb: Optional[KnowledgeBase] = None) -> None:
        # 知识库加载有一定开销，进程内**只加载一次**，所有请求共享。
        self.kb = kb or KnowledgeBase.load()

    # ------------------------------------------------------------ 路由

    def handle(
        self, path: str, method: str = "GET", body: Optional[dict] = None
    ) -> Response:
        """入口。``path`` 可含查询串，会被忽略。"""
        route = path.split("?", 1)[0].strip()
        if len(route) > 1:
            route = route.rstrip("/")

        try:
            if route == "/api/meta":
                self._require(method, "GET")
                return self.meta()
            if route == "/api/cipai":
                self._require(method, "GET")
                return self.cipai()
            if route == "/api/check":
                self._require(method, "POST")
                return self.check(body or {})
        except ApiError as exc:
            return Response(exc.status, {"ok": False, "error": exc.message})

        return Response(404, {"ok": False, "error": f"未知接口：{route}"})

    @staticmethod
    def _require(method: str, expected: str) -> None:
        if method.upper() != expected:
            raise ApiError(405, f"该接口只接受 {expected} 请求")

    # ------------------------------------------------------------ 接口

    def meta(self) -> Response:
        """服务与知识库概况，供前端初始化。"""
        ping = self.kb.book(PINGSHUI)
        cilin = self.kb.book(CILIN)
        try:
            xinyun_ok = self.kb.xinyun_available
        except Exception:  # pragma: no cover
            xinyun_ok = False

        return Response(
            200,
            {
                "ok": True,
                "version": __version__,
                "books": list(SUPPORTED_BOOKS),
                "books_info": {
                    PINGSHUI: {"chars": ping.size, "note": "近体诗用韵标准（106 韵）"},
                    CILIN: {"chars": cilin.size, "note": "填词用韵标准（19 部）"},
                    XINYUN: {
                        "chars": None,
                        "note": "普通话用韵标准（14 韵）",
                        "available": xinyun_ok,
                    },
                },
                "cipai_count": len(self.kb.cipai),
                "categories": len(self.kb.categories),
                "max_text_chars": MAX_TEXT_CHARS,
            },
        )

    def cipai(self) -> Response:
        """已收录的词牌一览。"""
        items: List[Dict[str, Any]] = []
        for name, spec in sorted(
            self.kb.cipai.items(), key=lambda kv: kv[1].get("字数", 0)
        ):
            items.append(
                {
                    "name": name,
                    "aliases": list(spec.get("别名", [])),
                    "chars": spec.get("字数"),
                    "stanzas": spec.get("段数"),
                    "lines": len(spec.get("格律", [])),
                    "rhyme": spec.get("韵", ""),
                }
            )
        return Response(200, {"ok": True, "count": len(items), "cipai": items})

    def check(self, body: dict) -> Response:
        """校验一首诗词。"""
        if not isinstance(body, dict):
            raise ApiError(400, "请求体必须是 JSON 对象")

        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ApiError(400, "缺少 text 字段，或内容为空")

        if len(text) > MAX_TEXT_CHARS:
            raise ApiError(
                400, f"文本过长（{len(text)} 字），单次最多 {MAX_TEXT_CHARS} 字"
            )

        book = body.get("book") or PINGSHUI
        if book not in SUPPORTED_BOOKS:
            raise ApiError(400, f"不支持的韵书：{book}（可选 {'、'.join(SUPPORTED_BOOKS)}）")

        shape = body.get("shape") or "auto"
        if shape not in SUPPORTED_SHAPES:
            raise ApiError(400, f"不支持的 shape：{shape}（可选 {'、'.join(SUPPORTED_SHAPES)}）")

        if book == XINYUN and not self.kb.xinyun_available:
            raise ApiError(
                400,
                "使用「中华新韵」需要安装 pypinyin：pip install pypinyin",
            )

        try:
            result = analyze(text, kb=self.kb, book=book, shape=shape)
        except KnowledgeError as exc:
            raise ApiError(500, f"知识库错误：{exc}") from exc
        except Exception as exc:  # pragma: no cover
            raise ApiError(500, f"校验失败：{exc}") from exc

        return Response(200, {"ok": True, "result": result.to_dict()})
