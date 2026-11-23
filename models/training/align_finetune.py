# -*- coding: utf-8 -*-
"""
align_finetune.py —— 跨语言对齐模型微调（e5-small + InfoNCE）
===============================================================
训练数据：corpus/aligned/pairs.jsonl 的 900 对中阿英同事件标题平行对
损失：MultipleNegativesRankingLoss（批内负例 = 无需负样本构造）
评测：留出 20% 对 → 检索 Recall@1/5/10（微调前 vs 微调后对照）
门禁：Recall@10 ≥ 0.80（规划表 5-1）

用法：models/.venv/Scripts/python training/align_finetune.py [--epochs 4]
"""
from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import numpy as np  # noqa: E402
import torch  # noqa: E402
from sentence_transformers import (InputExample, SentenceTransformer,  # noqa: E402
                                   losses, models, evaluation)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PAIRS_PATH = PROJECT_ROOT / "corpus" / "aligned" / "pairs.jsonl"
CKPT_DIR = PROJECT_ROOT / "models" / "checkpoints"
EVAL_DIR = PROJECT_ROOT / "models" / "evaluation"
MODEL_NAME = "intfloat/multilingual-e5-small"
SEED = 20261119


def load_pairs() -> List[tuple[str, str, str]]:
    pairs = []
    for line in PAIRS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        src, tgt = (d["src_title"] or "").strip(), (d["tgt_title"] or "").strip()
        if len(src) > 8 and len(tgt) > 8 and d["src_lang"] == "ar":
            pairs.append((src, tgt, d["cluster_id"] if "cluster_id" in d else ""))
    return pairs


def retrieval_scores(model: SentenceTransformer, srcs: List[str], tgts: List[str],
                     gold_idx: List[int]) -> dict:
    """在 tgt 池里检索：每个 src 的正确 tgt 排名 → R@K。"""
    s = model.encode(srcs, batch_size=64, convert_to_tensor=True,
                     normalize_embeddings=True, show_progress_bar=False)
    t = model.encode(tgts, batch_size=64, convert_to_tensor=True,
                     normalize_embeddings=True, show_progress_bar=False)
    sims = s @ t.T                      # [n, n]
    order = sims.argsort(dim=-1, descending=True)
    out = {}
    for k in (1, 5, 10):
        hits = 0
        for i, g in enumerate(gold_idx):
            rank = int((order[i] == g).nonzero(as_tuple=True)[0][0])
            hits += 1 if rank < k else 0
        out[f"R@{k}"] = round(hits / len(gold_idx), 4)
    return out


from typing import List  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    args = ap.parse_args()

    random.seed(SEED)
    pairs = load_pairs()
    print(f"[data] {len(pairs)} 平行标题对")
    if len(pairs) < 100:
        raise SystemExit("对数不足，先跑 event_cluster.py")

    random.shuffle(pairs)
    n_test = max(50, int(len(pairs) * 0.2))
    test_pairs, train_pairs = pairs[:n_test], pairs[n_test:]
    # 检索池：src 池 × tgt 池（正确 tgt 在池内）
    srcs = [p[0] for p in test_pairs]
    tgts = [p[1] for p in test_pairs]
    gold = list(range(len(test_pairs)))

    torch.manual_seed(SEED)
    model = SentenceTransformer(MODEL_NAME)

    base = retrieval_scores(model, srcs, tgts, gold)
    print(f"[baseline e5] {base}")

    # 训练集（query / positive 标题对，e5 前缀约定）
    train_examples = [InputExample(texts=[f"query: {s}", f"passage: {t}"])
                      for s, t, _ in train_pairs]
    loader = torch.utils.data.DataLoader(train_examples, batch_size=args.batch,
                                         shuffle=True, drop_last=True)
    loss = losses.MultipleNegativesRankingLoss(model)
    warmup = int(len(loader) * args.epochs * 0.1)
    model.fit(
        train_objectives=[(loader, loss)],
        epochs=args.epochs,
        warmup_steps=warmup,
        optimizer_params={"lr": args.lr},
        show_progress_bar=True,
    )

    tuned = retrieval_scores(model, srcs, tgts, gold)
    print(f"[finetuned e5] {tuned}")

    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    ckpt = CKPT_DIR / "e5-align-v1"
    model.save(str(ckpt))

    report = {
        "train_pairs": len(train_pairs), "test_pairs": len(test_pairs),
        "model": MODEL_NAME, "epochs": args.epochs, "batch": args.batch,
        "baseline": base, "finetuned": tuned,
        "gate_R10_ge_0.80": tuned["R@10"] >= 0.80,
        "checkpoint": str(ckpt),
    }
    out = EVAL_DIR / "alignment_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] → {out}")
    print(f"[gate] R@10 {'PASS' if tuned['R@10'] >= 0.80 else 'FAIL'} "
          f"({tuned['R@10']} vs 基线 {base['R@10']})")


if __name__ == "__main__":
    main()
