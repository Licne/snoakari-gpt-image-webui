#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收藏夹（作品管理）层：多收藏夹、导入导出、旧收藏自动迁移"""
import hashlib
import io
import json
import os
import threading
import time
import zipfile

from .storage import DATA_DIR, FAV_PATH, IMG_MIMES, OUTPUT_DIR, log

COLLECTIONS_PATH = os.path.join(DATA_DIR, "collections.json")
EXPORT_FORMAT = "snoakari-favorites-export"
EXPORT_VERSION = 1
DEFAULT_NAME = "我的收藏"
_LOCK = threading.Lock()


# ---------- 底层读写 ----------

def _read_raw():
    if os.path.exists(COLLECTIONS_PATH):
        try:
            with open(COLLECTIONS_PATH, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("collections"), list):
                return d
        except Exception:
            pass
    return None


def _write_raw(d):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(COLLECTIONS_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def load_collections():
    """读取收藏夹数据；首次访问自动迁移旧 favorites.json 到默认夹"""
    with _LOCK:
        d = _read_raw()
        if d is None:
            items = []
            if os.path.exists(FAV_PATH):
                try:
                    with open(FAV_PATH, encoding="utf-8") as f:
                        old = json.load(f)
                    if isinstance(old, list):
                        items = [x for x in old if isinstance(x, str)]
                except Exception:
                    pass
            d = {"version": 1, "default_id": "c0",
                 "collections": [{"id": "c0", "name": DEFAULT_NAME, "items": items}]}
            _write_raw(d)
            if items:
                log(f"旧收藏已自动迁移到默认收藏夹「{DEFAULT_NAME}」：{len(items)} 张")
        # 规范化：id 去重、默认夹必须存在
        seen, cols = set(), []
        for c in d["collections"]:
            if not isinstance(c, dict):
                continue
            cid = str(c.get("id") or "").strip()
            if not cid or cid in seen:
                continue
            seen.add(cid)
            cols.append({"id": cid,
                        "name": str(c.get("name") or "未命名").strip() or "未命名",
                        "items": [x for x in (c.get("items") or [])
                                  if isinstance(x, str) and x]})
        if not cols:
            cols = [{"id": "c0", "name": DEFAULT_NAME, "items": []}]
        if d.get("default_id") not in [c["id"] for c in cols]:
            d["default_id"] = cols[0]["id"]
        d["collections"] = cols
        return d


def _save(d):
    with _LOCK:
        _write_raw(d)


def _new_id(d):
    import uuid
    while True:
        cid = "c" + uuid.uuid4().hex[:8]
        if cid not in [c["id"] for c in d["collections"]]:
            return cid


def _get(d, cid):
    return next((c for c in d["collections"] if c["id"] == cid), None)


# ---------- 面向 API 的操作 ----------

def list_collections():
    d = load_collections()
    out = [{"id": c["id"], "name": c["name"], "count": len(c["items"]),
            "is_default": c["id"] == d["default_id"]}
           for c in d["collections"]]
    return {"collections": out, "default_id": d["default_id"],
            "default_name": _get(d, d["default_id"])["name"]}


def default_items():
    d = load_collections()
    return set(_get(d, d["default_id"])["items"])


def items_of(cid):
    d = load_collections()
    c = _get(d, cid)
    if c is None:
        raise ValueError("收藏夹不存在")
    return set(c["items"])


def create_collection(name):
    name = (name or "").strip()
    if not name:
        raise ValueError("收藏夹名称不能为空")
    if len(name) > 40:
        raise ValueError("收藏夹名称过长（≤40 字）")
    d = load_collections()
    if any(c["name"] == name for c in d["collections"]):
        raise ValueError(f"收藏夹「{name}」已存在")
    cid = _new_id(d)
    d["collections"].append({"id": cid, "name": name, "items": []})
    _save(d)
    log(f"新建收藏夹：{name}")
    return {"id": cid, "name": name}


def rename_collection(cid, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("收藏夹名称不能为空")
    d = load_collections()
    c = _get(d, cid)
    if c is None:
        raise ValueError("收藏夹不存在")
    if any(x["name"] == name and x["id"] != cid for x in d["collections"]):
        raise ValueError(f"收藏夹「{name}」已存在")
    old = c["name"]
    c["name"] = name
    _save(d)
    log(f"收藏夹改名：{old} -> {name}")
    return {"id": cid, "name": name}


def delete_collection(cid):
    d = load_collections()
    if cid == d["default_id"]:
        raise ValueError("默认收藏夹不可删除（可改名）")
    c = _get(d, cid)
    if c is None:
        raise ValueError("收藏夹不存在")
    d["collections"] = [x for x in d["collections"] if x["id"] != cid]
    _save(d)
    log(f"删除收藏夹：{c['name']}（{len(c['items'])} 个条目已解除关联，图片保留）")
    return {"deleted": cid}


def set_item(cid, name, add):
    name = os.path.basename(name or "")
    d = load_collections()
    c = _get(d, cid)
    if c is None:
        raise ValueError("收藏夹不存在")
    if add:
        if not os.path.isfile(os.path.join(OUTPUT_DIR, name)):
            raise ValueError("文件不存在")
        if name not in c["items"]:
            c["items"].append(name)
    else:
        c["items"] = [x for x in c["items"] if x != name]
    _save(d)
    return {"ok": True, "add": add, "name": name}


def rename_file(old, new):
    """图片重命名后，同步所有收藏夹里的条目"""
    d = load_collections()
    changed = 0
    for c in d["collections"]:
        if old in c["items"]:
            c["items"] = [new if x == old else x for x in c["items"]]
            changed += 1
    if changed:
        _save(d)
    return changed


# ---------- 哈希去重 ----------

def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def import_image_bytes(data, name):
    """把图片字节落进 outputs/：重名比内容哈希——同内容跳过，不同内容加后缀。返回最终文件名"""
    name = os.path.basename(name or "")
    ext = os.path.splitext(name)[1].lower()
    if not name or ext not in IMG_MIMES:
        raise ValueError(f"不支持的图片类型：{name or '(空)'}")
    if not name or not name[0].isalnum():
        raise ValueError("文件名需以字母或数字开头")
    target = os.path.join(OUTPUT_DIR, name)
    if os.path.isfile(target):
        if _sha256_bytes(data) == _sha256_file(target):
            return name, True  # 同内容，跳过
        base, e = os.path.splitext(name)
        i = 1
        while True:
            cand = f"{base}-{i}{e}"
            target = os.path.join(OUTPUT_DIR, cand)
            if not os.path.exists(target):
                name = cand
                break
            if _sha256_bytes(data) == _sha256_file(target):
                return cand, True
            i += 1
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(target, "wb") as f:
        f.write(data)
    return name, False


# ---------- 导出 / 导入 ----------

def export_zip(cid="all"):
    d = load_collections()
    if cid == "all":
        cols = d["collections"]
    else:
        c = _get(d, cid)
        if c is None:
            raise ValueError("收藏夹不存在")
        cols = [c]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        manifest = {"format": EXPORT_FORMAT, "version": EXPORT_VERSION,
                    "exported_at": time.strftime("%Y-%m-%d"),
                    "collections": [{"name": c["name"], "items": c["items"]} for c in cols]}
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        seen = set()
        for c in cols:
            for fn in c["items"]:
                if fn in seen:
                    continue
                seen.add(fn)
                p = os.path.join(OUTPUT_DIR, fn)
                if os.path.isfile(p):
                    z.write(p, "files/" + fn)
    return buf.getvalue()


def import_zip(data):
    """导入收藏导出包：同名夹合并、文件按内容哈希去重。返回汇总"""
    if not (data[:2] == b"PK"):
        raise ValueError("不是有效的收藏导出包（zip）")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        if "manifest.json" not in names:
            raise ValueError("导出包缺少 manifest.json")
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        if manifest.get("format") != EXPORT_FORMAT:
            raise ValueError(f"未知的导出包格式：{manifest.get('format')}")
        d = load_collections()
        created = merged = added = skipped = dup_in_col = 0
        for col in manifest.get("collections") or []:
            cname = str(col.get("name") or "").strip()
            if not cname:
                continue
            c = next((x for x in d["collections"] if x["name"] == cname), None)
            if c is None:
                c = {"id": _new_id(d), "name": cname, "items": []}
                d["collections"].append(c)
                created += 1
            else:
                merged += 1
            for fn in col.get("items") or []:
                fn = os.path.basename(str(fn))
                zpath = "files/" + fn
                if zpath not in names:
                    continue
                final, same = import_image_bytes(z.read(zpath), fn)
                if same:
                    skipped += 1
                else:
                    added += 1
                if final in c["items"]:
                    dup_in_col += 1
                else:
                    c["items"].append(final)
        _save(d)
        log(f"导入收藏包：新建夹 {created}、合并夹 {merged}、新图 {added}、"
            f"内容重复跳过 {skipped}、夹内重复 {dup_in_col}")
        return {"created": created, "merged": merged, "added": added,
                "skipped": skipped, "dup": dup_in_col}
