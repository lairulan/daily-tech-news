---
name: daily-tech-news
description: 每日AI科技财经资讯自动策展与发布。热搜驱动选题，权威媒体采集，精美HTML排版，一键发布微信公众号。
version: 3.1.0
author: rulanlai
tags: [news, automation, wechat, rss, ai]
---

# Daily Tech News Publisher V3.1

每日 AI/科技/财经资讯自动策展与发布系统。

## 功能概述

- 🔥 **热搜驱动选题** - 多平台热度分析，智能权重分配
- 📰 **权威媒体采集** - 10+ RSS源 + WebSearch 双保障
- 🎨 **精美视觉设计** - 渐变色卡片 + AI封面图
- 📋 **质量检查清单** - 发布前自动验证
- 🛡️ **环境预检查** - 减少运行时错误
- 🤖 **双 API 降级** - OpenRouter + 豆包双保障

---

## 快速开始

### 基础用法

```bash
# 运行每日新闻采集与发布
python3 ~/.claude/skills/daily-tech-news/scripts/auto_daily_news.py
```

### 高级用法

```bash
# 仅检查环境依赖
python3 ~/.claude/skills/daily-tech-news/scripts/auto_daily_news.py --check-env

# 试运行（不发布）
python3 ~/.claude/skills/daily-tech-news/scripts/auto_daily_news.py --dry-run

# 指定公众号发布
python3 ~/.claude/skills/daily-tech-news/scripts/auto_daily_news.py --appid wx5c5f1c55d02d1354
```

---

## 前置条件

运行前请确认以下条件：

- [x] Python 3.8+
- [x] `zhdate` 包已安装 (`pip install zhdate`)
- [x] `certifi` 包已安装 (`pip install certifi`)
- [x] `WECHAT_API_KEY` 环境变量已设置
- [x] `OPENROUTER_API_KEY` 或 `DOUBAO_API_KEY` 环境变量已设置
- [x] 网络可访问 RSS 源和 API 服务

---

## 工作流程

```
┌─────────────────────────────────────────────────────────────┐
│                    Daily Tech News V3.0                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Step -1: 环境预检查                                          │
│   • 脚本文件 • 环境变量 • 网络连通性                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 0: 热搜分析与权重分配 【新增】                            │
│   • 微博/百度/抖音/东方财富热搜                                │
│   • 热度评估 🔥🔥🔥🔥🔥 → 置顶                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 1-3: 新闻采集与筛选                                      │
│   • RSS源 + WebSearch • 权威媒体优先 • 去重过滤               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 4-5: 内容生成                                           │
│   • 渐变色 HTML 格式化 • 微语生成 • 封面图生成                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 6: 质量检查 【新增】                                     │
│   • 15条新闻 • 无重复 • 来源权威 • 格式正确                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 7: 发布到微信公众号                                      │
│   • 微绿流量宝 API • 草稿箱                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 详细步骤说明

### Step -1: 环境依赖预检查

运行前自动验证所有依赖是否就绪。

**检查项目**：

1. **脚本检查**：
   - `~/.claude/skills/daily-tech-news/scripts/auto_daily_news.py`
   - `~/.claude/skills/daily-tech-news/scripts/generate_image.py`
   - `~/.claude/skills/daily-tech-news/scripts/rss_news_collector.py`

2. **环境变量检查**：
   - `WECHAT_API_KEY` ✅
   - `WECHAT_APP_ID`（可选，默认使用三更AI）
   - `DOUBAO_API_KEY` 或 `OPENROUTER_API_KEY` ✅

3. **网络连通性检查**：
   - RSS 源可访问性
   - API 服务可达性

**决策**：如果依赖缺失，立即停止并报告具体错误。

---

### Step 0: 热搜分析与权重分配（新增）

**搜索各平台热搜榜**：

| 平台 | 搜索词 | 权重 |
|------|--------|------|
| 微博热搜 | AI/科技/财经 | ⭐⭐⭐⭐⭐ |
| 百度热搜 | 科技/财经榜 | ⭐⭐⭐⭐ |
| 抖音热搜 | 科技相关 | ⭐⭐⭐ |
| 东方财富 | 财经热点 | ⭐⭐⭐⭐ |

**热度评估标准**：
- 🔥🔥🔥🔥🔥 = 多平台同时上榜 → **置顶报道**
- 🔥🔥🔥🔥 = 2-3平台上榜 → **优先收录**
- 🔥🔥🔥 = 单平台热搜 → **正常收录**

---

### Step 1: 确定日期范围

计算前一天的日期用于新闻收集。

示例：如果今天是 2026-01-28，搜索 2026-01-27 的新闻。

---

### Step 2: 新闻采集

#### RSS 源采集（主要）

使用 `rss_news_collector.py` 从以下权威源采集：

**国内源**：
- 机器之心（AI专业媒体）
- 36氪（科技创投）
- 虎嗅（商业科技）
- 钛媒体（科技财经）

**国际源**：
- TechCrunch（科技创业）
- TechCrunch AI（AI专栏）
- The Verge（消费科技）
- Wired（深度科技）
- Ars Technica（技术分析）
- Reuters Tech（财经科技）

#### WebSearch 补充（辅助）

针对每个类别搜索权威媒体：

**🤖 AI 领域**：
- "机器之心 [前一天日期] AI"
- "量子位 人工智能 最新"
- "MIT Technology Review AI [yesterday]"

**💻 科技动态**：
- "36氪 科技 [前一天日期]"
- "TechCrunch [yesterday]"
- "The Verge tech news [yesterday]"

**💰 财经要闻**：
- "财联社 [前一天日期]"
- "Bloomberg news [yesterday]"
- "Reuters financial [yesterday]"

---

### Step 3: 新闻筛选与分类

使用 AI 将收集的新闻分类到三个类别：

1. **每类选择 5 条**最重要的新闻
2. **去重过滤**：基于标题相似度
3. **时间过滤**：仅保留昨天的新闻
4. **来源验证**：确保来自权威媒体

**总计**：15 条新闻（3 类别 × 5 条）

---

### Step 4: 内容格式化

#### HTML 格式（渐变标签 + 清爽排版 + 编号）

**内容结构**：
- **日期卡片**：紫色渐变背景，显示农历/星期/公历
- **三个分类标题**：
  - 📱 AI 领域：紫色渐变 (#667eea → #764ba2)
  - 💻 科技动态：粉红渐变 (#f093fb → #f5576c)
  - 💰 财经要闻：蓝色渐变 (#4facfe → #00f2fe)
- **每个分类 5 条新闻**：编号 01-05，颜色与标题一致
- **微语卡片**：粉黄渐变背景，励志语录

---

### Step 5: 封面图生成

使用豆包 SeeDream API 生成封面图：

```bash
python3 ~/.claude/skills/daily-tech-news/scripts/generate_image.py cover \
  --title "X月X日AI科技财经日报" \
  --style "tech" \
  --retry 3 \
  --retry-delay 3 \
  --size 2048x2048
```

**注意**：图片尺寸必须至少 3686400 像素（2048x2048 推荐）。

---

### Step 6: 发布前质量检查（新增）

发布前自动验证以下项目：

- [ ] 每条新闻来自权威媒体（机器之心/36氪/财联社等）
- [ ] 无重复或高度相似的新闻
- [ ] 三个分类各5条，总计15条
- [ ] 所有新闻时间为前一天
- [ ] 微语励志且贴合当日热点主题
- [ ] 封面图已成功生成（尺寸≥2048x2048）
- [ ] HTML格式渲染正确

---

### Step 7: 发布到微信公众号

使用微绿流量宝 API 发布：

```bash
python3 ~/.claude/skills/daily-tech-news/scripts/auto_daily_news.py
```

**发布参数**：
- 格式：`news`（普通文章）
- 封面图：AI 生成，尺寸 2048x2048
- 内容格式：HTML（contentFormat: html）

**已配置的公众号**：

| 项目 | 值 |
|------|-----|
| 公众号 | 三更AI |
| AppID | `wx5c5f1c55d02d1354`（可通过环境变量覆盖）|

---

## 环境变量配置

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `WECHAT_API_KEY` | ✅ | 微绿流量宝 API Key |
| `WECHAT_APP_ID` | ❌ | 公众号 AppID（默认三更AI）|
| `OPENROUTER_API_KEY` | ✅* | OpenRouter API Key（推荐）|
| `DOUBAO_API_KEY` | ✅* | 豆包 API Key（备用）|

> *至少需要设置 `OPENROUTER_API_KEY` 或 `DOUBAO_API_KEY` 之一

---

## 权威媒体来源

### AI 领域权威来源

**中国**：
- 机器之心（Synced）- 专注AI的专业媒体
- 量子位 - AI科技媒体，覆盖产业动态
- 新智元 - AI产业媒体，商业化应用

**海外**：
- MIT Technology Review - 麻省理工科技评论
- VentureBeat AI - AI行业新闻，创投视角

### 科技动态权威来源

**中国**：
- 36氪 - 科技创投媒体，创业公司动态
- 钛媒体 - 科技财经媒体，深度报道
- 虎嗅 - 商业科技媒体，商业分析
- InfoQ - 技术社区，技术趋势

**海外**：
- TechCrunch - 科技创业新闻
- The Verge - 科技新闻，消费科技
- Ars Technica - 深度科技报道

### 财经要闻权威来源

**中国**：
- 财联社 - 证券资讯，快讯及时
- 第一财经 - 综合财经媒体，权威性强
- 证券时报 - 证券专业媒体
- 21世纪经济报道 - 财经新闻，深度分析

**海外**：
- Bloomberg - 彭博社，全球金融数据
- Reuters - 路透社，国际财经快讯
- Financial Times - 金融时报，专业分析

---

## 示例输出

```
1月28日AI+科技+财经微报，农历乙巳年腊月廿九，星期二

📱 AI 领域
1. OpenAI发布GPT-5预览版，多模态能力大幅提升，支持实时视频理解；
2. 国产大模型DeepSeek-V3性能评测超越GPT-4，在数学推理领域表现突出；
3. 百度文心一言用户数突破3亿，推出企业级AI解决方案；
4. 斯坦福发布2026年AI指数报告，中国AI论文发表量位居全球第二；
5. 英伟达推出新一代AI芯片Blackwell，算力提升4倍功耗降低30%。

💻 科技动态
1. 华为鸿蒙系统原生应用数量突破5000款，生态建设进入快车道；
2. 中国5G基站总数达400万个，覆盖所有地级市；
3. 台积电2nm工艺试产成功，预计2026年量产；
4. 苹果Vision Pro国行版发售，首日销量突破10万台；
5. 中国量子计算机"祖冲之三号"实现1000+量子比特操控。

💰 财经要闻
1. 央行下调存款准备金率0.5个百分点，释放长期资金约1万亿元；
2. A股三大指数集体收涨，成交额重回万亿规模；
3. 人民币兑美元汇率升破7.1，创三个月新高；
4. 比特币突破10万美元大关，加密市场总市值超4万亿美元；
5. 新能源汽车销量连续12个月增长，比亚迪月销突破50万辆。

【微语】技术的进步不是为了取代人类，而是为了释放人类的潜能，让我们能做更有创造力的事情。
```

---

## 故障排查

### 环境变量问题

**症状**：`错误: 未设置 WECHAT_API_KEY 环境变量`

**解决方案**：
```bash
# 检查环境变量
echo $WECHAT_API_KEY
echo $OPENROUTER_API_KEY

# 设置环境变量
export WECHAT_API_KEY="your-api-key"
export OPENROUTER_API_KEY="your-api-key"
```

### RSS 采集失败

**症状**：`RSS 收集失败，退出码: 1`

**排查步骤**：
1. 检查网络连接：`curl -I https://www.jiqizhixin.com/rss`
2. 检查 SSL 证书：确认 `certifi` 包已安装
3. 查看日志：`cat ~/.claude/skills/daily-tech-news/logs/rss-news.log`

### 封面图生成失败

**症状**：`封面图生成失败，将不使用封面图发布`

**排查步骤**：
1. 检查 API Key：`echo $DOUBAO_API_KEY` 或 `echo $OPENROUTER_API_KEY`
2. 检查脚本权限：`ls -la ~/.claude/skills/daily-tech-news/scripts/generate_image.py`
3. 手动测试：
   ```bash
   python3 ~/.claude/skills/daily-tech-news/scripts/generate_image.py cover \
     --title "测试封面" --style "tech" --size 2048x2048
   ```

### 发布失败

**症状**：`发布失败`

**排查步骤**：
1. 检查 API Key：确认 `WECHAT_API_KEY` 正确
2. 检查 AppID：确认公众号 AppID 正确
3. 检查内容长度：微信限制文章长度
4. 检查 HTML 格式：确保无语法错误
5. 查看 API 响应：检查日志中的错误信息

### WebSearch 结果有限

**症状**：搜索返回的新闻数量不足

**解决方案**：
- 尝试替代搜索词
- 添加年/月到搜索查询
- 搜索更广泛的主题后再过滤

---

## 最佳实践

- **优先搜索权威媒体**：使用媒体名称 + 日期进行精准搜索
- **交叉验证**：同一新闻在多个来源出现时优先采用
- **来源标注**（可选）：重大新闻可在文末标注来源媒体
- 搜索多个查询词以获得全面覆盖
- 保持摘要简洁（每条 1-2 句话）
- 平衡三个类别的覆盖
- 包含突发新闻（如有）
- 使用专业但吸引人的语言

---

## 定时调度

本技能设计用于每日执行。推荐时间：
- 早上（8:00-10:00）用于当日发布
- 或通过自动化工具调度以确保稳定交付

### GitHub Actions 定时任务

```yaml
name: Daily Tech News
on:
  schedule:
    - cron: '0 0 * * *'  # UTC 00:00 = 北京时间 08:00
  workflow_dispatch:

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install zhdate certifi requests
      - name: Run daily news
        env:
          WECHAT_API_KEY: ${{ secrets.WECHAT_API_KEY }}
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
        run: python3 scripts/auto_daily_news.py
```

---

## 版本历史

### v3.1.0 (2026-01-31)
- ✨ **内容质量优化**：新闻内容客观化，纯事实陈述
- 🎯 **分类优化**：AI与科技领域严格区分，避免交叉
- 💬 **微语风格保持**：恢复励志语录风格
- 🧹 **代码清理**：删除测试生成的临时文件

### v3.0.0 (2026-01-28)
- 🔥 **新增热搜驱动选题系统**：多平台热度分析，智能权重分配
- 🔥 **新增环境预检查机制**：运行前自动验证依赖（`--check-env`）
- 🔥 **新增发布前质量检查清单**：确保输出质量稳定
- 🔥 **新增 dry-run 模式**：试运行不发布（`--dry-run`）
- ⚡ **文档重构**：完善 Front Matter、故障排查、工作流程图
- 🐛 **修复硬编码 AppID**：改为环境变量 `WECHAT_APP_ID` 配置
- 🐛 **修复 SSL 证书问题**：使用 `certifi` 正确验证证书
- 🐛 **添加请求速率限制**：RSS 采集添加 0.5 秒间隔
- 🔧 **代码重构**：提取公共函数到 `utils.py`

### v2.0.3 (之前版本)
- RSS 新闻收集器
- 渐变色 HTML 样式
- 双 API 降级支持（OpenRouter + 豆包）
- 权威媒体优先策略
- 自动封面图生成

---

## 相关技能

- [wechat-publish](../wechat-publish/SKILL.md) - 微信公众号发布
- [industrial-robot-insights](../industrial-robot-insights/SKILL.md) - 工业机器人洞察
- [ai-edu-publisher](../ai-edu-publisher/SKILL.md) - AI教育资讯发布
