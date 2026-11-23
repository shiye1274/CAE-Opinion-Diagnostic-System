# -*- coding: utf-8 -*-
"""
annotate.py —— LLM-as-Annotator 双模型交叉标注流水线（银标准）
===============================================================
机制（规划表 4-2）：
  每条样本 → 模型A(qwen-plus) 与 模型B(deepseek-v4-flash) 独立标注
  → 字段一致性 + 自报置信度 → 双模型一致且置信 ≥0.85 自动入库 LLM_SILVER
  → 任何核心字段分歧 → review_needed=True 回流人工仲裁

用法：
  python annotate.py --limit 30               # 试点 30 条
  python annotate.py --input xxx.json         # 自定义输入（LS 格式或 {items:[...]}）
  python annotate.py --workers 4

输入默认：corpus/processed/calibration_set.json（与人工标注同一批 → 事后可算
LLM vs 人工 的 Macro-F1 = 规划门禁 ≥0.80 的检验）
输出：annotation/data/silver_{ts}.jsonl（canonical schema，见 annotation/schema/）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ANNOTATOR_DIR = Path(__file__).resolve().parents[1]        # annotation/
PROJECT_ROOT = ANNOTATOR_DIR.parent
DATA_DIR = ANNOTATOR_DIR / "data"

# 载入 annotation/.env
for _line in (ANNOTATOR_DIR / ".env").read_text(encoding="utf-8").splitlines():
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        k, v = _line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

API_BASE = os.environ.get("LLM_API_BASE", "").rstrip("/")
API_KEY = os.environ.get("LLM_API_KEY", "")
MODEL_A = os.environ.get("LLM_MODEL_A", "qwen-plus")
MODEL_B = os.environ.get("LLM_MODEL_B", "deepseek-v4-flash-0731")

PROMPTS = json.loads(json.dumps(
    __import__("yaml").safe_load(
        (Path(__file__).parent / "prompts.yaml").read_text(encoding="utf-8"))))

# 核心字段（分歧→回流人工的判定依据）与全部字段（一致性统计）
CORE_FIELDS = ["primary_frame", "sentiment_5scale", "misreading_type"]
ALL_FIELDS = ["brand_matrix", "role_type", "referent_level", "primary_frame",
              "sentiment_5scale", "aspect_category", "misreading_type"]

# canonical 代码集（纯代码，无中文尾巴）
CODE_SETS = {
    "role_type": {"CORE_SUBJECT", "BENCHMARK", "PASSING_MENTION", "NOT_APPLICABLE"},
    "referent_level": {"CORPORATE", "PRODUCT_BRAND", "SPECIFIC_MODEL", "INDUSTRY_CHAIN",
                       "FINANCIAL", "INFRASTRUCTURE", "MIXED", "OTHER"},
    "primary_frame": {"TECH_LEADERSHIP", "PRICE_ADVANTAGE", "SAFETY_RECALL", "AFTER_SALES",
                      "ENVIRONMENTAL", "POLICY_GEO", "CULTURAL_CONFLICT",
                      "MARKET_COMPETITION", "LOCALIZATION_INVEST", "LUXURY_STATUS", "OTHER"},
    "sentiment_5scale": {"+2", "+1", "0", "-1", "-2"},
    "aspect_category": {"BATTERY_RANGE", "THERMAL_AC", "SMART_CABIN", "AUTONOMOUS_DRIVING",
                        "EXTERIOR_SPACE", "PRICE_FINANCE", "RESALE_VALUE", "CHARGING_NET",
                        "DEALER_SERVICE", "SAFETY_QUALITY", "DATA_PRIVACY", "BRAND_PRESTIGE",
                        "CLIMATE_GEO", "RELIGION_CUSTOM", "GEO_ECONOMIC", "无"},
    "misreading_type": {"FACTUAL_ERROR", "CONTEXT_MISPLACEMENT", "STEREOTYPICAL_ATTRIBUTION",
                        "KEY_CONTEXT_OMISSION", "NO_MISREADING", "CANNOT_DETERMINE"},
}

import requests  # noqa: E402

H = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def call_model(model: str, item: dict, retries: int = 3) -> dict:
    """单模型标注 → 解析后的 dict（含 confidence）。"""
    user = (f"标题: {(item.get('title') or '').strip()}\n"
            f"语言: {item.get('language') or '未知'}\n"
            f"正文:\n{(item.get('text_clean') or '').strip()[:1500]}")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": PROMPTS["system"]},
            *PROMPTS.get("few_shot", []),
            {"role": "user", "content": user},
        ],
        "temperature": 0,       # 稳定性优先（两次试点间一致率波动大）
        "max_tokens": 2000,     # 推理系模型会先输出思考过程，800 会截断 JSON
    }
    last_err = ""
    for attempt in range(retries):
        try:
            r = requests.post(f"{API_BASE}/chat/completions", headers=H,
                              timeout=90, json=payload)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                last_err = "429 rate_limited"
                continue
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}: {r.text[:150]}"
                time.sleep(3 * (attempt + 1))
                continue
            data = r.json()
            msg = data["choices"][0]["message"]
            content = (msg.get("content") or "").strip()
            if not content:   # 推理系模型可能把正文放 reasoning_content
                content = (msg.get("reasoning_content") or "").strip()
            if not content:
                last_err = "empty_content"
                time.sleep(2)
                continue
            parsed = parse_json(content)
            if parsed.get("_error"):
                last_err = f"json_parse_failed: {content[:150]}"
                # 强制追问一次：推理系模型先思考后补 JSON（或被截断）
                try:
                    payload2 = dict(payload)
                    payload2["messages"] = payload["messages"] + [
                        {"role": "assistant", "content": content[:3000]},
                        {"role": "user",
                         "content": "只输出最终 JSON 对象本身，禁止任何解释、思考过程或代码块标记。"},
                    ]
                    r2 = requests.post(f"{API_BASE}/chat/completions", headers=H,
                                       timeout=90, json=payload2)
                    if r2.status_code == 200:
                        m2 = r2.json()["choices"][0]["message"]
                        c2 = (m2.get("content") or m2.get("reasoning_content") or "").strip()
                        parsed2 = parse_json(c2)
                        if not parsed2.get("_error"):
                            return parsed2
                except Exception as e:  # noqa: BLE001
                    last_err = f"reask_failed: {str(e)[:80]}"
                time.sleep(2)
                continue
            return parsed
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {str(e)[:120]}"
            time.sleep(3 * (attempt + 1))
    return {"_error": True, "_reason": last_err or "unknown", "confidence": 0.0}


def parse_json(content: str) -> dict:
    """稳健解析：剥代码块、截取首个平衡花括号块。"""
    c = content.strip()
    c = re.sub(r"^```(?:json)?\s*|\s*```$", "", c, flags=re.S)
    start, end = c.find("{"), c.rfind("}")
    if start >= 0 and end > start:
        c = c[start:end + 1]
    try:
        return json.loads(c)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", c, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {"_error": True, "confidence": 0.0}


def canon(field: str, value) -> list | str | None:
    """模型输出（可能带中文尾巴）→ canonical 代码。"""
    allowed = CODE_SETS.get(field)
    if value is None:
        return None if field != "aspect_category" else ["无"]
    if field in ("brand_matrix",):
        return value if isinstance(value, list) else [str(value)]
    if field == "aspect_category":
        items = value if isinstance(value, list) else [value]
        out = []
        for v in items:
            head = str(v).strip().split()[0] if str(v).strip() else ""
            head = head.strip("|")
            out.append(head if head in allowed else str(v).strip())
        return out or ["无"]
    head = str(value).strip().split()[0] if str(value).strip() else ""
    return head if head in allowed else str(value).strip()


def norm_anno(d: dict) -> dict:
    out = {}
    for f in ALL_FIELDS:
        out[f] = canon(f, d.get(f))
    out["misreading_evidence"] = d.get("misreading_evidence")
    out["confidence_self"] = float(d.get("confidence") or 0.0)
    return out


def field_equal(f: str, a, b) -> bool:
    if f == "aspect_category":
        return set(a or []) == set(b or [])
    if f == "brand_matrix":
        return set(a or []) == set(b or [])
    return a == b


def process_item(item: dict) -> dict:
    ra = call_model(MODEL_A, item)
    rb = call_model(MODEL_B, item)
    a = norm_anno(ra) if not ra.get("_error") else None
    b = norm_anno(rb) if not rb.get("_error") else None
    if a is None or b is None:
        return {"ok": False, "doc_id": item.get("doc_id"),
                "error": f"A:{ra.get('_reason', '-')} | B:{rb.get('_reason', '-')}"}

    agrees = {f: field_equal(f, a.get(f), b.get(f)) for f in ALL_FIELDS}
    core_ok = all(agrees[f] for f in CORE_FIELDS)
    agree_rate = round(sum(agrees.values()) / len(agrees), 3)
    self_conf = round((a["confidence_self"] + b["confidence_self"]) / 2, 3)
    confidence = round(self_conf * (0.5 + 0.5 * agree_rate), 3)   # 一致率折算
    accept = core_ok and self_conf >= 0.85

    annotations = {"model_a": a, "model_b": b}
    if accept:
        annotations["final"] = {k: a[k] for k in ALL_FIELDS}
        annotations["final"]["misreading_evidence"] = (
            a.get("misreading_evidence") or b.get("misreading_evidence"))

    return {
        "ok": True,
        "doc_id": item.get("doc_id"),
        "record": {
            "doc_id": item.get("doc_id"),
            "text": (item.get("text_clean") or "")[:2000],
            "metadata": {
                "language": item.get("language"),
                "lang_variant": item.get("lang_variant"),
                "country": item.get("country"),
                "title": item.get("title"),
                "calib_id": item.get("calib_id"),
            },
            "annotations": annotations,
            "annotation_meta": {
                "annotator_source": "LLM_SILVER",
                "round": "silver",
                "model": f"{MODEL_A}+{MODEL_B}",
                "confidence": confidence,
                "field_agreement": agree_rate,
                "field_agrees": agrees,
                "accepted": accept,
                "review_needed": not accept,
                "annotated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(PROJECT_ROOT / "corpus" / "processed" / "calibration_set.json"))
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("items", [])
    items = [it.get("data", it) for it in items]
    items = [it for it in items if (it.get("text_clean") or "").strip()][: args.limit]
    print(f"[input] {len(items)} 条（{Path(args.input).name}）")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = DATA_DIR / f"silver_{ts}.jsonl"

    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(process_item, it): it for it in items}
        done = 0
        for fut in as_completed(futs):
            results.append(fut.result())
            done += 1
            if done % 10 == 0:
                print(f"  {done}/{len(items)}")

    ok = [r for r in results if r["ok"]]
    fails = [r for r in results if not r["ok"]]
    fail_reasons: dict[str, int] = {}
    for r in fails:                       # 失败原因分桶（诊断用）
        key = str(r.get("error", ""))[:60]
        fail_reasons[key] = fail_reasons.get(key, 0) + 1
    with open(out_path, "w", encoding="utf-8") as f:
        for r in ok:
            f.write(json.dumps(r["record"], ensure_ascii=False) + "\n")

    # 统计
    n = len(ok)
    stats = {"items": len(items), "ok": n, "failed": len(results) - n,
             "fail_reasons": fail_reasons,
             "model_a": MODEL_A, "model_b": MODEL_B, "elapsed_sec": round(time.time() - t0, 1)}
    if n:
        stats["field_agreement_mean"] = round(sum(
            r["record"]["annotation_meta"]["field_agreement"] for r in ok) / n, 4)
        stats["confidence_mean"] = round(sum(
            r["record"]["annotation_meta"]["confidence"] for r in ok) / n, 4)
        stats["accepted_silver"] = sum(
            1 for r in ok if r["record"]["annotation_meta"]["accepted"])
        stats["acceptance_rate"] = round(stats["accepted_silver"] / n, 4)
        stats["review_needed"] = n - stats["accepted_silver"]
        for f_ in ALL_FIELDS:
            stats[f"agree_{f_}"] = round(sum(
                1 for r in ok if r["record"]["annotation_meta"]["field_agrees"][f_]) / n, 4)
        stats["plan_gate_auto_accept_ge_0.85_conf"] = stats.get("field_agreement_mean", 0) >= 0.5

    report_path = DATA_DIR / f"silver_report_{ts}.json"
    report_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"[out] {out_path}")
    print(f"[report] {report_path}")


if __name__ == "__main__":
    main()
