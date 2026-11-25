# -*- coding: utf-8 -*-
"""
Playwright 浏览器渲染适配器
============================
用于 NEEDS_BROWSER 源：先用 Playwright 渲染搜索/列表页，提取文章 URL，
再用 HTTPSession 抓取正文，复用 readability-lxml / BeautifulSoup 抽取
title/body/published/author/language。

配置项（source.config）：
  search_url          搜索模板，含 {q} 占位；为空则使用 listing_url
  listing_url         静态列表页模板，可含 {page}
  link_selector       文章链接 CSS selector（默认常见 WordPress 主题）
  wait_selector       页面加载后等待的元素（默认同 link_selector）
  next_selector       分页「下一页」selector（可选）
  content_selector    正文 CSS selector（可选）
  article_url_regex   过滤文章链接的正则（可选）
  max_pages           每个查询最多翻页数（默认 3）
  timeout             Playwright 等待超时 ms（默认 30000）
  headless            是否无头（默认 True，smoke 可开 False 调试）
"""
from __future__ import annotations

import json
import re
from typing import Iterator, List, Optional
from urllib.parse import urljoin, quote_plus

from .base import AuditLog, HTTPSession, RawRecord, RawStore
from .site_search import extract_text, BeautifulSoup

try:
    from readability import Document
except ImportError:  # pragma: no cover
    Document = None


def _extract_article(html: str, content_selector: Optional[str] = None) -> tuple:
    """返回 (title, body, published, author)。"""
    title = ""
    published = ""
    author = ""

    if Document is not None:
        try:
            doc = Document(html)
            title = (doc.title() or "").strip()
            body_html = doc.summary(html_partial=False)
            body = extract_text(body_html, content_selector)
        except Exception:
            body = extract_text(html, content_selector)
    else:
        body = extract_text(html, content_selector)

    # 兜底：BeautifulSoup 解析 meta
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        if not title:
            t = soup.find("title")
            title = t.get_text(strip=True) if t else ""
        # published
        for sel in [
            "meta[property='article:published_time']",
            "meta[name='publishedDate']",
            "meta[name='date']",
            "time[datetime]",
        ]:
            el = soup.select_one(sel)
            if el is not None:
                published = el.get("content") or el.get("datetime") or ""
                if published:
                    break
        # author
        for sel in [
            "meta[name='author']",
            "meta[property='article:author']",
            "a[rel='author']",
            ".author",
            "[class*='author']",
        ]:
            el = soup.select_one(sel)
            if el is not None:
                author = el.get("content") or el.get_text(strip=True)
                if author:
                    break
    return title, body, published, author


class PlaywrightAdapter:
    adapter_name = "playwright"

    def __init__(self, source: dict, http: HTTPSession, store: RawStore, audit: AuditLog):
        self.source = source
        self.http = http
        self.store = store
        self.audit = audit
        cfg = source.get("config") or {}
        self.search_url = (source.get("search_url") or "").strip()
        self.listing_url = cfg.get("listing_url", "")
        self.link_selector = cfg.get("link_selector", "article a[href], .post a[href], .entry-title a[href], h2 a[href]")
        self.wait_selector = cfg.get("wait_selector") or self.link_selector
        self.next_selector = cfg.get("next_selector")
        self.content_selector = cfg.get("content_selector")
        self.article_url_regex = cfg.get("article_url_regex")
        self.max_pages = int(cfg.get("max_pages", 3))
        self.timeout = int(cfg.get("timeout", 30000))
        self.headless = bool(cfg.get("headless", True))
        self.proxy = cfg.get("proxy")

    def _listing_urls(self, query: str) -> List[str]:
        """根据 query 生成需要渲染的列表页 URL。"""
        urls = []
        if self.search_url and "{q}" in self.search_url:
            base = self.search_url.replace("{q}", quote_plus(query))
            urls.append(base)
        elif self.listing_url:
            if "{page}" in self.listing_url:
                for p in range(1, self.max_pages + 1):
                    urls.append(self.listing_url.replace("{page}", str(p)))
            else:
                urls.append(self.listing_url)
        return urls

    def _extract_links(self, page) -> List[str]:
        """在已渲染页面上提取文章链接。"""
        hrefs = []
        try:
            page.wait_for_selector(self.wait_selector, timeout=self.timeout)
        except Exception as e:
            # 继续尝试，也许部分元素已加载
            pass
        elements = page.query_selector_all(self.link_selector)
        for el in elements:
            href = el.get_attribute("href")
            if not href:
                continue
            href = urljoin(page.url, href)
            if self.article_url_regex and not re.search(self.article_url_regex, href):
                continue
            # 简单去重
            if href not in hrefs:
                hrefs.append(href)
        return hrefs

    def _render_links(self, urls: List[str]) -> List[str]:
        """使用 Playwright 渲染所有列表页并收集链接。"""
        from playwright.sync_api import sync_playwright
        collected: List[str] = []
        seen = set()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, proxy={"server": self.proxy} if self.proxy else None)
            context = browser.new_context(
                user_agent=self.http.session.headers.get("User-Agent"),
                locale=self.source.get("language", "en"),
            )
            page = context.new_page()
            page.set_default_timeout(self.timeout)
            for url in urls:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 2)
                    # 额外等待动态内容
                    page.wait_for_timeout(2000)
                    links = self._extract_links(page)
                    for link in links:
                        if link not in seen:
                            seen.add(link)
                            collected.append(link)
                    # 翻页
                    if self.next_selector:
                        for _ in range(self.max_pages - 1):
                            nxt = page.query_selector(self.next_selector)
                            if not nxt:
                                break
                            href = nxt.get_attribute("href")
                            if not href:
                                break
                            nxt_url = urljoin(page.url, href)
                            page.goto(nxt_url, wait_until="domcontentloaded", timeout=self.timeout * 2)
                            page.wait_for_timeout(2000)
                            for link in self._extract_links(page):
                                if link not in seen:
                                    seen.add(link)
                                    collected.append(link)
                except Exception as e:
                    self.audit.log(self.source["id"], self.adapter_name, "",
                                   url, status="degraded", error=str(e)[:200])
                    continue
            context.close()
            browser.close()
        return collected

    def follow_article(self, url: str) -> Optional[RawRecord]:
        """用 HTTPSession 拉取正文并抽取。"""
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
        if not self.search_url and not self.listing_url:
            self.audit.log(self.source["id"], self.adapter_name, "", "",
                           status="skipped", error="config.search_url 或 listing_url 未配置")
            return

        # 若走 listing_url 模式，queries 仅用于过滤/记录，不构造 URL
        urls = []
        if self.listing_url and "{q}" not in self.listing_url:
            urls = self._listing_urls("")
        else:
            for query, lang, country in queries:
                urls.extend(self._listing_urls(query))

        if not urls:
            self.audit.log(self.source["id"], self.adapter_name, "", "",
                           status="skipped", error="无法生成列表页 URL")
            return

        try:
            links = self._render_links(urls)
        except Exception as e:
            self.audit.log(self.source["id"], self.adapter_name, "", urls[0],
                           status="error", error=str(e)[:300])
            return

        self.audit.log(self.source["id"], self.adapter_name, "", urls[0],
                       status="ok", n_hits=len(links))

        saved = 0
        for link in links[:max_per_query]:
            rec = self.follow_article(link)
            if rec:
                rec.extra["via"] = "playwright"
                saved += 1
                yield rec
        if saved == 0 and links:
            self.audit.log(self.source["id"], self.adapter_name, "", urls[0],
                           status="degraded", n_hits=len(links),
                           error="提取到链接但正文均不满足长度阈值")
