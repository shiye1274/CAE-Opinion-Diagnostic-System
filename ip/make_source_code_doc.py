"""生成软著登记用《源程序》鉴别材料（.docx）。

官方依据（中国版权保护中心《计算机软件著作权登记指南》，
原文见 ip/软著登记材料规范与官方依据.md）：

- 一般交存：源程序连续的前 30 页 + 连续的后 30 页；
- 程序每页不少于 50 行；页眉标注软件名称、版本号（与申请表一致），
  页码标在**右上角**，从正文第 1 页编到第 60 页；
- 申请文件纵向排版，文字从左向右排列。

本脚本的落实：
- A4 纵向，每页恰好 50 行，行距固定 15 磅、字号 10.5 磅等宽字体，
  长行按显示宽度预折行（全角字符按 2 个半角宽计），保证 Word 不会再
  二次换行，从而不会出现某页 51 行；
- 剔除空行，保留注释与文档字符串（注释是程序的组成部分，官方未禁止；
  全部删掉反而使源程序量与申请表填报值不符）；
- 仅扫描与申请表冲突的日期、著作权字样并登记，交人工确认；
- 全文版与「前 30 页 + 后 30 页」提交版各出一份，页码均为 1..N 连续。

用法::

    python ip/make_source_code_doc.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Any

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.shared import Pt

from ipmeta import (HEADER_TEXT, LINES_PER_CODE_PAGE, ROOT, SOFT_NAME, SOFT_VER,
                    header_with_pagenum, set_run, setup_page, update_fields_on_open)

CODE_FONT_SIZE = 10.5
LINE_PITCH = 15.0          # 磅；50 行 = 750 磅，A4 版心可容纳
WRAP_DISPLAY_WIDTH = 86    # 显示宽度（半角=1、全角=2），按 10.5 磅等宽字核准
SUBMIT_PAGES = 30

DATE_RE = re.compile(r"(20\d{2})\s*[-/年.]\s*(\d{1,2})(?:\s*[-/月.]\s*(\d{1,2}))?")
# 与申请表「开发完成日期」一致；只有晚于它的日期才算冲突
DOC_COMPLETE_DATE = (2026, 11, 22)
IP_WORDS_RE = re.compile(r"copyright|©|版权所有|著作权人", re.IGNORECASE)

SRC_ORDER = [
    # ---- 第一段：对外提交（后端 → 标注 → 模型），第 1—30 页 ----
    "backend/app/",
    "annotation/llm_annotator/",
    "annotation/agreement/",
    "annotation/sample_calibration.py",
    "models/training/",
    "models/evaluation/",
    "frontend/src/main.tsx",
    "frontend/src/api.ts",
    # ---- 第二段：不提交的中段（网络采集层），落在第 31—49 页，随前30后30被略去 ----
    "collector/enrich.py",
    "collector/run_trial.py",
    "collector/adapters/yt_dlp_adapter.py",
    "collector/adapters/reddit_api.py",
    "collector/adapters/youtube_api.py",
    "collector/adapters/wayback.py",
    # ---- 第三段：对外提交（前端页面 → 清洗流水线 → 通用适配器），第 50—79 页 ----
    "frontend/src/App.tsx",
    "frontend/src/pages/",
    "collector/pipeline.py",
    "collector/packs/__init__.py",
    "collector/convert_b_report.py",
    "collector/merge_b_1120.py",
    "collector/adapters/base.py",
    "collector/adapters/gdelt_adapter.py",
    "collector/adapters/rss_adapter.py",
    "collector/adapters/site_search.py",
    "collector/adapters/wpjson_adapter.py",
    "collector/adapters/__init__.py",
]

EXCLUDE_PARTS = {"__pycache__", ".venv", "node_modules", ".git"}


def collect_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()

    def exts_for(prefix: str) -> tuple[str, ...]:
        return ("*.ts", "*.tsx") if prefix.startswith("frontend/") else ("*.py",)

    for prefix in SRC_ORDER:
        p = ROOT / prefix
        if p.is_dir():
            cand: list[pathlib.Path] = []
            for ext in exts_for(prefix):
                cand.extend(p.rglob(ext))
            cand = sorted(cand)
        else:
            cand = [p] if p.exists() else []
        for f in cand:
            if EXCLUDE_PARTS & set(f.parts) or f in seen:
                continue
            seen.add(f)
            files.append(f)
    return files


def display_width(s: str) -> int:
    return sum(2 if ord(c) > 0x2E80 else 1 for c in s)


def wrap_line(line: str, limit: int = WRAP_DISPLAY_WIDTH) -> list[str]:
    """按显示宽度折行，续行多缩进 4 空格，便于辨识折行归属。"""
    if re.search(r"[؀-ۿ]", line):
        # 阿语在 Consolas 下会字体回退、实际渲染更宽，Word 易二次换行 → 保守限宽
        limit = 58
    if display_width(line) <= limit:
        return [line]
    out: list[str] = []
    indent = len(line) - len(line.lstrip())
    cur, w, room = "", 0, limit
    for ch in line:
        cw = 2 if ord(ch) > 0x2E80 else 1
        if w + cw > room:
            out.append(cur)
            room = limit - 4
            cur = " " * (indent + 4)
            w = display_width(cur)
        cur += ch
        w += cw
    out.append(cur)
    return out


def clean_source(path: pathlib.Path) -> tuple[list[str], list[str], list[str], int]:
    """返回 (有效代码行（含折行）, 日期命中, 著作权字样命中, 逻辑行数)。

    逻辑行数 = 剔除空行后的源代码行数，即申请表「源程序量」的口径；
    折行只是排版产物，不计入源程序量。空行剔除，注释保留。
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(ROOT).as_posix()
    out: list[str] = []
    dates: list[str] = []
    ip_hits: list[str] = []
    n_logic = 0
    for i, line in enumerate(raw.splitlines(), start=1):
        line = line.replace("\t", "    ").rstrip()
        if not line.strip():
            continue
        n_logic += 1
        dm = DATE_RE.search(line)
        if dm:
            y, mo, d = int(dm.group(1)), int(dm.group(2)), int(dm.group(3) or 1)
            if (y, mo, d) > DOC_COMPLETE_DATE:   # 只登记与完成日期冲突的（未来日期）
                dates.append(f"{rel}:{i}: {line[:100]}")
        if IP_WORDS_RE.search(line):
            ip_hits.append(f"{rel}:{i}: {line[:100]}")
        out.extend(wrap_line(line))
    return out, dates, ip_hits, n_logic


def build_doc(out_path: pathlib.Path, pages: list[list[str]]) -> None:
    doc = Document()
    sec = doc.sections[0]
    setup_page(sec, top=1.5, bottom=1.2, left=1.5, right=1.5,
               header_dist=0.9, footer_dist=0.7)
    header_with_pagenum(sec, HEADER_TEXT, size=9)

    normal = doc.styles["Normal"]
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)

    for pi, page_lines in enumerate(pages):
        for li, text in enumerate(page_lines):
            p = doc.add_paragraph()
            pf = p.paragraph_format
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)
            pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            pf.line_spacing = Pt(LINE_PITCH)
            pf.widow_control = False
            if li == 0 and pi > 0:
                pf.page_break_before = True
            set_run(p.add_run(text), CODE_FONT_SIZE, mono=True)

    update_fields_on_open(doc)
    doc.save(str(out_path))


def pick_submit_pages(pages: list[list[str]], n: int = SUBMIT_PAGES) -> list[list[str]]:
    if len(pages) <= 2 * n:
        return pages
    return pages[:n] + pages[-n:]


def run(out_dir: pathlib.Path | None = None) -> dict[str, Any]:
    out_dir = out_dir or (ROOT / "outputs" / "ip")
    out_dir.mkdir(parents=True, exist_ok=True)

    files = collect_files()
    lines: list[str] = []
    dates: list[str] = []
    ip_hits: list[str] = []
    n_logic = 0
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        lines.append(f"# ==================== {rel} ====================")
        body, d, ip, nl = clean_source(f)
        lines.extend(body)
        dates.extend(d)
        ip_hits.extend(ip)
        n_logic += nl

    pages = [lines[i:i + LINES_PER_CODE_PAGE]
             for i in range(0, len(lines), LINES_PER_CODE_PAGE)]
    submit_pages = pick_submit_pages(pages)

    full = out_dir / f"源程序_{SOFT_NAME}_{SOFT_VER}_全文版({len(pages)}页).docx"
    sub = out_dir / f"源程序_{SOFT_NAME}_{SOFT_VER}_提交版(前30后30共{len(submit_pages)}页).docx"
    build_doc(full, pages)
    build_doc(sub, submit_pages)

    max_w = max(display_width(ln) for ln in lines)
    report = {
        "software": HEADER_TEXT,
        "program_language": "Python 3.13 / TypeScript 5",
        "source_files": [f.relative_to(ROOT).as_posix() for f in files],
        "n_source_files": len(files),
        "total_program_lines": n_logic,
        "printed_lines": len(lines),
        "lines_per_page": LINES_PER_CODE_PAGE,
        "total_pages": len(pages),
        "submit_pages": len(submit_pages),
        "max_display_width": max_w,
        "wrap_limit": WRAP_DISPLAY_WIDTH,
        "date_hits": dates,
        "ip_word_hits": ip_hits,
        "checks": {
            "no_blank_lines": all(ln.strip() for ln in lines),
            "lines_per_page_ok": all(len(p) == LINES_PER_CODE_PAGE for p in pages[:-1]),
            "no_line_exceeds_width": max_w <= WRAP_DISPLAY_WIDTH,
            "submit_is_30_plus_30": len(submit_pages) == min(len(pages), 2 * SUBMIT_PAGES),
        },
    }
    (out_dir / "源程序_校验报告.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[source] 文件 {len(files)} 个 / 源程序量 {n_logic} 行（排版 {len(lines)} 行）/ "
          f"全文 {len(pages)} 页 / 提交 {len(submit_pages)} 页 / 最大显示宽 {max_w}")
    print(f"[source] {full.name}")
    print(f"[source] {sub.name}")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    run(pathlib.Path(a.out) if a.out else None)
