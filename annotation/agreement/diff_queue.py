# -*- coding: utf-8 -*-
"""
diff_queue.py —— 双人分歧清单 → 仲裁队列（队长按此逐条裁决）
==============================================================
输入两份 LS 导出，按 calib_id/doc_id 对齐，逐字段找出不一致项，输出：
  annotation/data/arbitration_queue.csv   （一行一个"文档×分歧字段"）
  终端摘要：总分歧数、按字段分布、完全一致条数

CSV 列：doc_id, calib_id, language, 语言字段, a1值, a2值, 原文标题（有则带）
队长裁决后把最终值填进 a_final 列，脚本 --apply 可把仲裁结果写回成 final 版导出。

用法：
  python annotation/agreement/diff_queue.py ann_a1.json ann_a2.json
  python annotation/agreement/diff_queue.py ann_a1.json ann_a2.json --apply
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

AGREEMENT = Path(__file__).resolve().parent
DATA_DIR = AGREEMENT.parent / "data"

sys.path.insert(0, str(AGREEMENT))
from llm_vs_gold import canon, load_gold  # noqa: E402

FIELDS = ["brand_matrix", "role_type", "referent_level", "primary_frame",
          "sentiment_5scale", "aspect_category", "misreading_type"]


def load_meta(paths: list[Path]) -> dict[str, dict]:
    """doc_id → {calib_id, language, title}"""
    meta = {}
    for p in paths:
        for it in json.loads(p.read_text(encoding="utf-8")):
            d = it.get("data", {})
            doc_id = d.get("doc_id") or d.get("calib_id")
            if doc_id and doc_id not in meta:
                meta[doc_id] = {"calib_id": d.get("calib_id", ""),
                                "language": d.get("language", ""),
                                "title": (d.get("title") or "")[:60]}
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("gold", nargs=2, help="两份 LS 导出")
    ap.add_argument("--apply", action="store_true",
                    help="读取 queue 的 a_final 列生成仲裁版 final 导出")
    args = ap.parse_args()

    g1 = load_gold([Path(args.gold[0])])
    g2 = load_gold([Path(args.gold[1])])
    meta = load_meta([Path(args.gold[0]), Path(args.gold[1])])
    common = sorted(set(g1) & set(g2))
    queue_path = DATA_DIR / "arbitration_queue.csv"

    if args.apply:
        # 读回队长填好的 a_final → 生成 merged final 版（只对已裁决行）
        rows = list(csv.DictReader(open(queue_path, encoding="utf-8-sig")))
        final_by_doc: dict[str, dict] = {}
        decided = 0
        for r in rows:
            if (r.get("a_final") or "").strip():
                final_by_doc.setdefault(r["doc_id"], {})[r["field"]] = \
                    canon(r["field"], r["a_final"].strip())
                decided += 1
        out = DATA_DIR / "gold_final.jsonl"
        n = 0
        with open(out, "w", encoding="utf-8") as f:
            for doc_id in common:
                merged = dict(g1.get(doc_id) or g2.get(doc_id) or {})
                if doc_id in final_by_doc:
                    merged.update(final_by_doc[doc_id])
                f.write(json.dumps({
                    "doc_id": doc_id, "gold": merged,
                    "annotation_meta": {"annotator_source": "HUMAN_GOLD",
                                        "round": "gold",
                                        "arbitrated": doc_id in final_by_doc},
                }, ensure_ascii=False) + "\n")
                n += 1
        print(f"[apply] 仲裁值 {decided} 处 → {out.name}（{n} 条）")
        return

    rows, per_field, exact = [], {f: 0 for f in FIELDS}, 0
    for doc_id in common:
        diff_fields = []
        for f in FIELDS:
            v1, v2 = g1[doc_id].get(f), g2[doc_id].get(f)
            if v1 != v2:
                diff_fields.append(f)
                per_field[f] += 1
                m = meta.get(doc_id, {})
                rows.append({"doc_id": doc_id, "calib_id": m.get("calib_id", ""),
                             "language": m.get("language", ""), "field": f,
                             "a1_value": v1, "a2_value": v2,
                             "title": m.get("title", ""), "a_final": ""})
        if not diff_fields:
            exact += 1

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(queue_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["doc_id", "calib_id", "language",
                                           "field", "a1_value", "a2_value",
                                           "title", "a_final"])
        w.writeheader()
        w.writerows(rows)

    print(f"[对齐] 共同样本 {len(common)} | 完全一致 {exact} 条 "
          f"({exact / max(len(common), 1):.0%}) | 分歧 {len(rows)} 处")
    print("[按字段]", {k: v for k, v in sorted(per_field.items(), key=lambda x: -x[1]) if v})
    print(f"[产出] {queue_path.name} —— 队长填 a_final 列后跑 --apply 生成仲裁版")


if __name__ == "__main__":
    main()
