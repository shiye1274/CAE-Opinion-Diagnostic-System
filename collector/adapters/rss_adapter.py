# -*- coding: utf-8 -*-
"""
Google News RSS 适配器：实时增量 + 全源兜底通道。
每个 (品牌 × 国家 × 语言) 组合渲染一个 RSS 查询 URL，逐条解析产出 RawRecord。
"""
from __future__ import annotations

from typing import Iterator, List, Optional
from urllib.parse import quote_plus

from .base import AuditLog, HTTPSession, RawRecord, RawStore

RSS_TEMPLATES = {
    # lang → Google News RSS 参数
    "ar": dict(hl="ar", gl="SA", ceid="SA:ar"),
    "en": dict(hl="en", gl="AE", ceid="AE:en"),
    "zh": dict(hl="zh-CN", gl="CN", ceid="CN:zh-Hans"),
}


def gnews_rss_url(query: str, lang: str) -> str:
    p = RSS_TEMPLATES.get(lang, RSS_TEMPLATES["en"])
    return (f"https://news.google.com/rss/search?q={quote_plus(query)}"
            f"&hl={p['hl']}&gl={p['gl']}&ceid={p['ceid']}")


def parse_feed(xml_text: str) -> List[dict]:
    try:
        import xml.etree.ElementTree as ET
    except ImportError:  # pragma: no cover
        return []
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for it in root.iter("item"):
        def tag(t: str) -> Optional[str]:
            el = it.find(t)
            return el.text if el is not None else None
        items.append({
            "title": tag("title") or "",
            "link": tag("link") or "",
            "published": tag("pubDate"),
            "source": (it.find("source").text if it.find("source") is not None else ""),
        })
    return items


class RSSAdapter:
    adapter_name = "google_news"

    def __init__(self, http: HTTPSession, store: RawStore, audit: AuditLog,
                 source_id: str = "googlenews", layer: str = "L2", language: str = "auto"):
        self.http = http
        self.store = store
        self.audit = audit
        self.source_id = source_id
        self.layer = layer

    def collect(self, queries: List[tuple], max_per_query: int = 10) -> Iterator[RawRecord]:
        """queries: [(query_string, lang, country_code), ...]"""
        for query, lang, country in queries:
            url = gnews_rss_url(query, lang)
            try:
                resp = self.http.get(url)
                items = parse_feed(resp.text)
                self.audit.log(self.source_id, self.adapter_name, query, url,
                               status="ok", n_hits=len(items))
                saved = 0
                for it in items[:max_per_query]:
                    if not it["link"]:
                        continue
                    rec = RawRecord(
                        source_id=self.source_id,
                        layer=self.layer,
                        language=lang,
                        country=country,
                        url=it["link"],
                        title=it["title"],
                        text=it["title"],   # RSS 仅标题+摘要；全文由 pipeline 的 follow-link 或 site 通道补齐
                        published=it["published"],
                        content_type="article",
                        extra={"origin_query": query, "gnews_source": it["source"]},
                    )
                    self.store.save(self.source_id, rec, raw_payload=resp.text[:200000])
                    saved += 1
                    yield rec
                if len(items) > max_per_query:
                    self.audit.log(self.source_id, self.adapter_name, query, url,
                                   status="ok", n_hits=len(items), saved=saved,
                                   extra={"truncated": True})
            except Exception as e:  # noqa: BLE001
                self.audit.log(self.source_id, self.adapter_name, query, url,
                               status="error", error=str(e))
                continue
