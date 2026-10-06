#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2ray-confighub 每日免费节点抓取整理
- 从公开免费节点源抓取订阅内容
- 按内容哈希自动去重（不同网址但内容完全相同只保留一份）
- 网页直接展示节点的源 -> 自动存为 txt 保存到项目 nodes/日期/
- txt 订阅链接的源 -> 把完整链接贴到当日页面
- 生成 data/YYYY-MM-DD.json + 更新 data/index.json
纯标准库，无第三方依赖。
"""
import urllib.request, urllib.parse
import json, re, os, hashlib, base64
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
NODES_DIR = os.path.join(BASE, "nodes")
TZ_SH = timezone(timedelta(hours=8))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 固定订阅源：(名称, 订阅URL)
SUB_SOURCES = [
    ("Pawdroid", "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub"),
    ("ripaojiedian", "https://raw.githubusercontent.com/ripaojiedian/freenode/main/sub"),
    ("ermaozi", "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/v2ray.txt"),
    ("freefq", "https://raw.githubusercontent.com/freefq/free/master/v2"),
    ("NoMoreWalls", "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt"),
    ("openproxylist", "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt"),
]

PROTOS = ["vmess://", "vless://", "ss://", "ssr://", "trojan://",
          "hysteria://", "hysteria2://", "tuic://", "wireguard://", "socks://"]


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def decode_if_b64(raw: bytes) -> str:
    try:
        txt = raw.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""
    if not txt:
        return ""
    # 整文件 base64（无 :// 但像 base64）
    if "://" not in txt and re.fullmatch(r"[A-Za-z0-9+/=\s]+", txt) and len(txt) > 100:
        try:
            dec = base64.b64decode(re.sub(r"\s", "", txt)).decode("utf-8", errors="ignore")
            if "://" in dec:
                return dec
        except Exception:
            pass
    return txt


def count_nodes(text: str) -> int:
    n = sum(text.count(p) for p in PROTOS)
    if n == 0:
        # 可能是每行一个 base64 节点
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        b64_lines = [l for l in lines if re.fullmatch(r"[A-Za-z0-9+/=]+", l) and len(l) > 40]
        if b64_lines:
            ok = 0
            for l in b64_lines[:50]:
                try:
                    d = base64.b64decode(l + "=" * (-len(l) % 4)).decode("utf-8", errors="ignore")
                    if "://" in d or any(k in d for k in ("ps", "add", "port", "id")):
                        ok += 1
                except Exception:
                    pass
            if ok:
                return int(ok / min(50, len(b64_lines)) * len(b64_lines))
    return n


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def get_nodefree_txt():
    """从 nodefree.org 首页找到最新文章里的每日 txt 订阅链接"""
    try:
        html = fetch("https://nodefree.org/", timeout=20).decode("utf-8", errors="ignore")
        posts = re.findall(r'href="(https://nodefree\.org/p/\d+\.html)"', html)
        seen = list(dict.fromkeys(posts))
        for p in seen[:3]:
            ph = fetch(p, timeout=20).decode("utf-8", errors="ignore")
            m = re.search(r'https?://[^"<> ]+\.txt', ph, re.I)
            if m:
                return "NodeFree", m.group(0)
    except Exception as e:
        print(f"  [nodefree fail] {e}")
    return None


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    today = datetime.now(TZ_SH).strftime("%Y-%m-%d")
    day_dir = os.path.join(NODES_DIR, today)
    os.makedirs(day_dir, exist_ok=True)

    raw_items = []  # (name, url, content_bytes|None)
    for name, url in SUB_SOURCES:
        print(f"fetch {name} ...", flush=True)
        try:
            raw = fetch(url)
            print(f"  -> {len(raw)} bytes", flush=True)
            raw_items.append((name, url, raw))
        except Exception as e:
            print(f"  [fail] {name}: {e}", flush=True)

    nf = get_nodefree_txt()
    if nf:
        name, url = nf
        print(f"fetch {name} ({url}) ...", flush=True)
        try:
            raw = fetch(url)
            raw_items.append((name, url, raw))
            print(f"  -> {len(raw)} bytes", flush=True)
        except Exception as e:
            print(f"  [txt unreachable, keep link only] {e}", flush=True)
            raw_items.append((name, url, None))

    # 按内容哈希去重
    seen_hash = {}
    entries = []
    for name, url, raw in raw_items:
        if raw is None:
            h = "unfetched:" + hashlib.sha256(url.encode()).hexdigest()[:16]
            text, node_count = "", -1
        else:
            h = hashlib.sha256(raw).hexdigest()
            text = decode_if_b64(raw)
            node_count = count_nodes(text)
        if h in seen_hash:
            # 内容完全相同：合并来源名，不重复收录
            seen_hash[h]["dup_sources"].append(name)
            seen_hash[h]["dup_urls"].append(url)
            print(f"  [dup] {name} 内容与 {seen_hash[h]['name']} 完全相同，已合并", flush=True)
            continue
        local_file = ""
        if raw is not None:
            fname = f"{slug(name)}.txt"
            with open(os.path.join(day_dir, fname), "wb") as f:
                f.write(raw)
            local_file = f"nodes/{today}/{fname}"
        entry = {
            "name": name, "url": url,
            "node_count": node_count,
            "hash": h[:16],
            "local_file": local_file,
            "dup_sources": [], "dup_urls": [],
        }
        seen_hash[h] = entry
        entries.append(entry)

    # 节点数多的排前面，未知放最后
    entries.sort(key=lambda e: e["node_count"], reverse=True)

    day_file = os.path.join(DATA_DIR, f"{today}.json")
    json.dump(entries, open(day_file, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    idx_file = os.path.join(DATA_DIR, "index.json")
    idx = []
    if os.path.exists(idx_file):
        try:
            idx = json.load(open(idx_file, encoding="utf-8"))
        except Exception:
            pass
    dates = {d["date"]: d for d in idx}
    total_nodes = sum(e["node_count"] for e in entries if e["node_count"] > 0)
    dates[today] = {"date": today, "count": len(entries), "nodes": total_nodes}
    idx = sorted(dates.values(), key=lambda d: d["date"], reverse=True)
    json.dump(idx, open(idx_file, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"done: {today} 去重后 {len(entries)} 个订阅源，共约 {total_nodes} 个节点", flush=True)


if __name__ == "__main__":
    main()
