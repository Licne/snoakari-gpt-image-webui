#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成核心：参数构造、上游调用、结果落盘"""
import base64
import json
import os
import re
import time
import urllib.error
import uuid

from .jobs import (_ACTIVE_JOBS, _JOBS_LOCK, _bg_finish, _register_job,
                   _register_resp, fetch_bytes, read_response)
from .network import api_request
from .storage import FORMATS, IMG_EXTS, OUTPUT_DIR, SIZE_PRESETS, log

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
