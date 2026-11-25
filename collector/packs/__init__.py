# -*- coding: utf-8 -*-
"""
packs —— 词包加载与查询式生成
==============================
 brands_cn.yaml    中国品牌（核心锚点 BYD + 集群）
 brands_comp.yaml  对照品牌（Tesla/Lucid/日韩欧系）
 context_mena.yaml 海湾场景痛点词
 countries.yaml    国家/城市 + GDELT 语言过滤

查询组合策略（穷尽 × 可控）：
  gdelt 通道：品牌(全语言变体 OR) × 国家过滤 × 语言过滤          → 查全主力
  google_news 通道：品牌 × 国家名（当前语言）                     → 增量兜底
  site 通道：品牌英文名（多数站内搜索不支持阿语 OR 组合）
  reddit 通道：品牌英文名 × 城市
  youtube 通道：品牌 × 场景词（阿语优先）
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

PACKS_DIR = Path(__file__).resolve().parent

# 默认只跑核心锚点与高权重品牌（BYD + 4 个代表），避免首跑查询爆炸；
# --brands 参数可覆盖；--brands all 跑全部。
DEFAULT_BRANDS = ["byd", "nio", "xpeng", "jetour", "mg", "tesla", "lucid"]

# L1 政策层主题词（中/英/阿），不绑定品牌，用于政府门户与智库 RSS/HTML 源
POLICY_TERMS = {
    "zh": [
        "沙特 2030 愿景", "阿联酋 电动车政策", "海湾 电动汽车",
        "中东 可持续交通", "中国汽车 中东投资", "海湾 新能源",
        "卡塔尔 能源转型", "科威特 交通规划",
    ],
    "en": [
        "Vision 2030", "electric vehicle strategy", "Saudi EV",
        "UAE EV", "transport strategy", "automotive standards",
        "Chinese investment", "Gulf sustainability",
    ],
    "ar": [
        "رؤية 2030", "السيارات الكهربائية", "استراتيجية النقل",
        "معايير السيارات", "الاستدامة", "الشركات الصينية",
    ],
}


def load_packs() -> dict:
    import yaml
    def _load(name):
        with open(PACKS_DIR / name, encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {
        "brands_cn": (_load("brands_cn.yaml") or {}).get("brands_cn", []),
        "brands_comp": (_load("brands_comp.yaml") or {}).get("brands_comp", []),
        "context": (_load("context_mena.yaml") or {}).get("context_mena", []),
        "countries": (_load("countries.yaml") or {}).get("countries", []),
        "gdelt_langs": (_load("countries.yaml") or {}).get("gdelt_langs", {}),
        "gdelt_fips_or": (_load("countries.yaml") or {}).get("gdelt_fips_or", ""),
    }


def _brand_set(brands: Optional[List[str]]):
    packs = load_packs()
    all_b = packs["brands_cn"] + packs["brands_comp"]
    if not brands or brands == ["all"]:
        return all_b
    return [b for b in all_b if b["id"] in set(brands)]


def build_query_set(brands: Optional[List[str]] = None,
                    max_context_per_brand: int = 2) -> Dict[str, List[Tuple[str, str, str]]]:
    """返回各通道的查询列表 [(query, lang, country_code), ...]。"""
    packs = load_packs()
    sel = _brand_set(brands) or _brand_set(DEFAULT_BRANDS)
    countries = packs["countries"][:6]        # GCC 六国核心圈（辐射圈二期再开）
    langs = packs["gdelt_langs"]

    out: Dict[str, List[Tuple[str, str, str]]] = {
        "gdelt": [], "google_news": [], "site": [], "site_brands": [],
        "reddit": [], "youtube": [], "policy_terms": [],
    }

    for b in sel:
        qs = b["queries"]
        # --- GDELT：语言级 OR 组合 × GCC 国别 OR 组（一品牌一语言一查询，控总量防限流）---
        # 实测：GDELT 限流严格（惩罚累积，实测需 ≥60s/请求），错误以 200+纯文本返回
        fips = packs.get("gdelt_fips_or", "")
        for lang, flt in langs.items():
            # 实测规则：引号短语必须 ≥4 字符；短词（BYD/نيو/سير）用裸词
            def _term(t: str) -> str:
                core = t.strip('"')
                if len(core) < 4 and " " not in core:
                    return core          # 裸词
                return '"' + core + '"'  # 长短语加引号
            brand_terms = [_term(t) for t in (qs.get(lang) or qs.get("en", []))[:3]]
            if not brand_terms:
                continue
            core = " OR ".join(brand_terms)
            # 2026-11-19 实测：sourcecountry OR 组含无效代码会被整体拒绝且触发双倍请求，
            # 故去掉国别参数；国别改由 GDELT 返回的 sourcecountry 字段入库时打标
            q = f"({core}) {flt}".strip()
            out["gdelt"].append((q, lang, "GCC"))

        # --- Google News：品牌 × 国家（用国家本地语词做语境） ---
        for c in countries[:3]:
            for lang in ("ar", "en"):
                for t in (qs.get(lang, []) or [])[:2]:
                    cn_word = (c["queries"].get(lang) or [""])[0]
                    out["google_news"].append((f"{t} {cn_word}", lang, c["code"]))

        # --- 阿语增量：品牌 × 场景词组合（全新查询空间，避开重复捞取） ---
        ar_terms = (qs.get("ar") or [])[:1]
        ctx_ar = [c for ctx in packs["context"][:6]
                  for c in (ctx["queries"].get("ar") or [])[:1]]
        for t in ar_terms:
            for ctx_t in ctx_ar[:5]:
                out["gdelt"].append(
                    (f"({t.strip(chr(34))}) ({ctx_t.strip(chr(34))}) sourcelang:arabic", "ar", "GCC"))
                out["google_news"].append((f"{t} {ctx_t}", "ar", "GCC"))

        # --- 站内搜索：英文品牌名 ---
        for t in (qs.get("en") or [])[:1]:
            out["site_brands"].append((t, qs.get("en", [t])[0], "GCC"))

        # --- Reddit：品牌 × 城市（英文） ---
        for t in (qs.get("en") or [])[:1]:
            for c in countries[:2]:
                city = (c["queries"].get("en") or [""])[1] if len(c["queries"].get("en", [])) > 1 else ""
                out["reddit"].append((f"{t} {city}".strip(), "en", c["code"]))

        # --- YouTube：品牌 × 阿语场景词 ---
        ar_ctx = [c for ctx in packs["context"][:max_context_per_brand]
                  for c in (ctx["queries"].get("ar") or [])[:1]]
        for t in (qs.get("ar") or qs.get("en") or [])[:1]:
            for ctx_t in ar_ctx[:3]:
                out["youtube"].append((f"{t} {ctx_t}", "ar", "GCC"))

        # --- 中文源：品牌中文名 × 中东场景词（补中文层） ---
        zh_terms = (qs.get("zh") or [])[:2]
        ctx_zh = [c for ctx in packs["context"][:6]
                  for c in (ctx["queries"].get("zh") or [])[:1]]
        for t in zh_terms:
            for ctx_t in ctx_zh[:3]:
                out["site_brands"].append((f"{t} {ctx_t}", "zh", "CN"))
            out["google_news"].append((f"{t} 中东", "zh", "CN"))
            out["google_news"].append((f"{t} 沙特", "zh", "CN"))
            out["google_news"].append((f"{t} 阿联酋", "zh", "CN"))

    # --- L1 政策层主题查询（不绑定品牌） ---
    for lang, terms in POLICY_TERMS.items():
        for term in terms:
            out["policy_terms"].append((term, lang, "GCC"))

    # 去重保序
    for k in out:
        seen = set()
        uniq = []
        for item in out[k]:
            if item[0] not in seen:
                seen.add(item[0])
                uniq.append(item)
        out[k] = uniq
    return out
