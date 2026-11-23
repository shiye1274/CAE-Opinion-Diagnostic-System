# -*- coding: utf-8 -*-
"""品牌声量统计（雷达看板数据源 v0.5：声量 + 语言分布；情感雷达待标注完成后接入）。"""
from fastapi import APIRouter

from ..core.db import query
from ..services.brands import load_brand_index, brand_match_sql

router = APIRouter()


@router.get("/brands/volume")
def brand_volume():
    """各品牌：中/阿/英语料声量计数（LIKE 匹配 title+text）。"""
    out = []
    for bid, b in load_brand_index().items():
        terms = brand_match_sql(bid)[:6]   # 控制单品牌查询成本
        if not terms:
            continue
        conds, params = [], []
        for t in terms:
            conds.append("(title LIKE ? OR text_clean LIKE ?)")
            params += [f"%{t}%", f"%{t}%"]
        rows = query(
            f"""SELECT language, COUNT(*) n FROM corpus_documents
                WHERE ({' OR '.join(conds)}) GROUP BY language""", tuple(params))
        lang_map = {r["language"]: r["n"] for r in rows}
        out.append({
            "brand_id": bid, "name": b["name"], "group": b["group"],
            "total": sum(lang_map.values()),
            "ar": lang_map.get("ar", 0), "en": lang_map.get("en", 0), "zh": lang_map.get("zh", 0),
        })
    out.sort(key=lambda x: -x["total"])
    return {"brands": out}
