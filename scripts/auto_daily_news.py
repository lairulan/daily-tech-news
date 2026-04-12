#!/usr/bin/env python3
"""
每日科技新闻自动收集和发布脚本 V4.1
支持本地手动运行和 GitHub Actions 定时发布

特性：
- 纯 RSS 模式，46 个源，100% 真实新闻
- RSSHub 多实例 fallback + 分类补救机制
- AI 分类失败时自动切换规则分类兜底
- 财经 RSS 供给不足时支持可选第三方 API 补源
- 环境预检查 (--check-env)
- 试运行模式 (--dry-run)
- 环境变量 / .env.local 配置 AppID 与 API key
- 默认启用 TLS 校验，支持显式降级
"""

import os
import sys
import json
import re
import subprocess
import argparse
from datetime import datetime, timedelta

import requests

# 共享工具
from utils import get_env_var

try:
    import certifi
except ImportError:
    certifi = None

# 配置
WECHAT_API_KEY = get_env_var("WECHAT_API_KEY", required=False)
DOUBAO_API_KEY = get_env_var("DOUBAO_API_KEY", required=False)
# 从环境变量读取 AppID，默认使用三更AI
APPID = get_env_var("WECHAT_APP_ID", default="wx5c5f1c55d02d1354", required=False)  # 三更AI


def parse_bool_env(value: str, default: bool = True) -> bool:
    """解析布尔环境变量。"""
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def resolve_ssl_verify():
    """解析微信发布接口的 TLS 校验配置。"""
    verify_enabled = parse_bool_env(get_env_var("WECHAT_SSL_VERIFY", required=False), default=True)
    if not verify_enabled:
        return False

    ca_bundle = get_env_var("WECHAT_CA_BUNDLE", required=False)
    if ca_bundle:
        return ca_bundle

    if certifi:
        return certifi.where()
    return True


SSL_VERIFY = resolve_ssl_verify()

# 工作目录 - 兼容本地和 GitHub Actions
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.dirname(SCRIPT_DIR)
LOG_FILE = os.path.join(WORK_DIR, "logs", "daily-news.log")

API_BASE = "https://wx.limyai.com/api/openapi"

NON_NEWS_STYLE_KEYWORDS = [
    "一手实测",
    "好用吗",
    "会复刻",
    "不买账",
    "结构性解法",
    "终于来了",
    "唯一代表",
    "高端制造突围",
    "具身领跑",
]

NON_NEWS_STYLE_PATTERNS = [
    r"[?？!！]",
    r"狂揽\d+\+?(?:Star|star|Stars|stars)",
    r"全球\w*新王",
    r"^从.+到.+[:：]",
]

GENERIC_ENGLISH_TOKENS = {
    "agent", "agents", "meta-learning", "wifi", "wi-fi", "star", "stars",
}

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

    if not get_env_var("WECHAT_APP_ID", required=False):
        warnings.append(f"未设置 WECHAT_APP_ID，将使用默认公众号 (AppID: {APPID})")

    if SSL_VERIFY is False:
        warnings.append("WECHAT_SSL_VERIFY=false，微信公众号发布将跳过 TLS 校验")

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
        print(f"  {'✅' if get_env_var('WECHAT_APP_ID', required=False) else '⚠️'} WECHAT_APP_ID")
        print(f"  {'✅' if DOUBAO_API_KEY else '❌'} DOUBAO_API_KEY")
        print(f"  {'⚠️' if SSL_VERIFY is False else '✅'} WECHAT_SSL_VERIFY")

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

    # 检查是否包含三个分类（支持带空格和不带空格两种格式）
    category_checks = [
        ("AI 领域", "AI领域"),
        "科技动态",
        "财经要闻"
    ]
    for cat_check in category_checks:
        if isinstance(cat_check, tuple):
            # 任一匹配即可
            found = any(c in html_content for c in cat_check)
            if not found:
                errors.append(f"缺少分类: {cat_check[0]}")
        else:
            if cat_check not in html_content:
                errors.append(f"缺少分类: {cat_check}")

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

    title_matches = re.findall(r"</span>(.*?)</p>", html_content, re.DOTALL | re.IGNORECASE)
    news_titles = [re.sub(r"<[^>]+>", "", match).strip() for match in title_matches]
    if news_titles and len(news_titles) < 15:
        warnings.append(f"成稿新闻条数少于15条（当前 {len(news_titles)} 条）")

    for index, title in enumerate(news_titles, 1):
        if has_non_news_style(title):
            errors.append(f"第{index}条标题不符合新闻简讯规范: {title[:28]}")
        if has_excessive_english(title):
            errors.append(f"第{index}条标题英文占比过高: {title[:28]}")
        if count_chinese_chars(title) < 8:
            errors.append(f"第{index}条标题中文信息量不足: {title[:28]}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def count_chinese_chars(text: str) -> int:
    """统计文本中的中文字符数。"""
    return len(re.findall(r"[\u4e00-\u9fa5]", text or ""))


def extract_ascii_tokens(text: str) -> list[str]:
    """提取标题中的英文/数字混合词。"""
    return re.findall(r"[A-Za-z][A-Za-z0-9.+\-]*", text or "")


def has_non_news_style(title: str) -> bool:
    """判断标题是否带有提问、评测或营销腔。"""
    title = re.sub(r"\s+", " ", (title or "")).strip()
    if not title:
        return False

    if any(keyword in title for keyword in NON_NEWS_STYLE_KEYWORDS):
        return True

    for pattern in NON_NEWS_STYLE_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return True

    return False


def has_excessive_english(title: str) -> bool:
    """过滤英文占比过高的标题。"""
    title = re.sub(r"\s+", " ", (title or "")).strip()
    if not title:
        return False

    english_tokens = extract_ascii_tokens(title)
    if not english_tokens:
        return False

    chinese_count = count_chinese_chars(title)
    lower_tokens = {token.lower() for token in english_tokens}

    if lower_tokens & GENERIC_ENGLISH_TOKENS:
        return True
    if len(english_tokens) >= 5:
        return True
    if chinese_count < 6 and len(english_tokens) >= 2:
        return True
    if re.match(r"^[A-Za-z][A-Za-z0-9.+\-]*(?:\s+[A-Za-z][A-Za-z0-9.+\-]*)*", title) and chinese_count < 10:
        return True

    return False

def get_traditional_lunar_date(dt):
    """获取传统农历日期格式：乙巳年冬月廿七"""
    try:
        from zhdate import ZhDate
    except ImportError:
        # 让 --check-env 能正常输出依赖缺失，而不是在启动阶段直接崩溃
        return ""

    try:
        zh_date = ZhDate.from_datetime(dt)

        # 获取天干地支年
        chinese_full = zh_date.chinese()
        parts = chinese_full.split()
        gz_year = parts[1] if len(parts) >= 2 else ""

        # 农历月份（传统写法）
        months = ["", "正月", "二月", "三月", "四月", "五月", "六月",
                  "七月", "八月", "九月", "十月", "冬月", "腊月"]
        lunar_month = months[zh_date.lunar_month] if 0 < zh_date.lunar_month <= 12 else ""

        # 农历日期（传统写法）
        days = ["", "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
                "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
                "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"]
        lunar_day = days[zh_date.lunar_day] if 0 < zh_date.lunar_day <= 30 else ""

        result = f"{gz_year}{lunar_month}{lunar_day}"
        if result:
            return result
        return zh_date.chinese()
    except Exception as e:
        # 真正出错时记录日志，保持流程可继续
        print(f"警告：农历日期转换失败 ({dt.strftime('%Y-%m-%d')}): {type(e).__name__}: {e}")
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

def call_doubao_api(prompt, max_tokens=2000):
    """调用豆包 API 生成内容"""
    if not DOUBAO_API_KEY:
        return None
    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    headers = {
        "Authorization": f"Bearer {DOUBAO_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "doubao-seed-2-0-lite-260215",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"豆包 API 调用失败: {e}")
        return None


def call_llm_api(prompt, max_tokens=2000):
    """调用豆包 API"""
    return call_doubao_api(prompt, max_tokens)

def generate_news_html_with_rss(yesterday_str, today_lunar, today_weekday, today_date, weekly=False):
    """使用 RSS 收集器生成真实新闻 HTML 内容

    Args:
        yesterday_str: 昨天的日期字符串（用于新闻内容）
        today_lunar: 今天的农历日期
        today_weekday: 今天的星期
        today_date: 今天的公历日期
        weekly: 是否为周报模式
    """
    log("正在从 RSS 源收集真实新闻...")

    # 调用 RSS 收集器
    rss_script = os.path.join(SCRIPT_DIR, "rss_news_collector.py")
    try:
        log(f"调用 RSS 收集器: {rss_script}")
        cmd = ["python3", rss_script]
        if weekly:
            cmd.append("--weekly")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,  # 15分钟超时，适配多源RSS采集与网络抖动
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
        log(f"RSS 收集超时 (900秒): {e}")
        return None
    except FileNotFoundError as e:
        log(f"RSS 收集器脚本未找到: {e}")
        return None
    except Exception as e:
        log(f"RSS 收集异常: {type(e).__name__}: {e}")
        return None

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

    # 读取 RSS 收集器已生成的摘要（避免重复调用 AI）
    today_str_raw = datetime.now().strftime("%Y%m%d")
    raw_news_file = os.path.join(WORK_DIR, f"raw_news_{today_str_raw}.json")
    summary = None
    if os.path.exists(raw_news_file):
        try:
            with open(raw_news_file, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            summary = raw_data.get("summary", "").strip().strip('"\'')
            if summary:
                log(f"使用RSS收集器摘要: {summary}")
        except Exception:
            pass

    # 如果没有现成摘要，再调用 AI 生成
    if not summary:
        plain_text = extract_text_from_html(content)
        summary_prompt = f"""请根据以下新闻日报内容，生成一句简洁的摘要（20-30字），要求：
1. 提炼出当天最重要的1-2个新闻亮点
2. 语言简洁有力，吸引读者点击
3. 不要包含日期信息

新闻内容：
{plain_text[:800]}"""
        summary = call_llm_api(summary_prompt, max_tokens=100)
        if summary:
            summary = summary.strip().strip('"\'')
            log(f"生成摘要: {summary}")

    payload = {
        "wechatAppid": APPID,
        "title": title,
        "content": content,
        "contentFormat": "html",
        "summary": summary or "AI、科技、财经领域最新资讯汇总",
        "articleType": "news"
    }
    if cover_url:
        payload["coverImage"] = cover_url

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30, verify=SSL_VERIFY)
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
        except Exception:
            log(f"响应内容: {response.text[:500]}")
        return False
    except Exception as e:
        log(f"发布异常: {e}")
        return False

def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="每日科技新闻自动收集和发布脚本 V4.1")
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
    log("开始执行每日新闻收集任务 V4.1")
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

    # 判断是否为周一（周报模式）
    is_monday = today.weekday() == 0
    if is_monday:
        week_end = today - timedelta(days=1)    # 上周日
        week_start = today - timedelta(days=7)  # 上周一
        report_title = (
            f"{week_start.month}月{week_start.day}日-{week_end.month}月{week_end.day}日"
            "AI科技财经周报"
        )
        log(f"周一模式：生成周报，标题: {report_title}")
    else:
        report_title = f"{today.month}月{today.day}日AI科技财经日报"

    log(f"今天日期: {today_date} {today_weekday}")
    log(f"农历日期: {today_lunar}")
    log(f"新闻目标日期: {yesterday_str}")

    # 1. 生成新闻内容（优先使用 RSS 收集器获取真实新闻）
    log("正在生成新闻内容...")
    content = generate_news_html_with_rss(yesterday_str, today_lunar, today_weekday, today_date, weekly=is_monday)

    # 如果 RSS 收集失败，直接退出，不使用AI生成虚假新闻（确保内容真实性）
    if not content:
        log("❌ RSS 收集失败，为确保新闻真实性，任务终止")
        log("请检查网络连接或RSS源可用性")
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
    else:
        log("❌ 质量检查未通过，内容不完整，终止发布")
        log("可能原因: 周末/节假日RSS源更新量不足，或网络问题导致抓取失败")
        sys.exit(1)

    # 2. 生成封面图
    log("正在生成封面图...")
    cover_url = generate_cover_image(report_title)
    if not cover_url:
        log("封面图生成失败，将不使用封面图发布")
        cover_url = None

    # 试运行模式：不发布
    if args.dry_run:
        log("=" * 50)
        log("✅ 试运行完成")
        log(f"标题: {report_title}")
        log(f"内容长度: {len(content)} 字符")
        log(f"封面图: {cover_url or '无'}")
        log("=" * 50)
        sys.exit(0)

    # 3. 保存文件到本地(在发布前保存,确保有备份)
    today_str = today.strftime("%Y%m%d")
    news_file = os.path.join(WORK_DIR, f"news_{today_str}.md")
    try:
        with open(news_file, "w", encoding="utf-8") as f:
            f.write(content)
        log(f"文件已保存: {news_file}")
    except Exception as e:
        log(f"警告:文件保存失败: {e}")

    # 4. 发布到公众号
    log("正在发布到公众号...")
    title = report_title
    success = publish_to_wechat(title, content, cover_url)

    if success:
        log("发布成功！")

        # 5. 不再在 CI 中提交回仓库，避免与 .gitignore 冲突导致误报
        log("发布流程完成（已跳过自动 Git 提交）")

        log("任务完成")
        log("=" * 50)
    else:
        log("发布失败")
        log("=" * 50)
        sys.exit(1)

if __name__ == "__main__":
    main()
