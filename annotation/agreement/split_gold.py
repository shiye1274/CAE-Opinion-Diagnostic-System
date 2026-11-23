# -*- coding: utf-8 -*-
"""
split_gold.py —— 金标准 6:2:2 切分（规划表 4-2：少样本提示库 / 验证集 / 盲测集）
==================================================================================
按语言分层、固定种子，产出三个 canonical JSONL：
  annotation/data/split_few_shot.jsonl   60%（可作 LLM few-shot 提示池）
  annotation/data/split_dev.jsonl        20%（调参/阈值）
  annotation/data/split_test.jsonl       20%（盲测，门禁 F1 只在此集上报）

用法：
  python annotation/agreement/split_gold.py --gold ann_a1.json [ann_a2.json ...]
  python annotation/agreement/split_gold.py --gold ... --use-final   # 若导出含仲裁 final
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

AGREEMENT = Path(__file__).resolve().parent
DATA_DIR = AGREEMENT.parent / "data"
SEED = 20261119
RATIOS = (0.6, 0.2, 0.2)

import sys  # noqa: E402

sys.path.insert(0, str(AGREEMENT))
from llm_vs_gold import canon, load_gold  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", nargs="+", required=True)
    args = ap.parse_args()

    gold = load_gold([Path(p) for p in args.gold])
    # 语言分层：从导出 data 中取（load_gold 未保留 → 重新扫一遍建立 doc→lang）
    lang_of: dict[str, str] = {}
    for p in args.gold:
        for it in json.loads(Path(p).read_text(encoding="utf-8")):
            d = it.get("data", {})
            doc_id = d.get("doc_id") or d.get("calib_id")
            if doc_id and doc_id not in lang_of:
                lang_of[doc_id] = d.get("language") or "unknown"

    by_lang: dict[str, list[str]] = defaultdict(list)
    for doc_id in gold:
        by_lang[lang_of.get(doc_id, "unknown")].append(doc_id)

    rng = random.Random(SEED)
    splits: dict[str, list[str]] = {"few_shot": [], "dev": [], "test": []}
    for lang, ids in sorted(by_lang.items()):
        rng.shuffle(ids)
        n = len(ids)
        n1, n2 = int(n * RATIOS[0]), int(n * RATIOS[1])
        splits["few_shot"] += ids[:n1]
        splits["dev"] += ids[n1:n1 + n2]
        splits["test"] += ids[n1 + n2:]
        print(f"[分层] {lang}: {n} 条 → {n1}/{n2}/{n - n1 - n2}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name, ids in splits.items():
        out = DATA_DIR / f"split_{name}.jsonl"
        with open(out, "w", encoding="utf-8") as f:
            for doc_id in sorted(ids):
                rec = {"doc_id": doc_id, "language": lang_of.get(doc_id),
                       "gold": gold[doc_id],
                       "annotation_meta": {"annotator_source": "HUMAN_GOLD",
                                           "round": "gold"}}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[产出] {out.name}: {len(ids)} 条")

    total = sum(len(v) for v in splits.values())
    assert total == len(gold), f"切分总数 {total} != 金标准 {len(gold)}"
    print(f"[OK] 6:2:2 切分完成（种子 {SEED}，可复现），合计 {total} 条")


if __name__ == "__main__":
    main()
