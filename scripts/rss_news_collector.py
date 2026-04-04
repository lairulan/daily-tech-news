#!/usr/bin/env python3
"""
基于 RSS 订阅的新闻收集脚本 V4.3.1
纯 RSS 模式，48 个源，24h 时间窗口，100% 真实新闻

特性：
- 48 个 RSS 源（AI 13 + 国内科技 11 + 国际科技 12 + 财经 12）
- RSSHub 多实例 fallback 机制（财经源高可用）
- 并发 RSS 采集（10线程），采集时间从 7min 压缩到 ~30s
- 分类补救机制（不足 3 条时自动补充）
- 单行新闻简讯：每条新闻只保留一行事实型简讯
- RSS 源健康摘要：记录空返回源与 fallback 命中情况
- 强过滤与主体纠偏：减少栏目标题、导航噪音和泛化主体
- 模糊去重：字符级 Jaccard 相似度（阈值 0.6）
- HTML 清洗增强：CDATA + unescape + content:encoded 解析
- 分类 JSON 解析正则 fallback
- 入选新闻原文上下文补充：补抓页面标题/导语，减少主体缺失
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
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}
ARTICLE_CONTEXT_CACHE: Dict[str, Dict[str, str]] = {}
LAST_RSS_HEALTH: List[Dict[str, str]] = []

GENERIC_SUBJECT_WORDS = {
    "项目", "模型", "平台", "系统", "产品", "事项", "计划", "团队", "机构", "公司",
    "企业", "组织", "方案", "应用", "服务", "工具", "赛道", "领域", "榜单",
    "开源项目", "开源模型", "开源OCR项目", "国产世界模型", "这类大模型", "该模型",
    "该项目", "该平台", "该系统", "这类模型", "这一项目", "这一模型",
    "OCR", "AI", "UI", "Pro", "Lite", "技术科技", "这家公司", "年入8亿",
    "版本", "恶意版本", "记者", "国行", "B轮融资", "A轮融资", "C轮融资",
}

GENERIC_SUBJECT_LOWER_WORDS = {
    "meta-learning", "agent", "agents", "assistant", "assistants",
    "copilot", "copilots", "wifi", "wi-fi",
}

SITE_NOISE_TOKENS = {
    "量子位", "QbitAI", "IT之家", "RuanMei.com", "少数派", "爱范儿", "雷峰网",
    "钛媒体", "OSCHINA", "Wired", "TechCrunch", "Engadget", "Ars Technica",
    "MarketWatch", "Forbes", "CNBC", "VentureBeat", "Yahoo Finance",
    "Win10", "Win11", "AI慕课学院", "极客购", "要知App", "软媒魔方", "IT圈",
}

HARD_EXCLUDE_KEYWORDS = [
    "派早报",
    "早报",
    "日报",
    "观察",
    "周观察",
    "征文",
    "指南",
    "评测",
    "一览表",
    "背后",
    "博弈",
    "盘点",
    "合集",
]

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

ACTION_VERBS = (
    "发布", "推出", "宣布", "上线", "曝光", "登顶", "完成", "开启", "停运", "停服",
    "停更", "停用", "停止运营", "冲刺", "上市", "开源", "收购", "并购", "融资",
    "更新", "升级", "亮相", "发布会", "发布了",
)

RESULT_KEYWORDS = (
    "领先", "超越", "霸榜", "稳居第一", "第一", "融资", "估值", "量产", "发布",
    "升级", "修复", "削减", "离职", "定档", "聆讯", "营收", "同比", "支持",
    "专享", "登顶", "开源", "亮相", "通过", "集体出走", "流向微软",
)

TIME_MARKER_PATTERNS = [
    r"\d{4}年\s*\d{1,2}月\s*\d{1,2}日",
    r"\d{4}年\s*\d{1,2}月",
    r"\d{4}年",
    r"\d{1,2}\s*月\s*\d{1,2}\s*日",
    r"\d{1,2}\s*月",
    r"Q[1-4]",
    r"第[一二三四]季度",
    r"上半年",
    r"下半年",
    r"今年",
    r"明年",
    r"后年",
    r"本月",
    r"下月",
    r"本周",
    r"下周",
    r"春季",
    r"夏季",
    r"秋季",
    r"冬季",
    r"年内",
    r"年底",
    r"月内",
    r"月底",
    r"上旬",
    r"中旬",
    r"下旬",
]

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


def count_chinese_chars(text: str) -> int:
    """统计文本中的中文字符数。"""
    return len(re.findall(r"[\u4e00-\u9fa5]", text or ""))


def extract_ascii_tokens(text: str) -> List[str]:
    """提取标题中的英文/数字混合词。"""
    return re.findall(r"[A-Za-z][A-Za-z0-9.+\-]*", text or "")


def has_non_news_style(title: str) -> bool:
    """判断标题是否带有评测、评论、提问或营销腔。"""
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
    """过滤英文占比过高或以泛英文概念起手的标题。"""
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

    if has_non_news_style(title):
        return False
    if has_excessive_english(title):
        return False

    # 强过滤：无论是否含科技关键词，这些类型都不适合新闻简讯
    for keyword in HARD_EXCLUDE_KEYWORDS:
        if keyword in title:
            return False

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
# 工作目录 - 兼容本地和 GitHub Actions
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.dirname(SCRIPT_DIR)
LOG_FILE = os.path.join(WORK_DIR, "logs", "rss-news.log")

# 检查 API Key
if not DOUBAO_API_KEY:
    print("错误: 未设置 DOUBAO_API_KEY 环境变量")
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
    {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss", "limit": 12},  # XML容错已处理
    {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml", "limit": 8},
    {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml", "limit": 8},
    {"name": "AI News", "url": "https://www.artificialintelligence-news.com/feed/", "limit": 8},
    {"name": "Google DeepMind", "url": "https://deepmind.google/blog/rss.xml", "limit": 8},
    {"name": "Google Research", "url": "https://research.google/blog/rss", "limit": 8},
    {"name": "AWS ML Blog", "url": "https://aws.amazon.com/blogs/machine-learning/feed/", "limit": 8},
    {"name": "NVIDIA Blog", "url": "https://blogs.nvidia.com/feed/", "limit": 8},
    {"name": "ZDNet AI", "url": "https://www.zdnet.com/topic/artificial-intelligence/rss.xml", "limit": 10},
    {"name": "MIT News AI", "url": "https://news.mit.edu/rss/topic/artificial-intelligence2", "limit": 8},
    {"name": "KDnuggets", "url": "https://www.kdnuggets.com/feed", "limit": 8},
    {"name": "IEEE Spectrum AI", "url": "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss", "limit": 8},
    # === 国内科技源（9个） ===
    {"name": "36氪", "url": "https://rsshub.rssforever.com/36kr/news/latest", "limit": 12,
     "fallback_urls": ["https://36kr.com/feed"]},
    {"name": "钛媒体", "url": "https://www.tmtpost.com/rss", "limit": 10},
    {"name": "爱范儿", "url": "https://www.ifanr.com/feed", "limit": 8},
    {"name": "少数派", "url": "https://sspai.com/feed", "limit": 8},
    {"name": "InfoQ", "url": "https://www.infoq.cn/feed", "limit": 8},
    {"name": "IT之家", "url": "https://www.ithome.com/rss/", "limit": 10},
    {"name": "雷峰网", "url": "https://www.leiphone.com/feed", "limit": 8},
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
    # === 财经源（15个） ===
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
        req = urllib.request.Request(url, headers=HTTP_HEADERS)
        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as response:
            content = response.read()

        # 解析 XML（加容错：先尝试标准解析，失败则清理后重试）
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            # 清理���见的 XML 破坏字符（如机器之心的 mismatched tag）
            cleaned = content.decode('utf-8', errors='ignore')
            # 移除非法控制字符
            cleaned = ''.join(c for c in cleaned if ord(c) >= 32 or c in '\n\r\t')
            # 截断到最后一个完整的 </item> 或 </entry>
            for close_tag in ['</item>', '</entry>']:
                idx = cleaned.rfind(close_tag)
                if idx > 0:
                    # 找对应的根关闭标签并截断
                    cleaned = cleaned[:idx + len(close_tag)] + '</channel></rss>' if close_tag == '</item>' else cleaned[:idx + len(close_tag)] + '</feed>'
                    break
            try:
                root = ET.fromstring(cleaned.encode('utf-8'))
            except ET.ParseError:
                return []

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
            item['original_title'] = item['title']

            # 描述/摘要（优先 content:encoded 获取更丰富正文）
            desc_text = ''
            for desc_path in ['{http://purl.org/rss/1.0/modules/content/}encoded', 'description', '{http://www.w3.org/2005/Atom}summary', 'content', '{http://www.w3.org/2005/Atom}content']:
                desc_elem = elem.find(desc_path)
                if desc_elem is not None and desc_elem.text:
                    desc_text = desc_elem.text
                    break
            desc_text = clean_html_content(desc_text)
            item['summary'] = desc_text[:500] if desc_text else ''
            item['original_summary'] = item['summary']

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
    """并发辅助函数：获取单个 RSS 源（含 fallback），返回抓取结果与健康信息。"""
    items = fetch_rss_items(source['url'], source['limit'])
    used_url = source['url']
    used_fallback = False

    # 如果主URL失败且有fallback，尝试备选URL
    if len(items) == 0 and 'fallback_urls' in source:
        for fallback_url in source['fallback_urls']:
            items = fetch_rss_items(fallback_url, source['limit'])
            if len(items) > 0:
                used_url = fallback_url
                used_fallback = True
                break

    for item in items:
        item['rss_source'] = source['name']

    return {
        "source_name": source['name'],
        "items": items,
        "used_url": used_url,
        "used_fallback": used_fallback,
        "status": "ok" if items else "empty",
        "attempted_urls": [source['url']] + source.get('fallback_urls', []),
    }


def collect_all_news() -> List[Dict]:
    """收集所有 RSS 新闻（并发模式，10线程），支持 fallback URLs"""
    global LAST_RSS_HEALTH

    # 计算时间范围用于日志（过去24小时）
    now = datetime.now().astimezone()
    cutoff_time = now - timedelta(hours=24)

    log(f"开始收集 RSS 新闻（并发模式，{len(ALL_RSS_SOURCES)} 个源）...")
    log(f"时间过滤范围: 过去24小时 ({cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} - {now.strftime('%Y-%m-%d %H:%M:%S')})")

    all_items = []
    source_health = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_source_with_fallback, source): source for source in ALL_RSS_SOURCES}
        for future in as_completed(futures):
            result = future.result()
            source_name = result["source_name"]
            items = result["items"]
            log(f"  - {source_name}: 获取 {len(items)} 条")
            all_items.extend(items)
            source_health.append({
                "source": source_name,
                "item_count": len(items),
                "status": result["status"],
                "used_fallback": result["used_fallback"],
                "used_url": result["used_url"],
            })

    LAST_RSS_HEALTH = sorted(source_health, key=lambda item: (item["item_count"], item["source"]))
    healthy_sources = [item for item in LAST_RSS_HEALTH if item["item_count"] > 0]
    empty_sources = [item for item in LAST_RSS_HEALTH if item["item_count"] == 0]
    fallback_sources = [item for item in LAST_RSS_HEALTH if item["used_fallback"]]
    log(
        f"RSS源健康检查: 正常{len(healthy_sources)}个，空返回{len(empty_sources)}个，"
        f"fallback命中{len(fallback_sources)}个"
    )
    if empty_sources:
        log(f"  空返回源: {', '.join(item['source'] for item in empty_sources[:12])}")
    if fallback_sources:
        log(f"  fallback源: {', '.join(item['source'] for item in fallback_sources[:8])}")

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

def fetch_article_context(url: str) -> Dict[str, str]:
    """抓取原文页面上下文，用于补全主体名和关键信息。"""
    if not url or not url.startswith("http"):
        return {"page_title": "", "page_h1": "", "meta_description": "", "page_excerpt": ""}

    if url in ARTICLE_CONTEXT_CACHE:
        return dict(ARTICLE_CONTEXT_CACHE[url])

    context = {
        "page_title": "",
        "page_h1": "",
        "meta_description": "",
        "page_excerpt": "",
    }

    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=15)
        response.raise_for_status()
        raw_html = response.text

        title_match = re.search(r"<title>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
        if title_match:
            context["page_title"] = clean_html_content(title_match.group(1))[:200]

        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", raw_html, re.IGNORECASE | re.DOTALL)
        if h1_match:
            context["page_h1"] = clean_html_content(h1_match.group(1))[:200]

        meta_match = re.search(
            r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\'](.*?)["\']',
            raw_html,
            re.IGNORECASE | re.DOTALL,
        )
        if meta_match:
            context["meta_description"] = clean_html_content(meta_match.group(1))[:300]

        text_html = re.sub(r"<script[^>]*>.*?</script>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)
        text_html = re.sub(r"<style[^>]*>.*?</style>", " ", text_html, flags=re.IGNORECASE | re.DOTALL)
        text_html = re.sub(r"<noscript[^>]*>.*?</noscript>", " ", text_html, flags=re.IGNORECASE | re.DOTALL)
        context["page_excerpt"] = clean_html_content(text_html)[:1500]
    except Exception as e:
        log(f"抓取原文上下文失败 [{url}]: {e}")

    ARTICLE_CONTEXT_CACHE[url] = context
    return dict(context)


def enrich_selected_news_context(categorized: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """为入选新闻补充原文页面标题/导语，降低主体缺失概率。"""
    log("正在补充入选新闻的原文上下文...")

    total = 0
    enriched = 0
    for items in categorized.values():
        for item in items:
            total += 1
            item.setdefault("original_title", item.get("title", ""))
            item.setdefault("original_summary", item.get("summary", ""))
            context = fetch_article_context(item.get("link", ""))
            item.update(context)
            if any(context.values()):
                enriched += 1

    log(f"原文上下文补充完成: {enriched}/{total} 条")
    return categorized


def build_source_context(item: Dict) -> str:
    """聚合原标题、摘要和原文上下文，作为改写依据。"""
    parts = [
        item.get("original_title", "") or item.get("title", ""),
        item.get("original_summary", "") or item.get("summary", ""),
        item.get("page_title", ""),
        item.get("page_h1", ""),
        item.get("meta_description", ""),
        item.get("page_excerpt", ""),
    ]
    return re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()


def extract_time_markers(text: str) -> List[str]:
    """提取标题中的时间表达，避免模型引入原文里没有的时间信息。"""
    markers = []
    if not text:
        return markers

    for pattern in TIME_MARKER_PATTERNS:
        for match in re.finditer(pattern, text):
            marker = re.sub(r"\s+", "", match.group(0).strip())
            if marker and marker not in markers:
                markers.append(marker)

    return markers


def build_allowed_time_markers(item: Dict) -> List[str]:
    """构建该新闻允许出现的时间表达集合。"""
    markers = extract_time_markers(build_source_context(item))
    parsed_time = item.get("parsed_time", "")

    if parsed_time:
        try:
            dt = datetime.strptime(parsed_time, "%Y-%m-%d %H:%M:%S")
            for marker in (
                f"{dt.year}年",
                f"{dt.month}月",
                f"{dt.month}月{dt.day}日",
            ):
                if marker not in markers:
                    markers.append(marker)
        except ValueError:
            pass

    return markers


def is_generic_subject(subject: str) -> bool:
    """判断主体是否过于泛化。"""
    subject = re.sub(r"\s+", "", subject or "")
    if not subject:
        return True

    lower_subject = subject.lower()

    if subject in GENERIC_SUBJECT_WORDS:
        return True
    if lower_subject in GENERIC_SUBJECT_LOWER_WORDS:
        return True
    if subject in SITE_NOISE_TOKENS:
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?", subject):
        return True
    if re.fullmatch(r"[A-Z]{1,4}\d*", subject):
        return True
    if re.fullmatch(r"Win\d+(?:Win\d+)?", subject):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?(?:万|亿)?元?[A-Z]?轮(?:融资)?", subject):
        return True
    if re.search(r"(?:轮融资|亿元融资)$", subject) and re.search(r"\d", subject):
        return True

    if subject.startswith(("目前", "当前", "针对", "关于", "这类", "该类", "这一", "该", "这个")):
        return True

    for generic in GENERIC_SUBJECT_WORDS:
        if subject in {f"中国{generic}", f"国产{generic}", f"全球{generic}"}:
            return True

    return False


def extract_subject_candidates(text: str) -> List[str]:
    """从原始材料中提取可能的主体候选，用于约束标题改写。"""
    if not text:
        return []

    candidates = []
    seen = set()

    def add_candidate(raw: str):
        candidate = clean_html_content(raw)
        candidate = candidate.strip(" ,，。：:；;（）()【】[]“”\"'")
        if not candidate or len(candidate) < 2 or len(candidate) > 40:
            return
        compact = re.sub(r"\s+", "", candidate)
        if compact.lower() in {"github", "star", "stars", "news", "today"}:
            return
        if is_generic_subject(compact):
            return
        if compact not in seen:
            seen.add(compact)
            candidates.append(candidate)

    model_name_pattern = r"\b[A-Za-z]+[A-Za-z0-9]*(?:[.-][A-Za-z0-9]+)+(?:\s+[A-Za-z0-9.+\-]+)?\b"
    camel_case_pattern = r"\b[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]+)+\b"
    english_pattern = r"\b[A-Za-z][A-Za-z0-9.+\-]*(?:\s+[A-Za-z0-9.+\-]+){0,3}\b"
    for pattern in (model_name_pattern, camel_case_pattern, english_pattern):
        for match in re.finditer(pattern, text):
            token = match.group(0).strip()
            compact = token.replace(" ", "")
            strong_token = (
                any(ch.isdigit() for ch in compact)
                or "-" in compact
                or "." in compact
                or any(ch.isupper() for ch in compact[1:])
            )
            if strong_token:
                add_candidate(token)

    organization_pattern = r"([A-Za-z0-9\u4e00-\u9fa5·\-\.\s]{2,30}(?:AI实验室|研究院|研究所|实验室|集团|公司|科技|大学|学院|研究中心|工厂|银行))"
    for match in re.finditer(organization_pattern, text):
        token = match.group(0).strip()
        add_candidate(token)

    verb_group = "|".join(ACTION_VERBS)
    prefix_pattern = rf"([A-Za-z0-9\u4e00-\u9fa5·\-\.\s]{{2,30}}?)(?:正式|日前|将|已|最新|刚刚|成功|全面|火速)?(?:{verb_group})"
    for match in re.finditer(prefix_pattern, text):
        add_candidate(match.group(1))

    finance_prefix_pattern = r"([A-Za-z0-9\u4e00-\u9fa5·\-\.\s]{2,24}?)(?:营收|年报|财报|估值|上市|融资|聆讯|并购|收购|交付|涨停|量产)"
    for match in re.finditer(finance_prefix_pattern, text):
        add_candidate(match.group(1))

    suffix_pattern = r"([A-Za-z0-9\u4e00-\u9fa5·\-\.\s]{2,30}(?:实验室|研究院|研究所|集团|公司|大学|学院|工厂|银行|框架|版本|笔记本|手机|大模型|模型|系统|计划))"
    for match in re.finditer(suffix_pattern, text):
        add_candidate(match.group(1))

    return candidates[:10]


def normalize_material_text(text: str) -> str:
    """清理素材句子里的站点噪音和时间前缀。"""
    text = clean_html_content(text)
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"IT之家\s*\d+\s*月\s*\d+\s*日消息[，,:：]?", "", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", "", text)
    text = re.sub(r"来源[:：]\S+", "", text)
    text = re.sub(r"量子位\s*\|\s*公众号\s*QbitAI", "", text)
    text = re.sub(r"首页\s+资讯.*?扫码关注量子位", "", text)
    text = re.sub(r"推荐快报广场.*?视频投稿App下载", "", text)
    text = re.sub(r"首页\s+IT圈.*?Win11\s+专题", "", text)
    text = re.sub(r"您正在使用IE低版浏览器.*?极客购", "", text)
    text = re.sub(r"-->\s*OSCHINA\s*-\s*开源\s*×\s*AI\s*·\s*开发者生态社区", "", text)
    text = re.sub(r"\s*[–\-|｜]\s*(量子位|IT之家|爱范儿|雷峰网|OSCHINA|钛媒体官方网站?)\s*$", "", text)
    text = re.sub(r"^[，,:：;；、\-\s]+", "", text)
    return text.strip()


def compact_title_text(title: str) -> str:
    """压缩标题中的无意义空格和冗余标点。"""
    title = normalize_material_text(title)
    title = re.sub(r"(\d)\s+月\s+(\d+)\s+日", r"\1月\2日", title)
    title = re.sub(r"(\d)\s+月", r"\1月", title)
    title = re.sub(r"(\d)\s+日", r"\1日", title)
    title = re.sub(r"\s*([，。！？：；])\s*", r"\1", title)
    title = re.sub(r"\s{2,}", " ", title)
    return title.strip(" ，,。；;")


def score_subject_candidate(candidate: str, item: Dict) -> int:
    """给主体候选打分，优先选择具体项目名和机构名。"""
    if not candidate:
        return -100

    candidate = clean_html_content(candidate)
    compact = re.sub(r"\s+", "", candidate)
    lower_candidate = compact.lower()
    if is_generic_subject(compact):
        return -100
    if compact in SITE_NOISE_TOKENS or lower_candidate in {token.lower() for token in SITE_NOISE_TOKENS}:
        return -100

    title_text = item.get("original_title", "") or item.get("title", "")
    summary_text = item.get("original_summary", "") or item.get("summary", "")
    page_title = item.get("page_title", "")
    meta_description = item.get("meta_description", "")
    page_excerpt = item.get("page_excerpt", "")

    score = 0
    if compact in title_text:
        score += 6
    if compact in summary_text:
        score += 3
    if compact in page_title:
        score += 3
    if compact in meta_description:
        score += 2
    if compact in page_excerpt:
        score += 1

    if re.search(rf"(领先|超越|击败|终结)[^。！？]*{re.escape(compact)}", summary_text + meta_description + page_excerpt):
        score -= 4

    if any(ch.isdigit() for ch in compact) or "-" in compact or "." in compact:
        score += 4
    if any(ch.isupper() for ch in compact[1:]):
        score += 3
    if re.search(r"(实验室|研究院|研究所|集团|公司|科技|大学|学院|中心|工厂|银行)$", compact):
        score += 3
    if 2 <= len(compact) <= 18:
        score += 1
    if len(compact) > 24:
        score -= 3
    if lower_candidate in {"qbitai", "it之家", "oschina"}:
        score -= 6

    return score


def pick_best_subject(item: Dict) -> str:
    """从素材中挑选最具体、最适合放进简讯里的主体名。"""
    source_context = build_source_context(item)
    candidates = extract_subject_candidates(source_context)
    if not candidates:
        return ""

    scored = sorted(
        ((score_subject_candidate(candidate, item), candidate) for candidate in candidates),
        key=lambda pair: (-pair[0], len(pair[1]))
    )

    best_score, best_candidate = scored[0]
    return best_candidate if best_score >= 4 else ""


def is_title_specific_enough(item: Dict) -> bool:
    """判断原标题是否已经足够具体，避免被规则兜底误伤。"""
    original_title = compact_title_text(item.get("original_title", item.get("title", "")))
    if not original_title or original_title.startswith(("目前", "当前", "针对", "关于", "这类", "该类", "这一", "这个")):
        return False
    if has_non_news_style(original_title) or has_excessive_english(original_title):
        return False

    if re.search(r"[A-Za-z]+[A-Za-z0-9]*(?:[.-][A-Za-z0-9]+)+", original_title):
        return True
    if re.search(r"[A-Za-z0-9\u4e00-\u9fa5·]{2,20}(?:实验室|研究院|研究所|集团|公司|科技|工厂|银行)", original_title):
        return True
    if any(keyword in original_title for keyword in ACTION_VERBS + RESULT_KEYWORDS):
        return True

    subject = pick_best_subject(item)
    return bool(subject and subject in original_title)


def extract_fact_sentences(item: Dict, subject: str, related_entities: List[str]) -> List[str]:
    """从标题、摘要和原文中抽取可用于生成简讯的事实句。"""
    sentences = []
    raw_texts = [
        item.get("original_summary", "") or item.get("summary", ""),
        item.get("meta_description", ""),
        item.get("original_title", "") or item.get("title", ""),
        item.get("page_title", ""),
        item.get("page_h1", ""),
    ]

    for text in raw_texts:
        cleaned = compact_title_text(text)
        if cleaned:
            sentences.append(cleaned)

    excerpt = normalize_material_text(item.get("page_excerpt", ""))
    for sentence in re.split(r"[。！？\n]", excerpt):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > 90:
            for clause in sentence.split("，"):
                clause = clause.strip()
                if clause:
                    sentences.append(clause)
            continue
        sentences.append(sentence)

    ranked = []
    for sentence in sentences:
        score = 0
        if subject and subject in sentence:
            score += 5
        if any(entity and entity in sentence for entity in related_entities):
            score += 3
        if any(keyword in sentence for keyword in ACTION_VERBS + RESULT_KEYWORDS):
            score += 4
        if re.search(r"\d", sentence):
            score += 2
        if 12 <= len(sentence) <= 60:
            score += 2
        if any(token in sentence for token in SITE_NOISE_TOKENS):
            score -= 4
        if any(noise in sentence for noise in ("首页", "扫码关注", "公众号", "推荐快报", "订阅 RSS订阅")):
            score -= 8
        ranked.append((score, sentence))

    ranked.sort(key=lambda pair: (-pair[0], len(pair[1])))
    return [sentence for score, sentence in ranked if score >= 3][:12]


def inject_specific_entity(sentence: str, subject: str, related_entities: List[str]) -> str:
    """把摘要中的泛化主语替换成更具体的项目名。"""
    sentence = compact_title_text(sentence)
    for entity in related_entities:
        if not entity or entity == subject or entity in sentence:
            continue
        if "开源模型" in sentence:
            sentence = sentence.replace("开源模型", f"{entity}开源模型", 1)
            break
        if "OCR项目" in sentence:
            sentence = sentence.replace("OCR项目", entity, 1)
            break
        if "世界模型" in sentence and "国产世界模型" in sentence:
            sentence = sentence.replace("国产世界模型", entity, 1)
            break
        if "大模型" in sentence and any(ch.isdigit() for ch in entity):
            sentence = sentence.replace("大模型", entity, 1)
            break
    return compact_title_text(sentence)


def shorten_title(title: str, max_len: int = 52) -> str:
    """尽量在不丢关键信息的前提下压缩标题长度。"""
    title = compact_title_text(title)
    if len(title) <= max_len:
        return title

    replacements = [
        ("，并在与Polymarket人类交易市场的直接对比中展现出显著优势", "，直接对比人类交易者占优"),
        ("，研发人员集体出走", "，核心团队多人离职"),
        ("，苹果Vision Pro头显专享", "，Vision Pro专享"),
        ("，目标2030年前开发", "，目标2030年前量产"),
        ("，Find X9 Ultra、Find X9s Pro 手机等将至", "，Find X9系列等将至"),
    ]
    for old, new in replacements:
        if old in title:
            title = title.replace(old, new)
            if len(title) <= max_len:
                return compact_title_text(title)

    if "，" in title:
        clauses = [clause.strip() for clause in title.split("，") if clause.strip()]
        compacted = clauses[0]
        if len(clauses) > 1:
            second = clauses[1]
            if len(compacted) + len(second) + 1 <= max_len:
                compacted = f"{compacted}，{second}"
        title = compacted

    if len(title) > max_len:
        title = title[:max_len].rstrip("，,、；;：:")

    return compact_title_text(title)


def restore_precise_entities(item: Dict, title: str) -> str:
    """尽量把模型省略掉的版本号或完整项目名补回标题。"""
    title = compact_title_text(title)
    source_context = build_source_context(item)
    for entity in extract_subject_candidates(source_context):
        if entity in title:
            continue
        if not (any(ch.isdigit() for ch in entity) or "-" in entity or "." in entity):
            continue
        variants = {
            entity.replace(".0", ""),
            entity.replace(".5", ""),
            entity.split(".0")[0],
        }
        for variant in variants:
            variant = variant.strip()
            if variant and variant != entity and variant in title:
                title = title.replace(variant, entity, 1)
                break
    return compact_title_text(title)


def build_rule_based_rewrite(item: Dict, reason: str = "") -> Dict[str, str]:
    """在 LLM 失败时，用主体+事实句规则兜底生成简讯。"""
    subject = pick_best_subject(item)
    source_context = build_source_context(item)
    related_entities = [candidate for candidate in extract_subject_candidates(source_context) if candidate != subject]
    fact_sentences = extract_fact_sentences(item, subject, related_entities)
    if is_title_specific_enough(item):
        original_first = compact_title_text(item.get("original_title", item.get("title", "")))
        if original_first:
            fact_sentences = [original_first] + [sentence for sentence in fact_sentences if sentence != original_first]

    for sentence in fact_sentences:
        candidate = inject_specific_entity(sentence, subject, related_entities)
        if any(token in candidate for token in SITE_NOISE_TOKENS):
            continue
        if subject and subject not in candidate:
            if candidate.startswith(ACTION_VERBS + RESULT_KEYWORDS):
                candidate = f"{subject}{candidate}"
            elif any(keyword in candidate for keyword in ("领先", "霸榜", "登顶", "稳居第一", "Elo")):
                candidate = f"{subject}{candidate}"
            else:
                candidate = f"{subject}{candidate}"

        candidate = shorten_title(candidate)
        candidate = restore_precise_entities(item, candidate)
        valid, _ = validate_rewritten_title(item, subject, candidate)
        if valid:
            return {"subject": subject, "title": candidate}

    fallback_title = compact_title_text(item.get("original_title", item.get("title", "")))
    fallback_title = inject_specific_entity(fallback_title, subject, related_entities)
    if subject and subject not in fallback_title and fallback_title:
        fallback_title = shorten_title(f"{subject}{fallback_title}")
    else:
        fallback_title = shorten_title(fallback_title)
    fallback_title = restore_precise_entities(item, fallback_title)

    return {
        "subject": subject,
        "title": fallback_title,
    }


def parse_json_payload(result: str, fallback):
    """兼容 markdown code fence 的 JSON 解析。"""
    if not result:
        return fallback

    cleaned = result.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    for pattern in (r"\[[\s\S]*\]", r"\{[\s\S]*\}"):
        match = re.search(pattern, cleaned)
        if not match:
            continue
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            continue

    return fallback


def validate_rewritten_title(item: Dict, subject: str, title: str) -> tuple:
    """校验生成的新闻简讯是否满足事实性和可读性要求。"""
    subject = clean_html_content(subject)
    title = compact_title_text(title)

    if not subject:
        return False, "主体为空"
    if is_generic_subject(subject):
        return False, f"主体泛化: {subject}"

    if not title:
        return False, "标题为空"
    if title.startswith(("目前", "当前", "针对", "关于", "这类", "该类", "这一", "这个")):
        return False, f"标题出现空泛起手: {title[:12]}"
    if has_non_news_style(title):
        return False, "标题带有提问/评测/营销表达"
    if has_excessive_english(title):
        return False, "标题英文占比过高或含泛英文概念"
    if any(token in title for token in SITE_NOISE_TOKENS):
        return False, "标题混入站点名或栏目名"
    if re.match(r"^\d{4,}", title):
        return False, "标题以编号或补丁号起手"
    if len(title) < 18 or len(title) > 52:
        return False, f"标题长度异常: {len(title)}字"
    if count_chinese_chars(title) < 8:
        return False, "标题中文信息量不足"
    if not is_valid_news_title(title):
        return False, "标题未通过新闻有效性校验"

    normalized_title = re.sub(r"\s+", "", title).lower()
    normalized_subject = re.sub(r"\s+", "", subject).lower()
    if normalized_subject not in normalized_title:
        return False, f"标题未包含主体: {subject}"

    allowed_time_markers = set(build_allowed_time_markers(item))
    title_time_markers = extract_time_markers(title)
    new_time_markers = [marker for marker in title_time_markers if marker not in allowed_time_markers]
    if new_time_markers:
        return False, f"新增原文中不存在的时间表达: {','.join(new_time_markers)}"

    return True, ""


def rewrite_single_title(item: Dict, reason: str = "") -> Dict[str, str]:
    """单条回退改写，用更强约束修复主体泛化或时间错乱问题。"""
    subject_hints = extract_subject_candidates(build_source_context(item))
    forced_subject = pick_best_subject(item)
    important_entities = [entity for entity in subject_hints if entity != forced_subject][:4]
    prompt = f"""你是专业中文新闻编辑，请将这条新闻改写成一句可直接发布的中文新闻简讯。

【新闻素材】
- 来源: {item.get('rss_source', '')}
- 发布时间: {item.get('parsed_time', '')}
- 原始标题: {item.get('original_title', item.get('title', ''))}
- RSS摘要: {item.get('original_summary', item.get('summary', ''))}
- 页面标题: {item.get('page_title', '')}
- 页面导语: {item.get('meta_description', '')}
- 页面摘录: {item.get('page_excerpt', '')[:400]}
- 主体候选: {', '.join(subject_hints) if subject_hints else '无'}
- 固定主体: {forced_subject or '无'}
- 需尽量保留的具体名词: {', '.join(important_entities) if important_entities else '无'}
- 上次失败原因: {reason or '无'}

【硬规则】
1. 只写材料里已经明确出现的事实，不得脑补，不得评论。
2. 如果材料里出现了具体项目名/模型名/产品名/公司名/机构名，标题必须明确写出该主体。
3. 如果“固定主体”不为空，标题主体必须使用该名称，不得替换成更泛的说法。
4. 如果“需尽量保留的具体名词”中有 OLMo、PaddleOCR、EchoZ-1.0、GigaWorld-1 等项目名，且它们与事件直接相关，标题里也要尽量带上。
5. 严禁使用“项目”“模型”“平台”“系统”“事项”“计划”“这类大模型”等泛化主语替代具体名称。
6. 不得引入材料里没有的时间表达；非必要不要写时间。
7. 22-48字，单句，格式为“主体+动作+结果”。

请只输出一个 JSON 对象：
{{"subject": "...", "title": "..."}}"""

    result = call_llm_api(prompt, max_tokens=600)
    payload = parse_json_payload(result, {})
    if isinstance(payload, dict):
        return {
            "subject": clean_html_content(str(payload.get("subject", ""))),
            "title": clean_html_content(str(payload.get("title", ""))),
        }
    return {"subject": "", "title": ""}


def normalize_titles(categorized: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """将入选新闻改写为单行新闻简讯，保留具体主体并避免时间错乱。"""
    log("正在将入选新闻改写为单行新闻简讯...")

    selected_items = []
    for items in categorized.values():
        selected_items.extend(items)

    if not selected_items:
        return categorized

    materials = []
    for idx, item in enumerate(selected_items, 1):
        source_context = build_source_context(item)
        materials.append({
            "id": idx,
            "source": item.get("rss_source", ""),
            "published": item.get("parsed_time", ""),
            "original_title": item.get("original_title", item.get("title", "")),
            "rss_summary": item.get("original_summary", item.get("summary", ""))[:240],
            "page_title": item.get("page_title", ""),
            "page_h1": item.get("page_h1", ""),
            "meta_description": item.get("meta_description", ""),
            "context_excerpt": source_context[:420],
            "subject_hints": extract_subject_candidates(source_context),
        })

    prompt = f"""你是专业中文新闻编辑，请将以下 {len(materials)} 条素材改写成适合公众号列表展示的“单行新闻简讯”。

新闻素材：
{json.dumps(materials, ensure_ascii=False, indent=2)}

【硬规则】
1. 只写素材里已经明确出现的事实，不得脑补，不得评论，不得写空话。
2. 如果素材里有具体项目名/模型名/产品名/公司名/机构名，必须在标题中明确写出，且不得用“项目”“模型”“平台”“系统”“事项”“计划”等泛词替代。
3. 不得引入素材中不存在的时间表达；非必要不要写时间。
4. 每条标题 22-42 字，单句，适合公众号新闻列表阅读。
5. 标题格式统一为“主体 + 动作 + 结果”，避免“目前”“当前”“针对需要预测的事项”“这类大模型”等空泛表达。
6. 仅允许保留品牌名/产品名的英文原文。

【特别提醒】
- 如果素材中出现 PaddleOCR、EchoZ-1.0、GigaWorld-1、Qwen3.5-Omni、IdeaPad 5i 这类具体名词，标题必须保留这些名称。
- 优先选择最具体的主体，不要退化成“中国开源OCR项目”“国产世界模型”“这类大模型”。

请只输出 JSON 数组，长度必须为 {len(materials)}，每项格式如下：
{{"id": 1, "subject": "...", "title": "..."}}"""

    result = call_llm_api(prompt, max_tokens=2500)
    payload = parse_json_payload(result, [])

    rewrite_map = {}
    if isinstance(payload, list):
        for record in payload:
            if not isinstance(record, dict):
                continue
            rewrite_map[record.get("id")] = {
                "subject": clean_html_content(str(record.get("subject", ""))),
                "title": restore_precise_entities(
                    selected_items[record.get("id") - 1],
                    clean_html_content(str(record.get("title", "")))
                ) if isinstance(record.get("id"), int) and 1 <= record.get("id") <= len(selected_items)
                else clean_html_content(str(record.get("title", ""))),
            }

    updated_count = 0
    kept_count = 0
    retry_count = 0
    rule_fallback_count = 0

    for idx, item in enumerate(selected_items, 1):
        original_specific = is_title_specific_enough(item)
        rewrite = rewrite_map.get(idx, {"subject": "", "title": ""})
        valid, reason = validate_rewritten_title(item, rewrite.get("subject", ""), rewrite.get("title", ""))

        if not valid:
            retry_count += 1
            rewrite = rewrite_single_title(item, reason)
            rewrite["title"] = restore_precise_entities(item, rewrite.get("title", ""))
            valid, reason = validate_rewritten_title(item, rewrite.get("subject", ""), rewrite.get("title", ""))

        if not valid and not original_specific:
            rule_fallback_count += 1
            rewrite = build_rule_based_rewrite(item, reason)
            valid, reason = validate_rewritten_title(item, rewrite.get("subject", ""), rewrite.get("title", ""))

        if not valid and original_specific:
            original_title = shorten_title(item.get("original_title", item.get("title", "")))
            original_subject = pick_best_subject(item)
            valid, reason = validate_rewritten_title(item, original_subject, original_title)
            if valid:
                rewrite = {"subject": original_subject, "title": original_title}

        if valid:
            old_title = item.get("title", "")
            item["title"] = compact_title_text(rewrite["title"])
            item["subject"] = rewrite["subject"]
            log(f"  简讯改写: {len(old_title)}字 → {len(item['title'])}字")
            updated_count += 1
        else:
            item["title"] = compact_title_text(item.get("original_title", item.get("title", "")))
            item["subject"] = ""
            log(f"  保留原标题（{reason}）: {item['title'][:40]}...")
            kept_count += 1

    log(
        f"标题简讯化完成: 更新{updated_count}条，保留原标题{kept_count}条，"
        f"单条回退{retry_count}条，规则兜底{rule_fallback_count}条"
    )
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

def call_doubao_api(prompt, max_tokens=2000, retries=3):
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
    for attempt in range(retries + 1):
        try:
            if attempt > 0:
                wait = min(5 * (2 ** (attempt - 1)), 30)  # 5s, 10s, 20s, 最多30s
                log(f"豆包 API 重试第 {attempt} 次（等待 {wait}s）...")
                time.sleep(wait)
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
    """调用豆包 API"""
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
        "rss_source_health": LAST_RSS_HEALTH,
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

    # 2.6 补充入选新闻的原文上下文
    categorized_news = enrich_selected_news_context(categorized_news)

    # 2.7 生成单行新闻简讯
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
