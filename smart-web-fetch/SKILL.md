---
name: smart-web-fetch
description: 智能网页内容获取技能，自动尝试多种 markdown 转换服务（markdown.new/, defuddle.md/, r.jina.ai/）来获取网页的 clean markdown 版本。当需要读取网页文章、新闻、文档等内容时使用此技能，支持微信文章、新闻网站等各种需要内容提取的场景。如果这些服务都失败，会尝试使用 Scrapling 爬虫工具。
---

# Smart Web Fetch

智能网页内容获取技能，优先使用 markdown 转换服务。

## 使用流程

1. 首先尝试 `markdown.new/` + URL
2. 失败则尝试 `defuddle.md/` + URL
3. 再失败尝试 `r.jina.ai/` + URL
4. 全部失败则提示用户

## 💡 微信文章专属

**推荐：微信文章直接用 defuddle.md，效果最好！**

| 服务 | 微信文章效果 |
|------|-------------|
| defuddle.md | ✅ 推荐首选 |
| markdown.new | ⚠️ 不稳定 |
| r.jina.ai | ❌ 通常被拦截 |

## 使用方法

**使用 web_fetch 工具：**

```python
# 按顺序尝试各服务
services = [
    "https://markdown.new/",
    "https://defuddle.md/",
    "https://r.jina.ai/"
]

for service in services:
    try:
        result = web_fetch(url=service + original_url)
        if result and len(result.get("text", "")) > 100:
            return result
    except:
        continue
```

**使用浏览器工具（遇到验证时）：**

```python
browser.open(url=original_url)
# 等待加载后 snapshot 获取内容
```

**使用 Scrapling（最后手段）：**

查看 `scripts/scrapling_fetcher.py` 脚本。

## 服务特点

- **markdown.new/**: 适合 Cloudflare 站点，转换质量高
- **defuddle.md/**: 通用性好，支持更多网站
- **r.jina.ai/**: Jina AI 提供，稳定可靠

## 安装依赖

### 快速安装
```bash
# 进入技能目录
cd /path/to/smart-web-fetch

# 安装 Python 依赖
pip install -r requirements.txt

# ✅ 完成！不需要下载浏览器！
```

### 依赖说明
| 依赖 | 用途 | 必须 |
|------|------|------|
| `requests` | HTTP 请求 | ✅ |

## ✅ 优势

- **不需要下载浏览器**（无 Playwright/Scrapling）
- 轻量快速
- 微信文章效果好（推荐 defuddle.md）

## 脚本说明

- `scripts/smart_fetcher.py` - 主脚本，按顺序尝试各服务
- `scripts/scrapling_fetcher.py` - ⚠️ 已废弃，不再使用（可删除）

