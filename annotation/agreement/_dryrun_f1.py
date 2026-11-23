# -*- coding: utf-8 -*-
"""F1 评测链路端到端演练（临时）：合成银标 == 金标准 → 应 PASS 1.0"""
import json
import sys
from pathlib import Path

AGREEMENT = Path(__file__).resolve().parent
DATA_DIR = AGREEMENT.parent / "data"

gold = json.loads((DATA_DIR / "_dryrun_a1.json").read_text(encoding="utf-8"))
rows = []
for it in gold:
    labels = {}
    for ann in (it.get("annotations") or [])[:1]:
        for res in ann.get("result", []):
            v = res.get("value", {})
            labels[res["from_name"]] = (v.get("choice") or v.get("colors")
                                        or v.get("choices") or v.get("text"))
    rows.append({"doc_id": it["data"]["doc_id"],
                 "annotations": {"model_a": labels, "model_b": labels},
                 "annotation_meta": {"accepted": True}})
out = DATA_DIR / "_dryrun_silver.jsonl"
out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
               encoding="utf-8")
print(f"[setup] 合成银标 {len(rows)} 条 → {out.name}")

sys.argv = ["llm_vs_gold.py", "--gold", str(DATA_DIR / "_dryrun_a1.json"),
            "--silver", str(out)]
import llm_vs_gold  # noqa: E402
llm_vs_gold.main()
