#!/usr/bin/env python3
"""
基于 RSS 订阅的新闻收集脚本 V3.0
使用 Python 内置库解析 RSS，无需额外依赖

新增功能：
- 请求速率限制（0.5秒间隔）
- 使用 certifi 正确验证 SSL 证书
- 共享工具函数
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
import time
from email.utils import parsedate_to_datetime
import requests

# 尝试导入 certifi 用于正确的 SSL 证书验证
try:
    import certifi
    ssl_context = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    # 如果 certifi 不可用，使用不验证证书的上下文（备用）
    ssl_context = ssl._create_unverified_context()

# 导入共享工具函数
try:
    from utils import get_traditional_lunar_date, get_weekday_name
except ImportError:
    # 如果导入失败，使用本地定义
    from zhdate import ZhDate

    def get_traditional_lunar_date(dt: datetime) -> str:
        """获取传统农历日期格式：乙巳年冬月廿七"""
        try:
            zh_date = ZhDate.from_datetime(dt)
            chinese_full = zh_date.chinese()
            parts = chinese_full.split()
            gz_year = parts[1] if len(parts) >= 2 else ''
            months = ['', '正月', '二月', '三月', '四月', '五月', '六月',
                      '七月', '八月', '九月', '十月', '冬月', '腊月']
            lunar_month = months[zh_date.lunar_month]
            days = ['', '初一', '初二', '初三', '初四', '初五', '初六', '初七', '初八', '初九', '初十',
                    '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十',
                    '廿一', '廿二', '廿三', '廿四', '廿五', '廿六', '廿七', '廿八', '廿九', '三十']
            lunar_day = days[zh_date.lunar_day]
            return f'{gz_year}{lunar_month}{lunar_day}'
        except (TypeError, ValueError, IndexError) as e:
            # zhdate 库可能无法处理某些日期（如2026年2月），返回空字符串
            print(f"警告：农历日期转换失败 ({dt}): {e}")
            return ""

    def get_weekday_name(dt: datetime) -> str:
        """获取中文星期名称"""
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        return weekday_names[dt.weekday()]

# 速率限制配置
REQUEST_DELAY = 0.5  # 请求间隔（秒）

# 排除规则：过滤掉无效或低质量的标题
TITLE_EXCLUDE_PATTERNS = [
    r"^本文[将能可]?",  # 以"本文"开头的标题
    r"^一文带你",  # "一文带你了解..."
    r"^一张图",  # "一张图看懂..."
    r"^视频：",  # 视频标题
    r"^直播：",  # 直播标题
    r"^问答：",  # 问答标题
    r"^采访：",  # 采访标题
    r"^独家",  # 独家内容（通常需要上下文）
    r"^重磅",  # 重磅消息（通常需要上下文）
    r"^突发",  # 突发新闻（通常需要上下文）
    r"[?？]$",  # 以问号结尾的标题（通常是引导性问题，不是新闻）
    r"^[^a-zA-Z0-9\u4e00-\u9fa5]",  # 以非字母数字中文开头（可能是特殊格式）
]

# 排除关键词（任何匹配这些关键词的标题都会被过滤）
# 但如果标题同时包含科技/AI/财经关键词，则保留
TITLE_EXCLUDE_KEYWORDS = [
    "红包大战",
    "春晚",
    "春节",
    "过年",
    "元宵节",
    "中秋节",
    "端午节",
    "清明节",
    "国庆节",
    "五一",
    "妇女节",
    "情人节",
    "圣诞节",
    "平安夜",
    "双十一",
    "618",
    "年货节",
    "促销",
    "优惠",
    "打折",
    "抽奖",
    "福利",
    "送礼",
    "养生",
    "食疗",
    "减肥",
    "美容",
    "护肤",
    "整形",
]

# 如果标题包含以下关键词，即使有排除关键词也保留
KEEP_KEYWORDS = [
    "AI", "大模型", "LLM", "ChatGPT", "OpenAI", "Google", "Meta", "微软",
    "英伟达", "NVIDIA", "芯片", "GPU", "模型", "算法", "机器学习", "深度学习",
    "自动驾驶", "智能驾驶", "电动车", "Tesla", "比亚迪",
    "融资", "投资", "上市", "IPO", "并购", "收购",
    "营收", "净利润", "财报", "业绩", "股价", "市值",
    "美元", "人民币", "加息", "降息", "央行", "美联储",
    "石油", "天然气", "能源", "油价", "OPEC",
    "手机", "电脑", "笔记本", "平板", "iPhone", "Android",
    "发布", "推出", "上线", "产品", "服务",
    "技术", "研究", "突破", "创新",
]


def is_valid_news_title(title: str) -> bool:
    """检查标题是否为有效的新闻标题

    Args:
        title: 新闻标题

    Returns:
        True 如果标题有效，否则 False
    """
    if not title or len(title.strip()) < 8:
        return False

    # 清理标题
    title = title.strip()

    # 检查排除模式
    for pattern in TITLE_EXCLUDE_PATTERNS:
        if re.match(pattern, title):
            # 检查是否有保留关键词
            has_keep_keyword = any(kw.lower() in title.lower() for kw in KEEP_KEYWORDS)
            if not has_keep_keyword:
                return False

    # 检查排除关键词
    for keyword in TITLE_EXCLUDE_KEYWORDS:
        if keyword in title:
            # 检查是否有保留关键词
            has_keep_keyword = any(kw.lower() in title.lower() for kw in KEEP_KEYWORDS)
            if not has_keep_keyword:
                return False

    # 检查标题是否包含新闻要素（至少包含以下之一）
    news_elements = [
        "发布", "推出", "推出", "上线", "融资", "投资", "收购", "并购",
        "获得", "完成", "宣布", "召开", "举行", "成立", "上市",
        "产品", "服务", "公司", "企业", "机构", "平台",
        "技术", "研究", "开发", "实现", "突破", "创新",
        "市场", "行业", "领域", "全球", "中国", "美国", "欧洲",
        "AI", "大模型", "模型", "模型", "算法", "芯片", "GPU",
        "净利润", "营收", "财报", "利润", "销售额",
    ]

    has_news_element = any(elem in title for elem in news_elements)
    if not has_news_element:
        # 如果没有新闻要素，检查是否是事件类标题
        event_patterns = [
            r"\d+月\d+日",  # 日期
            r"\d+日",  # 某日
            r"北京", "上海", "深圳", "广州", "杭州",
            r"年度", r"季度", r"月份",
            r"首次", r"第一届", r"第二届",
        ]
        has_event = any(re.search(p, title) for p in event_patterns)
        if not has_event:
            return False

    return True

# 配置
DOUBAO_API_KEY = os.environ.get("DOUBAO_API_KEY")
# 工作目录 - 兼容本地和 GitHub Actions
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.dirname(SCRIPT_DIR)
LOG_FILE = os.path.join(WORK_DIR, "logs", "rss-news.log")

# 检查 API Key - 优先使用 OpenRouter（GitHub Actions 更稳定），备用豆包
if not DOUBAO_API_KEY:
    print("错误: 未设置 DOUBAO_API_KEY 环境变量")
    print("请运行: export DOUBAO_API_KEY='your-api-key'")
    print("或者: export DOUBAO_API_KEY='your-api-key'")
    sys.exit(1)

# 确定使用哪个 API

# RSS 源配置（优化后：优先使用从 GitHub Actions 美国服务器能稳定访问的源）
ALL_RSS_SOURCES = [
    # 国内源（从美国访问较稳定的）
    {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss", "limit": 15},
    {"name": "36氪", "url": "https://36kr.com/feed", "limit": 15},
    {"name": "虎嗅", "url": "https://www.huxiu.com/rss/0.xml", "limit": 12},
    {"name": "钛媒体", "url": "https://www.tmtpost.com/rss", "limit": 12},
    {"name": "极客公园", "url": "https://www.geekpark.net/feed", "limit": 10},
    {"name": "爱范儿", "url": "https://www.ifanr.com/feed", "limit": 10},
    {"name": "少数派", "url": "https://sspai.com/feed", "limit": 8},
    {"name": "品玩", "url": "https://www.pingwest.com/feed", "limit": 10},
    # 国际源（从美国访问稳定）
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "limit": 12},
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "limit": 12},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "limit": 10},
    {"name": "Wired", "url": "https://www.wired.com/feed/rss", "limit": 8},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "limit": 8},
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "limit": 8},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/ai/feed/", "limit": 8},
]

# 目标分类
CATEGORIES = ["AI 领域", "科技动态", "财经要闻"]

def log(message):
    """记录日志"""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(message, flush=True)  # 确保输出立即刷新

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

            # 精确的时间检查：只收集昨天的新闻（严格模式）
            if not item['published']:
                # 没有发布时间的新闻，跳过以确保内容真实性
                continue

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
            except Exception as e:
                # 无法解析时间格式，跳过此新闻以确保内容真实性
                # 不记录日志避免刷屏，这是正常的过滤行为
                continue

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

        # 添加速率限制，避免请求过快
        time.sleep(REQUEST_DELAY)

    # 去重（基于标题）
    seen_titles = set()
    unique_items = []
    invalid_count = 0
    for item in all_items:
        title = item['title']
        title_lower = title.lower()

        # 检查标题是否有效
        if not is_valid_news_title(title):
            invalid_count += 1
            log(f"  过滤无效标题: {title[:30]}...")
            continue

        if title_lower not in seen_titles and title != '无标题':
            seen_titles.add(title_lower)
            unique_items.append(item)

    if invalid_count > 0:
        log(f"已过滤 {invalid_count} 条无效标题")

    log(f"收集完成，共获取 {len(unique_items)} 条去重后新闻")
    return unique_items


def generate_supplement_news(target_count: int = 15) -> List[Dict]:
    """使用 AI 生成补充新闻（当 RSS 收集不足时）- 兼容版本

    生成平衡的3类新闻，每类约5条

    Args:
        target_count: 目标新闻数量

    Returns:
        补充的新闻列表
    """
    log(f"RSS 新闻不足，使用 AI 补充新闻（目标 {target_count} 条）...")

    today = datetime.now()
    today_str = today.strftime("%Y年%m月%d日")

    # 每类生成5条
    per_category = 5

    prompt = f"""请生成{today_str}可能发生的AI、科技、财经领域新闻标题。

⚠️ 重要约束：
1. 所有标题必须是{today_str}前后可能发生的事件
2. 不要引用具体的历史数据（如股价、汇率、商品价格等）
3. 避免使用过时的统计数字或时间节点
4. 如果涉及财经数据，使用"上涨"、"下跌"、"波动"等趋势词，不要写具体数字
5. 聚焦公司动态、产品发布、政策发布等非数据类事件
6. **每条新闻只描述一个单一事件**，严禁多条消息合并
7. **严禁使用"早报"、"本周动态"、"X条动态"等多消息合并形式**

内容要求：
1. 生成 {per_category * 3} 条新闻标题（AI领域{per_category}条、科技动态{per_category}条、财经要闻{per_category}条）
2. 每条标题必须有具体的事件、公司名、产品名等
3. 格式：每行一个标题，不要序号
4. **严格控制在 30-50 字之间**（不少于30字，不超过50字）
5. 每条新闻独立成句，信息点单一清晰

分类要求（按顺序每类5条）：
- AI领域（前5条）：大模型、AI产品发布、AI公司融资、AI研究突破、AI应用等
- 科技动态（接下来5条）：手机、电脑、互联网产品、科技公司动态、新能源车等
- 财经要闻（最后5条）：股市、融资、并购、财报、能源、货币政策等（不要具体价格数据）

✅ 推荐示例：
阿里云发布通义千问3.5大模型，多模态能力全面升级
苹果正式推出iPhone16系列，相机系统迎来重大革新
宁德时代发布2025年财报，全年净利润超市场预期

❌ 禁止示例：
比特币价格突破50000美元关口（具体价格可能过时）
黄金期货涨至2800美元每盎司（历史数据）
美联储宣布加息50个基点至4.5%（具体数字可能过时）
本周出海三动态：中东光伏短期交付受阻，欧盟废除小额包裹免税政策（多条消息合并）
今日早报：苹果发布新品，vivo新旗舰上市（多条消息合并）

请直接输出 {per_category * 3} 条新闻标题，每行一条："""

    result = call_llm_api(prompt, max_tokens=1200)
    if not result:
        log("AI 生成补充新闻失败")
        return []

    # 解析标题
    titles = [line.strip() for line in result.strip().split('\n') if line.strip()]
    titles = [re.sub(r'^\d+[.、]\s*', '', title).strip() for title in titles]

    # 转换为新闻格式（按顺序分类，前5条AI，中间5条科技，最后5条财经）
    news_items = []
    sources = ["AI补充生成", "科技补充生成", "财经补充生成"]

    for i, title in enumerate(titles[:target_count]):
        if len(title) < 8:
            continue

        # 按位置分配类别
        if i < per_category:
            source = sources[0]  # AI领域
        elif i < per_category * 2:
            source = sources[1]  # 科技动态
        else:
            source = sources[2]  # 财经要闻

        news_items.append({
            "title": title,
            "summary": "",
            "link": "",
            "published": today.strftime("%a, %d %b %Y %H:%M:%S +0800"),
            "source": source,
            "parsed_time": today.strftime("%Y-%m-%d %H:%M:%S"),
            "rss_source": source
        })

    log(f"AI 补充生成 {len(news_items)} 条新闻")
    return news_items


def generate_category_supplement_news(category: str, count: int) -> List[Dict]:
    """针对特定类别生成补充新闻

    Args:
        category: 类别名称（AI领域/科技动态/财经要闻）
        count: 需要补充的数量

    Returns:
        补充的新闻列表
    """
    log(f"针对 {category} 类别补充 {count} 条新闻...")

    today = datetime.now()
    today_str = today.strftime("%Y年%m月%d日")

    # 根据类别设置不同的 prompt
    category_prompts = {
        "AI领域": """请生成今天可能发生的AI领域新闻标题。

⚠️ 重要约束：
1. 所有标题必须是近期可能发生的事件
2. 聚焦公司动态、产品发布、研究突破等确定性事件
3. 避免使用可能过时的统计数字或排名

内容要求：
1. 生成 {count} 条新闻标题
2. 每条标题有具体公司名、产品名或事件
3. 格式：每行一个标题，不要序号
4. **严格控制在 30-50 字之间**（不少于30字，不超过50字）
5. 每条新闻独立成句，信息点单一清晰
5. 聚焦：AI大模型发布、AI公司融资、AI研究突破、AI产品发布、AI应用落地等

✅ 推荐示例：
OpenAI发布全新GPT系列模型，推理能力实现重大突破
英伟达推出新一代AI芯片，算力大幅提升
Anthropic完成新一轮融资，加速大模型研发

请直接输出 {count} 条新闻标题：""",

        "科技动态": """请生成今天可能发生的科技领域（非AI）新闻标题。

⚠️ 重要约束：
1. 所有标题必须是近期可能发生的事件
2. 聚焦产品发布、公司动态等确定性事件
3. 避免使用可能过时的销量、市占率等数据

内容要求：
1. 生成 {count} 条新闻标题
2. 每条标题有具体公司名、产品名或事件
3. 格式：每行一个标题，不要序号
4. **严格控制在 30-50 字之间**（不少于30字，不超过50字）
5. 每条新闻独立成句，信息点单一清晰
5. 聚焦：手机、电脑、新能源车、互联网产品、硬件发布、科技公司动态、游戏、航天等

✅ 推荐示例：
特斯拉正式发布Model 3改款车型，续航能力进一步提升
苹果推出新一代MacBook Air，搭载最新芯片
小米发布全新旗舰手机，影像系统全面升级

请直接输出 {count} 条新闻标题：""",

        "财经要闻": """请生成今天可能发生的财经领域新闻标题。

⚠️ 重要约束（严格执行）：
1. 所有标题必须是近期可能发生的事件
2. **严禁使用具体价格数据**（如股价、金价、汇率、油价等数字）
3. **严禁使用具体涨跌幅度数字**（如"涨10%"、"跌200点"）
4. 如涉及市场波动，使用"上涨"、"下跌"、"波动"、"震荡"等趋势词
5. 聚焦公司动态、财报发布、政策发布、并购等非价格类事件

内容要求：
1. 生成 {count} 条新闻标题
2. 每条标题有具体公司名、事件或政策
3. 格式：每行一个标题，不要序号
4. **严格控制在 30-50 字之间**（不少于30字，不超过50字）
5. 每条新闻独立成句，信息点单一清晰
5. 聚焦：财报、融资、并购、货币政策、监管政策等

✅ 推荐示例：
宁德时代发布年度财报，全年业绩超市场预期
某互联网巨头完成对新兴公司全资收购
央行宣布新一轮货币政策调整，市场反应积极

❌ 严禁示例：
黄金价格突破2800美元每盎司（具体价格数据）
比特币涨至50000美元关口（具体价格）
美股纳指大跌500点（具体涨跌幅）
人民币汇率跌破7.2（具体汇率数据）

请直接输出 {count} 条新闻标题："""
    }

    prompt = category_prompts.get(category, category_prompts["科技动态"]).format(count=count)

    result = call_llm_api(prompt, max_tokens=800)
    if not result:
        log(f"AI 生成 {category} 补充新闻失败")
        return []

    # 解析标题
    titles = [line.strip() for line in result.strip().split('\n') if line.strip()]
    titles = [re.sub(r'^\d+[.、]\s*', '', title).strip() for title in titles]

    # 转换为新闻格式
    news_items = []
    source_map = {
        "AI领域": "AI补充生成",
        "科技动态": "科技补充生成",
        "财经要闻": "财经补充生成"
    }
    source = source_map.get(category, "科技补充生成")

    for title in titles[:count]:
        if len(title) < 8:
            continue

        news_items.append({
            "title": title,
            "summary": "",
            "link": "",
            "published": today.strftime("%a, %d %b %Y %H:%M:%S +0800"),
            "source": source,
            "parsed_time": today.strftime("%Y-%m-%d %H:%M:%S"),
            "rss_source": source
        })

    log(f"为 {category} 补充生成 {len(news_items)} 条新闻")
    return news_items

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

分类标准（严格区分，不得交叉）：
- **AI 领域**: 仅限人工智能核心技术 - 大模型、LLM、机器学习、深度学习、NLP、CV、AI训练/推理、AI芯片、AI应用（注意：必须是真正使用AI技术的产品/服务）、AI研究论文、OpenAI、Google DeepMind、Anthropic、Meta AI、xAI等AI公司动态等。**汽车电动化/自动驾驶如果与AI无关则归入科技动态**
- **科技动态**: 非AI的科技内容 - 智能手机、电脑硬件、通用芯片、互联网产品、软件工程、游戏、新能源车（注意：汽车行业新闻如果与AI无关）、航天、5G/6G、物联网、创业公司、产品发布、科技企业动态等。**不包括任何AI相关内容**
- **财经要闻**: 金融经济类 - 股市、基金、债券、经济政策、货币政策、融资、并购、IPO、金融监管、宏观经济、企业财报、行业投资、**石油、天然气、能源、大宗商品**等。**特别注意：石油增产、能源价格、产油国等绝对不能归入AI领域或科技动态**

重要排除规则：
1. **石油、能源、大宗商品、货币政策、经济数据**等财经新闻，**必须归入财经要闻**，即使标题中出现了"AI"或"科技"也不改变分类
2. 标题中出现的公司/产品名不改变其本质分类，例如"某石油公司发布AI产品"应归入财经要闻（因为本质是石油公司新闻）
3. 春节红包、春晚、节假日促销等泛流量内容，如果没有AI/科技/财经核心内容，应该排除

请按以下 JSON 格式输出（只输出 JSON，不要其他文字）：
{{
  "AI 领域": [1, 3, 5, 7, 9],
  "科技动态": [2, 4, 6, 8, 10],
  "财经要闻": [11, 12, 13, 14, 15]
}}

注意：
1. **严格区分AI领域和科技动态**，AI相关必须归入AI领域，非AI科技归入科技动态，不得混淆或交叉
2. **财经要闻必须包含真正的财经/金融/经济新闻**，石油、能源、大宗商品等必须归入财经
3. 每个类别选择最重要的 5 条，如果某个类别新闻不足5条，可以少于5条
4. 输出纯 JSON 格式"""

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

def normalize_titles(categorized: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """使用 AI 规范化标题长度，确保排版整齐

    Args:
        categorized: 分类后的新闻字典

    Returns:
        标题规范化后的新闻字典
    """
    log("正在规范化标题长度...")

    # 收集所有标题
    all_titles = []
    title_mapping = {}  # 用于映射原标题到新标题

    for category, items in categorized.items():
        for item in items:
            original_title = item.get('title', '')
            all_titles.append(original_title)

    if not all_titles:
        return categorized

    # 构建标题优化 prompt
    titles_text = ""
    for i, title in enumerate(all_titles, 1):
        titles_text += f"{i}. {title}\n"

    prompt = f"""你是一位专业新闻编辑。请将以下新闻标题改写为长度一致、内容丰富饱满的标题。

原始标题：
{titles_text}

要求：
1. **严格控制字数**：每个标题必须在 35-50 字之间（含标点符号）
2. **合理使用标点**：使用逗号、顿号等标点符号分隔信息，符合中文新闻标题规范
3. **内容丰富饱满**：包含核心事件、关键细节、背景信息、影响或意义
4. **信息完整**：回答"谁做了什么""为什么重要""产生什么影响"
5. **语言简洁有力**：信息量大但不冗长，使用精准的专业术语
6. **风格统一**：保持新闻报道的专业性，突出亮点和价值
7. **顺序对应**：按原顺序输出，每行一个标题

**严格禁止**：
- **禁止使用"早报"、"派早报"、"今日早报"、"本周动态"、"X条动态"等多消息合并形式**
- **每个标题只能描述一个单一事件**，如果原标题包含多个事件，必须选择其中最重要的一个事件重写
- 禁止将不同新闻的内容混合到一个标题中
- 禁止添加原标题中没有的信息
- 禁止使用"本文"、"本文梳理"等无意义开头
- 禁止使用"一文带你"、"一张图看懂"等引导性短语作为标题开头
- 标题必须描述一个具体的事件或动态，不能是泛泛而谈

示例：
原标题：除夕迎「源神」？Qwen3.5以小胜大，捅破性价比天花板，大模型竞赛下半场开始了
优化后：阿里通义千问发布Qwen3.5大模型，以小规模参数实现性能突破，打破性价比天花板，标志国产大模型竞赛进入下半场（50字）

请直接输出优化后的标题列表，每行一个，不要序号和其他文字："""

    result = call_llm_api(prompt, max_tokens=1000)
    if not result:
        log("标题规范化失败，使用原标题")
        return categorized

    # 解析优化后的标题
    optimized_titles = [line.strip() for line in result.strip().split('\n') if line.strip()]

    # 去掉可能的序号
    cleaned_titles = []
    invalid_count = 0
    for title in optimized_titles:
        # 移除可能的序号格式：1. 或 1、
        title = re.sub(r'^\d+[.、]\s*', '', title)
        title = title.strip()

        # 安全检查：验证标题是否有效
        if not is_valid_news_title(title):
            log(f"  警告：AI生成的标题无效，已过滤: {title[:30]}...")
            invalid_count += 1
            continue

        cleaned_titles.append(title)

    # 如果有无效标题，只使用有效的
    if invalid_count > 0:
        log(f"已过滤 {invalid_count} 条AI生成的无效标题")

    # 更新标题
    if len(cleaned_titles) >= len(all_titles):
        title_index = 0
        for category, items in categorized.items():
            for item in items:
                if title_index < len(cleaned_titles):
                    old_title = item.get('title', '')
                    new_title = cleaned_titles[title_index]
                    # 只有当新标题有效时才更新
                    if is_valid_news_title(new_title):
                        item['title'] = new_title
                        log(f"  标题优化: {len(old_title)}字 → {len(new_title)}字")
                    title_index += 1
        log("标题规范化完成")
    else:
        log(f"有效标题数量不足（原{len(all_titles)}条，有效{len(cleaned_titles)}条），使用原标题")

    return categorized

def call_llm_api(prompt, max_tokens=2000):
    """调用 LLM API（仅使用豆包）"""
    return call_doubao_api(prompt, max_tokens)

def call_doubao_api(prompt, max_tokens=2000, retries=2):
    """调用豆包 API 生成内容（带重试机制）"""
    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

    headers = {
        "Authorization": f"Bearer {DOUBAO_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "doubao-seed-2-0-lite-260215",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7
    }

    for attempt in range(retries + 1):
        try:
            if attempt > 0:
                log(f"豆包 API 重试第 {attempt} 次...")
                time.sleep(2)  # 等待2秒后重试
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt == retries:
                log(f"豆包 API 调用失败（已重试 {retries} 次）: {e}")
                return None
            else:
                log(f"豆包 API 调用失败（第 {attempt + 1} 次尝试）: {e}")

def format_news_to_html(categorized: Dict[str, List[Dict]], yesterday_str: str, lunar_date: str = "", weekday: str = "") -> str:
    """将分类后的新闻格式化为 HTML（使用 inline style，兼容微信公众号）"""

    # 定义分类颜色、渐变和emoji
    category_colors = {
        "AI领域": "#4a90e2",
        "科技动态": "#e91e63",
        "财经要闻": "#ff9800"
    }

    category_gradients = {
        "AI领域": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
        "科技动态": "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)",
        "财经要闻": "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)"
    }

    category_emojis = {
        "AI领域": "🤖",
        "科技动态": "📱",
        "财经要闻": "💰"
    }

    # 生成新闻HTML片段
    news_html = ""
    for category, items in categorized.items():
        if not items:
            continue

        color = category_colors.get(category, "#666")
        gradient = category_gradients.get(category, f"linear-gradient(135deg, {color} 0%, {color} 100%)")
        emoji = category_emojis.get(category, "")

        # 使用 section 标签，添加白色圆角背景卡片
        news_html += f'<section style="margin-bottom: 25px; background: #fff; border-radius: 15px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.08);">\n'
        news_html += f'<p style="display: inline-block; background: {gradient}; color: #fff; font-size: 18px; font-weight: bold; padding: 10px 25px; border-radius: 25px; margin: 0 0 20px 0; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);">{emoji} {category}</p>\n'
        news_html += '<div style="padding: 0 10px;">\n'

        for i, item in enumerate(items, 1):
            title = item.get('title', '无标题')
            # 确保标题以句号结尾
            if not title.endswith(('。', '！', '？', '…')):
                title = title + '。'
            # 最后一条新闻的 margin-bottom 为 0
            margin_style = "margin: 0 0 15px 0" if i < len(items) else "margin: 0 0 0 0"
            # 编号右边加一个小竖线装饰
            news_html += f'  <p style="{margin_style}; line-height: 2; color: #333; font-size: 15px;"><span style="color: {color}; font-weight: bold; margin-right: 10px; padding-right: 10px; border-right: 3px solid {color};">{i:02d}</span>{title}</p>\n'

        news_html += '</div>\n'
        news_html += '</section>\n\n'

    # 使用 AI 生成微语（简短总结）
    news_texts = []
    for category, items in categorized.items():
        for item in items:
            news_texts.append(f"【{category}】{item.get('title', '')}")

    microword_prompt = f"""根据以下新闻标题，写一句与今日科技动态相关的深度金句。

新闻标题:
{chr(10).join(news_texts[:10])}

要求:
1. 25-40字，有节奏感，富有哲理和思考深度
2. 不要总结新闻内容，而是从新闻背后提炼出深层洞察或启示
3. 与科技、AI、创新、商业趋势相关，要有时代感
4. 语气深沉有力，像一句让人深思的格言或警句
5. 必须包含标点符号（逗号、句号或感叹号），句式可以是转折、递进或对比
6. 只输出金句本身，不要任何前缀说明

风格示例（参考，不要照抄）：
- 科技的边界每天都在后退，而真正的壁垒，始终是人的认知与格局。
- 当所有人都在追逐下一个风口，最稳的赢家，往往是那个定义了规则的人。
- AI 不会取代人，但懂得用 AI 的人，终将重塑每一个行业的生存法则。
- 每一次技术革命的背后，都是旧秩序的终结与新信仰的重建。
- 时代抛弃你时，连招呼都不会打"""

    microword = call_llm_api(microword_prompt, max_tokens=200)
    if not microword:
        microword = "科技的边界每天都在后退，而真正的壁垒，始终是人的认知与格局。"
    microword = microword.strip().strip('"\'')
    # 确保微语以标点符号结尾
    if not microword.endswith(('。', '！', '？', '…', '，')):
        microword = microword + '。'

    # 使用 AI 生成智能摘要（用于微信公众号文章摘要）
    summary_prompt = f"""根据以下新闻标题，生成一句简短的文章摘要，用于微信公众号文章摘要。

新闻标题:
{chr(10).join(news_texts[:15])}

要求:
1. 25-35字，简洁有力，能吸引读者点击
2. 突出今日新闻的核心关键词（如品牌名、产品名、技术名称）
3. 语言要有节奏感，可以用逗号分隔关键点
4. 风格示例（参考格式，不要照抄）：
   - 通义千问Qwen3.5发布，字节Seed 2.0登顶榜单，央视春晚机器人惊艳亮相。
   - DeepSeek震撼发布，OpenAI人事变动，港股市场迎来新机遇。
   - GPT-5传闻不断，特斯拉FSD重大更新，字节跳动大额套现。
5. 只输出摘要本身，不要任何前缀说明
6. 确保以标点符号结尾（句号、感叹号或问号）"""

    summary = call_llm_api(summary_prompt, max_tokens=150)
    if not summary:
        summary = "AI、科技、财经领域今日重要动态。"
    summary = summary.strip().strip('"\'')
    # 确保摘要以标点符号结尾
    if not summary.endswith(('。', '！', '？', '…')):
        summary = summary + '。'

    # 构建日期卡片内容（三行格式）
    date_card_lines = []
    if lunar_date:
        date_card_lines.append(f'<div style="font-size: 13px; margin-bottom: 6px; color: rgba(255,255,255,0.85);">{lunar_date}</div>')
    if weekday:
        date_card_lines.append(f'<div style="font-size: 32px; margin-bottom: 6px; font-weight: bold; letter-spacing: 2px;">{weekday}</div>')
    date_card_lines.append(f'<div style="font-size: 16px; font-weight: 500; color: rgba(255,255,255,0.95);">{yesterday_str}</div>')

    date_card_html = '\n'.join(date_card_lines)

    # 全部使用 inline style + 渐变背景，避免微信过滤
    html_template = f"""<div style="max-width: 750px; width: 100%; margin: 0 auto; padding: 0 15px; font-family: 微软雅黑, sans-serif; background-color: #ffffff; color: #333; line-height: 1.8;">

<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px 0; text-align: center; border-radius: 10px; margin: 20px 0 30px; color: #ffffff; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);">
{date_card_html}
</div>

{news_html}
<p style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); padding: 20px; border-radius: 8px; color: #ffffff; font-size: 15px; line-height: 1.8; margin: 30px 0 20px; text-align: left; box-shadow: 0 4px 15px rgba(250, 112, 154, 0.3);">【今日微语】{microword}</p>

</div>"""

    return html_template, summary

def save_raw_news(news_items: List[Dict], categorized: Dict[str, List[Dict]], date_str: str, summary: str = ""):
    """保存原始新闻数据为 JSON"""
    raw_data = {
        "date": date_str,
        "total_news": len(news_items),
        "categorized_count": {cat: len(items) for cat, items in categorized.items()},
        "summary": summary,  # 添加智能摘要
        "all_news": news_items,
        "categorized_news": categorized
    }

    raw_file = os.path.join(WORK_DIR, f"raw_news_{date_str}.json")
    try:
        with open(raw_file, 'w', encoding='utf-8') as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=2)
        log(f"原始新闻已保存: {raw_file}")
    except Exception as e:
        log(f"保存原始新闻失败: {e}")

def main():
    """主函数"""
    log("=" * 50)
    log("RSS 新闻收集开始")

    # 计算日期（使用今天作为显示日期）
    today = datetime.now()
    today_display_str = today.strftime("%Y年%m月%d日")
    today_str = today.strftime("%Y%m%d")

    # 计算昨天日期（用于新闻收集时间范围）
    yesterday = today - timedelta(days=1)

    # 计算农历和星期（使用今天）
    lunar_date = get_traditional_lunar_date(today)
    weekday = get_weekday_name(today)

    # 1. 收集所有 RSS 新闻
    all_news = collect_all_news()

    # 1.5 如果 RSS 新闻不足 15 条，使用 AI 补充
    if len(all_news) < 15:
        supplement_news = generate_supplement_news(15 - len(all_news))
        all_news.extend(supplement_news)
        log(f"补充后共 {len(all_news)} 条新闻")

    # 2. 使用 AI 分类
    categorized_news = classify_news_with_ai(all_news)

    # 2.4 规范化分类键名称（统一使用无空格的版本）
    normalized_categorized = {}
    category_mapping = {
        "AI 领域": "AI领域",
        "AI领域": "AI领域",
        "科技动态": "科技动态",
        "财经要闻": "财经要闻",
    }

    for old_key, news_list in categorized_news.items():
        new_key = category_mapping.get(old_key, old_key)
        if new_key in normalized_categorized:
            # 如果已存在，合并列表
            normalized_categorized[new_key].extend(news_list)
        else:
            normalized_categorized[new_key] = news_list
    categorized_news = normalized_categorized
    log(f"分类规范化后: {list(categorized_news.keys())}")

    # 2.5 检查每个类别是否达到 5 条，不足则补充
    target_count = 5
    categories = ["AI领域", "科技动态", "财经要闻"]

    for category in categories:
        current_count = len(categorized_news.get(category, []))
        if current_count < target_count:
            need_count = target_count - current_count
            log(f"{category} 当前 {current_count} 条，需要补充 {need_count} 条")
            supplement = generate_category_supplement_news(category, need_count)
            if supplement:
                # 将补充的新闻添加到对应类别
                if category not in categorized_news:
                    categorized_news[category] = []
                categorized_news[category].extend(supplement)
                # 同时添加到 all_news 以便后续保存
                all_news.extend(supplement)
                log(f"{category} 补充后共 {len(categorized_news[category])} 条")

    # 2.55 最终分类清理：确保只有3个标准分类
    final_categories = ["AI领域", "科技动态", "财经要闻"]
    cleaned_categorized = {}
    for cat in final_categories:
        if cat in categorized_news:
            cleaned_categorized[cat] = categorized_news[cat]
        # 也检查带空格版本
        elif "AI 领域" in cat:
            cleaned_categorized["AI领域"] = categorized_news.get("AI 领域", [])
    categorized_news = cleaned_categorized
    log(f"最终分类: {list(categorized_news.keys())}")

    # 2.6 规范化标题长度
    categorized_news = normalize_titles(categorized_news)

    # 3. 格式化为 HTML（同时生成智能摘要）
    log("正在格式化新闻...")
    html_content, summary = format_news_to_html(categorized_news, today_display_str, lunar_date, weekday)

    if not html_content:
        log("格式化失败")
        return None, None

    log(f"智能摘要: {summary}")

    # 保存原始数据（包含摘要）
    save_raw_news(all_news, categorized_news, today_str, summary)

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

    return html_content, summary

if __name__ == "__main__":
    main()
