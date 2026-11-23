# -*- coding: utf-8 -*-
"""
通用站内搜索适配器：selector 可配置，正文抽取 + 原始 HTML 快照。
search_url 模板 {q} 占位；selector 为空时使用 Readability 兜底策略。
"""
from __future__ import annotations

from typing import Iterator, List, Optional
from urllib.parse import quote_plus

from .base import AuditLog, HTTPSession, RawRecord, RawStore

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None


NOISE_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"]


def extract_text(html: str, content_selector: Optional[str] = None) -> str:
    """正文抽取：优先指定 selector，否则取文本最长的 <article>/<main>/<div>。"""
    if BeautifulSoup is None:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(NOISE_TAGS):
        t.decompose()
    node = None
    if content_selector:
        node = soup.select_one(content_selector)
    if node is None:
        for cand in soup.find_all(["article", "main", "section", "div"]):
            if cand is None:
                continue
            if node is None or len(cand.get_text(strip=True)) > len(node.get_text(strip=True)):
                node = cand
    return node.get_text("\n", strip=True) if node else soup.get_text("\n", strip=True)


class SiteSearchAdapter:
    adapter_name = "site"

    def __init__(self, source: dict, http: HTTPSession, store: RawStore, audit: AuditLog):
        self.source = source
        self.http = http
        self.store = store
        self.audit = audit
        self.selector = (source.get("config") or {}).get("content_selector")

    def _search_url(self, query: str) -> Optional[str]:
        tpl = self.source.get("search_url")
        if not tpl or "{q}" not in tpl:
            return None
        return tpl.replace("{q}", quote_plus(query))

    def follow_article(self, url: str) -> Optional[RawRecord]:
        """抓取单篇正文（用于 RSS/GDELT 命中链接的全文回源）。"""
        try:
            resp = self.http.get(url)
            text = extract_text(resp.text, self.selector)
            if len(text) < 200:
                return None
            rec = RawRecord(
                source_id=self.source["id"],
                layer=self.source["layer"],
                language=self.source["language"],
                country=self.source["country"],
                url=url,
                title=(BeautifulSoup(resp.text, "html.parser").title.get_text(strip=True)
                       if BeautifulSoup is not None and "<title" in resp.text else url),
                text=text,
                content_type="article",
            )
            self.store.save(self.source["id"], rec, raw_payload=resp.text[:400000])
            return rec
        except Exception:  # noqa: BLE001
            return None

    def collect(self, queries: List[tuple], max_per_query: int = 10) -> Iterator[RawRecord]:
        """queries: [(query_string, lang, country), ...]；search_url 缺失则记 skipped。"""
        for query, lang, country in queries:
            url = self._search_url(query)
            if not url:
                self.audit.log(self.source["id"], self.adapter_name, query,
                               "", status="skipped",
                               error="search_url 未配置（NEEDS_VERIFY），依赖 gdelt/google_news 通道")
                continue
            try:
                resp = self.http.get(url)
                soup = BeautifulSoup(resp.text, "html.parser")
                links = []
                for a in soup.select("a[href]"):
                    href = a.get("href", "")
                    if any(s in href for s in ("/20", "news", "article", "post", "topic", "car")):
                        import urllib.parse as up
                        full = up.urljoin(resp.url, href)
                        if full not in links:
                            links.append(full)
                self.audit.log(self.source["id"], self.adapter_name, query, url,
                               status="ok", n_hits=len(links))
                for link in links[:max_per_query]:
                    rec = self.follow_article(link)
                    if rec:
                        rec.extra["origin_query"] = query
                        yield rec
            except Exception as e:  # noqa: BLE001
                self.audit.log(self.source["id"], self.adapter_name, query, url,
                               status="error", error=str(e))
                continue
