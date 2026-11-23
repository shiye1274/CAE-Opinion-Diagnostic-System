# -*- coding: utf-8 -*-
"""
文化合规审查规则库 v0.1
========================
五维规则（对齐方案B"文化合规审查"与规划文档第四章准则）：
  RELIGION   宗教禁忌（日常感叹词 vs 实质宗教议题，规则内已按准则一/二处理）
  POLITICS   政治与地缘敏感
  GENDER     性别与家庭隐私
  CUSTOM     社会习俗（斋月/饮食/赌彩等）
  STEREOTYPE 刻板归因与事实性误导表达

severity: high = 建议必改 / medium = 强烈建议复核 / low = 提示注意
每条规则给 advice（本土化改写建议方向）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

RULES: List[Dict[str, Any]] = [
    # ---------- RELIGION 宗教 ----------
    {"id": "R01", "category": "RELIGION", "severity": "high",
     "patterns": [r"jesus", r"christ", r"cross\b", r"بشارة", r"صليب", r"耶稣", r"十字架"],
     "advice": "营销文案避免宗教符号与宗教人物；改用 '创新/未来' 等中性叙事。"},
    {"id": "R02", "category": "RELIGION", "severity": "medium",
     "patterns": [r"mosque", r"مسجد", r"清真寺", r"qibla", r"قبلة"],
     "advice": "涉及宗教场所需本地化复核：如车载 Qibla 指南功能为正向加分项，可保留并强调。"},
    {"id": "R03", "category": "RELIGION", "severity": "medium",
     "patterns": [r"ramadan sale", r"رمضان كريم.*?offer", r"斋月促销", r"斋月营销"],
     "advice": "斋月营销合规：强调家庭团聚/慈善，避免 '大促' 语感；营业时间表述需调整。"},
    {"id": "R04", "category": "RELIGION", "severity": "high",
     "patterns": [r"halal\?|not halal", r"haram", r"حرام", r"哈拉姆"],
     "advice": "慎用宗教裁决类词汇描述产品；金融产品需走正式 Islamic finance 认证表述。"},

    # ---------- POLITICS 政治地缘 ----------
    {"id": "P01", "category": "POLITICS", "severity": "high",
     "patterns": [r"Israel", r"إسرائيل", r"以色列", r"west bank", r"gaza"],
     "advice": "商业文案绝对避免卷入巴以议题；相关新闻聚合需打标签隔离。"},
    {"id": "P02", "category": "POLITICS", "severity": "high",
     "patterns": [r"iran regime", r"خامن", r"mullah", r"伊朗政权"],
     "advice": "地缘政治表述交由政府事务口径，营销文案一律不涉及。"},
    {"id": "P03", "category": "POLITICS", "severity": "medium",
     "patterns": [r"oil dependence", r"oil-rich", r"石油依赖", r"产油国包袱"],
     "advice": "避免'石油依赖=落后'叙事；改用'能源转型伙伴'框架。"},
    {"id": "P04", "category": "POLITICS", "severity": "medium",
     "patterns": [r"expat only", r"for foreigners", r"仅限外籍"],
     "advice": "Gulf 双层话语圈敏感：避免暗示本地公民/外籍分层。"},

    # ---------- GENDER 性别与家庭 ----------
    {"id": "G01", "category": "GENDER", "severity": "high",
     "patterns": [r"sexy", r"hot\b.*(girl|woman)", r"bikini", r"محجبة\?", r"性感女郎", r"比基尼"],
     "advice": "女性形象呈现需本地化：家庭场景/职业形象优先，避免物化表达。"},
    {"id": "G02", "category": "GENDER", "severity": "medium",
     "patterns": [r"women can'?t? ?drive|женщины за рулем", r"女性不该开车"],
     "advice": "沙特 2018 年已解除女性驾驶禁令；此为典型 FACTUAL_ERROR，必须删除。"},
    {"id": "G03", "category": "GENDER", "severity": "medium",
     "patterns": [r"family privacy", r"خصوصية العائلة", r"家庭隐私"],
     "advice": "正向适配项：后排遮阳帘/家庭隐私模式可作为卖点正面表述。"},

    # ---------- CUSTOM 社会习俗 ----------
    {"id": "C01", "category": "CUSTOM", "severity": "high",
     "patterns": [r"\balcohol\b|\bbeer\b|\bwine\b", r"خمر|كحول", r"酒精|啤酒|红酒"],
     "advice": "海湾市场禁酒：车载酒柜/酒类广告一律删除；车辆文案勿关联酒类场景。"},
    {"id": "C02", "category": "CUSTOM", "severity": "high",
     "patterns": [r"\bpork\b|bacon", r"لحم الخنزير", r"猪肉|培根"],
     "advice": "饮食禁忌：广告素材与联名活动排除猪肉元素。"},
    {"id": "C03", "category": "CUSTOM", "severity": "medium",
     "patterns": [r"casino|gambling|lottery", r"قمار|مسابح يانصيب", r"赌场|博彩|彩票"],
     "advice": "博彩元素禁用；抽奖活动需走合规赠品机制。"},
    {"id": "C04", "category": "CUSTOM", "severity": "low",
     "patterns": [r"dog\?.*car|pet in car", r"كلب", r"宠物狗"],
     "advice": "宠物元素低敏感，但投放素材可优先家庭/科技场景。"},

    # ---------- STEREOTYPE 刻板归因 ----------
    {"id": "S01", "category": "STEREOTYPE", "severity": "medium",
     "patterns": [r"cheap chinese", r"صيني رخيص|صيني بو هبة", r"中国货廉价|中国车不行"],
     "advice": "典型 STEREOTYPICAL_ATTRIBUTION；用技术证据（刀片电池/夏测数据）反制。"},
    {"id": "S02", "category": "STEREOTYPE", "severity": "medium",
     "patterns": [r"will (never )?(catch fire|explode)", r"اشتعال البطاريات", r"必然自燃|一定爆炸"],
     "advice": "对照规划准则四：对已完成阿联酋/沙特夏测车型，无依据普遍否定 → 事实核查回应。"},
    {"id": "S03", "category": "STEREOTYPE", "severity": "low",
     "patterns": [r"copycat|copy of tesla", r"نسخة من", r"抄袭特斯拉|山寨"],
     "advice": "'模仿者'框架 → 转向'自研技术/专利数'叙事。"},
]

# 准则二：日常宗教感叹词白名单（出现不计为违规）
RELIGION_WHITELIST = [r"إن ?شاء ?الله", r"الحمد ?لله", r"ما ?شاء ?الله", r"تبارك ?الله",
                      r"والله", r"السلام ?عليكم", r"inshallah", r"mashallah", r"alhamdulillah"]


def scan(text: str) -> Dict[str, Any]:
    """扫描文本，返回命中规则列表 + 总体风险等级 + 改写建议。"""
    if not text or not text.strip():
        return {"risk_level": "CLEAN", "hits": [], "summary": "文本为空"}
    low = text.lower()
    hits: List[Dict[str, Any]] = []
    for rule in RULES:
        for pat in rule["patterns"]:
            flags = re.IGNORECASE
            m = re.search(pat, text if any('\u0600' <= c <= '\u06FF' for c in text) or pat.isascii() is False else low, flags)
            m = m or re.search(pat, low, flags)
            if m:
                s, e = m.span()
                hits.append({
                    "rule_id": rule["id"],
                    "category": rule["category"],
                    "severity": rule["severity"],
                    "matched": text[max(s - 20, 0):min(e + 20, len(text))],
                    "term": m.group(0),
                    "advice": rule["advice"],
                })
                break  # 每规则命中一次即可
    # 风险分级
    if any(h["severity"] == "high" for h in hits):
        level = "HIGH"
    elif any(h["severity"] == "medium" for h in hits):
        level = "MEDIUM"
    elif hits:
        level = "LOW"
    else:
        level = "CLEAN"
    cats = sorted({h["category"] for h in hits})
    summary = {
        "HIGH": "存在高风险表达，建议发布前必改",
        "MEDIUM": "存在中等风险，强烈建议复核改写",
        "LOW": "存在提示级风险，可酌情优化",
        "CLEAN": "未命中已知规则；上线前仍建议人工终审",
    }[level]
    return {"risk_level": level, "categories": cats, "hits": hits, "summary": summary}
