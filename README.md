# Daily Tech News - RSS 订阅版

## 概述

基于 RSS 订阅的每日科技新闻自动收集和发布系统。从权威媒体 RSS 源获取真实新闻，使用 AI 格式化后发布到微信公众号。

## 工作原理

```
RSS Feed (XML) → Python 解析 → 真实新闻数据 → 豆包 AI 格式化 → HTML 日报 → 公众号发布
```

## RSS 源配置

### AI 领域 (4个源)

| 媒体 | RSS 地址 | 每日获取 |
|------|----------|----------|
| 量子位 | https://www.qbitai.com/feed | 8条 |
| 机器之心 | https://www.jiqizhixin.com/rss | 8条 |
| TechCrunch AI | https://techcrunch.com/category/artificial-intelligence/feed/ | 5条 |
| The Verge AI | https://www.theverge.com/rss/ai-artificial-intelligence/index.xml | 5条 |

### 科技动态 (5个源)

| 媒体 | RSS 地址 | 每日获取 |
|------|----------|----------|
| 36氪 | https://36kr.com/feed | 8条 |
| 虎嗅 | https://www.huxiu.com/rss/0.xml | 8条 |
| 钛媒体 | https://www.tmtpost.com/rss | 5条 |
| 爱范儿 | https://www.ifanr.com/feed | 5条 |
| TechCrunch | https://techcrunch.com/feed/ | 5条 |

### 财经要闻 (2个源)

| 媒体 | RSS 地址 | 每日获取 |
|------|----------|----------|
| 华尔街见闻 | https://dedicated.wallstreetcn.com/rss.xml | 10条 |
| Bloomberg Tech | https://feeds.bloomberg.com/markets/news.rss | 8条 |

## 文件结构

```
~/.claude/skills/daily-tech-news/
├── SKILL.md                      # Skill 文档
├── README.md                     # 本文件
├── news_YYYYMMDD.md             # 生成的日报
├── raw_news_YYYYMMDD.json       # 原始新闻数据
├── scripts/
│   ├── rss_news_collector.py     # RSS 收集主脚本
│   └── daily-news.sh             # Shell 包装脚本
└── logs/
    ├── rss-news.log              # 收集日志
    ├── scheduler.log             # 调度日志
    └── scheduler-error.log       # 错误日志
```

## 定时任务

- **运行时间**: 每天 8:00
- **任务名称**: com.dailytechnews.scheduler
- **执行脚本**: `rss_news_collector.py`

## 常用命令

### 手动运行
```bash
python3 ~/.claude/skills/daily-tech-news/scripts/rss_news_collector.py
```

### 查看日志
```bash
# 收集日志
tail -f ~/.claude/skills/daily-tech-news/logs/rss-news.log

# 调度日志
tail -f ~/.claude/skills/daily-tech-news/logs/scheduler.log

# 错误日志
tail -f ~/.claude/skills/daily-tech-news/logs/scheduler-error.log
```

### 查看任务状态
```bash
launchctl list | grep dailytechnews
```

### 启动/停止任务
```bash
# 启动
launchctl start com.dailytechnews.scheduler

# 停止
launchctl stop com.dailytechnews.scheduler

# 重新加载
launchctl unload ~/Library/LaunchAgents/com.dailytechnews.scheduler.plist
launchctl load ~/Library/LaunchAgents/com.dailytechnews.scheduler.plist
```

## 添加新的 RSS 源

编辑 `scripts/rss_news_collector.py` 中的 `RSS_SOURCES`：

```python
RSS_SOURCES = {
    "AI 领域": [
        {
            "name": "新媒体名称",
            "url": "https://example.com/feed",
            "limit": 8  # 获取条数
        }
    ]
}
```

## 输出格式

生成的日报包含：
- **日期卡片**: 粉绿渐变背景，显示农历/星期/公历
- **AI 领域**: 紫色渐变标签，5条精选新闻
- **科技动态**: 蓝色渐变标签，5条精选新闻
- **财经要闻**: 粉红渐变标签，5条精选新闻
- **微语**: 粉黄渐变背景，励志语录

## 故障排查

### 新闻数量少
- 检查日志: `tail -50 logs/rss-news.log`
- 某些 RSS 可能暂时不可用

### 格式化失败
- 检查豆包 API key: `echo $DOUBAO_API_KEY`
- 查看 API 调用日志

### 发布失败
- 检查公众号授权状态
- 确认微信 API key 有效

## 卸载

```bash
launchctl unload ~/Library/LaunchAgents/com.dailytechnews.scheduler.plist
rm ~/Library/LaunchAgents/com.dailytechnews.scheduler.plist
```

## RSS 源验证

添加新源前先验证：

```bash
python3 -c "
import urllib.request, ssl, xml.etree.ElementTree as ET
ssl_context = ssl._create_unverified_context()
req = urllib.request.Request('RSS_URL', headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
    root = ET.fromstring(response.read())
    items = root.findall('.//item')
    print(f'✅ 有效: {len(items)} 条')
"
```

## 参考资料

- [量子位](https://www.qbitai.com)
- [机器之心](https://www.jiqizhixin.com)
- [36氪](https://36kr.com)
- [虎嗅](https://www.huxiu.com)
- [TechCrunch](https://techcrunch.com)
- [The Verge](https://www.theverge.com)
