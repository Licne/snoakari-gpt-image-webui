#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""前端页面装配：读取 web/ 下静态文件并注入版本号（启动时一次加载）"""
import os

from .version import APP_VER

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def _read(name):
    with open(os.path.join(WEB_DIR, name), encoding="utf-8") as f:
        return f.read()


# 启动时装配页面：css/js 以内联方式进 html（保持单请求返回整页，前端无需构建）
INDEX_HTML = (_read("index.html")
              .replace("<!--STYLE-->", "<style>\n" + _read("style.css") + "\n</style>")
              .replace("<!--SCRIPT-->", "<script>\n" + _read("app.js") + "\n</script>")
              .replace("__APP_VER__", APP_VER))
