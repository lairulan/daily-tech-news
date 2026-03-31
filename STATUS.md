# daily-tech-news STATUS v4.3.1 — 2026-03-31

## 断点
- **本次完成**：新闻内容质量专项修复
  - `rss_news_collector.py`：入选新闻补抓原文上下文（页面标题 / 导语 / 摘要）
  - `rss_news_collector.py`：标题改写从“长度规范化”升级为“单行新闻简讯”，要求主体明确、事实可追溯
  - `rss_news_collector.py`：新增主体泛化校验、时间表达校验，拦截“项目/模型/计划/事项”等空泛主语
  - `rss_news_collector.py`：加入站点导航噪音清洗、主体候选打分、精确实体回填，减少把站点词当主体
  - `rss_news_collector.py`：加入强过滤关键词，剔除“派早报 / 观察 / 背后 / 盘点”等非简讯素材
  - `rss_news_collector.py`：取消每条新闻下方的补充长文渲染，只保留单行简讯
  - `rss_news_collector.py`：每次运行将 RSS 源健康摘要写入 `raw_news_*.json`
  - `auto_daily_news.py` / `rss_news_collector.py`：Gemini 首次失败后本轮停用，避免重复 400
  - `SKILL.md`：更新为 RSS-only、云端单触发、单行简讯的当前真实流程
- **下一步**：观察 2026-04-01 北京时间 08:30 云端定时发布的标题质量，重点看具体项目名、时间表达和 RSS 空返回源是否稳定

## 环境
- 脚本路径：`~/.claude/skills/daily-tech-news/scripts/`
- 核心文件：`rss_news_collector.py`（主逻辑）、`auto_daily_news.py`（入口）、`generate_image.py`（封面图）
- API 配置（已硬编码默认值）：
  - `WECHAT_API_KEY`：xhs_94c57efb...（微绿流量宝）
  - `WECHAT_APP_ID`：wx5c5f1c55d02d1354（三更AI）
  - `DOUBAO_API_KEY`：bb95205d...（豆包 ARK 封面图）
  - `GOOGLE_API_KEY`：Gemini 可用时参与生成，失败后自动停用
  - `IMGBB_API_KEY`：封面图永久链接托管（需环境变量，无则用临时 URL）
- 定时任务：GitHub Actions UTC 00:30 = 北京时间 08:30

## 已知问题
- wx.limyai.com SSL 证书已过期，SSL_VERIFY = False 临时跳过（TODO：证书续期后恢复）
- IMGBB_API_KEY 未硬编码，本地需设置环境变量，否则封面图用豆包临时 URL
- 部分 RSS 源稳定性一般（如 XML 异常、403、超时），需要继续做源健康治理

## 勿碰
- `logs/` 目录（运营记录，不清理）
- `raw_news_*.json`（原始数据备份）
