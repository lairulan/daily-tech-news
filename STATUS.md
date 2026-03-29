# daily-tech-news STATUS v4.2.1 — 2026-03-29

## 断点
- **本次完成**：修复本地发布三连失败问题
  - `generate_image.py`：AI Gateway → 豆包 Seedream ARK API（doubao-seedream-3-0-t2i-250415）
    - 流程：生成临时 URL → 下载 → 上传 imgbb 获取永久链接（失败则直接用临时 URL）
  - `auto_daily_news.py`：WECHAT_API_KEY / APPID 加默认值，SSL_VERIFY = False（证书过期）
  - 已 push 到 GitHub，commit: `acfe731`
- **下一步**：观察明日（2026-03-30）北京时间 08:00 定时任务是否正常发布

## 环境
- 脚本路径：`~/.claude/skills/daily-tech-news/scripts/`
- 核心文件：`rss_news_collector.py`（主逻辑）、`auto_daily_news.py`（入口）、`generate_image.py`（封面图）
- API 配置（已硬编码默认值）：
  - `WECHAT_API_KEY`：xhs_94c57efb...（微绿流量宝）
  - `WECHAT_APP_ID`：wx5c5f1c55d02d1354（三更AI）
  - `DOUBAO_API_KEY`：bb95205d...（豆包 ARK 封面图）
  - `GOOGLE_API_KEY`：新闻分类主力 Gemini 2.0 Flash
  - `IMGBB_API_KEY`：封面图永久链接托管（需环境变量，无则用临时 URL）
- 定时任务：GitHub Actions UTC 00:00 = 北京时间 08:00

## 已知问题
- wx.limyai.com SSL 证书已过期，SSL_VERIFY = False 临时跳过（TODO：证书续期后恢复）
- IMGBB_API_KEY 未硬编码，本地需设置环境变量，否则封面图用豆包临时 URL

## 勿碰
- `logs/` 目录（运营记录，不清理）
- `raw_news_*.json`（原始数据备份）
