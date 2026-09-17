# -*- coding: utf-8 -*-
"""基于标准库 ``http.server`` 的本地服务。

刻意不引入 FastAPI / Flask —— 保持「零第三方依赖即可运行」，
让使用者 ``python server.py`` 就能起服务，不必先 pip install 一堆东西。

要换成别的框架，只需复用 :class:`poetry_checker.api.CheckerAPI`（框架无关）。
"""

from __future__ import annotations

import json
import mimetypes
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional, Tuple, Type
from urllib.parse import unquote, urlparse

from . import __version__
from .api import CheckerAPI

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MAX_BODY = 1 << 20  # 1 MB

# 端口被占用时依次尝试
PORT_CANDIDATES = (8765, 8766, 8767, 8768, 8080, 8000)

# Windows 的注册表常把 .js 映射成 text/plain，导致浏览器拒绝执行脚本。
# 这里显式覆盖，保证前端资源以正确的 MIME 类型送出。
mimetypes.init()
for _ext, _ctype in (
    (".html", "text/html"),
    (".css", "text/css"),
    (".js", "text/javascript"),
    (".mjs", "text/javascript"),
    (".json", "application/json"),
    (".svg", "image/svg+xml"),
    (".woff2", "font/woff2"),
):
    mimetypes.add_type(_ctype, _ext)


def _fail(status: int, message: str) -> bytes:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False).encode("utf-8")


def resolve_static(url_path: str) -> Optional[Path]:
    """把 URL 路径映射到 ``web/`` 下的真实文件，拒绝目录穿越。"""
    rel = unquote(urlparse(url_path).path).lstrip("/")
    if not rel or rel.endswith("/"):
        rel += "index.html"
    root = WEB_DIR.resolve()
    target = (WEB_DIR / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None  # 试图跳出 web/ 目录
    return target if target.is_file() else None


def make_handler(api: CheckerAPI) -> Type[BaseHTTPRequestHandler]:
    """把 API 包成一个 HTTP 请求处理器。"""

    class Handler(BaseHTTPRequestHandler):
        server_version = f"PoetryChecker/{__version__}"
        protocol_version = "HTTP/1.1"

        # ---------------------------------------------------- 工具

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, payload: str) -> None:
            self._send(status, payload.encode("utf-8"), "application/json; charset=utf-8")

        # ---------------------------------------------------- GET

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                resp = api.handle(path, "GET")
                self._json(resp.status, resp.to_json())
                return

            file = resolve_static(self.path)
            if file is None:
                self._send(404, _fail(404, "文件不存在"), "application/json; charset=utf-8")
                return
            ctype, _encoding = mimetypes.guess_type(str(file))
            if ctype and ctype.startswith("text/"):
                ctype += "; charset=utf-8"
            self._send(200, file.read_bytes(), ctype or "application/octet-stream")

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        # ---------------------------------------------------- POST

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0

            if length <= 0:
                self._json(400, _fail(400, "请求体为空").decode("utf-8"))
                return
            if length > MAX_BODY:
                self._json(413, _fail(413, "请求体过大").decode("utf-8"))
                return

            raw = self.rfile.read(length)
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json(400, _fail(400, f"请求体不是合法 JSON：{exc}").decode("utf-8"))
                return

            resp = api.handle(path, "POST", body)
            self._json(resp.status, resp.to_json())

        # ---------------------------------------------------- 日志

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            """静音：本地工具不需要每个请求都刷屏。"""

        def log_error(self, fmt: str, *args) -> None:  # noqa: A003
            pass

    return Handler


def bind(
    host: str,
    port: Optional[int],
    handler_cls: Type[BaseHTTPRequestHandler],
    fallback: bool = True,
) -> Tuple[ThreadingHTTPServer, int]:
    """绑定端口。

    先试 ``port``（若有），再依次试候选端口。
    双击启动的场景下，「换个端口能用」远好过「直接报错退出」。
    """
    candidates: list = []
    if port:
        candidates.append(port)
    if fallback:
        candidates += [p for p in PORT_CANDIDATES if p not in candidates]

    last: Optional[OSError] = None
    for p in candidates:
        try:
            return ThreadingHTTPServer((host, p), handler_cls), p
        except OSError as exc:  # 端口被占用
            last = exc
    raise SystemExit(f"无法绑定端口 {candidates}：{last}")


def serve(
    host: str = "127.0.0.1",
    port: Optional[int] = 8765,
    open_browser: bool = True,
    quiet: bool = False,
) -> int:
    """启动服务。返回进程退出码。"""
    if not WEB_DIR.is_dir():
        print(f"找不到前端目录：{WEB_DIR}")
        return 2

    api = CheckerAPI()
    httpd, actual_port = bind(host, port, make_handler(api))

    url = f"http://{host}:{actual_port}/"

    if not quiet:
        print()
        print("  诗词格律校验器  v" + __version__)
        print("  " + "─" * 52)
        if port and actual_port != port:
            print(f"  注意：端口 {port} 已被占用，已自动改用 {actual_port}")
        print(f"  服务已启动：  {url}")
        print(f"  接口：  POST {url}api/check")
        print(f"          GET  {url}api/meta    GET {url}api/cipai")
        print("  停服务：在这个窗口按 Ctrl+C，或直接关掉窗口")
        print("  " + "─" * 52)
        print()

    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        if not quiet:
            print("\n  已停止。")
    finally:
        httpd.server_close()
    return 0


def find_free_port(host: str = "127.0.0.1", start: int = 8765) -> int:
    """找一个可用的端口（供测试使用）。"""
    for p in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
            except OSError:
                continue
            return p
    raise RuntimeError("找不到可用端口")
