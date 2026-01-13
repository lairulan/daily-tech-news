#!/usr/bin/env python3
"""
每日科技新闻自动收集和发布脚本
每天 8:00 自动运行，收集前一天的 AI/科技/财经新闻并发布到公众号
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timedelta
import requests

# 配置
WECHAT_API_KEY = os.environ.get("WECHAT_API_KEY", "xhs_94c57efb6ea323e2496487fc2a5bcd8a")
DOUBAO_API_KEY = os.environ.get("DOUBAO_API_KEY", "a26f05b1-4025-4d66-a43d-ea3a64b267cf")
APPID = "wx5c5f1c55d02d1354"
WORK_DIR = os.path.expanduser("~/.claude/skills/daily-tech-news")
LOG_FILE = os.path.join(WORK_DIR, "logs", "daily-news.log")

API_BASE = "https://wx.limyai.com/api/openapi"

def log(message):
    """记录日志"""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(message)

def call_doubao_api(prompt, max_tokens=2000):
    """调用豆包 API 生成内容"""
    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

    headers = {
        "Authorization": f"Bearer {DOUBAO_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "doubao-pro-256k",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"豆包 API 调用失败: {e}")
        return None

def generate_news_html(yesterday):
    """生成新闻 HTML 内容"""
    prompt = f"""请生成{yesterday}的AI科技财经日报，格式如下（严格按此格式输出，只输出HTML代码）：

<section style="padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', 'PingFang SC', sans-serif;">

<section style="text-align: center; padding: 20px 0 30px 0; background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); border-radius: 15px; margin-bottom: 30px;">
<p style="margin: 0; font-size: 14px; color: #666; letter-spacing: 1px;">农历乙巳年XX月XX</p>
<p style="margin: 8px 0 0 0; font-size: 20px; font-weight: bold; color: #333; letter-spacing: 3px;">星期X</p>
<p style="margin: 8px 0 0 0; font-size: 13px; color: #999;">2026年X月X日</p>
</section>

<section style="margin-bottom: 30px;">
<p style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; font-size: 18px; font-weight: bold; padding: 10px 25px; border-radius: 25px; margin: 0 0 20px 0; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);">📱 AI 领域</p>
<div style="padding: 0 10px;">
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #667eea; font-weight: bold; margin-right: 8px;">01</span>AI新闻1</p>
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #667eea; font-weight: bold; margin-right: 8px;">02</span>AI新闻2</p>
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #667eea; font-weight: bold; margin-right: 8px;">03</span>AI新闻3</p>
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #667eea; font-weight: bold; margin-right: 8px;">04</span>AI新闻4</p>
<p style="margin: 0 0 0 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #667eea; font-weight: bold; margin-right: 8px;">05</span>AI新闻5</p>
</div>
</section>

<section style="margin-bottom: 30px;">
<p style="display: inline-block; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: #fff; font-size: 18px; font-weight: bold; padding: 10px 25px; border-radius: 25px; margin: 0 0 20px 0; box-shadow: 0 4px 15px rgba(245, 87, 108, 0.3);">💻 科技动态</p>
<div style="padding: 0 10px;">
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #f5576c; font-weight: bold; margin-right: 8px;">01</span>科技新闻1</p>
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #f5576c; font-weight: bold; margin-right: 8px;">02</span>科技新闻2</p>
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #f5576c; font-weight: bold; margin-right: 8px;">03</span>科技新闻3</p>
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #f5576c; font-weight: bold; margin-right: 8px;">04</span>科技新闻4</p>
<p style="margin: 0 0 0 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #f5576c; font-weight: bold; margin-right: 8px;">05</span>科技新闻5</p>
</div>
</section>

<section style="margin-bottom: 30px;">
<p style="display: inline-block; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: #fff; font-size: 18px; font-weight: bold; padding: 10px 25px; border-radius: 25px; margin: 0 0 20px 0; box-shadow: 0 4px 15px rgba(79, 172, 254, 0.3);">💰 财经要闻</p>
<div style="padding: 0 10px;">
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #4facfe; font-weight: bold; margin-right: 8px;">01</span>财经新闻1</p>
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #4facfe; font-weight: bold; margin-right: 8px;">02</span>财经新闻2</p>
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #4facfe; font-weight: bold; margin-right: 8px;">03</span>财经新闻3</p>
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #4facfe; font-weight: bold; margin-right: 8px;">04</span>财经新闻4</p>
<p style="margin: 0 0 0 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #4facfe; font-weight: bold; margin-right: 8px;">05</span>财经新闻5</p>
</div>
</section>

<section style="margin-top: 40px; padding: 25px; background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); border-radius: 15px;">
<p style="margin: 0 0 12px 0; font-size: 16px; font-weight: bold; color: #fff; letter-spacing: 2px;">【 微 语 】</p>
<p style="margin: 0; color: #fff; font-size: 15px; line-height: 1.8; text-align: justify;">一句关于技术、创新或人生的励志语录...</p>
</section>

</section>

要求：
1. 每个类别5条新闻，共15条
2. 新闻要真实、重要、最新
3. 每条新闻1-2句话，简洁明了
4. 微语要励志、有深度
5. 只输出HTML代码，不要其他文字"""

    content = call_doubao_api(prompt, max_tokens=3000)
    return content

def generate_cover_image(title):
    """生成封面图"""
    script = os.path.expanduser("~/.claude/skills/wechat-publish/scripts/generate_image.py")

    cmd = [
        "python3", script,
        "cover",
        "--title", title,
        "--style", "tech",
        "--retry", "3",
        "--retry-delay", "3",
        "--size", "2048x2048"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            output = json.loads(result.stdout)
            if output.get("success"):
                return output.get("url")
        log(f"封面图生成失败: {result.stderr}")
        return None
    except Exception as e:
        log(f"封面图生成异常: {e}")
        return None

def publish_to_wechat(title, content, cover_url):
    """发布到微信公众号"""
    url = f"{API_BASE}/wechat-publish"

    headers = {
        "X-API-Key": WECHAT_API_KEY,
        "Content-Type": "application/json"
    }

    # 生成摘要
    summary_prompt = f"请用一句话总结以下新闻日报的主要内容（30字以内）：\n{content[:500]}"
    summary = call_doubao_api(summary_prompt, max_tokens=100)

    payload = {
        "wechatAppid": APPID,
        "title": title,
        "content": content,
        "contentFormat": "html",
        "summary": summary or "AI、科技、财经领域最新资讯汇总",
        "coverImage": cover_url,
        "articleType": "news"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result.get("success", False)
    except Exception as e:
        log(f"发布失败: {e}")
        return False

def main():
    """主函数"""
    log("=" * 50)
    log("开始执行每日新闻收集任务")

    # 计算昨天的日期
    yesterday = datetime.now() - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y年%m月%d日")
    today_str = datetime.now().strftime("%Y%m%d")

    log(f"目标日期: {yesterday_str}")

    # 检查是否已生成
    news_file = os.path.join(WORK_DIR, f"news_{today_str}.md")
    if os.path.exists(news_file):
        log("今日已生成新闻文件，跳过")
        return

    # 1. 生成新闻内容
    log("正在生成新闻内容...")
    content = generate_news_html(yesterday_str)
    if not content:
        log("新闻内容生成失败")
        return

    # 保存内容
    with open(news_file, "w", encoding="utf-8") as f:
        f.write(content)
    log(f"新闻内容已保存到: {news_file}")

    # 2. 生成封面图
    log("正在生成封面图...")
    cover_url = generate_cover_image(f"{yesterday.month}月{yesterday.day}日AI科技财经日报")
    if not cover_url:
        log("封面图生成失败，将不使用封面图发布")
        cover_url = ""

    # 3. 发布到公众号
    log("正在发布到公众号...")
    title = f"{yesterday.month}月{yesterday.day}日AI科技财经日报"
    success = publish_to_wechat(title, content, cover_url)

    if success:
        log("发布成功！")
    else:
        log("发布失败")

    log("任务完成")
    log("=" * 50)

if __name__ == "__main__":
    main()
