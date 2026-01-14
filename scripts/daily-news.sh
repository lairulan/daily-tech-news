#!/bin/bash
#
# daily-tech-news 定时执行脚本
# 每天 8:00 自动收集前一天的新闻并发布到公众号
#

# 配置环境变量
export WECHAT_API_KEY="xhs_94c57efb6ea323e2496487fc2a5bcd8a"
export DOUBAO_API_KEY="a26f05b1-4025-4d66-a43d-ea3a64b267cf"

# 配置参数
WORK_DIR="$HOME/.claude/skills/daily-tech-news"
LOG_FILE="$WORK_DIR/logs/daily-news.log"
APPID="wx5c5f1c55d02d1354"  # 三更
PYTHON_SCRIPT="$HOME/.claude/skills/wechat-publish/scripts/publish.py"

# 创建日志目录
mkdir -p "$WORK_DIR/logs"

# 记录开始时间
echo "========================================" >> "$LOG_FILE"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# 计算昨天的日期
YESTERDAY=$(date -v-1d '+%Y年%m月%d日' 2>/dev/null || date -d 'yesterday' '+%Y年%m月%d日' 2>/dev/null)
YESTERDAY_FILE=$(date -v-1d '+%Y%m%d' 2>/dev/null || date -d 'yesterday' '+%Y%m%d' 2>/dev/null)

echo "目标日期: $YESTERDAY" >> "$LOG_FILE"

# 检查是否已存在今日生成的文件
TODAY_FILE=$(date '+%Y%m%d')
if [ -f "$WORK_DIR/news_${TODAY_FILE}.md" ]; then
    echo "今日已生成新闻文件，跳过" >> "$LOG_FILE"
    exit 0
fi

# 调用 Claude Code 执行 daily-tech-news skill
# 这里需要通过 Claude Code 的 API 或者调用方式来执行
# 暂时使用占位符，实际使用时需要配置 Claude Code 的调用方式

echo "等待 Claude Code 执行新闻收集和发布..." >> "$LOG_FILE"

# TODO: 实际调用 Claude Code 的方式
# 选项1: 使用 Claude Code CLI (如果有)
# 选项2: 使用 API 调用
# 选项3: 使用 osascript 与运行中的 Claude Code 交互

echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
