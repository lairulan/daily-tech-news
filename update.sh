#!/bin/bash
# 快速更新脚本 - 修改代码后运行此脚本推送

SKILL_DIR="/Users/rulanlai/.claude/skills/daily-tech-news"
cd "$SKILL_DIR"

# 查看修改
echo "📋 查看修改内容..."
git status

# 添加所有修改
echo ""
echo "📦 添加修改..."
git add .

# 提交（使用传入的参数作为提交信息，或默认信息）
COMMIT_MSG="${1:-update: 更新代码}"
git commit -m "$COMMIT_MSG"

# 推送
echo "📤 推送到 GitHub..."
git push

echo ""
echo "✅ 更新完成！GitHub Actions 将使用最新代码。"
