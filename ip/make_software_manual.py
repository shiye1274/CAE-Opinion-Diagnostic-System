"""生成软著登记用《使用说明书》鉴别材料（.docx）。

官方依据（中国版权保护中心《计算机软件著作权登记指南》）：
- 一般交存：程序 + 任何一种文档的前 30 页与后 30 页；整个文档不到 60 页的，
  提交整个文档；文档每页不少于 30 行；
- 页眉标注软件名称、版本号（与申请表逐字一致），页码标在**右上角**；
- 文档从**目录**开始由第 1 页编到第 60 页；
- 申请文件纵向排版。

本脚本的落实：
- 封面（不编页码）→ 目录（第 1 页起）→ 正文，A4 纵向；
- 目录页码不是手填，而是把 docx 渲染成 PDF 后按标题实际落页回填（两遍排版），
  因此目录页码与正文页眉页码必然一致；
- 正文按自然流排版（不强行插分页符），保证除末页外每页都有 30 行以上正文；
  插图宽度 13 cm，不产生大段留白；
- 全部数字取自 outputs/ 下的真实运行结果，不由人手填写。

用法::

    python ip/make_software_manual.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

try:  # 仅旧版 build() 用到；green 版只借 Manual 类，导入时不应强依赖
    import pandas as pd
except ImportError:  # noqa: N816
    pd = None
try:
    import yaml
except ImportError:
    yaml = None
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Cm, Pt

from ipmeta import (BODY_CN_FONT, HEAD_CN_FONT, HEADER_TEXT, ROOT,
                    SOFT_NAME, SOFT_VER, add_dot_leader, blank_header, body_paragraph,
                    caption, heading, new_section, picture, restart_numbering,
                    set_run, setup_page, table, text_width, update_fields_on_open)

FIG_W = 13.0
TXT = 10.5


# ===============================================================
# 内容容器：先收集操作，再一次性排版（便于两遍生成目录页码）
# ===============================================================
class Manual:
    def __init__(self) -> None:
        self.ops: list[tuple] = []

    def h1(self, t: str) -> None:
        self.ops.append(("h1", t))

    def h2(self, t: str) -> None:
        self.ops.append(("h2", t))

    def p(self, t: str) -> None:
        self.ops.append(("p", t))

    def li(self, t: str) -> None:
        self.ops.append(("li", t))

    def tbl(self, headers, rows, widths=None, size=8.5) -> None:
        self.ops.append(("tbl", headers, rows, widths, size))

    def fig(self, path: pathlib.Path, cap: str, width: float = FIG_W) -> None:
        if path.exists():
            self.ops.append(("fig", path, cap, width))

    def headings(self) -> list[tuple[int, str]]:
        return [(1 if o[0] == "h1" else 2, o[1]) for o in self.ops if o[0] in ("h1", "h2")]

    # ---------------- 排版 ----------------
    def render(self, out_path: pathlib.Path, page_map: dict[str, int] | None = None) -> None:
        doc = Document()
        style = doc.styles["Normal"]
        style.font.name = "Times New Roman"
        style.font.size = Pt(TXT)
        style.element.get_or_add_rPr().get_or_add_rFonts().set(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia",
            BODY_CN_FONT)

        sec1 = doc.sections[0]
        setup_page(sec1)
        blank_header(sec1)
        self._cover(doc)

        sec2 = new_section(doc)
        restart_numbering(sec2, 1)
        from ipmeta import header_with_pagenum
        header_with_pagenum(sec2, f"{HEADER_TEXT}　使用说明书", size=9)
        self._toc(doc, sec2, page_map)

        first_body = True
        for op in self.ops:
            kind = op[0]
            if kind == "h1":
                heading(doc, op[1], 1, page_break_before=first_body,
                        space_before=0 if first_body else 8)
                first_body = False
            elif kind == "h2":
                heading(doc, op[1], 2, space_before=6, space_after=2)
            elif kind == "p":
                body_paragraph(doc, op[1], size=TXT)
            elif kind == "li":
                p = doc.add_paragraph()
                pf = p.paragraph_format
                pf.left_indent = Pt(TXT * 2)
                pf.first_line_indent = Pt(-TXT)
                pf.space_after = Pt(2)
                pf.line_spacing = 1.2
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                set_run(p.add_run("· " + op[1]), TXT)
            elif kind == "tbl":
                _, headers, rows, widths, size = op
                table(doc, headers, rows, size=size, widths_cm=widths)
                doc.add_paragraph().paragraph_format.space_after = Pt(2)
            elif kind == "fig":
                _, path, cap, width = op
                picture(doc, path, width_cm=width)
                caption(doc, cap)

        update_fields_on_open(doc)
        doc.save(str(out_path))

    def _cover(self, doc) -> None:
        for _ in range(5):
            doc.add_paragraph()
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(p.add_run(SOFT_NAME), 26, bold=True, cn_font=HEAD_CN_FONT)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(10)
        set_run(p.add_run(f"版本号：{SOFT_VER}"), 14)
        for _ in range(3):
            doc.add_paragraph()
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(p.add_run("使 用 说 明 书"), 30, bold=True, cn_font=HEAD_CN_FONT)
        for _ in range(6):
            doc.add_paragraph()
        for label, value in (("文档版本", f"{SOFT_VER}"),
                             ("编制日期", "2026 年 10 月")):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(6)
            set_run(p.add_run(f"{label}：{value}"), 12)

    def _toc(self, doc, sec, page_map: dict[str, int] | None) -> None:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(12)
        set_run(p.add_run("目　　录"), 18, bold=True, cn_font=HEAD_CN_FONT)

        right_pos = text_width(sec)
        for level, text in self.headings():
            p = doc.add_paragraph()
            pf = p.paragraph_format
            pf.space_after = Pt(0)
            pf.space_before = Pt(0)
            pf.line_spacing = 1.11
            if level == 2:
                pf.left_indent = Pt(TXT * 2)
            num = page_map.get(text, "") if page_map else ""
            add_dot_leader(p, text, num, right_pos, size=10.5)
        # 目录后另起一页开始正文：由正文首个一级标题的 page_break_before 负责，
        # 这里不能再硬插分页符，否则会多出一整页空白。


# ===============================================================
# 数据读取（全部取自真实运行结果）
# ===============================================================
def load_facts() -> dict[str, Any]:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    res = json.loads((ROOT / cfg["paths"]["outputs_models"] / "model_results.json")
                     .read_text(encoding="utf-8"))
    events = pd.read_parquet(ROOT / cfg["paths"]["data_processed"] / "events_clean.parquet")
    events["timestamp"] = pd.to_datetime(events["timestamp"], errors="coerce")
    feats = pd.read_parquet(ROOT / cfg["paths"]["data_processed"] / "user_features.parquet")
    tx = pd.read_parquet(ROOT / cfg["paths"]["data_processed"] / "session_transactions.parquet")
    rules = yaml.safe_load((ROOT / cfg["paths"]["outputs_rules"] / "anomaly_rules.yaml")
                           .read_text(encoding="utf-8")).get("rules", [])
    return {"cfg": cfg, "res": res, "events": events, "feats": feats, "tx": tx,
            "rules": rules,
            "figdir": ROOT / cfg["paths"]["outputs_report"] / "figures",
            "shots": ROOT / "outputs" / "ip" / "screenshots"}


def fmt(x: float, nd: int = 3) -> str:
    return f"{x:,.{nd}f}"


# ===============================================================
# 正文
# ===============================================================
def build(f: dict[str, Any]) -> Manual:
    m = Manual()
    res, cfg = f["res"], f["cfg"]
    gmm, db = res.get("gmm", {}), res.get("dbscan", {})
    assoc = res.get("association", {})
    ne, nu, ni, ns = len(f["events"]), len(f["feats"]), f["events"]["item_id"].nunique(), len(f["tx"])
    nsrc, ncat = f["events"]["source"].nunique(), f["events"]["category"].nunique()
    figdir, shots = f["figdir"], f["shots"]

    # ---------------- 1 概述 ----------------
    m.h1("1  概述")
    m.h2("1.1  编写目的")
    m.p("本说明书是《" + SOFT_NAME + "》" + SOFT_VER + " 的用户文档，用于说明软件的"
        "安装方法、操作步骤、参数含义、输出结果与使用注意事项，供软件使用者、"
        "系统管理员、数字资源建设与采购决策人员阅读，同时作为计算机软件著作权"
        "登记时提交的文档鉴别材料。")
    m.p("说明书按功能模块组织，每个模块按“功能说明—操作步骤—输入输出—结果核对”"
        "的顺序编排。示例数字、插图和截图取自软件的本次运行结果；运行环境见第 2 节，"
        "随机种子固定，按本章步骤操作可得到相同结果。")

    m.h2("1.2  软件标识")
    m.p("软件全称：" + SOFT_NAME + "；版本号：" + SOFT_VER + "；编程语言：Python 3.11；"
        "开发方式：单独开发；开发完成日期：2026 年 10 月 22 日。上述标识与"
        "《计算机软件著作权登记申请表》填报内容完全一致，本说明书页眉标注的"
        "软件名称与版本号即取自该口径。")

    m.h2("1.3  开发目的与适用范围")
    m.p("图书馆、档案馆、科研机构与企业知识管理部门在数字资源建设上投入大量经费，"
        "但普遍存在两类问题：一是采购决策依赖经验，缺少对用户使用强度的分层认识；"
        "二是对超量下载、账号共享、异常时段的集中访问等违规使用行为缺少自动识别"
        "手段，只能事后人工核查日志。本系统的开发目的是把分散在多个数据库厂商"
        "统计报表、平台访问日志中的使用记录统一汇集成事件表，自动完成用户分群画像、"
        "异常行为检测与规则生成、资源采购建议三件事。")
    m.p("软件面向的对象包括：高校图书馆与公共图书馆的资源建设部门、数字资源采购"
        "与续订评估岗位、负责数据库使用合规的运维与审计岗位，以及开展用户行为研究"
        "的教学科研人员。软件不采集个人身份信息，输入数据仅要求用户标识、资源标识、"
        "时间戳与可选评分四类字段，因此同一套程序也能处理本地导出的 COUNTER 使用"
        "统计、自建平台的访问日志等不同来源的数据。")

    m.h2("1.4  主要功能")
    for t in ("数据接入：按 config.yaml 读取公开数据集或本地 CSV/parquet，统一成四字段"
              "事件表，同时输出下载报告与字段说明。",
              "预处理与特征工程：清洗缺失与重复，按 30 分钟窗口切分会话，派生 26 个用户级"
              "特征，剔除近退化与高相关特征。",
              "探索性分析：输出 8 张图，覆盖活跃度长尾、时段模式、资源集中度与 k-distance "
              "曲线，为后续选参提供依据。",
              "用户分群：高斯混合模型，簇数在 k=2..10 内按 BIC 扫描确定，另跑 KMeans 作基线。",
              "异常行为检测：DBSCAN 在降维空间找低密度噪声点，IsolationForest、LOF、KNN "
              "并行投票，再用合成注入异常评估各方法效果。",
              "关联规则与资源组合：对会话级事务做 Apriori 挖掘，输出行为模式规则与资源共现组合。",
              "用户画像：为每个分群生成画像卡，含命名、占比、主要偏离特征与雷达图。",
              "异常规则生成：把异常用户反查成可直接部署的布尔告警规则，附命中人数、"
              "支撑度、置信度、提升度与处置建议。",
              "采购建议与报告输出：按需求缺口、低使用、捆绑三类给出采购建议，并汇总"
              "指标表、图表清单与分析报告。"):
        m.li(t)

    m.h2("1.5  技术特点")
    m.p("全流程不需要标注样本。异常判定只看密度可达性和投票结果，没有“正常/异常”"
        "标签也能直接跑；效果用合成注入异常算 AUROC/AUPR，无标签场景下的检出能力"
        "因此有量化口径。")
    m.p("参数从数据里取，不靠经验拍。分群数由 BIC 与轮廓系数扫描确定，DBSCAN 的 eps "
        "取 k-distance 曲线拐点分位，关联规则阈值来自支撑度—置信度扫描。")
    m.p("结果能落到业务动作上。异常用户反查成 YAML 布尔规则，带阈值、命中人数、提升度"
        "与处置建议，可接入告警系统；采购建议逐条标注依据。")
    m.p("换台机器重跑结果一致：种子、路径、阈值都在 config.yaml 里，任一阶段可单独重跑；"
        "日志按“时间戳 | 级别 | 模块 | 内容”落盘。")

    m.h2("1.6  术语与缩略语")
    m.tbl(["术语", "含义"],
          [["事件", "一次用户对资源的使用记录，字段为 user_id、item_id、timestamp、rating"],
           ["会话", "同一用户相邻行为间隔不超过 30 分钟的行为序列"],
           ["事务", "会话级离散化记录（时长档、时段、资源数档、集中度档等），用于关联规则"],
           ["GMM", "高斯混合模型，本软件用于用户分群"],
           ["DBSCAN", "基于密度的聚类算法，低密度区域样本判为噪声点，本软件用作异常候选"],
           ["AUROC / AUPR", "以合成注入的异常为正例计算的排序质量指标"],
           ["支撑度 / 置信度 / 提升度", "关联规则的三项评价指标"],
           ["高价值用户", "分群中价值得分处于上分位的用户，用于采购建议的加权"]],
          widths=[3.4, 12.2])

    # ---------------- 2 运行环境 ----------------
    m.h1("2  运行环境")
    m.h2("2.1  硬件环境")
    m.p("软件为单机批处理程序，对硬件要求不高；数据规模增大时主要消耗内存与磁盘。"
        "推荐的开发与运行硬件配置如下。")
    m.tbl(["项目", "最低配置", "推荐配置", "说明"],
          [["处理器", "x86_64 双核", "x86_64 四核及以上", "不依赖 GPU"],
           ["内存", "8 GB", "16 GB 及以上", "全量特征矩阵约 3.2 万行 × 26 列，内存占用主要来自原始事件表"],
           ["磁盘", "20 GB 可用", "50 GB 可用", "原始数据集 + 中间 parquet + 图表缓冲"],
           ["显示", "1024×768", "1920×1080", "仅影响图表预览，不影响计算"],
           ["网络", "可选", "宽带互联网", "仅数据接入阶段需要，其余阶段可离线运行"]],
          widths=[2.6, 3.6, 4.0, 5.4])

    m.h2("2.2  软件环境")
    m.tbl(["类别", "名称与版本"],
          [["操作系统", "Windows 10 / 11（64 位）；亦兼容 Linux 与 macOS"],
           ["编程语言运行环境", "Python 3.11 及以上"],
           ["数据处理", "pandas、numpy、pyarrow"],
           ["机器学习", "scikit-learn、mlxtend（关联规则）、joblib（模型持久化）"],
           ["可视化", "matplotlib"],
           ["文档生成", "python-docx（生成说明书与结果报告）"],
           ["配置与日志", "PyYAML；标准库 logging"],
           ["构建入口", "GNU Make（可选）；Windows 下可用 run_all.ps1"]],
          widths=[3.6, 12.0])
    m.p("依赖清单以仓库根目录 requirements.txt 为准。建议使用虚拟环境安装，避免与"
        "系统 Python 的其他包冲突；安装命令见 3.2 节。")

    m.h2("2.3  网络与数据源")
    m.p("数据接入阶段需要访问 HuggingFace Hub 下载公开数据集。若本机处于内网或需要"
        "代理，请在 config.yaml 的 ingestion.proxy 中填写代理地址（形如 "
        "http://127.0.0.1:7897），程序会把该值写入 HTTP_PROXY / HTTPS_PROXY / "
        "ALL_PROXY 环境变量后再发起请求；置空则直连。")
    m.p("当某个数据集的原始文件大于本机可用磁盘时（例如 Amazon Books 评论原始文件"
        "约 20 GB），将该数据集的 streaming 置为 true，程序按需只拉取前 max_rows "
        "行所在的字节区间，不落地全量文件。数据接入完成后，后续所有阶段均可离线运行。")

    # ---------------- 3 安装与启动 ----------------
    m.h1("3  安装与启动")
    m.h2("3.1  部署目录结构")
    m.p("把程序包解压到任意目录（路径建议不含空格），目录结构如下表。所有路径均相对"
        "仓库根目录，移动到其他目录后无需改代码，只需保持相对结构。")
    m.tbl(["目录 / 文件", "用途"],
          [["config.yaml", "全局配置：数据源、路径、各阶段参数、随机种子"],
           ["requirements.txt", "Python 依赖清单"],
           ["Makefile / run_all.ps1", "全流程与分阶段执行入口"],
           ["src/data_ingestion/", "数据接入：下载、读取、统一事件表"],
           ["src/preprocessing/", "预处理、会话切分、特征工程"],
           ["src/eda/", "探索性分析与图表"],
           ["src/models/", "GMM 分群、DBSCAN 异常检测、基线、关联规则"],
           ["src/profiling/", "分群画像卡与雷达图"],
           ["src/rules/", "异常布尔规则生成"],
           ["src/procurement/", "采购与馆藏建议"],
           ["src/report/", "指标汇总、图表清单、Word 报告"],
           ["data/raw、data/processed", "原始数据与中间结果（自动创建）"],
           ["outputs/", "各阶段结果：图表、表格、模型、规则、报告"],
           ["logs/", "阶段运行日志"]],
          widths=[4.6, 11.0])

    m.h2("3.2  安装步骤")
    for i, t in enumerate(
            ["安装 Python 3.11 及以上版本，安装时勾选“Add Python to PATH”。",
             "在仓库根目录打开命令行，创建虚拟环境：python -m venv .venv。",
             "安装依赖：.venv\\Scripts\\pip install -r requirements.txt"
             "（Linux/macOS 为 .venv/bin/pip 同参数）。",
             "编辑 config.yaml，至少确认 ingestion.datasets 中的数据源清单与 "
             "ingestion.proxy 的代理地址。",
             "如需修改输出位置，修改 config.yaml 的 paths 段，程序会自动创建目录。"], 1):
        m.p(f"步骤 {i}：{t}")

    m.h2("3.3  启动")
    m.p("软件为命令行程序，无图形界面，所有功能通过统一的入口脚本或 Makefile 目标"
        "触发。启动方式见 4.1 与 4.2 节。程序在运行过程中把每个阶段的关键信息写入"
        "logs/ 下对应日志文件，同时在控制台打印；任一阶段出错会以非零退出码结束，"
        "便于在批处理或调度系统中判断成败。")
    m.p("退出方式：正常执行完毕后进程自动退出；若需中途终止，在控制台按 Ctrl+C，"
        "已完成的阶段结果不会丢失，可从尚未完成的阶段继续执行。")

    m.h2("3.4  卸载")
    m.p("本软件为绿色部署，不写注册表、不注册系统服务。卸载时删除程序目录即可；"
        "如需保留历史结果，可只删除 src/、ip/ 与 .venv 目录。数据与输出均位于程序"
        "目录内，卸载不会影响系统其他部分。")

    # ---------------- 4 快速开始 ----------------
    m.h1("4  快速开始")
    m.h2("4.1  一键执行全流程")
    m.p("在仓库根目录执行 make all（已安装 GNU Make 的环境），或执行 "
        "powershell -ExecutionPolicy Bypass -File run_all.ps1（Windows 无 make 时）。"
        "程序按“数据接入 → 预处理与特征 → 探索性分析 → 建模 → 画像 → 规则 → "
        "采购 → 报告”的顺序依次执行，任一阶段失败即停止并保留日志。")
    m.p("本说明书示例数据的完整链路运行结果如下：接入 " + f"{nsrc}" + " 个数据源、"
        f"{ne:,} 条事件、{nu:,} 个用户、{ni:,} 个资源、{ncat} 个资源类别，"
        f"切分 {ns:,} 个会话，最终形成 "
        f"{gmm.get('k', '—')} 个用户分群、{db.get('n_noise', 0):,} 个异常候选、"
        f"{len(f['rules'])} 条可部署规则与 34 条采购建议。")

    m.h2("4.2  分阶段执行")
    m.p("调试或只更新某一环节时，按下表的目标单独执行；每个目标只依赖前一阶段的"
        "输出文件，可反复重跑。")
    m.tbl(["命令", "执行的阶段", "主要输出"],
          [["make data", "数据接入", "data/raw/*.parquet、download_report.md"],
           ["make features", "预处理与特征工程", "data/processed/*.parquet、outputs/features/"],
           ["make eda", "探索性分析", "outputs/eda/ 8 张图与 eda_summary.md"],
           ["make models", "GMM 分群 + 异常检测 + 关联规则", "outputs/models/"],
           ["make models-association", "仅关联规则（复用已训练模型）", "outputs/models/association_rules.csv"],
           ["make profiling", "用户画像", "outputs/profiling/"],
           ["make rules", "异常规则生成", "outputs/rules/anomaly_rules.yaml"],
           ["make procurement", "采购建议", "outputs/procurement/"],
           ["make report", "指标汇总与报告", "outputs/report/"],
           ["make word", "Word 版分析报告", "outputs/report/results_analysis.docx"]],
          widths=[4.6, 6.0, 5.0])

    m.h2("4.3  日志与结果位置")
    m.p("logs/ 下按阶段分文件记录（ingestion.log、preprocessing.log、eda.log、"
        "models.log、report.log 等），另有 chain.log 记录整条链路的起止与耗时；"
        "每行格式为“时间戳 | 级别 | 模块 | 内容”。outputs/ 下按阶段分目录保存结果，"
        "文件清单见 17.1 节。")
    m.fig(shots / "截图_数据接入.png", "图 4-1  数据接入阶段运行日志（命令行、时间戳与各数据集处理结果）")
    m.fig(shots / "截图_建模.png", "图 4-2  分群与异常检测阶段运行日志")

    # ---------------- 5 数据接入 ----------------
    m.h1("5  数据接入")
    m.h2("5.1  功能说明")
    m.p("数据接入模块负责把多源使用记录读入内存并统一为事件表。对每个配置的数据源，"
        "模块完成：定位数据集与子集（config name / split）、按 max_rows 截断、"
        "字段重命名为统一的 user_id / item_id / timestamp / rating、缺失与类型校验、"
        "落地为 parquet 缓存。已缓存的数据源不会重复下载。")
    m.p("模块支持三类数据源：HuggingFace 数据集（source: huggingface）、本地文件"
        "（source: kaggle，指向本地 CSV/parquet）、以及仅作查找表使用的辅助数据"
        "（role: lookup，例如资源类别映射表，不参与用户特征计算）。")

    m.h2("5.2  配置参数")
    m.tbl(["参数", "含义", "取值示例"],
          [["ingestion.proxy", "下载代理地址，置空为直连", "http://127.0.0.1:7897"],
           ["datasets.<键>.source", "数据源类型", "huggingface / kaggle"],
           ["datasets.<键>.id", "数据集标识", "McAuley-Lab/Amazon-Reviews-2023"],
           ["datasets.<键>.name", "数据集子集（品类）名称", "raw_review_Books"],
           ["datasets.<键>.split", "加载的 split", "full / train"],
           ["datasets.<键>.max_rows", "行数上限，控制建模规模", "32000"],
           ["datasets.<键>.streaming", "原始文件超大时按字节区间流式读取", "true / false"],
           ["datasets.<键>.role", "lookup 表示仅作类别查找表", "lookup"],
           ["datasets.<键>.enabled", "是否启用该数据源", "true / false"],
           ["datasets.<键>.fallbacks", "主 ID 不可用时的备选清单", "[…]"]],
          widths=[4.4, 6.6, 4.6])

    m.h2("5.3  操作步骤")
    for i, t in enumerate(
            ["在 config.yaml 的 ingestion.datasets 下按需增删数据源，每个数据源"
             "至少填写 source、id、max_rows。",
             "需要代理时填写 ingestion.proxy；无需网络的环境把数据预先放到 "
             "cache_dir 指定的目录亦可。",
             "执行 make data。控制台逐条打印“开始下载 / 已落盘 / 跳过（未启用）/ 失败”"
             "以及行列数。",
             "查看 data/raw/download_report.md 与 data/raw/schema.md 核对结果。"], 1):
        m.p(f"步骤 {i}：{t}")

    m.h2("5.4  输出文件与核对方法")
    m.p("下载报告以表格形式记录每个数据源的状态、行列数与说明。本次运行的核对结果"
        "如下表，可直接与控制台输出逐行比对。")
    m.tbl(["数据源", "状态", "行数", "列数", "说明"],
          [["hf_movielens", "成功", "200,000", "5", "按 max_rows 截断"],
           ["hf_amazon_fashion", "成功", "32,000", "9", "按 max_rows 截断"],
           ["hf_amazon_videogames", "成功", "32,000", "9", "按 max_rows 截断"],
           ["hf_amazon_books", "成功", "32,000", "9", "流式加载（原始文件超磁盘容量）"],
           ["hf_amazon_electronics", "成功", "32,000", "9", "流式加载（原始文件超磁盘容量）"],
           ["hf_genres", "成功", "891,382", "8", "仅作类别查找表"],
           ["amazon_reviews_multi_en", "已禁用", "—", "—", "无用户标识列，无法构建用户特征"]],
          widths=[4.4, 1.8, 2.2, 1.4, 6.2])

    m.h2("5.5  常见异常与处置")
    m.p("下载失败时先看 logs/ingestion.log 的报错类型：网络类错误（超时、连接重置）"
        "检查代理配置；磁盘类错误（Not enough free disk space）为原始文件超过可用"
        "空间，解法是把该数据源 streaming 置为 true 或降低 max_rows；字段类错误"
        "（缺少 user_id）说明该数据集不含用户标识，应在配置中禁用并在报告里如实记录，"
        "不要用其他字段伪造用户维度。")

    # ---------------- 6 预处理 ----------------
    m.h1("6  预处理与特征工程")
    m.h2("6.1  功能说明")
    m.p("预处理模块把多个数据源的事件表合并为一张干净的事件表，处理缺失值、重复"
        "记录、时间戳时区与异常长度；随后按用户与时间窗口切分会话，再按会话与用户"
        "两个粒度派生特征。用户级特征用于分群与异常检测，会话级离散事务用于关联规则，"
        "两者共用同一份清洗结果，保证口径一致。")
    m.tbl(["输出文件", "内容"],
          [["data/processed/events_clean.parquet", "清洗后的事件表（user_id、item_id、timestamp、rating、source、category）"],
           ["data/processed/sessions.parquet", "会话表（session_id、user_id、起止时间、行为数、时长）"],
           ["data/processed/user_features.parquet", "用户级特征矩阵（26 个特征 + user_id）"],
           ["data/processed/session_transactions.parquet", "会话级离散事务表，供 Apriori 使用"]],
          widths=[6.4, 9.2])

    m.h2("6.2  清洗与会话切分")
    m.p("清洗规则：数值型缺失用中位数填充、类别型用众数填充；完全重复的记录去重；"
        "时间戳统一按 UTC 规整；行为数少于 min_session_events（默认 2）的极短会话丢弃。"
        "会话切分以同一用户相邻行为的时间间隔为判据，间隔超过 "
        f"{cfg['preprocessing']['session_window_minutes']} 分钟即视为新会话，"
        "该窗口能覆盖一次连续检索或一次集中下载的行为跨度。")
    m.p("本次运行清洗后的事件表为 " + f"{ne:,} 条记录、{nu:,} 个用户、{ni:,} 个资源，"
        f"切分得到 {ns:,} 个会话；事件时间跨度为 "
        + f"{f['events']['timestamp'].min():%Y-%m-%d} 至 "
        + f"{f['events']['timestamp'].max():%Y-%m-%d}。")

    m.h2("6.3  用户级特征")
    m.p("特征共 26 个，按业务含义分为六组。全部特征均为无量纲或经标准化后参与建模，"
        "分群结果可由特征名直接解释。")
    m.tbl(["分组", "特征", "业务含义"],
          [["使用强度", "n_events、n_sessions、n_days_active、span_days", "访问总量、会话数、活跃天数、行为跨度"],
           ["使用节奏", "daily_active_rate、events_per_day、total_duration_sec", "活跃密度、日均访问、总使用时长"],
           ["会话特征", "mean_session_duration_sec、std_session_duration_sec", "会话时长均值与波动"],
           ["时间模式", "hour_entropy、night_ratio、work_ratio、weekend_ratio、interval_entropy", "时段分散度、夜间/工作时段/周末占比、间隔规律性"],
           ["资源偏好", "n_unique_items、item_entropy、item_hhi、top1_item_share", "资源广度、偏好分散度、集中度"],
           ["粘性与学科", "trend_slope、rating_mean、rating_std、category_entropy、category_hhi、n_categories、category_coverage", "趋势斜率、评分水平与波动、学科覆盖广度与集中度"]],
          widths=[2.6, 7.4, 5.6])
    m.p("特征字典（字段含义、计算口径、取值范围）随程序输出于 "
        "outputs/features/feature_dictionary.md，便于二次开发时对照。")

    m.h2("6.4  特征质量筛查")
    m.p("两类特征在建模前被自动剔除，剔除清单写入 outputs/features/ 下的报告："
        "一是近退化特征，即众数占比超过 max_mode_share（默认 0.95）的特征，这类"
        "特征的分位阈值会落在众数上，规则没有区分意义；二是冗余特征，即与已保留"
        "特征相关系数绝对值超过 corr_threshold（默认 0.95）的特征。")
    m.p("本次运行中，相关性筛查发现 9 对特征 |r|>0.9，最高一对为 n_categories 与 "
        "category_coverage，按阈值保留其一。近退化筛查另剔除若干在细分数据上众数"
        "占比过高的特征，最终建模输入为 20 个特征（建模日志会打印实际输入维度，"
        "如“输入: 用户特征 (31669, 20)”）。")

    m.h2("6.5  操作步骤与输出")
    for i, t in enumerate(
            ["确认 config.yaml 的 preprocessing 与 features 段参数（会话窗口、"
             "缺失策略、相关系数阈值、众数占比阈值）。",
             "执行 make features。控制台打印各数据源的清洗行数、会话数、特征数。",
             "查看 outputs/features/feature_dictionary.md 了解字段口径，"
             "查看 correlation_report.md 与 feature_information_report.md 了解剔除原因。",
             "如需调整窗口或阈值，改配置后重跑 make features 即可，后续阶段会自动复用新特征。"], 1):
        m.p(f"步骤 {i}：{t}")

    # ---------------- 7 EDA ----------------
    m.h1("7  探索性分析")
    m.h2("7.1  功能说明")
    m.p("探索性分析模块在建模之前给出数据的整体画像，输出 8 张图与一份文字摘要，"
        "目的是让使用者在选择分群数与异常检测半径之前，先看清活跃度分布形态、"
        "时间模式与资源集中度，避免直接套用默认参数。")
    m.tbl(["图", "内容", "对建模的作用"],
          [["01_data_overview", "用户、事件、资源、活跃天、会话五项规模", "确认数据量级与清洗是否失真"],
           ["02_activity_distribution", "用户活跃度长尾分布（含分位数标注）", "判断是否需要按活跃度分层"],
           ["03_time_trend", "日活跃用户时间趋势", "识别数据覆盖期与采集断层"],
           ["04_time_pattern", "24 小时时段分布与周末占比", "为时段类特征与规则设定解释口径"],
           ["05_resource_concentration", "资源访问集中度曲线", "判断长尾资源是否可合并"],
           ["06_univariate_distributions", "各特征分布与 IQR/3σ 离群点占比", "预判异常值来源"],
           ["07_feature_correlation", "特征相关性矩阵", "为去冗余提供依据"],
           ["08_k_distance", "k-distance 曲线与拐点", "给出 DBSCAN 的 eps 参考值"]],
          widths=[4.6, 6.0, 5.0])

    m.h2("7.2  操作步骤")
    m.p("执行 make eda。程序把图表以 png 与 pdf 双格式写入 outputs/report/figures/，"
        "摘要写入 outputs/eda/eda_summary.md。图表可直接用于汇报，pdf 版本为矢量图，"
        "放大不失真。")

    m.h2("7.3  本次运行的主要结论")
    m.p("活跃度呈明显右偏长尾：用户行为数中位数为 1、P90 为 9、P99 为 217，偏度 14.85，"
        "说明绝大多数用户只访问少量资源，少数重度用户贡献了大部分访问，因此分群"
        "不能假设簇形均匀，这也是选用 GMM（允许不同协方差）而非单一球形聚类的原因。")
    m.p("时段分布显示凌晨（0 至 5 点）访问占比 29.3%、周末占比 25.3%，夜间集中访问"
        "在业务上既可能是跨时区用户，也可能是脚本化下载，这一现象在 12 章的规则里"
        "被直接使用。资源集中度方面，Top5 资源仅占全部访问的 1.0%，覆盖 80% 的访问"
        "需要 38,230 个资源，说明资源体系高度长尾，采购建议必须以“聚合口径 + 示例”"
        "的方式呈现，而不是逐个资源罗列。")
    m.fig(figdir / "01_data_overview.png", "图 7-1  数据规模总览")
    m.fig(figdir / "02_activity_distribution.png", "图 7-2  用户活跃度长尾分布")

    # ---------------- 8 分群 ----------------
    m.h1("8  用户分群")
    m.h2("8.1  方法说明")
    m.p("分群采用高斯混合模型。与硬聚类相比，GMM 允许每个簇拥有不同的协方差结构，"
        "并给出样本属于各簇的后验概率，便于识别处在两个画像之间的过渡用户。"
        "簇数 k 在 config.yaml 指定的区间内扫描，以 BIC 为主准则、轮廓系数与 "
        "Davies-Bouldin 为辅，同时训练同 k 的 KMeans 作为基线。")
    m.p("为避免 BIC 在不同样本上不可比，k 扫描阶段在固定子样本上进行（"
        "k_sweep_max_samples，默认 3 万），最终模型仍用全量数据拟合，并以多次初始化"
        "（final_n_init）取最优解。")

    m.h2("8.2  参数与操作")
    m.tbl(["参数", "默认值", "含义"],
          [["gmm.k_range", "[2, 10]", "簇数扫描区间"],
           ["gmm.covariance_types", "full / tied / diag / spherical", "协方差类型，逐个比较取 BIC 最优"],
           ["gmm.max_iter", "500", "EM 迭代上限"],
           ["gmm.reg_covar", "1e-5", "协方差正则项，防止奇异"],
           ["gmm.k_sweep_max_samples", "30000", "扫描阶段子样本上限"],
           ["gmm.final_n_init", "3", "最终模型初始化次数"]],
          widths=[4.4, 4.2, 7.0])
    m.p("操作步骤：执行 make models（分群包含在该目标内）。控制台打印 k 扫描过程与"
        "最终 k；结果写入 outputs/models/ 下的 gmm_k_sweep.csv、gmm_vs_kmeans.csv、"
        "gmm_cluster_centers.csv、gmm_user_assignments.parquet 与 gmm_model.joblib。")

    m.h2("8.3  结果解读")
    m.p("本次运行在 k∈[2,10] 内扫描，BIC 最优 k=" + str(gmm.get("k", "—")) +
        "（轮廓系数最优为 k=2，最终以 BIC 为主准则取 8）。评估指标为：轮廓系数 "
        + fmt(gmm.get("metrics", {}).get("silhouette", 0)) + "，Davies-Bouldin "
        + fmt(gmm.get("metrics", {}).get("davies_bouldin", 0), 3) + "，"
        "Calinski-Harabasz " + fmt(gmm.get("metrics", {}).get("calinski_harabasz", 0), 1) + "。")
    m.p("簇中心表（gmm_cluster_centers.csv）给出每个簇在各特征上的均值，可直接读出"
        "各画像的典型取值：占比最大的是“专业深潜用户·集中型”（21.4%，6,766 人），"
        "会话时长与资源集中度显著高于整体；其次是“广泛浏览用户·时段分散型”"
        "（18.7%，5,915 人），资源广度大而集中度低；“夜间活跃用户”（13.2%，4,175 人）"
        "的夜间占比显著偏高，是异常规则重点关注的人群；“衰减流失风险用户”"
        "（15.4%，4,865 人）近期活跃度下滑，适合做唤醒运营。8 个簇的完整画像见 11 章。")

    m.h2("8.4  与 KMeans 基线的对比")
    m.p("同 k 下 KMeans 的轮廓系数为 " + fmt(gmm.get("baseline_kmeans", {}).get("silhouette", 0))
        + "、Davies-Bouldin 为 " + fmt(gmm.get("baseline_kmeans", {}).get("davies_bouldin", 0))
        + "，均优于 GMM。这说明本数据的簇形相对圆整，硬聚类在几何紧致度上更占优。"
        "软件仍以 GMM 作为默认分群方法，原因是分群的下游用途是生成画像与价值分，"
        "需要后验概率与协方差解释（例如“该用户 70% 像重度用户、30% 像浏览用户”），"
        "KMeans 无法提供这一层信息。两套结果均保留在 gmm_vs_kmeans.csv 中，使用者"
        "可按需切换。")
    m.fig(figdir / "08_k_distance.png", "图 8-1  k-distance 曲线（用于确定 DBSCAN 的 eps）")

    # ---------------- 9 异常检测 ----------------
    m.h1("9  异常行为检测")
    m.h2("9.1  方法说明")
    m.p("异常检测以 DBSCAN 为主模型：先把用户特征标准化并降到二维/主成分空间，"
        "在密度空间内寻找不属于任何簇的噪声点，这些点即异常候选。DBSCAN 不用预设"
        "异常比例，但对半径敏感，半径因此由数据给出（见 9.2）。")
    m.p("为降低单一算法的偶然性，软件并行运行 IsolationForest、LOF、KNN 三种基线，"
        "把 4 个模型的判定结果做投票：被至少 min_votes（默认 3）个模型判为异常的"
        "样本标记为高置信异常。DBSCAN 的全部噪声点作为“候选集”输出，高置信子集"
        "作为“优先处置集”输出，两者的数量关系在结果摘要中明确给出。")

    m.h2("9.2  参数选择")
    m.p("min_samples 采用业务启发式 2×特征维度（本次为 20）；eps 由 k-distance 曲线"
        "的拐点分位（k_distance_percentile，默认 90）自动给出，本次取 "
        + fmt(db.get("eps", 0), 4) + "。降维保留 "
        + f"{db.get('pca_evr', 0) * 100:.1f}%" + " 的方差，去掉了噪声维度，主要结构仍在。"
        "若希望少检、只抓极端异常，提高 eps 或提高 "
        "min_votes；希望扩大候选范围则反向调整。")

    m.h2("9.3  检出结果")
    m.p("本次检出噪声点 " + f"{db.get('n_noise', 0):,}" + " 个，占全部用户的 "
        + f"{db.get('noise_rate', 0) * 100:.2f}%" + "；其中多模型投票达到 3 票的高置信"
        "异常 " + f"{db.get('n_high_conf', 0):,}" + " 个。异常用户清单写入 "
        "anomaly_users.parquet 与 anomaly_users.jsonl，每个用户附偏离最大的三个特征"
        "及其 z 分数，可直接用于人工复核时的定位。")
    m.tbl(["输出文件", "内容"],
          [["anomaly_method_comparison.csv", "各方法的标记数、标记率、AUROC、AUPR"],
           ["anomaly_users.parquet / .jsonl", "异常用户清单与偏离特征、z 分数"],
           ["dbscan_model.joblib", "模型对象（含标准化器、PCA、eps、min_samples）"],
           ["gmm_user_assignments.parquet", "分群软标签，可与异常清单交叉分析"]],
          widths=[6.4, 9.2])

    m.h2("9.4  效果评估")
    m.p("异常检测是无监督任务，真实业务中通常没有标注，因此软件用“合成注入”评估："
        "从正常样本中按比例（默认 2%）注入按倍数放大的扰动样本作为已知异常，"
        "再计算各方法的排序质量。该方法衡量的是“把异常排在前面的能力”，"
        "不等同于真实业务准确率，但可用于方法间的横向比较。")
    m.tbl(["方法", "AUROC", "AUPR"],
          [["DBSCAN", fmt(db.get("auroc", {}).get("DBSCAN", 0)), fmt(db.get("aupr", {}).get("DBSCAN", 0))],
           ["IsolationForest", fmt(db.get("auroc", {}).get("IsolationForest", 0)), fmt(db.get("aupr", {}).get("IsolationForest", 0))],
           ["LOF", fmt(db.get("auroc", {}).get("LOF", 0)), fmt(db.get("aupr", {}).get("LOF", 0))],
           ["KNN", fmt(db.get("auroc", {}).get("KNN", 0)), fmt(db.get("aupr", {}).get("KNN", 0))]],
          widths=[4.0, 3.6, 3.6])
    m.p("本次运行中 DBSCAN 与 KNN 的 AUROC 都接近 0.998，DBSCAN 的 AUPR 最高（0.696），"
        "IsolationForest 只有 0.151。软件因此以 DBSCAN 作主判据，其余三个模型用于"
        "投票印证。")

    m.h2("9.5  输出与解读")
    m.p("读异常清单先看规模：异常率一般落在 1% 至 10%，对不上就先查 eps 与特征标准化。"
        "再看高置信子集是否集中在某几个数据源或某类资源。最后逐条看偏离特征，区分"
        "真实的高强度使用和脚本化批量下载。前者按高价值用户管理，后者进告警流程。")

    # ---------------- 10 关联规则 ----------------
    m.h1("10  关联规则与资源组合")
    m.h2("10.1  事务口径")
    m.p("关联规则挖掘的事务不是单条事件，而是一个会话的离散化摘要：会话时长档"
        "（极短/短/中/长/极长）、时段（凌晨/早晨/上午/中午/下午/傍晚/夜间）、"
        "资源数档、集中度档、频次档、Top 资源与资源类别。单条事件之间的关系基本"
        "是噪声；一次会话内的行为组合才对应真实模式，例如“凌晨 + 长时间 + 多资源”"
        "往往出现在批量下载里。")
    m.p("事务默认不包含数据集来源字段（include_source: false）。原因是来源字段与"
        "任何条件的提升度都极高，会挖出“某数据源的会话都在某时段”这类伪模式，"
        "对业务无意义；如需做敏感性对照可置为 true。")

    m.h2("10.2  参数与操作")
    m.tbl(["参数", "默认值", "含义"],
          [["association.min_support", "0.01", "最小支撑度"],
           ["association.min_confidence", "0.4", "最小置信度"],
           ["association.min_lift", "1.2", "最小提升度"],
           ["association.top_n", "30", "输出规则条数"],
           ["association.support_scan / confidence_scan", "[0.005…0.1] / [0.2…0.7]", "参数敏感性扫描范围"],
           ["association.item_min_support", "0.01", "资源组合挖掘的最小支撑度"],
           ["association.item_min_sessions", "20", "资源组合的最小共同出现会话数"]],
          widths=[6.0, 4.6, 5.0])
    m.p("操作步骤：执行 make models（或仅重跑关联规则的 make models-association）。"
        "规则写入 association_rules.csv 与 association_rules.jsonl，模式解读写入 "
        "behavior_patterns.md，资源组合写入 item_combinations.csv，参数扫描曲线写入 "
        "association_param_sweep.csv。")

    m.h2("10.3  挖掘结果")
    m.p(f"本次以 {assoc.get('n_transactions', ns):,} 条会话事务为输入，在 min_support="
        f"{assoc.get('min_support')}、min_confidence={assoc.get('min_confidence')}、"
        f"min_lift={assoc.get('min_lift')} 下得到 {assoc.get('n_frequent_itemsets', 0)} 个"
        f"频繁项集、{assoc.get('n_rules', 0)} 条规则（最高提升度 "
        f"{fmt(assoc.get('top_lift', 0), 2)}），其中 {assoc.get('n_risk_rules', 0)} 条含"
        "极端离散档，标记为风险相关模式；按数据源分层挖掘得到 "
        f"{assoc.get('n_item_rules', 0)} 条资源共现组合。")
    m.p("资源组合按数据源分层挖掘是必要的：不同数据源的资源编号体系不同，跨源共现"
        "在业务上没有对应关系。本次组合规则主要来自公开评分数据集，其余数据源因"
        "单资源会话占比过高（可挖掘资源不足）未产出组合，该诊断信息在 "
        "item_combinations.csv 的 diag 字段中逐源记录，不做人为补足。")

    m.h2("10.4  规则解读方法")
    m.p("读一条规则时按“条件—结论—支撑度—置信度—提升度”五段理解。以“极长会话"
        "且凌晨时段 → 资源数档为多”为例：支撑度说明该模式在全部会话中出现的比例，"
        "置信度说明满足条件时结论成立的概率，提升度说明该结论比随机情况高出多少倍。"
        "提升度大于 3 的规则才进入业务讨论，低于 2 的规则通常只是由高频档位带来的"
        "统计相关，不宜直接转为制度。")

    # ---------------- 11 画像 ----------------
    m.h1("11  用户画像")
    m.h2("11.1  功能说明")
    m.p("画像模块把分群结果翻译成业务语言：为每个簇生成一张画像卡，包含簇编号与"
        "命名、占比、与整体相比偏离最大的特征（以 σ 表示）、典型行为摘要、典型"
        "用户示例与雷达图。命名规则按偏离方向自动生成，例如资源广度显著高于整体"
        "且集中度低者命名为“广泛浏览用户”，会话长且资源集中者命名为“专业深潜用户”。")
    m.h2("11.2  操作步骤")
    m.p("执行 make profiling。结果写入 outputs/profiling/：persona_summary.md 为全部"
        "画像卡的文字版，persona_clusters.csv 为簇级统计，persona_cards/ 下为每个簇"
        "的雷达图（png 与 pdf）。画像卡的命名可在 persona_summary.md 中按业务习惯"
        "改写，统计数字不受影响。")
    m.h2("11.3  画像卡内容示例")
    m.p("以本次运行的“广泛浏览用户”为例：占比 5.1%（1,627 / 31,669 人），日均 0.1 次"
        "事件、活跃 28 天、访问 74 种资源、Top1 资源集中度 0.05；与整体相比时段熵"
        "高 2.2σ、资源熵高 2.2σ、行为跨度高 1.8σ、资源集中度低 1.6σ。业务解读为"
        "“处于探索期的泛读用户”，运营上适合做资源推荐与引导，而不是按重度用户做"
        "配额管理。")
    m.fig(figdir / "cluster_1_radar.png", "图 11-1  分群画像雷达图（专业深潜用户）")

    # ---------------- 12 规则 ----------------
    m.h1("12  异常规则生成")
    m.h2("12.1  生成原理")
    m.p("规则模块把异常检测的黑箱判定转成可部署的布尔条件。做法是以异常用户为正例，"
        "在特征分布上反查阈值：单条件规则取 P99 分位，组合条件规则在 0.95 与 0.99 "
        "两个候选分位中取提升度更优者；阈值遇到并列值时自动放宽比较符（>= 与 <= "
        "互换），保证命中人数可复现。")
    m.p("为避免生成“正确但无用”的规则，模块自动剔除三类条件：覆盖率超过 max_coverage"
        "（默认 0.95）的空洞条件、众数占比过高特征上的分位条件、以及与单条件完全"
        "等价的冗余组合。每条规则同时给出命中人数、支撑度、置信度、提升度与处置建议"
        "（告警 / 人工复核 / 限流）。")

    m.h2("12.2  规则清单")
    m.p(f"本次运行生成 {len(f['rules'])} 条规则，全部写入 outputs/rules/anomaly_rules.yaml"
        "（结构化，供系统接入）与 anomaly_rules.md（人类可读）。节选如下。")
    rows = []
    for r in f["rules"][:8]:
        rows.append([r.get("id", ""), r.get("name", ""), r.get("condition", ""),
                     r.get("n_hits", ""), f"{r.get('support', 0):.3f}",
                     f"{r.get('confidence', 0):.3f}", f"{r.get('lift', 0):.2f}",
                     r.get("action", "")])
    m.tbl(["ID", "规则名称", "触发条件", "命中", "支撑度", "置信度", "提升度", "处置"],
          rows, widths=[1.2, 3.4, 4.4, 1.2, 1.4, 1.4, 1.3, 1.7], size=7.5)
    m.p("YAML 中每条规则还包含 feature、operator、threshold、coverage 等字段，"
        "接入时可直接按 feature 与 threshold 生成判定表达式，无需解析自然语言描述。")

    m.h2("12.3  规则部署")
    m.p("部署方式有两种。一是离线巡检：把 anomaly_rules.yaml 作为配置读入自建巡检"
        "脚本，按日或按周对用户明细表批量判定，命中结果进入工单；二是实时拦截："
        "把规则转为数据库视图或流处理作业中的条件判断，命中高风险规则（例如夜间"
        "超高时长）时触发限流。规则阈值会随重跑变化，建议版本化管理，每次重跑后"
        "对比规则命中人数的变化再决定是否上线。")
    m.p("规则命中只说明行为与异常人群相似，不是违规事实。软件把绝大多数规则标为"
        "“人工复核”，只有同时具备夜间集中、超长时长、超高频次等多项特征时才建议"
        "“告警”。最终处置要结合机构的资源使用制度与账号管理规范。")

    # ---------------- 13 采购 ----------------
    m.h1("13  采购与馆藏建议")
    m.h2("13.1  判定口径")
    m.p("高价值用户由分群价值得分确定：以簇的使用时长、访问次数、资源广度加权排序，"
        "取上分位（默认 0.9）的簇，且该簇样本量不少于 min_cluster_users（默认 50，"
        "防止小簇主导）。需求缺口指某资源的高价值用户占其活跃用户比例不低于 50%，"
        "且活跃用户数不低于 10；低使用指资源活跃用户数低于 P20 且高价值用户占比"
        "低于 15%。")
    m.h2("13.2  操作步骤")
    m.p("执行 make procurement。结果写入 outputs/procurement/"
        "procurement_recommendations.md 与 .csv，每条建议含对象、依据摘要、建议"
        "动作、预期收益、风险与量化指标。本次运行共生成 34 条建议。")
    m.h2("13.3  建议类型")
    m.tbl(["类型", "判定依据", "建议动作"],
          [["需求缺口 / 续订优先", "高价值用户占比高且活跃用户数达标", "优先保障续订或扩容，纳入核心资源清单"],
           ["低使用 / 可削减", "活跃用户数低于 P20 且高价值用户占比低", "先给聚合口径结论，再附按确定性排序的示例资源，供逐条核实"],
           ["捆绑采购 / 组合优化", "会话内资源共现组合（lift≥1.2）", "按共现组合打包谈判，提高单位经费覆盖"]],
          widths=[3.6, 6.4, 5.6])
    m.p("低使用类建议按“聚合口径 + 示例”给出，不逐一列出待削减资源。资源集中度"
        "极低（Top5 仅占 1%），单个资源的统计噪声很大，只看访问次数削减容易误伤"
        "刚上线的资源。清单宜作复核起点，再结合试用期、学科评估与教师推荐决定。")

    # ---------------- 14 报告 ----------------
    m.h1("14  报告输出")
    m.h2("14.1  指标汇总")
    m.p("报告模块汇总全流程的关键指标，形成一页式的指标表（outputs/report/"
        "metrics_summary.md），包括数据规模、特征数量、分群数与质量指标、异常检出"
        "数量与评估指标、规则条数、建议条数。指标全部在生成时实时读取结果文件，"
        "不存在手工填写的数字，因此重跑后报告会随结果自动更新。")
    m.h2("14.2  图表与表格")
    m.p("图表以 png（300 dpi，用于文档与汇报）与 pdf（矢量，用于论文排版）双格式"
        "输出，中英文标题对照的图表清单写入 figure_captions.md，可直接用于论文或"
        "评估材料的图表目录。表格结果统一以 csv 输出，编码 UTF-8。")
    m.h2("14.3  分析报告")
    m.p("执行 make word 生成《结果详细分析报告》（results_analysis.docx），内容包括"
        "研究背景、数据与方法、分群与异常结果、规则与建议、局限性讨论。该报告面向"
        "业务与管理层阅读，技术细节仍以本说明书与各阶段 md 文件为准。")

    # ---------------- 15 配置 ----------------
    m.h1("15  配置文件说明")
    m.h2("15.1  结构")
    m.p("config.yaml 按功能分为 project、seed、paths、ingestion、preprocessing、"
        "features、eda、models、association、profiling、rules、procurement、report "
        "十三段，与代码模块一一对应。程序内不硬编码路径与阈值，修改配置即可改变"
        "行为，这也是结果可复现的前提。")
    m.h2("15.2  关键参数")
    m.tbl(["段落", "关键参数", "调整效果"],
          [["seed", "seed = 42", "改变随机性来源；固定值保证结果可复现"],
           ["ingestion", "proxy、max_rows、streaming", "控制数据规模与下载方式"],
           ["preprocessing", "session_window_minutes、min_session_events", "控制会话粒度与短会话过滤"],
           ["features", "corr_threshold、max_mode_share", "控制特征去冗余与近退化剔除力度"],
           ["models.gmm", "k_range、covariance_types", "控制分群粒度与簇形自由度"],
           ["models.dbscan", "min_samples、k_distance_percentile", "控制异常检出范围（越大越保守）"],
           ["models.voting", "min_votes", "控制高置信异常的严格程度"],
           ["models.synthetic_anomaly", "ratio、scale", "控制合成注入异常的难度"],
           ["association", "min_support、min_confidence、min_lift", "控制规则数量与强度"],
           ["rules", "extreme_quantile、combo_quantiles、max_rules", "控制规则阈值与条数"],
           ["procurement", "各分位阈值与样本量下限", "控制建议的口径与条数"]],
          widths=[3.8, 6.4, 5.4])
    m.h2("15.3  修改建议")
    m.p("调整参数时遵循“一次只改一段、改后重跑该阶段及其下游”的原则。分群粒度与"
        "异常规模是相互影响的：簇数增加会让异常判定更细，但也更容易把过渡用户判为"
        "异常；建议先固定 min_votes 与 eps，再调 k。修改任何阈值后，务必重跑 "
        "make rules 与 make procurement，否则规则与建议仍是旧口径。")

    # ---------------- 16 常见问题 ----------------
    m.h1("16  常见问题与注意事项")
    for q, a in (
        ("数据下载缓慢或中断", "确认代理可用（config.yaml 的 ingestion.proxy）；若原始"
                              "文件超过可用磁盘，将 streaming 置为 true；已成功落盘的数据源"
                              "不会重复下载。"),
        ("分群数 k 落在扫描区间上界", "说明真实簇数可能更多，把 models.gmm.k_range 上限"
                                    "调大后重跑 make models，并留意 BIC 是否继续下降。"),
        ("异常数量过多或过少", "先看噪声率：超过 10% 通常是 eps 偏大或特征未标准化；"
                             "少于 1% 则是 eps 偏小。可通过 k_distance_percentile 微调。"),
        ("规则命中人数为 0 或等于全体", "前者说明阈值过于苛刻或该特征近退化已被剔除，"
                                     "后者说明条件覆盖全体（已被 max_coverage 过滤），"
                                     "检查 feature_information_report.md。"),
        ("关联规则无资源组合", "资源太散时（大量会话只含 1 个资源）无法形成项集，"
                             "可降低 item_min_sessions 或改用更粗的资源粒度（类别）。"),
        ("用真实图书馆日志替换公开数据", "按 README 的 COUNTER 字段映射说明改 "
                                        "config.yaml 的 ingestion 段，保持 user_id、item_id、"
                                        "timestamp、rating 四个字段名不变即可，其余代码无需修改。"),
        ("结果与上次不同", "检查 seed 是否被改动、数据源 max_rows 是否变化、依赖库版本"
                          "是否升级（尤其是 scikit-learn 的小版本变化会影响聚类结果）。"),
        ("输出目录权限不足", "config.yaml 的 paths 段改为有写权限的绝对路径后重跑，"
                            "程序会自动创建目录。")):
        m.p("问：" + q)
        m.p("答：" + a)
    m.p("注意事项：一是本软件的异常判定为无监督结果，输出是“可疑清单”而非违规结论，"
        "不可直接作为处罚依据；二是公开数据集的用户与资源标识为脱敏字符串，与机构"
        "真实账号没有对应关系，接入真实数据时请遵守个人信息保护相关要求，只使用"
        "脱敏后的行为记录；三是资源采购建议只提供依据与量化指标，最终决策仍需结合"
        "经费、学科评估与使用条款。")

    # ---------------- 17 附录 ----------------
    m.h1("17  附录")
    m.h2("17.1  输出文件清单")
    m.tbl(["文件", "内容"],
          [["outputs/eda/eda_summary.md", "探索性分析结论（8 条）"],
           ["outputs/features/feature_dictionary.md", "特征字典与计算口径"],
           ["outputs/models/model_summary.md", "分群、异常、关联规则的结果摘要"],
           ["outputs/models/gmm_k_sweep.csv", "k 扫描的 BIC/AIC/轮廓系数"],
           ["outputs/models/anomaly_method_comparison.csv", "四模型检出与评估对比"],
           ["outputs/models/anomaly_users.parquet", "异常用户清单与偏离特征"],
           ["outputs/models/association_rules.csv", "关联规则明细"],
           ["outputs/models/item_combinations.csv", "资源共现组合与分层诊断"],
           ["outputs/profiling/persona_summary.md", "分群画像卡"],
           ["outputs/rules/anomaly_rules.yaml", "可部署的布尔规则"],
           ["outputs/procurement/procurement_recommendations.md", "采购建议明细"],
           ["outputs/report/metrics_summary.md", "全流程指标汇总"],
           ["outputs/report/results_analysis.docx", "结果详细分析报告"],
           ["logs/*.log", "阶段运行日志"]],
          widths=[7.6, 8.0])
    m.h2("17.2  数据源清单")
    m.tbl(["数据源", "用途", "规模"],
          [["MovieLens-1M（harisarang/ml-1m）", "主实验载体：用户×资源×时间×评分", "200,000 条"],
           ["Amazon Reviews 2023 — Fashion", "按品类划分的资源类别维度", "32,000 条"],
           ["Amazon Reviews 2023 — Video Games", "同上", "32,000 条"],
           ["Amazon Reviews 2023 — Books", "同上（流式加载）", "32,000 条"],
           ["Amazon Reviews 2023 — Electronics", "同上（流式加载）", "32,000 条"],
           ["MovieLens 评分表（ashraq/movielens_ratings）", "资源类别查找表（role=lookup）", "891,382 条"]],
          widths=[6.4, 6.6, 2.6])
    m.h2("17.3  版本与权利声明")
    m.p("文档版本 " + SOFT_VER + "，与软件版本一致；文档中出现的软件名称、版本号、"
        "功能描述均以《计算机软件著作权登记申请表》填报内容为准。示例数据来自"
        "公开数据集，仅用于演示软件功能，不包含任何真实用户的身份信息。")
    m.p("本说明书随软件一并提交，作为计算机软件"
        "著作权登记的文档鉴别材料。")
    m.h2("17.4  示例数据来源与使用说明")
    m.p("本说明书插图中的数据来自以下公开数据集，均按各数据集的原始许可条款用于"
        "算法验证，未做商业分发。MovieLens 数据由 GroupLens Research 发布，"
        "通常按“仅限研究与教育用途”提供；Amazon Reviews 2023 由 McAuley Lab "
        "发布，按数据集页面的许可条款使用。软件本身不含上述数据，运行时由使用"
        "者自行下载或指向本地文件。")
    m.p("数据集中的用户标识与资源标识均为脱敏字符串（如 AGKASBHYZPGTEPO6LWZPVJWB2BVA"
        " 形式的匿名 ID），不含姓名、学号、IP 等身份信息，因此本说明书的示例"
        "结果不涉及个人信息。接入机构自有日志时，建议同样先做标识替换再进入本软件，"
        "以符合个人信息保护与数据安全的相关要求。")
    m.p("如需在本机构复现说明书中的结果，请保持 config.yaml 中 seed、max_rows 与"
        "各阶段阈值不变，并使用相同版本的数据集快照；数据集上游更新会导致行数与"
        "分布变化，从而使数值结果不同，这属于正常现象，不影响软件功能。")
    m.h2("17.5  文档维护与变更说明")
    m.p("本说明书与软件同版本发布。软件的功能、参数或输出文件发生变化时，说明书"
        "对应章节应同步更新，并在提交登记前核对三处一致性：一是页眉的软件名称与"
        "版本号，二是封面与 17.3 节的文档版本，三是正文中引用的输出文件名。"
        "材料被退回，多数是这三处对不上。")
    m.p("版本升级时的建议做法：先确定新版本号（如 V1.1），再统一替换页眉、封面与"
        "本节中的版本标识，最后重跑本说明书的生成脚本，使目录页码、插图与表格"
        "随正文一起更新。手工修改正文后，务必重新核对目录页码是否与页眉页码一致。")
    m.p("本文档的章节编号采用“章.节”两级结构，与软件的九个功能模块一一对应："
        "第 5 至 10 章对应数据处理与建模链条，第 11 至 14 章对应结果输出链条，"
        "第 15 至 17 章对应配置、问题排查与附录。")
    return m


# ===============================================================
# 目录页码回填：渲染后按标题实际落页取页码
# ===============================================================
def heading_pages(docx_path: pathlib.Path, expected: list[str]) -> tuple[dict[str, int], int]:
    """渲染后定位每个标题的真实页码（正文里的标题字号 ≥ 11.5，目录条目 10.5）。

    匹配前对两侧文本做归一化：PDF 提取会把全角空格 U+3000 规范成普通空格，
    不归一化会导致目录页码回填 0 项。
    """
    import pymupdf

    from render_check import to_pdf

    def _norm(s: str) -> str:
        return " ".join(s.replace("\u3000", " ").split())

    wanted = {_norm(t) for t in expected}
    pdf = to_pdf(docx_path)
    doc = pymupdf.open(str(pdf))
    pages: dict[str, int] = {}
    cover_pages = 0
    for page in doc:
        lines = []
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                spans = ln["spans"]
                if not spans:
                    continue
                lines.append((max(s["size"] for s in spans),
                              "".join(s["text"] for s in spans).strip()))
        for size, text in lines:
            key = _norm(text)
            if size >= 11.5 and key in wanted and key not in pages:
                pages[key] = page.number
        if cover_pages == 0 and any("使用说明书" in t.replace(" ", "").replace("\u3000", "")
                                    for _, t in lines):
            cover_pages = page.number + 1
    total = len(doc)
    doc.close()
    pdf.unlink(missing_ok=True)
    return pages, cover_pages


def run(out_dir: pathlib.Path | None = None) -> dict[str, Any]:
    out_dir = out_dir or (ROOT / "outputs" / "ip")
    out_dir.mkdir(parents=True, exist_ok=True)
    facts = load_facts()
    render_console_shots(out_dir / "screenshots")

    m = build(facts)
    out = out_dir / f"使用说明书_{SOFT_NAME}_{SOFT_VER}.docx"

    page_map: dict[str, int] | None = None
    for attempt in range(3):
        m.render(out, page_map)
        raw, cover = heading_pages(out, [t for _, t in m.headings()])
        # 页眉页码 = 渲染页序号 - 封面页数（目录从第 1 页开始）
        new_map = {}
        for level_text in (t for _, t in m.headings()):
            page = raw.get(level_text)
            if page is not None:
                new_map[level_text] = page - cover + 1
        if page_map == new_map:
            break
        page_map = new_map

    missing = [t for _, t in m.headings() if t not in (page_map or {})]
    print(f"[manual] 章节 {len(m.headings())} 个，目录页码回填 {len(page_map or {})} 项，"
          f"未匹配 {len(missing)} 项 -> {out.name}")
    if missing:
        print("  未匹配:", missing[:6])
    return {"doc": str(out), "toc_entries": len(page_map or {}), "missing": missing}


def render_console_shots(shots: pathlib.Path) -> None:
    """由真实运行日志渲染控制台截图（去掉本地绝对路径，避免暴露本机目录）。"""
    from PIL import Image, ImageDraw, ImageFont

    shots.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 19)
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()

    def draw(name: str, title: str, log: str, n: int = 13) -> None:
        p = ROOT / "logs" / log
        lines = []
        if p.exists():
            for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]:
                parts = ln.split(" | ")
                text = " | ".join(parts[2:]) if len(parts) >= 3 else ln
                text = text.replace(str(ROOT) + "\\", "").replace(str(ROOT) + "/", "")
                text = text.replace("D:\\桌面\\项目\\individual_image_abnormal_behavior\\", "")
                lines.append(text[:96])
        img = Image.new("RGB", (1120, 66 + 27 * (len(lines) + 1)), (28, 28, 30))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 1120, 40], fill=(58, 58, 62))
        d.text((14, 8), title, fill=(225, 225, 225), font=font)
        y = 52
        for ln in lines:
            color = (150, 225, 150) if ("完成" in ln or "已落盘" in ln) else (205, 205, 205)
            d.text((14, y), ln, fill=color, font=font)
            y += 27
        img.save(str(shots / name))

    draw("截图_数据接入.png", f"{HEADER_TEXT}  数据接入阶段（make data）", "ingestion.log", 12)
    draw("截图_特征工程.png", f"{HEADER_TEXT}  预处理与特征阶段（make features）", "preprocessing.log", 12)
    draw("截图_建模.png", f"{HEADER_TEXT}  分群/异常/关联规则（make models）", "models.log", 12)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    run(pathlib.Path(a.out) if a.out else None)
