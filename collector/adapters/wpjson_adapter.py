# -*- coding: utf-8 -*-
"""
WordPress REST API (wp-json) 适配器
====================================
实测发现的正确通道：/?s= 站内搜索返回首页/栏目页（误判），
但站点公开的 wp-json 接口返回真实搜索结果 + 全文 content.rendered。

端点：{base}/wp-json/wp/v2/posts?search={q}&per_page=50&_fields=...
     （B 的实测：almuraba 767 篇均 5,000 词；arabgt 34 篇均 3,800 词）
"""
from __future__ import annotations

import json
from typing import Iterator, List
from urllib.parse import quote

from .base import AuditLog, HTTPSession, RawRecord, RawStore
from .site_search import extract_text


class WPJsonAdapter:
    adapter_name = "wpjson"

    def __init__(self, source: dict, http: HTTPSession, store: RawStore, audit: AuditLog):
        self.source = source
        self.http = http
        self.store = store
        self.audit = audit
        cfg = source.get("config") or {}
        self.base = (cfg.get("search_base") or "").rstrip("/")
        self.per_page = int(cfg.get("per_page", 50))

    def collect(self, queries: List[tuple], max_per_query: int = 30) -> Iterator[RawRecord]:
        if not self.base:
            self.audit.log(self.source["id"], self.adapter_name, "", "",
                           status="skipped", error="config.search_base 未配置")
            return
        for query, lang, country in queries:
            url = (f"{self.base}/wp-json/wp/v2/posts"
                   f"?search={quote(query)}&per_page={self.per_page}"
                   f"&_fields=id,link,title,excerpt,date,content")
            try:
                resp = self.http.get(url, timeout=40)
                items = resp.json()
                if not isinstance(items, list):
                    self.audit.log(self.source["id"], self.adapter_name, query, url,
                                   status="error", error=str(items)[:120])
                    continue
            except Exception as e:  # noqa: BLE001
                self.audit.log(self.source["id"], self.adapter_name, query, url,
                               status="error", error=str(e))
                continue

            saved = 0
            for it in items[:max_per_query]:
                content_html = (it.get("content") or {}).get("rendered", "")
                text = extract_text(content_html)
                if len(text.split()) < 60:
                    continue   # 空内容/截断
                title = (it.get("title") or {}).get("rendered", "")
                title = extract_text(title).strip() or title
                rec = RawRecord(
                    source_id=self.source["id"], layer=self.source["layer"],
                    language=lang, country=country,
                    url=it.get("link", ""), title=title, text=text,
                    published=(it.get("date") or "")[:19].replace("T", " "),
                    content_type="article",
                    extra={"origin_query": query, "via": "wp-json",
                           "wp_id": it.get("id"), "contributor_channel": "wpjson"},
                )
                self.store.save(self.source["id"], rec,
                                raw_payload=json.dumps(it, ensure_ascii=False)[:300000])
                saved += 1
                yield rec
            self.audit.log(self.source["id"], self.adapter_name, query, url,
                           status="ok", n_hits=len(items), saved=saved)
