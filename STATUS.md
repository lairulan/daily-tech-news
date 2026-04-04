# daily-tech-news STATUS v4.4.0 — 2026-04-05

## 断点
- **本次完成**：pipeline 健壮性全面升级（codex + 人工）
  - `rss_news_collector.py`：新增 `classify_news_with_rules` 规则分类兜底，AI 429/失败时不再卡死
  - `rss_news_collector.py`：新增 `fetch_marketaux_news` + `maybe_collect_external_news`，财经 RSS 不足时可选接入 Marketaux（英文财经兜底，需配 token）
  - `rss_news_collector.py`：新增 `parse_feed_datetime`，独立健壮日期解析（RFC 2822 / ISO 8601 / UTC后缀）
  - `utils.py`：统一 `get_env_var`，自动加载 `.env.local` / `.env`，本地测试不再需要 export
  - `.env.example`：新增本地配置模板
  - `daily-news.yml`：移除无用的 `AI_GATEWAY_API_KEY`，简化入口校验逻辑
  - 新增4个单元测试：日期解析、规则分类、SSL配置、环境变量加载
  - 源数量调整：48 → 46（去掉2个长期失效源）
- **下一步**：
  - 观察 2026-04-05 北京时间 08:30 运行质量，重点看规则分类兜底效果
  - 可选：Marketaux 免费 token 申请（marketaux.com，100次/天，用于财经补源）
  - 可选：财联社 CLS_TOKEN 获取（抓包财联社 APP 登录，彻底解决 403）

## 环境
- 脚本路径：`~/.claude/skills/daily-tech-news/scripts/`
- 核心文件：`rss_news_collector.py`（主逻辑）、`auto_daily_news.py`（入口）、`generate_image.py`（封面图）
- API 配置（支持 `.env.local` 本地文件）：
  - `DOUBAO_API_KEY`：豆包 ARK（AI分类 + 封面图），必填
  - `WECHAT_API_KEY` / `WECHAT_APP_ID`：三更AI 公众号发布
  - `MARKETAUX_API_TOKEN`：可选，英文财经补源
  - `IMGBB_API_KEY`：可选，封面图永久链接
- 定时任务：CF Worker 触发 GitHub Actions，北京时间 08:30

## 已知问题
- wx.limyai.com SSL 证书过期，`SSL_VERIFY=False` 临时跳过（TODO：证书续期后恢复）
- Marketaux 主要是英文财经，对中文财经场景补充有限，建议不配置（静默跳过）
- 财联社 / 财新 RSSHub 路由依赖公共实例，不稳定；根治方案是自建 RSSHub + CLS_TOKEN

## 勿碰
- `logs/` 目录（运营记录，不清理）
- `raw_news_*.json`（原始数据备份）
