"""生成《计算机软件著作权登记申请表 · 填报信息单》（.docx）。

字段顺序与口径严格照抄中国版权保护中心《计算机软件著作权登记申请表填写说明》
（https://www.ccopyright.com.cn/index.php?optionid=1081），
把该说明里的 1~10 项逐条落成可填写的表格，并在每行标注官方依据要点，
避免出现“自己想的字段”或“官方要求但漏填”的字段。

用法::

    python ip/make_apply_form.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

from ipmeta import (COPYRIGHT_HOLDER, HEAD_CN_FONT, ROOT, SOFT_NAME, SOFT_VER,
                    body_paragraph, heading, set_run, setup_page, table)

OFFICIAL = "https://www.ccopyright.com.cn/index.php?optionid="
DOC_COMPLETE_DATE = "2026-11-22"

# ---- 在线申请表第 5 项填报文案（与网页逐字一致；字数=含标点总字符数，网页计数口径）----
# (字段名, 填报值, 字数上限(None=不限), 官方口径说明)
ENV_FIELDS: list[tuple[str, str, int | None, str]] = [
    ("开发的硬件环境",
     "x86_64 四核及以上，内存 8GB 以上，磁盘 20GB 以上；批量微调模型时建议配独立显卡。",
     50, "指开发该软件的计算机硬件与专用设备"),
    ("软件环境",
     "Python 3.13 + Node.js 18，SQLite 单机库，依赖全为开源库，可离线运行。",
     50, "指开发与运行的总体软件环境"),
    ("开发该软件的操作系统",
     "Windows 11（64位）为开发环境，兼容 Windows 10 与主流 Linux 发行版。",
     50, "指开发阶段使用的操作系统"),
    ("软件开发环境 / 开发工具",
     "VS Code、Git，pip 与 npm 管理依赖，配套校验脚本与日志排查。",
     50, "指编码、构建与测试所用工具链"),
    ("运行平台 / 操作系统",
     "Windows 10/11（64 位）为主运行平台，兼容 Linux、macOS。",
     50, "指软件交付后实际运行的操作系统"),
    ("运行支撑环境 / 支持软件",
     "Python 3.13 及 FastAPI、React、SQLite 等开源库。",
     50, "指运行所需支撑软件名称及版本，完整清单以 requirements.txt 为准"),
    ("编程语言", "Python 3.13、TypeScript 5（前端 React）", None,
     "指编写登记软件的全部编程语言"),
]

DEV_GOAL = ("解决中国品牌出海中东时三语舆情分散难对齐、海湾方言情感难识别、"
            "文化合规难预警的问题。")
DOMAIN = "中国新能源等品牌出海中东的舆情监测与跨文化传播研究，可扩展至区域国别研究。"
TECH_TAGS = ["大数据软件", "人工智能软件"]
TECH_FEAT = ("中阿英三语语义对齐检索与海湾方言情感计算；大模型双模型交叉标注流水线，"
             "一致性质检自动分流金银标准；五维文化合规规则引擎，判定依据与改写建议逐条输出。")

MAIN_FUNC = """本软件围绕中国品牌出海中东的多语种舆情，覆盖从数据采集到诊断报告的完整功能。
一、多通道数据采集：经全球新闻索引、新闻聚合订阅、站点检索接口、视频平台官方接口与公开存档等通道采集中阿英三语语料，词包配置统一维护品牌在三语下的锚点词，每次采集自动生成查询级审计日志与证据日志，原始页面按数据源、按日期存档并计算内容哈希，保证任一条语料可追溯至抓取现场。
二、清洗与结构化入库：自动完成正文抽取、去重、语言与语种变体识别、个人信息脱敏，结果写入语料主表、品牌实体映射表、评论树表与标注结果表；标题级记录支持全文回源补齐，清洗规则以版本号管理，同一份数据重复处理结果一致。
三、语料检索：支持中文、阿拉伯语、英语关键词检索，可按语言、层级、国家与语种变体组合筛选，分页返回结果，点击详情可查看完整正文、来源链接与抓取时间。
四、KWIC 索引行：以关键词为中心返回左右等宽语境的索引行，阿拉伯语结果按从右向左排版并高亮关键词，支撑词语搭配分析、评价倾向观察与典型用例抽取。
五、品牌声量对比：按阿语、英语、中文三语堆叠展示各品牌声量柱状图，提供中国品牌集群与西方日韩对照品牌的雷达对照图，并给出三语声量与合计值明细表。
六、文化合规审查：基于宗教禁忌、政治地缘、性别与家庭、社会习俗、刻板归因五维规则库扫描待发布文案，输出高、中、低、清洁四级风险判定，逐条列出命中规则、原文上下文与本土化改写建议。
七、舆情监测大屏：汇总语料总篇数、用户生成内容数量、总词数与阿语占比四项核心指标，提供语言分布、国家分布、语种变体三类统计图与历时演化时间线，时间线标注萌芽、破局、爆发、深水四个事件锚点阶段。
八、人机协同标注：本地部署标注平台，按品牌、层级、框架、情感、方面、误读八组字段组织界面，支持双人独立盲标，标注完成后导出标注结果文件并自动计算各字段一致性系数，分歧样本进入仲裁流程。
九、模型评测与报告：提供跨语言对齐模型在留出集上的检索召回评测，以及大模型预标注与双模型交叉的字段一致率统计，评测报告与一致性报告均由脚本自动生成并随版本归档。"""

TEXT_FIELDS: list[tuple[str, str, int]] = [
    ("开发目的", DEV_GOAL, 50),
    ("面向领域/行业", DOMAIN, 50),
    ("软件的主要功能", MAIN_FUNC.replace("\n", ""), 1300),  # 下限 500 另检
    ("技术特点文本", TECH_FEAT, 100),
]


def _check_limits() -> None:
    """文案写入前自检：超字数直接报错，防止改文案后超出申请表限制。"""
    for name, text, lim in TEXT_FIELDS:
        n = len(text)
        if name == "软件的主要功能":
            if not 500 <= n <= lim:
                raise ValueError(f"「{name}」字数 {n} 不在 500-{lim}")
        elif n > lim:
            raise ValueError(f"「{name}」超字数：{n} > {lim}")
    for name, text, lim, _ in ENV_FIELDS:
        if lim is not None and len(text) > lim:
            raise ValueError(f"「{name}」超字数：{len(text)} > {lim}")


def _facts() -> dict[str, Any]:
    p = ROOT / "outputs" / "ip" / "源程序_校验报告.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _kv_table(doc, rows: list[list[str]], widths=(4.0, 6.6, 5.4), size=8.5):
    table(doc, ["申请表字段", "填报值", "官方要求 / 说明"], rows, size=size, widths_cm=widths)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def build(out_dir: pathlib.Path) -> pathlib.Path:
    _check_limits()
    rep = _facts()
    n_lines = rep.get("total_program_lines", 0)
    n_files = rep.get("n_source_files", 0)
    full_pages = rep.get("total_pages", 0)
    sub_pages = rep.get("submit_pages", 0)

    doc = Document()
    setup_page(doc.sections[0], top=2.2, bottom=2.0, left=2.4, right=2.2)
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(10.5)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(2)
    set_run(p.add_run("计算机软件著作权登记申请表 · 填报信息单"), 17, bold=True, cn_font=HEAD_CN_FONT)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(10)
    set_run(p.add_run(f"{SOFT_NAME}  {SOFT_VER}"), 11)

    body_paragraph(doc, "本表按中国版权保护中心《计算机软件著作权登记申请表填写说明》"
                        "（下称《填表说明》）的 1~10 项顺序整理，逐条给出本软件的填报值"
                        "与官方要求要点。在线填报时照此录入即可，不要改动字段口径；"
                        "表中标注【填写】的项为申请人个人信息，需本人据实填写。", size=10.5)

    # ---------------- 1 软件基本信息 ----------------
    heading(doc, "1  软件基本信息（《填表说明》第 1 项）", 1, size=12.5, space_before=8)
    _kv_table(doc, [
        ["软件全称", SOFT_NAME,
         "全称应简短明确、针对性强，不违反法律、不损害公共利益。申请材料中的名称必须保持一致，"
         "本材料在申请表、源程序页眉、说明书页眉与封面四处统一使用该名称"],
        ["软件简称", "（留空）",
         "没有简称请留空，不要填写“无”，且不得与全称完全相同"],
        ["版本号", SOFT_VER,
         "建议填 V1.0 或 1.0 两种形式之一。证书版本号以本表为准；鉴别材料页眉的版本号"
         "必须与本表一致，有无 V 亦以本表为准"],
        ["软件作品说明", "原创软件",
         "原创与修改二选一。选“修改”须填修改说明；已登记过前期版本的还须填原登记号"
         "并提交原证书照片或扫描件"],
        ["开发完成日期", DOC_COMPLETE_DATE,
         "填软件全部固定在某种有形载体（硬盘、光盘等）上的日期。本软件以全流程链路跑通、"
         "结果与本文档定稿之日为准"],
        ["发表状态", "未发表",
         "已发表的须填首次发表日期与首次发表地点（销售、网上发布、产品发布、为销售目的展示"
         "均属发表）；未发表直接选未发表"],
        ["开发方式", "单独开发",
         "单独开发指依靠自身条件自行完成。合作、委托、下达任务开发的，须另附协议或任务书"
         "原件的照片/扫描件"],
    ])

    # ---------------- 2 著作权人 ----------------
    heading(doc, "2  著作权人（《填表说明》第 2 项）", 1, size=12.5)
    _kv_table(doc, [
        ["姓名或名称", COPYRIGHT_HOLDER, "如实填写。个人填身份证姓名，单位填营业执照或法人证书上的全称"],
        ["类别", "【填写：自然人 / 法人 / 非法人组织 / 其他】", "四类之一，须与实际身份一致"],
        ["证件类型", "【填写：居民身份证 / 统一社会信用代码证书 等】", "须与所提交的身份证明文件一致"],
        ["证件号码", "【填写】", "如实填写，与证件逐位一致"],
        ["国籍", "中国", "外国申请人按实际填写，并附护照及中文译本"],
        ["省份 / 城市", "【填写】", "按实际所在地选择"],
    ])
    body_paragraph(doc, "身份证明文件：企业法人提交加载统一社会信用代码的营业执照副本；"
                        "事业单位法人提交事业单位法人证书副本；自然人提交身份证。"
                        "一律提交原件照片或扫描件（pdf），拍照须清晰、平铺、无反光、无遮挡。", size=10)

    # ---------------- 3 权利说明 ----------------
    heading(doc, "3  权利说明（《填表说明》第 3 项）", 1, size=12.5)
    _kv_table(doc, [
        ["权利取得方式", "原始取得",
         "原始取得要求申请登记的软件为独立开发；受让、继承、承受取得的属继受取得，"
         "须填原登记号并附转让合同、死亡证明、企业变更决议等证明文件"],
        ["权利范围", "全部权利",
         "全部权利指《计算机软件保护条例》第八条规定的所有权利；仅主张部分权利的，"
         "须注明具体权项"],
        ["原登记号", "无（首次登记）", "已登记过的软件须填原登记号；做过变更或补充登记的填变更证明编号"],
    ])

    # ---------------- 4 鉴别材料 ----------------
    heading(doc, "4  软件鉴别材料（《填表说明》第 4 项）", 1, size=12.5)
    _kv_table(doc, [
        ["交存方式", "一般交存", "含商业秘密需保密的可选例外交存，三种方式择一，覆盖部分不得超过 50%"],
        ["源程序", f"前 30 页 + 后 30 页，共 {sub_pages} 页（每页 50 行）",
         "一般交存提交源程序连续的前 30 页与连续的后 30 页；程序每页不少于 50 行"],
        ["文档", "《使用说明书》全本 10 页（每页正文不少于 30 行）",
         "一般交存提交任何一种文档的前 30 页与后 30 页；整个文档不到 60 页的，"
         "应提交整个文档；文档每页不少于 30 行"],
        ["页眉与页码", f"页眉左侧“{SOFT_NAME} {SOFT_VER}”，右上角“第 X 页”",
         "官方问答明确：鉴别材料需要页眉页脚，页眉标注软件名称、版本号且与申请表一致，"
         "右上角标注页码；源程序从正文第 1 页编到第 60 页，文档从目录开始由第 1 页编号"],
        ["源程序量", f"{n_lines:,} 行（源程序总行数，Python 与 TypeScript）",
         "指源程序的总行数或总条数，须与提交的源程序文档口径一致"],
        ["全文版备用", f"源程序全文 {full_pages} 页（不提交，仅备查）",
         "全文版用于核对后 30 页与程序结尾的连续性，登记时只提交 60 页提交版"],
    ])

    # ---------------- 5 功能与技术特点 ----------------
    heading(doc, "5  软件功能和技术特点（《填表说明》第 5 项）", 1, size=12.5)
    rows: list[list[str]] = []
    for name, text, lim, note in ENV_FIELDS:
        suffix = f"；≤{lim} 字，实填 {len(text)} 字" if lim is not None else ""
        rows.append([name, text, note + suffix])
    rows.append(["源程序量", f"{n_lines:,} 行（{n_files} 个源文件，含 Python 与 TypeScript）",
                 "与第 4 项口径一致，取自源程序校验报告"])
    _kv_table(doc, rows, widths=(3.4, 7.0, 5.6))

    body_paragraph(doc, "以下文案与在线申请表逐字一致，可直接粘贴；"
                        "字数为含标点总字符数（网页输入框计数口径）：", size=10.5)
    body_paragraph(doc, f"开发目的（{len(DEV_GOAL)} 字）：{DEV_GOAL}", size=10.5)
    body_paragraph(doc, f"面向领域/行业（{len(DOMAIN)} 字）：{DOMAIN}", size=10.5)
    n_func = len(MAIN_FUNC.replace("\n", ""))
    for i, part in enumerate(MAIN_FUNC.split("\n")):
        prefix = f"软件的主要功能（{n_func} 字，限 500-1300）：" if i == 0 else ""
        body_paragraph(doc, prefix + part, size=10.5)
    body_paragraph(doc, f"软件的技术特点：标签勾选「{'」「'.join(TECH_TAGS)}」；"
                        f"文本框（{len(TECH_FEAT)} 字，限 100）：{TECH_FEAT}", size=10.5)

    # ---------------- 6~10 ----------------
    heading(doc, "6  办理方式与签章（《填表说明》第 6~10 项）", 1, size=12.5)
    _kv_table(doc, [
        ["申请办理方式", "著作权人自行办理", "也可委托代理人办理；委托的须注明代理范围、权限与授权期限"],
        ["申请人", "著作权人本人", "申请人为著作权人；有多个著作权人的，申请人为其中之一"],
        ["代理人", "无", "有代理人的填代理人名称与授权期限"],
        ["申请人签章", "【本人签名 / 单位公章（鲜章）】",
         "在线打印申请确认签章页后手签或盖章，再扫描上传；不得擅自更改签章页内容、格式与打印比例"],
        ["证书领取方式", "官网用户中心下载 PDF 电子证书",
         "电子证书带“计算机软件著作权登记专用章”电子签章，可用 WPS 等查看签名属性或在线验签"],
    ])

    # ---------------- 附表 1 提交材料清单 ----------------
    heading(doc, "附表 1  在线提交材料清单", 1, size=12.5)
    table(doc, ["序号", "材料", "本套材料中的对应文件", "格式与要求"], [
        ["1", "软件著作权登记申请表（在线填报）", "按本信息单逐项录入", "在线生成，无需上传 Word"],
        ["2", "申请确认签章页", "在线打印后签名/盖章再扫描", "pdf；不得改格式与打印比例"],
        ["3", "源程序鉴别材料", "源程序_…_提交版(前30后30共60页).docx", "pdf；每页 50 行；右上角页码 1—60"],
        ["4", "文档鉴别材料", "使用说明书_…V1.0.docx", "pdf；全本 10 页；正文每页 ≥30 行"],
        ["5", "身份证明文件", "营业执照副本 / 身份证", "原件照片或扫描件，清晰无遮挡"],
        ["6", "权利归属证明（如适用）", "合作/委托开发协议、任务书、转让合同", "仅合作、委托、下达任务、受让时提交"],
    ], size=8.5, widths_cm=[1.2, 4.6, 6.2, 4.0])
    doc.add_paragraph().paragraph_format.space_after = Pt(2)

    # ---------------- 附表 2 自检 ----------------
    heading(doc, "附表 2  提交前自检（对应常见补正原因）", 1, size=12.5)
    for t in (
        "软件名称、版本号在申请表、源程序页眉、说明书页眉/封面四处完全一致，"
        "版本号的有无“V”一致。",
        "源程序为连续的前 30 页与后 30 页，页码 1—60 连续；每页 50 行，末页除外；无空白页。",
        "源程序内容与提交的软件功能一致，未混入第三方开源代码或他人著作权声明。",
        "说明书从目录开始编页码，页眉标注软件名称与版本号，正文每页不少于 30 行。",
        "说明书中的功能描述与申请表“主要功能和技术特点”栏不矛盾，截图与正文描述对应。",
        "开发完成日期不晚于提交日期，且不早于说明书中出现的任何运行时间。",
        "身份证明文件与申请表填写的名称、证件类型、证件号码逐字一致。",
        "签章页为在线打印原件，签名/盖章为鲜章，扫描件完整清晰。",
        "所有上传文件均为 pdf，纵向排版，文字从左向右。",
    ):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.left_indent = Pt(21)
        pf.first_line_indent = Pt(-10.5)
        pf.space_after = Pt(2)
        set_run(p.add_run("□ " + t), 10)

    # ---------------- 依据 ----------------
    heading(doc, "本表依据（中国版权保护中心官网）", 1, size=12.5)
    for name, oid in (("计算机软件著作权登记指南", "1033"),
                      ("申请须知", "1057"),
                      ("办理步骤", "1079"),
                      ("所需文件", "1080"),
                      ("填表说明", "1081"),
                      ("办理时限", "1084"),
                      ("问题问答（含页眉页码要求）", "1087")):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(1)
        set_run(p.add_run(f"{name}：{OFFICIAL}{oid}"), 9.5)
    body_paragraph(doc, "办理时限：自受理日起 60 日内审查完成；材料有问题的，应在收到补正通知"
                        "之日起 30 日内补正，逾期未补正视为撤回申请。", size=9.5)

    out = out_dir / "软著申请表_信息填写单.docx"
    doc.save(str(out))
    print(f"[apply] {out.name}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    build(pathlib.Path(a.out) if a.out else ROOT / "outputs" / "ip")
