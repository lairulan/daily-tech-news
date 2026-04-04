# Daily Tech News - RSS 订阅版

## 概述

基于 RSS 订阅的每日科技新闻自动收集和发布系统。从权威媒体 RSS 源获取真实新闻，必要时可用第三方 API 补充财经候选新闻，再使用 AI 格式化后发布到微信公众号。

## 工作原理

```
RSS Feed (XML) → Python 解析 → 规则去重/过滤 →（可选）第三方 API 财经补源 → AI/规则分类 → HTML 日报 → 公众号发布
```

## RSS 源配置（当前代码为 46 个源）

### AI 专项源 (13个源)

| 媒体 | RSS 地址 | 每日获取 | 状态 |
|------|----------|----------|------|
| 量子位 | https://www.qbitai.com/feed | 12条 | ✅ |
| 机器之心 | https://www.jiqizhixin.com/rss | 12条 | ✅ |
| OpenAI Blog | https://openai.com/blog/rss.xml | 8条 | ✅ |
| Hugging Face Blog | https://huggingface.co/blog/feed.xml | 8条 | ✅ |
| AI News | https://www.artificialintelligence-news.com/feed/ | 8条 | ✅ |
| Google DeepMind | https://deepmind.google/blog/rss.xml | 8条 | ✅ |
| Google Research | https://research.google/blog/rss | 8条 | ✅ |
| AWS ML Blog | https://aws.amazon.com/blogs/machine-learning/feed/ | 8条 | ✅ |
| NVIDIA Blog | https://blogs.nvidia.com/feed/ | 8条 | ✅ |
| ZDNet AI | https://www.zdnet.com/topic/artificial-intelligence/rss.xml | 10条 | ✅ |
| MIT News AI | https://news.mit.edu/rss/topic/artificial-intelligence2 | 8条 | ✅ |
| KDnuggets | https://www.kdnuggets.com/feed | 8条 | ✅ |
| IEEE Spectrum AI | https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss | 8条 | ✅ |

### 科技动态源 (21个源)

| 媒体 | RSS 地址 | 每日获取 | 状态 |
|------|----------|----------|------|
| 36氪 | https://rsshub.rssforever.com/36kr/news/latest | 12条 | ✅ |
| 钛媒体 | https://www.tmtpost.com/rss | 10条 | ✅ |
| 爱范儿 | https://www.ifanr.com/feed | 8条 | ✅ |
| 少数派 | https://sspai.com/feed | 8条 | ✅ |
| InfoQ | https://www.infoq.cn/feed | 8条 | ✅ |
| IT之家 | https://www.ithome.com/rss/ | 10条 | ✅ |
| 雷峰网 | https://www.leiphone.com/feed | 8条 | ✅ |
| OSCHINA | https://www.oschina.net/news/rss | 8条 | ✅ |
| cnBeta | https://www.cnbeta.com.tw/backend.php | 10条 | ✅ |
| TechCrunch | https://techcrunch.com/feed/ | 10条 | ✅ |
| TechCrunch AI | https://techcrunch.com/category/artificial-intelligence/feed/ | 10条 | ✅ |
| The Verge | https://www.theverge.com/rss/index.xml | 8条 | ✅ |
| Wired | https://www.wired.com/feed/rss | 8条 | ✅ |
| Ars Technica | https://feeds.arstechnica.com/arstechnica/index | 8条 | ✅ |
| MIT Tech Review | https://www.technologyreview.com/feed/ | 8条 | ✅ |
| Engadget | https://www.engadget.com/rss.xml | 8条 | ✅ |
| ZDNet | https://www.zdnet.com/news/rss.xml | 8条 | ✅ |
| The Register | https://www.theregister.com/headlines.atom | 8条 | ✅ |
| 9to5Mac | https://9to5mac.com/feed/ | 8条 | ✅ |
| Android Authority | https://www.androidauthority.com/feed/ | 8条 | ✅ |
| Hacker News Best | https://hnrss.org/best | 8条 | ✅ |

### 财经要闻 (12个源)

| 媒体 | RSS 地址 | 每日获取 | 状态 |
|------|----------|----------|------|
| 财联社快讯 | https://rsshub.rssforever.com/cls/telegraph | 15条 | ✅ |
| 财新网 | https://rsshub.pseudoyu.com/caixin/latest | 15条 | ✅ |
| 金十数据 | https://rsshub.rssforever.com/jin10/flash | 10条 | ✅ |
| 华尔街见闻 | https://dedicated.wallstreetcn.com/rss.xml | 12条 | ✅ |
| Bloomberg Markets | https://feeds.bloomberg.com/markets/news.rss | 10条 | ✅ |
| CNBC | https://www.cnbc.com/id/100003114/device/rss/rss.html | 8条 | ✅ |
| MarketWatch | https://feeds.marketwatch.com/marketwatch/topstories/ | 8条 | ✅ |
| Yahoo Finance | https://finance.yahoo.com/news/rssindex | 8条 | ✅ |
| Seeking Alpha | https://seekingalpha.com/feed.xml | 8条 | ✅ |
| Forbes Business | https://www.forbes.com/business/feed2 | 8条 | ✅ |
| Business Insider | https://feeds.businessinsider.com/custom/all | 8条 | ✅ |
| CoinDesk | https://www.coindesk.com/arc/outboundfeeds/rss/ | 8条 | ✅ |

> **已废弃 / 已移除**：极客公园（404）、VentureBeat AI（404）、品玩（解析问题）、DeepLearning.AI（404）、Reuters（404）、Financial Times / FT Markets / The Economist（当前版本未启用）、虎嗅 / 动点科技 / Microsoft Research / Analytics Vidhya（当前版本未启用）

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

- **线上运行时间**: 每天 08:30（北京时间）
- **触发方式**: Cloudflare Worker `repository_dispatch`
- **GitHub Workflow**: `.github/workflows/daily-news.yml`
- **本地手动调试**: 直接运行 `scripts/rss_news_collector.py` 或 `scripts/auto_daily_news.py`

## 常用命令

### 手动运行
```bash
python3 ~/.claude/skills/daily-tech-news/scripts/rss_news_collector.py
```

### 本地私有配置
```bash
cp ~/.claude/skills/daily-tech-news/.env.example ~/.claude/skills/daily-tech-news/.env.local
```

- 优先读取 shell 环境变量
- 若未设置，则自动读取项目根目录下的 `.env.local`
- `.env.local` 已加入 `.gitignore`，适合保存本机私有 key
- 微信发布默认开启 TLS 校验；如本机网络环境特殊，可在 `.env.local` 中显式设置 `WECHAT_SSL_VERIFY=false`

### 运行测试
```bash
python3 -m unittest \
  ~/.claude/skills/daily-tech-news/scripts/test_rss_datetime_parsing.py \
  ~/.claude/skills/daily-tech-news/scripts/test_rule_based_classification.py \
  ~/.claude/skills/daily-tech-news/scripts/test_local_env_loading.py \
  ~/.claude/skills/daily-tech-news/scripts/test_ssl_config.py
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
- **AI 领域**: 紫色渐变标签，5条精选单行新闻简讯
- **科技动态**: 蓝色渐变标签，5条精选单行新闻简讯
- **财经要闻**: 粉红渐变标签，5条精选单行新闻简讯
- **微语**: 粉黄渐变背景，励志语录
- **原始 JSON 诊断**: `raw_news_*.json` 额外保存 `rss_source_health`，便于排查空返回 RSS 源

## 故障排查

### 新闻数量少
- 检查日志: `tail -50 logs/rss-news.log`
- 某些 RSS 可能暂时无更新，或 Atom 时间格式未被正确识别
- 查看 `raw_news_*.json` 中的 `rss_source_health` 和 `external_source_health`

### 格式化失败
- 检查豆包 API key: `echo $DOUBAO_API_KEY`
- 若本地未导出环境变量，确认 `.env.local` 已填写
- 查看 API 调用日志

### AI 分类失败
- 当前已内置规则分类兜底，豆包限流时不会整期清空
- 若需补强财经覆盖，可配置 `MARKETAUX_API_TOKEN`

### 第三方 API 补源
- 当前支持可选的 `Marketaux` 财经补源
- 仅当财经 RSS 近 24 小时供给不足时触发
- GitHub Actions 如需启用，请配置仓库 Secret: `MARKETAUX_API_TOKEN`

### 发布失败
- 检查公众号授权状态
- 确认微信 API key 有效
- 若遇到本机证书链问题，可临时在 `.env.local` 中设置 `WECHAT_SSL_VERIFY=false` 或提供 `WECHAT_CA_BUNDLE`

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
