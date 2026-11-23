# collector —— 可穷尽多源爬取框架

设计文档：`../docs/爬取框架方案.md`（先读这个）

## 安装

```bash
pip install -r requirements.txt
# 可选：YOUTUBE_API_KEY=xxx  （评论区通道）
```

## 用法

```bash
python run_trial.py --dry-run                  # 预览查询式，不采集
python run_trial.py --max-per-query 15         # 小样试跑（推荐首跑）
python run_trial.py --layers L2                # 只跑主流新闻层
python run_trial.py --brands byd tesla         # 只跑指定品牌
python run_trial.py --skip-pipeline            # 只采集不清洗入库
python pipeline.py                             # 单独跑清洗入库
```

## 输出

| 路径 | 内容 |
|---|---|
| `../corpus/raw/{source_id}/{yyyymmdd}/` | 原始 JSON 快照（meta + raw_payload + SHA256） |
| `../corpus/processed/records.jsonl` | 清洗去重后记录 |
| `../corpus/meta/corpus.sqlite` | 四表结构化语料库 |
| `audit/run_*.jsonl` | 查询级审计日志 |
| `audit/试采证据日志_*.csv` | 试采证据日志（Excel 可开） |
| `audit/gate_report_*.json` | 质量门禁报告（500 篇 / 15 源 / 阿语 45%） |

## 首次运行须知

1. sources.yaml 中 `verify: true` 的源在首次探测后会回写核验状态；探测失败自动降级到 GDELT/Google News 通道并在审计日志记 `DEGRADED`/`skipped`。
2. Haraj/部分阿语站点的搜索模板需要试采期人工确认后填入 `search_url`。
3. X/Twitter 未接入（API 收费），L5 受众层由 Reddit + YouTube 评论区承担。
4. 视频无字幕者需后续用 Whisper-large-v3 转写（`models/training/whisper_transcribe.py`，待建）。
