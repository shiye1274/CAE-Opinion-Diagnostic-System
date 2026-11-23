# -*- coding: utf-8 -*-
"""品牌映射：从 collector 词包加载品牌 → 检索词（用于声量统计）。"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, List

from ..core.config import PACKS_DIR


@lru_cache(maxsize=1)
def load_brand_index() -> Dict[str, dict]:
    """brand_id → {name, group, terms:{lang:[term]}}（group: cn / comp）"""
    import yaml
    idx: Dict[str, dict] = {}
    for fname, group in (("brands_cn.yaml", "cn"), ("brands_comp.yaml", "comp")):
        with open(PACKS_DIR / fname, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for b in data.get(fname.replace(".yaml", ""), []):
            idx[b["id"]] = {"id": b["id"], "name": b["name"], "group": group,
                            "queries": b.get("queries", {})}
    return idx


def brand_match_sql(brand_id: str) -> List[str]:
    """返回该品牌所有 LIKE 匹配片段（用于 SQL 计数）。"""
    b = load_brand_index().get(brand_id)
    if not b:
        return []
    terms: List[str] = []
    for lang_terms in b["queries"].values():
        for t in lang_terms:
            terms.append(t.strip('"'))
    return terms
