---
name: daily-tech-news
description: Daily AI/tech/finance news curator. Collects previous day's hot topics (15 items in 3 categories), formats with styled HTML, and publishes to WeChat. Use when user asks to collect daily news or create tech digest.
---

# Daily Tech News Publisher

Automatic daily news curation for AI, technology, and finance domains.

## Overview

This skill collects the previous day's hot news in AI + Technology + Finance categories, formats it into an organized digest, and automatically publishes to a specified WeChat Official Account.

## Output Format

**HTML 格式（渐变标签 + 清爽排版 + 编号）**

内容结构：
- **日期卡片**：粉绿渐变背景，显示农历/星期/公历
- **三个分类标题**：
  - 📱 AI 领域：紫色渐变 (#667eea → #764ba2)
  - 💻 科技动态：粉红渐变 (#f093fb → #f5576c)
  - 💰 财经要闻：蓝色渐变 (#4facfe → #00f2fe)
- **每个分类 5 条新闻**：编号 01-05，颜色与标题一致
- **微语卡片**：粉黄渐变背景，励志语录

**发布参数**：
- 格式：`news`（普通文章）
- 封面图：使用豆包 SeeDream API，尺寸 2048x2048
- 内容格式：HTML（contentFormat: html）

## Instructions

### Step 1: Determine Date Range

Calculate the previous day's date for news collection.

Example: If today is 2026-01-13, search for news from 2026-01-12.

### Step 2: Search for News by Category

Use WebSearch to find news in three categories. For each category, search multiple queries to get comprehensive coverage:

**AI 领域搜索词**:
- "AI人工智能 2026年1月12日"
- "人工智能新闻 最新"
- "AI行业动态 大模型"

**科技动态搜索词**:
- "科技新闻 2026年1月"
- "5G 芯片 科技动态"
- "互联网 科技公司"

**财经要闻搜索词**:
- "财经新闻 2026年1月12日"
- "股市 经济动态"
- "金融 财经要闻"

### Step 3: Select and Organize News

For each category:
1. Select **exactly 5** most relevant and important news items
2. Rewrite each item in 1-2 sentences (keep concise)
3. Number sequentially within category
4. Ensure factual accuracy and remove duplicates

**Total**: **15 news items** across 3 categories (5 per category)

### Step 4: Generate Daily Quote (微语)

Create or select an inspiring quote related to technology, innovation, or life wisdom:
1-2 sentences, poetic and thought-provoking.

### Step 5: Generate Cover Image

Generate cover image using Doubao SeeDream API:

```bash
DOUBAO_API_KEY="your-doubao-api-key" python3 ~/.claude/skills/wechat-publish/scripts/generate_image.py cover \
  --title "X月X日AI科技财经日报" \
  --style "tech" \
  --retry 3 \
  --retry-delay 3 \
  --size 2048x2048
```

**Note**: Image size must be at least 3686400 pixels (2048x2048 recommended).

### Step 6: Format and Publish

1. Format the complete news digest as HTML with styled sections
2. **Important**: Do NOT repeat title in content body
3. Use **wechat-publish** skill with `news` type:

```bash
# Set environment variables
export WECHAT_API_KEY="your-wechat-api-key"
export DOUBAO_API_KEY="your-doubao-api-key"

# Publish with cover image and styled HTML content
python3 ~/.claude/skills/wechat-publish/scripts/publish.py publish \
  --appid "wx5c5f1c55d02d1354" \
  --title "X月X日AI科技财经日报" \
  --content-file "/path/to/styled_news.md" \
  --summary "..." \
  --cover "COVER_IMAGE_URL" \
  --type "news"
```

**Important**:
- Content must use HTML format with inline styles
- Include cover image URL
- Use `contentFormat: html` when making API requests directly

## Example Output

```
1月13日AI+科技+财经微报，农历乙巳年冬月廿五，星期二

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

## Requirements

- **WebSearch**: Required for news gathering
- **wechat-publish skill**: Required for automatic publishing
- **Date accuracy**: Always verify the correct previous day's date
- **News quality**: Prioritize authoritative sources and verified information

## Best Practices

- Search multiple queries per category for comprehensive coverage
- Verify news from authoritative sources
- Keep summaries concise (1-2 sentences per item)
- Balance coverage across all three categories
- Include breaking news if available
- Use engaging but professional language

## Scheduling

This skill is designed for daily execution. Recommended timing:
- Morning (8:00-10:00) for same-day publication
- Or schedule via automation tools for consistent delivery

## Troubleshooting

If WebSearch returns limited results:
- Try alternative search terms
- Add year/month to search queries
- Search for broader topics then filter

If wechat-publish fails:
- Check account credentials
- Verify content length limits
- Ensure proper formatting
