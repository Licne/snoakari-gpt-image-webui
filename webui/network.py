#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网络层：出站 opener（代理/证书兜底）、上游请求"""
import ssl
import urllib.request

REQUEST_TIMEOUT = 600

# CA 证书兜底：系统证书库过旧时（如缺 Let's Encrypt 新根证书）优先用 certifi，
# 未安装 certifi 则回落系统默认，行为与旧版一致
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = None

def _make_opener(proxy):
    """出站 opener：proxy 为空=直连（不走系统/环境代理），否则走指定 http(s) 代理"""
    handlers = []
    if _SSL_CTX is not None:
        handlers.append(urllib.request.HTTPSHandler(context=_SSL_CTX))
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


_opener = _make_opener("")


def set_proxy(proxy):
    global _opener
    _opener = _make_opener((proxy or "").strip())


def open_url(req, timeout=REQUEST_TIMEOUT):
    return _opener.open(req, timeout=timeout)


def api_request(url, headers, data=None, timeout=REQUEST_TIMEOUT):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    return open_url(req, timeout=timeout)

