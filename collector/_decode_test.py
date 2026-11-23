# -*- coding: utf-8 -*-
"""验证：Google News CBMi token 本地解码出真实文章 URL（临时脚本）"""
import base64
import re
import sqlite3

db = sqlite3.connect(r"D:\桌面\语料库论文\corpus\meta\corpus.sqlite")
urls = [r[0] for r in db.execute(
    "SELECT url FROM corpus_documents WHERE url LIKE '%news.google%' LIMIT 8")]


def decode_gnews(url: str) -> str | None:
    m = re.search(r"/rss/articles/([A-Za-z0-9_-]+)", url)
    if not m:
        return None
    token = m.group(1)
    pad = token + "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(pad)
    except Exception as e:
        return f"DECODE_FAIL: {e}"
    hits = re.findall(rb"https?://[\x20-\x7e]+", raw)
    if not hits:
        return None
    # 取第一个非 google 域名的 URL，截到非法字符为止
    u = hits[0].decode("ascii", errors="ignore")
    return u


for u in urls:
    print(decode_gnews(u))
