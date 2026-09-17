# -*- coding: utf-8 -*-
"""基于标准库 ``http.server`` 的本地服务。

刻意不引入 FastAPI / Flask —— 保持「零第三方依赖即可运行」，
让使用者 ``python server.py`` 就能起服务，不必先 pip install 一堆东西。

要换成别的框架，只需复用 :class:`poetry_checker.api.CheckerAPI`（框架无关）。
"""

from __future__ import annotations

import html as _html
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


def not_found_page(requested: str) -> bytes:
    """静态文件缺失时给出的**可诊断**页面。

    这个页面是被真实故障逼出来的：开发过程中，一个指向已删除临时目录的
    残留进程占着端口，结果**连首页都打不开**，浏览器里只有一句
    ``{"ok": false, "error": "文件不存在"}``，完全看不出发生了什么。

    使用者能遇到的同类情形：把项目文件夹挪了位置、改了名，或删过一份解压副本
    却忘了停服务。所以这里必须把「服务实际在用的目录」摆出来。
    """
    web = WEB_DIR
    exists = web.is_dir()
    listing = ""
    if exists:
        names = sorted(p.name for p in web.iterdir() if p.is_file())
        listing = "、".join(names) if names else "（空目录）"

    safe_path = _html.escape(requested)
    status_cls = "good" if exists else "bad"
    status_txt = "存在" if exists else "不存在"
    listing_html = (
        f'<div>其中的文件：<code>{_html.escape(listing)}</code></div>' if exists else ""
    )

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>找不到页面 · 诗词格律校验器</title>
<style>
 body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
      background:#f6f3ed;color:#2b2723;max-width:680px;margin:8vh auto;
      padding:0 24px;line-height:1.85}}
 h1{{font-size:20px;color:#8c2f39;margin-bottom:14px}}
 code{{background:#fffdf9;border:1px solid #e7e1d7;border-radius:4px;
      padding:1px 6px;font-size:13px;word-break:break-all}}
 .box{{background:#fffdf9;border:1px solid #e7e1d7;border-radius:10px;
      padding:14px 20px;margin:18px 0}}
 .box div{{margin:4px 0}}
 .bad{{color:#b02a2a;font-weight:600}} .good{{color:#2f7d4f;font-weight:600}}
 ol{{padding-left:1.4em}} li{{margin:6px 0}}
 a{{color:#8c2f39}}
</style></head><body>
<h1>找不到「{safe_path}」</h1>

<div class="box">
  <div>服务在用的前端目录：</div>
  <div><code>{_html.escape(str(web))}</code></div>
  <div>该目录：<span class="{status_cls}">{status_txt}</span></div>
  {listing_html}
</div>

<p>连首页都打不开，通常只有两个原因：</p>
<ol>
  <li><b>项目文件夹被移动、重命名或删除了</b>，而服务还指向旧位置。</li>
  <li><b>端口上跑着另一个残留进程</b>——例如你曾解压过一份副本、
      删掉了那份，但它的服务没有停。</li>
</ol>

<p>处理办法：</p>
<ol>
  <li>双击 <code>停止校验器.bat</code>，把所有相关服务停掉；</li>
  <li>重新双击 <code>启动校验器.bat</code>；</li>
  <li>若仍打不开，请确认 <code>web/</code> 目录还在项目根目录下
      （里面有 <code>index.html</code>、<code>style.css</code>、<code>app.js</code>）。</li>
</ol>

<p>接口本身是好的，可直接验证：<a href="/api/meta">/api/meta</a></p>
</body></html>"""
    return doc.encode("utf-8")


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

            # 页面里已声明 SVG 图标；浏览器仍会顺手要一次 /favicon.ico。
            # 回 204，省得控制台里多一条刺眼的红色 404。
            if path == "/favicon.ico":
                self._send(204, b"", "image/x-icon")
                return

            file = resolve_static(self.path)
            if file is None:
                # 不用 JSON —— 这是浏览器在看页面，得给能看懂的东西
                self._send(404, not_found_page(path), "text/html; charset=utf-8")
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
        print(f"  前端目录：    {WEB_DIR}")
        print("  停服务：在这个窗口按 Ctrl+C，或直接关掉窗口")
        print("  " + "─" * 52)
        print()
        print("  提示：服务运行期间请不要移动或重命名本文件夹，")
        print("        否则前端文件会找不到（重启即可恢复）。")
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
