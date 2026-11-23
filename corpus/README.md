# corpus — 语料数据目录

| 目录 | 内容 | Git 策略 |
|---|---|---|
| `raw/` | 采集原始快照（JSON：meta + raw_payload），按 `{source_id}/{日期}/` 组织 | 不入 Git（体积大），保留本地 |
| `processed/` | `records.jsonl` 清洗去重后记录 | 增量入库 |
| `aligned/` | 中—阿—英平行/可比事件簇（event_clusters） | 二期构建 |
| `meta/` | `corpus.sqlite` 四表库 + 数据源清单 + License 记录 | schema 入 Git，数据不入 |

## 四表 Schema（对齐规划文档表 3-4，collector/pipeline.py 已实现三表）

1. `corpus_documents` — 文档主表（doc_id 主键，lang_variant 区分 MSA/Khaliji/Arabizi/EN/ZH）
2. `doc_entities` — 品牌-文档映射（role_in_doc: CORE / BENCHMARK / PASSING_MENTION）
3. `corpus_spans_annotations` — 段落级标注（预留，标注阶段写入）
4. `ugc_threads` — 评论树（author_hash 脱敏，dialect_tag）

数据合规：公开释放版仅含 URL+元数据+标注标签+短片段索引；UGC 100% 脱敏。
