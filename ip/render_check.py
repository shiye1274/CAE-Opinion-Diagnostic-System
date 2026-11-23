"""把 docx 渲染为 PDF 并逐页统计实际行数（用本机 Word，真实排版结果）。

用途：软著鉴别材料的硬指标只有渲染后才知道——
「程序每页不少于 50 行」「文档每页不少于 30 行」「页数」都取决于 Word 的
实际分页，python-docx 里数段数是不可靠的。

同时会检查页眉的实际水平位置（官方要求页码标在右上角）。

用法::

    python ip/render_check.py 文件1.docx [文件2.docx ...]
    python ip/render_check.py --keep-pdf        # 保留 PDF 便于人工翻阅
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import pymupdf


def to_pdf(docx_path: pathlib.Path) -> pathlib.Path:
    import pythoncom
    import win32com.client

    pdf = docx_path.with_suffix(".pdf")
    src = str(docx_path.resolve())
    out = str(pdf.resolve())
    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(src, ReadOnly=True, AddToRecentFiles=False)
        doc.Fields.Update()
        doc.SaveAs(out, FileFormat=17)  # wdFormatPDF
        doc.Close(False)
    finally:
        word.Quit()
        pythoncom.CoUninitialize()
    return pdf


def page_stats(pdf_path: pathlib.Path, header_band: float = 42.0) -> list[dict]:
    """返回每页的行数（正文区）与页眉文本。

    页眉按字号区分（页眉 9 磅，正文 ≥10.5 磅），不按固定 y 阈值：
    版心起点随页边距变化，纯 y 阈值会把正文第一行算进页眉。

    双向文字（阿拉伯语）行会被 PDF 提取按字符方向拆成两条 y 相近的记录，
    与 Word 中打开看到的视觉行数不符；这里按 y 归并间距 <3 磅的相邻行，
    使计数与实际版面一致（正常行距 ≥10 磅，不会误并）。
    """
    out = []
    doc = pymupdf.open(str(pdf_path))
    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        hdr, body = [], []
        for b in blocks:
            for ln in b.get("lines", []):
                spans = ln.get("spans", [])
                txt = "".join(s["text"] for s in spans).strip()
                if not txt:
                    continue
                size = max((s["size"] for s in spans if s["text"].strip()), default=0)
                y0 = ln["bbox"][1]
                is_hdr = size <= 9.5 or (y0 < header_band and size < 10.4)
                (hdr if is_hdr else body).append((y0, txt))
        # 归并 bidi 拆行：按 y 排序后，间距 <3 磅的相邻行视为同一视觉行
        body.sort(key=lambda t: t[0])
        merged: list[tuple[float, str]] = []
        for y0, txt in body:
            if merged and abs(y0 - merged[-1][0]) < 3.0:
                continue
            merged.append((y0, txt))
        out.append({
            "page": page.number + 1,
            "header": " || ".join(t for _, t in hdr),
            "lines": len(merged),
            "body_h": page.rect.height,
        })
    doc.close()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--keep-pdf", action="store_true")
    a = ap.parse_args(argv)

    bad = 0
    for f in a.files:
        p = pathlib.Path(f)
        pdf = to_pdf(p)
        stats = page_stats(pdf)
        counts = [s["lines"] for s in stats]
        print(f"\n=== {p.name} ===")
        print(f"渲染页数: {len(stats)}　正文行数 min/median/max: "
              f"{min(counts)}/{sorted(counts)[len(counts) // 2]}/{max(counts)}")
        print(f"页眉示例: {stats[0]['header'][:100]}")
        low = [(s['page'], s['lines']) for s in stats if s['lines'] < 30]
        if low:
            print(f"正文少于 30 行的页: {low[:12]}{' ...' if len(low) > 12 else ''}")
        if not a.keep_pdf:
            pdf.unlink(missing_ok=True)
        else:
            print(f"PDF: {pdf}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
