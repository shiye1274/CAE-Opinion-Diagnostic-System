# -*- coding: utf-8 -*-
"""collector.adapters —— 各通道适配器统一入口。"""
from .base import (AuditLog, HTTPSession, RawRecord, RawStore,  # noqa: F401
                   load_sources, iter_enabled, load_yaml, text_sha256)
from .rss_adapter import RSSAdapter          # noqa: F401
from .gdelt_adapter import GDELTAdapter      # noqa: F401
from .site_search import SiteSearchAdapter   # noqa: F401
from .yt_dlp_adapter import YTDLPSearchAdapter, YouTubeAPIAdapter  # noqa: F401
from .reddit_api import RedditAdapter        # noqa: F401
from .wpjson_adapter import WPJsonAdapter    # noqa: F401
from .playwright_adapter import PlaywrightAdapter  # noqa: F401
from .html_adapter import HTMLAdapter          # noqa: F401
from .sitemap_adapter import SitemapAdapter    # noqa: F401
from .wayback import wayback_available, wayback_fetch  # noqa: F401
