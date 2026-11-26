#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""存储层：数据目录、config、收藏、常量表"""
import json
import os
import shutil
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
FAV_PATH = os.path.join(DATA_DIR, "favorites.json")


def migrate_v1():
    """v1 -> v2 一次性迁移：config.json / favorites.json / outputs -> data/"""
    moved = []
    os.makedirs(DATA_DIR, exist_ok=True)
    for src, dst in [(os.path.join(BASE_DIR, "config.json"), CONFIG_PATH),
                     (os.path.join(BASE_DIR, "favorites.json"), FAV_PATH),
                     (os.path.join(BASE_DIR, "outputs"), OUTPUT_DIR)]:
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                shutil.move(src, dst)
                moved.append(os.path.basename(src))
            except OSError:
                pass
    return moved


def log(msg):
    """控制台实时日志：显示在启动 WebUI 的黑色窗口里"""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


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
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)


def load_config():
    cfg = _read_disk_config()
    groups = normalize_groups(cfg)
    active_name = (cfg.get("active_group") or "").strip()
    if active_name not in [g["name"] for g in groups]:
        active_name = groups[0]["name"]
    g = next(x for x in groups if x["name"] == active_name)
    api_key = os.environ.get("GPT_IMAGE_API_KEY", "").strip() or (cfg.get("api_key") or "").strip() or g["api_key"]
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
