# -*- coding: utf-8 -*-
"""
check_exports.py — 标注导出检查与验收入口
============================================
扫描 annotation/data/ 下的 Label Studio 导出文件，自动完成：
  1. 缺失提醒（0 / 1 份时的友好提示）
  2. 字段完整性校验
  3. 调用 kappa.py 计算 Cohen's κ
  4. κ≥0.78 时调用 diff_queue.py + split_gold.py 生成仲裁队列与训练/验证/测试集
  5. 调用 llm_vs_gold.py 计算 LLM-vs-human Macro-F1
  6. 输出 human-readable readiness report

用法：
    python annotation/data/check_exports.py
"""
from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# 保证在 Windows 等默认编码非 UTF-8 的终端上中文正常输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ---------- 路径常量 ----------
ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "annotation" / "data"
AGREEMENT_DIR = ROOT / "annotation" / "agreement"
KAPPA_REPORT = AGREEMENT_DIR / "kappa_report.json"
LLM_REPORT = DATA_DIR / "llm_vs_gold_report.json"

# ---------- 字段口径 ----------
# 任务要求的“规范名” → Label Studio 配置里可能出现的 from_name（按优先级匹配）
REQUIRED_FIELDS = {
    "sentiment": ["sentiment_5scale", "sentiment"],
    "aspect": ["aspect_category", "aspect"],
    "stance": ["primary_frame", "stance"],
    "brand_role": ["role_type", "brand_role"],
}
OPTIONAL_FIELDS = {
    "gulf_dialect": ["gulf_dialect", "dialect", "lang_variant"],
}
EXTRA_FIELDS = {
    "referent_level": ["referent_level"],
    "primary_frame": ["primary_frame"],
    "misreading_type": ["misreading_type"],
    "brand_matrix": ["brand_matrix"],
    "secondary_frame": ["secondary_frame"],
}
ALL_CANONICAL = {**REQUIRED_FIELDS, **OPTIONAL_FIELDS, **EXTRA_FIELDS}

KAPPA_GATE = 0.78


def discover_exports() -> list[Path]:
    """找出所有疑似人工导出的 JSON 文件。"""
    files: list[Path] = []
    if DATA_DIR.exists():
        files.extend(DATA_DIR.glob("ann_*.json"))
        files.extend(DATA_DIR.glob("export.json"))
    # 去重并保持稳定顺序
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in sorted(files, key=lambda x: x.name.lower()):
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def annotator_name(path: Path) -> str:
    """从文件名提取标注员名字。"""
    name = path.stem
    if name.lower().startswith("ann_"):
        return name[4:]
    return name


def load_ls_labels(path: Path) -> dict[str, dict[str, str]]:
    """解析 LS 导出 JSON → {doc_id: {field: value}}。"""
    text = path.read_text(encoding="utf-8-sig")
    out: dict[str, dict[str, str]] = {}
    data = json.loads(text)
    if not isinstance(data, list):
        return out
    for item in data:
        d = item.get("data") or {}
        cid = d.get("doc_id") or d.get("calib_id") or str(item.get("id"))
        labels: dict[str, str] = {}
        for ann in item.get("annotations", []) or []:
            for res in ann.get("result", []) or []:
                name = res.get("from_name")
                val = res.get("value")
                if not name or val is None:
                    continue
                if isinstance(val, dict):
                    v = (val.get("choice") or val.get("choices")
                         or val.get("labels") or val.get("text") or val.get(name))
                    labels[name] = "|".join(sorted(map(str, v))) if isinstance(v, list) else str(v)
                elif isinstance(val, list):
                    labels[name] = "|".join(sorted(map(str, val)))
                else:
                    labels[name] = str(val)
        out[str(cid)] = labels
    return out


def resolve_field(labels: dict[str, str], canonical: str) -> str | None:
    """按别名表找某个规范字段的实际值。"""
    for key in ALL_CANONICAL.get(canonical, [canonical]):
        if key in labels and labels[key].strip():
            return labels[key]
    return None


def field_completeness(records: dict[str, dict[str, str]]) -> dict[str, int]:
    """统计每个规范字段有值的记录数。"""
    n = len(records)
    counts: dict[str, int] = {"_records": n}
    for canonical in list(REQUIRED_FIELDS) + list(OPTIONAL_FIELDS) + list(EXTRA_FIELDS):
        counts[canonical] = sum(
            1 for labels in records.values() if resolve_field(labels, canonical) is not None
        )
    return counts


def run_script(script: Path, args: list[str]) -> subprocess.CompletedProcess | None:
    """安全调用项目脚本，失败不抛异常。"""
    cmd = [sys.executable, str(script), *args]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        return subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False, env=env
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  [错误] 调用失败 {script.name}: {exc}")
        return None


def parse_kappa_report() -> dict[str, Any]:
    if not KAPPA_REPORT.exists():
        return {}
    try:
        return json.loads(KAPPA_REPORT.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def parse_llm_report() -> dict[str, Any]:
    if not LLM_REPORT.exists():
        return {}
    try:
        return json.loads(LLM_REPORT.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with open(path, encoding="utf-8-sig") as f:
            return max(0, sum(1 for _ in csv.reader(f)) - 1)
    except Exception:  # noqa: BLE001
        return 0


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except Exception:  # noqa: BLE001
        return 0


def print_file_summary(path: Path) -> None:
    records = load_ls_labels(path)
    counts = field_completeness(records)
    name = annotator_name(path)
    print(f"\n  [文件] {path.name}（标注员：{name}）")
    print(f"     记录数：{counts['_records']}")
    print("     必填字段完整率：")
    for field in REQUIRED_FIELDS:
        c = counts.get(field, 0)
        pct = f"{c / max(counts['_records'], 1):.0%}" if counts["_records"] else "N/A"
        print(f"       - {field}: {c}/{counts['_records']} ({pct})")
    print("     建议字段完整率：")
    for field in list(OPTIONAL_FIELDS) + list(EXTRA_FIELDS):
        c = counts.get(field, 0)
        pct = f"{c / max(counts['_records'], 1):.0%}" if counts["_records"] else "N/A"
        print(f"       - {field}: {c}/{counts['_records']} ({pct})")


def run_pipeline(paths: list[Path]) -> dict[str, Any]:
    """执行 κ / 仲裁 / 切分 / F1 流水线。"""
    a, b = paths[0], paths[1]
    results: dict[str, Any] = {"kappa": None, "f1": None, "splits": {}, "arbitration": 0}

    # 1) Cohen's κ
    print("\n[2/4] 计算双人标注一致性（Cohen's κ）...")
    kappa_proc = run_script(AGREEMENT_DIR / "kappa.py", [str(a), str(b)])
    if kappa_proc:
        print(kappa_proc.stdout)
        if kappa_proc.stderr:
            print(kappa_proc.stderr)
    kappa_data = parse_kappa_report()
    results["kappa"] = kappa_data

    # 2) 分歧队列 + 切分（仅当 κ 过门禁）
    field_report = kappa_data.get("fields", {})
    core_kappas = [v["kappa"] for v in field_report.values()
                   if isinstance(v, dict) and "kappa" in v]
    overall_kappa = round(sum(core_kappas) / len(core_kappas), 4) if core_kappas else 0.0
    results["overall_kappa"] = overall_kappa

    if overall_kappa >= KAPPA_GATE:
        print(f"\n[3/4] κ={overall_kappa:.3f} ≥ {KAPPA_GATE}，生成仲裁队列与数据集拆分...")
        dq = run_script(AGREEMENT_DIR / "diff_queue.py", [str(a), str(b)])
        if dq:
            print(dq.stdout)
        results["arbitration"] = count_csv_rows(DATA_DIR / "arbitration_queue.csv")

        sg = run_script(AGREEMENT_DIR / "split_gold.py", ["--gold", str(a), str(b)])
        if sg:
            print(sg.stdout)
        results["splits"] = {
            "train": count_jsonl(DATA_DIR / "split_few_shot.jsonl"),
            "dev": count_jsonl(DATA_DIR / "split_dev.jsonl"),
            "test": count_jsonl(DATA_DIR / "split_test.jsonl"),
        }
    else:
        print(f"\n[3/4] κ={overall_kappa:.3f} < {KAPPA_GATE}，暂不生成分歧队列与拆分。")
        # 即使没过门禁也生成 diff_queue 供队长审阅，但不切分
        dq = run_script(AGREEMENT_DIR / "diff_queue.py", [str(a), str(b)])
        if dq:
            print(dq.stdout)
        results["arbitration"] = count_csv_rows(DATA_DIR / "arbitration_queue.csv")

    # 3) LLM vs Gold F1
    print("\n[4/4] 计算 LLM 银标准 vs 人工金标准 Macro-F1...")
    f1_proc = run_script(AGREEMENT_DIR / "llm_vs_gold.py", ["--gold", str(a), str(b)])
    if f1_proc:
        print(f1_proc.stdout)
        if f1_proc.stderr:
            print(f1_proc.stderr)
    results["f1"] = parse_llm_report()

    return results


def print_readiness_report(results: dict[str, Any], paths: list[Path]) -> None:
    print("\n" + "=" * 60)
    print("[报告] 标注 readiness report")
    print("=" * 60)

    kappa_data = results.get("kappa") or {}
    field_report = kappa_data.get("fields", {})
    overall = results.get("overall_kappa", 0.0)
    print(f"\n[一致性] 双人一致性（Cohen's κ）")
    print(f"   共同样本数：{kappa_data.get('samples', 'N/A')}")
    print(f"   总体 κ（字段均值）：{overall:.3f}  门禁：≥{KAPPA_GATE}")
    if field_report:
        print("   各字段 κ：")
        for field, info in sorted(field_report.items()):
            if isinstance(info, dict) and "kappa" in info:
                gate = info.get("gate")
                gate_s = f" 门禁≥{gate:.2f}" if gate is not None else ""
                print(f"     - {field}: κ={info['kappa']:.3f}{gate_s}")
    else:
        print("   （未生成字段级 κ 报告，请检查两份导出是否有共同 doc_id）")

    f1_data = results.get("f1") or {}
    print(f"\n[F1] LLM-vs-human Macro-F1")
    print(f"   银标文件：{f1_data.get('silver_file', 'N/A')}")
    print(f"   交集样本：{f1_data.get('n_common', 'N/A')}")
    print(f"   核心字段 Macro-F1：{f1_data.get('macro_f1_core', 'N/A')}")
    print(f"   门禁：≥{f1_data.get('gate', 0.80)}")

    splits = results.get("splits", {})
    if splits:
        print(f"\n[拆分] 金标准拆分（6:2:2）")
        print(f"   train / few_shot: {splits.get('train', 0)} 条")
        print(f"   dev:              {splits.get('dev', 0)} 条")
        print(f"   test:             {splits.get('test', 0)} 条")
    else:
        print("\n[拆分] 金标准拆分：尚未生成（κ 未达门禁）")

    print(f"\n[仲裁] 仍需仲裁的分歧数：{results.get('arbitration', 0)} 处")

    if overall >= KAPPA_GATE:
        print("\n[通过] 结论：一致性 κ 已达标，可进入金标准阶段。")
        print("   下一步：队长审阅 arbitration_queue.csv，必要时补充仲裁，")
        print("   然后运行 diff_queue.py --apply 生成 gold_final.jsonl。")
    else:
        print("\n[未通过] 结论：一致性 κ 未达门禁，当前不能进入金标准阶段。")
        print("   建议：修订 annotation/guidelines/标注入门指南.md → 定向重标校准集，")
        print("   重跑导出后再执行本脚本。")

    print("\n" + "=" * 60)


def main() -> int:
    print("=" * 60)
    print("GreenSilk 标注导出检查与验收")
    print("=" * 60)

    paths = discover_exports()

    if not paths:
        print("\n尚未收到标注员 JSON，请提醒标注员导出。")
        print("导出步骤：Label Studio → 项目 → Export → JSON，")
        print("文件名保存为 annotation/data/ann_名字.json")
        return 0

    print(f"\n[1/4] 发现 {len(paths)} 份导出文件：")
    for p in paths:
        print(f"   - {p.name}")

    if len(paths) == 1:
        received = annotator_name(paths[0])
        print_file_summary(paths[0])
        print(f"\n[注意] 仅收到标注员「{received}」的导出，另一位标注员尚未提交。")
        print("请提醒另一位尽快导出并发送。")
        return 0

    # 两份及以上：以排序后的前两份为准
    if len(paths) > 2:
        print(f"\n注：发现 {len(paths)} 份导出，本次验收取前两份（按文件名排序）：")
        print(f"   {paths[0].name} 与 {paths[1].name}")

    for p in paths[:2]:
        print_file_summary(p)

    results = run_pipeline(paths[:2])
    print_readiness_report(results, paths[:2])
    return 0


if __name__ == "__main__":
    sys.exit(main())
