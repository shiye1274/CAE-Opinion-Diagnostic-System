# -*- coding: utf-8 -*-
"""
Wayback Machine 存档回源：付费墙/失效页的历史快照兜底通道。
用法：wayback_fetch(url) → (archived_url, html) 或 None
"""
from __future__ import annotations

from typing import Optional, Tuple
from urllib.parse import quote

from .base import HTTPSession


def wayback_available(http: HTTPSession, url: str) -> Optional[str]:
    """查询最近一次快照 URL。"""
    api = f"https://archive.org/wayback/available?url={quote(url, safe='')}"
    try:
        data = http.get(api, timeout=20).json()
        snap = data.get("archived_snapshots", {}).get("closest", {})
        if snap.get("available"):
            return snap.get("url")
    except Exception:  # noqa: BLE001
        pass
    return None


def wayback_fetch(http: HTTPSession, url: str) -> Optional[Tuple[str, str]]:
    """返回 (snapshot_url, html)。"""
    snap = wayback_available(http, url)
    if not snap:
        return None
    try:
        resp = http.get(snap, timeout=40)
        if resp.ok and len(resp.text) > 300:
            return snap, resp.text
    except Exception:  # noqa: BLE001
        pass
    return None
