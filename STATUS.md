# daily-tech-news STATUS v4.5.0 — 2026-04-12

## 断点
- **本次完成**：周报功能 + DeepSeek-V3 文本兜底
  - `rss_news_collector.py`：新增 `--weekly` flag，hours_ago=168，周报 date card / 卡片排版 / 简报 badge
  - `rss_news_collector.py`：新增 `generate_news_briefs()`（40-60字简报批量生成）
  - `rss_news_collector.py`：新增 `generate_feature_article()`，周报末尾本周专题（300-400字深度文章）
  - `auto_daily_news.py`：周一自动切换周报模式，标题格式"X月X日-X月X日AI科技财经周报"
  - 文本 LLM 链路：Claude Sonnet → DeepSeek-V3（兜底）→ 无（豆包 lite 从文本链路移除）
  - `call_deepseek_api()` 新增至两个脚本；GitHub secret DEEPSEEK_API_KEY 已写入
  - `.env.local`：新增 DEEPSEEK_API_KEY
- **下一步**：
  - 观察周报首次运行质量（下一个周一 2026-04-13 08:00）
  - 可选：Marketaux 免费 token 申请（100次/天，财经补源）
  - 可选：财联社 CLS_TOKEN 获取（根治财联社 403）

## 环境
- 脚本路径：`~/.claude/skills/daily-tech-news/scripts/`
- 核心文件：`rss_news_collector.py`（主逻辑）、`auto_daily_news.py`（入口）、`generate_image.py`（封面图）
- API 配置（支持 `.env.local`）：
  - `ANTHROPIC_API_KEY`：Claude Sonnet（主力，所有文本任务）
  - `DEEPSEEK_API_KEY`：DeepSeek-V3（文本兜底，Claude 失败时接管）
  - `DOUBAO_API_KEY`：豆包 Seedream（仅封面图）
  - `WECHAT_API_KEY` / `WECHAT_APP_ID`：三更AI 公众号发布
  - `TAVILY_API_KEY`：可选，新闻补充搜索
  - `IMGBB_API_KEY`：可选，封面图永久链接
- 定时任务：CF Worker 触发 GitHub Actions，北京时间 08:00（原 08:30 已调整）
- 周报：每周一自动触发，时间窗口 168h（Mon-Sun）

## 已知问题
- wx.limyai.com SSL 证书：`SSL_VERIFY=False` 临时跳过
- Marketaux 主要为英文财经，中文场景补充有限，建议不配置（静默跳过）
- 财联社 / 财新 RSSHub 路由依赖公共实例，不稳定

## 勿碰
- `logs/` 目录（运营记录）
- `raw_news_*.json`（原始数据备份）
- `generate_image.py`（豆包 Seedream 图像生成，独立链路，不动）
