# 破壁中东 · 中阿英跨语言舆情语料库与智能品牌诊断系统

> 对应方案：`docs/方案B-中阿英跨语言舆情语料库与智能品牌诊断系统-详细设计方案.md`
> 底层规划：`docs/挑战杯选题升级与多语种语料库建设完整规划(1).docx`

## 项目结构

```
├── docs/          # 方案、规划、爬取框架方案、系统搭建指南等文档
├── archive/       # 旧文件归档（原方案一/二及相关素材）
├── collector/     # ★ 可穷尽多源爬取框架（配置驱动、可复现、带审计日志）
├── corpus/        # 语料数据（raw 原始 / processed 清洗 / aligned 对齐 / meta 元数据）
├── annotation/    # 标注体系（guidelines 手册 / llm_annotator / active_learning / agreement）
├── models/        # 模型研发（training 微调脚本 / evaluation 评测脚本）
├── backend/       # ★ FastAPI 后端 v0.5（已实测：统计/检索/KWIC/品牌/合规）
├── frontend/      # ★ React 前端 v0.5 源码（npm install && npm run dev）
└── deployment/    # docker-compose 部署（二期）
```

## 快速开始（爬虫试采）

```bash
cd collector
pip install -r requirements.txt
# 快速试采（Google News 通道，约 10 分钟）
python run_trial.py --no-gdelt --max-per-query 5
# GDELT 夜间批跑（限速 30s/请求，约 30 分钟）
python run_trial.py --no-gnews --max-per-query 50
# 只跑某几个源 / 某几层
python run_trial.py --no-gdelt --layers L3
python run_trial.py --no-gdelt --brands byd tesla
python run_trial.py --dry-run   # 只预览查询式
python pipeline.py              # 单独跑清洗入库
```

产出：
- `corpus/raw/` 原始网页/JSON/字幕（按源分目录，保留快照与哈希）
- `corpus/processed/records.jsonl` 清洗入库记录
- `corpus/meta/corpus.sqlite` 结构化语料库（四表 Schema，见 docs 方案）
- `collector/audit/` 每次运行的《试采证据日志》（查询式、命中数、失败原因全留痕）

## 质量门禁（14 天试采硬性指标）

| 指标 | 目标 |
|---|---|
| 有效全文 | ≥ 500 篇 |
| 覆盖媒体/平台 | ≥ 15 家 |
| 阿语占比 | ≥ 45% |

`run_trial.py` 结束时自动输出门禁报告。

## 当前进度

- [x] 工程骨架 + 旧文件归档（archive/）
- [x] 爬取框架 v0.1（Google News RSS / GDELT / Reddit / yt-dlp / 站内搜索 + 清洗入库流水线）
- [x] 首次实采验证：304 条原始 → 264 条入库（阿语 56% 达标，命中 Changan/Jetour/Chery/XPENG/MG/Haval 目标内容）
- [x] 后端 FastAPI v0.5：统计/检索/KWIC/品牌声量/合规审查 全部接口实测通过
- [x] 前端 React v0.5 源码：舆情大屏 / 语料检索+KWIC / 品牌声量看板 / 合规审查台（npm install 后即可运行）
- [x] 合规规则库 v0.1：五维 17 条规则（含宗教感叹词白名单、海湾本土化规则）
- [ ] GDELT 夜间批跑（54 查询 × 30s 限速，约 30 分钟；--no-gnews 搭配）
- [ ] 站内搜索 URL 逐一核验（sources.yaml 中 verify: true 项）
- [ ] Label Studio 部署 + 标注规范 v2.0 导入
- [ ] 品牌雷达接入情感数据（依赖标注产出）
