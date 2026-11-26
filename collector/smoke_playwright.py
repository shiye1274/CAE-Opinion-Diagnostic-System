# -*- coding: utf-8 -*-
"""
smoke_playwright.py
二期 NEEDS_BROWSER 源最小 smoke 验证（每个源最多 3 条）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters.base import AuditLog, HTTPSession, RawStore, load_sources, iter_enabled
from adapters.playwright_adapter import PlaywrightAdapter
from packs import build_query_set

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = PROJECT_ROOT / "collector" / "sources.yaml"

def main():
    sources = load_sources(SOURCES_PATH)
    enabled = iter_enabled(sources, only_layers=["L2", "L3"])
    targets = [s for s in enabled if s.get("adapter") == "playwright"]

    queries = build_query_set()
    site_all = list(queries.get("site_brands", []))
    # smoke 只跑前 3 个品牌查询，控制时间
    src_queries = site_all[:3]

    store = RawStore()
    audit = AuditLog("smoke_playwright")
    results = []

    for s in targets:
        sid = s["id"]
        print(f"\n[TEST] {sid}: {s.get('name')}")
        http = HTTPSession(sid, rate=s.get("rate", 1.0), audit=audit)
        ad = PlaywrightAdapter(s, http, store, audit)
        q_for_src = [(t, s["language"], s["country"]) for t, _, _ in src_queries]
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
        results.append({
            "id": sid,
            "name": s.get("name"),
            "status": status,
            "hits": hits,
            "error": error,
        })
        print(f"  -> {status}, hits={len(hits)}, error={error[:120]}")

    audit.close()
    out_path = PROJECT_ROOT / "collector" / "audit" / "smoke_playwright.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[report] {out_path}")

if __name__ == "__main__":
    main()
