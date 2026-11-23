#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语料清洗脚本
读取原始语料，完成去重、去噪、语言识别、分词，输出清洗后语料库。

用法：
  python clean_corpus.py
  python clean_corpus.py --input data/corpus_raw.csv --output-dir data/corpus

输出：
  data/corpus/corpus_clean.csv    清洗后元数据+正文
  data/corpus/texts/               每篇报道的清洗文本（.txt）
"""

import os
import sys
import re
import csv
import logging
import argparse

# --------------------------- 日志 ---------------------------
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "clean.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE_DIR, "data")


# --------------------------- 语言识别 ---------------------------
def detect_language(text, fallback="unknown"):
    """
    用 langdetect 识别语言。
    若 langdetect 不可用，根据字符特征粗判。
    """
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        # 粗判：阿拉伯语字符占比
        arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
        total = len(text)
        if total > 0 and arabic_chars / total > 0.3:
            return "ar"
        return fallback


# --------------------------- 文本清洗 ---------------------------
def clean_text(text):
    """
    去除 HTML 残留、多余空白、特殊字符。
    """
    if not text:
        return ""
    # 去 HTML 标签（如有残留）
    text = re.sub(r"<[^>]+>", " ", text)
    # 去 URL
    text = re.sub(r"https?://\S+", " ", text)
    # 去邮件
    text = re.sub(r"\S+@\S+\.\S+", " ", text)
    # 去多余空白
    text = re.sub(r"\s+", " ", text).strip()
    # 去阿拉伯语音标（可选，视需求）
    # text = re.sub(r"[\u064B-\u0652]", "", text)
    return text


def is_valid(text, min_words=50):
    """判断是否为有效全文。"""
    if not text:
        return False
    words = text.split()
    if len(words) < min_words:
        return False
    # 排除明显是导航/菜单的文本
    noise_markers = ["subscribe", "sign up", "log in", "read more", "advertisement"]
    lower = text.lower()
    if any(m in lower for m in noise_markers) and len(words) < 120:
        return False
    return True


# --------------------------- 去重 ---------------------------
def deduplicate(rows):
    """
    基于标题+正文前200字符去重。
    """
    seen = set()
    unique = []
    for row in rows:
        title = (row.get("title") or "").lower().strip()
        text = (row.get("text") or "")
        key = (title, text[:200])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    logger.info(f"去重：{len(rows)} -> {len(unique)}")
    return unique


# --------------------------- 生成文档 ID ---------------------------
def generate_doc_id(row, existing_ids):
    """
    生成 doc_id：品牌_语言_序号
    """
    brand = (row.get("brand") or "UNK").upper().replace(" ", "")
    lang = (row.get("language") or "UNK")
    if lang.lower().startswith("ar"):
        lang_code = "AR"
    elif lang.lower().startswith("en"):
        lang_code = "EN"
    else:
        lang_code = "OT"

    prefix = f"{brand}_{lang_code}_"
    # 查找最大序号
    max_n = 0
    for eid in existing_ids:
        if eid.startswith(prefix):
            try:
                n = int(eid.split("_")[-1])
                if n > max_n:
                    max_n = n
            except ValueError:
                pass
    new_id = f"{prefix}{max_n + 1:03d}"
    return new_id


# --------------------------- 主流程 ---------------------------
def run_clean(input_path, output_dir, min_words=50):
    os.makedirs(output_dir, exist_ok=True)
    text_dir = os.path.join(output_dir, "texts")
    os.makedirs(text_dir, exist_ok=True)

    logger.info(f"读取原始语料: {input_path}")

    # 读取原始数据
    rows = []
    with open(input_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    logger.info(f"原始条数: {len(rows)}")

    # 去重
    rows = deduplicate(rows)

    # 清洗与校验
    cleaned = []
    existing_ids = set()
    for row in rows:
        text = clean_text(row.get("text", ""))
        if not is_valid(text, min_words=min_words):
            continue

        # 语言识别
        detected = detect_language(text, fallback=row.get("language", "unknown"))

        # 文档 ID
        doc_id = generate_doc_id(row, existing_ids)
        existing_ids.add(doc_id)

        cleaned.append({
            "doc_id": doc_id,
            "brand": row.get("brand", ""),
            "media": row.get("media", ""),
            "source_tier": row.get("source_tier", ""),
            "country": row.get("country", ""),
            "language": detected,
            "date": row.get("date", ""),
            "url": row.get("url", ""),
            "title": clean_text(row.get("title", "")),
            "word_count": len(text.split()),
            "text_clean": text,
        })

        # 保存单篇文本
        with open(os.path.join(text_dir, f"{doc_id}.txt"), "w", encoding="utf-8") as f:
            f.write(text)

    logger.info(f"有效条数: {len(cleaned)}")

    # 保存清洗后 CSV
    output_path = os.path.join(output_dir, "corpus_clean.csv")
    if cleaned:
        fieldnames = list(cleaned[0].keys())
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(cleaned)
        logger.info(f"已保存清洗后语料: {output_path}")

        # 统计报告
        from collections import Counter
        brand_counts = Counter(r["brand"] for r in cleaned)
        lang_counts = Counter(r["language"] for r in cleaned)
        tier_counts = Counter(r["source_tier"] for r in cleaned)

        report_lines = [
            "# 语料清洗报告",
            "",
            f"- 原始条数: {len(rows)}",
            f"- 有效条数: {len(cleaned)}",
            f"- 输出目录: {output_dir}",
            "",
            "## 品牌分布",
            "",
        ]
        for b, c in brand_counts.most_common():
            report_lines.append(f"- {b}: {c}")
        report_lines += ["", "## 语言分布", ""]
        for l, c in lang_counts.most_common():
            report_lines.append(f"- {l}: {c}")
        report_lines += ["", "## 媒体层级分布", ""]
        for t, c in tier_counts.most_common():
            report_lines.append(f"- {t}: {c}")

        report_path = os.path.join(output_dir, "清洗报告.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))
        logger.info(f"清洗报告已保存: {report_path}")
    else:
        logger.warning("无有效数据")


def main():
    parser = argparse.ArgumentParser(description="语料清洗脚本")
    parser.add_argument("--input", default=os.path.join(DATA_DIR, "corpus_raw.csv"),
                        help="原始语料 CSV 路径")
    parser.add_argument("--output-dir", default=os.path.join(DATA_DIR, "corpus"),
                        help="输出目录")
    parser.add_argument("--min-words", type=int, default=50,
                        help="有效全文最小词数")
    args = parser.parse_args()

    run_clean(args.input, args.output_dir, args.min_words)


if __name__ == "__main__":
    main()
