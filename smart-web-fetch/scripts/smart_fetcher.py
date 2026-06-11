#!/usr/bin/env python3
"""
智能网页内容获取脚本
按顺序尝试: markdown.new -> defuddle.md -> r.jina.ai
⚠️ 已移除 Scrapling/Playwright，不需要下载浏览器！
"""

import sys
import requests

# 服务列表，按优先级排序
SERVICES = [
    "https://markdown.new/",
    "https://defuddle.md/",
    "https://r.jina.ai/"
]

def fetch_with_service(service, url):
    """使用指定服务获取内容"""
    try:
        full_url = service + url
        print(f"[*] 尝试: {full_url}")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(full_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            content = response.text.strip()
            if len(content) > 200:  # 确保内容有意义
                print(f"[+] 成功获取: {service}")
                return content
    except Exception as e:
        print(f"[!] {service} 失败: {e}")
    
    return None

def smart_fetch(url):
    """智能获取网页内容"""
    print(f"[*] 开始获取: {url}")
    print("-" * 60)
    
    # 尝试各服务
    for service in SERVICES:
        content = fetch_with_service(service, url)
        if content:
            return content
    
    print("[-] 所有转换服务都失败了")
    return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用: python smart_fetcher.py <url>")
        print("\n示例:")
        print("  python smart_fetcher.py https://example.com/article")
        print("\n推荐: 微信文章优先用 defuddle.md")
        sys.exit(1)
    
    url = sys.argv[1]
    content = smart_fetch(url)
    
    if content:
        print("\n" + "="*80)
        print(content[:3000] + "\n...\n[内容已截断，全文获取成功]" if len(content) > 3000 else content)
    else:
        print("\n[!] 所有方法都失败了")
