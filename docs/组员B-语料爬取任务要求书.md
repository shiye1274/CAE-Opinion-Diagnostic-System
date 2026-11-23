# 组员 B · 语料爬取任务要求书

> 项目：《破壁中东——中阿英跨语言舆情语料库构建与智能品牌诊断系统》（挑战杯）
> 你的角色：数据采集组 B 席（增量通道 + 汽车垂直 + 视频字幕 + UGC）
> 本文档自包含：读完照做即可，遇到问题在群里 @A
> 版本：2026-11-18

---

## 一、项目一句话背景

我们要建一个"中国新能源汽车品牌在中东（沙特/阿联酋/卡塔尔等海湾六国）的中·阿·英三语舆情语料库"。你的工作是：**用团队已写好的爬虫框架，每天跑增量采集 + 负责你名下数据源的核验与出量**。不需要你写爬虫代码，框架已经全部做好。

---

## 二、第一天环境搭建（约 30 分钟，做完在群里发截图）

### 1. 装 Python 3.10 或更高版本
官网 https://www.python.org/downloads/ 下载安装，**安装时勾选 "Add Python to PATH"**。

### 2. 装 Git
https://git-scm.com/download/win 安装，一路默认。

### 3. 拉代码
打开 PowerShell（开始菜单搜 PowerShell），逐条粘贴：
```powershell
cd D:\
git clone https://github.com/<队长GitHub用户名>/middle-east-brand-sentinel.git
cd middle-east-brand-sentinel\collector
pip install -r requirements.txt
```
（仓库链接和你的 GitHub 邀请邮件，队长会发你；首次克隆可能要登录 GitHub 账号）

### 4. 验证环境（最重要的一步）
```powershell
python run_trial.py --dry-run
```
屏幕打印出 **618 个查询组合** 和若干条 GDELT 查询式 = 环境全通。截图发群。

---

## 三、你的日常工作（每天约 10 分钟）

### 1. 每日增量采集（必做，约 10 分钟）
```powershell
cd D:\middle-east-brand-sentinel\collector
python run_trial.py --no-gdelt --max-per-query 5
```
这条命令跑 Google News 增量 + 你名下可跑的源 + Reddit + YouTube。
- `--no-gdelt` 是**必带参数**：GDELT 数据源限流极其严格且按网络 IP 计，**由队长独占**，你跑了两个人都会被封锁。

### 2. 更新代码（每天开始工作前）
```powershell
git pull
```

### 3. 源核验（第 1–2 周的重点，见第四节清单）
打开文件 `collector/sources.yaml`，找到**你名下的源**，逐个做这件事：
- 在浏览器打开该网站，找到它的站内搜索功能
- 搜一个品牌名（如 BYD），看地址栏的 URL 长什么样
- 把 URL 里的搜索词换成 `{q}`，填进该源的 `search_url:` 字段
- 把该源的 `verify: true` 改成 `verify: false`
- 示例——填好的样子：
```yaml
- id: drivearabia
  name: DriveArabia
  search_url: https://www.drivearabia.com/?s={q}
  verify: false        # ← 已核验
```
改完提交并上传：
```powershell
git add sources.yaml
git commit -m "verify: drivearabia 等核验完成"
git push
```
> **只允许改 `owner: B` 的源条目**，其他源是队长名下的，动了会产生代码冲突。

### 4. 每周日晚：数据回传（必做）
```powershell
# ① 打包你采集的原始数据（把路径里的日期换成实际日期段）
#    在 D:\middle-east-brand-sentinel\collector 目录下执行：
Compress-Archive -Path ..\corpus\raw\googlenews, ..\corpus\raw\reddit_dubai, ..\corpus\raw\reddit_saudi, ..\corpus\raw\reddit_qatar, ..\corpus\raw\reddit_dph, ..\corpus\raw\youtube_kw_ar -DestinationPath corpus_raw_B_20261124.zip
# ② 审计日志一起打包
Compress-Archive -Path audit\run_*.jsonl -Update -DestinationPath corpus_raw_B_20261124.zip
# ③ 上传到团队网盘，群里通知队长
```
**队长每周日统一合并入库**，你不需要自己跑 pipeline。

---

## 四、你名下的数据源清单（owner: B）

| 层 | 源 ID | 名称 | 语言 | 你要做什么 |
|---|---|---|---|---|
| L2 | gulfnews | Gulf News | 英 | 核验 search_url |
| L2 | khaleejtimes | Khaleej Times | 英 | 核验 search_url |
| L2 | thenational | The National | 英 | 核验 search_url |
| L2 | arabianbusiness | Arabian Business | 英 | 核验；若遇付费墙→只记录不硬爬 |
| L2 | arabnews | Arab News | 英 | 核验 search_url（沙特英语旗舰，优先） |
| L2 | saudigazette | Saudi Gazette | 英 | 核验 search_url |
| L2 | zawya | Zawya | 英 | 付费墙倾向→记录即可 |
| L2 | agbi | AGBI | 英 | 付费墙→记录即可 |
| L2 | meed | MEED | 英 | 强付费墙→**不要尝试爬**，记录即可 |
| L3 | arabgt | ArabGT（中东第一车媒） | 阿 | 核验 search_url（**最优先**） |
| L3 | almuraba | المربع نت | 阿 | 核验 search_url |
| L3 | saudishift | سعودي شفت | 阿 | 核验 search_url |
| L3 | striveme | StriveME | 阿 | 核验 search_url |
| L3 | moterat | Moterat | 阿 | 核验 search_url |
| L3 | drivearabia | DriveArabia | 英 | 核验 search_url |
| L3 | yallamotor | YallaMotor | 英 | 核验 search_url |
| L3 | carswitch | CarSwitch | 英 | 核验 search_url |
| L4 | yt_channel_arabgt 等 4 个 | YouTube 频道 | 阿/英 | 核验频道 handle 是否正确 |
| L5 | reddit_dubai / reddit_saudi / reddit_qatar / reddit_dph | Reddit 四个版 | 英 | 配置已就绪，直接跑即可出量 |

**出量责任**：一期 UGC 目标 9,500 条主要靠你（Reddit + YouTube 评论区）；L3 垂直车评正文由你的源承担。

---

## 五、红线（违反会拖垮全队进度）

1. **永远不要跑不带 `--no-gdelt` 的命令**——GDELT 限流按 IP 算，如果你和队长连同一个 WiFi，两人同时跑会互相封锁（此问题已发生过，见团队文档）。
2. **不要改 `owner: A` 的源**、不要改 `packs/` 词包文件——发现新品牌词或新好源，在群里报，由队长统一加。
3. **不要把 `corpus/` 里的文件传上 Git**——数据走网盘回传。
4. **不要硬爬付费墙/验证码站点**（MEED、AGBI、X）——框架设计里有降级方案，遇到就记录报告。
5. 遇到网站打不开、乱码、命令报错：**截图 + 复制报错文字**发群里，不要自己重装环境瞎折腾超过 20 分钟。

---

## 六、每周验收标准（周日晚队长检查）

| 周 | 你应交付 |
|---|---|
| 第 1 周末 | 环境跑通截图；Reddit 已出量；L3 至少核验 4 个源；首次数据回传 |
| 第 2 周末 | L3 全部核验完；YouTube 频道字幕已出量；UGC 累计 ≥2,000 条 |
| 第 3 周末 | L2 英语站核验完；UGC 累计 ≥5,000 条；坏源清单（打不开的站+原因）提交 |

---

## 七、你采集的数据去哪了

你的原始数据每周被队长合并进团队语料库（`corpus.sqlite`），自动流向：
- **前端大屏**（http://localhost:5173 ：语言分布饼图、品牌声量图）
- **KWIC 语料检索系统**（答辩演示用的核心模块）
- **标注平台**（标注同学在你采的数据上打标签）

所以你看到大屏上数字每天涨，有你每天的 10 分钟在里面。
