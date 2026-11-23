# -*- coding: utf-8 -*-
"""
外部进度包合并器（20261122）
1) 隔离四个污染源的 raw + 删 DB 记录（人工复核：/?s= 返回首页/栏目页）
2) 转换外部回传数据入库：almuraba 767 全文 / arabgt 34 全文 /
   youtube 7,733 评论（官方API，已脱敏）/ googlenews 223 新增
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters.base import RawRecord, RawStore  # noqa: E402
import sqlite3  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "corpus" / "raw"
INCOMING = ROOT / "corpus" / "_incoming_B_20261120"
JUNK_SOURCES = ["arabgt", "almuraba", "carswitch", "saudigazette"]

# ---- 1) 隔离污染 raw ----
quarantine = RAW / "_quarantine"
for src in JUNK_SOURCES:
    d = RAW / src
    if d.exists():
        quarantine.mkdir(exist_ok=True)
        shutil.move(str(d), str(quarantine / f"{src}_junk_20261122"))
        print(f"[隔离] raw/{src}")

# ---- 2) 删 DB 污染记录 ----
db = sqlite3.connect(ROOT / "corpus" / "meta" / "corpus.sqlite")
cur = db.execute(
    f"DELETE FROM corpus_documents WHERE source_id IN ({','.join('?' * len(JUNK_SOURCES))})",
    JUNK_SOURCES)
print(f"[清除] DB 污染记录 {cur.rowcount} 条")
db.commit()
db.close()

# ---- 3) 转换 B 的真实数据 ----
store = RawStore()
counts = {}


def conv_gnews(path: Path, source_id: str):
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        rec = RawRecord(
            source_id=source_id, layer="L2", language=d.get("lang", "ar"),
            country=d.get("country", "GCC"), url=d.get("link", ""),
            title=d.get("title", ""),
            text=(d.get("title", "") + " " + (d.get("snippet") or "")).strip(),
            published=d.get("pub_date"), content_type="article",
            extra={"origin_query": d.get("query"), "publisher": d.get("publisher"),
                   "contributor": "member_B", "her_id": d.get("id")},
        )
        store.save(source_id, rec, raw_payload=json.dumps(d, ensure_ascii=False)[:50000])
        n += 1
    return n


def conv_media(path: Path):
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if (d.get("text_len") or 0) < 200:
            continue  # 她标记的提取不足样本
        rec = RawRecord(
            source_id=d["source_id"], layer="L3", language=d.get("lang", "ar"),
            country="GCC", url=d.get("url", ""), title=d.get("title", ""),
            text=d.get("text", ""), published=None, content_type="article",
            extra={"contributor": "member_B", "extraction": d.get("extraction"),
                   "her_id": d.get("id")},
        )
        store.save(d["source_id"], rec, raw_payload=json.dumps(d, ensure_ascii=False)[:200000])
        n += 1
    return n


def conv_yt_comments(path: Path):
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("ugc_type") != "comment":
            continue
        rec = RawRecord(
            source_id="youtube", layer="L5", language="", country="GCC",
            url=f"https://www.youtube.com/watch?v={d.get('video_id', '')}",
            title="(YouTube 评论)", text=d.get("text", ""),
            published=d.get("timestamp"), author=d.get("author_hash"),
            engagement={"likes": d.get("like_count")},
            content_type="comment",
            parent_url=f"https://www.youtube.com/watch?v={d.get('video_id', '')}",
            extra={"contributor": "member_B", "via": "youtube_api_official",
                   "her_id": d.get("id")},
        )
        store.save("youtube", rec, raw_payload=json.dumps(d, ensure_ascii=False)[:30000])
        n += 1
    return n


counts["gnews_1120"] = conv_gnews(INCOMING / "googlenews_20261120_items.jsonl", "googlenews_B")
counts["almuraba"] = conv_media(INCOMING / "almuraba_20261120_items.jsonl")
counts["arabgt"] = conv_media(INCOMING / "arabgt_20261120_items.jsonl")
counts["yt_comments"] = conv_yt_comments(INCOMING / "youtube_kw_ar_20261120_items.jsonl")
print("[转换]", counts)
