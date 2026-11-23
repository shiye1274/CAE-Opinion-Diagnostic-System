# -*- coding: utf-8 -*-
"""
YouTube Data API v3 适配器（v0.2，接入真实 API Key）
=====================================================
用法：YOUTUBE_API_KEY 从 collector/.env 读取（key 已配好）
能力：
  1. resolve_channel(handle)      @handle → channelId（search.list，100 units/次）
  2. channel_videos(handle, n)    频道最新 n 条视频清单（channels+playlistItems，1 unit/次）
  3. collect_comments(video_ids)  评论区抓取（commentThreads，1 unit/次，每视频最多100条）
配额说明：免费 10,000 units/天；handle 解析 4 次 ≈ 400 units，清单/评论每次 1 unit，余量充足。
"""
from __future__ import annotations

import json
import os
from typing import List, Optional, Tuple
from urllib.parse import quote

from .base import AuditLog, HTTPSession, RawRecord, RawStore


class YouTubeAPIAdapter:
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

    # ---------- 频道解析 ----------
    def resolve_channel(self, handle: str) -> Optional[str]:
        """@handle → channelId（search.list type=channel）。"""
        if not self.key:
            return None
        q = handle.lstrip("@")
        url = (f"{self.BASE}/search?part=snippet&type=channel"
               f"&q={quote(q)}&maxResults=1&key={self.key}")
        try:
            data = self.http.get(url).json()
            items = data.get("items") or []
            if items:
                cid = items[0]["id"].get("channelId")
                self.audit.log(self.source_id, self.adapter_name, f"resolve:{handle}",
                               url, status="ok", n_hits=1, extra={"channelId": cid})
                return cid
        except Exception as e:  # noqa: BLE001
            self.audit.log(self.source_id, self.adapter_name, f"resolve:{handle}",
                           url, status="error", error=str(e))
        return None

    # ---------- 频道视频清单 ----------
    def channel_videos(self, handle: str, max_videos: int = 10,
                       source: Optional[dict] = None) -> List[Tuple[str, str]]:
        """返回 [(video_id, title), ...]，并把 video_meta 落盘 raw 层。"""
        cid = self.resolve_channel(handle)
        if not cid:
            return []
        # channels.list → uploads playlist id
        url = f"{self.BASE}/channels?part=contentDetails&id={cid}&key={self.key}"
        try:
            items = (self.http.get(url).json().get("items") or [])
            uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        except Exception as e:  # noqa: BLE001
            self.audit.log(self.source_id, self.adapter_name, f"channels:{handle}",
                           url, status="error", error=str(e))
            return []

        out: List[Tuple[str, str]] = []
        page_token = ""
        while len(out) < max_videos:
            url2 = (f"{self.BASE}/playlistItems?part=snippet,contentDetails"
                    f"&playlistId={uploads}&maxResults=50"
                    f"{f'&pageToken={page_token}' if page_token else ''}&key={self.key}")
            try:
                data = self.http.get(url2).json()
            except Exception as e:  # noqa: BLE001
                self.audit.log(self.source_id, self.adapter_name, f"playlist:{handle}",
                               url2, status="error", error=str(e))
                break
            for it in data.get("items") or []:
                vid = it.get("contentDetails", {}).get("videoId")
                title = it.get("snippet", {}).get("title", "")
                if vid and vid not in [v for v, _ in out]:
                    out.append((vid, title))
                    if len(out) >= max_videos:
                        break
            page_token = data.get("nextPageToken") or ""
            if not page_token:
                break
        self.audit.log(self.source_id, self.adapter_name, f"videos:{handle}", url2 if 'url2' in dir() else url,
                       status="ok", n_hits=len(out))
        # 落盘 video_meta（正文由 yt-dlp 字幕步骤补充）
        for vid, title in out:
            rec = RawRecord(
                source_id=self.source_id, layer=self.layer,
                language=(source or {}).get("language", "ar"),
                country=(source or {}).get("country", "GCC"),
                url=f"https://www.youtube.com/watch?v={vid}",
                title=title, text="", content_type="video_meta",
                extra={"channel": handle, "via": "youtube_api"},
            )
            self.store.save(self.source_id, rec, raw_payload=json.dumps(
                {"videoId": vid, "title": title}, ensure_ascii=False))
        return out

    # ---------- 评论区（UGC 主力） ----------
    def collect_comments(self, video_ids: List[str], max_per_video: int = 60) -> List[RawRecord]:
        if not self.key:
            self.audit.log(self.source_id, self.adapter_name, "comments", "",
                           status="skipped", error="YOUTUBE_API_KEY 未配置")
            return []
        saved: List[RawRecord] = []
        for vid in video_ids:
            url = (f"{self.BASE}/commentThreads?part=snippet&videoId={vid}"
                   f"&maxResults=100&order=relevance&key={self.key}")
            try:
                data = self.http.get(url).json()
                items = data.get("items") or []
            except Exception as e:  # noqa: BLE001
                self.audit.log(self.source_id, self.adapter_name, f"comments:{vid}",
                               url, status="error", error=str(e))
                continue
            for it in items[:max_per_video]:
                sn = it["snippet"]["topLevelComment"]["snippet"]
                rec = RawRecord(
                    source_id=self.source_id, layer=self.layer,
                    language="", country="GCC",   # 语言由 pipeline 从正文识别（勿传正文）
                    url=f"https://www.youtube.com/watch?v={vid}",
                    title=sn.get("authorDisplayName", ""),
                    text=sn.get("textOriginal", ""),
                    published=sn.get("publishedAt"),
                    author=sn.get("authorChannelId", {}).get("value"),
                    engagement={"likes": sn.get("likeCount"),
                                "replies": sn.get("totalReplyCount")},
                    content_type="comment",
                    parent_url=f"https://www.youtube.com/watch?v={vid}",
                    extra={"via": "youtube_api"},
                )
                self.store.save(self.source_id, rec)
                saved.append(rec)
            self.audit.log(self.source_id, self.adapter_name, f"comments:{vid}",
                           url, status="ok", n_hits=len(items),
                           saved=min(len(items), max_per_video))
        return saved
