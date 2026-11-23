# -*- coding: utf-8 -*-
"""检查 token 内部结构（临时脚本）"""
import base64
import re
import sqlite3

db = sqlite3.connect(r"D:\桌面\语料库论文\corpus\meta\corpus.sqlite")
url = db.execute(
    "SELECT url FROM corpus_documents WHERE url LIKE '%news.google%' LIMIT 1"
).fetchone()[0]
token = re.search(r"/rss/articles/([A-Za-z0-9_-]+)", url).group(1)
print("token len:", len(token), "| head:", token[:44])
pad = token + "=" * (-len(token) % 4)
raw = base64.urlsafe_b64decode(pad)
print("raw len:", len(raw))
print("hex head:", raw[:28].hex())
print("repr:", repr(raw[:80]))
