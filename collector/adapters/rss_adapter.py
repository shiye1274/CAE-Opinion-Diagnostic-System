# -*- coding: utf-8 -*-
"""
RSS 适配器
==========
1. Google News RSS：实时增量 + 全源兜底通道。
2. 源直采 RSS/Atom：source.config.feed_urls 指定订阅地址，
   可选按 query 关键词过滤标题/摘要。

每个 (品牌 × 国家 × 语言) 组合渲染一个 RSS 查询 URL，逐条解析产出 RawRecord。
"""
from __future__ import annotations

from typing import Iterator, List, Optional
from urllib.parse import quote_plus

import feedparser

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
    """使用 feedparser 解析 RSS/Atom，兼容 Google News 与通用源。"""
    items = []
    try:
        feed = feedparser.parse(xml_text)
    except Exception:
        return items
    for entry in feed.entries:
        published = (entry.get("published") or entry.get("updated") or
                     entry.get("pubDate") or "")
        items.append({
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "published": published,
            "source": (entry.get("source", {}).get("title")
                       if isinstance(entry.get("source"), dict)
                       else entry.get("source", "")),
            "summary": entry.get("summary", ""),
        })
    return items


def _matches_query(item: dict, query: str) -> bool:
    """简单关键词匹配：query 中所有非空词都需出现在标题或摘要中。"""
    terms = [t.lower() for t in query.replace("OR", " ").replace("\"", " ").split() if len(t) > 1]
    if not terms:
        return True
    hay = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    return all(t in hay for t in terms)


class RSSAdapter:
    adapter_name = "google_news"

    def __init__(self, http: HTTPSession, store: RawStore, audit: AuditLog,
                 source: Optional[dict] = None, source_id: str = "googlenews",
                 layer: str = "L2", language: str = "auto"):
        self.http = http
        self.store = store
        self.audit = audit
        self.source = source
        self.source_id = source_id
        self.layer = layer
        self.language = language
        self.feed_urls: List[str] = []
        if source:
            self.source_id = source["id"]
            self.layer = source["layer"]
            self.language = source.get("language", "auto")
            cfg = source.get("config") or {}
            self.feed_urls = cfg.get("feed_urls") or []
            if isinstance(self.feed_urls, str):
                self.feed_urls = [self.feed_urls]

    def _record_from_item(self, item: dict, query: str = "",
                          country: str = "") -> Optional[RawRecord]:
        link = item.get("link")
        if not link:
            return None
        rec = RawRecord(
            source_id=self.source_id,
            layer=self.layer,
            language=self.language,
            country=country or (self.source.get("country") if self.source else ""),
            url=link,
            title=item.get("title", ""),
            text=item.get("summary", item.get("title", "")),
            published=item.get("published"),
            content_type="article",
            extra={"origin_query": query, "gnews_source": item.get("source", "")},
        )
        self.store.save(self.source_id, rec, raw_payload=str(item)[:200000])
        return rec

    def _collect_feed(self, feed_url: str, queries: List[tuple],
                      max_per_query: int) -> Iterator[RawRecord]:
        try:
            resp = self.http.get(feed_url)
            items = parse_feed(resp.text)
        except Exception as e:
            self.audit.log(self.source_id, self.adapter_name, "", feed_url,
                           status="error", error=str(e)[:300])
            return

        saved_total = 0
        if not queries:
            # 无查询过滤：直接取前 N 条
            for it in items[:max_per_query]:
                rec = self._record_from_item(it)
                if rec:
                    saved_total += 1
                    yield rec
            self.audit.log(self.source_id, self.adapter_name, "", feed_url,
                           status="ok", n_hits=len(items), saved=saved_total)
            return

        for query, lang, country in queries:
            saved = 0
            for it in items:
                if not _matches_query(it, query):
                    continue
                rec = self._record_from_item(it, query=query, country=country)
                if rec:
                    saved += 1
                    yield rec
                if saved >= max_per_query:
                    break
            saved_total += saved
        self.audit.log(self.source_id, self.adapter_name, "", feed_url,
                       status="ok", n_hits=len(items), saved=saved_total)

    def _collect_google_news(self, queries: List[tuple],
                             max_per_query: int) -> Iterator[RawRecord]:
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
                        text=it["title"],   # RSS 仅标题+摘要；全文由 pipeline follow-link 补齐
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
                               status="error", error=str(e)[:300])
                continue

    def collect(self, queries: List[tuple], max_per_query: int = 10) -> Iterator[RawRecord]:
        """queries: [(query_string, lang, country_code), ...]"""
        if self.source and self.feed_urls:
            # 源直采模式
            self.adapter_name = "rss"
            for feed_url in self.feed_urls:
                yield from self._collect_feed(feed_url, queries, max_per_query)
        else:
            # Google News 兜底模式
            self.adapter_name = "google_news"
            yield from self._collect_google_news(queries, max_per_query)
