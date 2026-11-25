# -*- coding: utf-8 -*-
"""
轻量 HTML 列表适配器
====================
用于 L1 政策门户等无 RSS/无 wp-json 的源：直接请求列表页，
CSS selector 提取文章链接，再回源正文。

配置项（source.config）：
  listing_url         列表页模板，可含 {page}
  link_selector       文章链接 selector
  next_selector       下一页 selector（可选）
  content_selector    正文 selector（可选）
  article_url_regex   链接过滤正则（可选）
  max_pages           最大翻页（默认 3）
"""
from __future__ import annotations

import re
from typing import Iterator, List, Optional
from urllib.parse import urljoin

from .base import AuditLog, HTTPSession, RawRecord, RawStore
from .playwright_adapter import _extract_article
from .site_search import BeautifulSoup


class HTMLAdapter:
    adapter_name = "html"

    def __init__(self, source: dict, http: HTTPSession, store: RawStore, audit: AuditLog):
        self.source = source
        self.http = http
        self.store = store
        self.audit = audit
        cfg = source.get("config") or {}
        self.listing_url = cfg.get("listing_url", "")
        self.link_selector = cfg.get("link_selector", "article a[href], h2 a[href], h3 a[href]")
        self.next_selector = cfg.get("next_selector")
        self.content_selector = cfg.get("content_selector")
        self.article_url_regex = cfg.get("article_url_regex")
        self.max_pages = int(cfg.get("max_pages", 3))

    def _listing_urls(self) -> List[str]:
        if not self.listing_url:
            return []
        if "{page}" in self.listing_url:
            return [self.listing_url.replace("{page}", str(p)) for p in range(1, self.max_pages + 1)]
        return [self.listing_url]

    def _extract_links(self, html: str, base_url: str) -> List[str]:
        if BeautifulSoup is None:
            return []
        soup = BeautifulSoup(html, "html.parser")
        hrefs = []
        seen = set()
        for a in soup.select(self.link_selector):
            href = a.get("href")
            if not href:
                continue
            full = urljoin(base_url, href)
            if self.article_url_regex and not re.search(self.article_url_regex, full):
                continue
            if full not in seen:
                seen.add(full)
                hrefs.append(full)
        return hrefs

    def follow_article(self, url: str) -> Optional[RawRecord]:
        try:
            resp = self.http.get(url)
            title, body, published, author = _extract_article(resp.text, self.content_selector)
            if len(body) < 200:
                return None
            rec = RawRecord(
                source_id=self.source["id"],
                layer=self.source["layer"],
                language=self.source.get("language", "en"),
                country=self.source.get("country", ""),
                url=url,
                title=title,
                text=body,
                published=published,
                author=author,
                content_type="article",
            )
            self.store.save(self.source["id"], rec, raw_payload=resp.text[:400000])
            return rec
        except Exception as e:
            self.audit.log(self.source["id"], self.adapter_name, "", url,
                           status="error", error=str(e)[:200])
            return None

    def collect(self, queries: List[tuple], max_per_query: int = 10) -> Iterator[RawRecord]:
        urls = self._listing_urls()
        if not urls:
            self.audit.log(self.source["id"], self.adapter_name, "", "",
                           status="skipped", error="config.listing_url 未配置")
            return

        collected: List[str] = []
        seen = set()
        for url in urls:
            try:
                resp = self.http.get(url)
                links = self._extract_links(resp.text, resp.url)
                for link in links:
                    if link not in seen:
                        seen.add(link)
                        collected.append(link)
                # 翻页
                if self.next_selector:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    nxt = soup.select_one(self.next_selector)
                    if nxt:
                        href = nxt.get("href")
                        if href:
                            nxt_url = urljoin(resp.url, href)
                            if nxt_url not in urls:
                                urls.append(nxt_url)
            except Exception as e:
                self.audit.log(self.source["id"], self.adapter_name, "", url,
                               status="error", error=str(e)[:200])
                continue

        self.audit.log(self.source["id"], self.adapter_name, "", urls[0],
                       status="ok", n_hits=len(collected))

        saved = 0
        for link in collected[:max_per_query]:
            rec = self.follow_article(link)
            if rec:
                rec.extra["via"] = "html"
                saved += 1
                yield rec
