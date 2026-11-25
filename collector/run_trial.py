# -*- coding: utf-8 -*-
"""
run_trial.py —— 14 天试采编排器
================================
用法：
  python run_trial.py                          # 全部启用源，小样试跑
  python run_trial.py --days 3 --max-per-query 15
  python run_trial.py --layers L2 L3           # 只跑某几层
  python run_trial.py --sources arabnews gulfnews alarabiya_ar
  python run_trial.py --dry-run                # 只打印查询式不采集

产出：
  corpus/raw/…（原始快照）
  collector/audit/run_{run_id}.jsonl（查询级审计）
  collector/audit/试采证据日志_{run_id}.csv
  collector/audit/gate_report_{run_id}.json（质量门禁报告）
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters.base import (AUDIT_DIR, AuditLog, HTTPSession, RawRecord,  # noqa: E402
                           RawStore, iter_enabled, load_sources)
from adapters.gdelt_adapter import GDELTAdapter            # noqa: E402
from adapters.rss_adapter import RSSAdapter                # noqa: E402
from adapters.site_search import SiteSearchAdapter         # noqa: E402
from adapters.wpjson_adapter import WPJsonAdapter          # noqa: E402
from adapters.playwright_adapter import PlaywrightAdapter  # noqa: E402
from adapters.html_adapter import HTMLAdapter              # noqa: E402
from adapters.reddit_api import RedditAdapter              # noqa: E402
from adapters.yt_dlp_adapter import YTDLPSearchAdapter     # noqa: E402
from packs import build_query_set, load_packs              # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="14 天试采编排器")
    p.add_argument("--days", type=int, default=3, help="本次计划跑的天数（日志标注用）")
    p.add_argument("--max-per-query", type=int, default=10, help="每查询最多保存条数")
    p.add_argument("--timespan", default="1y", help="GDELT 时间窗（实测支持 1y/1w 等）")
    p.add_argument("--sources", nargs="*", help="只跑这些 source_id")
    p.add_argument("--layers", nargs="*", help="只跑这些层（L1..L5）")
    p.add_argument("--brands", nargs="*", help="只跑这些品牌 id（默认全部核心品牌）")
    p.add_argument("--skip-pipeline", action="store_true", help="跳过清洗入库")
    p.add_argument("--no-gdelt", action="store_true", help="跳过 GDELT（限速严格，建议夜间批跑）")
    p.add_argument("--no-gnews", action="store_true", help="跳过 Google News RSS")
    p.add_argument("--langs", nargs="*", default=None,
                   help="只跑指定语言的查询（如 --langs ar），用于定向补语种占比")
    p.add_argument("--dry-run", action="store_true", help="只打印查询式")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
    audit = AuditLog(run_id)
    print(f"[run_id] {run_id}")

    sources = load_sources(PROJECT_ROOT / "collector" / "sources.yaml")
    enabled = iter_enabled(sources, only_ids=args.sources, only_layers=args.layers)
    print(f"[sources] enabled = {len(enabled)}")

    queries = build_query_set(brands=args.brands)
    # wp-json 站内搜索锚点不参与语种过滤（其内容语言由正文识别，--langs ar 曾把它误滤空）
    site_all = list(queries.get("site_brands", []))
    policy_all = list(queries.get("policy_terms", []))
    if args.langs:   # 语种定向：只保留指定语言的查询
        keep = set(args.langs)
        for k in list(queries):
            queries[k] = [q for q in queries[k] if q[1] in keep]
        site_all = [q for q in site_all if q[1] in keep]
        policy_all = [q for q in policy_all if q[1] in keep]
    total_q = sum(len(v) for v in queries.values())
    print(f"[queries] {total_q} 个 (品牌 × 国家 × 语言) 组合")
    if args.dry_run:
        for q in queries.get("gdelt", [])[:15]:
            print("  GDELT:", q[0])
        audit.close()
        return

    store = RawStore()
    import os
    # 加载 collector/.env（YOUTUBE_API_KEY / COLLECTOR_PROXY 等本地密钥）
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    PROXY = os.environ.get("COLLECTOR_PROXY", "http://127.0.0.1:7897")  # 被墙域统一走本地代理
    n_saved = 0
    t0 = time.time()

    # ---- 通道 1：GDELT（主力查全；实测限流惩罚累积，需 ≥30s/请求 + 429 长退避）----
    if not args.no_gdelt:
        gdelt_http = HTTPSession("gdelt", rate=30.0, timeout=60, audit=audit)
        gd = GDELTAdapter(gdelt_http, store, audit, source_id="gdelt")
        for rec in gd.collect(queries.get("gdelt", []),
                              max_per_query=max(args.max_per_query, 20),
                              timespan=args.timespan):
            n_saved += 1

    # ---- 通道 2：Google News RSS（增量 + 兜底；Google 域 → 走代理）----
    if not args.no_gnews:
        gn = RSSAdapter(HTTPSession("googlenews", rate=1.5, audit=audit, proxy=PROXY),
                        store, audit)
        for rec in gn.collect(queries.get("google_news", []), max_per_query=args.max_per_query):
            n_saved += 1

    # ---- 通道 3：站内搜索（逐源）----
    for s in enabled:
        if s.get("adapter") != "site_search":
            continue
        http = HTTPSession(s["id"], rate=s.get("rate", 2.0), audit=audit)
        ad = SiteSearchAdapter(s, http, store, audit)
        # search_url 已核验的源才跑；查询用品牌英文锚点词（三元组：term, en_name, GCC）
        src_queries = [(t, s["language"], s["country"])
                       for t, _, _ in queries.get("site_brands", [])]
        for rec in ad.collect(src_queries, max_per_query=args.max_per_query):
            n_saved += 1

    # ---- 通道 3b：wp-json（B 实测验证的 WordPress 正确通道）----
    for s in enabled:
        if s.get("adapter") != "wpjson":
            continue
        http = HTTPSession(s["id"], rate=s.get("rate", 2.0), audit=audit)
        ad = WPJsonAdapter(s, http, store, audit)
        src_queries = [(t, s["language"], s["country"])
                       for t, _, _ in site_all]   # 不受 --langs 过滤（语言由正文识别）
        for rec in ad.collect(src_queries, max_per_query=args.max_per_query):
            n_saved += 1

    # ---- 通道 3c：Playwright 浏览器渲染（NEEDS_BROWSER 源）----
    for s in enabled:
        if s.get("adapter") != "playwright":
            continue
        http = HTTPSession(s["id"], rate=s.get("rate", 2.0), audit=audit)
        ad = PlaywrightAdapter(s, http, store, audit)
        src_queries = [(t, s["language"], s["country"])
                       for t, _, _ in site_all]
        for rec in ad.collect(src_queries, max_per_query=args.max_per_query):
            n_saved += 1

    # ---- 通道 3d：源直采 RSS/Atom（中文源 / L1 新闻室等）----
    for s in enabled:
        if s.get("adapter") != "rss":
            continue
        http = HTTPSession(s["id"], rate=s.get("rate", 2.0), audit=audit)
        ad = RSSAdapter(http, store, audit, source=s)
        src_queries = [(t, s["language"], s["country"])
                       for t, _, _ in (site_all + policy_all)]
        for rec in ad.collect(src_queries, max_per_query=args.max_per_query):
            n_saved += 1

    # ---- 通道 3e：轻量 HTML 列表解析（L1 政策门户兜底）----
    for s in enabled:
        if s.get("adapter") != "html":
            continue
        http = HTTPSession(s["id"], rate=s.get("rate", 2.0), audit=audit)
        ad = HTMLAdapter(s, http, store, audit)
        src_queries = [(t, s["language"], s["country"])
                       for t, _, _ in policy_all]
        for rec in ad.collect(src_queries, max_per_query=args.max_per_query):
            n_saved += 1

    # ---- 通道 4：Reddit UGC（被墙域 → 走代理）----
    for s in enabled:
        if s.get("adapter") != "reddit":
            continue
        ad = RedditAdapter(s, HTTPSession(s["id"], rate=s.get("rate", 2.0),
                                          audit=audit, proxy=PROXY),
                           store, audit)
        for rec in ad.collect(queries.get("reddit", []), max_per_query=args.max_per_query):
            n_saved += 1

    # ---- 通道 5：YouTube（API 清单/评论优先 + yt-dlp 补字幕，代理统一走 PROXY）----
    from adapters.youtube_api import YouTubeAPIAdapter
    yt_key = os.environ.get("YOUTUBE_API_KEY", "")
    for s in enabled:
        if s.get("adapter") != "yt_dlp":
            continue
        cfg = s.get("config") or {}
        ad = YTDLPSearchAdapter(s, store, audit, proxy=PROXY)
        api = (YouTubeAPIAdapter(HTTPSession(s["id"], rate=1.0, audit=audit, proxy=PROXY),
                                 store, audit, source_id=s["id"], layer=s["layer"])
               if yt_key else None)
        video_ids: list[tuple[str, str]] = []
        if api and cfg.get("mode") == "channel" and cfg.get("handle"):
            # API 取频道清单（可靠）→ yt-dlp 逐视频补字幕 → API 抓评论区（UGC）
            video_ids = api.channel_videos(cfg["handle"],
                                           int(cfg.get("max_videos", 10)), source=s)
        if video_ids:
            for vid, title in video_ids:
                try:
                    full = ad._fetch_ydl({**ad.video_opts(), "extract_flat": False},
                                         f"https://www.youtube.com/watch?v={vid}")
                    if full:
                        ad._save_video(full, title)
                        n_saved += 1
                except Exception:  # noqa: BLE001
                    continue
            api.collect_comments([v for v, _ in video_ids[:10]], max_per_video=60)
        else:
            # API 不可用 / 非频道源 → 原 yt-dlp 通道（含熔断）
            for rec in ad.collect(queries.get("youtube", []),
                                  max_per_query=args.max_per_query):
                n_saved += 1

    elapsed = time.time() - t0
    print(f"[collect] 保存原始记录 {n_saved} 条，耗时 {elapsed:.0f}s")

    # ---- 清洗入库 ----
    stats = {}
    if not args.skip_pipeline:
        from pipeline import run_pipeline  # noqa: E402
        stats = run_pipeline()
        print(f"[pipeline] in={stats['raw_in']} kept={stats['kept']}")
        print(json.dumps(stats["stats"], ensure_ascii=False, indent=2))

    # ---- 试采证据日志 CSV ----
    AUDIT_DIR.mkdir(exist_ok=True)
    csv_path = AUDIT_DIR / f"试采证据日志_{run_id}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ts", "source_id", "adapter", "query", "url", "status", "n_hits", "error"])
        with open(audit.path, encoding="utf-8") as jf:
            for line in jf:
                r = json.loads(line)
                w.writerow([r["ts"], r["source_id"], r["adapter"], r["query"],
                            r["url"], r["status"], r["n_hits"], r["error"]])
    print(f"[audit] 试采证据日志 → {csv_path.name}")

    # ---- 门禁报告（直接查库的真实指标，不用入库条数冒充全文）----
    import sqlite3 as _sq
    _db = _sq.connect(str(PROJECT_ROOT / "corpus" / "meta" / "corpus.sqlite"))
    _n, _ar = _db.execute(
        "SELECT COUNT(*), SUM(CASE WHEN language='ar' THEN 1 ELSE 0 END) "
        "FROM corpus_documents").fetchone()
    _full = _db.execute(
        "SELECT COUNT(*) FROM corpus_documents WHERE word_count >= 200").fetchone()[0]
    _srcs = _db.execute(
        "SELECT COUNT(DISTINCT source_id) FROM corpus_documents").fetchone()[0]
    _ugc = _db.execute("SELECT COUNT(*) FROM ugc_threads").fetchone()[0]
    _db.close()
    gate = {
        "run_id": run_id,
        "raw_saved_this_run": n_saved,
        "corpus_total": _n,
        "corpus_arabic": _ar,
        "corpus_fulltext_ge200": _full,
        "corpus_sources": _srcs,
        "corpus_ugc": _ugc,
        "gates": {
            "有效全文>=500": _full >= 500,
            "覆盖源>=15": _srcs >= 15,
            "阿语占比>=45%": (_ar / max(_n, 1)) >= 0.45,
        },
        "elapsed_sec": round(elapsed, 1),
    }
    gate_path = AUDIT_DIR / f"gate_report_{run_id}.json"
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[gate] {json.dumps(gate['gates'], ensure_ascii=False)}")
    print(f"[gate] 报告 → {gate_path.name}")
    audit.close()


def _ar_ratio(stats: dict) -> float:
    total = sum(sum(v.values()) for v in stats.values()) or 1
    ar = sum(stats.get("ar", {}).values())
    return ar / total


if __name__ == "__main__":
    main()
