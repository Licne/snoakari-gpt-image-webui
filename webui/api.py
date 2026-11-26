#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""API 路由层：GET/POST 端点（Handler 方法以 Mixin 形式提供）"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler

from . import collections as CL
from .generate import do_generate, run_bg_generate
from .jobs import (_ACTIVE_JOBS, _BG_JOBS, _JOBS_LOCK, _bg_register,
                   _bg_finish, _kill_response)
from .network import _make_opener, set_proxy
from .storage import (BACKGROUNDS, BASE_DIR, FORMATS, IMG_MIMES, MODELS,
                       MODERATIONS, OUTPUT_DIR, QUALITIES, SIZE_GROUPS, SIZE_PRESETS,
                       _read_disk_config, _write_disk_config, log,
                       mask_key, save_config_file)
from .version import APP_VER
from .webindex import INDEX_HTML


def _fs_safe(s):
    """目录名安全化：替换 Windows/Linux 非法字符，中文保留"""
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(s or "")).strip("_") or "未命名"


def _open_folder(path):
    """跨平台打开本地目录（导出完成后唤起文件管理器）"""
    try:
        if os.name == "nt":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


class ApiMixin(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"gpt-image-webui/{APP_VER}"

    def log_message(self, fmt, *args):
        pass  # 静默访问日志

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra_headers=None, cache_control="no-store"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        if ctype:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.send_header("X-Internal-Build-Tag", "76.105.99.110.101")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            try:
                self.wfile.write(body)
            except OSError:
                log("浏览器连接已断开，跳过响应回写")

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path.startswith("/outputs/"):
            name = os.path.basename(urllib.parse.unquote(self.path[len("/outputs/"):]))
            ext = os.path.splitext(name)[1].lower()
            if ext not in IMG_MIMES or not re.fullmatch(r"[\w.-]+", name):
                return self._send(404, {"error": "not found"})
            path = os.path.join(OUTPUT_DIR, name)
            if not os.path.isfile(path):
                return self._send(404, {"error": "not found"})
            st = os.stat(path)
            etag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
            if self.headers.get("If-None-Match") == etag:
                return self._send(304, b"", ctype=None,
                                  extra_headers={"ETag": etag},
                                  cache_control="private, max-age=86400")
            with open(path, "rb") as f:
                self._send(200, f.read(), IMG_MIMES[ext],
                           extra_headers={"ETag": etag},
                           cache_control="private, max-age=86400")
        elif self.path.startswith("/assets/"):
            from .webindex import ASSETS
            name = os.path.basename(urllib.parse.unquote(self.path[len("/assets/"):]))
            if name in ASSETS:
                mime = "image/webp" if name.endswith(".webp") else "image/png"
                return self._send(200, ASSETS[name], mime)
            return self._send(404, {"error": "not found"})
        elif self.path == "/api/config":
            cfg = self.server.app_config
            self._send(200, {"model": cfg["model"], "models": cfg.get("models") or MODELS,
                             "sizes": SIZE_PRESETS, "size_groups": SIZE_GROUPS,
                             "qualities": QUALITIES, "backgrounds": BACKGROUNDS,
                             "formats": FORMATS, "moderations": MODERATIONS,
                             "group": cfg.get("group") or "",
                             "groups": [g["name"] for g in (cfg.get("groups") or [])]})
        elif self.path == "/api/groups":
            cfg = self.server.app_config
            gs = [{"name": g["name"], "base_url": g["base_url"],
                   "key_masked": mask_key(g["api_key"]) if g["api_key"] else "",
                   "has_key": bool(g["api_key"]), "models": g["models"],
                   "proxy": g.get("proxy") or ""}
                  for g in (cfg.get("groups") or [])]
            self._send(200, {"groups": gs, "active": cfg.get("group") or "",
                             "model": cfg["model"], "models": cfg.get("models") or []})
        elif self.path == "/api/settings":
            cfg = self.server.app_config
            self._send(200, {"base_url": cfg["base_url"], "model": cfg["model"],
                             "key_masked": mask_key(cfg["api_key"]),
                             "proxy": cfg.get("proxy") or "",
                             "env_key": bool(os.environ.get("GPT_IMAGE_API_KEY", "").strip())})
        elif self.path == "/api/jobs":
            with _JOBS_LOCK:
                jobs = [{k: v for k, v in e.items() if k != "payload"}
                        for e in _BG_JOBS.values() if e.get("bg")]
            jobs.sort(key=lambda x: (0 if x["status"] == "running" else 1, -(x["t_end"] or x["t0"])))
            self._send(200, {"jobs": jobs[:30]})
        elif self.path.startswith("/api/history"):
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            fav_only = (qs.get("fav") or [""])[0] == "1"
            cid = (qs.get("cid") or [""])[0].strip()
            favs = CL.default_items()
            try:
                sel = CL.items_of(cid) if cid else (favs if fav_only else None)
            except ValueError:
                return self._send(200, {"error": "收藏夹不存在"})
            items = []
            for fn in os.listdir(OUTPUT_DIR):
                ext = os.path.splitext(fn)[1].lower()
                if ext in IMG_MIMES:
                    if sel is not None and fn not in sel:
                        continue
                    st = os.stat(os.path.join(OUTPUT_DIR, fn))
                    items.append({"name": fn, "url": f"/outputs/{fn}",
                                  "size": st.st_size, "mtime": st.st_mtime,
                                  "fav": fn in favs})
            items.sort(key=lambda x: -x["mtime"])
            self._send(200, items[:500] if sel is not None else items[:200])
        elif self.path == "/api/collections":
            self._send(200, CL.list_collections())
        elif self.path.startswith("/api/collections/export"):
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            cid = (qs.get("id") or ["all"])[0]
            try:
                data = CL.export_zip(cid)
            except ValueError as e:
                return self._send(200, {"error": str(e)})
            self._send(200, data, "application/zip",
                       {"Content-Disposition": 'attachment; filename="snoakari-collections.zip"'})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/export":
            # 导出：把 data 中的图片复制到 exports/（不动原文件），完成后打开目录
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                export_dir = os.path.join(BASE_DIR, "exports")
                os.makedirs(export_dir, exist_ok=True)
                name = os.path.basename((p.get("name") or "").strip())
                if name:
                    if not re.fullmatch(r"[\w.-]+", name) or os.path.splitext(name)[1].lower() not in IMG_MIMES:
                        return self._send(200, {"error": "非法文件名"})
                    src = os.path.join(OUTPUT_DIR, name)
                    if not os.path.isfile(src):
                        return self._send(200, {"error": "文件不存在"})
                    shutil.copy2(src, os.path.join(export_dir, name))
                    log(f"导出图片：outputs/{name} → exports/")
                    _open_folder(export_dir)
                    return self._send(200, {"ok": True, "dir": "exports", "count": 1})
                cid = (p.get("cid") or "").strip()
                if not cid:
                    return self._send(200, {"error": "缺少 name 或 cid"})
                cols = CL.list_collections()["collections"]
                targets = [c for c in cols if cid in ("all", c["id"])]
                if not targets:
                    return self._send(200, {"error": "合集不存在"})
                total = 0
                for c in targets:
                    names = [fn for fn in CL.items_of(c["id"])
                             if os.path.isfile(os.path.join(OUTPUT_DIR, fn))]
                    n = 0
                    if names:
                        sub = os.path.join(export_dir, _fs_safe(c["name"]))
                        os.makedirs(sub, exist_ok=True)
                        for fn in names:
                            shutil.copy2(os.path.join(OUTPUT_DIR, fn), os.path.join(sub, fn))
                            n += 1
                    total += n
                    log(f"导出合集「{c['name']}」：{n} 张 → exports/{_fs_safe(c['name'])}/")
                if not total:
                    return self._send(200, {"error": "合集内没有可导出的图片"})
                _open_folder(export_dir if cid == "all" else os.path.join(export_dir, _fs_safe(targets[0]["name"])))
                self._send(200, {"ok": True, "dir": "exports", "count": total})
            except Exception as ex:
                self._send(200, {"error": f"{type(ex).__name__}: {ex}"})
            return
        if path == "/api/settings":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                base_url = (payload.get("base_url") or "").strip()
                model = (payload.get("model") or "").strip()
                api_key = (payload.get("api_key") or "").strip()
                if not base_url.startswith("http"):
                    return self._send(200, {"error": "中转站地址必须以 http(s):// 开头"})
                if not model:
                    return self._send(200, {"error": "默认模型不能为空"})
                proxy = (payload.get("proxy") or "").strip()
                if proxy and not (proxy.startswith("http://") or proxy.startswith("https://")):
                    return self._send(200, {"error": "代理地址需以 http:// 或 https:// 开头（socks 暂不支持）"})
                save_config_file(base_url, model, api_key or None, proxy=proxy)
                if api_key:
                    self.server.app_config["api_key"] = api_key
                self.server.app_config["base_url"] = base_url.rstrip("/")
                self.server.app_config["model"] = model
                self.server.app_config["proxy"] = proxy
                set_proxy(proxy)
                cfg = self.server.app_config
                log(f"设置已更新：base_url={cfg['base_url']} 默认模型={cfg['model']} 代理={cfg.get('proxy') or '直连'}")
                self._send(200, {"ok": True, "base_url": cfg["base_url"], "model": cfg["model"],
                                 "key_masked": mask_key(cfg["api_key"])})
            except Exception as e:
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            return

        if path == "/api/groups":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                raw = p.get("groups")
                if not isinstance(raw, list) or not raw:
                    return self._send(200, {"error": "至少需要一个分组"})
                old_groups = {g["name"]: g for g in (self.server.app_config.get("groups") or [])}
                groups, seen = [], set()
                for g in raw:
                    if not isinstance(g, dict):
                        continue
                    name = (g.get("name") or "").strip()
                    url = (g.get("base_url") or "").strip().rstrip("/")
                    if not name:
                        return self._send(200, {"error": "分组名称不能为空"})
                    if name in seen:
                        return self._send(200, {"error": f"分组名称重复：{name}"})
                    if not url.startswith("http"):
                        return self._send(200, {"error": f"分组「{name}」的地址必须以 http(s):// 开头"})
                    seen.add(name)
                    key = (g.get("api_key") or "").strip()
                    if not key and name in old_groups:          # 留空 = 沿用旧密钥
                        key = old_groups[name]["api_key"]
                    groups.append({"name": name, "base_url": url, "api_key": key,
                                   "models": [str(m).strip() for m in (g.get("models") or []) if str(m).strip()],
                                   "proxy": (g.get("proxy") or "").strip()})
                if not groups:
                    return self._send(200, {"error": "没有有效分组"})
                disk = _read_disk_config()
                disk["groups"] = groups
                active = (disk.get("active_group") or self.server.app_config.get("group") or "").strip()
                if active not in [g["name"] for g in groups]:
                    active = groups[0]["name"]
                disk["active_group"] = active
                # 激活组字段变化时同步运行时与顶层
                cfg = self.server.app_config
                ag = next(g for g in groups if g["name"] == active)
                cfg["groups"] = groups
                cfg["group"] = active
                if ag["api_key"]:
                    cfg["api_key"] = ag["api_key"]
                cfg["base_url"] = ag["base_url"]
                cfg["proxy"] = ag["proxy"]
                cfg["models"] = ag["models"] or list(MODELS)
                if cfg["model"] not in cfg["models"]:
                    cfg["model"] = cfg["models"][0] if cfg["models"] else cfg["model"]
                set_proxy(cfg["proxy"])
                disk.update({"api_key": cfg["api_key"], "base_url": cfg["base_url"],
                             "model": cfg["model"], "proxy": cfg["proxy"]})
                _write_disk_config(disk)
                log(f"分组已保存：{len(groups)} 组，当前={active}，模型 {len(cfg['models'])} 个")
                self._send(200, {"ok": True, "active": active,
                                 "groups": [g["name"] for g in groups]})
            except Exception as e:
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            return

        if path == "/api/group/switch":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                name = (p.get("name") or "").strip()
                groups = self.server.app_config.get("groups") or []
                g = next((x for x in groups if x["name"] == name), None)
                if g is None:
                    return self._send(200, {"error": "分组不存在（先在设置里保存）"})
                if not g["api_key"]:
                    return self._send(200, {"error": "该分组未配置密钥"})
                models = g["models"] or list(MODELS)
                cfg = self.server.app_config
                cfg["group"] = name
                cfg["base_url"] = g["base_url"]
                cfg["api_key"] = g["api_key"]
                cfg["proxy"] = g["proxy"]
                cfg["models"] = models
                if cfg["model"] not in models:
                    cfg["model"] = models[0]
                set_proxy(g["proxy"])
                disk = _read_disk_config()
                disk.update({"active_group": name, "base_url": g["base_url"], "api_key": g["api_key"],
                             "model": cfg["model"], "proxy": g["proxy"]})
                _write_disk_config(disk)
                log(f"已切换分组：{name}（{g['base_url']}，模型 {len(models)} 个）")
                self._send(200, {"ok": True, "group": name, "model": cfg["model"], "models": models})
            except Exception as e:
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            return

        if path == "/api/models":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                url = (p.get("base_url") or "").strip().rstrip("/")
                key = (p.get("api_key") or "").strip()
                proxy = (p.get("proxy") or "").strip()
                if not url.startswith("http"):
                    return self._send(200, {"error": "地址必须以 http(s):// 开头"})
                if not key:
                    gname = (p.get("name") or "").strip()
                    g = next((x for x in (self.server.app_config.get("groups") or []) if x["name"] == gname), None)
                    if g:
                        key = g["api_key"]
                if not key:
                    return self._send(200, {"error": "缺少 API 密钥"})
                opener = _make_opener(proxy)
                req = urllib.request.Request(url + "/v1/models",
                                             headers={"Authorization": f"Bearer {key}"}, method="GET")
                with opener.open(req, timeout=30) as r:
                    data = json.loads(r.read().decode("utf-8"))
                ids = [str(it.get("id")) for it in (data.get("data") or []) if it.get("id")]
                self._send(200, {"ok": True, "models": sorted(ids)})
            except Exception as e:
                self._send(200, {"error": f"拉取失败：{e}"})
            return

        if path == "/api/fav":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                raw = (p.get("name") or "").strip()
                name = os.path.basename(raw)
                if raw != name or not re.fullmatch(r"[\w.-]+", name) or os.path.splitext(name)[1].lower() not in IMG_MIMES:
                    return self._send(200, {"error": "非法文件名"})
                if not os.path.isfile(os.path.join(OUTPUT_DIR, name)):
                    return self._send(200, {"error": "文件不存在"})
                want = bool(p.get("fav"))
                cid = CL.load_collections()["default_id"]
                CL.set_item(cid, name, want)
                log(f"收藏{'添加' if want else '取消'}：{name}")
                self._send(200, {"ok": True, "fav": want})
            except Exception as e:
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            return

        if path == "/api/rename":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                raw_n, raw_t = (p.get("name") or "").strip(), (p.get("to") or "").strip()
                name, to = os.path.basename(raw_n), os.path.basename(raw_t)
                if raw_n != name or not re.fullmatch(r"[\w.-]+", name) or os.path.splitext(name)[1].lower() not in IMG_MIMES:
                    return self._send(200, {"error": "原文件名非法"})
                if raw_t != to or not re.fullmatch(r"[\w.-]+", to) or os.path.splitext(to)[1].lower() not in IMG_MIMES:
                    return self._send(200, {"error": "新文件名非法（仅限字母数字下划线连字符，需带图片扩展名，不能带路径）"})
                src_p, dst_p = os.path.join(OUTPUT_DIR, name), os.path.join(OUTPUT_DIR, to)
                if not os.path.isfile(src_p):
                    return self._send(200, {"error": "文件不存在"})
                if os.path.normcase(src_p) != os.path.normcase(dst_p) and os.path.exists(dst_p):
                    return self._send(200, {"error": "已存在同名文件"})
                os.rename(src_p, dst_p)
                CL.rename_file(name, to)
                log(f"重命名：outputs/{name} -> outputs/{to}")
                self._send(200, {"ok": True, "name": to, "url": f"/outputs/{to}"})
            except Exception as e:
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            return

        if path == "/api/collections/create":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8"))
                self._send(200, CL.create_collection(p.get("name")))
            except ValueError as e:
                self._send(200, {"error": str(e)})
            except Exception as e:
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            return

        if path == "/api/collections/rename":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8"))
                self._send(200, CL.rename_collection((p.get("id") or "").strip(), p.get("name")))
            except ValueError as e:
                self._send(200, {"error": str(e)})
            except Exception as e:
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            return

        if path == "/api/collections/delete":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8"))
                self._send(200, CL.delete_collection((p.get("id") or "").strip()))
            except ValueError as e:
                self._send(200, {"error": str(e)})
            except Exception as e:
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            return

        if path == "/api/collections/item":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8"))
                cid = (p.get("id") or "").strip()
                name = (p.get("name") or "").strip()
                if not re.fullmatch(r"[\w.-]+", name) or os.path.splitext(name)[1].lower() not in IMG_MIMES:
                    return self._send(200, {"error": "非法文件名"})
                self._send(200, CL.set_item(cid, name, bool(p.get("add"))))
            except ValueError as e:
                self._send(200, {"error": str(e)})
            except Exception as e:
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            return

        if path == "/api/collections/import_image":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length > 60 * 1024 * 1024:
                    return self._send(200, {"error": "图片过大（>60MB）"})
                qs = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                raw_name = (qs.get("name") or [""])[0]
                if raw_name != os.path.basename(raw_name) or not raw_name.strip():
                    return self._send(200, {"error": "非法文件名"})
                final, same = CL.import_image_bytes(self.rfile.read(length), raw_name)
                log(f"导入图片：{raw_name} -> {final}" + ("（内容重复，已复用）" if same else ""))
                self._send(200, {"name": final, "dup": same})
            except ValueError as e:
                self._send(200, {"error": str(e)})
            except Exception as e:
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            return

        if path == "/api/collections/import":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length > 500 * 1024 * 1024:
                    return self._send(200, {"error": "收藏包过大（>500MB）"})
                self._send(200, CL.import_zip(self.rfile.read(length)))
            except ValueError as e:
                self._send(200, {"error": str(e)})
            except Exception as e:
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            return

        if path == "/api/cancel":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                jid = (p.get("job_id") or "").strip()
                with _JOBS_LOCK:
                    e = _ACTIVE_JOBS.get(jid)
                    cancelled = bool(e)
                    if e:
                        e["cancelled"] = True
                        resp = e["resp"]
                    else:
                        resp = None
                if resp is not None:
                    _kill_response(resp)
                log(f"中止请求 job={jid or '空'}：{'已中止' if cancelled else '无进行中的任务'}")
                self._send(200, {"ok": True, "cancelled": cancelled})
            except Exception as ex:
                self._send(200, {"error": f"{type(ex).__name__}: {ex}"})
            return

        if path == "/api/jobs/background":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                jid = (p.get("job_id") or "").strip()
                with _JOBS_LOCK:
                    e = _BG_JOBS.get(jid)
                    if e is None:
                        return self._send(200, {"error": "任务不存在或尚未登记"})
                    e["bg"] = True
                self._send(200, {"ok": True})
            except Exception as ex:
                self._send(200, {"error": f"{type(ex).__name__}: {ex}"})
            return

        if path == "/api/jobs/retry":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                old = (p.get("job_id") or "").strip()
                with _JOBS_LOCK:
                    e = _BG_JOBS.get(old)
                    if e is None:
                        return self._send(200, {"error": "任务不存在"})
                    if e["status"] == "running":
                        return self._send(200, {"error": "任务仍在进行中，不能重试"})
                    pl = e.get("payload")
                    if not pl:
                        return self._send(200, {"error": "原始参数已清理，无法重试；请在主界面重新发起"})
                    pl = dict(pl)
                    e.pop("payload", None)  # 参数移交给新任务，避免双份大图驻留
                jid = f"job-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
                pl["job_id"] = jid
                cfg_snap = dict(self.server.app_config)
                _bg_register(jid, pl, cfg_snap)
                with _JOBS_LOCK:
                    ne = _BG_JOBS.get(jid)
                    if ne is not None:
                        ne["bg"] = True  # 从面板发起的重试，直接进面板
                threading.Thread(target=run_bg_generate,
                                 args=(cfg_snap, pl, jid),
                                 daemon=True).start()
                log(f"重试任务 {old} -> {jid}")
                self._send(200, {"ok": True, "job_id": jid})
            except Exception as ex:
                self._send(200, {"error": f"{type(ex).__name__}: {ex}"})
            return

        if path == "/api/jobs/delete":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                jid = (p.get("job_id") or "").strip()
                resp = None
                with _JOBS_LOCK:
                    e = _BG_JOBS.get(jid)
                    if e is not None and e["status"] == "running":
                        # running 也允许删除：先标记中止（掐断下载/生成），再从面板移除；
                        # 后台线程结束时会发现条目已不存在，自然收尾
                        act = _ACTIVE_JOBS.get(jid)
                        if act is not None:
                            act["cancelled"] = True
                            resp = act.get("resp")
                    _BG_JOBS.pop(jid, None)
                if resp is not None:
                    _kill_response(resp)
                self._send(200, {"ok": True})
            except Exception as ex:
                self._send(200, {"error": f"{type(ex).__name__}: {ex}"})
            return

        if path == "/api/jobs/clear":
            with _JOBS_LOCK:
                for k in [k for k, v in _BG_JOBS.items() if v["status"] != "running"]:
                    _BG_JOBS.pop(k, None)
            self._send(200, {"ok": True})
            return

        if path != "/api/generate":
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 80 * 1024 * 1024:
                return self._send(413, {"error": "请求体过大（图片太多或太大）"})
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            jid = (payload.get("job_id") or "").strip()
            cfg_snap = dict(self.server.app_config)
            _bg_register(jid, payload, cfg_snap)
            try:
                result = do_generate(cfg_snap, payload)
                _bg_finish(jid, "done",
                           images=[im.get("name") for im in (result.get("images") or [])],
                           elapsed=result.get("elapsed"))
                self._send(200, result)
            except urllib.error.HTTPError as e:
                try:
                    detail = e.read().decode("utf-8", "replace")[:800]
                except Exception:
                    detail = str(e)
                log(f"生成失败：上游返回 HTTP {e.code}：{detail[:200]}")
                _bg_finish(jid, "failed", error=f"上游返回 HTTP {e.code}")
                self._send(200, {"error": f"上游返回 HTTP {e.code}", "detail": detail})
            except ValueError as e:
                log(f"生成失败（参数校验）：{e}")
                _bg_finish(jid, "cancelled" if str(e) == "已中止" else "failed", error=str(e))
                self._send(200, {"error": str(e)})
            except Exception as e:
                log(f"生成失败：{type(e).__name__}: {e}")
                _bg_finish(jid, "failed", error=f"{type(e).__name__}: {e}")
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            finally:
                # 任务全周期结束（含结果图下载），清理中止注册表
                with _JOBS_LOCK:
                    _ACTIVE_JOBS.pop(jid, None)
            return
        except Exception as e:
            self._send(200, {"error": f"{type(e).__name__}: {e}"})

