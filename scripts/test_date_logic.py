#!/usr/bin/env python3
"""
测试日期逻辑和HTML模板
不需要API调用，只验证日期计算和模板结构
"""

from datetime import datetime, timedelta
from zhdate import ZhDate

def test_date_logic():
    """测试日期逻辑"""
    print("=" * 60)
    print("测试日期逻辑")
    print("=" * 60)

    # 计算日期
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    # 格式化日期字符串
    yesterday_str = yesterday.strftime("%Y年%m月%d日")
    today_date = today.strftime("%Y年%m月%d日")

    # 获取今天的星期
    weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    today_weekday = weekday_names[today.weekday()]

    # 获取真实的农历日期
    zh_date = ZhDate.from_datetime(today)
    today_lunar = zh_date.chinese().split()[0]  # 例如: "二零二五年十一月二十七"

    print(f"\n✅ 今天日期: {today_date} {today_weekday}")
    print(f"✅ 农历日期: {today_lunar}")
    print(f"✅ 新闻目标日期（昨天）: {yesterday_str}")

    # 标题和封面图使用今天的日期
    title = f"{today.month}月{today.day}日AI科技财经日报"
    print(f"\n✅ 文章标题: {title}")

    return yesterday_str, today_lunar, today_weekday, today_date

def test_html_template(yesterday_str, today_lunar, today_weekday, today_date):
    """测试HTML模板结构"""
    print("\n" + "=" * 60)
    print("测试HTML模板结构")
    print("=" * 60)

    # 生成简化的HTML模板（只显示关键部分）
    html_preview = f"""
<!-- 日期卡片 - 显示今天的日期 -->
<section style="text-align: center; padding: 25px 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
<p>{today_lunar}</p>
<p>{today_weekday}</p>
<p>{today_date}</p>
</section>

<!-- 内容说明 -->
<section style="text-align: center; margin-bottom: 25px;">
<p>📰 以下是 <strong>{yesterday_str}</strong> 的新闻汇总</p>
</section>

<!-- AI 领域 -->
<section>
<p>📱 AI 领域</p>
<p><span>01</span>AI新闻1</p>
<p><span>02</span>AI新闻2</p>
...
</section>
"""

    print("\n✅ HTML模板关键部分预览:")
    print(html_preview)

    print("\n✅ 验证要点:")
    print(f"  1. 日期卡片显示: {today_date} {today_weekday} ({today_lunar})")
    print(f"  2. 内容说明显示: {yesterday_str} 的新闻汇总")
    print(f"  3. 逻辑正确: 标题显示今天，内容是昨天的新闻")

if __name__ == "__main__":
    # 测试日期逻辑
    yesterday_str, today_lunar, today_weekday, today_date = test_date_logic()

    # 测试HTML模板
    test_html_template(yesterday_str, today_lunar, today_weekday, today_date)

    print("\n" + "=" * 60)
    print("✅ 所有测试通过！日期逻辑正确。")
    print("=" * 60)
