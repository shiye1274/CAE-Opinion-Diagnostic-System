# -*- coding: utf-8 -*-
"""
fill_entities.py —— 品牌-文档实体映射灌数（doc_entities 表，规划表 3-4）
========================================================================
按 collector/packs 品牌词包对每篇文档做多语言锚点匹配，启发式判定角色：
  - 中国品牌且出现在标题、总提及最多 → CORE_SUBJECT 主角
  - 对照品牌（Tesla/Lucid 等）出现在标题 → BENCHMARK 对照标杆
  - 其余出现（仅正文或次要标题提及）→ PASSING_MENTION 顺带提及

幂等：每次全量重算（表清空重建）。供品牌看板/共现网络/报告引用。

用法：python collector/fill_entities.py
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from packs import load_packs  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB = PROJECT_ROOT / "corpus" / "meta" / "corpus.sqlite"


def brand_terms() -> dict[str, dict]:
    """brand_id → {group, terms: [已去引号的锚点词]}"""
    packs = load_packs()
    out: dict[str, dict] = {}
    for b in packs["brands_cn"] + packs["brands_comp"]:
        terms = []
        for lang_terms in b.get("queries", {}).values():
            for t in lang_terms:
                t = t.strip().strip('"').strip()
                if t:
                    terms.append(t)
        group = "cn" if b in packs["brands_cn"] else "comp"
        out[b["id"]] = {"group": group, "terms": terms}
    return out


def count_mentions(text: str, terms: list[str]) -> int:
    low = text.lower()
    n = 0
    for t in terms:
        if re.search(r"[A-Za-z]", t):
            if " " in t or "/" in t:
                n += low.count(t.lower())
            else:
                # 纯英文单词用词边界，避免 junior/senior 命中 NIO 之类子串假阳性
                n += len(re.findall(rf"\b{re.escape(t)}\b", low))
        else:
            n += text.count(t)
    return n


def main() -> None:
    brands = brand_terms()
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    docs = db.execute(
        """SELECT doc_id, title, text_clean FROM corpus_documents
           WHERE content_type IN ('article', 'article_full')""").fetchall()
    print(f"[load] 文档 {len(docs)} 篇，品牌 {len(brands)} 个")

    db.execute("DELETE FROM doc_entities")
    n_rows = 0
    for d in docs:
        title = d["title"] or ""
        body = (d["text_clean"] or "")[:5000]
        hits = {}
        for bid, info in brands.items():
            c_title = count_mentions(title, info["terms"])
            c_body = count_mentions(body, info["terms"])
            total = c_title + c_body
            if total:
                hits[bid] = {"group": info["group"], "title": c_title,
                             "body": c_body, "total": total}
        if not hits:
            continue
        # 角色判定
        cn_in_title = {b: h for b, h in hits.items()
                       if h["group"] == "cn" and h["title"] > 0}
        core = (max(cn_in_title, key=lambda b: cn_in_title[b]["total"])
                if cn_in_title else None)
        for bid, h in hits.items():
            if bid == core:
                role = "CORE_SUBJECT"
            elif h["group"] == "comp" and h["title"] > 0:
                role = "BENCHMARK"
            else:
                role = "PASSING_MENTION"
            db.execute(
                "INSERT INTO doc_entities (doc_id, brand_id, role_in_doc, mention_count)"
                " VALUES (?, ?, ?, ?)",
                (d["doc_id"], bid, role, h["total"]))
            n_rows += 1
    db.commit()

    stat = db.execute(
        """SELECT role_in_doc, COUNT(*) FROM doc_entities GROUP BY 1""").fetchall()
    top = db.execute(
        """SELECT brand_id, COUNT(*) n FROM doc_entities
           GROUP BY 1 ORDER BY n DESC LIMIT 8""").fetchall()
    print(f"[done] doc_entities {n_rows} 行 | 角色分布: {dict(stat)}")
    print("[top]", [(r[0], r[1]) for r in top])
    db.close()


if __name__ == "__main__":
    main()
