# -*- coding: utf-8 -*-
"""调试 Google News 重定向链接（临时脚本）"""
import re
import sqlite3
import requests

db = sqlite3.connect(r"D:\桌面\语料库论文\corpus\meta\corpus.sqlite")
url = db.execute("SELECT url FROM corpus_documents WHERE url LIKE '%news.google%' LIMIT 1").fetchone()[0]
print("URL:", url[:110])

P = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}
H = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")}
r = requests.get(url, headers=H, proxies=P, timeout=30)
print("status:", r.status_code, "| final url:", r.url[:100])
print("html len:", len(r.text))

# 找目标文章链接（排除 google 自身域名）
targets = re.findall(r'https?://(?!news\.google|www\.google|accounts\.google|policies\.google)[^"\'<>\s]+',
                     r.text)
uniq = []
for t in targets:
    t = t.rstrip('\\').rstrip(',')
    if t not in uniq:
        uniq.append(t)
print("候选目标链接:", len(uniq))
for t in uniq[:8]:
    print("  -", t[:120])
