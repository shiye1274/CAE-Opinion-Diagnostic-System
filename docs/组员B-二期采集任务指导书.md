# 组员 B · 二期采集任务指导书

> 项目：《中阿英跨语言舆情语料库与品牌出海舆情诊断系统》（挑战杯）
> 角色：数据采集组 B 席
> 版本：2026-11-25（二期）
> 仓库：https://github.com/shiye1274/CAE-Opinion-Diagnostic-System

---

## 〇、一期回顾与你现在要做什么

一期你已经交付了 Google News / Reddit / YouTube 评论等大头数据，语料库总量从 0 做到 4 万条。现在进入二期，项目有三个明确缺口要靠你补：

| 缺口 | 当前值 | 目标 | 你的任务 |
|---|---|---|---|
| **Playwright 浏览器源**（6 个 NEEDS_BROWSER） | 0 条 | 每源 ≥50 | 渲染搜索页，拿新闻正文 |
| **中文语料** | ~310 条 | ≥2,000 条 | 中文 RSS + 垂直媒体 |
| **L1 政策层** | 0 条 | ≥200 条 | 政府门户/通讯社新闻 |

另外：**数据回传规范已升级**（manifest.json + 校验脚本），以后每次回传前必须自检。

---

## 一、环境准备（30 分钟，只做一次）

```powershell
# 1. 拉最新代码
cd D:\
git clone https://github.com/shiye1274/CAE-Opinion-Diagnostic-System.git
cd CAE-Opinion-Diagnostic-System

# 2. 装依赖（二期新增了 feedparser / playwright / readability 等）
cd collector
pip install -r requirements.txt

# 3. 装 Playwright 浏览器（只装 chromium，约 100MB）
playwright install chromium

# 4. 验证
python run_trial.py --dry-run
```

看到 `[queries] 682 个` 之类的打印 = 环境全通，截图发群。

---

## 二、你的日常（每天 10 分钟）

```powershell
cd CAE-Opinion-Diagnostic-System
git pull
cd collector

# ① Google News 增量 + 可自动跑的源（--no-gdelt 必带，GDELT 由队长独占）
python run_trial.py --no-gdelt --max-per-query 5

# ② 中文定向批（重点！）
python run_trial.py --langs zh --sources xinhua_world people_auto chinadaily_cn chinanews_auto autohome_news yiche_news --max-per-query 20 --no-gdelt

# ③ L1 政策层定向批
python run_trial.py --sources vision2030 spa_en spa_ar uae_gov qat_tarsheed kuwait_mew bahrain_edb --max-per-query 5 --no-gdelt --no-gnews
```

---

## 三、本周三个专项（按优先级）

### 专项 1：Playwright 浏览器源（6 个 NEEDS_BROWSER）

这 6 个源之前用 `SiteSearchAdapter` 拿不到正文（需要 JS 渲染），现在已改成 `adapter: playwright`：

| 源 ID | 网站 | 你要核验的字段 |
|---|---|---|
| `arabianbusiness` | arabianbusiness.com | `search_url` 是否有效 |
| `saudishift` | saudishift.com | `search_url` 是否 `/?s={q}` |
| `striveme` | striveme.com | `search_url` |
| `moterat` | moterat.com | `search_url` |
| `drivearabia` | drivearabia.com | `search_url` |
| `yallamotor` | yallamotor.com | `search_url` |

**逐个验证步骤**：
1. 浏览器打开该网站，点站内搜索，搜 `BYD`。
2. 看地址栏 URL，把搜索词替换成 `{q}`。
3. 打开 `collector/sources.yaml`，找到对应源条目，更新 `search_url`。
4. 如果该站没有搜索页，改用列表页：把 `config.listing_url` 填成栏目页 URL，并调整 `config.link_selector`。
5. 跑 smoke：
   ```powershell
   python run_trial.py --sources yallamotor --max-per-query 3 --no-gdelt --no-gnews
   ```
6. 看 `collector/audit/试采证据日志_*.csv`，`n_hits>0` 即通过。
7. 通过后把 `verify: false` 保持不变，提交：
   ```powershell
   git add sources.yaml
   git commit -m "verify: yallamotor playwright search_url"
   git push
   ```

**预期**：每个源跑 3 条命中；正文 `word_count≥200` 的才算有效。

---

### 专项 2：中文源（6 个）

| 源 ID | 名称 | adapter | 你要做什么 |
|---|---|---|---|
| `xinhua_world` | 新华网-国际+汽车 | rss | 已通，直接跑 |
| `people_auto` | 人民网-汽车 | rss | 验证 RSS URL |
| `chinadaily_cn` | 中国日报中文网 | rss | 验证 RSS URL |
| `chinanews_auto` | 中新网汽车 | rss | 验证 RSS URL |
| `autohome_news` | 汽车之家-新闻 | html | 验证 `search_url` + `content_selector` |
| `yiche_news` | 易车-新闻 | html | 同上 |

**验证方法**：
1. 先用浏览器/PowerShell 打开 RSS URL，确认返回 XML 而不是 404。
   ```powershell
   Invoke-WebRequest http://xinhuanet.com/world/news_world.xml
   ```
2. 如果 404，在 `sources.yaml` 里替换 URL（方案文档 `docs/中文源补采方案.md` 有备用地址）。
3. `autohome_news` / `yiche_news` 的搜索页：打开 `https://www.autohome.com.cn/search?keyword=BYD`，把正文 `content_selector` 换成实际的 CSS（右键正文 → 检查 → 复制 selector）。
4. 跑批量：
   ```powershell
   python run_trial.py --langs zh --sources people_auto chinadaily_cn chinanews_auto autohome_news yiche_news --max-per-query 20 --no-gdelt
   ```

**查询词**：框架已自动用「品牌中文名 × 中东/沙特/阿联酋」组合，你不用改查询。

---

### 专项 3：L1 政策层（13 个）

| 源 ID | 名称 | adapter | 你要做什么 |
|---|---|---|---|
| `vision2030` | 沙特 2030 愿景新闻室 | html | 验证 `listing_url` + selector |
| `spa_en` | 沙特通讯社英文 | rss | 验证 RSS URL |
| `spa_ar` | 沙特通讯社阿语 | rss | 验证 RSS URL |
| `uae_gov` | 阿联酋政府新闻 | html | 验证 |
| `qat_tarsheed` | 卡塔尔 Tarsheed 新闻 | html | 验证 |
| `kuwait_mew` | 科威特水电部新闻 | html | 验证 |
| `bahrain_edb` | 巴林 EDB 新闻 | html | 验证 |
| `kapsarc` | KAPSARC 能源智库 | html | 验证 |
| `agsiw` | AGSIW 海湾智库 | html | 验证 |
| `carnegie_me` | Carnegie 中东 | html | 验证 |
| `saso` | 沙特标准局 | html | 验证 |
| `kahramaa` | 卡塔尔 Kahramaa | html | 验证 |
| `uae_moei` | 阿联酋能源基建部 | html | 验证 |

**验证方法**：同上——浏览器打开列表页，复制正文 selector，更新 `config`，跑 smoke，确认 `n_hits>0`。

**注意**：L1 源查询词是**政策主题**（Vision 2030 / EV strategy / 2030 愿景 等），不是品牌名，这是设计如此。

---

## 四、数据回传规范（升级版）

以前的 `Compress-Archive` 方式已作废，现在必须带 manifest：

### 1. 打包结构
```
corpus_raw_B_20261125.zip
├── manifest.json          ← 必须有
├── raw/
│   ├── xinhua_world/
│   │   └── records.jsonl
│   ├── youtube_kw_ar/
│   │   └── ...
│   └── ...
└── README.txt             ← 可选
```

### 2. manifest.json 模板
照抄 `docs/data_package_example_manifest.json`，改文件名、条数、时间。

必填字段：
- `package_id`：与 zip 文件名一致
- `owner`：固定 `"B"`
- `sources[]`：每个源一条，含 `source_id / adapter / layer / language / files / records`
- `total_records`：总条数
- `checksum`：可选，SHA-256

### 3. 传包前自检
```powershell
python collector/check_manifest.py --zip corpus_raw_B_20261125.zip
```
输出 `[OK] manifest 校验全部通过` 才能传给队长。

### 4. 命名规则
- 固定：`corpus_raw_B_YYYYMMDD.zip`
- 同一天多次：`corpus_raw_B_YYYYMMDD_2.zip`
- **禁止**：`(1)`、`副本`、中文日期

### 5. 传输
- <100MB：微信直发
- 100-500MB：网盘链接发群里
- >500MB：分卷，每卷 ≤200MB

### 6. 你必须先做的脱敏
- [ ] 邮箱/手机号/真实用户名 → 占位符或哈希
- [ ] 作者字段 → `sha256:...` 前 16 位
- [ ] 时间尽量标准化 `YYYY-MM-DD HH:MM:SS`
- [ ] 同批次内去重（URL/内容哈希）
- [ ] `text` 不能为空；`title` 缺失用 `text[:80]` 填充

---

## 五、红线（不要踩）

1. **永远带 `--no-gdelt`**——GDELT 按 IP 限流，你和队长同 WiFi 会互相封锁。
2. **只改 `owner: B` 的源**——`packs/`、`owner: A` 的源由队长统一维护。
3. **`corpus/`、`.env`、原始数据 zip 不进 Git**。
4. **不硬爬付费墙/验证码**（MEED/AGBI/X）——记录即可。
5. **Playwright 无头模式跑**——`headless: true`，不要开有头浏览器调试（跑批时）。
6. **遇到问题 20 分钟内发群**——截图 + 报错文字，别自己瞎折腾。

---

## 六、本周验收标准（周日晚队长检查）

| 项目 | 目标 |
|---|---|
| Playwright 源 | 6 个源 smoke 全通，每源 ≥3 条命中 |
| 中文源 | 6 个源 smoke 全通；累计中文 ≥500 条 |
| L1 政策层 | ≥7 个源 smoke 全通；累计 L1 ≥50 条 |
| 数据回传 | 用新规范传 1 个包，manifest 校验通过 |
| 代码同步 | 每天 `git pull`，selector/URL 修改已 push |

---

## 七、常见问题

**Q：Playwright 报 `Executable doesn't exist`？**
A：`playwright install chromium`

**Q：RSS 返回 404？**
A：在 `sources.yaml` 里换备用 URL（方案文档有列表），或改 `adapter: html` 用列表页。

**Q：某站点搜索页返回首页而不是结果页？**
A：改用 `config.listing_url` + `config.article_url_regex`（列表页模式），并调整 `link_selector`。

**Q：中文源出量很少？**
A：先确认 Google News 中文通道在跑（不带 `--no-gnews`）；RSS 源出量少通常是因为品牌词没命中，检查 `packs/brands_cn.yaml` 的中文词。

**Q：数据包校验失败？**
A：看 `check_manifest.py` 的报错——通常是 `package_id` 与文件名不一致，或 `records` 条数与实际不符。

---

## 八、你采集的数据去哪了

原始数据每周由队长合并进 `corpus.sqlite`，自动流向：
- 前端大屏（http://localhost:5173）
- KWIC 语料检索系统
- 标注平台（标注同学在你采的数据上打标签）

大屏上数字每天涨，有你每天 10 分钟在里面。
