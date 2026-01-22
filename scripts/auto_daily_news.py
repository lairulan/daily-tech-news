#!/usr/bin/env python3
"""
每日科技新闻自动收集和发布脚本
每天 8:00 自动运行，收集前一天的 AI/科技/财经新闻并发布到公众号
"""

import os
import sys
import json
import re
import subprocess
from datetime import datetime, timedelta
import requests
from zhdate import ZhDate

# 配置
WECHAT_API_KEY = os.environ.get("WECHAT_API_KEY")
DOUBAO_API_KEY = os.environ.get("DOUBAO_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
APPID = "wx5c5f1c55d02d1354"  # 三更AI

# 检查必需的环境变量
if not WECHAT_API_KEY:
    print("错误: 未设置 WECHAT_API_KEY 环境变量")
    print("请运行: export WECHAT_API_KEY='your-api-key'")
    sys.exit(1)

if not OPENROUTER_API_KEY and not DOUBAO_API_KEY:
    print("错误: 未设置 OPENROUTER_API_KEY 或 DOUBAO_API_KEY 环境变量")
    print("请运行: export OPENROUTER_API_KEY='your-api-key'")
    print("或者: export DOUBAO_API_KEY='your-api-key'")
    sys.exit(1)

# 确定使用哪个 API（优先 OpenRouter）
USE_OPENROUTER = bool(OPENROUTER_API_KEY)

# 工作目录 - 兼容本地和 GitHub Actions
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.dirname(SCRIPT_DIR)
LOG_FILE = os.path.join(WORK_DIR, "logs", "daily-news.log")

API_BASE = "https://wx.limyai.com/api/openapi"

def get_traditional_lunar_date(dt):
    """获取传统农历日期格式：乙巳年冬月廿七"""
    zh_date = ZhDate.from_datetime(dt)

    # 获取天干地支年
    chinese_full = zh_date.chinese()
    parts = chinese_full.split()
    gz_year = parts[1] if len(parts) >= 2 else ''

    # 农历月份（传统写法）
    months = ['', '正月', '二月', '三月', '四月', '五月', '六月',
              '七月', '八月', '九月', '十月', '冬月', '腊月']
    lunar_month = months[zh_date.lunar_month]

    # 农历日期（传统写法）
    days = ['', '初一', '初二', '初三', '初四', '初五', '初六', '初七', '初八', '初九', '初十',
            '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十',
            '廿一', '廿二', '廿三', '廿四', '廿五', '廿六', '廿七', '廿八', '廿九', '三十']
    lunar_day = days[zh_date.lunar_day]

    return f'{gz_year}{lunar_month}{lunar_day}'

def log(message):
    """记录日志"""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_msg + "\n")
    except Exception:
        pass  # 日志写入失败不影响主流程

def extract_text_from_html(html_content):
    """从 HTML 中提取纯文本内容，用于生成摘要"""
    # 移除 HTML 标签
    text = re.sub(r'<[^>]+>', ' ', html_content)
    # 移除多余空白
    text = re.sub(r'\s+', ' ', text).strip()
    # 移除特殊字符编码
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    return text

def call_llm_api(prompt, max_tokens=2000):
    """调用 LLM API（优先 OpenRouter，备用豆包）"""
    if USE_OPENROUTER:
        return call_openrouter_api(prompt, max_tokens)
    else:
        return call_doubao_api(prompt, max_tokens)

def call_openrouter_api(prompt, max_tokens=2000):
    """调用 OpenRouter API（从 GitHub Actions 稳定访问）"""
    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/lairulan/daily-tech-news",
        "X-Title": "Daily Tech News"
    }

    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"OpenRouter API 调用失败: {e}")
        # 如果 OpenRouter 失败且有豆包 key，尝试豆包
        if DOUBAO_API_KEY:
            log("尝试使用豆包 API 作为备用...")
            return call_doubao_api(prompt, max_tokens)
        return None

def call_doubao_api(prompt, max_tokens=2000):
    """调用豆包 API 生成内容（备用）"""
    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

    headers = {
        "Authorization": f"Bearer {DOUBAO_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "doubao-seed-1-6-lite-251015",
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

def generate_news_html_with_rss(yesterday_str, today_lunar, today_weekday, today_date):
    """使用 RSS 收集器生成真实新闻 HTML 内容

    Args:
        yesterday_str: 昨天的日期字符串（用于新闻内容）
        today_lunar: 今天的农历日期
        today_weekday: 今天的星期
        today_date: 今天的公历日期
    """
    log("正在从 RSS 源收集真实新闻...")

    # 调用 RSS 收集器
    rss_script = os.path.join(SCRIPT_DIR, "rss_news_collector.py")
    try:
        log(f"调用 RSS 收集器: {rss_script}")
        result = subprocess.run(
            ["python3", rss_script],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=SCRIPT_DIR
        )

        # 记录 stdout 和 stderr
        if result.stdout:
            log(f"RSS 收集器输出: {result.stdout[:500]}")
        if result.stderr:
            log(f"RSS 收集器错误: {result.stderr[:500]}")

        if result.returncode != 0:
            log(f"RSS 收集失败，退出码: {result.returncode}")
            return None

        log("RSS 新闻收集成功")

        # 读取生成的 HTML 文件
        today_str = datetime.now().strftime("%Y%m%d")
        html_file = os.path.join(WORK_DIR, f"news_{today_str}.md")

        if not os.path.exists(html_file):
            log(f"HTML 文件不存在: {html_file}")
            return None

        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        if not html_content or len(html_content) < 100:
            log(f"HTML 内容为空或过短: {len(html_content)} 字符")
            return None

        # 替换日期卡片为紫色渐变样式
        # 原样式是浅色渐变，需要替换为紫色渐变
        old_date_card = '<section style="text-align: center; padding: 20px 0 30px 0; background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); border-radius: 15px; margin-bottom: 30px;">'
        new_date_card = '<section style="text-align: center; padding: 25px 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 20px; margin-bottom: 30px; box-shadow: 0 8px 20px rgba(102, 126, 234, 0.3);">'

        html_content = html_content.replace(old_date_card, new_date_card)

        # 更新日期卡片中的文字颜色为白色
        import re
        # 替换日期卡片内的颜色
        html_content = re.sub(
            r'<p style="margin: 0; font-size: 14px; color: #666;',
            '<p style="margin: 0; font-size: 13px; color: rgba(255,255,255,0.8);',
            html_content
        )
        html_content = re.sub(
            r'<p style="margin: 8px 0 0 0; font-size: 20px; font-weight: bold; color: #333;',
            '<p style="margin: 10px 0; font-size: 28px; font-weight: bold; color: #fff;',
            html_content
        )
        html_content = re.sub(
            r'<p style="margin: 8px 0 0 0; font-size: 13px; color: #999;',
            '<p style="margin: 0; font-size: 14px; color: rgba(255,255,255,0.9);',
            html_content
        )

        return html_content

    except subprocess.TimeoutExpired as e:
        log(f"RSS 收集超时 (180秒): {e}")
        return None
    except FileNotFoundError as e:
        log(f"RSS 收集器脚本未找到: {e}")
        return None
    except Exception as e:
        log(f"RSS 收集异常: {type(e).__name__}: {e}")
        return None

def generate_news_html(yesterday_str, today_lunar, today_weekday, today_date):
    """生成新闻 HTML 内容（备用方案，如果 RSS 失败则使用）

    Args:
        yesterday_str: 昨天的日期字符串（用于新闻内容）
        today_lunar: 今天的农历日期
        today_weekday: 今天的星期
        today_date: 今天的公历日期
    """
    prompt = f"""请生成{yesterday_str}的AI科技财经日报。

重要说明：
1. 日期卡片显示的是今天（{today_date}）的日期信息
2. 新闻内容是昨天（{yesterday_str}）发生的事情
3. 严格按照以下格式输出，只输出HTML代码

<section style="padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', 'PingFang SC', sans-serif; background: #f8f9fa;">

<!-- 日期卡片 - 显示今天的日期 -->
<section style="text-align: center; padding: 25px 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 20px; margin-bottom: 30px; box-shadow: 0 8px 20px rgba(102, 126, 234, 0.3);">
<p style="margin: 0; font-size: 13px; color: rgba(255,255,255,0.8); letter-spacing: 1px;">{today_lunar}</p>
<p style="margin: 10px 0; font-size: 28px; font-weight: bold; color: #fff; letter-spacing: 4px;">{today_weekday}</p>
<p style="margin: 0; font-size: 14px; color: rgba(255,255,255,0.9);">{today_date}</p>
</section>

<!-- AI 领域 -->
<section style="margin-bottom: 25px; background: #fff; border-radius: 15px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.08);">
<p style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; font-size: 18px; font-weight: bold; padding: 10px 25px; border-radius: 25px; margin: 0 0 20px 0; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);">📱 AI 领域</p>
<div style="padding: 0 10px;">
<p style="margin: 0 0 15px 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #667eea;"><span style="color: #667eea; font-weight: bold; margin-right: 10px;">01</span>AI新闻1</p>
<p style="margin: 0 0 15px 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #667eea;"><span style="color: #667eea; font-weight: bold; margin-right: 10px;">02</span>AI新闻2</p>
<p style="margin: 0 0 15px 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #667eea;"><span style="color: #667eea; font-weight: bold; margin-right: 10px;">03</span>AI新闻3</p>
<p style="margin: 0 0 15px 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #667eea;"><span style="color: #667eea; font-weight: bold; margin-right: 10px;">04</span>AI新闻4</p>
<p style="margin: 0 0 0 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #667eea;"><span style="color: #667eea; font-weight: bold; margin-right: 10px;">05</span>AI新闻5</p>
</div>
</section>

<!-- 科技动态 -->
<section style="margin-bottom: 25px; background: #fff; border-radius: 15px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.08);">
<p style="display: inline-block; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: #fff; font-size: 18px; font-weight: bold; padding: 10px 25px; border-radius: 25px; margin: 0 0 20px 0; box-shadow: 0 4px 15px rgba(245, 87, 108, 0.3);">💻 科技动态</p>
<div style="padding: 0 10px;">
<p style="margin: 0 0 15px 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #f5576c;"><span style="color: #f5576c; font-weight: bold; margin-right: 10px;">01</span>科技新闻1</p>
<p style="margin: 0 0 15px 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #f5576c;"><span style="color: #f5576c; font-weight: bold; margin-right: 10px;">02</span>科技新闻2</p>
<p style="margin: 0 0 15px 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #f5576c;"><span style="color: #f5576c; font-weight: bold; margin-right: 10px;">03</span>科技新闻3</p>
<p style="margin: 0 0 15px 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #f5576c;"><span style="color: #f5576c; font-weight: bold; margin-right: 10px;">04</span>科技新闻4</p>
<p style="margin: 0 0 0 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #f5576c;"><span style="color: #f5576c; font-weight: bold; margin-right: 10px;">05</span>科技新闻5</p>
</div>
</section>

<!-- 财经要闻 -->
<section style="margin-bottom: 25px; background: #fff; border-radius: 15px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.08);">
<p style="display: inline-block; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: #fff; font-size: 18px; font-weight: bold; padding: 10px 25px; border-radius: 25px; margin: 0 0 20px 0; box-shadow: 0 4px 15px rgba(79, 172, 254, 0.3);">💰 财经要闻</p>
<div style="padding: 0 10px;">
<p style="margin: 0 0 15px 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #4facfe;"><span style="color: #4facfe; font-weight: bold; margin-right: 10px;">01</span>财经新闻1</p>
<p style="margin: 0 0 15px 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #4facfe;"><span style="color: #4facfe; font-weight: bold; margin-right: 10px;">02</span>财经新闻2</p>
<p style="margin: 0 0 15px 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #4facfe;"><span style="color: #4facfe; font-weight: bold; margin-right: 10px;">03</span>财经新闻3</p>
<p style="margin: 0 0 15px 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #4facfe;"><span style="color: #4facfe; font-weight: bold; margin-right: 10px;">04</span>财经新闻4</p>
<p style="margin: 0 0 0 0; line-height: 2; color: #333; font-size: 15px; padding-left: 5px; border-left: 3px solid #4facfe;"><span style="color: #4facfe; font-weight: bold; margin-right: 10px;">05</span>财经新闻5</p>
</div>
</section>

<!-- 微语 -->
<section style="margin-top: 30px; padding: 25px; background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); border-radius: 15px; box-shadow: 0 4px 15px rgba(250, 112, 154, 0.3);">
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

    content = call_llm_api(prompt, max_tokens=3000)

    # 清理markdown代码块标记
    if content:
        content = content.strip()
        # 移除开头的 ```html 或 ```
        if content.startswith("```html"):
            content = content[7:].strip()
        elif content.startswith("```"):
            content = content[3:].strip()
        # 移除结尾的 ```
        if content.endswith("```"):
            content = content[:-3].strip()

    return content

def generate_cover_image(title):
    """生成封面图"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(script_dir, "generate_image.py")

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
        log(f"调用封面图生成器: {script}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=script_dir)

        # 记录输出
        if result.stdout:
            log(f"封面图生成器输出: {result.stdout[:300]}")
        if result.stderr:
            log(f"封面图生成器错误: {result.stderr[:300]}")

        if result.returncode == 0:
            try:
                output = json.loads(result.stdout)
                if output.get("success"):
                    cover_url = output.get("url")
                    log(f"封面图生成成功: {cover_url}")
                    return cover_url
                else:
                    log(f"封面图生成失败: {output.get('error', '未知错误')}")
            except json.JSONDecodeError as e:
                log(f"解析封面图生成器输出失败: {e}")
        else:
            log(f"封面图生成失败，退出码: {result.returncode}")

        return None
    except subprocess.TimeoutExpired as e:
        log(f"封面图生成超时 (120秒): {e}")
        return None
    except FileNotFoundError as e:
        log(f"封面图生成器脚本未找到: {e}")
        return None
    except Exception as e:
        log(f"封面图生成异常: {type(e).__name__}: {e}")
        return None

def publish_to_wechat(title, content, cover_url):
    """发布到微信公众号"""
    url = f"{API_BASE}/wechat-publish"

    headers = {
        "X-API-Key": WECHAT_API_KEY,
        "Content-Type": "application/json"
    }

    # 生成摘要 - 先提取纯文本再让 AI 生成摘要
    plain_text = extract_text_from_html(content)
    summary_prompt = f"""请根据以下新闻日报内容，生成一句简洁的摘要（20-30字），要求：
1. 提炼出当天最重要的1-2个新闻亮点
2. 语言简洁有力，吸引读者点击
3. 不要包含日期信息

新闻内容：
{plain_text[:800]}"""
    summary = call_llm_api(summary_prompt, max_tokens=100)
    if summary:
        # 清理可能的多余内容
        summary = summary.strip().strip('"\'')
        log(f"生成摘要: {summary}")

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
        log(f"API响应: {result}")
        success = result.get("success", False)
        if not success:
            log(f"发布失败原因: {result.get('error', result)}")
        return success
    except Exception as e:
        log(f"发布异常: {e}")
        return False

def main():
    """主函数"""
    log("=" * 50)
    log("开始执行每日新闻收集任务")
    log(f"工作目录: {WORK_DIR}")
    log(f"脚本目录: {SCRIPT_DIR}")

    # 计算日期
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    # 格式化日期字符串
    yesterday_str = yesterday.strftime("%Y年%m月%d日")
    today_date = today.strftime("%Y年%m月%d日")

    # 获取今天的星期
    weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    today_weekday = weekday_names[today.weekday()]

    # 获取传统农历日期
    today_lunar = get_traditional_lunar_date(today)  # 例如: "乙巳年冬月廿七"

    log(f"今天日期: {today_date} {today_weekday}")
    log(f"农历日期: {today_lunar}")
    log(f"新闻目标日期: {yesterday_str}")

    # 1. 生成新闻内容（优先使用 RSS 收集器获取真实新闻）
    log("正在生成新闻内容...")
    content = generate_news_html_with_rss(yesterday_str, today_lunar, today_weekday, today_date)

    # 如果 RSS 收集失败，使用备用方案
    if not content:
        log("RSS 收集失败，使用备用方案生成新闻...")
        content = generate_news_html(yesterday_str, today_lunar, today_weekday, today_date)

    if not content:
        log("新闻内容生成失败")
        sys.exit(1)

    log(f"生成的内容长度: {len(content)} 字符")

    # 2. 生成封面图
    log("正在生成封面图...")
    cover_url = generate_cover_image(f"{today.month}月{today.day}日AI科技财经日报")
    if not cover_url:
        log("封面图生成失败，将不使用封面图发布")
        cover_url = ""

    # 3. 发布到公众号
    log("正在发布到公众号...")
    title = f"{today.month}月{today.day}日AI科技财经日报"
    success = publish_to_wechat(title, content, cover_url)

    if success:
        log("发布成功！")
        log("任务完成")
        log("=" * 50)
    else:
        log("发布失败")
        log("=" * 50)
        sys.exit(1)

if __name__ == "__main__":
    main()
