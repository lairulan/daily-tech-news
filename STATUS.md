# daily-tech-news STATUS v4.2.0 — 2026-03-13

## 断点
- 本次完成：v4.2.0 内容质量大升级
  - LLM 主力从 doubao-seed-2-0-lite 换成 **Gemini 2.0 Flash**，豆包仅兜底
  - temperature 从 0.7 降到 0.3，减少幻觉
  - 修复 normalize_titles：新增铁律"禁止泛化主语"，严禁用"科研团队/行业机构"替换具体名称
  - 修复 classify_news：排除生物医学/社会新闻，加入语义去重规则
  - 修复微语 prompt：强调语法完整，杜绝乱码
- 下一步：**等明天定时任务跑完**，对比今日内容质量，判断是否需要进一步调整

## 环境
- 脚本路径：`~/.claude/skills/daily-tech-news/scripts/`
- 核心文件：`rss_news_collector.py`（主逻辑）、`auto_daily_news.py`（入口）
- 环境变量：`GOOGLE_API_KEY`（已硬编码默认值）、`WECHAT_API_KEY`、`DOUBAO_API_KEY`（兜底）
- 定时任务：GitHub Actions UTC 00:00 = 北京时间 08:00

## 已知问题
- Google API Key 已硬编码在代码中（GOOGLE_API_KEY 默认值），生产环境建议改为环境变量注入

## 勿碰
- `logs/` 目录（运营记录，不清理）
- `raw_news_*.json`（原始数据备份）
