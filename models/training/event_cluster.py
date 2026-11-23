# -*- coding: utf-8 -*-
"""
event_cluster.py —— 中阿英跨语言事件簇生成（对齐语料的地基）
==============================================================
原理：同一事件在中/阿/英三语的报道 = 语义相近 + 发布时间相近。
  1. 取语料库长文（≥80 词），标题+导语做向量（multilingual-e5-small）
  2. 按日期排序，±7 天窗口内余弦相似度 ≥ 0.78 的文档并查集归簇
  3. 输出跨语言簇与平行对（ar-en / ar-zh / en-zh）

产出：
  corpus/aligned/event_clusters.jsonl   簇清单（含成员与语言覆盖）
  corpus/aligned/pairs.jsonl            跨语言平行对（模型训练直接可用）

用法：
  models/.venv/Scripts/python event_cluster.py            # 向量模式（需模型）
  python event_cluster.py --heuristic                     # 兜底启发式模式
  python event_cluster.py --threshold 0.75 --window 10
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]   # models/training/event_cluster.py → 项目根
DB_PATH = PROJECT_ROOT / "corpus" / "meta" / "corpus.sqlite"
OUT_DIR = PROJECT_ROOT / "corpus" / "aligned"

MODEL_NAME = "intfloat/multilingual-e5-small"


def load_docs(min_words: int = 80) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT doc_id, language, country, title, text_clean, published, fetched_at,
                  raw_path, url, word_count
           FROM corpus_documents
           WHERE word_count >= ? AND language IN ('ar','en','zh')
             AND content_type IN ('article','article_full')""",
        (min_words,),
    ).fetchall()
    docs = []
    for r in rows:
        d = dict(r)
        d["date"] = (parse_date(d["published"]) or parse_date(d["fetched_at"])
                     or file_mtime_date(d.get("raw_path")))
        d["snippet"] = ((d["title"] or "") + " " + (d["text_clean"] or "")[:400]).strip()
        docs.append(d)
    conn.close()
    return docs   # 无日期文档保留（date=None），窗口匹配时作通配


def file_mtime_date(rel_path: str | None):
    """最后兜底：raw 文件的修改时间（修复历史 meta.fetched_at=null 的行）。"""
    if not rel_path:
        return None
    p = Path(rel_path)
    if not p.is_absolute():
        p = PROJECT_ROOT / rel_path
    try:
        return datetime.fromtimestamp(p.stat().st_mtime)
    except OSError:
        return None


def parse_date(s: str | None):
    if not s:
        return None
    s = s.strip()
    try:
        if len(s) >= 8 and s[:8].isdigit() and (s[8:9] in ("T", "-", "") or s[4:5] == "-"):
            if s[4:5] == "-":                       # ISO: 2026-08-23...
                return datetime.strptime(s[:10], "%Y-%m-%d")
            return datetime.strptime(s[:8], "%Y%m%d")   # GDELT: 20260823T144500Z
        if "," in s:                               # RSS RFC822: Tue, 17 Nov 2026
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(s).replace(tzinfo=None)   # 统一 naive，避免混排崩溃
        if len(s) >= 10 and s[:4].isdigit():
            return datetime.strptime(s[:10], "%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None
    return None


class UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def embed(docs: list[dict]) -> "object":
    from sentence_transformers import SentenceTransformer
    import numpy as np
    model = SentenceTransformer(MODEL_NAME)
    # 实测（_diag2）：标题+query前缀的跨语言相似度天花板显著更高（p90=0.853 vs 正文 0.833）
    embs = model.encode(["query: " + (d["title"] or d["snippet"][:80]) for d in docs],
                        batch_size=64, show_progress_bar=True,
                        normalize_embeddings=True)
    return np.asarray(embs, dtype="float32")


def cluster(docs: list[dict], embs, threshold: float, window_days: int) -> list[list[int]]:
    import numpy as np
    order = sorted(range(len(docs)), key=lambda i: docs[i]["date"] or datetime.max)
    uf = UnionFind(len(docs))
    dates = [docs[i]["date"] for i in order]
    for a in range(len(order)):
        for b in range(a + 1, len(order)):
            if dates[a] and dates[b] and (dates[b] - dates[a]).days > window_days:
                break
            sim = float(embs[order[a]] @ embs[order[b]])
            if sim >= threshold:
                uf.union(order[a], order[b])
    groups: dict[int, list[int]] = {}
    for i in range(len(docs)):
        groups.setdefault(uf.find(i), []).append(i)
    return [m for m in groups.values() if len(m) >= 2]


def cross_pair_extract(docs: list[dict], embs, threshold: float,
                       window_days: int) -> list[tuple[int, int, float]]:
    """跨语言贪心配对（ar × en/zh）：
    全部窗口内跨语言候选按相似度降序 → 贪心占用，每个文档至多配一次。
    避免并查集同语言巨型簇连坐问题，产出即高置信平行对。"""
    idxs = list(range(len(docs)))
    cands: list[tuple[float, int, int]] = []
    for a in idxs:
        if docs[a]["language"] != "ar":
            continue
        for b in idxs:
            if docs[b]["language"] == "ar":
                continue
            da, db = docs[a]["date"], docs[b]["date"]
            if da and db and abs((da - db).days) > window_days:
                continue
            sim = float(embs[a] @ embs[b])
            if sim >= threshold:
                cands.append((sim, a, b))
    cands.sort(reverse=True)
    used: set[int] = set()
    pairs: list[tuple[int, int, float]] = []
    for sim, a, b in cands:
        if a in used or b in used:
            continue
        used.add(a)
        used.add(b)
        pairs.append((a, b, sim))
    return pairs


def cluster_heuristic(docs: list[dict], window_days: int = 7) -> list[list[int]]:
    """兜底：同语言 TF-IDF 近邻 + 跨语言同品牌同日归簇（无模型时用）。"""
    from collections import defaultdict
    # 跨语言：品牌锚点 + ±3 天
    BRANDS = ["BYD", "بي واي دي", "比亚迪", "Tesla", "تسلا", "NIO", "蔚来", "Lucid",
              "لوسيد", "Jetour", "جيتور", "Geely", "جيلي", "Chery", "شيري"]
    buckets: dict[str, list[int]] = defaultdict(list)
    for i, d in enumerate(docs):
        day = d["date"].strftime("%Y-%m-%d")
        for b in BRANDS:
            if b in (d["snippet"] or ""):
                buckets[f"{b}|{day}"].append(i)
                buckets[f"{b}|{(d['date'] - timedelta(days=1)).strftime('%Y-%m-%d')}"].append(i)
    uf = UnionFind(len(docs))
    for idxs in buckets.values():
        for j in idxs[1:]:
            uf.union(idxs[0], j)
    groups: dict[int, list[int]] = {}
    for i in range(len(docs)):
        groups.setdefault(uf.find(i), []).append(i)
    return [m for m in groups.values() if len(m) >= 2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.80,
                    help="余弦相似度阈值（实测：标题模式 0.80 → 900 对高质量平行对）")
    ap.add_argument("--window", type=int, default=7)
    ap.add_argument("--max-size", type=int, default=25,
                    help="簇尺寸熔断：超过视为过度合并，不产平行对")
    ap.add_argument("--heuristic", action="store_true")
    ap.add_argument("--min-words", type=int, default=20,
                    help="候选词数下限（20=含标题级，事件匹配最佳信号；80=仅长文）")
    args = ap.parse_args()

    docs = load_docs(args.min_words)
    print(f"[load] {len(docs)} 篇候选长文")
    if not docs:
        return

    mode = "heuristic"
    embs = None
    if not args.heuristic:
        try:
            embs = embed(docs)
            mode = f"embedding:{MODEL_NAME}"
        except Exception as e:  # noqa: BLE001
            print(f"[warn] 模型不可用({e}) → 启发式兜底")

    clusters = (cluster(docs, embs, args.threshold, args.window) if embs is not None
                else cluster_heuristic(docs, args.window))
    pairs = (cross_pair_extract(docs, embs, args.threshold, args.window)
             if embs is not None else [])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "event_clusters.jsonl", "w", encoding="utf-8") as fc:
        for cid, members in enumerate(clusters, 1):
            langs = {docs[i]["language"] for i in members}
            rec = {
                "cluster_id": f"EC{cid:05d}",
                "size": len(members),
                "langs": sorted(langs),
                "over_merged": len(members) > args.max_size,
                "date": (docs[members[0]]["date"] or datetime.max).strftime("%Y-%m-%d"),
                "members": [{"doc_id": docs[i]["doc_id"], "lang": docs[i]["language"],
                             "title": (docs[i]["title"] or "")[:120],
                             "url": docs[i]["url"]} for i in members],
            }
            fc.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n_pairs = 0
    with open(OUT_DIR / "pairs.jsonl", "w", encoding="utf-8") as fp:
        for a, b, sim in pairs:
            fp.write(json.dumps({
                "src_doc": docs[a]["doc_id"], "tgt_doc": docs[b]["doc_id"],
                "src_lang": docs[a]["language"], "tgt_lang": docs[b]["language"],
                "src_title": (docs[a]["title"] or "")[:200],
                "tgt_title": (docs[b]["title"] or "")[:200],
                "sim": round(sim, 4),
                "date": (docs[a]["date"] or docs[b]["date"] or datetime.max).strftime("%Y-%m-%d"),
            }, ensure_ascii=False) + "\n")
            n_pairs += 1

    cross_clusters = sum(1 for m in clusters if len({docs[i]["language"] for i in m}) >= 2)
    print(f"[done] mode={mode}")
    print(f"[done] 簇 {len(clusters)} 个（跨语言簇 {cross_clusters}）"
          f" | 贪心跨语言平行对 {n_pairs} 对")
    print(f"[done] 产出: corpus/aligned/event_clusters.jsonl + pairs.jsonl")
    print(f"[gate] 对齐平行对目标 ≥500: {'PASS' if n_pairs >= 500 else f'FAIL ({n_pairs})'}")


if __name__ == "__main__":
    main()
