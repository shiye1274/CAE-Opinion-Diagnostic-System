# -*- coding: utf-8 -*-
"""大屏统计聚合接口。"""
from fastapi import APIRouter

from ..core.db import query

router = APIRouter()


@router.get("/stats/overview")
def overview():
    total = query("SELECT COUNT(*) n FROM corpus_documents")[0]["n"]
    by_lang = query("""SELECT language, COUNT(*) n FROM corpus_documents
                       GROUP BY language ORDER BY n DESC""")
    by_layer = query("""SELECT source_layer layer, COUNT(*) n FROM corpus_documents
                        GROUP BY source_layer ORDER BY n DESC""")
    by_country = query("""SELECT country, COUNT(*) n FROM corpus_documents
                          GROUP BY country ORDER BY n DESC LIMIT 10""")
    by_variant = query("""SELECT lang_variant, COUNT(*) n FROM corpus_documents
                          GROUP BY lang_variant ORDER BY n DESC""")
    ugc = query("SELECT COUNT(*) n FROM ugc_threads")[0]["n"]
    words = query("SELECT SUM(word_count) n FROM corpus_documents")[0]["n"] or 0
    return {
        "total_docs": total,
        "total_ugc": ugc,
        "total_words": words,
        "arabic_ratio": round(next((x["n"] for x in by_lang if x["language"] == "ar"), 0) / max(total, 1), 3),
        "by_language": by_lang,
        "by_layer": by_layer,
        "by_country": by_country,
        "by_lang_variant": by_variant,
    }


@router.get("/stats/timeline")
def timeline(lang: str = ""):
    """按月语料量时间线 + 四阶段事件锚点（萌芽/破局/爆发/深水，规划文档 3.2 节）。"""
    where, params = ["1=1"], []
    if lang:
        where.append("language = ?")
        params.append(lang)
    rows = query(
        f"""SELECT published, language, word_count FROM corpus_documents
            WHERE {' AND '.join(where)} AND published IS NOT NULL LIMIT 5000""",
        tuple(params),
    )

    def to_ym(s: str) -> str | None:
        s = (s or "").strip()
        try:
            if "T" in s and s[:4].isdigit():          # GDELT: 20260823T144500Z
                return s[:4] + "-" + s[4:6]
            if "," in s:                               # RSS: Tue, 17 Nov 2026 ...
                from email.utils import parsedate_to_datetime
                return parsedate_to_datetime(s).strftime("%Y-%m")
            if len(s) >= 7 and s[:4].isdigit():        # ISO: 2026-11-17T...
                return s[:7]
        except Exception:  # noqa: BLE001
            return None
        return None

    buckets: dict[str, int] = {}
    for r in rows:
        ym = to_ym(r["published"])
        if ym and "1900" < ym < "2100":
            buckets[ym] = buckets.get(ym, 0) + 1
    timeline = [{"ym": k, "n": buckets[k]} for k in sorted(buckets)]

    # 四阶段事件锚点（可视化 markArea 用）
    phases = [
        {"name": "萌芽期", "range": ["2018-01", "2020-12"],
         "note": "海湾净零倡议萌芽与 Tesla 先行"},
        {"name": "破局期", "range": ["2021-01", "2022-12"],
         "note": "中阿峰会、沙特 Ceer/Lucid 布局、中国车企批量涌入"},
        {"name": "爆发期", "range": ["2023-01", "2024-12"],
         "note": "BYD 全面登陆海湾、COP28 迪拜、主权基金投资"},
        {"name": "深水期", "range": ["2025-01", "2026-11"],
         "note": "中东本土建厂、高温长测口碑分化、渠道洗牌"},
    ]
    return {"timeline": timeline, "phases": phases}
