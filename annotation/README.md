# annotation — 标注体系

> ⚠️ 标注流程完全遵循 `docs/挑战杯选题升级与多语种语料库建设完整规划(1).docx` 第四章（编码手册 v2.0 三层 28 维 + 人机协同三级流水线）。

## 目录

| 目录 | 用途 | 状态 |
|---|---|---|
| `guidelines/` | 编码手册 v2.0（从规划 docx 第四章导出为 md，供 Label Studio 导入） | 待导出 |
| `llm_annotator/` | LLM 预标脚本 + Prompt 模板（Qwen2.5-72B + GPT-4o 双模型交叉，输出 JSON+证据句） | 待建 |
| `active_learning/` | 低置信度样本筛选（双模型一致且置信度≥0.85 → 自动 Silver；分歧样本 100% 回流人工） | 待建 |
| `agreement/` | Cohen's Kappa / Krippendorff's Alpha 计算 + 校准集/金标准集进度表 | 待建 |

## 三级流水线（规划表 4-2）

1. **校准集**：200 篇 + 500 条 UGC，双人盲标，κ≥0.78（主框架/情感）/ κ≥0.72（误读）不达标则修订手册重标
2. **专家金标准集**：1,200 篇 + 3,000 条，双人盲标 + 第三人仲裁；抽检准确率≥92%
3. **银标准集**：其余全部，LLM 双模型交叉预标；Gold Test 上 Macro-F1≥0.80 才可入库

铁律：`annotator_source` 字段严格区分 HUMAN_GOLD / LLM_SILVER / VERIFIED；论文核心统计在金标准集与全量集分别汇报。
