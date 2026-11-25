# -*- coding: utf-8 -*-
"""
merge_b_1125.py —— 组员B 20261125 数据包合并器（通用版）
================================================================
自动按字段分派三种格式（B_data_format.md 口径）：
  ugc_type 字段 → YouTube 评论 → source_id=youtube, L5
  link 字段     → Google News  → source_id googlenews_B, L2
  url 字段      → 汽车媒体全文 → source_id 原样, L3（text_len<200 跳过）

去重由 pipeline 的内容哈希完成，历史已入库条目重复无害。

用法：python collector/merge_b_1125.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters.base import RawRecord, RawStore  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STAGING = PROJECT_ROOT / "corpus" / "_incoming_B_20261125"


def convert_item(d: dict, src_name: str, store: RawStore) -> bool:
    if "ugc_type" in d:                       # YouTube 评论/帖子
        if d.get("ugc_type") != "comment":
            return False
        vid = d.get("video_id", "")
        rec = RawRecord(
            source_id="youtube", layer="L5", language="", country="GCC",
            url=f"https://www.youtube.com/watch?v={vid}",
            title="(YouTube 评论)", text=d.get("text", ""),
            published=d.get("timestamp"), author=d.get("author_hash"),
            engagement={"likes": d.get("like_count")},
            content_type="comment",
            parent_url=f"https://www.youtube.com/watch?v={vid}",
            extra={"contributor": "member_B", "via": "youtube_api_official",
                   "her_id": d.get("id")},
        )
        store.save("youtube", rec, raw_payload=json.dumps(d, ensure_ascii=False)[:30000])
        return True
    if "link" in d:                            # Google News
        rec = RawRecord(
            source_id="googlenews_B", layer="L2",
            language=d.get("lang", "ar"), country=d.get("country", "GCC"),
            url=d.get("link", ""), title=d.get("title", ""),
            text=(d.get("title", "") + " " + (d.get("snippet") or "")).strip(),
            published=d.get("pub_date"), content_type="article",
            extra={"origin_query": d.get("query"),
                   "publisher": d.get("publisher"),
                   "contributor": "member_B", "her_id": d.get("id")},
        )
        store.save("googlenews_B", rec, raw_payload=json.dumps(d, ensure_ascii=False)[:50000])
        return True
    if "url" in d:                             # 汽车媒体全文
        if (d.get("text_len") or 0) < 200:
            return False
        rec = RawRecord(
            source_id=d.get("source_id", src_name), layer="L3",
            language=d.get("lang", "ar"), country="GCC",
            url=d.get("url", ""), title=d.get("title", ""),
            text=d.get("text", ""), content_type="article",
            extra={"contributor": "member_B",
                   "extraction": d.get("extraction"), "her_id": d.get("id")},
        )
        store.save(d.get("source_id", src_name), rec,
                   raw_payload=json.dumps(d, ensure_ascii=False)[:200000])
        return True
    return False


def main() -> None:
    store = RawStore()
    counts: dict[str, int] = {}
    files = sorted(STAGING.rglob("items.jsonl"))
    for f in files:
        src_name = f.parent.parent.name   # <src>/<date>/items.jsonl
        n = 0
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                if convert_item(json.loads(line), src_name, store):
                    n += 1
            except Exception:  # noqa: BLE001
                continue
        key = src_name if "youtube" not in src_name else "youtube"
        counts[key] = counts.get(key, 0) + n
    total = sum(counts.values())
    print(f"[merge] 文件 {len(files)} 份 → 转换 {total} 条: {counts}")
    if total == 0:
        print("[warn] 无新记录（可能已全部合并过，pipeline 去重也会兜底）")


if __name__ == "__main__":
    main()
