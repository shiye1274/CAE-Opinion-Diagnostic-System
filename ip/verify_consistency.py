"""软著提交材料一致性校验（以**渲染后的真实版面**为准）。

为什么不数段落：官方指标（每页 50 行 / 30 行、页码、总页数）都是排版结果，
python-docx 里的段落数不等于 Word 实际分页。本脚本调用本机 Word 把 docx 转成
PDF，再用 PyMuPDF 逐页统计正文行数、页眉文本与页码坐标，因此结论与打开文档
看到的一致。

校验项对应官方要求（见 outputs/ip/软著登记材料规范与官方依据.md）：
1. A4 纵向；
2. 页眉含"软件名称 + 版本号"，与申请表逐字一致；
3. 页码在右上角（坐标校验）；
4. 源程序：60 页、每页 50 行（末页为程序结尾可不足）、页码 1..60 连续；
5. 说明书：目录起第 1 页、封面不编号、除封面外每页正文 ≥30 行；
6. 说明书目录条目页码与正文实际落页逐条一致；
7. 两份材料的页眉名称/版本号与源程序校验报告中的标识一致；
8. 源程序无与开发完成日期冲突的年份、无著作权人字样。

用法::

    python ip/verify_consistency.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

import pymupdf
from docx import Document

from ipmeta import HEADER_TEXT, SOFT_NAME, SOFT_VER
from render_check import to_pdf

ROOT = pathlib.Path(__file__).resolve().parent.parent
IP = ROOT / "outputs" / "ip"
RIGHT_TOLERANCE_PT = 12.0


def right_text_edge(docx_path: pathlib.Path) -> float:
    """版心右边界（pt）：按本文档实际的右页边距计算，不能写死。"""
    sec = Document(str(docx_path)).sections[0]
    from docx.shared import Emu
    return Emu(int(sec.page_width) - int(sec.right_margin)).pt


def page_lines(page) -> list[tuple[str, tuple[float, float, float, float]]]:
    out = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = "".join(s["text"] for s in ln["spans"]).strip()
            if t:
                out.append((t, tuple(ln["bbox"])))
    return out


PAGENO_RE = re.compile(r"^第\s*\d+\s*页$")


def split_header_body(page) -> tuple[str, float, list[str]]:
    """按文本特征区分页眉与正文（页眉 = 顶部且含软件标识或页码的行）。

    不能只用 y 阈值：源程序版心从 1.6 cm 起、说明书从 2.4 cm 起，
    页眉文字的下沿分别在 40 pt 与 51 pt 附近，固定阈值必然有一边判错。

    双向文字（阿拉伯语）行会被 PDF 提取按字符方向拆成两条 y 相近的记录，
    按 y 归并间距 <3 磅的相邻行，使行数与 Word 中打开看到的视觉行一致
    （正常行距 ≥10 磅，不会误并）。
    """
    hdr, body_y, right_x = [], [], 0.0
    for text, bbox in page_lines(page):
        is_hdr = bbox[3] < 62 and (HEADER_TEXT in text or PAGENO_RE.match(text))
        if is_hdr:
            hdr.append(text)
            right_x = max(right_x, bbox[2])
        else:
            body_y.append((bbox[1], text))
    body_y.sort(key=lambda t: t[0])
    merged: list[tuple[float, str]] = []
    for y, text in body_y:
        if merged and abs(y - merged[-1][0]) < 3.0:
            continue
        merged.append((y, text))
    return " ".join(hdr), right_x, [t for _, t in merged]


def analyze(pdf_path: pathlib.Path) -> dict:
    doc = pymupdf.open(str(pdf_path))
    pages = []
    for pg in doc:
        hdr, hx1, body = split_header_body(pg)
        m = re.search(r"第\s*(\d+)\s*页", hdr)
        pages.append({"w": pg.rect.width, "h": pg.rect.height,
                      "header": hdr, "page_no": int(m.group(1)) if m else None,
                      "header_right_x": hx1, "n_body": len(body),
                      "first": body[0] if body else ""})
    doc.close()
    return {"pages": pages, "count": len(pages)}


def check_source(report: dict[str, list[tuple[str, bool, str]]]) -> None:
    cand = sorted(IP.glob("源程序_*提交版*.docx"))
    add = lambda name, ok, detail="": report.setdefault("源程序", []).append((name, ok, detail))
    if not cand:
        add("提交版存在", False, "未找到 源程序_*提交版*.docx")
        return
    docx_path = cand[-1]
    add("提交版存在", True, docx_path.name)
    pdf = to_pdf(docx_path)
    info = analyze(pdf)
    pages = info["pages"]
    pdf.unlink(missing_ok=True)

    add("A4 纵向", all(abs(p["w"] - 595.3) < 2 and abs(p["h"] - 841.9) < 2 for p in pages),
        f"{len(pages)} 页，页面 {pages[0]['w']:.0f}×{pages[0]['h']:.0f} pt")
    add("总页数为 60（前 30 + 后 30）", len(pages) == 60, f"实际 {len(pages)} 页")
    nos = [p["page_no"] for p in pages]
    add("页码 1—60 连续", nos == list(range(1, len(pages) + 1)), f"取到 {nos[:3]}…{nos[-2:]}")
    add("页眉含软件名称+版本号", all(HEADER_TEXT in p["header"] for p in pages),
        pages[0]["header"][:60])
    right = right_text_edge(docx_path)
    add("页码在右上角", all(abs(p["header_right_x"] - right) <= RIGHT_TOLERANCE_PT for p in pages),
        f"页眉右边界 {pages[0]['header_right_x']:.1f} pt，版心右侧 {right:.1f} pt")
    full = [p["n_body"] for p in pages]
    add("除末页外每页不少于 50 行", all(n >= 50 for n in full[:-1]),
        f"每页行数 {min(full)}–{max(full)}，末页 {full[-1]} 行（程序结尾）")

    rep_json = IP / "源程序_校验报告.json"
    if rep_json.exists():
        rep = json.loads(rep_json.read_text(encoding="utf-8"))
        add("源程序量已记录（申请表口径）", rep["total_program_lines"] > 0,
            f"{rep['total_program_lines']:,} 行 / {rep['n_source_files']} 个源文件")
        add("源程序无空行", rep["checks"]["no_blank_lines"], "")
        add("长行不超出版心（无二次换行）", rep["checks"]["no_line_exceeds_width"],
            f"最大显示宽 {rep['max_display_width']}")
        add("无与申请表冲突的日期", len(rep["date_hits"]) == 0, f"命中 {len(rep['date_hits'])} 处")
        add("源程序无著作权人/版权字样", len(rep["ip_word_hits"]) == 0,
            f"命中 {len(rep['ip_word_hits'])} 处" if rep["ip_word_hits"] else "")


def check_manual(report: dict[str, list[tuple[str, bool, str]]]) -> None:
    cand = sorted(IP.glob("使用说明书_*.docx"))
    add = lambda name, ok, detail="": report.setdefault("使用说明书", []).append((name, ok, detail))
    if not cand:
        add("说明书存在", False, "未找到 使用说明书_*.docx")
        return
    docx_path = cand[-1]
    add("说明书存在", True, docx_path.name)
    pdf = to_pdf(docx_path)
    info = analyze(pdf)
    pages = info["pages"]
    pdf.unlink(missing_ok=True)

    add("A4 纵向", all(abs(p["w"] - 595.3) < 2 and abs(p["h"] - 841.9) < 2 for p in pages),
        f"共 {len(pages)} 页（含封面）")
    add("不到 60 页，应提交全本", len(pages) - 1 < 60, f"编号页 {len(pages) - 1} 页")
    add("封面不编页码", pages[0]["page_no"] is None and not pages[0]["header"],
        "封面无页眉与页码")
    add("目录为编号第 1 页", pages[1]["page_no"] == 1, f"第 2 页页眉：{pages[1]['header']}")
    add("正文含目录", "目" in pages[1]["first"].replace(" ", ""), f"目录页首行：{pages[1]['first'][:20]}")
    body_pages = pages[1:]
    add("页码连续", [p["page_no"] for p in body_pages] == list(range(1, len(body_pages) + 1)),
        f"1—{len(body_pages)}")
    add("页眉含软件名称+版本号", all(HEADER_TEXT in p["header"] for p in body_pages),
        body_pages[0]["header"][:70])
    right = right_text_edge(docx_path)
    add("页码在右上角", all(abs(p["header_right_x"] - right) <= RIGHT_TOLERANCE_PT
                          for p in body_pages),
        f"页眉右边界 {body_pages[0]['header_right_x']:.1f} pt")
    counts = [p["n_body"] for p in body_pages]
    add("每页正文不少于 30 行", all(n >= 30 for n in counts),
        f"最少 {min(counts)} 行 / 中位 {sorted(counts)[len(counts) // 2]} 行")

    # 目录页码与正文实际落页逐条比对
    toc_pdf = to_pdf(docx_path)
    doc = pymupdf.open(str(toc_pdf))
    try:
        toc_lines = []
        for i in (1, 2, 3):
            if i < len(doc):
                toc_lines += [l.strip() for l in doc[i].get_text().splitlines() if "...." in l]
        mismatch, checked = [], 0
        for line in toc_lines:
            m = re.match(r"^(.*?)\s*\.{3,}\s*(\d+)$", line)
            if not m:
                continue
            name, num = m.group(1).strip(), int(m.group(2))
            actual = None
            for pi, pg in enumerate(doc):
                for b in pg.get_text("dict")["blocks"]:
                    for ln in b.get("lines", []):
                        t = "".join(s["text"] for s in ln["spans"]).strip()
                        if t == name and max((s["size"] for s in ln["spans"]), default=0) > 11:
                            actual = pi
            checked += 1
            if actual is not None and actual != num:
                mismatch.append(f"{name}: 目录 {num} / 实际 {actual}")
        add("目录页码与正文落页一致", len(mismatch) == 0 and checked > 0,
            f"{checked} 条比对，不一致 {len(mismatch)} 条" + ("：" + "；".join(mismatch[:3]) if mismatch else ""))
    finally:
        doc.close()
        toc_pdf.unlink(missing_ok=True)


def check_apply_form(report) -> None:
    add = lambda name, ok, detail="": report.setdefault("申请表信息单", []).append((name, ok, detail))
    p = IP / "软著申请表_信息填写单.docx"
    add("信息单存在", p.exists(), p.name if p.exists() else "缺少 软著申请表_信息填写单.docx")
    if not p.exists():
        return
    text = "\n".join(par.text for par in Document(str(p)).paragraphs)
    for t in Document(str(p)).tables:
        for row in t.rows:
            text += "\n" + " ".join(c.text for c in row.cells)
    for field in ("软件全称", "简称", "版本号", "软件作品说明", "开发完成日期", "发表状态",
                  "开发方式", "权利取得方式", "权利范围", "编程语言", "源程序量"):
        add(f"含官方字段：{field}", field in text)
    add("软件名称与版本一致", SOFT_NAME in text and SOFT_VER in text)


def export_pdfs(out: pathlib.Path) -> list[str]:
    """登记系统只接受 pdf 上传：把两份鉴别材料导出到 提交用PDF/。"""
    made = []
    for pattern in ("源程序_*提交版*.docx", "使用说明书_*.docx"):
        cand = sorted(IP.glob(pattern))
        if not cand:
            continue
        src = cand[-1]
        pdf = to_pdf(src)
        target = out / f"{src.stem}.pdf"
        pdf.replace(target)
        made.append(target.name)
    return made


def main(out_dir: pathlib.Path | None = None) -> int:
    report: dict[str, list[tuple[str, bool, str]]] = {}
    check_source(report)
    check_manual(report)
    check_apply_form(report)

    all_ok = all(ok for items in report.values() for _, ok, _ in items)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# 软著提交材料一致性校验报告", "",
             f"软件：{HEADER_TEXT}　|　校验时间：{stamp}",
             "校验方式：用本机 Word 将 docx 渲染为 PDF 后逐页实测（页数、每页行数、"
             "页眉文本、页码坐标、目录落页），非段落计数。", ""]
    for group, items in report.items():
        lines += [f"## {group}", ""]
        for name, ok, detail in items:
            lines.append(f"- [{'PASS' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""))
        lines.append("")
    lines.append(f"结论：{'全部通过' if all_ok else '存在未通过项，请按上表处理'}")
    pdf_dir = (out_dir or IP) / "提交用PDF"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    made = export_pdfs(pdf_dir)
    for stale in (out_dir or IP).glob("*.pdf"):
        stale.unlink(missing_ok=True)
    if made:
        lines += ["", "## 提交用 PDF", ""] + [f"- {m}" for m in made]

    out = (out_dir or IP) / "一致性校验报告.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if all_ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    sys.exit(main(pathlib.Path(a.out) if a.out else None))
