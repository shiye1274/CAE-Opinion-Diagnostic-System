# -*- coding: utf-8 -*-
"""复现 site_search NoneType 错误（临时）"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bs4
print("bs4 version:", bs4.__version__)

from adapters.base import AuditLog, HTTPSession, RawStore, load_sources
from adapters.site_search import SiteSearchAdapter, BeautifulSoup, extract_text
print("BeautifulSoup is None?", BeautifulSoup is None)

sources = {s["id"]: s for s in load_sources(Path(__file__).resolve().parent / "sources.yaml")}
s = sources["saudigazette"]
print("search_url:", s.get("search_url"))

audit = AuditLog("site_debug")
http = HTTPSession("saudigazette", rate=1.0, audit=audit, timeout=20)
store = RawStore()
ad = SiteSearchAdapter(s, http, store, audit)

try:
    n = 0
    for rec in ad.collect([("BYD", "en", "SA")], max_per_query=3):
        print("GOT:", rec.title[:60], rec.word_count if hasattr(rec, "word_count") else len(rec.text))
        n += 1
    print("saved:", n)
except Exception:
    traceback.print_exc()
audit.close()
