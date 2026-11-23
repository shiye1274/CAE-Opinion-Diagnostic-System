# B 数据格式说明（组员B，来源可行性核验+采集）

本文件只写脚本里真实存在的字段（来自 run_daily.ps1 和 run_extra.ps1 的 [ordered]@{...} 定义），不含推测。

## 存放位置

corpus\raw\<源ID>\<日期>\
- items.jsonl：每行一条 JSON，UTF-8（无 BOM）
- 原始文件：googlenews 存 gn_<哈希前12位>.xml；reddit 存 search_<哈希前12位>.json；汽车媒体存 html_<哈希前12位>.html；youtube 存 <视频ID>.<语言>.vtt 字幕
- manifest.jsonl：只有 googlenews 有（记录每次请求的 url / fetched_at / sha256）
- youtube 目录额外有 videos.jsonl（每个视频一行）

源ID取值：googlenews、reddit_dubai、reddit_saudi、reddit_qatar、reddit_dph、youtube_kw_ar、arabgt、almuraba、carswitch 等（与 B_verify_results.csv 的 id 对应）。

## 1. Google News（googlenews\items.jsonl）

| 字段 | 含义 |
|---|---|
| id | 本条唯一哈希（对 link 做 SHA-256） |
| source_id | 固定值 googlenews |
| lang | 本次查询用的语言（ar 或 en） |
| country | 本次查询用的国家（SA / AE / QA） |
| query | 命中的搜索关键词 |
| title | 新闻标题 |
| link | Google News 给出的文章链接 |
| pub_date | RSS 里的发布时间原文 |
| publisher | RSS 里给出的媒体名称 |
| snippet | RSS 摘要，已去掉 HTML 标签；只是标题级摘要，不是全文 |
| fetched_at | 抓取时间（本机时间，ISO 格式） |

## 2. Reddit 帖子（reddit_*\items.jsonl，ugc_type=post）

| 字段 | 含义 |
|---|---|
| id | 唯一哈希（"rp|"+帖子ID 的 SHA-256） |
| source_id | 版块代号 reddit_dubai / reddit_saudi / reddit_qatar / reddit_dph |
| ugc_type | 固定 post |
| lang | 固定 en |
| post_id | Reddit 帖子 ID |
| title | 帖子标题（已脱敏） |
| text | 帖子正文（已脱敏） |
| created_utc | 发帖时间（Unix 秒） |
| score | 帖子分数 |
| num_comments | 评论数 |
| author_hash | 作者名哈希（不保存用户名） |
| permalink | 帖子相对链接 |
| fetched_at | 抓取时间 |

## 3. Reddit 评论（reddit_*\items.jsonl，ugc_type=comment）

| 字段 | 含义 |
|---|---|
| id | 唯一哈希（"rc|"+评论ID 的 SHA-256） |
| source_id | 版块代号（同上四个） |
| ugc_type | 固定 comment |
| lang | 固定 en |
| comment_id | 评论 ID |
| post_id | 所属帖子的 link_id 原值（形如 t3_xxxx） |
| text | 评论正文（已脱敏） |
| created_utc | 评论时间（Unix 秒） |
| score | 评论分数 |
| author_hash | 作者名哈希 |
| fetched_at | 抓取时间 |

## 4. YouTube 评论（youtube_kw_ar\items.jsonl）

| 字段 | 含义 |
|---|---|
| id | 唯一哈希（"yc|"+视频ID+"|"+评论ID 的 SHA-256） |
| source_id | 固定 youtube |
| ugc_type | 固定 comment |
| video_id | 视频 ID |
| text | 评论内容（已脱敏） |
| like_count | 该评论点赞数 |
| timestamp | yt-dlp 给出的评论时间 |
| author_hash | 作者 ID 哈希（不保存用户名） |
| fetched_at | 抓取时间 |

## 5. YouTube 视频（youtube_kw_ar\videos.jsonl）

| 字段 | 含义 |
|---|---|
| id | 唯一哈希（"yt|"+视频ID 的 SHA-256） |
| source_id | 固定 youtube |
| video_id | 视频 ID |
| title | 视频标题 |
| channel | 频道名 |
| caption_files | 这次为它下载到的字幕文件个数 |
| fetched_at | 抓取时间 |

## 6. 汽车媒体文章（arabgt / almuraba / carswitch 等\items.jsonl）

| 字段 | 含义 |
|---|---|
| id | 唯一哈希（"art|"+URL 的 SHA-256） |
| source_id | 站点代号，如 arabgt |
| lang | 抓取时使用的搜索语言（ar 或 en） |
| url | 文章地址 |
| title | 页面 <title> 文字 |
| text | 从页面 <p> 标签提取的正文（初步提取） |
| text_len | text 的字符数（<200 视为提取不足） |
| extraction | 提取方式标记，固定 generic_p_tags_preliminary |
| fetched_at | 抓取时间 |

## 需要注意的真实限制

1. Google News 只有 title + snippet，属标题级，不能当全文，也不能算 UGC。
2. UGC 只统计 Reddit 帖子+评论和 YouTube 评论。
3. 汽车媒体的 text 是通用 <p> 提取，属"初步提取"，未做正文清洗。
4. 去重靠 corpus\meta\seen_hashes.txt（一行一个哈希），已入库的条目不会重复采集。
5. 作者信息一律存哈希（author_hash），不存用户名；正文里的邮箱/电话/@用户名已被替换为 [EMAIL]/[PHONE]/[USER]。
