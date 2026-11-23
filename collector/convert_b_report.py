# -*- coding: utf-8 -*-
"""外部回传数据转换器：外部 JSONL → 本系统 raw 格式（一次性，可复用）"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters.base import RawRecord, RawStore, text_sha256  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "corpus" / "_incoming_B_20261119" / "googlenews_items.jsonl"
store = RawStore()
n = 0
for line in SRC.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    d = json.loads(line)
    rec = RawRecord(
        source_id="googlenews_B",
        layer="L2",
        language=d.get("lang", "ar"),
        country=d.get("country", "GCC"),
        url=d.get("link", ""),
        title=d.get("title", ""),
        text=(d.get("title", "") + " " + (d.get("snippet") or d.get("desc") or "")).strip(),
        published=d.get("published") or d.get("date"),
        content_type="article",
        extra={"origin_query": d.get("query"), "contributor": "member_B",
               "her_id": d.get("id")},
    )
    store.save("googlenews_B", rec, raw_payload=json.dumps(d, ensure_ascii=False)[:50000])
    n += 1
print(f"converted {n} items → corpus/raw/googlenews_B/")
