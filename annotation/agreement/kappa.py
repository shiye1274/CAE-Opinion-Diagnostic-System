# -*- coding: utf-8 -*-
"""
kappa.py —— 双人标注一致性（Cohen's Kappa）计算与门禁判定
==========================================================
输入：两名标注员的导出文件（Label Studio JSON 导出 或 标准 CSV）
对齐键：data.calib_id（JSON）或首列（CSV）
输出：每字段 κ 值 + 是否过门禁（主框架/情感 ≥0.78，误读 ≥0.72）

用法：
  python kappa.py ann1.json ann2.json
  python kappa.py ann1.csv ann2.csv
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

# 门禁阈值（规划文档表 4-2）
GATES = {
    "primary_frame": 0.78, "sentiment_5scale": 0.78,
    "misreading_type": 0.72, "referent_level": 0.75,
    "role_type": 0.75, "aspect_category": 0.70,
    "secondary_frame": 0.70, "brand_matrix": 0.70,
}

MULTI_FIELDS = {"brand_matrix", "aspect_category"}   # 多选字段按集合算 κ


def load_labels(path: Path) -> dict[str, dict[str, str]]:
    """→ {calib_id: {field: label}}"""
    text = path.read_text(encoding="utf-8-sig")
    out: dict[str, dict[str, str]] = {}
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        for item in data:
            d = item.get("data") or {}
            cid = d.get("calib_id") or d.get("doc_id") or str(item.get("id"))
            labels: dict[str, str] = {}
            for ann in item.get("annotations", []) or []:
                for res in ann.get("result", []):
                    name, val = res.get("from_name"), res.get("value")
                    if not name or val is None:
                        continue
                    if isinstance(val, dict):
                        # LS 导出结构：Choices={"choice":...} / {"choices":[...]} /
                        # TextArea={"text":[...]} / Labels={"labels":[...]}
                        v = (val.get("choice") or val.get("choices")
                             or val.get("labels") or val.get("text") or val.get(name))
                        labels[name] = "|".join(sorted(map(str, v))) if isinstance(v, list) else str(v)
                    elif isinstance(val, list):
                        labels[name] = "|".join(sorted(map(str, val)))
                    else:
                        labels[name] = str(val)
            out[cid] = labels
    else:
        reader = csv.DictReader(text.splitlines())
        for i, row in enumerate(reader, 1):
            cid = row.get("calib_id") or row.get("doc_id") or next(iter(row.values()))
            out[str(cid)] = {k: (v or "").strip() for k, v in row.items() if v and k not in
                             ("calib_id", "doc_id", "language", "lang_variant", "country",
                              "title", "annotator_1", "annotator_2", "agreement", "arbiter")}
    return out


def kappa(pairs: list[tuple[str, str]]) -> float:
    """Cohen's kappa；多选集合视为同一标签字符串。"""
    n = len(pairs)
    if n == 0:
        return float("nan")
    observed = sum(1 for a, b in pairs if a == b) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    if abs(1 - expected) < 1e-9:
        return 1.0 if observed >= 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    a = load_labels(Path(sys.argv[1]))
    b = load_labels(Path(sys.argv[2]))
    common = sorted(set(a) & set(b))
    only_a, only_b = len(set(a) - set(b)), len(set(b) - set(a))
    print(f"[对齐] 共同样本 {len(common)} | 仅标注员1 有 {only_a} | 仅标注员2 有 {only_b}")
    if not common:
        print("无交集，检查导出文件的 calib_id")
        sys.exit(2)

    fields = sorted({f for cid in common for f in set(a[cid]) | set(b[cid])})
    report: dict[str, dict] = {}
    print(f"\n{'字段':<24}{'κ':>8}{'门禁':>8}  {'结果'}")
    print("-" * 56)
    all_pass = True
    for f in fields:
        pairs = [(a[cid].get(f, ""), b[cid].get(f, "")) for cid in common
                 if f in a[cid] and f in b[cid]]
        if len(pairs) < 10:
            continue
        k = kappa(pairs)
        gate = GATES.get(f)
        ok = gate is None or k >= gate
        all_pass &= ok
        gate_s = f"{gate:.2f}" if gate else "—"
        print(f"{f:<24}{k:>8.3f}{gate_s:>8}  {'✅' if ok else '❌'}")
        report[f] = {"kappa": round(k, 4), "n": len(pairs), "gate": gate, "pass": ok}

    verdict = "通过门禁，可进入金标准阶段" if all_pass else "未全部达标 → 修订手册 v2.1 后重标校准集"
    print(f"\n[结论] {verdict}")
    out = Path(__file__).resolve().parent / "kappa_report.json"
    out.write_text(json.dumps({"samples": len(common), "fields": report,
                               "all_pass": all_pass}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"[报告] {out}")


if __name__ == "__main__":
    main()
