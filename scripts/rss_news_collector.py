#!/usr/bin/env python3
"""
基于 RSS 订阅的新闻收集脚本 V4.2.0
纯 RSS 模式，48 个源，24h 时间窗口，100% 真实新闻

特性：
- 48 个 RSS 源（AI 13 + 国内科技 11 + 国际科技 12 + 财经 12）
- RSSHub 多实例 fallback 机制（财经源高可用）
- 并发 RSS 采集（10线程），采集时间从 7min 压缩到 ~30s
- 分类补救机制（不足 3 条时自动补充）
- 新闻正文简报：每条新闻附带1-2句40-60字简报
- 模糊去重：字符级 Jaccard 相似度（阈值 0.6）
- HTML 清洗增强：CDATA + unescape + content:encoded 解析
- 分类 JSON 解析正则 fallback
- 使用 certifi 正确验证 SSL 证书
- 纯 RSS 模式，不使用 AI 补充新闻
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
import html as html_module
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        "发布", "推出", "上线", "融资", "投资", "收购", "并购",
        "获得", "完成", "宣布", "召开", "举行", "成立", "上市",
        "产品", "服务", "公司", "企业", "机构", "平台",
        "技术", "研究", "开发", "实现", "突破", "创新",
        "市场", "行业", "领域", "全球", "中国", "美国", "欧洲",
        "AI", "大模型", "模型", "算法", "芯片", "GPU",
        "净利润", "营收", "财报", "利润", "销售额",
    ]

    has_news_element = any(elem in title for elem in news_elements)
    if not has_news_element:
        # 如果没有新闻要素，检查是否是事件类标题
        event_patterns = [
            r"\d+月\d+日",  # 日期
            r"\d+日",  # 某日
            r"北京", r"上海", r"深圳", r"广州", r"杭州",
            r"年度", r"季度", r"月份",
            r"首次", r"第一届", r"第二届",
        ]
        has_event = any(re.search(p, title) for p in event_patterns)
        if not has_event:
            return False

    return True

# 配置
DOUBAO_API_KEY = os.environ.get("DOUBAO_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
# 工作目录 - 兼容本地和 GitHub Actions
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.dirname(SCRIPT_DIR)
LOG_FILE = os.path.join(WORK_DIR, "logs", "rss-news.log")

# 检查 API Key（至少有一个即可）
if not DOUBAO_API_KEY and not GOOGLE_API_KEY:
    print("错误: 未设置 DOUBAO_API_KEY 或 GOOGLE_API_KEY 环境变量")
    sys.exit(1)

# RSSHub 镜像实例列表（用于 fallback）
RSSHUB_INSTANCES = [
    "https://rsshub.rssforever.com",
    "https://rsshub.pseudoyu.com",
    "https://rsshub.ktachibana.party",
]

# RSS 源配置（2026-03-08 优化：强化财经源，清理失效源）
# 每个源可以有 "fallback_urls" 列表，主URL失败时自动尝试备选
ALL_RSS_SOURCES = [
    # === AI 专项源（13个） ===
    {"name": "量子位", "url": "https://www.qbitai.com/feed", "limit": 12},
    {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss", "limit": 12},
    {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml", "limit": 8},
    {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml", "limit": 8},
    {"name": "AI News", "url": "https://www.artificialintelligence-news.com/feed/", "limit": 8},
    {"name": "Google DeepMind", "url": "https://deepmind.google/blog/rss.xml", "limit": 8},
    {"name": "Google Research", "url": "https://research.google/blog/rss", "limit": 8},
    {"name": "Microsoft Research", "url": "https://www.microsoft.com/en-us/research/blog/feed/", "limit": 8},
    {"name": "NVIDIA Blog", "url": "https://blogs.nvidia.com/feed/", "limit": 8},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "limit": 8},
    {"name": "MIT News AI", "url": "https://news.mit.edu/rss/topic/artificial-intelligence2", "limit": 8},
    {"name": "KDnuggets", "url": "https://www.kdnuggets.com/feed", "limit": 8},
    {"name": "Analytics Vidhya", "url": "https://www.analyticsvidhya.com/feed/", "limit": 8},
    # === 国内科技源（11个） ===
    {"name": "36氪", "url": "https://36kr.com/feed", "limit": 12},
    {"name": "虎嗅", "url": "https://www.huxiu.com/rss/0.xml", "limit": 10},
    {"name": "钛媒体", "url": "https://www.tmtpost.com/rss", "limit": 10},
    {"name": "爱范儿", "url": "https://www.ifanr.com/feed", "limit": 8},
    {"name": "少数派", "url": "https://sspai.com/feed", "limit": 8},
    {"name": "InfoQ", "url": "https://www.infoq.cn/feed", "limit": 8},
    {"name": "IT之家", "url": "https://www.ithome.com/rss/", "limit": 10},
    {"name": "雷峰网", "url": "https://www.leiphone.com/feed", "limit": 8},
    {"name": "动点科技", "url": "https://cn.technode.com/feed/", "limit": 8},
    {"name": "OSCHINA", "url": "https://www.oschina.net/news/rss", "limit": 8},
    {"name": "cnBeta", "url": "https://www.cnbeta.com.tw/backend.php", "limit": 10},
    # === 国际科技源（12个） ===
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "limit": 10},
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "limit": 10},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "limit": 8},
    {"name": "Wired", "url": "https://www.wired.com/feed/rss", "limit": 8},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "limit": 8},
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "limit": 8},
    {"name": "Engadget", "url": "https://www.engadget.com/rss.xml", "limit": 8},
    {"name": "ZDNet", "url": "https://www.zdnet.com/news/rss.xml", "limit": 8},
    {"name": "The Register", "url": "https://www.theregister.com/headlines.atom", "limit": 8},
    {"name": "9to5Mac", "url": "https://9to5mac.com/feed/", "limit": 8},
    {"name": "Android Authority", "url": "https://www.androidauthority.com/feed/", "limit": 8},
    {"name": "Hacker News Best", "url": "https://hnrss.org/best", "limit": 8},
    # === 财经源（15个，强化中文财经源 + RSSHub多实例fallback） ===
    # 中文财经源（通过 RSSHub 镜像，带 fallback）
    {"name": "财联社快讯", "url": "https://rsshub.rssforever.com/cls/telegraph", "limit": 15,
     "fallback_urls": ["https://rsshub.pseudoyu.com/cls/telegraph", "https://rsshub.ktachibana.party/cls/telegraph"]},
    {"name": "财新网", "url": "https://rsshub.pseudoyu.com/caixin/latest", "limit": 15,
     "fallback_urls": ["https://rsshub.rssforever.com/caixin/latest", "https://rsshub.ktachibana.party/caixin/latest"]},
    {"name": "金十数据", "url": "https://rsshub.rssforever.com/jin10/flash", "limit": 10,
     "fallback_urls": ["https://rsshub.pseudoyu.com/jin10/flash", "https://rsshub.ktachibana.party/jin10/flash"]},
    # 直连财经源
    {"name": "华尔街见闻", "url": "https://dedicated.wallstreetcn.com/rss.xml", "limit": 12},
    {"name": "Bloomberg Markets", "url": "https://feeds.bloomberg.com/markets/news.rss", "limit": 10},
    {"name": "CNBC", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html", "limit": 8},
    {"name": "MarketWatch", "url": "https://feeds.marketwatch.com/marketwatch/topstories/", "limit": 8},
    {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex", "limit": 8},
    {"name": "Seeking Alpha", "url": "https://seekingalpha.com/feed.xml", "limit": 8},
    {"name": "Forbes Business", "url": "https://www.forbes.com/business/feed2", "limit": 8},
    {"name": "Business Insider", "url": "https://feeds.businessinsider.com/custom/all", "limit": 8},
    {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "limit": 8},
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

def clean_html_content(raw_text):
    """清洗 HTML 内容：移除 CDATA、HTML标签、转义字符、多余空白"""
    if not raw_text:
        return ''
    text = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', raw_text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    text = html_module.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def is_similar_title(t1, t2, threshold=0.6):
    """字符级 Jaccard 相似度检查"""
    s1, s2 = set(t1), set(t2)
    return len(s1 & s2) / len(s1 | s2) > threshold if s1 | s2 else False


def fetch_rss_items(url: str, limit: int = 10, hours_ago: int = 24) -> List[Dict]:
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

        # 尝试不同的 RSS/Atom 格式
        item_elements = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')

        # 精确的时间过滤：只收集过去24小时的新闻
        now = datetime.now().astimezone()  # 使用 aware datetime，避免时区比较错误
        hours_24_ago = now - timedelta(hours=24)  # 过去24小时

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

            # 描述/摘要（优先 content:encoded 获取更丰富正文）
            desc_text = ''
            for desc_path in ['{http://purl.org/rss/1.0/modules/content/}encoded', 'description', '{http://www.w3.org/2005/Atom}summary', 'content', '{http://www.w3.org/2005/Atom}content']:
                desc_elem = elem.find(desc_path)
                if desc_elem is not None and desc_elem.text:
                    desc_text = desc_elem.text
                    break
            desc_text = clean_html_content(desc_text)
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

            # 精确的时间检查：只收集过去24小时的新闻（严格模式）
            if not item['published']:
                # 没有发布时间的新闻，跳过以确保内容真实性
                continue

            try:
                pub_time = parsedate_to_datetime(item['published'])
                # 转换为本地时区（北京时间）进行比较
                pub_time_local = pub_time.astimezone()

                # 过去24小时时间检查
                if pub_time_local < hours_24_ago:
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

def fetch_source_with_fallback(source: Dict) -> tuple:
    """并发辅助函数：获取单个 RSS 源（含 fallback），返回 (source_name, items)"""
    items = fetch_rss_items(source['url'], source['limit'])

    # 如果主URL失败且有fallback，尝试备选URL
    if len(items) == 0 and 'fallback_urls' in source:
        for fallback_url in source['fallback_urls']:
            items = fetch_rss_items(fallback_url, source['limit'])
            if len(items) > 0:
                break

    for item in items:
        item['rss_source'] = source['name']

    return source['name'], items


def collect_all_news() -> List[Dict]:
    """收集所有 RSS 新闻（并发模式，10线程），支持 fallback URLs"""
    # 计算时间范围用于日志（过去24小时）
    now = datetime.now().astimezone()
    cutoff_time = now - timedelta(hours=24)

    log(f"开始收集 RSS 新闻（并发模式，{len(ALL_RSS_SOURCES)} 个源）...")
    log(f"时间过滤范围: 过去24小时 ({cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} - {now.strftime('%Y-%m-%d %H:%M:%S')})")

    all_items = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_source_with_fallback, source): source for source in ALL_RSS_SOURCES}
        for future in as_completed(futures):
            source_name, items = future.result()
            log(f"  - {source_name}: 获取 {len(items)} 条")
            all_items.extend(items)

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
            # 模糊去重：检查与已有标题的字符级 Jaccard 相似度
            is_duplicate = any(is_similar_title(title_lower, existing) for existing in seen_titles)
            if is_duplicate:
                log(f"  模糊去重过滤: {title[:30]}...")
                continue
            seen_titles.add(title_lower)
            unique_items.append(item)

    if invalid_count > 0:
        log(f"已过滤 {invalid_count} 条无效标题")

    log(f"收集完成，共获取 {len(unique_items)} 条去重后新闻")
    return unique_items


def classify_news_with_ai(news_items: List[Dict]) -> Dict[str, List[Dict]]:
    """使用 AI 将新闻分类到 3 个类别"""
    log("正在使用 AI 分类新闻...")

    # 准备新闻列表（最多40条，确保各分类有足够候选）
    news_list = news_items[:40]

    # 构建分类 prompt
    news_text = ""
    for i, item in enumerate(news_list, 1):
        news_text += f"{i}. 标题: {item['title']}\n"
        if item['summary']:
            news_text += f"   摘要: {item['summary'][:200]}\n"
        news_text += f"   来源: {item['rss_source']}\n\n"

    prompt = f"""你是专业新闻编辑，负责筛选和分类今日科技财经新闻。请从以下新闻中，为每个类别各选出5条最重要的新闻。

{news_text}

【三大类别定义——严格区分，不得交叉】

**AI 领域**（仅限AI核心技术与应用）：
- 大模型/LLM发布与评测、AI训练推理技术、AI芯片（专用）
- OpenAI/Google DeepMind/Anthropic/Meta AI/xAI/百度/阿里/字节AI部门等AI公司动态
- AI产品发布（必须是真正基于AI技术的产品）、AI研究论文与学术成果
- ❌ 排除：普通互联网产品、手机、游戏、医学研究（即使用了AI也要看核心是否是AI进展）

**科技动态**（非AI的科技内容）：
- 智能手机/电脑/平板硬件、消费电子新品发布
- 互联网产品（社交/搜索/电商平台功能更新）、游戏、软件工程
- 航天探索、量子计算、5G/6G、半导体通用芯片（非AI专用）
- 科技公司企业动态（产品层面而非财务层面）
- ❌ 排除：生物医学研究、心理学、社会学研究、养老/医疗行业新闻

**财经要闻**（金融经济类）：
- 股市行情、A股港股美股动态、基金、债券
- 企业融资/IPO/并购/收购、营收财报、估值市值
- 宏观经济政策、央行/美联储货币政策、汇率
- 大宗商品（石油/黄金/铜等）、加密货币行情
- ❌ 排除：产品发布（应归入对应科技/AI类）

【去重规则——重要！】
如果多条新闻报道同一事件（同一公司的同一融资/同一产品/同一政策），只选其中最重要的1条，不重复选择同一事件的不同角度报道。

【选择优先级】
优先选择：知名公司/大额融资/重大政策/行业重磅消息
降低优先级：学术小组研究、行业综述、分析师评论（如果没有更好的选择才用）

请按以下 JSON 格式输出（只输出 JSON，不要其他文字）：
{{
  "AI 领域": [1, 3, 5, 7, 9],
  "科技动态": [2, 4, 6, 8, 10],
  "财经要闻": [11, 12, 13, 14, 15]
}}

注意：每个类别各选5条（不足时少选），同一事件只选1条，严禁重复。"""

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
        log(f"解析 AI 分类结果失败: {e}，尝试正则 fallback...")
        # 正则 fallback：提取 JSON 对象
        json_match = re.search(r'\{[^{}]*\}', result, re.DOTALL)
        if json_match:
            try:
                classification = json.loads(json_match.group())
                categorized = {cat: [] for cat in CATEGORIES}
                for category, indices in classification.items():
                    if category in CATEGORIES:
                        for idx in indices[:5]:
                            if idx - 1 < len(news_list):
                                categorized[category].append(news_list[idx - 1])
                log(f"正则 fallback 成功: AI领域{len(categorized['AI 领域'])}条, 科技动态{len(categorized['科技动态'])}条, 财经要闻{len(categorized['财经要闻'])}条")
                return categorized
            except Exception:
                pass
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

    prompt = f"""你是专业中文新闻编辑，将以下新闻标题改写为30-42字的**中文**新闻简讯。

原始标题：
{titles_text}

【铁律——违反任何一条即为失败】

**1. 所有输出必须是中文**
- 英文标题必须完整翻译为中文，禁止输出英文句子
- 仅允许保留品牌名/产品名的英文原文（如OpenAI、iPhone、Tesla、GPT-4）
- 除品牌名外，标题中不允许出现任何英文单词

**2. 主语必须具体，禁止泛化**
- ✅ 必须保留原标题中的真实主体：公司名、人名、机构名、产品名
  例：OpenAI、苹果、特斯拉、谷歌、华为、MIT、斯坦福大学、DeepSeek
- ❌ 严禁用以下泛化词替换具体名称：
  "科研团队"、"研发团队"、"行业机构"、"消息人士"、"第三方机构"、"分析机构"、"业内人士"
- 原标题本身就没有具体名称时（如匿名来源），才允许用"研究人员"、"分析人士"

**3. 字数：严格30-42字（含标点），少于30字视为不合格，每条描述单一事件**

**4. 格式：主体+动作+结果，以句号或逗号结尾**

示例改写：
原: MIT develops heart failure AI model predicting one-year patient deterioration
改: MIT研究人员开发心力衰竭预后AI模型，可预测患者一年内病情恶化，精准度超过现有临床标准。

原: Nvidia Omniverse platform accelerates industrial AI design workflows
改: 英伟达Omniverse平台发布工业AI设计套件，整合数字孪生技术，大幅提升制造业多环节协作效率。

原: Apple cuts App Store commission rates in China
改: 苹果宣布下调中国区App Store佣金费率，降幅约X%，利好国内中小开发者降低运营成本。

按原顺序每行输出一个改写后的标题，不要序号："""

    result = call_llm_api(prompt, max_tokens=1500)
    if not result:
        log("标题规范化失败，使用原标题")
        return categorized

    # 解析优化后的标题
    optimized_titles = [line.strip() for line in result.strip().split('\n') if line.strip()]

    # 去掉可能的序号
    cleaned_titles = []
    for title in optimized_titles:
        # 移除可能的序号格式：1. 或 1、
        title = re.sub(r'^\d+[.、]\s*', '', title)
        title = title.strip()
        cleaned_titles.append(title)

    # 逐条替换：每条标题独立验证，无效的保留原标题
    title_index = 0
    updated_count = 0
    kept_count = 0
    for category, items in categorized.items():
        for item in items:
            old_title = item.get('title', '')

            if title_index < len(cleaned_titles):
                new_title = cleaned_titles[title_index]
                title_index += 1

                # 验证新标题质量
                chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', new_title))
                english_words = len(re.findall(r'[a-zA-Z]{4,}', new_title))
                is_mostly_english = english_words > 5

                if not is_valid_news_title(new_title):
                    log(f"  保留原标题（AI生成无效）: {new_title[:30]}...")
                    kept_count += 1
                elif chinese_chars < 15:
                    log(f"  保留原标题（中文字数不足{chinese_chars}字）: {new_title[:30]}...")
                    kept_count += 1
                elif is_mostly_english:
                    log(f"  保留原标题（含过多英文）: {new_title[:30]}...")
                    kept_count += 1
                else:
                    item['title'] = new_title
                    log(f"  标题优化: {len(old_title)}字 → {len(new_title)}字")
                    updated_count += 1
            else:
                kept_count += 1

    log(f"标题规范化完成: 更新{updated_count}条，保留原标题{kept_count}条")
    return categorized

def generate_news_briefs(categorized: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """使用 AI 为每条入选新闻生成1-2句简报"""
    log("正在生成新闻简报...")

    # 收集所有入选新闻的 title + summary + source
    news_items_for_brief = []
    for category, items in categorized.items():
        for item in items:
            news_items_for_brief.append(item)

    if not news_items_for_brief:
        return categorized

    # 构建 prompt
    brief_text = ""
    for i, item in enumerate(news_items_for_brief, 1):
        title = item.get('title', '')
        summary = item.get('summary', '')[:200]
        source = item.get('rss_source', '')
        brief_text += f"{i}. 标题: {title}\n"
        if summary:
            brief_text += f"   摘要: {summary}\n"
        brief_text += f"   来源: {source}\n\n"

    prompt = f"""你是专业新闻编辑，为以下新闻各写1-2句简报（40-60字），补充标题未涵盖的关键信息。

{brief_text}

【要求】
1. 每条简报40-60字，语法完整，信息量大
2. 遵循新闻写作规范：Who（谁）、What（做了什么）、When/Where（时间/地点，如有）
3. 补充标题中没有的信息（如具体数据、影响范围、技术细节）
4. 如果摘要信息不足，基于标题合理推断，不要编造具体数字
5. 中文输出，品牌名可保留英文
6. 按原顺序每行输出一条简报，不要序号

示例：
该模型在多项基准测试中超越GPT-4o，推理速度提升40%，已面向企业用户开放API接口。"""

    result = call_llm_api(prompt, max_tokens=1500)
    if not result:
        log("简报生成失败，brief 留空")
        return categorized

    # 解析简报
    briefs = [line.strip() for line in result.strip().split('\n') if line.strip()]
    # 去掉可能的序号
    cleaned_briefs = []
    for brief in briefs:
        brief = re.sub(r'^\d+[.、]\s*', '', brief).strip()
        if brief:
            cleaned_briefs.append(brief)

    # 填入 item['brief']
    idx = 0
    for category, items in categorized.items():
        for item in items:
            if idx < len(cleaned_briefs):
                item['brief'] = cleaned_briefs[idx]
                idx += 1
            else:
                item['brief'] = ''

    log(f"简报生成完成: {idx}/{len(news_items_for_brief)} 条")
    return categorized

def call_gemini_api(prompt, max_tokens=2000):
    """调用 Google Gemini API（主力）"""
    if not GOOGLE_API_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.3,
        }
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        log(f"Gemini API 调用失败: {e}")
        return None


def call_doubao_api(prompt, max_tokens=2000, retries=1):
    """调用豆包 API 生成内容（兜底）"""
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
    for attempt in range(retries + 1):
        try:
            if attempt > 0:
                log(f"豆包 API 重试第 {attempt} 次...")
                time.sleep(2)
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt == retries:
                log(f"豆包 API 调用失败（已重试 {retries} 次）: {e}")
                return None
            log(f"豆包 API 调用失败（第 {attempt + 1} 次尝试）: {e}")


def call_llm_api(prompt, max_tokens=2000):
    """调用 LLM API：Gemini 主力，豆包兜底"""
    result = call_gemini_api(prompt, max_tokens)
    if result:
        return result
    log("Gemini 失败，尝试豆包兜底...")
    return call_doubao_api(prompt, max_tokens)

def format_news_to_html(categorized: Dict[str, List[Dict]], yesterday_str: str, lunar_date: str = "", weekday: str = "") -> str:
    """将分类后的新闻格式化为 HTML（使用 inline style，兼容微信公众号）"""

    # 定义分类颜色、渐变和emoji
    category_colors = {
        "AI领域": "#4a90e2",
        "科技动态": "#e91e63",
        "财经要闻": "#ff9800"
    }

    category_gradients = {
        "AI领域": "linear-gradient(135deg, #4A6CF7 0%, #8B5CF6 100%)",
        "科技动态": "linear-gradient(135deg, #ec4899 0%, #f43f5e 100%)",
        "财经要闻": "linear-gradient(135deg, #f59e0b 0%, #ea580c 100%)"
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
            # 序号使用圆形背景 + 白色数字（跟随板块颜色）
            news_html += f'  <p style="{margin_style}; line-height: 2; color: #333; font-size: 15px;"><span style="display: inline-block; min-width: 24px; height: 24px; background: {color}; color: #fff; font-weight: bold; font-size: 13px; text-align: center; line-height: 24px; border-radius: 50%; margin-right: 12px;">{i:02d}</span>{title}</p>\n'
            # 简报正文（如有）
            brief = item.get('brief', '')
            if brief:
                if not brief.endswith(('。', '！', '？', '…')):
                    brief = brief + '。'
                brief_margin = "margin: -10px 0 15px 0" if i < len(items) else "margin: -10px 0 0 0"
                news_html += f'  <p style="{brief_margin}; padding-left: 36px; line-height: 1.8; color: #888; font-size: 13px;">{brief}</p>\n'

        news_html += '</div>\n'
        news_html += '</section>\n\n'

    # 使用 AI 生成微语（简短总结）
    news_texts = []
    for category, items in categorized.items():
        for item in items:
            news_texts.append(f"【{category}】{item.get('title', '')}")

    microword_prompt = f"""根据以下新闻标题，写一句今日科技感言。

新闻标题:
{chr(10).join(news_texts[:10])}

要求:
1. 25-40字，句子语法完整，语义通顺，不能出现乱码或残句
2. 从这批新闻背后提炼出一个深层洞察，不要直接复述新闻内容
3. 与AI/科技/商业趋势相关，有时代感，有哲理
4. 使用标点符号（逗号、句号），句式清晰
5. 只输出感言本身，不要任何前缀或说明

风格参考（不要照抄）：
- 科技的边界每天都在后退，真正的壁垒始终是人的认知与格局。
- 当所有人都在追逐风口，定义规则的人往往已悄悄赢得下一局。
- AI不会取代人，但懂得用AI的人，终将重塑每个行业的生存法则。"""

    microword = call_llm_api(microword_prompt, max_tokens=300)
    default_microword = "科技的边界每天都在后退，而真正的壁垒，始终是人的认知与格局。"
    if not microword:
        microword = default_microword
    microword = microword.strip().strip('"\'')
    # 截断检测：如果微语太短或不以标点结尾，可能被截断，使用默认值
    if len(microword) < 15 or (not microword.endswith(('。', '！', '？', '…')) and len(microword) > 45):
        log(f"  微语可能被截断或格式异常（{len(microword)}字），使用默认值")
        microword = default_microword
    # 确保微语以标点符号结尾
    if not microword.endswith(('。', '！', '？', '…')):
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

    # 计算农历和星期（使用今天）
    lunar_date = get_traditional_lunar_date(today)
    weekday = get_weekday_name(today)

    # 1. 收集所有 RSS 新闻
    all_news = collect_all_news()

    # 1.5 RSS 新闻数量检查（不使用 AI 补充，确保内容全部来自真实 RSS 源）
    if len(all_news) == 0:
        log("❌ RSS 收集结果为 0 条，所有源均无法获取新闻，任务终止")
        log("请检查网络连接、SSL 证书或 RSS 源可用性")
        sys.exit(1)

    log(f"✅ 共获取 {len(all_news)} 条真实 RSS 新闻，进入分类流程")

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

    # 2.5 记录各类别实际数量，不足5条时尝试补救
    categories = ["AI领域", "科技动态", "财经要闻"]
    for category in categories:
        count = len(categorized_news.get(category, []))
        log(f"{category}: {count} 条真实新闻")

    # 2.51 补救机制：如果任何分类不足3条，用剩余未分类新闻再次请求AI分类补充
    min_count = min(len(categorized_news.get(cat, [])) for cat in categories)
    if min_count < 3:
        log(f"⚠️ 有分类不足3条，启动补救机制...")
        # 找出已使用的新闻标题
        used_titles = set()
        for cat_items in categorized_news.values():
            for item in cat_items:
                used_titles.add(item.get('title', '').lower())
        # 找出还没被分类的新闻
        unused_news = [n for n in all_news if n.get('title', '').lower() not in used_titles]
        if unused_news:
            log(f"  找到 {len(unused_news)} 条未使用新闻，重新分类补充...")
            supplement = classify_news_with_ai(unused_news)
            # 规范化补充分类的键名
            for old_key, news_list in supplement.items():
                new_key = category_mapping.get(old_key, old_key)
                if new_key in categories:
                    current = categorized_news.get(new_key, [])
                    needed = 5 - len(current)
                    if needed > 0:
                        categorized_news[new_key] = current + news_list[:needed]
                        log(f"  {new_key}: 补充 {min(needed, len(news_list))} 条")
        else:
            log(f"  没有未使用的新闻可供补充")

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

    # 2.7 生成新闻简报
    categorized_news = generate_news_briefs(categorized_news)

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
