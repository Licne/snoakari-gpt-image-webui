#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SnoAkari gpt-image WebUI v2 启动入口

用法：
    python app.py            # 默认监听 http://127.0.0.1:8787
    python app.py --port 9000
    python app.py --host 0.0.0.0   # 允许局域网访问（注意密钥安全）

架构（v2.0 起）：
    app.py            启动入口
    webui/server.py   服务器与路由组装
    webui/api.py      /api/* 端点
    webui/generate.py 生成核心（上游调用/落盘/后台重跑）
    webui/jobs.py     任务注册表与中止
    webui/network.py  出站网络（代理/证书兜底）
    webui/storage.py  配置/收藏/常量（数据在 data/ 目录）
    webui/web/        前端源文件（html/css/js，启动时内联装配）
"""
from webui.server import main

if __name__ == "__main__":
    main()
