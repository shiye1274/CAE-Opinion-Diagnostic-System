# -*- coding: utf-8 -*-
"""
smoke_l1.py
二期新增/改造 L1 政策层源最小 smoke 验证（每个源最多 3 条）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters.base import AuditLog, HTTPSession, RawStore, load_sources, iter_enabled
from adapters.rss_adapter import RSSAdapter
from adapters.html_adapter import HTMLAdapter
from packs import build_query_set

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = PROJECT_ROOT / "collector" / "sources.yaml"


def test_source(s, store, audit, queries):
    adapter_name = s.get("adapter")
    http = HTTPSession(s["id"], rate=s.get("rate", 1.0), audit=audit)
    if adapter_name == "rss":
        ad = RSSAdapter(http, store, audit, source=s)
    elif adapter_name == "html":
        ad = HTMLAdapter(s, http, store, audit)
    else:
        return None, f"unknown adapter {adapter_name}"

    q_for_src = [(t, s["language"], s["country"]) for t, _, _ in queries]
    hits = []
    error = ""
    try:
        for i, rec in enumerate(ad.collect(q_for_src, max_per_query=3)):
            hits.append({
                "title": rec.title[:120],
                "url": rec.url,
                "len": len(rec.text),
            })
            if i >= 2:
                break
    except Exception as e:
        error = str(e)[:300]
    status = "ok" if hits else ("error" if error else "no_hits")
    return {"id": s["id"], "name": s.get("name"), "adapter": adapter_name,
            "status": status, "hits": hits, "error": error}, None


def main():
    sources = load_sources(SOURCES_PATH)
    targets = [s for s in sources if s.get("layer") == "L1"]

    queries = build_query_set()
    policy_queries = list(queries.get("policy_terms", []))[:10]

    store = RawStore()
    audit = AuditLog("smoke_l1")
    results = []

    for s in targets:
        print(f"\n[TEST] {s['id']}: {s.get('name')}")
        res, err = test_source(s, store, audit, policy_queries)
        if err:
            print(f"  -> SKIP: {err}")
            continue
        results.append(res)
        print(f"  -> {res['status']}, hits={len(res['hits'])}, error={res['error'][:120]}")

    audit.close()
    out_path = PROJECT_ROOT / "collector" / "audit" / "smoke_l1.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[report] {out_path}")


if __name__ == "__main__":
    main()
