# -*- coding: utf-8 -*-
"""
sentiment_baseline.py —— 海湾方言情感计算 · 外部基线评测
=========================================================
数据：arbml/ArSAS（阿拉伯语推文情感，含方言标注 → 可切海湾方言子集）
模型：CAMeL-Lab/bert-base-arabic-camelbert-mix-sentiment（10.9万下载标准基线）
       + Ammar-alhaj-ali/arabic-MARBERT-sentiment（MARBERT 方言系，对照）

产出：models/evaluation/baseline_report.json
      （宏平均F1/准确率/各类别F1 + 按方言子集切分 → 证明海湾方言难点）

用法：models/.venv/Scripts/python evaluation/sentiment_baseline.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import numpy as np  # noqa: E402
import torch  # noqa: E402
from datasets import load_dataset  # noqa: E402
from transformers import (AutoModelForSequenceClassification,  # noqa: E402
                          AutoTokenizer, pipeline)

EVAL_DIR = Path(__file__).resolve().parent
DATASET_ID = "arbml/ArSAS"
MODELS = [
    "CAMeL-Lab/bert-base-arabic-camelbert-mix-sentiment",
    "Ammar-alhaj-ali/arabic-MARBERT-sentiment",
]
MAX_SAMPLES = 4000   # CPU 评测抽样上限（可改全量）
SEED = 20261119


def f1_macro(y_true, y_pred) -> float:
    labels = sorted(set(y_true) | set(y_pred))
    f1s = []
    for lb in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lb and p == lb)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lb and p == lb)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lb and p != lb)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return float(np.mean(f1s))


def main() -> None:
    print("[data] loading", DATASET_ID)
    try:
        ds = load_dataset(DATASET_ID, split="train")
    except Exception:
        ds = load_dataset(DATASET_ID)["train"]
    print(f"[data] rows={len(ds)} features={list(ds.features)}")
    cols = list(ds.features)
    text_col = next((c for c in cols if c.lower() in
                     ("tweet", "text", "sentence", "content", "tweet_text", "text_clean")),
                    None)
    if text_col is None:   # 模糊兜底：找含 text/tweet 的列
        text_col = next((c for c in cols if "text" in c.lower() or "tweet" in c.lower()
                         and "id" not in c.lower()), None)
    if text_col is None:
        raise SystemExit(f"找不到文本列，features={cols}")
    label_col = next((c for c in cols
                      if c.lower() in ("sentiment", "label", "labels")), None)
    if label_col is None:   # 兜底排除置信度列
        label_col = next((c for c in cols
                          if ("label" in c.lower() or "sentiment" in c.lower())
                          and "confidence" not in c.lower()), None)
    if label_col is None:
        raise SystemExit(f"找不到标签列，features={cols}")
    dialect_col = next((c for c in cols if "dialect" in c.lower()), None)

    keep = [text_col, label_col] + ([dialect_col] if dialect_col else [])
    ds = ds.remove_columns([c for c in ds.features if c not in keep])
    ds = ds.shuffle(seed=SEED).select(range(min(MAX_SAMPLES, len(ds))))
    texts = [str(t) for t in ds[text_col]]
    # ClassLabel 索引 → 名称（arbml/ArSAS: 0=Negative 1=Neutral 2=Positive 3=Mixed）
    feat = ds.features[label_col]
    label_names = getattr(feat, "names", None)
    if label_names:
        golds = [str(label_names[int(v)]).strip().lower() for v in ds[label_col]]
    else:
        golds = [str(v).strip().lower() for v in ds[label_col]]
    dialects = [str(x).strip() for x in ds[dialect_col]] if dialect_col else None
    print(f"[data] labels={sorted(set(golds))}"
          + (f" | dialect={sorted(set(dialects))[:8]}" if dialect_col else ""))

    report = {"dataset": DATASET_ID, "n_eval": len(golds),
              "label_set": sorted(set(golds)), "models": {}}

    for mid in MODELS:
        print(f"\n[model] {mid}")
        try:
            tok = AutoTokenizer.from_pretrained(mid)
            mdl = AutoModelForSequenceClassification.from_pretrained(mid)
            mdl.eval()
            clf = pipeline("text-classification", model=mdl, tokenizer=tok,
                           truncation=True, max_length=128, batch_size=32)
            preds_raw = clf(texts)
            id2 = {int(k): str(v) for k, v in mdl.config.id2label.items()}
            # pipeline 返回 label 名称；统一小写
            preds = [p["label"].strip().lower() for p in preds_raw]
            # 标签空间对齐诊断：模型输出 ∩ 数据标签
            overlap = set(preds) & set(golds)
            mapped = []
            for p in preds:
                if p in set(golds):
                    mapped.append(p)
                elif overlap:   # 名称不同但可启发式对齐（如 'positive' vs 'pos'）
                    best = max(overlap, key=lambda g: len(set(g) & set(p)))
                    mapped.append(best if len(set(best) & set(p)) >= 2 else p)
                else:
                    mapped.append(p)

            acc = float(np.mean([1.0 if a == b else 0.0 for a, b in zip(golds, mapped)]))
            mf1 = f1_macro(golds, mapped)
            # 公平口径：排除 mixed（两个基线模型均为3类，数据集4类 → mixed 必错）
            sub = [(g, p) for g, p in zip(golds, mapped) if g != "mixed"]
            mf1_3 = (f1_macro([g for g, _ in sub], [p for _, p in sub]) if sub else None)
            entry = {"acc": round(acc, 4), "macro_f1": round(mf1, 4),
                     "macro_f1_3class_subset": (round(mf1_3, 4) if mf1_3 else None),
                     "n_3class_subset": len(sub),
                     "model_labels": sorted(set(preds))}
            print(f"[result] {mid}: acc={acc:.4f} macro_f1={mf1:.4f}")

            # 按方言切分（海湾系 vs 其他）—— 点题"海湾方言情感难点"
            if dialect_col:
                by_d: dict[str, list[tuple[str, str]]] = defaultdict(list)
                for g, p, d in zip(golds, mapped, dialects):
                    by_d[d].append((g, p))
                per = {}
                for d, pairs in sorted(by_d.items(), key=lambda x: -len(x[1])):
                    if len(pairs) < 50:
                        continue
                    per[d] = {"n": len(pairs),
                              "macro_f1": round(f1_macro([a for a, _ in pairs],
                                                         [b for _, b in pairs]), 4)}
                entry["per_dialect"] = per
                print("[per-dialect]", json.dumps(per, ensure_ascii=False))

            report["models"][mid] = entry
            del mdl, tok, clf
            torch.cuda.empty_cache() if torch.cuda.is_available() else None
        except Exception as e:  # noqa: BLE001
            print(f"[error] {mid}: {e}")
            report["models"][mid] = {"error": str(e)[:300]}

    out = EVAL_DIR / "baseline_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[done] → {out}")


if __name__ == "__main__":
    main()
