# -*- coding: utf-8 -*-
"""
YouTube 适配器（双通道）：
1. yt_dlp_adapter — 关键词搜索 / 频道枚举 + 字幕下载（无需 API Key）
2. youtube_api    — YouTube Data API v3 评论区抓取（需环境变量 YOUTUBE_API_KEY）
"""
from __future__ import annotations

import json
import os
from typing import Iterator, List

from .base import AuditLog, HTTPSession, RawRecord, RawStore


class YTDLPSearchAdapter:
    """关键词搜索 / 频道视频枚举 + 字幕（阿语优先）。"""
    adapter_name = "yt_dlp"

    def __init__(self, source: dict, store: RawStore, audit: AuditLog,
                 proxy: str | None = None):
        self.source = source
        self.store = store
        self.audit = audit
        self.cfg = source.get("config") or {}
        self.proxy = proxy
        # 字幕抓取会话（ytimg/googlevideo 属 Google 域 → 走代理）
        from .base import HTTPSession
        self._http = HTTPSession(source["id"], rate=1.0, timeout=20,
                                 max_retries=2, audit=audit, proxy=proxy)

    def _fetch_ydl(self, opts: dict, url: str):
        import yt_dlp  # 延迟导入
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    def _save_video(self, info: dict, origin_query: str) -> RawRecord:
        vid = info.get("id", "")
        url = f"https://www.youtube.com/watch?v={vid}"
        # 字幕：手动优先，其次自动生成；阿语优先
        subs = (info.get("subtitles") or {}), (info.get("automatic_captions") or {})
        text = ""
        for capsets in subs:
            for lang in ("ar", "en", "zh-Hans"):
                if lang in capsets and capsets[lang]:
                    try:
                        sub_url = capsets[lang][-1]["url"]
                        sub_text = self._http.get(sub_url).text if getattr(self, "_http", None) else ""
                        # 简单 JSON3/VTT 清洗
                        import re
                        lines = re.sub(r"<[^>]+>", " ", sub_text)
                        text = "\n".join(l.strip() for l in lines.splitlines()
                                         if l.strip() and not l.startswith(("WEBVTT", "Kind:", "Language:")))
                        break
                    except Exception:  # noqa: BLE001
                        continue
                if text:
                    break
        rec = RawRecord(
            source_id=self.source["id"],
            layer=self.source["layer"],
            language=self.source["language"],
            country=self.source["country"],
            url=url,
            title=info.get("title", ""),
            text=text,
            published=info.get("upload_date"),
            author=info.get("channel"),
            engagement={"views": info.get("view_count"), "likes": info.get("like_count"),
                        "comments": info.get("comment_count")},
            content_type="subtitle" if text else "video_meta",
            extra={"origin_query": origin_query, "duration": info.get("duration"),
                   "has_subtitles": bool(text)},
        )
        self.store.save(self.source["id"], rec, raw_payload=json.dumps(info, ensure_ascii=False)[:300000])
        return rec

    def video_opts(self) -> dict:
        """yt-dlp 通用选项（字幕下载 + 代理 + 忽略单条错误）。"""
        opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                "writesubtitles": True, "writeautomaticsub": True,
                "subtitleslangs": ["ar", "en"], "ignoreerrors": True}
        if self.proxy:  # YouTube 被墙域 → 走代理
            opts["proxy"] = self.proxy
        return opts

    def collect(self, queries: List[tuple], max_per_query: int = 12) -> Iterator[RawRecord]:
        opts = self.video_opts()
        mode = self.cfg.get("mode", "keyword_search")
        handle = self.cfg.get("handle")
        max_videos = int(self.cfg.get("max_videos", 30))
        consec_err = 0          # 连续失败熔断（实测代理 SSL 抖动会无限刷错）
        ERR_BREAK = 6

        if mode == "channel" and handle:
            # 频道模式：先扁平列出视频清单（extract_flat，避免逐页全量抓取刷 9 小时），
            # 再对前 N 个视频逐个取字幕
            list_opts = dict(opts, extract_flat=True, playlistend=max_videos, lazy_playlist=True)
            url = f"https://www.youtube.com/{handle}/videos"
            try:
                info = self._fetch_ydl(list_opts, url)
                entries = [e for e in (info.get("entries") or []) if e]
                self.audit.log(self.source["id"], self.adapter_name, f"channel:{handle}",
                               url, status="ok", n_hits=len(entries))
            except Exception as e:  # noqa: BLE001
                self.audit.log(self.source["id"], self.adapter_name, f"channel:{handle}",
                               url, status="error", error=str(e))
                return
            for entry in entries[:max_videos]:
                vid = entry.get("id")
                if not vid:
                    continue
                watch = f"https://www.youtube.com/watch?v={vid}"
                try:
                    full = self._fetch_ydl({**opts, "extract_flat": False}, watch)
                    if not full:
                        continue
                    rec = self._save_video(full, entry.get("title") or "")
                    consec_err = 0
                    yield rec
                except Exception as e:  # noqa: BLE001
                    consec_err += 1
                    self.audit.log(self.source["id"], self.adapter_name, vid, watch,
                                   status="error", error=str(e))
                    if consec_err >= ERR_BREAK:
                        self.audit.log(self.source["id"], self.adapter_name, vid, watch,
                                       status="skipped", error=f"熔断：连续 {ERR_BREAK} 次失败")
                        break
            return

        # 关键词搜索模式
        for query, lang, country in queries:
            url = f"ytsearch{max_per_query}:{query}"
            try:
                info = self._fetch_ydl(opts, url)
                entries = [e for e in (info.get("entries") or []) if e]
                self.audit.log(self.source["id"], self.adapter_name, query, url,
                               status="ok", n_hits=len(entries))
                saved = 0
                for entry in entries[:max_per_query]:
                    if not entry or not entry.get("id"):
                        continue
                    try:
                        # 扁平结果无字幕信息 → 逐个取 watch 页详情
                        full = self._fetch_ydl({**opts, "extract_flat": False},
                                               f"https://www.youtube.com/watch?v={entry['id']}")
                        if not full:
                            continue
                        yield self._save_video(full, query)
                        saved += 1
                    except Exception as e:  # noqa: BLE001
                        self.audit.log(self.source["id"], self.adapter_name,
                                       entry.get("id", ""), "", status="error", error=str(e))
                consec_err = 0
            except Exception as e:  # noqa: BLE001
                consec_err += 1
                self.audit.log(self.source["id"], self.adapter_name, query, url,
                               status="error", error=str(e))
                if consec_err >= ERR_BREAK:
                    self.audit.log(self.source["id"], self.adapter_name, query, url,
                                   status="skipped",
                                   error=f"熔断：连续 {ERR_BREAK} 次查询失败（代理不稳），本轮终止")
                    break


class YouTubeAPIAdapter:
    """评论区抓取（Data API v3）。key 从环境变量 YOUTUBE_API_KEY 读取。"""
    adapter_name = "youtube_api"
    BASE = "https://www.googleapis.com/youtube/v3"

    def __init__(self, http: HTTPSession, store: RawStore, audit: AuditLog,
                 source_id: str = "youtube_api", layer: str = "L4"):
        self.http = http
        self.store = store
        self.audit = audit
        self.source_id = source_id
        self.layer = layer
        self.key = os.environ.get("YOUTUBE_API_KEY", "")

    def collect_comments(self, video_ids: List[str], max_per_video: int = 100) -> Iterator[RawRecord]:
        if not self.key:
            self.audit.log(self.source_id, self.adapter_name, "comments", "",
                           status="skipped", error="YOUTUBE_API_KEY 未配置")
            return
        for vid in video_ids:
            url = (f"{self.BASE}/commentThreads?part=snippet&videoId={vid}"
                   f"&maxResults=100&order=relevance&key={self.key}")
            try:
                resp = self.http.get(url)
                data = resp.json()
                items = data.get("items", [])
                self.audit.log(self.source_id, self.adapter_name, f"comments:{vid}", url,
                               status="ok", n_hits=len(items))
                for it in items:
                    sn = it["snippet"]["topLevelComment"]["snippet"]
                    rec = RawRecord(
                        source_id=self.source_id,
                        layer=self.layer,
                        language=sn.get("textOriginal", ""),
                        country="GCC",
                        url=f"https://www.youtube.com/watch?v={vid}",
                        title=sn.get("authorDisplayName", ""),
                        text=sn.get("textOriginal", ""),
                        published=sn.get("publishedAt"),
                        author=sn.get("authorChannelId", {}).get("value"),
                        engagement={"likes": sn.get("likeCount"), "replies": sn.get("totalReplyCount")},
                        content_type="comment",
                        parent_url=f"https://www.youtube.com/watch?v={vid}",
                    )
                    self.store.save(self.source_id, rec)
                    yield rec
            except Exception as e:  # noqa: BLE001
                self.audit.log(self.source_id, self.adapter_name, f"comments:{vid}", url,
                               status="error", error=str(e))
                continue
