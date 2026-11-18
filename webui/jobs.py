#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务层：后台任务注册表、中止注册表、下载与响应读取"""
import json
import socket
import threading
import time
import urllib.request

from .network import REQUEST_TIMEOUT, _opener
from .version import APP_VER

_ACTIVE_JOBS = {}          # job_id -> {"resp": HTTPResponse|None, "cancelled": bool}
_BG_JOBS = {}              # job_id -> 后台任务信息（供前端轮询进度）


def _bg_register(job_id, payload, cfg):
    if not job_id:
        return
    prompt = (payload.get("prompt") or "")
    with _JOBS_LOCK:
        _BG_JOBS[job_id] = {
            "id": job_id,
            "mode": payload.get("mode", "gen"),
            "model": payload.get("model") or cfg.get("model") or "",
            "size": (payload.get("size") or "auto"),
            "n": payload.get("n") or 1,
            "pshow": prompt[:30] + ("…" if len(prompt) > 30 else ""),
            "t0": time.time(), "t_end": None,
            "status": "running", "phase": "", "error": "", "images": [], "elapsed": 0,
            "bg": False,   # 仅点“转入后台”后进入任务面板
            "payload": dict(payload),  # 完整参数：失败后可供重试（成功/中止时释放）
        }
        done = [k for k, v in _BG_JOBS.items() if v["status"] != "running"]
        while len(_BG_JOBS) > 60 and done:
            _BG_JOBS.pop(done.pop(0), None)


def _bg_finish(job_id, status, images=None, elapsed=None, error=""):
    if not job_id:
        return
    with _JOBS_LOCK:
        e = _BG_JOBS.get(job_id)
        if e is None:
            return
        e["status"] = status
        e["phase"] = ""
        e["t_end"] = time.time()
        e["images"] = images or []
        e["error"] = error or ""
        e["elapsed"] = elapsed if elapsed is not None else round(e["t_end"] - e["t0"], 1)
        if status != "failed":
            e.pop("payload", None)  # 只有失败任务保留参数供重试


def _bg_phase(job_id, phase):
    """更新进行中任务的阶段（如 downloading：URL 结果下载中），不改状态本身"""
    if not job_id:
        return
    with _JOBS_LOCK:
        e = _BG_JOBS.get(job_id)
        if e is not None:
            e["phase"] = phase

_JOBS_LOCK = threading.Lock()


def _register_job(job_id):
    if not job_id:
        return
    with _JOBS_LOCK:
        _ACTIVE_JOBS[job_id] = {"resp": None, "cancelled": False}


def _register_resp(job_id, resp):
    if not job_id:
        return
    with _JOBS_LOCK:
        e = _ACTIVE_JOBS.get(job_id)
        if e is not None:
            e["resp"] = resp


def _kill_response(resp):
    """尽力掐断上游连接：先 shutdown 唤醒阻塞中的读线程，再 close"""
    try:
        sock = resp.fp.raw._sock
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
    except Exception:
        pass
    try:
        resp.close()
    except Exception:
        pass


def read_response(resp, job_id=""):
    """分块读取上游响应体；job_id 存在时每块之间检查中止标志"""
    buf = bytearray()
    try:
        while True:
            if job_id:
                with _JOBS_LOCK:
                    e = _ACTIVE_JOBS.get(job_id)
                    if e is not None and e["cancelled"]:
                        raise ValueError("已中止")
            try:
                chunk = resp.read(65536)
            except Exception:
                if job_id:
                    with _JOBS_LOCK:
                        e = _ACTIVE_JOBS.get(job_id)
                        if e is not None and e["cancelled"]:
                            raise ValueError("已中止") from None
                raise
            if not chunk:
                break
            buf += chunk
    finally:
        # 注意：不在此处清理 _ACTIVE_JOBS，任务注册表生命周期由 generate handler 统一管理，
        # 保证下载结果图阶段仍可中止
        try:
            resp.close()
        except Exception:
            pass
    return json.loads(bytes(buf).decode("utf-8"))


def _job_cancelled(job_id):
    if not job_id:
        return False
    with _JOBS_LOCK:
        e = _ACTIVE_JOBS.get(job_id)
        return e is not None and e["cancelled"]


def fetch_bytes(url, job_id=""):
    if _job_cancelled(job_id):
        raise ValueError("已中止")
    req = urllib.request.Request(url, headers={"User-Agent": f"gpt-image-webui/{APP_VER}"})
    r = _opener.open(req, timeout=REQUEST_TIMEOUT)
    # 注册下载 socket，让中止能掐断阻塞中的下载
    if job_id:
        with _JOBS_LOCK:
            e = _ACTIVE_JOBS.get(job_id)
            if e is not None and e["cancelled"]:
                r.close()
                raise ValueError("已中止")
            if e is not None:
                e["resp"] = r
    try:
        data = r.read()
    finally:
        if job_id:
            with _JOBS_LOCK:
                e = _ACTIVE_JOBS.get(job_id)
                if e is not None and e.get("resp") is r:
                    e["resp"] = None
        try:
            r.close()
        except Exception:
            pass
    if _job_cancelled(job_id):
        raise ValueError("已中止")
    return data


