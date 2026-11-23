# models — 模型研发（待建）

| 目录 | 内容 |
|---|---|
| `training/` | LoRA/SFT 微调脚本（transformers + PEFT）；Whisper 阿语转写脚本 |
| `evaluation/` | 评测脚本（情感 F1 / 对齐 Recall@10 / 合规召回误报） |

## 模型选型（docs/方案B 3.2 节）

- 跨语言对齐：`intfloat/multilingual-e5-large` 或 `BAAI/bge-m3` + 对比学习
- 阿语情感：MARBERTv2（方言优化）/ AraBERT
- LLM：Qwen2.5-7B/72B 本地部署 + GPT-4o 关键样本复核
- 门禁：情感 F1≥0.80；对齐 Recall@10≥0.80；合规召回≥0.90、误报≤0.15
