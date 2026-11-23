# -*- coding: utf-8 -*-
"""
enrich.py —— 全文回源（标题级语料 → 有效全文）
================================================
对语料库中 word_count 过低（仅标题/摘要级）的文章记录：
  1. 抓取原文 URL（requests 自动跟随 Google News 重定向到原发布页）
  2. 正文抽取（复用 site_search.extract_text）
  3. 失败/死链 → Wayback Machine 存档回源
  4. 回写 corpus_documents（text_clean/word_count/sha256），原文快照另存 raw 层

用法：
  python enrich.py --limit 5      # 冒烟测试
  python enrich.py                # 全量回源（约 1.5s/条）
  python enrich.py --min-words 100 --limit 200
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters.base import (AuditLog, HTTPSession, RawRecord,  # noqa: E402
                           RawStore, text_sha256)
from adapters.site_search import extract_text   # noqa: E402
from adapters.wayback import wayback_fetch      # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "corpus" / "meta" / "corpus.sqlite"


def enrich_one(http: HTTPSession, http_proxy: HTTPSession, store: RawStore, doc: dict,
               min_words: int = 150) -> tuple[str, int, str]:
    """返回 (status, new_word_count, new_text)。status: full / short / dead / error
    http: 直连会话（中东媒体等）；http_proxy: 代理会话（Google News 重定向链接）"""
    url = doc["url"] or ""
    if not url.startswith("http"):
        return "dead", doc["word_count"], doc.get("text_clean") or ""
    # Google News 加密 token 链接：实测无法解析（AU_yqL 加密 + 代理不稳），直接跳过不浪费超时
    if "news.google.com" in url:
        return "gnews", doc["word_count"], doc.get("text_clean") or ""
    # 域名分流：Google 域走代理（实测直连超时），其他直连（走代理反而 SSL 错误）
    use_proxy = "news.google.com" in url or "google.com" in url
    http = http_proxy if use_proxy else http
    html = None
    try:
        resp = http.get(url, timeout=30)
        if resp.ok and len(resp.text) > 500:
            html = resp.text
    except Exception:  # noqa: BLE001
        pass
    if html is None:  # 降级 Wayback
        try:
            got = wayback_fetch(http, url)
            if got:
                _, html = got
        except Exception:  # noqa: BLE001
            pass
    if html is None:
        return "dead", doc["word_count"], doc.get("text_clean") or ""
    text = extract_text(html)
    # 清理样板：Google News 重定向页常见提示行
    for junk in ("Learn more", "Sign in", "Continue reading", "打开"):
        text = text.replace(junk, " ")
    wc = len(text.split())
    if wc < 60:
        return "short", doc["word_count"], doc.get("text_clean") or ""
    # 落盘原始快照（provenance）
    rec = RawRecord(
        source_id=doc["source_id"], layer=doc["source_layer"], language=doc["language"],
        country=doc["country"], url=url, title=doc["title"] or "", text=text,
        published=doc["published"], content_type="article_full",
        extra={"parent_doc_id": doc["doc_id"], "enriched_from": "title_level"},
    )
    store.save(doc["source_id"], rec, raw_payload=html[:400000])
    return ("full", wc, text) if wc >= min_words else ("short", wc, text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-words", type=int, default=100, help="低于该词数视为需回源")
    ap.add_argument("--limit", type=int, default=0, help="最多处理 N 条（0=全部）")
    ap.add_argument("--rate", type=float, default=1.5)
    args = ap.parse_args()

    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    docs = [dict(r) for r in conn.execute(
        """SELECT doc_id, source_id, source_layer, language, country, url, title,
                  published, word_count FROM corpus_documents
           WHERE content_type='article' AND word_count < ? AND url IS NOT NULL
           ORDER BY word_count ASC""", (args.min_words,))]
    if args.limit:
        docs = docs[:args.limit]
    print(f"[enrich] 待回源 {len(docs)} 条（阈值 {args.min_words} 词）")

    audit = AuditLog("enrich_" + uuid.uuid4().hex[:6])
    import os
    proxy = os.environ.get("COLLECTOR_PROXY", "http://127.0.0.1:7897")
    http = HTTPSession("enrich", rate=args.rate, timeout=30, max_retries=2, audit=audit)
    http_proxy = HTTPSession("enrich_proxy", rate=args.rate, timeout=30,
                             max_retries=2, audit=audit, proxy=proxy)
    print(f"[enrich] 代理: {proxy}（仅用于 Google 域名）")
    store = RawStore()
    stats = {"full": 0, "short": 0, "dead": 0, "error": 0, "gnews": 0}
    t0 = time.time()
    for i, doc in enumerate(docs):
        try:
            status, wc, text = enrich_one(http, http_proxy, store, doc, args.min_words)
        except Exception as e:  # noqa: BLE001
            status, wc, text = "error", doc["word_count"], doc.get("text_clean") or ""
            audit.log(doc["source_id"], "enrich", doc["doc_id"], doc["url"] or "",
                      status="error", error=str(e))
        stats[status] = stats.get(status, 0) + 1
        if status in ("full", "short"):
            conn.execute(
                "UPDATE corpus_documents SET text_clean=?, word_count=?, sha256=? "
                "WHERE doc_id=?",
                (text, wc, text_sha256(text), doc["doc_id"]))
            if stats["full"] % 10 == 0:
                conn.commit()   # 增量提交：进程被杀也不丢已回源的正文
        audit.log(doc["source_id"], "enrich", doc["doc_id"], doc["url"] or "",
                  status=status, n_hits=wc)
        if (i + 1) % 25 == 0:
            print(f"[enrich] {i+1}/{len(docs)} {stats} elapsed={time.time()-t0:.0f}s", flush=True)

    conn.commit()

    # 最终统计
    full = conn.execute(
        "SELECT COUNT(*) FROM corpus_documents WHERE word_count >= 200").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM corpus_documents").fetchone()[0]
    print(f"[enrich] 完成 {stats} | 有效全文(≥200词): {full}/{total}")
    audit.close()
    conn.close()


if __name__ == "__main__":
    main()
