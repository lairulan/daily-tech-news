#!/usr/bin/env python3
"""
Daily Tech News 公共工具模块
提供共享的工具函数，避免代码重复
"""

import os
import ssl
import time
from datetime import datetime
from typing import Optional, Callable, Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.dirname(SCRIPT_DIR)
LOCAL_ENV_PATHS = [
    os.path.join(WORK_DIR, ".env.local"),
    os.path.join(WORK_DIR, ".env"),
]
_LOCAL_ENV_LOADED = False

# 尝试导入 certifi，如果不可用则使用系统证书
try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    # 如果 certifi 不可用，创建默认上下文
    SSL_CONTEXT = ssl.create_default_context()

# 备用：不验证证书的上下文（仅在必要时使用）
SSL_CONTEXT_UNVERIFIED = ssl._create_unverified_context()


def load_local_env(force: bool = False) -> None:
    """从项目根目录加载本地私有配置文件。

    只在环境变量尚未存在时注入，避免覆盖 CI 或 shell 中显式设置的值。
    """
    global _LOCAL_ENV_LOADED
    if _LOCAL_ENV_LOADED and not force:
        return

    for env_path in LOCAL_ENV_PATHS:
        if not os.path.exists(env_path):
            continue

        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("'").strip('"')
                    if key and key not in os.environ:
                        os.environ[key] = value
        except OSError:
            continue

    _LOCAL_ENV_LOADED = True


def get_env_var(name: str, default: Optional[str] = None, required: bool = True) -> Optional[str]:
    """优先从环境变量读取，否则回退到本地私有配置文件。"""
    load_local_env()
    value = os.environ.get(name, default)
    if required and not value:
        return None
    return value

def get_traditional_lunar_date(dt: datetime) -> str:
    """获取传统农历日期格式：乙巳年冬月廿七

    Args:
        dt: datetime 对象

    Returns:
        农历日期字符串，如 "乙巳年冬月廿七"
    """
    try:
        from zhdate import ZhDate
    except ImportError:
        return ""

    try:
        # 标准化为只包含日期部分（去除时间），避免zhdate报错
        date_only = datetime(dt.year, dt.month, dt.day)
        zh_date = ZhDate.from_datetime(date_only)

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
    except (TypeError, ValueError, IndexError, Exception):
        # zhdate 库可能无法处理某些日期，返回空字符串
        return ""

def get_weekday_name(dt: datetime) -> str:
    """获取中文星期名称

    Args:
        dt: datetime 对象

    Returns:
        星期名称，如 "星期一"
    """
    weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return weekday_names[dt.weekday()]

def rate_limited_request(
    func: Callable[..., Any],
    *args,
    delay: float = 0.5,
    **kwargs
) -> Any:
    """带速率限制的请求包装器

    Args:
        func: 要执行的函数
        *args: 函数参数
        delay: 请求后的延迟时间（秒）
        **kwargs: 函数关键字参数

    Returns:
        函数返回值
    """
    result = func(*args, **kwargs)
    time.sleep(delay)
    return result

def check_environment() -> dict:
    """检查运行环境依赖

    Returns:
        包含检查结果的字典：
        {
            "success": bool,
            "errors": list[str],
            "warnings": list[str],
            "details": dict
        }
    """
    errors = []
    warnings = []
    details = {}

    # 检查环境变量
    wechat_api_key = get_env_var("WECHAT_API_KEY", required=False)
    wechat_app_id = get_env_var("WECHAT_APP_ID", required=False)
    doubao_api_key = get_env_var("DOUBAO_API_KEY", required=False)

    details["env_vars"] = {
        "WECHAT_API_KEY": bool(wechat_api_key),
        "WECHAT_APP_ID": bool(wechat_app_id),
        "DOUBAO_API_KEY": bool(doubao_api_key),
    }

    if not wechat_api_key:
        errors.append("未设置 WECHAT_API_KEY 环境变量")

    if not wechat_app_id:
        warnings.append("未设置 WECHAT_APP_ID，将使用默认公众号")

    # 检查脚本文件
    script_dir = os.path.dirname(os.path.abspath(__file__))
    required_scripts = [
        "auto_daily_news.py",
        "generate_image.py",
        "rss_news_collector.py",
    ]

    details["scripts"] = {}
    for script in required_scripts:
        script_path = os.path.join(script_dir, script)
        exists = os.path.exists(script_path)
        details["scripts"][script] = exists
        if not exists:
            errors.append(f"脚本文件不存在: {script}")

    # 检查 Python 依赖
    details["dependencies"] = {}

    try:
        import zhdate
        details["dependencies"]["zhdate"] = True
    except ImportError:
        details["dependencies"]["zhdate"] = False
        errors.append("未安装 zhdate 包 (pip install zhdate)")

    try:
        import certifi
        details["dependencies"]["certifi"] = True
    except ImportError:
        details["dependencies"]["certifi"] = False
        warnings.append("未安装 certifi 包，将使用系统证书 (pip install certifi)")

    try:
        import requests
        details["dependencies"]["requests"] = True
    except ImportError:
        details["dependencies"]["requests"] = False
        errors.append("未安装 requests 包 (pip install requests)")

    return {
        "success": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "details": details,
    }

def print_environment_check_result(result: dict) -> None:
    """打印环境检查结果

    Args:
        result: check_environment() 返回的结果
    """
    print("=" * 50)
    print("环境依赖检查结果")
    print("=" * 50)

    # 环境变量
    print("\n📋 环境变量:")
    for var, exists in result["details"]["env_vars"].items():
        status = "✅" if exists else "❌"
        print(f"  {status} {var}")

    # 脚本文件
    print("\n📁 脚本文件:")
    for script, exists in result["details"]["scripts"].items():
        status = "✅" if exists else "❌"
        print(f"  {status} {script}")

    # Python 依赖
    print("\n📦 Python 依赖:")
    for dep, installed in result["details"]["dependencies"].items():
        status = "✅" if installed else "❌"
        print(f"  {status} {dep}")

    # 错误
    if result["errors"]:
        print("\n❌ 错误:")
        for error in result["errors"]:
            print(f"  • {error}")

    # 警告
    if result["warnings"]:
        print("\n⚠️ 警告:")
        for warning in result["warnings"]:
            print(f"  • {warning}")

    # 总结
    print("\n" + "=" * 50)
    if result["success"]:
        print("✅ 环境检查通过")
    else:
        print("❌ 环境检查失败，请修复上述错误")
    print("=" * 50)

def validate_news_content(html_content: str) -> dict:
    """验证新闻内容质量

    Args:
        html_content: HTML 格式的新闻内容

    Returns:
        验证结果字典
    """
    import re

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

    # 检查 HTML 格式
    if not html_content.strip().startswith("<"):
        warnings.append("内容可能不是有效的 HTML 格式")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }

if __name__ == "__main__":
    # 运行环境检查
    result = check_environment()
    print_environment_check_result(result)
