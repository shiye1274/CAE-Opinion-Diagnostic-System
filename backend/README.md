# backend — FastAPI 后端（待开发）

按 `docs/方案B-...-详细设计方案.md` 第四章结构开发：

```
app/
├── main.py                 # 入口
├── core/                   # 配置、JWT、日志
├── api/v1/                 # corpus / sentiment / alignment / compliance / dashboard / annotation / auth
├── models/  schemas/  services/
├── nlp/                    # langid / dialect / aligner / sentiment / compliance / llm_client
└── tasks.py                # Celery 异步任务
```

数据源：直接读 `../corpus/meta/corpus.sqlite`（collector 已建四表 Schema）。
