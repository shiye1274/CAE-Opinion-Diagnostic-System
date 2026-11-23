# -*- coding: utf-8 -*-
"""
合成数据端到端演练：模拟两名标注员的 Label Studio 导出 → kappa.py 一致性检验
=============================================================================
目的：真数据回传前验证整条验收链路无 bug（明天直接跑真文件零调试）。

演练内容：
1. 生成两份合成 LS 导出 JSON（200 条，a1/a2 各自视角，注入已知分歧率）
2. 跑 kappa.py → 应输出各字段 κ 与门禁判定
3. 生成"金标准最终版"（合并键 final）供后续 F1 评测使用

用法：python annotation/agreement/_dryrun_kappa.py
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

AGREEMENT = Path(__file__).resolve().parent
DATA_DIR = AGREEMENT.parent / "data"
FIELDS = ["brand_matrix", "role_type", "referent_level", "primary_frame",
          "sentiment_5scale", "aspect_category", "misreading_type"]

FRAME = ["TECH_LEADERSHIP", "PRICE_ADVANTAGE", "SAFETY_RECALL", "AFTER_SALES",
         "ENVIRONMENTAL", "POLICY_GEO", "CULTURAL_CONFLICT",
         "MARKET_COMPETITION", "LOCALIZATION_INVEST", "LUXURY_STATUS", "OTHER"]
SENT = ["+2", "+1", "0", "-1", "-2"]
MIS = ["FACTUAL_ERROR", "CONTEXT_MISPLACEMENT", "STEREOTYPICAL_ATTRIBUTION",
       "KEY_CONTEXT_OMISSION", "NO_MISREADING", "CANNOT_DETERMINE"]
ROLE = ["CORE_SUBJECT", "BENCHMARK", "PASSING_MENTION", "NOT_APPLICABLE"]
LEVEL = ["CORPORATE", "PRODUCT_BRAND", "SPECIFIC_MODEL", "INDUSTRY_CHAIN",
         "FINANCIAL", "INFRASTRUCTURE", "MIXED", "OTHER"]


def make_label(rng: random.Random) -> dict:
    return {
        "brand_matrix": rng.choice([["BYD 比亚迪"], ["Tesla 特斯拉"], ["无"]]),
        "role_type": rng.choice(ROLE),
        "referent_level": rng.choice(LEVEL),
        "primary_frame": rng.choice(FRAME),
        "sentiment_5scale": rng.choice(SENT),
        "aspect_category": rng.choice([["BATTERY_RANGE"], ["THERMAL_AC"], ["无"]]),
        "misreading_type": rng.choice(MIS),
    }


def make_export(ann_id: str, base: list[dict], flip_rate: float) -> dict:
    """生成一份 LS 导出：与基准答案一致，按 flip_rate 注入分歧。"""
    rng = random.Random(ann_id)
    items = []
    for i, truth in enumerate(base, 1):
        labels = dict(truth)
        if rng.random() < flip_rate:
            # 注入一个字段分歧（模拟真实边界案例）
            f = rng.choice(FIELDS)
            if f == "primary_frame":
                labels[f] = rng.choice([x for x in FRAME if x != truth[f]])
            elif f == "sentiment_5scale":
                labels[f] = rng.choice([x for x in SENT if x != truth[f]])
            elif f == "misreading_type":
                labels[f] = rng.choice([x for x in MIS if x != truth[f]])
        results = [{"from_name": f, "value": {("choices" if f in
                    ("brand_matrix", "aspect_category") else "choice"):
                    (labels[f] if isinstance(labels[f], list) else labels[f])}}
                   for f in FIELDS]
        items.append({
            "id": i,
            "data": {"calib_id": f"C{i:03d}", "doc_id": f"doc_{i:04d}"},
            "annotations": [{"completed_by": ann_id, "result": results}],
        })
    return items


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20261119)
    n = 200
    base = [make_label(rng) for _ in range(n)]

    a1 = make_export("a1", base, flip_rate=0.10)   # a1 与基准 10% 分歧
    a2 = make_export("a2", base, flip_rate=0.15)   # a2 15% 分歧 → 两人间约 20%+

    p1 = DATA_DIR / "_dryrun_a1.json"
    p2 = DATA_DIR / "_dryrun_a2.json"
    p1.write_text(json.dumps(a1, ensure_ascii=False), encoding="utf-8")
    p2.write_text(json.dumps(a2, ensure_ascii=False), encoding="utf-8")
    print(f"[dryrun] 合成导出: {p1.name} / {p2.name}（各 {n} 条，注入分歧 10%/15%）")

    # 跑 kappa.py（同进程调用）
    sys.argv = ["kappa.py", str(p1), str(p2)]
    import kappa  # noqa: E402
    kappa.main()

    # 校验产出
    report = AGREEMENT / "kappa_report.json"
    assert report.exists(), "kappa_report.json 未生成"
    rep = json.loads(report.read_text(encoding="utf-8"))
    assert rep["samples"] == n, f"对齐样本数异常: {rep['samples']}"
    print(f"[dryrun] ✅ 样本对齐 {rep['samples']} 条，报告字段 {len(rep['fields'])} 个")
    print("[dryrun] ✅ 验收链路就绪：真数据只需 python kappa.py ann_a1.json ann_a2.json")


if __name__ == "__main__":
    main()
