"""软著登记材料的公共口径与排版原语。

所有硬指标集中在此，三个生成脚本共用，避免各处口径漂移：

官方口径（中国版权保护中心《计算机软件著作权登记指南》，见
ip/软著登记材料规范与官方依据.md 中的链接与原文引用）：

- 页眉：标注软件名称、版本号，内容与申请表一致；
- 页码：标注在**右上角**，源程序从正文第 1 页编到第 60 页，
  文档从**目录**开始由第 1 页编到第 60 页；
- 程序每页不少于 50 行，文档每页不少于 30 行；
- 申请文件纵向排版，文字从左向右排列。
"""

from __future__ import annotations

import pathlib

from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

# ---------- 与申请表逐字一致的软件标识 ----------
SOFT_NAME = "中阿英跨语言舆情语料库与品牌出海舆情诊断系统"
SOFT_VER = "V1.0"
HEADER_TEXT = f"{SOFT_NAME} {SOFT_VER}"
PROGRAM_LANG = "Python 3.13 / TypeScript 5"
COPYRIGHT_HOLDER = "【申请人本人姓名】"   # 著作权人 = 申请人本人（提交前替换为真实姓名）

# ---------- 版面 ----------
A4_WIDTH, A4_HEIGHT = Cm(21), Cm(29.7)
BODY_CN_FONT = "宋体"
BODY_LATIN_FONT = "Times New Roman"
HEAD_CN_FONT = "黑体"
MONO_FONT = "Consolas"

LINES_PER_CODE_PAGE = 50
MIN_DOC_LINES_PER_PAGE = 30

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---------- run / 段落 ----------
def set_run(run, size: float, *, bold: bool = False, mono: bool = False,
            cn_font: str = BODY_CN_FONT, latin_font: str = BODY_LATIN_FONT) -> None:
    if mono:
        cn_font, latin_font = MONO_FONT, MONO_FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = latin_font
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.get_or_add_rFonts()
    fonts.set(qn("w:eastAsia"), cn_font)
    fonts.set(qn("w:ascii"), latin_font)
    fonts.set(qn("w:hAnsi"), latin_font)
    # 中文按字符数缩排，避免中英混排断行难看
    if not mono:
        rpr.append(_el("w:kern", {"w:val": "2"}))


def _el(tag: str, attrs: dict | None = None):
    e = OxmlElement(tag)
    for k, v in (attrs or {}).items():
        e.set(qn(k), v)
    return e


def setup_page(section, *, top=2.4, bottom=2.2, left=2.6, right=2.4,
               header_dist=1.4, footer_dist=1.2) -> None:
    """A4 纵向（官方：申请文件应纵向排版）。"""
    section.orientation = 0  # portrait
    section.page_width, section.page_height = A4_WIDTH, A4_HEIGHT
    section.top_margin, section.bottom_margin = Cm(top), Cm(bottom)
    section.left_margin, section.right_margin = Cm(left), Cm(right)
    section.header_distance, section.footer_distance = Cm(header_dist), Cm(footer_dist)


def text_width(section):
    return section.page_width - section.left_margin - section.right_margin


def _page_field(paragraph, size: float, prefix: str = "第 ", suffix: str = " 页") -> None:
    """插入可自动更新的 PAGE 域（带缓存值，未按 F9 也能正常显示）。"""
    if prefix:
        set_run(paragraph.add_run(prefix), size)
    for kind, payload in (("begin", None), ("instr", "PAGE"), ("separate", None),
                          ("text", "1"), ("end", None)):
        run = paragraph.add_run()
        set_run(run, size)
        if kind in ("begin", "separate", "end"):
            run._element.append(_el("w:fldChar", {"w:fldCharType": kind}))
        else:
            el = _el("w:instrText" if kind == "instr" else "w:t")
            el.set(qn("xml:space"), "preserve")
            el.text = payload
            run._element.append(el)
    if suffix:
        set_run(paragraph.add_run(suffix), size)


def header_with_pagenum(section, left_text: str, *, size: float = 9.0,
                        rule: bool = True) -> None:
    """页眉：左侧软件名称+版本号，右侧「第 X 页」（官方要求的右上角页码）。"""
    section.header.is_linked_to_previous = False
    p = section.header.paragraphs[0]
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    # Word 内置「页眉」样式自带居中/右对齐两个制表位（Letter 口径），
    # 不清理会让「第 X 页」停在版面中间而不是右上角。
    try:
        p.style.paragraph_format.tab_stops.clear_all()
    except Exception:  # noqa: BLE001
        pass
    pf.tab_stops.clear_all()
    right_pos = text_width(section)
    pf.tab_stops.add_tab_stop(right_pos, WD_TAB_ALIGNMENT.RIGHT)
    set_run(p.add_run(left_text), size)
    set_run(p.add_run("\t"), size)
    _page_field(p, size)
    if rule:
        pPr = p._element.get_or_add_pPr()
        bdr = _el("w:pBdr")
        bottom = _el("w:bottom", {"w:val": "single", "w:sz": "6",
                                  "w:space": "1", "w:color": "808080"})
        bdr.append(bottom)
        pPr.append(bdr)


def blank_header(section) -> None:
    section.header.is_linked_to_previous = False
    for p in section.header.paragraphs:
        for r in list(p.runs):
            r._element.getparent().remove(r._element)


def restart_numbering(section, start: int = 1) -> None:
    """本节页码从 start 重新开始（封面不参与编号）。"""
    sectPr = section._sectPr
    for old in sectPr.findall(qn("w:pgNumType")):
        sectPr.remove(old)
    sectPr.append(_el("w:pgNumType", {"w:start": str(start), "w:fmt": "decimal"}))


def new_section(doc, *, top=2.4, bottom=2.2, left=2.6, right=2.4):
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    setup_page(sec, top=top, bottom=bottom, left=left, right=right)
    return sec


def update_fields_on_open(doc) -> None:
    """让 Word 打开时自动更新域（页码），避免显示缓存值。"""
    settings = doc.settings.element
    for tag in ("w:updateFields",):
        for old in settings.findall(qn(tag)):
            settings.remove(old)
    settings.append(_el("w:updateFields", {"w:val": "true"}))


def add_dot_leader(p, left: str, page: str | int, right_pos, *, size: float = 10.5) -> None:
    """目录条目：左标题 + 点线 + 右页码。"""
    pf = p.paragraph_format
    pf.tab_stops.add_tab_stop(right_pos, WD_TAB_ALIGNMENT.RIGHT, 1)  # leader=1 dots
    set_run(p.add_run(left), size)
    set_run(p.add_run("\t"), size)
    set_run(p.add_run(str(page)), size)


def body_paragraph(doc, text: str, *, size: float = 10.5, indent: bool = True,
                   space_after: float = 2, line_spacing: float = 1.1,
                   align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    p = doc.add_paragraph()
    p.alignment = align
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(0)
    pf.line_spacing = line_spacing
    if indent:
        pf.first_line_indent = Pt(size * 2)
    set_run(p.add_run(text), size)
    return p


def heading(doc, text: str, level: int = 1, *, size: float | None = None,
            page_break_before: bool = False, space_before: float = 10,
            space_after: float = 6):
    sizes = {1: 15, 2: 12, 3: 10.5}
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.page_break_before = page_break_before
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.keep_with_next = True
    pf.line_spacing = 1.2
    pf.outline_level = level - 1  # 供 Word 导航/自动目录识别
    set_run(p.add_run(text), size or sizes.get(level, 10.5), bold=True, cn_font=HEAD_CN_FONT)
    return p


def table(doc, headers: list[str], rows: list[list], *, size: float = 9,
          widths_cm: list[float] | None = None, header_fill: str = "F2F2F2"):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.autofit = False
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(p.add_run(str(h)), size, bold=True, cn_font=HEAD_CN_FONT)
        tcPr = hdr[i]._tc.get_or_add_tcPr()
        shd = _el("w:shd", {"w:val": "clear", "w:fill": header_fill})
        tcPr.append(shd)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.1
            set_run(p.add_run("" if v is None else str(v)), size)
    if widths_cm:
        for r in t.rows:
            for i, w in enumerate(widths_cm):
                r.cells[i].width = Cm(w)
    return t


def caption(doc, text: str, *, size: float = 9):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(2)
    pf.space_after = Pt(8)
    set_run(p.add_run(text), size)
    return p


def picture(doc, path: pathlib.Path, width_cm: float = 13.0, max_h_cm: float = 6.0):
    """插入居中插图，按宽度与最大高度双重约束（避免整页只有一张图，
    导致该页正文不足文档要求的 30 行）。"""
    from PIL import Image

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(4)
    pf.space_after = Pt(0)
    pf.keep_with_next = True
    w = width_cm
    try:
        with Image.open(path) as im:
            iw, ih = im.size
        if ih / iw * w > max_h_cm:
            w = max_h_cm * iw / ih
    except Exception:  # noqa: BLE001
        pass
    p.add_run().add_picture(str(path), width=Cm(w))
    return p
