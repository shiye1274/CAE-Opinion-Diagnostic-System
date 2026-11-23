# -*- coding: utf-8 -*-
"""
sample_calibration.py —— 校准集分层抽样（200 篇主文档 + 500 条 UGC）
====================================================================
分层配额：语言（ar ≥45%）× 国家 × 语种变体；固定随机种子保证可复现。

产出：
  corpus/processed/calibration_set.json   ← Label Studio 导入格式
  corpus/processed/calibration_set.csv    ← 进度跟踪表（双人盲标各一列）

用法：
  python sample_calibration.py                 # 200 篇 + UGC（不足则尽量）
  python sample_calibration.py --docs 100      # 快速小样
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "corpus" / "meta" / "corpus.sqlite"
OUT_DIR = PROJECT_ROOT / "corpus" / "processed"

AR_RATIO = 0.45          # 阿语配额（对齐门禁）
SEED = 20261119          # 固定种子 → 任何人重跑得到同一抽样


def stratified_docs(conn: sqlite3.Connection, n: int) -> list[dict]:
    rows = [dict(r) for r in conn.execute(
        """SELECT doc_id, source_id, source_layer, language, lang_variant, country,
                  title, text_clean, word_count, published, url
           FROM corpus_documents
           WHERE content_type='article' AND text_clean IS NOT NULL
           ORDER BY word_count DESC""")]
    random.seed(SEED)
    random.shuffle(rows)

    # 两段式：优先全文（≥80词），不足用短文补位（标注仍可做，标记 short_text）
    full = [r for r in rows if (r["word_count"] or 0) >= 80]
    short = [r for r in rows if 20 <= (r["word_count"] or 0) < 80]
    rows = full + short
    for r in rows:
        r["short_text"] = (r["word_count"] or 0) < 80

    ar_n = round(n * AR_RATIO)
    ar = [r for r in rows if r["language"] == "ar"]
    en = [r for r in rows if r["language"] == "en"]
    other = [r for r in rows if r["language"] not in ("ar", "en")]

    picked: list[dict] = []
    # 国家内再按比例（沙特/阿联酋/卡塔尔均沾）
    def take(pool: list[dict], k: int) -> list[dict]:
        by_country: dict[str, list[dict]] = {}
        for r in pool:
            by_country.setdefault(r["country"] or "XX", []).append(r)
        out: list[dict] = []
        while len(out) < k and any(by_country.values()):
            for c in sorted(by_country):
                if by_country[c] and len(out) < k:
                    out.append(by_country[c].pop(0))
        return out

    picked += take(ar, min(ar_n, len(ar)))
    picked += take(en, min(n - len(picked), len(en)))
    picked += other[:max(0, n - len(picked))]

    if len(picked) < n:
        for r in rows:
            if r not in picked and len(picked) < n:
                picked.append(r)
    return picked


def stratified_ugc(conn: sqlite3.Connection, n: int) -> list[dict]:
    rows = [dict(r) for r in conn.execute(
        """SELECT comment_id AS doc_id, parent_doc_id, language, dialect_tag,
                  comment_text AS text_clean, engagement, author_hash
           FROM ugc_threads WHERE comment_text IS NOT NULL""")]
    random.seed(SEED + 1)
    random.shuffle(rows)
    return rows[:n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=int, default=200)
    ap.add_argument("--ugc", type=int, default=500)
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    docs = stratified_docs(conn, args.docs)
    ugc = stratified_ugc(conn, args.ugc)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Label Studio 导入格式
    ls_items = []
    for i, r in enumerate(docs, 1):
        ls_items.append({"data": {
            "calib_id": f"C{i:03d}", "doc_id": r["doc_id"], "language": r["language"],
            "lang_variant": r["lang_variant"], "country": r["country"],
            "title": r["title"], "text_clean": (r["text_clean"] or "")[:8000],
            "word_count": r["word_count"], "short_text": r.get("short_text", False),
            "published": r["published"], "url": r["url"], "kind": "doc",
        }})
    for i, r in enumerate(ugc, 1):
        ls_items.append({"data": {
            "calib_id": f"U{i:03d}", "doc_id": r["doc_id"], "language": r["language"],
            "lang_variant": r.get("dialect_tag"), "country": "",
            "title": "(UGC评论)", "text_clean": (r["text_clean"] or "")[:2000],
            "parent": r.get("parent_doc_id"), "kind": "ugc",
        }})

    json_path = OUT_DIR / "calibration_set.json"
    json_path.write_text(json.dumps(ls_items, ensure_ascii=False, indent=1), encoding="utf-8")

    # 进度跟踪 CSV（双人盲标各一列 + 仲裁列）
    csv_path = OUT_DIR / "calibration_set.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["calib_id", "doc_id", "language", "lang_variant", "country",
                    "title", "annotator_1", "annotator_2", "agreement", "arbiter"])
        for it in ls_items:
            d = it["data"]
            w.writerow([d["calib_id"], d["doc_id"], d["language"], d["lang_variant"],
                        d["country"], d["title"][:60], "", "", "", ""])

    n_ar = sum(1 for r in docs if r["language"] == "ar")
    print(f"[抽样] 固定种子 {SEED}（可复现）")
    print(f"[抽样] 主文档 {len(docs)} 篇（阿语 {n_ar} = {n_ar/max(len(docs),1):.0%}）")
    print(f"[抽样] UGC {len(ugc)} 条")
    print(f"[产出] {json_path.name}（Label Studio 导入用）")
    print(f"[产出] {csv_path.name}（进度跟踪）")
    if n_ar / max(len(docs), 1) < AR_RATIO:
        print("[警告] 阿语不足 45% —— 语料库阿语总量不够，先跑阿语增量采集")
    conn.close()


if __name__ == "__main__":
    main()
