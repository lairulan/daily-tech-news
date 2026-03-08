# 版本历史

## v4.1.0 (2026-03-08) 🔧 财经源强化 + 分类优化

### 财经 RSS 源强化
- **新增 3 个中文财经源**（替换 3 个失效国际源）：
  - 财联社快讯（via RSSHub）
  - 财新网（via RSSHub）
  - 金十数据（via RSSHub）
- **移除 3 个永久失效源**：Financial Times、FT Markets、The Economist（GitHub Actions 环境无法访问）
- **RSSHub 多实例 fallback 机制**：每个中文财经源配置 3 个备选镜像地址
  - rsshub.rssforever.com（主）
  - rsshub.pseudoyu.com（备用1）
  - rsshub.ktachibana.party（备用2）

### 分类补救机制
- **新增分类不足自动补救**：当某分类少于 3 条时，从未分类新闻池中补充
- **AI 分类输入扩容**：从 30 条提升到 40 条，提高分类覆盖率

### AI 分类提示词优化
- **汽车行业分类规则**：上市/定价→财经，AI自动驾驶→AI，硬件评测→科技
- **供应链新闻**→财经分类
- **强调每类必须选满 5 条**

### Fallback URL 采集机制
- `collect_all_news()` 新增 fallback URL 循环尝试逻辑
- 主 URL 无结果时自动切换备选镜像，提升采集成功率

---

## v4.0.0 (2026-03-07) 🚀 纯 RSS 重构 + 48源大扩展

### RSS 源扩展（16 → 48 个源）
- **AI 专项源**（2→13）：新增 OpenAI Blog、Hugging Face、AI News、Google DeepMind、Google Research、Microsoft Research、NVIDIA Blog、VentureBeat AI、MIT News AI、KDnuggets、Analytics Vidhya
- **国内科技源**（6→11）：新增 IT之家、雷峰网、动点科技、OSCHINA、cnBeta
- **国际科技源**（6→12）：新增 Engadget、ZDNet、The Register、9to5Mac、Android Authority、Hacker News Best
- **财经源**（2→12）：新增 CNBC、MarketWatch、Yahoo Finance、Financial Times、FT Markets、Seeking Alpha、The Economist、Forbes Business、Business Insider、CoinDesk
- 总计 48 个有效 RSS 源，确保纯 RSS 模式下每日有充足的真实新闻量

### 纯 RSS 模式
- **移除 AI 补充新闻**：删除 `generate_supplement_news()` 和 `generate_category_supplement_news()` 调用
- **RSS 数量为 0 时退出**：`sys.exit(1)` 终止任务，不再用 AI 生成假新闻填充
- 所有发布内容 100% 来自真实 RSS 订阅源

### 时间窗口调整
- **新闻窗口从 48h 压缩回 24h**：48 个源保证 24h 内有充足新闻量，无需跨天

### 定时发布双保险
- **恢复 GitHub Actions schedule**：`cron: '30 0 * * *'`（UTC 00:30 = 北京时间 08:30）
- **保留 Cloudflare Workers**：`repository_dispatch` 作为备份触发
- 双触发源确保每天必定发布

---

## v3.2.0 (2026-03-07) 🐛 关键 Bug 修复

### 致命 Bug 修复
- **时区比较错误修复（0条新闻根因）**: 修复所有 RSS 源返回 0 条的根本原因
  - 原因：`datetime.now()` 返回无时区 naive datetime，而 `parsedate_to_datetime().astimezone()` 返回有时区 aware datetime，Python 禁止两者比较，抛出 `TypeError` 被静默 `continue` 跳过
  - 修复：改为 `datetime.now().astimezone()` 确保两端均为 aware datetime
  - 影响文件：`scripts/rss_news_collector.py`（L267, L361）

### 时间窗口扩展
- **过滤窗口从 24h 扩展到 48h**：国际 RSS 源（The Verge、Wired、Ars Technica 等）更新频率较低，窗口由 24 小时改为 48 小时，确保不遗漏跨天更新的新闻

### 日志优化
- **消除日志刷屏**：移除 `fetch_rss_items` 内部每个 RSS 源都打印一次"时间过滤范围"的重复日志，改为只在 `collect_all_news` 中打印一次

### RSS 源优化（2026-03-07）
- **删除失效源**：极客公园（404）、VentureBeat AI（404）、品玩
- **新增**：量子位（12条）、华尔街见闻（12条）、Bloomberg Markets（10条）、InfoQ（8条）
- 总计 16 个有效 RSS 源，覆盖 AI 专项、国内科技、国际科技、财经四类

### 文件清理
- 删除中文日期格式冗余文件：`news_2026年03月03日.md`、`news_2026年03月06日.md`

---

## v3.1.0 (2026-01-31) ✨

### 内容质量优化
- **新闻内容客观化**: 优化 prompt 实现纯事实陈述
  - 要求客观陈述事实，包含关键数据和信息
  - 明确列出需要避免的主观评价词汇清单
  - 禁止使用"激励"、"希望"、"激发"、"精神"、"推动"、"展现"、"提醒"、"值得关注"、"引发热议"、"重大突破"等词汇
  - 影响文件: `scripts/rss_news_collector.py`

- **AI与科技领域严格区分**: 强化分类标准，避免内容交叉
  - AI 领域：仅限人工智能核心技术（大模型、LLM、机器学习、深度学习、NLP、CV、AI训练/推理、AI芯片、AI应用、AI研究论文等）
  - 科技动态：非AI的科技内容（智能手机、电脑硬件、通用芯片、互联网产品、软件工程、游戏、新能源车、航天、5G/6G、物联网、创业公司、产品发布、科技企业动态等）
  - 在分类 prompt 中添加"严格区分，不得交叉"的明确指令
  - 影响文件: `scripts/rss_news_collector.py`

- **微语风格保持**: 恢复励志语录风格
  - 微语部分保持原有的励志、有深度���启发性的风格
  - 与新闻的客观陈述风格形成对比
  - 影响文件: `scripts/rss_news_collector.py`

### 技术细节
- 内容风格定位：新闻部分类似新闻通稿（纯事实陈述），微语部分励志向上
- 分类准确性提升：通过更详细的分类标准和排除规则提高AI分类准确性
- 临时文件清理：删除测试生成的 news_*.md 和 raw_news_*.json 文件

---

## v2.0.3 (2026-01-16) 🔧

### 功能优化
- **摘要生成优化**: 修复摘要内容不准确的问题
  - 新增 `extract_text_from_html()` 函数，从 HTML 中提取纯文本
  - 优化摘要生成 prompt，要求提炼新闻亮点、语言简洁有力
  - 增加摘要生成日志便于追踪
  - 影响文件: `auto_daily_news.py`

### 技术细节
- 摘要生成前先移除 HTML 标签，确保 AI 能正确理解新闻内容
- 摘要长度控制在 20-30 字，突出 1-2 个新闻亮点

---

## v2.0.2 (2026-01-15) 🐛

### Bug 修复
- **GitHub Actions 执行失败修复**: 修复自动化任务执行失败问题
  - 添加发布失败时的错误退出码 (sys.exit(1))
  - 改进 subprocess 错误处理，添加详细日志记录
  - 修复 rss_news_collector.py 文件路径问题，使用相对路径
  - 添加文件存在性检查和内容验证
  - 添加超时和异常类型的详细处理
  - 影响文件: `auto_daily_news.py`, `rss_news_collector.py`

- **农历日期显示修复**: 修复农历日期显示错误并改用传统格式
  - 修复农历日期显示错误（之前显示十二月初五，实际应为十一月廿七）
  - 改用传统农历日期格式：乙巳年冬月廿七
  - 添加 get_traditional_lunar_date() 函数
  - 使用天干地支年份 + 传统月份（冬月/腊月）+ 传统日期（廿七）
  - 影响文件: `auto_daily_news.py`, `rss_news_collector.py`

### 技术细节
- 农历日期格式: "乙巳年冬月廿七"（传统格式）
- 错误处理: 完整的异常捕获和日志记录
- 定时任务: 调整为 UTC 00:30（北京时间 08:30）

---

## v2.0.1 (2026-01-15) 🐛

### Bug 修复
- **农历日期修复**: 使用 zhdate 库获取真实农历日期
  - 修复硬编码"乙巳年"的问题，现在动态获取正确的农历年份
  - 修复使用公历月日代替农历月日的问题
  - 影响文件: `auto_daily_news.py`, `test_date_logic.py`, `rss_news_collector.py`
- **依赖更新**: 在 GitHub Actions 中添加 zhdate 库依赖
  - 确保自动化任务中农历日期功能正常工作

### 技术细节
- 新增依赖: `zhdate==0.1`
- 农历日期格式: "二零二五年十一月二十七"（示例）
- 自动适配年份变化，无需手动更新

---

## v2.0.0 (2026-01-14) 🚀

### 核心功能重构
- **RSS 真实新闻源**: 替换 AI 生成，使用 12+ 权威 RSS 源收集真实新闻
  - 量子位、机器之心、36氪、虎嗅、钛媒体、爱范儿
  - TechCrunch、The Verge、Bloomberg、华尔街见闻
- **精准日期过滤**: 确保只收集昨天一整天的新闻（00:00:00 - 23:59:59）
- **AI 智能分类**: 使用豆包 API 将新闻智能分类到 3 个类别
- **去重机制**: 基于标题的智能去重，避免重复内容

### 安全性修复
- **移除硬编码 API key**: 所有文件中的 API key 已移除
- **环境变量验证**: 添加启动时的环境变量检查
- **文档安全**: 所有示例使用占位符而非真实 key

### HTML 模板优化
- **渐变标签设计**: 三个分类使用不同渐变色（紫色/粉红/蓝色）
- **日期卡片**: 粉绿渐变背景，显示农历/星期/公历
- **微语卡片**: 粉黄渐变背景，AI 生成励志语录
- **编号系统**: 每条新闻带彩色编号（01-05）
- **移除冗余**: 去除标题重复和多余的"以下是..."字样

### 部署优化
- **GitHub Actions**: 每天 08:00 自动运行（UTC 00:00）
- **本地任务清理**: 删除本地 launchd 任务，避免重复执行
- **日志系统**: 完整的运行日志记录

### 文件结构
- **新增**: `rss_news_collector.py` - RSS 新闻收集脚本
- **新增**: `CHANGELOG.md` - 版本历史记录
- **优化**: `SKILL.md` - 更新为 V2.0.0

---

## v1.0.0 (2026-01-12)
- 初始版本
- 基于 WebSearch 的新闻收集
- 基础 HTML 格式化
- 公众号发布功能
