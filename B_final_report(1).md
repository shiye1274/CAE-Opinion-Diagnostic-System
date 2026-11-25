# 中国新能源车·中东舆情语料库｜组员B 来源核验与采集报告

**临时版（截至2026-11-20晚），周一会更新**

本文件内所有数字均由命令行统计生成（读取 corpus\raw 下 items.jsonl 与 B_verify_results.csv），未人工填写。

## 一、已采集数量（截至 2026-11-20）

| 项目 | 数量 |
|---|---|
| Google News（RSS，标题级，不含全文）累计 | 1292 条 |
| ├ 2026-11-19 | 1069 条 |
| └ 2026-11-20 | 223 条 |
| YouTube 官方 Data API 评论总数 | 7733 条 |
| ├ 正文含品牌词 | 693 条（9.0%） |
| ├ 标题含品牌词视频下的评论 | 5428 条（70.2%，涉及 650 个视频） |
| └ 语言分布 | 阿语 3577 ／ 英语 3436 ／ 其他 720 |
| almuraba（wp-json 全文） | 767 篇（其中 text_len<200 的 8 篇） |
| arabgt（wp-json 全文） | 34 篇（其中 text_len<200 的 0 篇） |
| Reddit（帖子+评论） | 0 条（见第三节） |
| yt-dlp（字幕+评论） | 0 条（见第三节） |

说明：上表“其他 720 条”里有 712 条为纯表情/符号、不含任何字母的评论。

## 二、来源核验状态（共 17 个源）

- 需浏览器确认 NEEDS_BROWSER：10 个 —— almuraba、arabgt、arabianbusiness、carswitch、drivearabia、khaleejtimes、moterat、saudishift、striveme、yallamotor
  其中 almuraba、arabgt 已通过站点 wp-json 采到全文，但站内搜索页本身仍不可用，故核验状态保留在 NEEDS_BROWSER。
- 被 robots 禁止站内搜索 ROBOTS_BLOCK_SEARCH：4 个 —— arabnews、gulfnews、saudigazette、thenational
- 仅记录、不请求 RECORD_ONLY_PAYWALL：3 个 —— agbi、meed、zawya
- 自动初筛判定 OK：0 个

## 三、未完成及原因（均为实测结果，未做任何绕过）

- **Reddit**：接口返回 HTTP 403，脚本按规则停止，状态记 stopped_http_403；未换 UA、未换出口、未绕过。
- **yt-dlp（字幕+评论）**：连续 3 次失败后自动停止，状态记 stopped_3_failures_possible_block，判定为被拦。
- **yallamotor**：脚本抓取无文章链接（0 篇）。
- **carswitch**：抓到的是二手车列表页而非文章页，本周不采集。
- **moterat**：robots.txt 取不到——SSL 握手被断开（UNEXPECTED_EOF）；**striveme**：robots.txt 读取超时（25 秒）。两个站均按“不确定就不采”处理。
- **saudishift**：站点返回 HTTP 403（www 与非 www 两种写法都是 403）。

### 英语站 robots.txt 中与站内搜索相关的 Disallow 原文行

| 站点 | robots.txt 原文 |
|---|---|
| arabnews.com | `Disallow: /search` |
| gulfnews.com | `Disallow: /advanced-search*`<br>`Disallow: /search*`<br>`Disallow: /guides/event-search-page` |
| saudigazette.com.sa | `Disallow: /search/` |
| thenationalnews.com | `Disallow: /search`<br>`Disallow: /queryly-advanced-search/` |
| khaleejtimes.com | robots.txt 请求返回 403，取不到原文（因此未采集） |

## 四、采集方式与合规说明

- **Google News**：官方 RSS 搜索接口，只保留标题、链接、时间（标题级，不含正文）。
- **YouTube**：官方 Data API v3（search + commentThreads 两个端点），只存评论文本、点赞数、发布时间、视频ID。
- **almuraba / arabgt**：站点公开的 WordPress REST 接口 `wp-json/wp/v2/posts`；请求前先取 robots.txt 并按 `User-agent: *` 段的 Disallow 判断是否可请求。arabgt 的 search 参数会触发 “One moment, please...” 校验页，已改为“只取最新列表 + 本地品牌词过滤”，未做任何绕过。
- **访问频率**：脚本内请求间隔 1–5 秒。
- **User-Agent**：统一为 `StudentResearchCorpus/0.1 (academic project; low request rate)`，如实标明身份与用途，不做伪装。
- **脱敏**：作者标识一律 SHA-256 哈希（字段 author_hash），不存作者名、不存头像、不存用户主页；正文中的邮箱、手机号、@用户名统一替换为 [EMAIL] / [PHONE] / [USER]。
- **不绕过**：遇到 403、校验页、付费墙一律停止并记录状态码，不换 UA、不换参数反复试探；MEED / AGBI / Zawya 只登记不请求。

## 五、需要队长决定

1. **UGC 口径**：对外报哪个数——原始抓取条数（7733）、标题含品牌词视频下的评论（5428）、还是正文含品牌词（693）？三者相差约 10 倍，口径不同结论会变。
2. **pipeline 能否直接读** `corpus\raw\<源ID>\<日期>\items.jsonl`？字段说明见同包 `B_data_format.md`。
3. **Reddit 是否申请官方 API（OAuth）**？目前 403，未做任何绕过。


## 六、分工变化（11月22日起）

- **almuraba、arabgt**：自 2026-11-22 起，改由队长的适配器统一采集，组员B脚本不再新增这两站数据。本地已入库的历史快照保留：almuraba 768 篇、arabgt 40 篇（含 11-22 当日采到的 almuraba 1 篇、arabgt 6 篇）。
- **本脚本继续保留**：Google News RSS 每日增量（标题级，不含正文）、YouTube 官方 Data API 评论。
- **已停用**：Reddit（接口返回 403，已在脚本内直接关闭，状态记 disabled_per_captain）；yt-dlp 字幕/评论通道（可执行文件已停用，停止前状态 stopped_3_failures_possible_block）。
- **最新累计数量（2026-11-24 17:40 执行统计命令所得，非估算）**：

| 项目 | 累计 | 按日明细 / 说明 |
|---|---|---|
| Google News（标题级） | 2541 条 | 11-19：1069 ／ 11-20：223 ／ 11-21：79 ／ 11-22：593 ／ 11-23：284 ／ 11-24：293 |
| YouTube 官方 API 评论 | 47884 条 | 11-20：7733 ／ 11-21：20695 ／ 11-22：1782 ／ 11-23：16798 ／ 11-24：876 |
| ├ 正文含品牌词 | 4318 条（9.0%） | 品牌词表与 11-20 版完全相同 |
| ├ 标题含品牌词视频下的评论 | 36353 条（75.9%，涉及 1758 个视频） | 视频标题按品牌词＋泛品类词匹配 |
| └ 语言分布 | 阿语 15963 ／ 英语 27728 ／ 其他 4193 | 其他里 4158 条为纯表情/符号、不含任何字母 |
| almuraba（wp-json 全文） | 768 篇（text_len<200 的 8 篇） | 至 11-22 止；11-22 起由队长适配器采集，本脚本不再采 |
| arabgt（wp-json 全文） | 40 篇（text_len<200 的 0 篇） | 至 11-22 止；11-22 起由队长适配器采集，本脚本不再采 |
| Reddit | 0 条 | 已停（disabled_per_captain），队长另走公开存档 |
| yt-dlp（字幕+评论） | 0 条 | 已停（skipped_no_ytdlp） |

统计命令：`cat corpus\raw\<源ID>\items.jsonl | wc -l`（按日期目录逐份相加）；Reddit 为 `find corpus\raw\reddit_dubai -type f | wc -l`（结果 0）。统计时间 2026-11-24 17:40，本文件内数字均来自该命令回显。

说明三点，均为实测：

1. 本节数字为本报告的最新口径。第一节表格是 2026-11-20 当时的快照（Google News 1292 条、YouTube 7733 条），两者不要混用。
2. 2026-11-23 两次运行，均如实记录：14:30 那次在 YouTube 接口步骤被系统中断（任务计划程序返回 3221225786），只完成 Google News 247 条；15:00 自动重跑完整结束（任务结果 0），当日 Google News 再增 37 条（合计 284）、YouTube 评论新增 16798 条，来源核验、日报与两个包均已生成。本节数字与 B_logs\report_20261123.txt 的 total=2248、UGC_total=47008 一致。
3. 2026-11-24 17:30 那趟自动运行正常结束（任务结果 0）：当日 Google News 新增 293 条、YouTube 评论新增 876 条，核验、日报与 B_report_20261124.zip 均已生成。按脚本第 180 行的原定条件（只在周日或 11-21／11-23／11-26 生成），11-24 的原始全量包已按同一范围手工补生成：corpus_raw_B_20261124.zip（脚本未改，仍是今日自动运行不生成的行为）。


## 七、本周没做（2026-11-23 定格）

- **Reddit**：已停（状态记 disabled_per_captain），队长另走公开存档，本脚本不再请求该接口。
- **yt-dlp（字幕+评论）**：已停（可执行文件改名停用，运行日志记 skipped_no_ytdlp）。
- **汽车媒体其他站**：拒绝脚本访问 —— arabnews、gulfnews、saudigazette、thenational 的 robots.txt 明令 Disallow 站内搜索；yallamotor、carswitch 只能取到列表页而非文章页；moterat（SSL 握手断开）、striveme（读取超时）的 robots.txt 取不到；saudishift 返回 403。以上均按“不确定就不采”处理，未做任何绕过。
