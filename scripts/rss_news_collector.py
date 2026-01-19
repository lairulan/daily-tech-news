#!/usr/bin/env python3
"""
基于 RSS 订阅的新闻收集脚本
使用 Python 内置库解析 RSS，无需额外依赖
"""

import os
import sys
import json
import urllib.request
import urllib.error
import ssl
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict
import re
from email.utils import parsedate_to_datetime
from zhdate import ZhDate

# 创建 SSL 上下文（处理证书问题）
ssl_context = ssl._create_unverified_context()

# 配置
DOUBAO_API_KEY = os.environ.get("DOUBAO_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
# 工作目录 - 兼容本地和 GitHub Actions
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.dirname(SCRIPT_DIR)
LOG_FILE = os.path.join(WORK_DIR, "logs", "rss-news.log")

# 检查 API Key - 优先使用 OpenRouter（GitHub Actions 更稳定），备用豆包
if not OPENROUTER_API_KEY and not DOUBAO_API_KEY:
    print("错误: 未设置 OPENROUTER_API_KEY 或 DOUBAO_API_KEY 环境变量")
    print("请运行: export OPENROUTER_API_KEY='your-api-key'")
    print("或者: export DOUBAO_API_KEY='your-api-key'")
    sys.exit(1)

# 确定使用哪个 API
USE_OPENROUTER = bool(OPENROUTER_API_KEY)

# RSS 源配置（优化后：优先使用从 GitHub Actions 美国服务器能稳定访问的源）
ALL_RSS_SOURCES = [
    # 国内源（从美国访问较稳定的）
    {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss", "limit": 10},
    {"name": "36氪", "url": "https://36kr.com/feed", "limit": 10},
    {"name": "虎嗅", "url": "https://www.huxiu.com/rss/0.xml", "limit": 8},
    {"name": "钛媒体", "url": "https://www.tmtpost.com/rss", "limit": 8},
    # 国际源（从美国访问稳定）
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "limit": 8},
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "limit": 8},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "limit": 8},
    {"name": "Wired", "url": "https://www.wired.com/feed/rss", "limit": 5},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "limit": 5},
    {"name": "Reuters Tech", "url": "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best", "limit": 5},
]

# 目标分类
CATEGORIES = ["AI 领域", "科技动态", "财经要闻"]

def log(message):
    """记录日志"""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(message)

def fetch_rss_items(url: str, limit: int = 10, hours_ago: int = 48) -> List[Dict]:
    """获取 RSS 条目"""
    try:
        # 设置用户代理
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as response:
            content = response.read()

        # 解析 XML
        root = ET.fromstring(content)

        # RSS 格式：//rss/channel/item 或 //feed/entry
        items = []
        namespaces = {'': ''}  # 可以根据需要添加命名空间

        # 尝试不同的 RSS/Atom 格式
        item_elements = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')

        # 精确的时间过滤：只收集昨天一整天的新闻
        now = datetime.now()
        yesterday_start = datetime(now.year, now.month, now.day) - timedelta(days=1)  # 昨天 00:00:00
        yesterday_end = datetime(now.year, now.month, now.day) - timedelta(seconds=1)  # 昨天 23:59:59

        # 备用：如果需要更宽松的时间窗口（过去24小时）
        cutoff_time = datetime.now() - timedelta(hours=hours_ago)

        for elem in item_elements[:limit * 2]:
            item = {}

            # 标题 - 更健壮的解析
            title_text = ''
            for title_path in ['title', '{http://www.w3.org/2005/Atom}title']:
                title_elem = elem.find(title_path)
                if title_elem is not None and title_elem.text:
                    title_text = title_elem.text.strip()
                    break
            item['title'] = title_text if title_text else '无标题'

            # 描述/摘要
            desc_text = ''
            for desc_path in ['description', '{http://www.w3.org/2005/Atom}summary', 'content', '{http://www.w3.org/2005/Atom}content']:
                desc_elem = elem.find(desc_path)
                if desc_elem is not None and desc_elem.text:
                    desc_text = desc_elem.text
                    break
            # 移除 HTML 标签
            desc_text = re.sub('<[^<]+?>', '', desc_text)
            desc_text = desc_text.strip()
            item['summary'] = desc_text[:500] if desc_text else ''

            # 链接
            link_text = ''
            for link_path in ['link', '{http://www.w3.org/2005/Atom}link']:
                link_elem = elem.find(link_path)
                if link_elem is not None:
                    # 尝试获取 href 属性或文本
                    link_text = link_elem.get('href', '') or (link_elem.text if link_elem.text else '')
                    if link_text:
                        break
            item['link'] = link_text

            # 发布时间
            pub_text = ''
            for date_path in ['pubDate', '{http://www.w3.org/2005/Atom}published', 'date']:
                date_elem = elem.find(date_path)
                if date_elem is not None and date_elem.text:
                    pub_text = date_elem.text
                    break
            item['published'] = pub_text

            # 来源
            source_text = ''
            for source_path in ['.//title', './/{http://www.w3.org/2005/Atom}title']:
                source_elem = root.find(source_path)
                if source_elem is not None and source_elem.text:
                    source_text = source_elem.text
                    break
            item['source'] = source_text if source_text else '未知来源'

            # 精确的时间检查：只收集昨天的新闻
            if item['published']:
                try:
                    pub_time = parsedate_to_datetime(item['published'])
                    # 转换为本地时区（北京时间）进行比较
                    pub_time_local = pub_time.astimezone()

                    # 提取日期部分进行比较（忽略具体时间）
                    pub_date = pub_time_local.date()
                    yesterday_date = yesterday_start.date()

                    # 只保留昨天的新闻
                    if pub_date != yesterday_date:
                        continue

                    # 记录新闻的发布时间（用于调试）
                    item['parsed_time'] = pub_time_local.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    # 无法解析时间，使用宽松的时间窗口（过去24小时）
                    # 这样可以确保不会遗漏重要新闻
                    pass

            items.append(item)

        return items[:limit]

    except Exception as e:
        log(f"获取 RSS 失败 [{url}]: {e}")
        return []

def collect_all_news() -> List[Dict]:
    """收集所有 RSS 新闻到一起"""
    all_items = []

    # 计算时间范围用于日志
    now = datetime.now()
    yesterday_start = datetime(now.year, now.month, now.day) - timedelta(days=1)
    yesterday_end = datetime(now.year, now.month, now.day) - timedelta(seconds=1)

    log("开始收集 RSS 新闻...")
    log(f"时间过滤范围: {yesterday_start.strftime('%Y-%m-%d %H:%M:%S')} 到 {yesterday_end.strftime('%Y-%m-%d %H:%M:%S')}")

    for source in ALL_RSS_SOURCES:
        log(f"  - {source['name']}")
        items = fetch_rss_items(source['url'], source['limit'])
        for item in items:
            item['rss_source'] = source['name']
        all_items.extend(items)
        log(f"    获取 {len(items)} 条")

    # 去重（基于标题）
    seen_titles = set()
    unique_items = []
    for item in all_items:
        title_lower = item['title'].lower()
        if title_lower not in seen_titles and item['title'] != '无标题':
            seen_titles.add(title_lower)
            unique_items.append(item)

    log(f"收集完成，共获取 {len(unique_items)} 条去重后新闻")
    return unique_items

def classify_news_with_ai(news_items: List[Dict]) -> Dict[str, List[Dict]]:
    """使用 AI 将新闻分类到 3 个类别"""
    log("正在使用 AI 分类新闻...")

    # 准备新闻列表（最多30条，避免 token 过多）
    news_list = news_items[:30]

    # 构建分类 prompt
    news_text = ""
    for i, item in enumerate(news_list, 1):
        news_text += f"{i}. 标题: {item['title']}\n"
        if item['summary']:
            news_text += f"   摘要: {item['summary'][:100]}\n"
        news_text += f"   来源: {item['rss_source']}\n\n"

    prompt = f"""你是一位专业新闻编辑。请将以下新闻严格分类到 3 个类别中：

{news_text}

分类标准：
- **AI 领域**: 人工智能、大模型、机器学习、深度学习、自然语言处理、计算机视觉、机器人、AI应用等
- **科技动态**: 智能手机、电脑、芯片、互联网、软件、游戏、新能源车、航天、5G/6G、创业公司、产品发布等（非AI）
- **财经要闻**: 股市、经济、货币政策、融资、并购、IPO、金融政策、宏观经济、企业财报等

请按以下 JSON 格式输出（只输出 JSON，不要其他文字）：
{{
  "AI 领域": [1, 3, 5, 7, 9],
  "科技动态": [2, 4, 6, 8, 10],
  "财经要闻": [11, 12, 13, 14, 15]
}}

注意：
1. 严格按照分类标准，不要混淆
2. 每个类别选择最重要的 5 条
3. 输出纯 JSON 格式"""

    result = call_llm_api(prompt, max_tokens=2000)
    if not result:
        log("AI 分类失败")
        return {"AI 领域": [], "科技动态": [], "财经要闻": []}

    # 解析 AI 返回的 JSON
    try:
        # 清理可能的 markdown 代码块标记
        result = result.strip()
        if result.startswith('```'):
            result = result.split('\n', 1)[-1]
        if result.endswith('```'):
            result = result.rsplit('\n', 1)[0]
        result = result.strip()

        classification = json.loads(result)

        # 按分类组织新闻
        categorized = {cat: [] for cat in CATEGORIES}

        for category, indices in classification.items():
            if category in CATEGORIES:
                for idx in indices[:5]:  # 每类最多 5 条
                    if idx - 1 < len(news_list):
                        categorized[category].append(news_list[idx - 1])

        log(f"AI 分类完成: AI领域{len(categorized['AI 领域'])}条, 科技动态{len(categorized['科技动态'])}条, 财经要闻{len(categorized['财经要闻'])}条")
        return categorized

    except json.JSONDecodeError as e:
        log(f"解析 AI 分类结果失败: {e}")
        log(f"原始结果: {result[:500]}")
        return {"AI 领域": [], "科技动态": [], "财经要闻": []}

def get_traditional_lunar_date(dt: datetime) -> str:
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

def call_llm_api(prompt: str, max_tokens: int = 4000) -> str:
    """调用 LLM API（优先 OpenRouter，备用豆包）"""

    if USE_OPENROUTER:
        return call_openrouter_api(prompt, max_tokens)
    else:
        return call_doubao_api(prompt, max_tokens)

def call_openrouter_api(prompt: str, max_tokens: int = 4000) -> str:
    """调用 OpenRouter API（从 GitHub Actions 稳定访问）"""
    url = "https://openrouter.ai/api/v1/chat/completions"

    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7
    }

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                'Authorization': f"Bearer {OPENROUTER_API_KEY}",
                'Content-Type': 'application/json',
                'HTTP-Referer': 'https://github.com/lairulan/daily-tech-news',
                'X-Title': 'Daily Tech News'
            }
        )

        with urllib.request.urlopen(req, timeout=120, context=ssl_context) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result["choices"][0]["message"]["content"]

    except Exception as e:
        log(f"OpenRouter API 调用失败: {e}")
        # 如果 OpenRouter 失败且有豆包 key，尝试豆包
        if DOUBAO_API_KEY:
            log("尝试使用豆包 API 作为备用...")
            return call_doubao_api(prompt, max_tokens)
        return None

def call_doubao_api(prompt: str, max_tokens: int = 4000) -> str:
    """调用豆包 API（备用）"""
    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

    payload = {
        "model": "doubao-seed-1-6-lite-251015",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7
    }

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                'Authorization': f"Bearer {DOUBAO_API_KEY}",
                'Content-Type': 'application/json'
            }
        )

        with urllib.request.urlopen(req, timeout=120, context=ssl_context) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result["choices"][0]["message"]["content"]

    except Exception as e:
        log(f"豆包 API 调用失败: {e}")
        return None

def format_news_to_html(categorized_news: Dict[str, List[Dict]], yesterday: str) -> str:
    """将分类后的新闻格式化为 HTML"""
    # 获取今天的日期信息
    today = datetime.now()
    weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    today_weekday = weekday_names[today.weekday()]
    today_date = today.strftime("%Y年%m月%d日")

    # 获取传统农历日期
    today_lunar = get_traditional_lunar_date(today)  # 例如: "乙巳年冬月廿七"

    # 准备新闻摘要
    news_summary = f"以下是{yesterday}通过 RSS 收集并分类的新闻：\n\n"

    for category in CATEGORIES:
        items = categorized_news.get(category, [])
        news_summary += f"\n## {category}\n"
        for i, item in enumerate(items[:5], 1):
            title = item['title'][:100]
            news_summary += f"{i}. {title}\n"

    # 构建 prompt
    prompt = f"""你是一位专业新闻编辑。以下是{yesterday}通过 RSS 收集并分类的新闻：

{news_summary}

请按以下格式输出（只输出 HTML，不要其他内容）：

<section style="padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', 'PingFang SC', sans-serif;">

<section style="text-align: center; padding: 20px 0 30px 0; background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); border-radius: 15px; margin-bottom: 30px;">
<p style="margin: 0; font-size: 14px; color: #666; letter-spacing: 1px;">{today_lunar}</p>
<p style="margin: 8px 0 0 0; font-size: 20px; font-weight: bold; color: #333; letter-spacing: 3px;">{today_weekday}</p>
<p style="margin: 8px 0 0 0; font-size: 13px; color: #999;">{today_date}</p>
</section>

<section style="margin-bottom: 30px;">
<p style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; font-size: 18px; font-weight: bold; padding: 10px 25px; border-radius: 25px; margin: 0 0 20px 0; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);">📱 AI 领域</p>
<div style="padding: 0 10px;">
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #667eea; font-weight: bold; margin-right: 8px;">01</span>新闻内容</p>
</div>
</section>

<section style="margin-bottom: 30px;">
<p style="display: inline-block; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: #fff; font-size: 18px; font-weight: bold; padding: 10px 25px; border-radius: 25px; margin: 0 0 20px 0; box-shadow: 0 4px 15px rgba(245, 87, 108, 0.3);">💻 科技动态</p>
<div style="padding: 0 10px;">
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #f5576c; font-weight: bold; margin-right: 8px;">01</span>新闻内容</p>
</div>
</section>

<section style="margin-bottom: 30px;">
<p style="display: inline-block; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: #fff; font-size: 18px; font-weight: bold; padding: 10px 25px; border-radius: 25px; margin: 0 0 20px 0; box-shadow: 0 4px 15px rgba(79, 172, 254, 0.3);">💰 财经要闻</p>
<div style="padding: 0 10px;">
<p style="margin: 0 0 15px 0; line-height: 1.9; color: #333; font-size: 15px;"><span style="color: #4facfe; font-weight: bold; margin-right: 8px;">01</span>新闻内容</p>
</div>
</section>

<section style="margin-top: 40px; padding: 25px; background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); border-radius: 15px;">
<p style="margin: 0 0 12px 0; font-size: 16px; font-weight: bold; color: #fff; letter-spacing: 2px;">【 微 语 】</p>
<p style="margin: 0; color: #fff; font-size: 15px; line-height: 1.8; text-align: justify;">微语内容</p>
</section>

</section>

要求：使用上述分类后的真实新闻，每类5条，1-2句话概括，生成励志微语，只输出HTML。注意：新闻内容开头不要标注来源媒体。"""

    return call_llm_api(prompt, max_tokens=3000)

def save_raw_news(news_items: List[Dict], categorized: Dict[str, List[Dict]], date_str: str):
    """保存原始新闻数据"""
    raw_file = os.path.join(WORK_DIR, f"raw_news_{date_str}.json")
    with open(raw_file, 'w', encoding='utf-8') as f:
        json.dump({
            "all_news": news_items,
            "categorized": categorized
        }, f, ensure_ascii=False, indent=2)
    log(f"原始新闻已保存: {raw_file}")

def main():
    """主函数"""
    log("=" * 50)
    log("RSS 新闻收集开始")

    # 计算日期
    yesterday = datetime.now() - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y年%m月%d日")
    today_str = datetime.now().strftime("%Y%m%d")

    # 1. 收集所有 RSS 新闻
    all_news = collect_all_news()

    # 2. 使用 AI 分类
    categorized_news = classify_news_with_ai(all_news)

    # 保存原始数据
    save_raw_news(all_news, categorized_news, today_str)

    # 3. 格式化为 HTML
    log("正在格式化新闻...")
    html_content = format_news_to_html(categorized_news, yesterday_str)

    if not html_content:
        log("格式化失败")
        return None

    # 清理可能的 markdown 代码块标记
    html_content = html_content.strip()
    if html_content.startswith('```'):
        html_content = html_content.split('\n', 1)[-1]
        # 移除语言标记如 ```html
        if html_content.startswith('html'):
            html_content = html_content[4:].lstrip()
    if html_content.endswith('```'):
        html_content = html_content.rsplit('\n', 1)[0]
    html_content = html_content.strip()

    # 保存 HTML
    html_file = os.path.join(WORK_DIR, f"news_{today_str}.md")
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    log(f"HTML 已保存: {html_file}")

    log("RSS 新闻收集完成")
    log("=" * 50)

    return html_content

if __name__ == "__main__":
    main()
