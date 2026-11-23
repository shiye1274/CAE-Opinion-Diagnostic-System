# -*- coding: utf-8 -*-
"""
Reddit UGC 适配器（v0.2）
=========================
实测结论（2026-11-19）：
- reddit.com 直连被墙；走 Clash 代理仍 403（出口节点被 Reddit 拉黑，json/old/api 三端点全 403）
- Arctic Shift 公开存档 https://arctic-shift.photon-reddit.com 直连可用
  · 帖子: /api/posts/search?subreddit=X&limit=N
  · 评论: /api/comments/search?subreddit=X&limit=N
  · 不支持关键词搜索（仅 author/subreddit 过滤）→ 本地按品牌词过滤
故本适配器以 Arctic Shift 为主通道，Reddit JSON 作为可选备份（config.mode=json 时启用）。
"""
from __future__ import annotations

import hashlib
from typing import Iterator, List

from .base import AuditLog, HTTPSession, RawRecord, RawStore

ARCTIC = "https://arctic-shift.photon-reddit.com/api"

# 品牌 × 汽车场景本地过滤词（Arctic Shift 无关键词检索）
MATCH_TERMS = [
    "ev", "electric", "car", "cars", "vehicle", "tesla", "byd", "nio", "xpeng",
    "zeekr", "chery", "geely", "jetour", "mg ", "changan", "haval", "gwm",
    "hongqi", "lucid", "charger", "charging", "battery", "range", "dubai",
    "riyadh", "saudi", "gulf", "suv", "hybrid",
]


class RedditAdapter:
    adapter_name = "reddit"

    def __init__(self, source: dict, http: HTTPSession, store: RawStore, audit: AuditLog):
        self.source = source
        self.http = http
        self.store = store
        self.audit = audit
        self.subreddits = (source.get("config") or {}).get("subreddits", [])

    # ---------- 主通道：Arctic Shift ----------
    def _save_arctic(self, obj: dict, sub: str, ctype: str) -> RawRecord | None:
        text = (obj.get("title") or "") + " " + (obj.get("selftext") or obj.get("body") or "")
        low = text.lower()
        if not any(t in low for t in MATCH_TERMS):
            return None
        perma = obj.get("permalink", "")
        rec = RawRecord(
            source_id=self.source["id"],
            layer=self.source["layer"],
            language=self.source["language"],
            country=self.source["country"],
            url=f"https://www.reddit.com{perma}" if perma else f"https://www.reddit.com/r/{sub}/",
            title=(obj.get("title") or text[:80])[:300],
            text=text.strip(),
            published=str(obj.get("created_utc") or ""),
            author=obj.get("author"),
            engagement={"score": obj.get("score"), "num_comments": obj.get("num_comments")
                        or obj.get("total_reply_count")},
            content_type=ctype,
            parent_url=(f"https://www.reddit.com/r/{sub}/" if ctype == "post"
                        else obj.get("permalink")),
            extra={"subreddit": sub, "arctic_id": obj.get("id"),
                   "flair": obj.get("link_flair_text")},
        )
        self.store.save(self.source["id"], rec, raw_payload=str(obj)[:80000])
        return rec

    def _collect_arctic(self, max_per_query: int) -> Iterator[RawRecord]:
        for sub in self.subreddits:
            for endpoint, ctype in (("posts/search", "post"), ("comments/search", "comment")):
                url = f"{ARCTIC}/{endpoint}?subreddit={sub}&limit={max_per_query * 3}"
                try:
                    resp = self.http.get(url, timeout=40)
                    data = resp.json().get("data") or []
                    saved = 0
                    for obj in data:
                        rec = self._save_arctic(obj, sub, ctype)
                        if rec:
                            saved += 1
                            yield rec
                            if saved >= max_per_query:
                                break
                    self.audit.log(self.source["id"], self.adapter_name, f"{ctype}:{sub}",
                                   url, status="ok", n_hits=len(data), saved=saved)
                except Exception as e:  # noqa: BLE001
                    self.audit.log(self.source["id"], self.adapter_name, f"{ctype}:{sub}",
                                   url, status="error", error=str(e))

    # ---------- 备份通道：Reddit JSON（需 config.mode=json + 可用代理） ----------
    def _save_json(self, post: dict, sub: str, origin_query: str) -> RawRecord:
        rec = RawRecord(
            source_id=self.source["id"], layer=self.source["layer"],
            language=self.source["language"], country=self.source["country"],
            url=f"https://www.reddit.com{post.get('permalink', '')}",
            title=post.get("title", ""),
            text=post.get("selftext", "") or post.get("title", ""),
            published=str(post.get("created_utc", "")),
            author=post.get("author"),
            engagement={"score": post.get("score"), "num_comments": post.get("num_comments")},
            content_type="post",
            parent_url=f"https://www.reddit.com/r/{sub}/",
            extra={"origin_query": origin_query, "subreddit": sub},
        )
        self.store.save(self.source["id"], rec, raw_payload=str(post)[:100000])
        return rec

    def _collect_json(self, queries: List[tuple], max_per_query: int) -> Iterator[RawRecord]:
        for query, lang, country in queries:
            url = f"https://www.reddit.com/search.json?q={query}&limit={max_per_query}&sort=relevance&t=year"
            try:
                resp = self.http.get(url)
                posts = resp.json().get("data", {}).get("children", [])
                self.audit.log(self.source["id"], self.adapter_name, query, url,
                               status="ok", n_hits=len(posts))
                for child in posts[:max_per_query]:
                    yield self._save_json(child.get("data", {}), child.get("data", {}).get("subreddit", ""), query)
            except Exception as e:  # noqa: BLE001
                self.audit.log(self.source["id"], self.adapter_name, query, url,
                               status="error", error=str(e))

    def collect(self, queries: List[tuple], max_per_query: int = 20) -> Iterator[RawRecord]:
        mode = (self.source.get("config") or {}).get("mode", "arctic")
        if mode == "json":
            yield from self._collect_json(queries, max_per_query)
        else:
            yield from self._collect_arctic(max_per_query)
