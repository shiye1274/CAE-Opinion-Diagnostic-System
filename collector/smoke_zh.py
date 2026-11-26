# -*- coding: utf-8 -*-
"""
smoke_zh.py
二期新增中文源最小 smoke 验证（每个源最多 3 条，首次用查询过滤，
未命中时回退到空查询直接取 feed 前 3 条，以验证 RSS URL 本身可达性）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters.base import AuditLog, HTTPSession, RawStore, load_sources
from adapters.rss_adapter import RSSAdapter
from adapters.html_adapter import HTMLAdapter
from packs import build_query_set

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = PROJECT_ROOT / "collector" / "sources.yaml"


def collect_from(adapter, queries, max_per_query=3):
    hits = []
    error = ""
    try:
        for i, rec in enumerate(adapter.collect(queries, max_per_query=max_per_query)):
            hits.append({
                "title": rec.title[:120],
                "url": rec.url,
                "len": len(rec.text),
            })
            if i >= max_per_query - 1:
                break
    except Exception as e:
        error = str(e)[:300]
    return hits, error


def test_source(s, store, audit, zh_queries):
    adapter_name = s.get("adapter")
    http = HTTPSession(s["id"], rate=s.get("rate", 1.0), audit=audit)
    if adapter_name == "rss":
        ad = RSSAdapter(http, store, audit, source=s)
    elif adapter_name == "html":
        ad = HTMLAdapter(s, http, store, audit)
    else:
        return None, f"unknown adapter {adapter_name}"

    q_for_src = [(t, s["language"], s["country"]) for t, _, _ in zh_queries]
    hits, error = collect_from(ad, q_for_src, max_per_query=3)

    # RSS 若过滤无命中，回退空查询验证 feed 可达
    fallback_hits = []
    if adapter_name == "rss" and not hits and not error:
        fallback_hits, _ = collect_from(ad, [], max_per_query=3)

    status = "ok" if hits else ("error" if error else ("feed_ok" if fallback_hits else "no_hits"))
    return {
        "id": s["id"],
        "name": s.get("name"),
        "adapter": adapter_name,
        "status": status,
        "hits": hits,
        "fallback_hits": fallback_hits,
        "error": error,
    }, None


def main():
    sources = load_sources(SOURCES_PATH)
    targets = [s for s in sources if s.get("language") == "zh"]

    queries = build_query_set()
    zh_queries = [q for q in queries.get("site_brands", []) if q[1] == "zh"][:5]

    store = RawStore()
    audit = AuditLog("smoke_zh")
    results = []

    for s in targets:
        print(f"\n[TEST] {s['id']}: {s.get('name')}")
        res, err = test_source(s, store, audit, zh_queries)
        if err:
            print(f"  -> SKIP: {err}")
            continue
        results.append(res)
        total = len(res["hits"]) + len(res["fallback_hits"])
        print(f"  -> {res['status']}, hits={len(res['hits'])}, fallback={len(res['fallback_hits'])}, error={res['error'][:120]}")

    audit.close()
    out_path = PROJECT_ROOT / "collector" / "audit" / "smoke_zh.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[report] {out_path}")


if __name__ == "__main__":
    main()
