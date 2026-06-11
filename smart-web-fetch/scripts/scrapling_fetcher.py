#!/usr/bin/env python3
"""
Scrapling 网页内容获取脚本
最后手段，当所有 markdown 转换服务都失败时使用
"""

import sys
import asyncio
from scrapling import StealthDriver

async def fetch_with_scrapling(url, output_file=None):
    """
    使用 Scrapling 获取网页内容
    
    Args:
        url: 目标网址
        output_file: 可选，保存内容到文件
    
    Returns:
        网页内容文本
    """
    print(f"[*] 使用 Scrapling 获取: {url}")
    
    try:
        async with StealthDriver() as driver:
            response = await driver.get(url, wait_selector=None)
            
            if response.status != 200:
                print(f"[!] 状态码: {response.status}")
            
            content = response.text
            
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"[+] 内容已保存到: {output_file}")
            
            return content
            
    except Exception as e:
        print(f"[!] Scrapling 错误: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用: python scrapling_fetcher.py <url> [output_file]")
        sys.exit(1)
    
    url = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    content = asyncio.run(fetch_with_scrapling(url, output_file))
    
    if content:
        print("\n" + "="*80)
        print(content[:2000] + "..." if len(content) > 2000 else content)
    else:
        print("[!] 获取失败")
