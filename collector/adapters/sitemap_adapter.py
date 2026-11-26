# -*- coding: utf-8 -*-
"""
Sitemap 适配器
==============
L1 政策层最稳通道：直接读站点 sitemap.xml，按正则筛出文章 URL，再逐篇抓正文。
绕开站内搜索反爬、JS 列表页、robots 限制。

配置项（source.config）：
  sitemap_url       sitemap.xml 地址（可为 sitemap index，自动递归一层）
  sitemaps          多个 sitemap 地址列表（可选，优先于 sitemap_url）
  url_regex         文章 URL 过滤正则（必填，避免抓到导航页）
  max_articles      最多抓多少篇（默认 30）
  min_len           正文最短字符数（默认 200）
  content_selector  正文 CSS selector（可选）
  fetch_delay       每篇之间间隔秒数（默认 1.0，礼貌爬取）
"""
from __future__ import annotations

import re
import time
from typing import Iterator, List, Optional
from urllib.parse import urljoin

from .base import AuditLog, HTTPSession, RawRecord, RawStore
from .site_search import extract_text, BeautifulSoup


class SitemapAdapter:
    adapter_name = "sitemap"

    def __init__(self, source: dict, http: HTTPSession, store: RawStore, audit: AuditLog):
        self.source = source
        self.http = http
        self.store = store
        self.audit = audit
        cfg = source.get("config") or {}
        self.sitemaps: List[str] = list(cfg.get("sitemaps") or [])
        if not self.sitemaps and cfg.get("sitemap_url"):
            self.sitemaps = [cfg["sitemap_url"]]
        self.url_regex = cfg.get("url_regex") or ""
        self.max_articles = int(cfg.get("max_articles", 30))
        self.min_len = int(cfg.get("min_len", 200))
        self.content_selector = cfg.get("content_selector")
        self.fetch_delay = float(cfg.get("fetch_delay", 1.0))

    # ---------- sitemap 解析 ----------
    def _extract_locs(self, xml_text: str) -> tuple:
        """返回 (文章URL列表, 子sitemap列表)。"""
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml_text)
        subs = [l for l in locs if l.endswith(".xml")]
        arts = [l for l in locs if not l.endswith(".xml")]
        return arts, subs

    def _collect_article_urls(self) -> tuple:
        """拉取 sitemap（含一层 index 递归），返回过滤后的文章 URL。"""
        all_arts: List[str] = []
        subs_todo: List[str] = []
        for sm in self.sitemaps:
            try:
                resp = self.http.get(sm, timeout=30)
                arts, subs = self._extract_locs(resp.text)
                all_arts.extend(arts)
                subs_todo.extend(subs)
            except Exception as e:  # noqa: BLE001
                self.audit.log(self.source["id"], self.adapter_name, "", sm,
                               status="error", error=str(e)[:200])
        # 递归一层（sitemap index）
        for sub in subs_todo[:5]:
            try:
                resp = self.http.get(sub, timeout=30)
                arts, _ = self._extract_locs(resp.text)
                all_arts.extend(arts)
            except Exception:  # noqa: BLE001
                continue

        if self.url_regex:
            pat = re.compile(self.url_regex)
            all_arts = [u for u in all_arts if pat.search(u)]
        # 去重保序
        seen, uniq = set(), []
        for u in all_arts:
            if u not in seen:
                seen.add(u)
                uniq.append(u)
        return uniq, len(all_arts)

    # ---------- 单篇 ----------
    def follow_article(self, url: str) -> Optional[RawRecord]:
        try:
            resp = self.http.get(url, timeout=40)
            html = resp.text
            # 中文站常见 GBK/GB2312
            if resp.encoding in (None, "ISO-8859-1"):
                resp.encoding = resp.apparent_encoding or "utf-8"
                html = resp.text
            title = ""
            soup = BeautifulSoup(html, "html.parser")
            if soup.title:
                title = soup.title.get_text(strip=True)
            body = extract_text(html, self.content_selector)
            if len(body) < self.min_len:
                return None
            published = ""
            for sel in ["meta[property='article:published_time']",
                        "meta[name='publishedDate']", "meta[name='date']",
                        "time[datetime]", "meta[itemprop='datePublished']"]:
                el = soup.select_one(sel)
                if el is not None:
                    published = el.get("content") or el.get("datetime") or ""
                    if published:
                        break
            rec = RawRecord(
                source_id=self.source["id"],
                layer=self.source["layer"],
                language=self.source.get("language", "en"),
                country=self.source.get("country", ""),
                url=url,
                title=title or url,
                text=body,
                published=published,
                content_type="article",
                extra={"via": "sitemap", "contributor_channel": "sitemap"},
            )
            self.store.save(self.source["id"], rec, raw_payload=html[:400000])
            return rec
        except Exception as e:  # noqa: BLE001
            self.audit.log(self.source["id"], self.adapter_name, "", url,
                           status="error", error=str(e)[:200])
            return None

    # ---------- 主入口 ----------
    def collect(self, queries: List[tuple], max_per_query: int = 10) -> Iterator[RawRecord]:
        if not self.sitemaps:
            self.audit.log(self.source["id"], self.adapter_name, "", "",
                           status="skipped", error="config.sitemap_url 未配置")
            return
        if not self.url_regex:
            self.audit.log(self.source["id"], self.adapter_name, "", "",
                           status="skipped", error="config.url_regex 未配置（防抓导航页）")
            return

        urls, raw_n = self._collect_article_urls()
        if not urls:
            self.audit.log(self.source["id"], self.adapter_name, "", self.sitemaps[0],
                           status="error", error=f"sitemap 解析后 0 篇（原始 {raw_n}）")
            return

        cap = min(self.max_articles, max(max_per_query, 1) * 5)
        saved = 0
        for i, url in enumerate(urls[:cap]):
            rec = self.follow_article(url)
            if rec:
                saved += 1
                yield rec
            if i < cap - 1 and self.fetch_delay > 0:
                time.sleep(self.fetch_delay)

        self.audit.log(self.source["id"], self.adapter_name, "", self.sitemaps[0],
                       status="ok", n_hits=len(urls), saved=saved,
                       extra={"sitemap_urls": len(self.sitemaps)})
