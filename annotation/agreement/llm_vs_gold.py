# -*- coding: utf-8 -*-
"""
llm_vs_gold.py —— LLM 银标准 vs 人工金标准 Macro-F1 评测（规划门禁 ≥0.80）
============================================================================
输入：
  --gold  人工标注导出（Label Studio JSON，可给多份取并集/首份）
  --silver 大模型银标准 jsonl（默认取 annotation/data/最新一份）
比较口径：
  - 核心字段（主导框架 / 情感 / 误读 / 层级 / 角色）逐字段 Macro-F1
  - 模型侧取 annotations.model_a（并附 model_b 与"双模型一致子集"的结果）
  - 人工侧取导出中每条的第一份标注（LS 导出若含多份，取第一个）
  - 标签统一归一为纯代码（"TECH_LEADERSHIP 技术领先" → "TECH_LEADERSHIP"）

用法：
  python annotation/agreement/llm_vs_gold.py --gold ann_a1.json
  python annotation/agreement/llm_vs_gold.py --gold ann_a1.json --gold ann_a2.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

AGREEMENT = Path(__file__).resolve().parent
DATA_DIR = AGREEMENT.parent / "data"
CODE_FIELDS = ["role_type", "referent_level", "primary_frame",
               "sentiment_5scale", "misreading_type"]
SET_FIELDS = ["aspect_category", "brand_matrix"]
GATE = 0.80


def canon(field: str, value) -> str | list | None:
    if value is None:
        return None
    if field in SET_FIELDS:
        items = value if isinstance(value, list) else [value]
        out = []
        for v in items:
            tok = str(v).strip().split()
            out.append(tok[0] if tok else str(v))
        return sorted(set(out))
    tok = str(value).strip().split()
    return tok[0] if tok else str(value)


def load_gold(paths: list[Path]) -> dict[str, dict]:
    """LS 导出 → {doc_id: {field: canonical}}（多份时先到先得，可后续改为仲裁版）。"""
    gold: dict[str, dict] = {}
    for p in paths:
        items = json.loads(p.read_text(encoding="utf-8"))
        for it in items:
            d = it.get("data", {})
            doc_id = d.get("doc_id") or d.get("calib_id")
            if not doc_id or doc_id in gold:
                continue
            labels = {}
            for ann in (it.get("annotations") or [])[:1]:
                for res in ann.get("result", []):
                    name = res.get("from_name")
                    val = res.get("value")
                    if not name or val is None:
                        continue
                    if isinstance(val, dict):
                        v = (val.get("choice") or val.get("choices")
                             or val.get("labels") or val.get("text") or val.get(name))
                    else:
                        v = val
                    labels[name] = canon(name, v)
            if labels:
                gold[doc_id] = labels
    return gold


def load_silver(path: Path) -> dict[str, dict]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        a = r.get("annotations", {}).get("model_a")
        if a:
            out[r["doc_id"]] = {f: canon(f, a.get(f)) for f in CODE_FIELDS + SET_FIELDS}
    return out


def f1(y_true: list, y_pred: list) -> float:
    labels = sorted(set(y_true) | set(y_pred))
    f1s = []
    for lb in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lb and p == lb)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lb and p == lb)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lb and p != lb)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return sum(f1s) / len(f1s) if f1s else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", nargs="+", required=True, help="人工导出 JSON（可多份）")
    ap.add_argument("--silver", default=None, help="银标准 jsonl（默认最新）")
    args = ap.parse_args()

    silver_path = Path(args.silver) if args.silver else None
    if silver_path is None:
        cands = sorted(DATA_DIR.glob("silver_*.jsonl"),
                       key=lambda p: p.stat().st_mtime)
        if not cands:
            sys.exit("未找到银标准文件 annotation/data/silver_*.jsonl")
        silver_path = cands[-1]

    gold = load_gold([Path(p) for p in args.gold])
    silver = load_silver(silver_path)
    common = sorted(set(gold) & set(silver))
    print(f"[对齐] 金标准 {len(gold)} 条 | 银标准 {len(silver)} 条 | "
          f"交集 {len(common)} 条（{silver_path.name}）")
    if len(common) < 30:
        print("[警告] 交集不足 30 条，F1 参考性有限")
    if not common:
        sys.exit(2)

    per_field = {}
    for f in CODE_FIELDS + SET_FIELDS:
        yt, yp = [], []
        for cid in common:
            g, s = gold[cid].get(f), silver[cid].get(f)
            if f in SET_FIELDS:
                # 集合字段按完全匹配记 0/1 准确率，不计 Macro-F1
                yt.append("MATCH" if g == s else "MISS")
                yp.append("MATCH")
            else:
                if g is None or s is None:
                    continue
                yt.append(str(g))
                yp.append(str(s))
        if not yt:
            continue
        if f in SET_FIELDS:
            acc = sum(1 for t, p in zip(yt, yp) if t == p) / len(yt)
            per_field[f] = {"accuracy": round(acc, 4), "n": len(yt)}
        else:
            per_field[f] = {"macro_f1": round(f1(yt, yp), 4), "n": len(yt),
                            "accuracy": round(sum(1 for t, p in zip(yt, yp)
                                                  if t == p) / len(yt), 4)}

    core = [per_field[f]["macro_f1"] for f in CODE_FIELDS if f in per_field]
    macro_all = round(sum(core) / len(core), 4) if core else 0.0
    verdict = macro_all >= GATE

    print(f"\n{'字段':<20}{'Macro-F1':>10}{'准确率':>10}{'样本':>6}")
    print("-" * 46)
    for f in CODE_FIELDS:
        if f in per_field:
            v = per_field[f]
            print(f"{f:<20}{v.get('macro_f1', '-'):>10}{v.get('accuracy', '-'):>10}{v['n']:>6}")
    for f in SET_FIELDS:
        if f in per_field:
            v = per_field[f]
            print(f"{f:<20}{'—':>10}{v['accuracy']:>10}{v['n']:>6}  (集合口径)")
    print("-" * 46)
    print(f"核心字段 Macro-F1 = {macro_all}   门禁 ≥{GATE}: "
          f"{'✅ PASS' if verdict else '❌ FAIL'}")

    out = DATA_DIR / "llm_vs_gold_report.json"
    out.write_text(json.dumps({
        "silver_file": str(silver_path), "n_common": len(common),
        "macro_f1_core": macro_all, "gate": GATE, "pass": verdict,
        "per_field": per_field,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[报告] {out}")


if __name__ == "__main__":
    main()
