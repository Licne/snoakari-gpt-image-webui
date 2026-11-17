#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gpt-image 本地图形化 WebUI（单文件，零第三方依赖，Python 3.8+）

用法：
    python3 app.py            # 默认监听 http://127.0.0.1:8787
    python3 app.py --port 9000
    python3 app.py --host 0.0.0.0   # 允许局域网访问（注意密钥安全）

配置：同目录 config.json（可在页面右上角「设置」中直接修改并保存）
    { "api_key": "sk-...", "base_url": "https://your-relay.example.com", "model": "gpt-image-2" }
    也可用环境变量 GPT_IMAGE_API_KEY 覆盖密钥（优先级高于 config.json）。

功能：
    - 文生图（/v1/images/generations）与改图/多图融合（/v1/images/edits，含蒙版）
    - 图形化参数：模型 / 尺寸(auto·预设·自定义) / 张数 / 画质 / 背景 / 输出格式 /
      压缩率 / 审核级别，页面即时调整、浏览器本地记忆
    - 生成历史本地保存于 outputs/；设置（密钥/中转站）可在页面上修改
    - 后端代理转发，浏览器不受 CORS 限制，密钥不出本机
"""
import argparse
import base64
import json
import mimetypes
import os
import re
import socket
import ssl
import subprocess
import threading
import time
import uuid
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
FAV_PATH = os.path.join(BASE_DIR, "favorites.json")

def load_favs():
    """读取收藏文件名集合"""
    try:
        with open(FAV_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()

def save_favs(favs):
    try:
        with open(FAV_PATH, "w", encoding="utf-8", newline="\n") as f:
            json.dump(sorted(favs), f, ensure_ascii=False, indent=1)
    except Exception as e:
        log(f"收藏保存失败：{e}")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

MODELS = [
    "gpt-image-2", "gpt-image-2-2k", "gpt-image-2-4k",
    "gpt-image-2.5", "gpt-image-2.5-ext-2k", "gpt-image-2.5-ext-4k",
    "gpt-image-2.5-flare", "gpt-image-2.5-flare-2k", "gpt-image-2.5-flare-4k",
    "gpt-image-2.5-flare-ad", "gpt-image-2.5-sunburst", "gpt-image-2.5-sunburst-2k",
    "gpt-image-2.5-sunburst-4k", "gpt-image-2.5-sunburst-ad", "gpt-image-2.6",
    "nano-banana-2.1-1k", "nano-banana-2.1-2k", "nano-banana-2.1-4k",
    "banana-pro-1k", "banana-pro-2k", "banana-pro-4k",
    "banana2-1k", "banana2-2k", "banana2-4k",
    "gemini-3-pro-image-preview", "gemini-3.1-flash-image-preview",
    "grok-imagine-image", "grok-imagine-image-2.0",
    "grok-imagine-image-quality", "grok-4.7-build-fast",
]
SIZE_PRESETS = ["auto",
    "1024x1024", "2048x2048", "2880x2880",            # 1:1
    "1536x1024", "2160x1440", "3456x2304",            # 3:2
    "1024x1536", "1440x2160", "2304x3456",            # 2:3
    "1280x720", "2560x1440", "3840x2160",             # 16:9
    "720x1280", "1440x2560", "2160x3840",            # 9:16
    "1024x768", "2048x1536", "3200x2400",             # 4:3
    "768x1024", "1536x2048", "2400x3200",             # 3:4
    "1280x544", "2560x1088", "3840x1600",             # 21:9
]
SIZE_GROUPS = [
    ("自动", [("auto", "auto（自动）")]),
    ("1:1", [("1024x1024", "1024x1024（1K）"), ("2048x2048", "2048x2048（2K）"), ("2880x2880", "2880x2880（4K）")]),
    ("3:2", [("1536x1024", "1536x1024（1K）"), ("2160x1440", "2160x1440（2K）"), ("3456x2304", "3456x2304（4K）")]),
    ("2:3", [("1024x1536", "1024x1536（1K）"), ("1440x2160", "1440x2160（2K）"), ("2304x3456", "2304x3456（4K）")]),
    ("16:9", [("1280x720", "1280x720（1K）"), ("2560x1440", "2560x1440（2K）"), ("3840x2160", "3840x2160（4K）")]),
    ("9:16", [("720x1280", "720x1280（1K）"), ("1440x2560", "1440x2560（2K）"), ("2160x3840", "2160x3840（4K）")]),
    ("4:3", [("1024x768", "1024x768（1K）"), ("2048x1536", "2048x1536（2K）"), ("3200x2400", "3200x2400（4K）")]),
    ("3:4", [("768x1024", "768x1024（1K）"), ("1536x2048", "1536x2048（2K）"), ("2400x3200", "2400x3200（4K）")]),
    ("21:9", [("1280x544", "1280x544（1K）"), ("2560x1088", "2560x1088（2K）"), ("3840x1600", "3840x1600（4K）")]),
]
QUALITIES = ["auto", "low", "medium", "high", "xhigh", "max"]
BACKGROUNDS = ["auto", "transparent", "opaque"]
FORMATS = ["png", "jpeg", "webp"]
MODERATIONS = ["auto", "low"]
REQUEST_TIMEOUT = 600

IMG_EXTS = {"png": ".png", "jpeg": ".jpg", "jpg": ".jpg", "webp": ".webp"}
IMG_MIMES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def normalize_groups(cfg):
    """确保分组列表合法；旧配置自动迁移为一个默认分组"""
    groups = cfg.get("groups") if isinstance(cfg.get("groups"), list) else []
    out = []
    for g in groups:
        if not isinstance(g, dict):
            continue
        name = (g.get("name") or "").strip() or "未命名"
        out.append({
            "name": name,
            "base_url": (g.get("base_url") or "").strip().rstrip("/"),
            "api_key": (g.get("api_key") or "").strip(),
            "models": [str(m).strip() for m in (g.get("models") or []) if str(m).strip()],
            "proxy": (g.get("proxy") or "").strip(),
        })
    if not out:
        out.append({
            "name": "默认分组",
            "base_url": (cfg.get("base_url") or "https://your-relay.example.com").strip().rstrip("/"),
            "api_key": (cfg.get("api_key") or "").strip(),
            "models": list(MODELS),
            "proxy": (cfg.get("proxy") or "").strip(),
        })
    return out


def _read_disk_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {}


def _write_disk_config(d):
    with open(CONFIG_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def load_config():
    cfg = _read_disk_config()
    groups = normalize_groups(cfg)
    active_name = (cfg.get("active_group") or "").strip()
    if active_name not in [g["name"] for g in groups]:
        active_name = groups[0]["name"]
    g = next(x for x in groups if x["name"] == active_name)
    api_key = os.environ.get("GPT_IMAGE_API_KEY", "").strip() or (cfg.get("api_key") or "").strip() or g["api_key"]
    if not api_key:
        raise SystemExit("错误：未配置密钥。请在 config.json 填写 api_key，或设置环境变量 GPT_IMAGE_API_KEY")
    base_url = (cfg.get("base_url") or g["base_url"] or "https://your-relay.example.com").strip().rstrip("/")
    models = g["models"] or list(MODELS)
    model = cfg.get("model") or ""
    if model not in models:
        model = models[0] if models else "gpt-image-2"
    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "proxy": (cfg.get("proxy") or g["proxy"] or "").strip(),
        "group": active_name,
        "groups": groups,
        "models": models,
    }


def save_config_file(base_url, model, api_key=None, proxy=None):
    """把设置写回 config.json（保留未知字段）"""
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    cfg["base_url"] = base_url.rstrip("/")
    cfg["model"] = model
    if api_key and api_key.strip():
        cfg["api_key"] = api_key.strip()
    if proxy is not None:
        cfg["proxy"] = proxy.strip()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def mask_key(key):
    if len(key) <= 10:
        return "****"
    return key[:6] + "****" + key[-4:]


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


def api_request(url, headers, data=None, timeout=REQUEST_TIMEOUT):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    return _opener.open(req, timeout=timeout)


# ------------------------------ 生成任务中止 ------------------------------
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
            "status": "running", "error": "", "images": [], "elapsed": 0,
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
        e["t_end"] = time.time()
        e["images"] = images or []
        e["error"] = error or ""
        e["elapsed"] = elapsed if elapsed is not None else round(e["t_end"] - e["t0"], 1)
        if status != "failed":
            e.pop("payload", None)  # 只有失败任务保留参数供重试
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
            except Exception as ex:
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


def build_multipart(fields, files):
    """fields: dict; files: [(fieldname, filename, mime, bytes), ...]"""
    boundary = "----GPTImageWebUI" + uuid.uuid4().hex
    body = bytearray()
    for k, v in fields.items():
        body += (f"--{boundary}\r\n"
                 f'Content-Disposition: form-data; name="{k}"\r\n\r\n'
                 f"{v}\r\n").encode("utf-8")
    for (field, fname, mime, blob) in files:
        body += (f"--{boundary}\r\n"
                 f'Content-Disposition: form-data; name="{field}"; filename="{fname}"\r\n'
                 f"Content-Type: {mime}\r\n\r\n").encode("utf-8")
        body += blob + b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def validate_size(size, model=""):
    """校验自定义尺寸；返回 None 表示合法。-4k 模型放宽上限"""
    if size == "auto" or size in SIZE_PRESETS:
        return None
    m = re.fullmatch(r"(\d{1,5})x(\d{1,5})", size)
    if not m:
        return "自定义尺寸格式应为 WxH，例如 2048x1152"
    w, h = int(m.group(1)), int(m.group(2))
    if w % 16 or h % 16:
        return "自定义尺寸的宽和高都必须是 16 的倍数"
    ratio = max(w, h) / min(w, h)
    if ratio > 3.001:
        return "自定义尺寸宽高比必须在 1:3 到 3:1 之间"
    return None


def sniff_ext(blob, fallback=".png"):
    """按文件魔数判断真实格式（中转站可能忽略 output_format，返回 PNG 字节）"""
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if blob[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return ".webp"
    return fallback


def size_tier(size):
    """由请求的 size 推导档位：1k / 2k / 4k，auto 或无法解析时返回 auto"""
    s = (size or "").strip().lower()
    if s in ("", "auto"):
        return "auto"
    m = re.match(r"^(\d{3,5})\s*[x×]\s*(\d{3,5})$", s)
    if not m:
        return "auto"
    long_edge = max(int(m.group(1)), int(m.group(2)))
    if long_edge <= 1536:
        return "1k"
    if long_edge <= 2600:
        return "2k"
    return "4k"


def fs_safe(s):
    """文件名安全化：替换 Windows/Linux 路径非法字符，其余（含中文）保留"""
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(s or "")).strip("_") or "x"


def save_images(resp_json, fmt, prefix="", job_id=""):
    """解析响应（b64_json 或 url），落盘并返回 [{name,url,bytes}]。
    扩展名按实际字节魔数判断（中转站可能无视 output_format 始终返回 PNG）。
    prefix 附加在时间戳前，形如 档位_模型_分组。"""
    items = resp_json.get("data") or []
    results = []
    ext_hint = IMG_EXTS.get(fmt, ".png")
    for idx, item in enumerate(items, 1):
        if item.get("b64_json"):
            blob = base64.b64decode(item["b64_json"])
        elif item.get("url"):
            log(f"第 {idx} 张为 URL 结果，开始下载（可能较慢，耐心等待）")
            try:
                t_dl = time.time()
                blob = fetch_bytes(item["url"], job_id)
                log(f"第 {idx} 张下载完成，耗时 {round(time.time() - t_dl, 1)}s")
            except Exception as e:
                raise RuntimeError(
                    f"第 {idx} 张结果图下载失败：{e}\n"
                    f"图片很可能已在中转站生成（已计费），请尽快到中转站后台取回，直链：{item['url']}")
        else:
            continue
        stamp = time.strftime("%Y%m%d-%H%M%S")
        ext = sniff_ext(blob, ext_hint)
        name = (f"{prefix}_" if prefix else "") + f"{stamp}-{uuid.uuid4().hex[:6]}" + (f"-{idx}" if len(items) > 1 else "") + ext
        results.append({"name": name, "bytes": blob})
    if not results:
        raise RuntimeError("响应中没有图片数据：" + json.dumps(resp_json, ensure_ascii=False)[:1500])
    return results


def _common_params(p):
    """从 payload 提取可选公共参数（只带用户显式设置的）"""
    out = {}
    quality = (p.get("quality") or "").strip()
    if quality and quality != "auto":
        out["quality"] = quality
    fmt = (p.get("output_format") or "png").strip()
    if fmt in FORMATS and fmt != "png":
        out["output_format"] = fmt
        comp = p.get("output_compression")
        if fmt in ("jpeg", "webp") and comp is not None:
            try:
                out["output_compression"] = max(0, min(100, int(comp)))
            except (TypeError, ValueError):
                pass
    moderation = (p.get("moderation") or "").strip()
    if moderation and moderation != "auto":
        out["moderation"] = moderation
    background = (p.get("background") or "").strip()
    if background and background != "auto":
        out["background"] = background
        if background == "transparent" and fmt == "jpeg":
            raise ValueError("透明背景（background=transparent）不支持 jpeg 输出，请改用 png 或 webp")
    return out


def log(msg):
    """控制台实时日志：显示在启动 WebUI 的黑色窗口里"""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run_bg_generate(cfg, payload, jid):
    """后台执行生成任务（重试）：不回写 HTTP 响应，结果只进任务面板"""
    try:
        result = do_generate(cfg, payload)
        _bg_finish(jid, "done",
                   images=[im.get("name") for im in (result.get("images") or [])],
                   elapsed=result.get("elapsed"))
    except urllib.error.HTTPError as e:
        try:
            e.read()
        except Exception:
            pass
        log(f"后台任务失败 job={jid}：上游返回 HTTP {e.code}")
        _bg_finish(jid, "failed", error=f"上游返回 HTTP {e.code}")
    except ValueError as e:
        log(f"后台任务结束 job={jid}：{e}")
        _bg_finish(jid, "cancelled" if str(e) == "已中止" else "failed", error=str(e))
    except Exception as e:
        log(f"后台任务失败 job={jid}：{type(e).__name__}: {e}")
        _bg_finish(jid, "failed", error=f"{type(e).__name__}: {e}")
    finally:
        with _JOBS_LOCK:
            _ACTIVE_JOBS.pop(jid, None)


def do_generate(cfg, payload):
    """payload: {mode, prompt, model, size, n, quality, background,
                 output_format, output_compression, moderation, images, mask}"""
    mode = payload.get("mode", "gen")
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("提示词不能为空")
    if len(prompt) > 32000:
        raise ValueError("提示词过长（上限 32000 字符）")
    model = payload.get("model") or cfg["model"]
    size = (payload.get("size") or "auto").strip()
    err = validate_size(size, model)
    if err:
        raise ValueError(err)
    try:
        n = max(1, min(10, int(payload.get("n") or 1)))
    except (TypeError, ValueError):
        n = 1
    fmt = (payload.get("output_format") or "png").strip() if (payload.get("output_format") or "png").strip() in FORMATS else "png"
    extra = _common_params(payload)
    # 模型系列参数差异：quality/background/output_format/moderation 为 gpt-image 专属，
    # nano-banana / gemini / grok 等系列仅支持 size/n/prompt 等基础参数，多余字段会被上游 400
    if not model.lower().startswith("gpt-image"):
        if extra:
            log(f"模型 {model} 非 gpt-image 系列，忽略专属参数：{sorted(extra)}")
        extra = {}

    auth = {"Authorization": f"Bearer {cfg['api_key']}"}
    t0 = time.time()
    job_id = (payload.get("job_id") or "").strip()
    _register_job(job_id)

    if mode == "gen":
        body = {"model": model, "prompt": prompt, "size": size, "n": n}
        body.update(extra)
        data = json.dumps(body).encode("utf-8")
        headers = dict(auth, **{"Content-Type": "application/json"})
        pshow = prompt[:30] + ("…" if len(prompt) > 30 else "")
        log(f"开始生成 | 文生图 | 模型={model} 尺寸={size} 张数={n} 代理={cfg.get('proxy') or '直连'} | {pshow}")
        with api_request(f"{cfg['base_url']}/v1/images/generations", headers, data) as r:
            _register_resp(job_id, r)
            resp_json = read_response(r, job_id)
    else:  # edit
        imgs = payload.get("images") or []
        if not imgs:
            raise ValueError("改图模式需要至少上传一张输入图片")
        files = []
        for im in imgs[:16]:
            mime = im.get("mime") or "image/png"
            blob = base64.b64decode(im.get("data") or "")
            if not blob:
                raise ValueError(f"图片 {im.get('name')} 内容为空")
            if len(blob) > 20 * 1024 * 1024:
                raise ValueError(f"图片 {im.get('name')} 超过 20MB 上限")
            files.append(("image[]", im.get("name") or "input.png", mime, blob))
        mask = payload.get("mask")
        if mask:
            mime = mask.get("mime") or "image/png"
            if mime != "image/png":
                raise ValueError("蒙版必须是 PNG 格式（透明区域表示要修改的部分）")
            blob = base64.b64decode(mask.get("data") or "")
            if not blob:
                raise ValueError("蒙版内容为空")
            files.append(("mask", mask.get("name") or "mask.png", "image/png", blob))
        fields = {"model": model, "prompt": prompt, "size": size, "n": str(n)}
        fields.update({k: str(v) for k, v in extra.items()})
        body, ctype = build_multipart(fields, files)
        headers = dict(auth, **{"Content-Type": ctype})
        pshow = prompt[:30] + ("…" if len(prompt) > 30 else "")
        log(f"开始生成 | 改图 | 模型={model} 尺寸={size} 张数={n} 输入图={len(imgs[:16])}张 代理={cfg.get('proxy') or '直连'}"
            + (" 带蒙版" if mask else "") + f" | {pshow}")
        with api_request(f"{cfg['base_url']}/v1/images/edits", headers, body) as r:
            _register_resp(job_id, r)
            resp_json = read_response(r, job_id)

    name_prefix = f"{fs_safe(size_tier(size))}_{fs_safe(model)}_{fs_safe(cfg.get('group') or '')}"
    images = save_images(resp_json, fmt, prefix=name_prefix, job_id=job_id)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out = []
    for img in images:
        path = os.path.join(OUTPUT_DIR, img["name"])
        with open(path, "wb") as f:
            f.write(img["bytes"])
        out.append({"name": img["name"], "url": f"/outputs/{img['name']}",
                    "size": len(img["bytes"])})
    elapsed = round(time.time() - t0, 1)
    usage = resp_json.get("usage")
    log(f"完成 | 耗时 {elapsed}s | 模型={model} | 生成 {len(out)} 张"
        + (f" | 用量 {json.dumps(usage, ensure_ascii=False)}" if usage else ""))
    for img in out:
        log(f"  保存 outputs/{img['name']}（{img['size'] // 1024} KB）")
    return {"ok": True, "elapsed": elapsed, "usage": usage,
            "model": model, "size": size, "images": out}


APP_VER = "1.3.1"  # 应用版本号：每次发布更新；展示于设置弹窗底部


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


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"gpt-image-webui/{APP_VER}"

    def log_message(self, fmt, *args):
        pass  # 静默访问日志

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            log("浏览器连接已断开，跳过响应回写")

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, INDEX_HTML.replace("__APP_VER__", APP_VER).encode("utf-8"),
                      "text/html; charset=utf-8")
        elif self.path.startswith("/outputs/"):
            name = os.path.basename(self.path[len("/outputs/"):])
            ext = os.path.splitext(name)[1].lower()
            if ext not in IMG_MIMES or not re.fullmatch(r"[\w.-]+", name):
                return self._send(404, {"error": "not found"})
            path = os.path.join(OUTPUT_DIR, name)
            if not os.path.isfile(path):
                return self._send(404, {"error": "not found"})
            with open(path, "rb") as f:
                self._send(200, f.read(), IMG_MIMES[ext])
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
        elif self.path.startswith("/api/reveal"):
            import urllib.parse as _up
            qs = _up.parse_qs(_up.urlsplit(self.path).query)
            name = os.path.basename((qs.get("name") or [""])[0])
            if not re.fullmatch(r"[\w.-]+", name) or os.path.splitext(name)[1].lower() not in IMG_MIMES:
                return self._send(200, {"error": "非法文件名"})
            path = os.path.join(OUTPUT_DIR, name)
            if not os.path.isfile(path):
                return self._send(200, {"error": "文件不存在"})
            if os.name != "nt":
                return self._send(200, {"error": "仅 Windows 支持，当前系统 " + os.name})
            subprocess.Popen('explorer /select,"' + os.path.abspath(path) + '"')
            log(f"本地查看：已定位 outputs/{name}")
            self._send(200, {"ok": True})
        elif self.path == "/api/jobs":
            with _JOBS_LOCK:
                jobs = [{k: v for k, v in e.items() if k != "payload"}
                        for e in _BG_JOBS.values() if e.get("bg")]
            jobs.sort(key=lambda x: (0 if x["status"] == "running" else 1, -(x["t_end"] or x["t0"])))
            self._send(200, {"jobs": jobs[:30]})
        elif self.path.startswith("/api/history"):
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            favs = load_favs()
            fav_only = "fav=1" in self.path
            items = []
            for fn in os.listdir(OUTPUT_DIR):
                ext = os.path.splitext(fn)[1].lower()
                if ext in IMG_MIMES:
                    if fav_only and fn not in favs:
                        continue
                    st = os.stat(os.path.join(OUTPUT_DIR, fn))
                    items.append({"name": fn, "url": f"/outputs/{fn}",
                                  "size": st.st_size, "mtime": st.st_mtime,
                                  "fav": fn in favs})
            items.sort(key=lambda x: -x["mtime"])
            self._send(200, items[:500] if fav_only else items[:200])
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/settings":
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

        if self.path == "/api/groups":
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

        if self.path == "/api/group/switch":
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
                if not g["models"]:
                    return self._send(200, {"error": "该分组模型列表为空"})
                cfg = self.server.app_config
                cfg["group"] = name
                cfg["base_url"] = g["base_url"]
                cfg["api_key"] = g["api_key"]
                cfg["proxy"] = g["proxy"]
                cfg["models"] = g["models"]
                if cfg["model"] not in g["models"]:
                    cfg["model"] = g["models"][0]
                set_proxy(g["proxy"])
                disk = _read_disk_config()
                disk.update({"active_group": name, "base_url": g["base_url"], "api_key": g["api_key"],
                             "model": cfg["model"], "proxy": g["proxy"]})
                _write_disk_config(disk)
                log(f"已切换分组：{name}（{g['base_url']}，模型 {len(g['models'])} 个）")
                self._send(200, {"ok": True, "group": name, "model": cfg["model"], "models": g["models"]})
            except Exception as e:
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            return

        if self.path == "/api/models":
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

        if self.path == "/api/fav":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                raw = (p.get("name") or "").strip()
                name = os.path.basename(raw)
                if raw != name or not re.fullmatch(r"[\w.-]+", name) or os.path.splitext(name)[1].lower() not in IMG_MIMES:
                    return self._send(200, {"error": "非法文件名"})
                if not os.path.isfile(os.path.join(OUTPUT_DIR, name)):
                    return self._send(200, {"error": "文件不存在"})
                favs = load_favs()
                want = bool(p.get("fav"))
                (favs.add if want else favs.discard)(name)
                save_favs(favs)
                log(f"收藏{'添加' if want else '取消'}：{name}")
                self._send(200, {"ok": True, "fav": want})
            except Exception as e:
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            return

        if self.path == "/api/rename":
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
                favs = load_favs()
                if name in favs:
                    favs.discard(name)
                    favs.add(to)
                    save_favs(favs)
                log(f"重命名：outputs/{name} -> outputs/{to}")
                self._send(200, {"ok": True, "name": to, "url": f"/outputs/{to}"})
            except Exception as e:
                self._send(200, {"error": f"{type(e).__name__}: {e}"})
            return

        if self.path == "/api/cancel":
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

        if self.path == "/api/jobs/background":
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

        if self.path == "/api/jobs/retry":
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
                _bg_register(jid, pl, self.server.app_config)
                with _JOBS_LOCK:
                    ne = _BG_JOBS.get(jid)
                    if ne is not None:
                        ne["bg"] = True  # 从面板发起的重试，直接进面板
                threading.Thread(target=run_bg_generate,
                                 args=(self.server.app_config, pl, jid),
                                 daemon=True).start()
                log(f"重试任务 {old} -> {jid}")
                self._send(200, {"ok": True, "job_id": jid})
            except Exception as ex:
                self._send(200, {"error": f"{type(ex).__name__}: {ex}"})
            return

        if self.path == "/api/jobs/delete":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                jid = (p.get("job_id") or "").strip()
                with _JOBS_LOCK:
                    e = _BG_JOBS.get(jid)
                    if e is not None and e["status"] == "running":
                        return self._send(200, {"error": "进行中的任务请先中止再移除"})
                    _BG_JOBS.pop(jid, None)
                self._send(200, {"ok": True})
            except Exception as ex:
                self._send(200, {"error": f"{type(ex).__name__}: {ex}"})
            return

        if self.path == "/api/jobs/clear":
            with _JOBS_LOCK:
                for k in [k for k, v in _BG_JOBS.items() if v["status"] != "running"]:
                    _BG_JOBS.pop(k, None)
            self._send(200, {"ok": True})
            return

        if self.path != "/api/generate":
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 80 * 1024 * 1024:
                return self._send(413, {"error": "请求体过大（图片太多或太大）"})
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            jid = (payload.get("job_id") or "").strip()
            _bg_register(jid, payload, self.server.app_config)
            try:
                result = do_generate(self.server.app_config, payload)
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


# ------------------------------ 前端页面 ------------------------------
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SnoAkari gpt-image WebUI</title>
<style>
:root { --bg:#111413; --panel:#1a1f1d; --panel2:#222826; --line:#2c3431;
        --text:#e8ece9; --muted:#9aa5a0; --acc:#34d399; --acc2:#10b981; }
* { box-sizing:border-box; scrollbar-width:thin; scrollbar-color:#39423e transparent; }
::-webkit-scrollbar { width:8px; height:8px; }
::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:#39423e; border-radius:4px; }
::-webkit-scrollbar-thumb:hover { background:#4a564f; }
body { margin:0; background:var(--bg); color:var(--text);
       font-family:"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif; }
.layout { display:flex; height:100vh; }
aside { width:430px; min-width:360px; background:var(--panel); border-right:1px solid var(--line);
        padding:16px 20px; overflow-y:auto; }
main { flex:1; overflow-y:auto; padding:18px 24px; }
.head { display:flex; flex-direction:column; gap:10px; align-items:flex-start; margin-bottom:16px; }
.headTop { width:100%; display:flex; align-items:flex-start; justify-content:space-between; gap:8px; }
h1 { font-size:18px; margin:0 0 2px; }
h1 span { color:var(--acc); }
.sub { color:var(--muted); font-size:12px; margin-bottom:14px; }
#groupSel { background:var(--panel2); color:var(--text); border:1px solid var(--line); border-radius:8px;
  padding:6px 10px; font-size:12.5px; width:auto; max-width:220px; }
.gear { background:var(--panel2); border:1px solid var(--line); color:var(--muted);
        border-radius:8px; padding:5px 10px; cursor:pointer; font-size:15px; line-height:1; }
.gear:hover { color:var(--acc); border-color:var(--acc); }
.tabs { display:flex; gap:8px; margin-bottom:12px; }
.tabs button { flex:1; padding:9px 0; border:1px solid var(--line); border-radius:9px;
   background:var(--panel2); color:var(--muted); cursor:pointer; font-size:14px; }
.tabs button.active { background:var(--acc2); color:#06231a; border-color:var(--acc2); font-weight:600; }
label { display:block; font-size:12px; color:var(--muted); margin:12px 0 5px; }
label small { color:#6b7672; }
textarea, select, input[type=text] { width:100%; }
.sizeRow { display:flex; gap:8px; margin-top:6px; }
.sizeRow select { flex:1; width:auto; }
textarea { background:var(--panel2); color:var(--text); border:1px solid var(--line);
   border-radius:9px; padding:10px; font-size:14px; min-height:88px; resize:vertical;
   font-family:inherit; }
textarea:focus, select:focus, input:focus { outline:1px solid var(--acc); }
select, input[type=text] { background:var(--panel2); color:var(--text); border:1px solid var(--line);
   border-radius:9px; padding:9px 10px; font-size:14px; }
.row { display:flex; gap:10px; }
.row > div { flex:1; }
.sect { margin-top:16px; padding-top:12px; border-top:1px dashed #2c3431; }
.sect > .t { font-size:12px; color:var(--acc); letter-spacing:1px; margin-bottom:2px; }
.hint { font-size:11px; color:#6b7672; margin-top:4px; line-height:1.5; }
.drop { margin-top:6px; border:1.5px dashed #3d4945; border-radius:10px; padding:14px 10px;
   text-align:center; color:var(--muted); font-size:13px; cursor:pointer; transition:.15s; }
.drop.on { border-color:var(--acc); background:#1c2622; color:var(--text); }
.thumbs { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
.thumb { position:relative; width:74px; height:74px; border-radius:8px; overflow:hidden;
   border:1px solid var(--line); }
.thumb img { width:100%; height:100%; object-fit:cover; cursor:zoom-in; }
.thumb b { position:absolute; top:2px; right:2px; background:#000a; color:#fff;
   border-radius:50%; width:18px; height:18px; line-height:18px; text-align:center;
   cursor:pointer; font-size:11px; font-weight:400; }
.maskbtn { width:100%; margin-top:10px; padding:10px 0; border-radius:10px;
   background:var(--panel2); color:var(--text); border:1px solid var(--line);
   font-size:13px; cursor:pointer; }
.maskbtn:hover { border-color:var(--acc); color:var(--acc); }
.mcanvasWrap { background:#000; border:1px solid var(--line); border-radius:10px;
   max-height:58vh; overflow:auto; }
#maskCv { display:block; max-width:100%; cursor:crosshair; }
.slider { display:flex; align-items:center; gap:10px; }
.slider input[type=range] { flex:1; accent-color:var(--acc2); }
.slider span { font-size:12px; color:var(--muted); min-width:30px; text-align:right; }
#go { width:100%; margin-top:16px; padding:13px 0; border:0; border-radius:10px;
   background:var(--acc2); color:#06231a; font-size:15px; font-weight:700; cursor:pointer; }
#go:disabled { background:#2c5a49; color:#7fa393; cursor:not-allowed; }
.bgBtn { margin-top:10px; width:100%; padding:9px 0; border-radius:10px; cursor:pointer;
  border:1px dashed var(--acc); background:rgba(52,211,153,.06); color:var(--acc); font-size:13px; }
.bgBtn:hover { background:rgba(52,211,153,.14); }
.jobsPanel { margin-top:12px; border:1px solid var(--line); border-radius:10px; background:var(--panel2); padding:10px 12px; }
.jobsHead { display:flex; justify-content:space-between; font-size:12px; color:var(--muted); margin-bottom:8px; }
.jobsHead a { color:var(--acc); text-decoration:none; margin-left:8px; }
.jobItem { padding:8px 10px; border-bottom:1px dashed var(--line); font-size:12px; color:var(--text); line-height:1.5; }
.jobItem:last-child { border-bottom:0; }
.jobItem .jTop { display:flex; align-items:center; gap:8px; }
.jobItem .run { color:var(--acc); }
.jobItem .ok { color:#7dd3fc; }
.jobItem .fail { color:#f87171; }
.jobItem .can { color:var(--muted); }
.jobItem .jid { flex:1; font-size:11px; color:var(--muted); font-family:Consolas,monospace; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.jobItem .del { color:var(--muted); text-decoration:none; font-size:13px; padding:0 2px; }
.jobItem .retry { color:var(--acc); text-decoration:none; font-size:12px; flex-shrink:0; }
.jobItem .del:hover { color:#f87171; }
.jobItem .jMid { margin-top:2px; }
.jobItem .jErr { margin-top:2px; color:#f87171; font-size:11px; word-break:break-all; }
.jobItem .jSub { margin-top:2px; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.status { margin-top:12px; font-size:13px; color:var(--muted); min-height:20px;
   white-space:pre-wrap; word-break:break-all; }
.status.err { color:#f87171; }
h2 { font-size:14px; color:var(--muted); font-weight:600; margin:8px 0 12px; }
#results { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,540px),1fr)); gap:16px; }
#results .card img { width:auto; max-width:100%; align-self:center; }
#history { display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); gap:12px; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:12px;
   padding:10px; display:flex; flex-direction:column; gap:8px; }
.card img { width:100%; border-radius:8px; cursor:zoom-in; background:#000; }
.card img.masked { filter: blur(18px) brightness(.55) saturate(.6); }
.card.fav .meta > span:first-child::before { content: "★ "; color: #fbbf24; }
body.masked .card img { cursor:pointer; }
.maskBtn { float:right; font-size:12px; font-weight:600; padding:5px 12px; border-radius:999px;
  border:1px solid var(--line); background:var(--panel2); color:var(--muted); cursor:pointer; }
.chip { float:right; font-size:12px; font-weight:600; padding:5px 12px; border-radius:999px;
  border:1px solid var(--line); background:var(--panel2); color:var(--muted); cursor:pointer; margin-left:10px; }
.chip.on { color:#fbbf24; border-color:#fbbf24; background:rgba(251,191,36,.08); }
.maskBtn.on { background:var(--acc); border-color:var(--acc); color:#0b1512; }
.card .meta { font-size:11.5px; color:var(--muted); display:flex; justify-content:space-between; gap:6px; overflow:hidden; white-space:nowrap;
  align-items:baseline; }
.card .meta span:first-child { overflow:hidden; text-overflow:ellipsis; min-width:0; }
.card .meta span:last-child { white-space:nowrap; flex-shrink:0; }
.card .ops { display:flex; gap:8px; flex-wrap:wrap; }
.card .ops a:nth-child(-n+3) { flex:1 1 calc(33% - 8px); }
.card .ops a:nth-child(n+4) { flex:1 1 calc(50% - 8px); }
.card .ops a { flex:1; text-align:center; padding:6px 0; border-radius:7px; background:var(--panel2);
   color:var(--text); text-decoration:none; font-size:12px; border:1px solid var(--line); }
.card .ops a:hover { border-color:var(--acc); color:var(--acc); }
.empty { grid-column:1/-1; color:var(--muted); font-size:13px; padding:40px 0; text-align:center; }
.lightbox { position:fixed; inset:0; background:#000d; display:none; align-items:center;
   justify-content:center; z-index:50; cursor:zoom-out; }
.lightbox img { max-width:94vw; max-height:94vh; border-radius:10px; }
.modal { position:fixed; inset:0; background:#000a; display:none; align-items:center;
   justify-content:center; z-index:60; }
.modal .box { background:var(--panel); border:1px solid var(--line); border-radius:14px;
   width:min(440px,92vw); max-height:88vh; overflow-y:auto; padding:20px; }
.modal .ver { margin-top:14px; text-align:center; color:var(--muted); font-size:11px; }
.modal h3 { margin:0 0 4px; font-size:15px; }
.modal .box .sub { margin-bottom:10px; }
.modal .btns { display:flex; gap:10px; margin-top:16px; }
.modal .btns button { flex:1; padding:10px 0; border-radius:9px; border:1px solid var(--line);
   background:var(--panel2); color:var(--text); cursor:pointer; font-size:14px; }
.modal .btns button.primary { background:var(--acc2); color:#06231a; border-color:var(--acc2); font-weight:700; }
@media (max-width:860px){ .layout{flex-direction:column;} aside{width:auto; min-width:0;} main{height:auto;} }
</style>
</head>
<body>
<div class="layout">
<aside>
  <div class="head">
    <div class="headTop">
      <div>
        <h1>SnoAkari <span>gpt-image WebUI</span></h1>
        <div class="sub">本地调用 NewAPI 中转站 · 参数图形化配置</div>
      </div>
      <button class="gear" onclick="openSettings()" title="设置" aria-label="设置">⚙</button>
    </div>
    <select id="groupSel" title="切换中转站分组" onchange="switchGroupHeader()"></select>
  </div>

  <div class="tabs">
    <button id="tabGen" class="active" onclick="setMode('gen')">文生图</button>
    <button id="tabEdit" onclick="setMode('edit')">改图 / 多图融合</button>
  </div>

  <label>提示词 <small>（上限 32000 字符）</small></label>
  <textarea id="prompt" placeholder="描述要生成的画面……"></textarea>

  <div id="editBox" style="display:none">
    <label>输入图片（可多张融合，最多 16 张）</label>
    <div class="drop" id="drop">点击选择或拖拽图片到此处<small>（PNG / JPG / WEBP，单张 ≤ 20MB）</small></div>
    <input type="file" id="file" accept="image/*" multiple hidden>
    <div class="thumbs" id="thumbs"></div>

    <label>蒙版 mask <small>（可选，仅改图：透明区域=要修改的部分）</small></label>
    <div class="drop" id="dropMask">点击选择 PNG 蒙版（可选）</div>
    <input type="file" id="fileMask" accept="image/png" hidden>
    <div class="thumbs" id="thumbMask"></div>
    <button type="button" class="maskbtn" onclick="openMaskEditor()">✏ 在第一张原图上绘制蒙版（推荐）</button>
  </div>

  <div class="sect">
    <div class="t">基本参数</div>
    <label>模型</label>
    <select id="model"></select>
    <div class="hint" id="modelHint"></div>

    <div class="row">
      <div>
        <label>尺寸</label>
        <div class="sizeRow">
          <select id="sizeRatio"></select>
          <select id="sizeTier" style="display:none"></select>
        </div>
      </div>
      <div id="customSizeBox" style="display:none">
        <label>自定义 WxH</label>
        <input type="text" id="customSize" placeholder="2048x1152">
      </div>
    </div>
    <div class="hint" id="sizeHint"></div>

    <div class="row">
      <div><label>张数 n <small>(1~10)</small></label>
        <select id="n"></select>
      </div>
      <div><label>画质 quality</label>
        <select id="quality"></select>
      </div>
    </div>
    <div class="hint">画质档位：low / medium / high / auto 通用；<b>xhigh / max 仅 2.5 及以上系列</b>。
      画质越高耗时与费用越高。</div>
  </div>

  <div class="sect" id="outSect">
    <div class="t">输出选项 <small>（仅 gpt-image 系列支持）</small></div>
    <div class="row">
      <div><label>背景 background <small>(仅文生图)</small></label>
        <select id="background"></select>
      </div>
      <div><label>输出格式</label>
        <select id="format"></select>
      </div>
    </div>
    <div id="compBox" style="display:none">
      <label>压缩率 output_compression</label>
      <div class="slider">
        <input type="range" id="comp" min="0" max="100" value="100">
        <span id="compVal">100</span>
      </div>
      <div class="hint">0~100，数值越小文件越小（仅 jpeg / webp 有效）。</div>
    </div>
    <label>内容审核 moderation</label>
    <select id="moderation"></select>
    <div class="hint">low = 更宽松的过滤；auto = 默认。</div>
  </div>

  <button id="go" onclick="generate()">生成（约 60~90 秒 / 张）</button>
  <div class="status" id="status"></div>
  <button id="toBgBtn" class="bgBtn" style="display:none" onclick="toBackground()">转入后台，继续填写参数</button>
  <div id="jobsPanel" class="jobsPanel" style="display:none">
    <div class="jobsHead">
      <span>后台任务（<span id="jobsRun">0</span> 个进行中）</span>
      <span>
        <a href="javascript:void(0)" onclick="refreshJobs(true)">刷新</a>
        <a href="javascript:void(0)" onclick="clearJobs()">清除已完成</a>
        <a href="javascript:void(0)" onclick="toggleJobsPanel(false)">收起</a>
      </span>
    </div>
    <div id="jobsList"></div>
  </div>
</aside>

<main>
  <h2>本次结果 <button id="maskToggle" class="maskBtn" onclick="toggleMask()" title="隐私遮罩：开启后所有预览图自动模糊；单击单张图切换遮挡/显示，双击放大查看">遮罩：关</button></h2>
  <div class="grid" id="results"><div class="empty">还没有生成结果，先在左侧写好提示词</div></div>
  <h2 style="margin-top:24px">历史记录（outputs/ 目录）
    <button id="favOnlyBtn" class="chip" onclick="toggleFavOnly()">★ 只看收藏</button>
  </h2>
  <div class="grid" id="history"><div class="empty">加载中……</div></div>
</main>
</div>

<div class="lightbox" id="lb" onclick="this.style.display='none'"><img id="lbImg"></div>

<div class="modal" id="maskModal">
  <div class="box" style="width:min(94vw,960px)">
    <h3>✏ 绘制蒙版</h3>
    <div class="sub">在原图上用红色笔刷涂抹“要修改的区域”，保存后涂抹处即为 AI 重绘区域，其余保持原样</div>
    <div class="mcanvasWrap"><canvas id="maskCv"></canvas></div>
    <div class="slider" style="margin-top:12px">
      <small>笔刷</small>
      <input type="range" id="brushSize" min="8" max="120" value="36">
      <span id="brushVal">36</span>
    </div>
    <div class="btns">
      <button onclick="closeMaskEditor()">取消</button>
      <button onclick="clearMaskCanvas()">清空重画</button>
      <button class="primary" onclick="saveMaskEditor()">保存蒙版</button>
    </div>
  </div>
</div>

<div class="modal" id="settingsModal">
  <div class="box" style="max-width:560px">
    <h3>⚙ 中转站分组管理</h3>
    <div class="sub">每组独立配置地址/密钥/模型列表；修改后写入同目录 config.json</div>

    <label>分组</label>
    <select id="setGroup" onchange="renderGroupEditor()"></select>
    <div class="btns" style="margin:8px 0 14px">
      <button onclick="newGroup()">＋ 新增分组</button>
      <button onclick="delGroup()">删除分组</button>
      <button onclick="useGroup()">启用此组</button>
    </div>

    <label>分组名称</label>
    <input type="text" id="grpName">
    <label>中转站地址 base_url</label>
    <input type="text" id="grpUrl" placeholder="https://xxx.com">
    <label>API 密钥 <small id="keyMasked"></small></label>
    <input type="text" id="grpKey" placeholder="留空表示不修改">
    <label>网络代理 <small>（可选，如 http://127.0.0.1:7890；留空=直连）</small></label>
    <input type="text" id="grpProxy" placeholder="http://127.0.0.1:7890（留空直连）">
    <label>模型列表 <small>（每行一个，切换分组时下拉随之变化）</small></label>
    <textarea id="grpModels" rows="6" placeholder="每行一个模型名，或点下方按钮从接口拉取"></textarea>
    <div class="btns" style="margin:8px 0 4px">
      <button onclick="fetchModels()">从接口拉取模型列表</button>
      <button class="primary" onclick="saveAllGroups()">保存全部分组</button>
    </div>
    <div class="btns">
      <button onclick="closeSettings()">关闭</button>
    </div>
    <div class="status" id="setStatus"></div>
    <div class="ver">SnoAkari gpt-image WebUI · v__APP_VER__</div>
  </div>
</div>

<script>
let mode = 'gen', files = [], maskFile = null;
let genAbort = null, genJobId = '', genBgNow = false, genBusy = false;
const $ = id => document.getElementById(id);
const MODEL_NOTES = {
  'gpt-image-2': '旗舰单模型，画质 low/medium/high',
  'gpt-image-2-2k': '固定 2K 分辨率输出',
  'gpt-image-2-4k': '固定 4K 分辨率输出',
  'gpt-image-2.5': 'Images 2.5 基础版',
  'gpt-image-2.5-flare': '速度优先（比 gpt-image-2 快 2~4 倍），日常首选',
  'gpt-image-2.5-flare-ad': 'Flare 广告变体，适合营销素材',
  'gpt-image-2.5-sunburst': '质量/改图精度优先，多轮编辑更稳，耗时更长',
  'gpt-image-2.5-sunburst-ad': 'Sunburst 广告变体',
  'gpt-image-2.5-ext-2k': '2.5 ext 变体，2K 输出',
  'gpt-image-2.5-ext-4k': '2.5 ext 变体，4K 输出',
  'gpt-image-2.5-flare-2k': 'Flare 高分辨率档（2K）',
  'gpt-image-2.5-flare-4k': 'Flare 高分辨率档（4K）',
  'gpt-image-2.5-sunburst-2k': 'Sunburst 高分辨率档（2K）',
  'gpt-image-2.5-sunburst-4k': 'Sunburst 高分辨率档（4K）',
  'gpt-image-2.6': '最新一代',
  'nano-banana-2.1-1k': 'Google Nano Banana 2.1，1K',
  'nano-banana-2.1-2k': 'Google Nano Banana 2.1，2K',
  'nano-banana-2.1-4k': 'Google Nano Banana 2.1，4K',
  'banana-pro-1k': 'Banana Pro，1K',
  'banana-pro-2k': 'Banana Pro，2K',
  'banana-pro-4k': 'Banana Pro，4K',
  'banana2-1k': 'Banana 2，1K',
  'banana2-2k': 'Banana 2，2K',
  'banana2-4k': 'Banana 2，4K',
  'gemini-3-pro-image-preview': 'Gemini 3 Pro 图像预览版',
  'gemini-3.1-flash-image-preview': 'Gemini 3.1 Flash 图像预览版（快）',
  'grok-imagine-image': 'Grok 图像生成',
  'grok-imagine-image-2.0': 'Grok Imagine 2.0',
  'grok-imagine-image-quality': 'Grok Imagine 高质量版',
  'grok-4.7-build-fast': 'Grok 4.7 快速构建版'
};
const MODEL_QUALITY_MAX = m => /2\.5|2\.6|2-4k/.test(m) ? 'max' : 'high';

(async function init(){
  const cfg = await (await fetch('/api/config')).json();
  $('groupSel').innerHTML = (cfg.groups||[]).map(g => `<option value="${g}">${g}</option>`).join('');
  $('groupSel').value = cfg.group || '';
  let m0 = savedOrDefault('model', cfg.model);
  if (!(cfg.models||[]).includes(m0)) m0 = cfg.model;
  if (!(cfg.models||[]).includes(m0)) m0 = (cfg.models||[])[0] || '';
  $('model').innerHTML = (cfg.models||[]).map(m => `<option value="${m}">${m}</option>`).join('');
  $('model').value = m0;
  const ratioMap = {};
  $('sizeRatio').innerHTML = `<option value="auto">auto（自动）</option>`
    + (cfg.size_groups || []).filter(g => g[0] !== '自动').map(g => {
      ratioMap[g[0]] = g[1].map(it => it[0]);
      return `<option value="${g[0]}">${g[0]}</option>`; }).join('')
    + `<option value="custom">自定义…</option>`;
  window.RATIO_MAP = ratioMap;
  $('sizeTier').innerHTML = ['1K','2K','4K'].map((t,i)=>`<option value="${i}">${t}</option>`).join('');
  $('n').innerHTML = Array.from({length:10},(_,i)=>`<option>${i+1}</option>`).join('');
  $('quality').innerHTML = cfg.qualities.map(q => `<option value="${q}">${q==='auto'?'auto（默认）':q}</option>`).join('');
  $('background').innerHTML = cfg.backgrounds.map(b => `<option value="${b}">${b==='auto'?'auto（默认）':b==='transparent'?'transparent（透明底）':'opaque（不透明）'}</option>`).join('');
  $('format').innerHTML = cfg.formats.map(f => `<option value="${f}">${f==='png'?'png（默认）':f}</option>`).join('');
  $('moderation').innerHTML = cfg.moderations.map(m => `<option value="${m}">${m==='auto'?'auto（默认）':m}</option>`).join('');

  // 恢复上次参数（浏览器本地记忆）
  try{
    const saved = JSON.parse(localStorage.getItem('gptImageParams') || '{}');
    if (saved.size && saved.sizeRatio === undefined){
      if (saved.size === 'auto'){ saved.sizeRatio = 'auto'; }
      else {
        for (const [r, vals] of Object.entries(window.RATIO_MAP || {})){
          const i = vals.indexOf(saved.size);
          if (i >= 0){ saved.sizeRatio = r; saved.sizeTier = String(i); break; }
        }
      }
    }
    ['model','sizeRatio','sizeTier','customSize','n','quality','background','format','moderation','prompt'].forEach(k=>{
      if (saved[k] !== undefined && $(k)) $(k).value = saved[k];
    });
    if (saved.comp !== undefined){ $('comp').value = saved.comp; }
  }catch(e){}

  $('model').value = savedOrDefault('model', cfg.model);
  onModelChange(); onSizeChange(); onFormatChange();
  loadHistory();
})();

function savedOrDefault(k, d){ try{ return JSON.parse(localStorage.getItem('gptImageParams')||'{}')[k] ?? d; }catch(e){ return d; } }

function setMode(m){
  mode = m;
  $('tabGen').classList.toggle('active', m==='gen');
  $('tabEdit').classList.toggle('active', m==='edit');
  $('editBox').style.display = m==='edit' ? '' : 'none';
  $('background').disabled = (m==='edit');
  $('background').parentElement && ($('background').title = m==='edit' ? '背景参数仅文生图支持' : '');
}

function modelSeries(m){
  m = (m || '').toLowerCase();
  if (m.startsWith('gpt-image')) return 'gpt';
  if (m.includes('banana') || m.includes('gemini')) return 'banana';
  return 'other';
}
function onModelChange(){
  const m = $('model').value;
  const s = modelSeries(m);
  const lite = s !== 'gpt';   // 非 gpt-image 系列：仅支持 尺寸/张数 等基础参数
  $('quality').disabled = lite;
  if (lite) $('quality').value = 'auto';
  $('outSect').style.display = lite ? 'none' : '';
  if (lite){ $('background').value = 'auto'; $('format').value = 'png'; $('moderation').value = 'auto'; }
  let note = MODEL_NOTES[m] || '';
  if (lite) note += (note ? '　' : '') + (s === 'banana'
    ? 'nano-banana / gemini 系列：仅支持尺寸、张数等基础参数（画质/背景/格式/审核不适用，已自动隐藏）'
    : '该系列：仅支持尺寸、张数等基础参数（画质/背景/格式/审核不适用，已自动隐藏）');
  $('modelHint').textContent = note;
}
function onSizeChange(){
  const r = $('sizeRatio').value;
  const custom = r === 'custom';
  $('customSizeBox').style.display = custom ? '' : 'none';
  $('sizeTier').style.display = (custom || r === 'auto') ? 'none' : '';
  $('sizeHint').textContent = custom
    ? '自定义尺寸需满足：宽高均为 16 的倍数、宽高比 1:3~3:1；最长边与总像素不限制，能否生效由上游模型决定'
    : '';
}
function onFormatChange(){
  const f = $('format').value;
  $('compBox').style.display = (f==='jpeg'||f==='webp') ? '' : 'none';
  if (f==='jpeg' && $('background').value==='transparent'){
    $('background').value = 'auto';
  }
}
$('comp').oninput = () => $('compVal').textContent = $('comp').value;
$('prompt').addEventListener('input', persistParams);
$('model').onchange = onModelChange;
$('sizeRatio').onchange = onSizeChange; $('sizeTier').onchange = onSizeChange;
$('format').onchange = onFormatChange;

function persistParams(){
  const p = { mode, model:$('model').value, sizeRatio:$('sizeRatio').value, sizeTier:$('sizeTier').value,
    customSize:$('customSize').value, n:$('n').value, quality:$('quality').value,
    background:$('background').value, format:$('format').value,
    moderation:$('moderation').value, comp:$('comp').value, prompt:$('prompt').value };
  localStorage.setItem('gptImageParams', JSON.stringify(p));
}

function renderThumbs(){
  $('thumbs').innerHTML = files.map((f,i)=>`<div class="thumb"><img src="${f.url}" onclick="lbShow(this.src)"><b onclick="files.splice(${i},1);renderThumbs()">×</b></div>`).join('');
}
function renderMask(){
  $('thumbMask').innerHTML = maskFile ? `<div class="thumb"><img src="${maskFile.url}" onclick="lbShow(this.src)"><b onclick="maskFile=null;renderMask()">×</b></div>` : '';
}
function lbShow(u){ $('lbImg').src = u; $('lb').style.display='flex'; }

/* ---------- 隐私遮罩 ---------- */
let maskOn = localStorage.getItem('gptImageMask') === '1';
function syncMaskBtn(){
  const b = $('maskToggle');
  b.textContent = '遮罩：' + (maskOn ? '开' : '关');
  b.classList.toggle('on', maskOn);
}
function toggleMask(){
  maskOn = !maskOn;
  localStorage.setItem('gptImageMask', maskOn ? '1' : '0');
  document.body.classList.toggle('masked', maskOn);
  document.querySelectorAll('#results img[data-full], #history img[data-full]')
    .forEach(i => i.classList.toggle('masked', maskOn));
  syncMaskBtn();
}
syncMaskBtn();
if (maskOn) document.body.classList.add('masked');
const drop = $('drop'), fileInput = $('file');
drop.onclick = () => fileInput.click();
drop.ondragover = e => { e.preventDefault(); drop.classList.add('on'); };
drop.ondragleave = () => drop.classList.remove('on');
drop.ondrop = e => { e.preventDefault(); drop.classList.remove('on'); addFiles(e.dataTransfer.files); };
fileInput.onchange = () => { addFiles(fileInput.files); fileInput.value=''; };
function addFiles(list){
  for (const f of list){
    if (files.length >= 16) break;
    files.push({ name:f.name, mime:f.type||'image/png', url:URL.createObjectURL(f), file:f });
  }
  renderThumbs();
}
async function addAsInput(url, name){
  if (files.length >= 16){ alert('输入图片已达上限（16 张）'); return; }
  try{
    const blob = await (await fetch(url)).blob();
    const ext = (blob.type.split('/')[1] || 'png').replace('jpeg', 'jpg');
    const f = new File([blob], name || ('input.' + ext), { type: blob.type || 'image/png' });
    files.push({ name:f.name, mime:f.type, url:URL.createObjectURL(f), file:f });
    if (mode !== 'edit') setMode('edit');
    persistParams(); renderThumbs();
  }catch(e){ alert('引用失败：' + e); }
}
function revealImage(name){
  fetch('/api/reveal?name=' + encodeURIComponent(name)).then(r => r.json()).then(j => {
    if (j.error) alert('本地查看失败：' + j.error);
  }).catch(e => alert('本地查看失败：' + e));
}
const dropMask = $('dropMask'), fileMask = $('fileMask');
dropMask.onclick = () => fileMask.click();
fileMask.onchange = () => {
  const f = fileMask.files[0];
  if (f){ maskFile = { name:f.name, mime:f.type||'image/png', url:URL.createObjectURL(f), file:f }; }
  fileMask.value = '';
  renderMask();
};

// ---------------- 蒙版绘制（点击“绘制蒙版”按钮） ----------------
let mBase = null, mStroke = null, mCtx = null, sCtx = null, mPainting = false;
function openMaskEditor(){
  if (!files.length){ alert('请先上传至少一张原图，再绘制蒙版'); return; }
  const img = new Image();
  img.onload = () => {
    const cv = $('maskCv'), w = img.naturalWidth, h = img.naturalHeight;
    cv.width = w; cv.height = h;
    mBase = document.createElement('canvas'); mBase.width = w; mBase.height = h;
    mBase.getContext('2d').drawImage(img, 0, 0);
    mStroke = document.createElement('canvas'); mStroke.width = w; mStroke.height = h;
    sCtx = mStroke.getContext('2d');
    sCtx.strokeStyle = '#ff4040'; sCtx.lineCap = 'round'; sCtx.lineJoin = 'round';
    mCtx = cv.getContext('2d');
    redrawMask();
    $('maskModal').style.display = 'flex';
  };
  img.src = files[0].url;
}
function redrawMask(){
  if (!mCtx) return;
  const cv = $('maskCv');
  mCtx.clearRect(0, 0, cv.width, cv.height);
  mCtx.drawImage(mBase, 0, 0);
  mCtx.globalAlpha = 0.55; mCtx.drawImage(mStroke, 0, 0); mCtx.globalAlpha = 1;
}
function maskPos(e){
  const cv = $('maskCv'), r = cv.getBoundingClientRect();
  return { x:(e.clientX - r.left) * cv.width / r.width,
           y:(e.clientY - r.top) * cv.height / r.height };
}
$('maskCv').addEventListener('pointerdown', e => {
  if (!sCtx) return;
  mPainting = true;
  const p = maskPos(e);
  sCtx.lineWidth = +$('brushSize').value;
  sCtx.beginPath(); sCtx.moveTo(p.x, p.y); sCtx.lineTo(p.x + 0.01, p.y); sCtx.stroke();
  redrawMask();
});
$('maskCv').addEventListener('pointermove', e => {
  if (!mPainting || !sCtx) return;
  const p = maskPos(e);
  sCtx.lineWidth = +$('brushSize').value;
  sCtx.lineTo(p.x, p.y); sCtx.stroke();
  redrawMask();
});
window.addEventListener('pointerup', () => mPainting = false);
$('brushSize').oninput = () => $('brushVal').textContent = $('brushSize').value;
function clearMaskCanvas(){
  if (!sCtx) return;
  sCtx.clearRect(0, 0, mStroke.width, mStroke.height);
  redrawMask();
}
function closeMaskEditor(){ $('maskModal').style.display = 'none'; }
function saveMaskEditor(){
  if (!mStroke){ closeMaskEditor(); return; }
  const out = document.createElement('canvas');
  out.width = mStroke.width; out.height = mStroke.height;
  const octx = out.getContext('2d');
  octx.fillStyle = '#000'; octx.fillRect(0, 0, out.width, out.height);
  octx.globalCompositeOperation = 'destination-out';
  octx.drawImage(mStroke, 0, 0);
  out.toBlob(b => {
    const f = new File([b], 'mask-drawn.png', { type:'image/png' });
    if (maskFile && maskFile.url && maskFile.url.startsWith('blob:')) URL.revokeObjectURL(maskFile.url);
    maskFile = { name:'mask-drawn.png', mime:'image/png', url:URL.createObjectURL(f), file:f };
    renderMask();
    closeMaskEditor();
  }, 'image/png');
}

async function fileToB64(f){
  return new Promise((res, rej) => { const r = new FileReader();
    r.onload = () => res(r.result.split(',')[1]); r.onerror = rej; r.readAsDataURL(f); });
}

function currentSize(){
  const r = $('sizeRatio').value;
  if (r === 'auto') return 'auto';
  if (r === 'custom'){
    const v = ($('customSize').value || '').trim().toLowerCase();
    return v || 'auto';
  }
  const vals = (window.RATIO_MAP || {})[r] || [];
  return vals[+($('sizeTier').value || 0)] || 'auto';
}

let bgPollTimer = null;
function toBackground(){
  // 通知服务端进入后台面板，再断开前端 fetch（AbortController 只影响浏览器等待，服务端任务继续）
  genBgNow = true;
  if (genJobId) fetch('/api/jobs/background', { method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({job_id: genJobId}) }).catch(()=>{});
  if (genAbort) genAbort.abort();
  $('go').disabled = false; $('go').textContent = '生成（约 60~90 秒 / 张）';
  $('toBgBtn').style.display = 'none';
  $('status').className = 'status';
  $('status').textContent = '任务已转入后台：' + (genJobId||'');
  toggleJobsPanel(true); refreshJobs();
}
function toggleJobsPanel(show){
  $('jobsPanel').style.display = show ? '' : 'none';
  if (show) refreshJobs();
  if (bgPollTimer){ clearInterval(bgPollTimer); bgPollTimer = null; }
  if (show) bgPollTimer = setInterval(refreshJobs, 3000);
}
async function refreshJobs(force){
  try{
    const j = await (await fetch('/api/jobs')).json();
    const jobs = j.jobs || [];
    let running = 0;
    $('jobsList').innerHTML = jobs.map(t => {
      const stMap = {running:['run','进行中'], done:['ok','已完成'], failed:['fail','失败'], cancelled:['can','已中止']};
      const [cls, label] = stMap[t.status] || ['can', t.status];
      if (t.status === 'running') running++;
      const tstr = t.status === 'running'
        ? '已等 ' + Math.round((Date.now()/1000 - t.t0)) + ' 秒'
        : (t.elapsed || 0) + ' 秒';
      const imgs = (t.images||[]).length ? `，${t.images.length} 张已入库` : '';
      const err = t.error ? `，${t.error.slice(0,60)}` : '';
      return `<div class="jobItem">
        <div class="jTop">
          <span class="${cls}">● ${label}</span>
          <span class="jid">${t.id}</span>
          ${t.status==='failed' ? `<a class="retry" href="javascript:void(0)" onclick="retryJob('${t.id}')" title="用原参数重新生成">重试</a>` : ''}
          <a class="del" href="javascript:void(0)" onclick="jobX('${t.id}','${t.status}')" title="${t.status==='running'?'中止任务':'从列表移除'}">✕</a>
        </div>
        <div class="jMid">${t.mode==='edit'?'改图':'文生图'} · ${t.model} · ${t.size} · ${tstr}${imgs}</div>
        ${t.error ? `<div class="jErr">${t.error.slice(0,80)}</div>` : ''}
        <div class="jSub">${t.pshow||''}</div>
      </div>`;
    }).join('') || '<div class="jobItem" style="color:var(--muted)">暂无任务</div>';
    $('jobsRun').textContent = running;
    if (running === 0 && !force && !jobs.some(t => t.status==='done' && !(seenDone||{})[t.id])){
      // 有新完成任务时刷一次历史
      loadHistory();
    }
    (window.seenDone = window.seenDone || {});
    jobs.forEach(t => { if (t.status==='done') window.seenDone[t.id] = 1; });
    if (running === 0 && bgPollTimer){ clearInterval(bgPollTimer); bgPollTimer = null; }
  }catch(e){ /* 面板静默 */ }
}
async function clearJobs(){
  await fetch('/api/jobs/clear', { method:'POST' });
  refreshJobs();
}
async function cancelJob(jid){
  await fetch('/api/cancel', { method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({job_id: jid}) });
  refreshJobs();
  setTimeout(refreshJobs, 800);  // 服务端感知断开需要片刻，补刷一次
  setTimeout(refreshJobs, 2500);
}
async function retryJob(jid){
  const r = await (await fetch('/api/jobs/retry', { method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({job_id: jid}) })).json();
  if (r.error){ alert('重试失败：' + r.error); return; }
  refreshJobs();
}
function jobX(jid, status){
  if (status === 'running'){ cancelJob(jid); return; }
  // 已结束的任务：从列表移除
  fetch('/api/jobs/delete', { method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({job_id: jid}) })
    .then(() => refreshJobs()).catch(() => {});
}
function stopGenerate(){
  if (genJobId){
    fetch('/api/cancel', { method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({job_id: genJobId}) }).catch(()=>{});
  }
  if (genAbort) genAbort.abort();
}

async function generate(){
  if (genAbort){ stopGenerate(); return; }
  if (genBusy) return;   // 参数准备中（改图需编码大图），防快速连点重复提交
  genBusy = true;
  try {   // 包住全流程：任何路径结束（校验早退/中止/完成）都解除互斥
  const prompt = $('prompt').value.trim();
  const st = $('status');
  st.className = 'status'; st.textContent = '';
  if (!prompt){ st.className='status err'; st.textContent='请先填写提示词'; return; }
  if (mode==='edit' && !files.length){ st.className='status err'; st.textContent='改图模式请先上传至少一张图片'; return; }
  const size = currentSize();
  if (size !== 'auto' && !/^\d{1,5}x\d{1,5}$/.test(size) && !['1024x1024','1024x1536','1536x1024','2048x1152','3840x2160'].includes(size)){
    st.className='status err'; st.textContent='自定义尺寸格式应为 WxH，例如 2048x1152'; return; }

  persistParams();
  const payload = {
    mode, prompt,
    model: $('model').value,
    size,
    n: +$('n').value,
    quality: $('quality').value,
    background: (mode==='gen' && $('background').value) || '',
    output_format: $('format').value,
    output_compression: +$('comp').value,
    moderation: $('moderation').value,
    images: [], mask: null
  };
  if (mode==='edit'){
    for (const f of files) payload.images.push({ name:f.name, mime:f.mime, data:await fileToB64(f.file) });
    if (maskFile) payload.mask = { name:maskFile.name, mime:maskFile.mime, data:await fileToB64(maskFile.file) };
  }

  genAbort = new AbortController();
  genJobId = 'job-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
  payload.job_id = genJobId;
  $('go').textContent = '中止生成';
  $('toBgBtn').style.display = '';
  st.textContent = '正在请求中，再次点击按钮可中止本次请求……';
  const t0 = Date.now();
  const timer = setInterval(() => { st.textContent = `正在请求中，已等待 ${((Date.now()-t0)/1000).toFixed(0)} 秒……`; }, 1000);
  try{
    const r = await fetch('/api/generate', { method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload), signal: genAbort.signal });
    const j = await r.json();
    clearInterval(timer);
    if (j.error){ st.className='status err';
      st.textContent = '生成失败：' + j.error + (j.detail ? '\n' + j.detail : ''); return; }
    st.textContent = `完成 · ${j.model} · ${j.size} · 耗时 ${j.elapsed}s` + (j.usage ? ` · 用量 ${JSON.stringify(j.usage)}` : '');
    $('results').innerHTML = j.images.map(im => card(im)).join('');
    bindCard(); loadHistory();
  }catch(e){
    clearInterval(timer);
    if (e && e.name === 'AbortError'){ st.className='status';
      st.textContent = genBgNow ? '任务已转入后台，进度见右侧面板' : '已中止本次请求'; }
    else { st.className='status err'; st.textContent = '请求异常：' + e + '（服务是否还在运行？）'; }
  }finally{ $('go').disabled = false; $('go').textContent = '生成（约 60~90 秒 / 张）'; genAbort = null;
    $('toBgBtn').style.display = 'none';
    if (genBgNow){ toggleJobsPanel(true); } else { refreshJobs(); }
    genBgNow = false; }
  } finally { genBusy = false; }
}

function card(im){
  const kb = im.size ? (im.size/1024).toFixed(0)+' KB' : '';
  return `<div class="card${im.fav?' fav':''}" data-name="${im.name||''}">
    <img src="${im.url}" data-full="${im.url}" loading="lazy">
    <div class="meta"><span>${im.name||''}</span><span><span class="dims">…</span>${kb?' · '+kb:''}</span></div>
    <div class="ops"><a href="javascript:void(0)" onclick="toggleFav('${im.name||''}')">${im.fav?'取消收藏':'收藏'}</a>
    <a href="javascript:void(0)" onclick="renameImage('${im.name||''}')">重命名</a>
    <a href="javascript:void(0)" onclick="addAsInput('${im.url}','${im.name||''}')">引用</a>
    <a href="${im.url}" download="${im.name||'image'}">下载</a>
    <a href="javascript:void(0)" onclick="revealImage('${im.name||''}')">本地查看</a></div></div>`;
}
function bindCard(){
  document.querySelectorAll('#results img[data-full], #history img[data-full]').forEach(img=>{
    if (maskOn) img.classList.add('masked');
    img.onclick = () => {
      if (maskOn){ img.classList.toggle('masked'); return; }
      $('lbImg').src = img.dataset.full; $('lb').style.display='flex';
    };
    img.ondblclick = () => { $('lbImg').src = img.dataset.full; $('lb').style.display='flex'; };
    const dims = img.parentElement.querySelector('.dims');
    if (dims){
      const set = () => { if (img.naturalWidth) dims.textContent = img.naturalWidth + '×' + img.naturalHeight; };
      if (img.complete && img.naturalWidth) set(); else img.addEventListener('load', set);
    }
  });
}

let favOnly = false;
async function loadHistory(){
  try{
    const items = await (await fetch('/api/history' + (favOnly ? '?fav=1' : ''))).json();
    $('history').innerHTML = items.length
      ? items.map(im => card(im)).join('')
      : `<div class="empty">${favOnly ? '收藏夹为空' : '暂无历史记录'}</div>`;
    bindCard();
  }catch(e){ $('history').innerHTML = '<div class="empty">历史加载失败</div>'; }
}
function toggleFavOnly(){
  favOnly = !favOnly;
  $('favOnlyBtn').classList.toggle('on', favOnly);
  loadHistory();
}

function post(url, body){
  return fetch(url, { method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body) }).then(r => r.json());
}
function toggleFav(name){
  const first = document.querySelector('.card[data-name="' + CSS.escape(name) + '"]');
  post('/api/fav', { name, fav: !(first && first.classList.contains('fav')) }).then(j => {
    if (j.error) return alert('收藏失败：' + j.error);
    document.querySelectorAll('.card[data-name="' + CSS.escape(name) + '"]').forEach(el => {
      el.classList.toggle('fav', j.fav);
      const a = [...el.querySelectorAll('a')].find(x => x.textContent === '收藏' || x.textContent === '取消收藏');
      if (a) a.textContent = j.fav ? '取消收藏' : '收藏';
    });
  }).catch(e => alert('收藏失败：' + e));
}
function renameImage(name){
  const to = prompt('重命名为（需带图片扩展名，如 my-asset.png）：', name);
  if (!to || to === name) return;
  post('/api/rename', { name, to }).then(j => {
    if (j.error) return alert('重命名失败：' + j.error);
    document.querySelectorAll('.card[data-name="' + CSS.escape(name) + '"]').forEach(el => {
      el.dataset.name = j.name;
      el.querySelector('.meta span').textContent = j.name;
      const img = el.querySelector('img');
      img.src = j.url; img.dataset.full = j.url;
      const dl = el.querySelector('a[download]');
      dl.href = j.url; dl.setAttribute('download', j.name);
      el.querySelectorAll('a[onclick]').forEach(a => {
        a.setAttribute('onclick', (a.getAttribute('onclick')||'').split(name).join(j.name));
      });
    });
    loadHistory();
  }).catch(e => alert('重命名失败：' + e));
}


/* ---------- 中转站分组管理 ---------- */
let editGroups = [], editActive = '', gi = 0;
function closeSettings(){ $('settingsModal').style.display = 'none'; }
async function openSettings(){
  try{
    const s = await (await fetch('/api/groups')).json();
    editGroups = (s.groups||[]).map(g => ({ name:g.name, base_url:g.base_url, api_key:'',
      has_key:g.has_key, key_masked:g.key_masked, models:(g.models||[]).slice(), proxy:g.proxy||'' }));
    editActive = s.active || '';
    gi = Math.max(0, editGroups.findIndex(g => g.name === editActive));
    renderGroupEditor();
  }catch(e){ alert('读取分组失败：' + e); }
  $('settingsModal').style.display = 'flex';
}
function renderGroupEditor(){
  $('setGroup').innerHTML = editGroups.map((g,i) =>
    `<option value="${i}">${g.name}${g.name===editActive?'（当前）':''}</option>`).join('');
  $('setGroup').value = gi;
  const g = editGroups[gi] || {};
  $('grpName').value = g.name || '';
  $('grpUrl').value = g.base_url || '';
  $('grpKey').value = '';
  $('keyMasked').textContent = g.has_key ? `（已存 ${g.key_masked}，留空不改）` : '（未设置密钥）';
  $('grpProxy').value = g.proxy || '';
  $('grpModels').value = (g.models || []).join('\n');
  $('setStatus').textContent = '';
}
function collectEditor(){
  const g = editGroups[gi];
  if (!g) return;
  g.name = $('grpName').value.trim();
  g.base_url = $('grpUrl').value.trim();
  const k = $('grpKey').value.trim();
  if (k){ g.api_key = k; g.has_key = true; g.key_masked = k.slice(0,6) + '****' + k.slice(-4); }
  g.proxy = $('grpProxy').value.trim();
  g.models = $('grpModels').value.split('\n').map(s => s.trim()).filter(Boolean);
}
function newGroup(){
  collectEditor();
  editGroups.push({ name:'新分组' + (editGroups.length+1), base_url:'', api_key:'',
    has_key:false, key_masked:'', models:[], proxy:'' });
  gi = editGroups.length - 1;
  renderGroupEditor();
}
function delGroup(){
  if (editGroups.length <= 1){ setErr('至少保留一个分组'); return; }
  if (!confirm(`删除分组「${editGroups[gi].name}」？（不会删除任何图片）`)) return;
  editGroups.splice(gi, 1);
  gi = Math.min(gi, editGroups.length - 1);
  renderGroupEditor();
}
function setErr(msg){ $('setStatus').className='status err'; $('setStatus').textContent = msg; }
async function fetchModels(){
  collectEditor();
  const g = editGroups[gi];
  if (!g.base_url){ setErr('请先填写中转站地址'); return; }
  $('setStatus').className='status'; $('setStatus').textContent = '正在拉取模型列表……';
  const j = await post('/api/models', { name: g.name, base_url: g.base_url,
    api_key: g.api_key, proxy: g.proxy });
  if (j.error){ setErr('拉取失败：' + j.error); return; }
  g.models = j.models;
  $('grpModels').value = j.models.join('\n');
  $('setStatus').textContent = `已拉取 ${j.models.length} 个模型（尚未保存，请点「保存全部分组」）`;
}
async function saveAllGroups(silent){
  collectEditor();
  for (const g of editGroups){
    if (!g.name){ if(!silent) setErr('分组名称不能为空'); return null; }
    if (!g.base_url.startsWith('http')){ if(!silent) setErr(`分组「${g.name}」地址需以 http(s):// 开头`); return null; }
    if (!g.has_key && !g.api_key){ if(!silent) setErr(`分组「${g.name}」未填写密钥`); return null; }
  }
  const j = await post('/api/groups', { groups: editGroups });
  if (j.error){ if(!silent) setErr('保存失败：' + j.error); return null; }
  editActive = j.active;
  await refreshHeader();
  if (!silent){
    $('setStatus').className='status'; $('setStatus').textContent = '已保存 ✓';
    renderGroupEditor();
  }
  return j;
}
async function useGroup(){
  const saved = await saveAllGroups(true);
  if (!saved) return;
  const j = await post('/api/group/switch', { name: editGroups[gi].name });
  if (j.error){ setErr('切换失败：' + j.error); return; }
  editActive = j.group;
  await refreshHeader();
  applyModels(j.models, j.model);
  $('setStatus').className='status'; $('setStatus').textContent = `已切换到「${j.group}」✓`;
  setTimeout(closeSettings, 700);
}
async function switchGroupHeader(){
  const name = $('groupSel').value;
  const j = await post('/api/group/switch', { name });
  if (j.error){ alert('切换失败：' + j.error); await refreshHeader(); return; }
  applyModels(j.models, j.model);
}
async function refreshHeader(){
  try{
    const s = await (await fetch('/api/groups')).json();
    $('groupSel').innerHTML = (s.groups||[]).map(g => `<option value="${g.name}">${g.name}</option>`).join('');
    $('groupSel').value = s.active || '';
  }catch(e){}
}
function applyModels(models, model){
  const list = models || [];
  $('model').innerHTML = list.map(m => `<option value="${m}">${m}</option>`).join('');
  $('model').value = list.includes(model) ? model : (list[0] || '');
  onModelChange();
}
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="gpt-image 本地 WebUI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    args = parser.parse_args()

    cfg = load_config()
    set_proxy(cfg.get("proxy"))
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    try:
        httpd = QuietServer((args.host, args.port), Handler)
    except OSError as e:
        print(f"[gpt-image WebUI] 启动失败：端口 {args.port} 被占用（{e}）")
        print("[gpt-image WebUI] 常见原因：另一个副本还在运行（例如桌面旧版）。请先关闭它的黑色窗口，再重试本副本；")
        print(f"[gpt-image WebUI] 或者换端口启动：python app.py --port 9000")
        raise SystemExit(1)
    httpd.app_config = cfg  # type: ignore[attr-defined]
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
    print(f"[gpt-image WebUI] 服务已启动：{url}")
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


if __name__ == "__main__":
    main()
