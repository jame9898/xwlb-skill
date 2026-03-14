import requests
from datetime import datetime, timedelta
import re
import html as html_module
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
})

def fetch_html(url, timeout=15):
    for attempt in range(2):
        try:
            response = session.get(url, timeout=timeout)
            response.encoding = 'utf-8'
            return response.text
        except:
            if attempt == 0:
                continue
            return None
    return None

def fetch_detail_content(url):
    html_content = fetch_html(url)
    if not html_content:
        return None
    
    start_match = re.search(r'<div class="content_area"[^>]*>', html_content)
    if not start_match:
        return None
    
    start_pos = start_match.end()
    end_match = re.search(r'<div class="zebian">', html_content[start_pos:])
    
    if end_match:
        content = html_content[start_pos:start_pos + end_match.start()]
    else:
        content = html_content[start_pos:start_pos + 8000]
    
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
    content = re.sub(r'<br\s*/?>', '\n', content)
    content = re.sub(r'</p>', '\n', content)
    content = re.sub(r'<[^>]+>', '', content)
    content = html_module.unescape(content)
    content = re.sub(r'&nbsp;', ' ', content)
    content = re.sub(r'&[ld]dquo;', '"', content)
    content = re.sub(r'&mdash;', '——', content)
    content = re.sub(r'&middot;', '·', content)
    content = re.sub(r'\n\s*\n+', '\n', content)
    content = re.sub(r'[ \t]+', ' ', content)
    
    return content.strip() if content.strip() else None

def fetch_all_details_concurrent(news_items, max_workers=5):
    results = {}
    
    def fetch_one(item):
        content = fetch_detail_content(item['url'])
        return item['url'], content
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_one, item) for item in news_items]
        for future in as_completed(futures):
            url, content = future.result()
            results[url] = content
    
    for item in news_items:
        item['content'] = results.get(item['url'])

def is_brief_news(title):
    return '快讯' in title

def format_content(text, title="", is_md=True):
    if not text:
        return ""
    
    is_brief = is_brief_news(title)
    paragraphs = text.split('\n')
    formatted = []
    brief_items = []
    current_title = None
    
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        
        if is_brief:
            if p.startswith('央视网消息（新闻联播）'):
                p = re.sub(r'^央视网消息（新闻联播）[：:]\s*', '', p)
            if not p:
                continue
            
            if not re.search(r'[。！？]$', p):
                current_title = p
            else:
                if current_title:
                    if is_md:
                        brief_items.append('***' + current_title + '***\n　　' + p)
                    else:
                        brief_items.append('【' + current_title + '】\n　　' + p)
                    current_title = None
                else:
                    formatted.append('　　' + p)
        else:
            formatted.append('　　' + p)
    
    if is_brief:
        return '\n\n'.join(brief_items)
    
    return '\n'.join(formatted)

def clean_title(title):
    title = title.strip()
    title = re.sub(r'^\[视频\]\s*', '', title)
    return title.strip()

def parse_day_page(html):
    if not html:
        return []
    
    pattern = r'<a href="(https://tv\.cctv\.com/\d{4}/\d{2}/\d{2}/VIDE[^"]+)"[^>]*title="([^"]+)"'
    matches = re.findall(pattern, html)
    
    seen = set()
    items = []
    for url, title in matches:
        title = clean_title(title)
        if title and len(title) > 3 and '完整版' not in title and not title.startswith('《新闻联播》'):
            key = title[:20]
            if key not in seen:
                seen.add(key)
                items.append({'title': title, 'url': url})
    
    return items

CHINESE_NUMS = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
                '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十',
                '二十一', '二十二', '二十三', '二十四', '二十五', '二十六', '二十七', '二十八', '二十九', '三十']

def to_chinese(num):
    return CHINESE_NUMS[num] if 0 < num < len(CHINESE_NUMS) else str(num)

def format_summary(date_str, news_items):
    lines = ["=" * 50, f"{date_str} 新闻联播简介如下：", "=" * 50]
    for i, item in enumerate(news_items, 1):
        lines.append(f"第{to_chinese(i)}条，{item['title']}")
    lines.extend(["=" * 50, f"（来源：{date_str}的新闻联播 - 央视网新闻联播主页 - https://tv.cctv.com/lm/xwlb/index.shtml）", "=" * 50])
    return '\n'.join(lines)

def format_md_summary(date_str, news_items):
    lines = [f"# {date_str} 新闻联播", "", "> 来源：央视网新闻联播主页 - https://tv.cctv.com/lm/xwlb/index.shtml", ""]
    for i, item in enumerate(news_items, 1):
        lines.append(f"第{to_chinese(i)}条：{item['title']}")
        lines.append("")
    return '\n'.join(lines)

def format_md_detail(date_str, news_items):
    lines = [f"# {date_str} 新闻联播", "", "> 来源：央视网新闻联播主页 - https://tv.cctv.com/lm/xwlb/index.shtml", ""]
    for i, item in enumerate(news_items, 1):
        lines.append(f"## 第{to_chinese(i)}条：{item['title']}")
        lines.append("")
        if item.get('content'):
            lines.append(format_content(item['content'], item['title'], is_md=True))
        else:
            lines.append("暂无详细内容")
        lines.append("")
    return '\n'.join(lines)

def format_txt_detail(date_str, news_items):
    lines = []
    for i, item in enumerate(news_items, 1):
        if item.get('content'):
            lines.append("=" * 50)
            lines.append(f"第{to_chinese(i)}条：{item['title']}")
            lines.append("=" * 50)
            lines.append("")
            lines.append(format_content(item['content'], item['title'], is_md=False))
            lines.append("")
    return '\n'.join(lines)

def main():
    use_md = '--md' in sys.argv
    if use_md:
        sys.argv.remove('--md')
    
    if len(sys.argv) < 2:
        print("用法：")
        print("  python get_xwlb.py today              # 查看今天的新闻简介")
        print("  python get_xwlb.py yesterday          # 查看昨天的新闻简介")
        print("  python get_xwlb.py 2025-10-01         # 查看指定日期的新闻简介")
        print("  python get_xwlb.py today 1            # 查看今天所有新闻详情")
        print("  python get_xwlb.py today 1 --md       # 生成MD格式文件")
        return
    
    date_arg = sys.argv[1]
    
    if date_arg == "today":
        d = datetime.now()
    elif date_arg == "yesterday":
        d = datetime.now() - timedelta(days=1)
    else:
        try:
            if '-' in date_arg:
                parts = date_arg.split('-')
                d = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
            else:
                d = datetime(int(date_arg[:4]), int(date_arg[4:6]), int(date_arg[6:8]))
        except:
            print("日期格式错误，请使用：YYYY-MM-DD 或 YYYYMMDD")
            return
    
    year, month, day = d.year, d.month, d.day
    date_str = f"{year}年{month:02d}月{day:02d}日"
    target_str = f"{year}{month:02d}{day:02d}"
    
    print(f"正在获取 {date_str} 的新闻联播内容...")
    
    url = f"https://tv.cctv.com/lm/xwlb/day/{target_str}.shtml"
    html = fetch_html(url)
    
    if not html:
        print(f"未找到 {date_str} 的新闻内容")
        return
    
    news_items = parse_day_page(html)
    if not news_items:
        print(f"未找到 {date_str} 的新闻内容")
        return
    
    summary_dir, detail_dir = "News_Summary", "News_Detail"
    os.makedirs(summary_dir, exist_ok=True)
    os.makedirs(detail_dir, exist_ok=True)
    
    ext = ".md" if use_md else ".txt"
    summary_file = os.path.join(summary_dir, f"{target_str}_summary{ext}")
    detail_file = os.path.join(detail_dir, f"{target_str}_detail{ext}")
    
    if use_md:
        summary = format_md_summary(date_str, news_items)
    else:
        summary = format_summary(date_str, news_items)
    
    print(summary)
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"\n简介已保存到: {summary_file}")
    
    if len(sys.argv) > 2:
        print(f"\n正在并发获取所有新闻的详细内容（5线程）...")
        
        fetch_all_details_concurrent(news_items)
        
        if use_md:
            detail = format_md_detail(date_str, news_items)
        else:
            detail = format_txt_detail(date_str, news_items)
        
        with open(detail_file, "w", encoding="utf-8") as f:
            f.write(detail)
        print(f"详情已保存到: {detail_file}")

if __name__ == "__main__":
    main()
