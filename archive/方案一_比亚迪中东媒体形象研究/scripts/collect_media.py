#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
媒体采集脚本
用于收集中东媒体报道比亚迪（BYD）与特斯拉（Tesla）的语料。

用法：
  python collect_media.py --pilot            # 14天试采（每个查询限量）
  python collect_media.py --full             # 全量采集
  python collect_media.py --pilot --max 30   # 试采，每查询最多30条

输出：
  data/pilot_results.csv   试采结果
  data/corpus_raw.csv      原始语料
  logs/collect.log         运行日志
"""

import os
import sys
import time
import json
import csv
import logging
import argparse
import urllib.parse
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
import feedparser

# --------------------------- 日志 ---------------------------
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "collect.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# --------------------------- 路径 ---------------------------
BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# --------------------------- 媒体配置 ---------------------------
# tier: T1_AR_LOCAL / T2_AR_PANARAB / T3_EN_GCC / T4_EN_INTL
MEDIA_LIST = [
    # ---- 阿语本地媒体 ----
    {"name": "Al Arabiya",       "tier": "T1_AR_LOCAL", "country": "Saudi", "language": "Arabic",
     "brand": "BYD", "search_query": 'بي واي دي السعودية',
     "site": "alarabiya.net"},
    {"name": "Al Bayan",         "tier": "T1_AR_LOCAL", "country": "UAE",   "language": "Arabic",
     "brand": "BYD", "search_query": 'بي واي دي الإمارات',
     "site": "albayan.ae"},
    {"name": "Al Khaleej",       "tier": "T1_AR_LOCAL", "country": "UAE",   "language": "Arabic",
     "brand": "BYD", "search_query": 'بي واي دي',
     "site": "alkhaleej.ae"},
    {"name": "Okaz",             "tier": "T1_AR_LOCAL", "country": "Saudi", "language": "Arabic",
     "brand": "BYD", "search_query": 'بي واي دي',
     "site": "okaz.com.sa"},
    {"name": "Al Eqtisadiah",    "tier": "T1_AR_LOCAL", "country": "Saudi", "language": "Arabic",
     "brand": "BYD", "search_query": 'بي واي دي',
     "site": "aleqt.com"},
    {"name": "Asharq News",      "tier": "T1_AR_LOCAL", "country": "Saudi", "language": "Arabic",
     "brand": "BYD", "search_query": 'بي واي دي',
     "site": "asharq.com"},
    {"name": "Al Jazeera Arabic","tier": "T2_AR_PANARAB","country": "Qatar", "language": "Arabic",
     "brand": "BYD", "search_query": 'بي واي دي',
     "site": "aljazeera.net"},
    # ---- 英语 GCC 媒体 ----
    {"name": "Gulf News",        "tier": "T3_EN_GCC", "country": "UAE",   "language": "English",
     "brand": "BYD", "search_query": 'BYD Saudi Arabia electric vehicle',
     "site": "gulfnews.com"},
    {"name": "Khaleej Times",    "tier": "T3_EN_GCC", "country": "UAE",   "language": "English",
     "brand": "BYD", "search_query": 'BYD UAE electric vehicle',
     "site": "khaleejtimes.com"},
    {"name": "The National",     "tier": "T3_EN_GCC", "country": "UAE",   "language": "English",
     "brand": "BYD", "search_query": 'BYD electric vehicle',
     "site": "thenationalnews.com"},
    {"name": "Arabian Business", "tier": "T3_EN_GCC", "country": "UAE",   "language": "English",
     "brand": "BYD", "search_query": 'BYD electric vehicle',
     "site": "arabianbusiness.com"},
    {"name": "Arab News",        "tier": "T3_EN_GCC", "country": "Saudi", "language": "English",
     "brand": "BYD", "search_query": 'BYD Saudi Arabia electric vehicle',
     "site": "arabnews.com"},
    # ---- 英语国际媒体中东版 ----
    {"name": "Reuters Middle East","tier": "T4_EN_INTL","country": "International","language": "English",
     "brand": "BYD", "search_query": 'BYD Middle East electric vehicle',
     "site": "reuters.com"},
    {"name": "Bloomberg Middle East","tier": "T4_EN_INTL","country": "International","language": "English",
     "brand": "BYD", "search_query": "BYD Gulf electric vehicle",
     "site": "bloomberg.com"},
]

# Tesla 对照查询（与 BYD 使用相同媒体清单）
TESLA_QUERIES = {
    "Arabic": 'تسلا',
    "English": 'Tesla Gulf electric vehicle',
}


# --------------------------- 工具函数 ---------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}


def rate_limit(seconds=1.0):
    """简单限速，避免被封。"""
    time.sleep(seconds)


def google_news_rss(query, brand, max_results=50, days=2200):
    """
    通过 Google News RSS 获取新闻链接。
    query: 检索式
    brand: BYD / TESLA
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    encoded = urllib.parse.quote_plus(query)
    rss_url = (
        f"https://news.google.com/rss/search?q={encoded}"
        f"&hl=en-US&gl=US&ceid=US:en"
    )
    results = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:max_results]:
            link = entry.get("link", "")
            title = entry.get("title", "")
            pubdate = entry.get("published", "")
            results.append({
                "brand": brand,
                "query": query,
                "title": title,
                "url": link,
                "published": pubdate,
                "source": "GoogleNewsRSS",
            })
        logger.info(f"Google News RSS: {query} -> {len(results)} 条")
    except Exception as e:
        logger.error(f"Google News RSS 失败: {query} | {e}")
    return results


def fetch_full_text(url, timeout=20):
    """
    抓取网页全文。
    返回 dict: {url, title, text, fetch_ok, error}
    """
    result = {"url": url, "title": "", "text": "", "fetch_ok": False, "error": ""}
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # 标题
        if soup.title and soup.title.string:
            result["title"] = soup.title.string.strip()

        # 移除脚本/样式/导航/广告
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
            tag.decompose()

        # 常见正文容器
        article = None
        for sel in ["article", ".article-body", ".content", ".story-content",
                    "#story", ".post-content", "[itemprop='articleBody']"]:
            article = soup.select_one(sel)
            if article:
                break
        if article is None:
            article = soup.body or soup

        # 提取段落
        paragraphs = []
        for p in article.find_all("p"):
            text = p.get_text(" ", strip=True)
            if text and len(text) > 20:
                paragraphs.append(text)

        result["text"] = "\n".join(paragraphs)
        result["fetch_ok"] = bool(result["text"])
        if not result["text"]:
            result["error"] = "empty_text"
    except Exception as e:
        result["error"] = str(e)
    return result


def save_csv(rows, path, fieldnames=None):
    """保存 CSV。"""
    if not rows:
        logger.warning(f"无数据可保存: {path}")
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info(f"已保存 {len(rows)} 条到 {path}")


# --------------------------- 试采 ---------------------------
def run_pilot(max_per_query=30):
    """14天试采：每个媒体/品牌组合限量采集，记录证据。"""
    logger.info("=" * 60)
    logger.info("开始试采")
    logger.info("=" * 60)

    all_results = []
    evidence = []

    for media in MEDIA_LIST:
        name = media["name"]
        brand = media["brand"]
        query = media["search_query"]

        # Google News RSS 采集
        results = google_news_rss(query, brand, max_results=max_per_query, days=2200)
        time.sleep(1.0)  # 限速

        if not results:
            logger.warning(f"{name} / {brand}: 0 条结果")
            continue

        # 尝试抓取全文（限量）
        fulltext_count = 0
        included = 0
        dup_count = 0
        seen_urls = set()
        sample = results[:10]  # 试采时只抓前10条全文

        for r in sample:
            url = r["url"]
            if url in seen_urls:
                dup_count += 1
                continue
            seen_urls.add(url)

            fr = fetch_full_text(url)
            rate_limit(1.5)

            if fr["fetch_ok"]:
                fulltext_count += 1
                if len(fr["text"]) > 200:  # 有效全文阈值
                    included += 1
                    all_results.append({
                        "brand": brand,
                        "media": name,
                        "source_tier": media["tier"],
                        "country": media["country"],
                        "language": media["language"],
                        "title": fr["title"],
                        "url": url,
                        "text": fr["text"],
                        "word_count": len(fr["text"].split()),
                        "fetch_date": datetime.utcnow().strftime("%Y-%m-%d"),
                    })
            else:
                logger.debug(f"抓取失败: {url} | {fr['error']}")

        evidence.append({
            "media": name,
            "brand": brand,
            "query": query,
            "hits": len(results),
            "fulltext_available": fulltext_count,
            "duplicates": dup_count,
            "included": included,
            "total": len(all_results),
        })

    # 保存
    save_csv(all_results, os.path.join(DATA_DIR, "pilot_results.csv"))
    save_csv(evidence, os.path.join(DATA_DIR, "pilot_evidence.csv"))

    # 汇总报告
    total_hits = sum(e["hits"] for e in evidence)
    total_full = sum(e["fulltext_available"] for e in evidence)
    total_included = sum(e["included"] for e in evidence)
    logger.info("=" * 60)
    logger.info(f"试采完成：命中 {total_hits} 条，全文可得 {total_full} 篇，有效纳入 {total_included} 篇")
    logger.info("=" * 60)

    # 生成试采报告
    report_lines = [
        "# 14天媒体试采报告",
        "",
        f"- 采集日期：{datetime.utcnow().strftime('%Y-%m-%d')}",
        f"- 命中总数：{total_hits}",
        f"- 全文可得：{total_full}",
        f"- 有效纳入：{total_included}",
        "",
        "## 分媒体统计",
        "",
        "| 媒体 | 品牌 | 命中 | 全文 | 纳入 |",
        "|------|------|------|------|------|",
    ]
    for e in evidence:
        report_lines.append(
            f"| {e['media']} | {e['brand']} | {e['hits']} | "
            f"{e['fulltext_available']} | {e['included']} |"
        )
    report_lines += [
        "",
        "## 验收标准",
        "",
        f"- [ ] 有效全文 ≥ 100 篇（当前：{total_included}）",
        f"- [ ] 覆盖 ≥ 5 家媒体（当前：{len([e for e in evidence if e['included']>0])}）",
        f"- [ ] 阿语占比 ≥ 40%（需人工核对）",
        f"- [ ] 全文可得率 ≥ 60%（当前：{total_full}/{total_hits}）",
    ]
    report_path = os.path.join(DATA_DIR, "试采报告.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    logger.info(f"试采报告已保存: {report_path}")


# --------------------------- 全量采集 ---------------------------
def run_full(max_per_query=200):
    """全量采集。"""
    logger.info("=" * 60)
    logger.info("开始全量采集")
    logger.info("=" * 60)

    all_results = []

    for media in MEDIA_LIST:
        name = media["name"]
        brand = media["brand"]
        query = media["search_query"]

        results = google_news_rss(query, brand, max_results=max_per_query, days=2200)
        time.sleep(1.0)

        for r in results:
            url = r["url"]
            fr = fetch_full_text(url)
            rate_limit(1.5)

            if fr["fetch_ok"] and len(fr["text"]) > 200:
                all_results.append({
                    "brand": brand,
                    "media": name,
                    "source_tier": media["tier"],
                    "country": media["country"],
                    "language": media["language"],
                    "title": fr["title"],
                    "url": url,
                    "text": fr["text"],
                    "word_count": len(fr["text"].split()),
                    "fetch_date": datetime.utcnow().strftime("%Y-%m-%d"),
                })

    # Tesla 对照（使用相同媒体）
    for media in MEDIA_LIST:
        if media["language"] == "Arabic":
            query = TESLA_QUERIES["Arabic"]
        else:
            query = TESLA_QUERIES["English"]

        results = google_news_rss(query, "TESLA", max_results=max_per_query, days=2200)
        time.sleep(1.0)

        for r in results:
            url = r["url"]
            fr = fetch_full_text(url)
            rate_limit(1.5)

            if fr["fetch_ok"] and len(fr["text"]) > 200:
                all_results.append({
                    "brand": "TESLA",
                    "media": media["name"],
                    "source_tier": media["tier"],
                    "country": media["country"],
                    "language": media["language"],
                    "title": fr["title"],
                    "url": url,
                    "text": fr["text"],
                    "word_count": len(fr["text"].split()),
                    "fetch_date": datetime.utcnow().strftime("%Y-%m-%d"),
                })

    save_csv(all_results, os.path.join(DATA_DIR, "corpus_raw.csv"))
    logger.info(f"全量采集完成：{len(all_results)} 条")


# --------------------------- 主程序 ---------------------------
def main():
    parser = argparse.ArgumentParser(description="中东媒体报道采集脚本")
    parser.add_argument("--pilot", action="store_true", help="14天试采模式")
    parser.add_argument("--full", action="store_true", help="全量采集模式")
    parser.add_argument("--max", type=int, default=30, help="每个查询最大结果数")
    args = parser.parse_args()

    if args.pilot:
        run_pilot(max_per_query=args.max)
    elif args.full:
        run_full(max_per_query=args.max)
    else:
        print("请指定 --pilot 或 --full")
        print("示例：python collect_media.py --pilot --max 30")


if __name__ == "__main__":
    main()
