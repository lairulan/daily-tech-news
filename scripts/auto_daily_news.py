#!/usr/bin/env python3
"""
每日科技新闻自动收集和发布脚本 V3.0
每天 8:00 自动运行，收集前一天的 AI/科技/财经新闻并发布到公众号

新增功能：
- 环境预检查 (--check-env)
- 试运行模式 (--dry-run)
- 环境变量配置 AppID (WECHAT_APP_ID)
- 使用 certifi 正确验证 SSL 证书
"""

import os
import sys
import json
import re
import subprocess
import argparse
from datetime import datetime, timedelta

# 尝试导入 certifi 用于正确的 SSL 证书验证
try:
    import certifi
    SSL_VERIFY = certifi.where()
except ImportError:
    SSL_VERIFY = True  # 使用系统证书

import requests
from zhdate import ZhDate

# 配置
WECHAT_API_KEY = os.environ.get("WECHAT_API_KEY")
DOUBAO_API_KEY = os.environ.get("DOUBAO_API_KEY")
# 从环境变量读取 AppID，默认使用三更AI
APPID = os.environ.get("WECHAT_APP_ID", "wx5c5f1c55d02d1354")

# 确定使用哪个 API（优先 OpenRouter）

# 工作目录 - 兼容本地和 GitHub Actions
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.dirname(SCRIPT_DIR)
LOG_FILE = os.path.join(WORK_DIR, "logs", "daily-news.log")

API_BASE = "https://wx.limyai.com/api/openapi"

def check_environment(verbose: bool = True) -> bool:
    """检查运行环境依赖

    Args:
        verbose: 是否打印详细信息

    Returns:
        True 如果所有必需依赖都存在，否则 False
    """
    errors = []
    warnings = []

    # 检查环境变量
    if not WECHAT_API_KEY:
        errors.append("未设置 WECHAT_API_KEY 环境变量")

    if not DOUBAO_API_KEY:
        errors.append("未设置 DOUBAO_API_KEY 环境变量")

    if not os.environ.get("WECHAT_APP_ID"):
        warnings.append(f"未设置 WECHAT_APP_ID，将使用默认公众号 (AppID: {APPID})")

    # 检查脚本文件
    required_scripts = [
        os.path.join(SCRIPT_DIR, "generate_image.py"),
        os.path.join(SCRIPT_DIR, "rss_news_collector.py"),
    ]

    for script in required_scripts:
        if not os.path.exists(script):
            errors.append(f"脚本文件不存在: {script}")

    # 检查 Python 依赖
    try:
        import zhdate
    except ImportError:
        errors.append("未安装 zhdate 包 (pip install zhdate)")

    try:
        import certifi
    except ImportError:
        warnings.append("未安装 certifi 包，将使用系统证书 (pip install certifi)")

    if verbose:
        print("=" * 50)
        print("环境依赖检查")
        print("=" * 50)

        print("\n📋 环境变量:")
        print(f"  {'✅' if WECHAT_API_KEY else '❌'} WECHAT_API_KEY")
        print(f"  {'✅' if os.environ.get('WECHAT_APP_ID') else '⚠️'} WECHAT_APP_ID")
        print(f"  {'✅' if DOUBAO_API_KEY else '❌'} DOUBAO_API_KEY")

        print("\n📁 脚本文件:")
        for script in required_scripts:
            exists = os.path.exists(script)
            print(f"  {'✅' if exists else '❌'} {os.path.basename(script)}")

        if errors:
            print("\n❌ 错误:")
            for error in errors:
                print(f"  • {error}")

        if warnings:
            print("\n⚠️ 警告:")
            for warning in warnings:
                print(f"  • {warning}")

        print("\n" + "=" * 50)
        if not errors:
            print("✅ 环境检查通过")
        else:
            print("❌ 环境检查失败")
        print("=" * 50)

    return len(errors) == 0

def validate_news_content(html_content: str) -> dict:
    """验证新闻内容质量

    Args:
        html_content: HTML 格式的新闻内容

    Returns:
        验证结果字典
    """
    errors = []
    warnings = []

    # 检查内容长度
    if len(html_content) < 500:
        errors.append("内容过短（少于500字符）")

    # 检查是否包含三个分类
    categories = ["AI 领域", "科技动态", "财经要闻"]
    for cat in categories:
        if cat not in html_content:
            errors.append(f"缺少分类: {cat}")

    # 统计新闻条数（通过编号检测）
    news_count = 0
    for i in range(1, 6):
        pattern = rf'0{i}</span>'
        if re.search(pattern, html_content):
            news_count += 1

    if news_count < 5:
        warnings.append(f"每个分类可能不足5条新闻（检测到编号 01-0{news_count}）")

    # 检查微语
    if "微语" not in html_content and "微 语" not in html_content:
        warnings.append("可能缺少微语部分")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }

def get_traditional_lunar_date(dt):
    """获取传统农历日期格式：乙巳年冬月廿七"""
    try:
        zh_date = ZhDate.from_datetime(dt)

        # 获取天干地支年
        chinese_full = zh_date.chinese()
        parts = chinese_full.split()
        gz_year = parts[1] if len(parts) >= 2 else ''

        # 农历月份（传统写法）
        months = ['', '正月', '二月', '三月', '四月', '五月', '六月',
                  '七月', '八月', '九月', '十月', '冬月', '腊月']
        lunar_month = months[zh_date.lunar_month] if 0 < zh_date.lunar_month <= 12 else ''

        # 农历日期（传统写法）
        days = ['', '初一', '初二', '初三', '初四', '初五', '初六', '初七', '初八', '初九', '初十',
                '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十',
                '廿一', '廿二', '廿三', '廿四', '廿五', '廿六', '廿七', '廿八', '廿九', '三十']
        lunar_day = days[zh_date.lunar_day] if 0 < zh_date.lunar_day <= 30 else ''

        result = f'{gz_year}{lunar_month}{lunar_day}'
        if result:  # 如果成功转换，返回结果
            return result
        else:  # 如果转换为空，返回简化显示
            return zh_date.chinese()  # 返回完整中文显示作为回退
    except Exception as e:
        # 真正出错时，记录详细日志并返回空（但不会让程序崩溃）
        print(f"警告：农历日期转换失败 ({dt.strftime('%Y-%m-%d')}): {type(e).__name__}: {e}")
        # 即使出错，也尝试返回基础的星期信息作为补充
        return ""

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
    # 先移除 style 和 script 标签及其内容
    text = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # 移除其他 HTML 标签
    text = re.sub(r'<[^>]+>', ' ', text)
    # 移除多余空白
    text = re.sub(r'\s+', ' ', text).strip()
    # 移除特殊字符编码
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    return text

def call_llm_api(prompt, max_tokens=2000):
    """调用 LLM API（仅使用豆包）"""
    return call_doubao_api(prompt, max_tokens)

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
    except requests.exceptions.HTTPError as e:
        log(f"发布HTTP错误: {e}")
        try:
            error_detail = response.json()
            log(f"错误详情: {error_detail}")
        except:
            log(f"响应内容: {response.text[:500]}")
        return False
    except Exception as e:
        log(f"发布异常: {e}")
        return False

def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="每日科技新闻自动收集和发布脚本 V3.0")
    parser.add_argument("--check-env", action="store_true", help="仅检查环境依赖")
    parser.add_argument("--dry-run", action="store_true", help="试运行（不发布）")
    parser.add_argument("--appid", type=str, help="指定公众号 AppID")
    args = parser.parse_args()

    # 仅检查环境
    if args.check_env:
        success = check_environment(verbose=True)
        sys.exit(0 if success else 1)

    # 检查环境依赖（简略模式）
    if not check_environment(verbose=False):
        log("环境检查失败，请运行 --check-env 查看详情")
        sys.exit(1)

    # 使用命令行指定的 AppID
    global APPID
    if args.appid:
        APPID = args.appid
        log(f"使用指定的 AppID: {APPID}")

    log("=" * 50)
    log("开始执行每日新闻收集任务 V3.0")
    log(f"工作目录: {WORK_DIR}")
    log(f"脚本目录: {SCRIPT_DIR}")
    if args.dry_run:
        log("⚠️ 试运行模式：将不会发布到公众号")

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

    # 质量检查
    log("正在进行质量检查...")
    quality_result = validate_news_content(content)
    if quality_result["errors"]:
        for error in quality_result["errors"]:
            log(f"❌ 质量错误: {error}")
    if quality_result["warnings"]:
        for warning in quality_result["warnings"]:
            log(f"⚠️ 质量警告: {warning}")
    if quality_result["valid"]:
        log("✅ 质量检查通过")

    # 2. 生成封面图
    log("正在生成封面图...")
    cover_url = generate_cover_image(f"{today.month}月{today.day}日AI科技财经日报")
    if not cover_url:
        log("封面图生成失败，将不使用封面图发布")
        cover_url = ""

    # 试运行模式：不发布
    if args.dry_run:
        log("=" * 50)
        log("✅ 试运行完成")
        log(f"标题: {today.month}月{today.day}日AI科技财经日报")
        log(f"内容长度: {len(content)} 字符")
        log(f"封面图: {cover_url or '无'}")
        log("=" * 50)
        sys.exit(0)

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
