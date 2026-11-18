#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务器层：QuietServer + Handler 组装 + 启动流程"""
import argparse
import os
import threading
import webbrowser
from http.server import ThreadingHTTPServer

from .api import ApiMixin
from .network import set_proxy
from .storage import OUTPUT_DIR, load_config, migrate_v1
from .version import APP_VER


class QuietServer(ThreadingHTTPServer):
    """ThreadingHTTPServer + 静默浏览器断连噪音（handle_error 定义在 Server 类上）"""
    daemon_threads = True

    def handle_error(self, request, client_address):
        import sys
        exc = sys.exc_info()[1]
        # 浏览器断开 keep-alive 连接属正常现象（10053/10054），静默处理
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError,
                            BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class Handler(ApiMixin):
    pass


def main():
    parser = argparse.ArgumentParser(description="gpt-image 本地 WebUI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    args = parser.parse_args()

    moved = migrate_v1()
    if moved:
        print(f"[gpt-image WebUI] 已自动迁移 v1 数据到 data/ 目录：{', '.join(moved)}")
    cfg = load_config()
    set_proxy(cfg.get("proxy"))
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    try:
        httpd = QuietServer((args.host, args.port), Handler)
    except OSError as e:
        print(f"[gpt-image WebUI] 启动失败：端口 {args.port} 被占用（{e}）")
        print("[gpt-image WebUI] 常见原因：另一个副本还在运行（例如桌面旧版）。请先关闭它的黑色窗口，再重试本副本；")
        print("[gpt-image WebUI] 或者换端口启动：python app.py --port 9000")
        raise SystemExit(1)
    httpd.app_config = cfg  # type: ignore[attr-defined]
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
    print(f"[gpt-image WebUI] v{APP_VER} 服务已启动：{url}")
    print(f"[gpt-image WebUI] 默认模型：{cfg['model']}  历史保存于：{OUTPUT_DIR}")
    if cfg.get("proxy"):
        print(f"[gpt-image WebUI] 出站代理：{cfg['proxy']}")
    print("[gpt-image WebUI] 正在自动打开浏览器……（若没有弹出，请手动访问上面的地址）")
    print("[gpt-image WebUI] 保持本窗口开着即可使用；关闭本窗口或 Ctrl+C 退出")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[gpt-image WebUI] 已退出")
