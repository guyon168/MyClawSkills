# MyClawSkills 🐾

AI Agent 技能（Skills）合集 — 独立的 Python 工具脚本，开箱即用。

## 📦 技能列表

### 1. Binance Token Analysis 🔍

Binance Alpha 代币与合约代币交叉分析工具，自动从 Binance 公开 API 获取实时数据，生成市值分布报告。

**功能亮点：**
- 自动抓取 Binance Alpha 代币列表和 Futures 合约交易对
- 交叉比对找出同时存在于两处的代币
- 按市值排序，输出 JSON / CSV / 终端摘要报告
- 提供市值分级统计（微型/小型/中型/大型/巨型）、涨跌分布、Top5 榜单

**使用方法：**
```bash
cd binance-token-analysis
python scripts/analyze.py
```

输出文件保存在 `data/` 目录下。

---

### 2. Smart Web Fetch 🌐

智能网页内容获取工具，自动按优先级尝试多种 Markdown 转换服务，将网页转为干净的 Markdown 文本。特别适合抓取微信文章、新闻网站等内容。

**功能亮点：**
- 三级降级策略：`markdown.new` → `defuddle.md` → `r.jina.ai`
- 轻量无依赖（仅需 `requests`），无需下载浏览器
- **微信文章推荐使用 `defuddle.md`，效果最佳**

**安装依赖：**
```bash
cd smart-web-fetch
pip install -r requirements.txt
```

**使用方法：**
```bash
python scripts/smart_fetcher.py <URL>
```
示例：
```bash
python scripts/smart_fetcher.py https://example.com/article
```

---

## 🚀 快速上手

### 克隆仓库

```bash
git clone https://github.com/guyon168/MyClawSkills.git
cd MyClawSkills
```

### 直接运行脚本

每个技能都是独立的 Python 脚本，进入对应目录即可运行：

| 技能 | 运行命令 |
|------|----------|
| Binance Token Analysis | `cd binance-token-analysis && python scripts/analyze.py` |
| Smart Web Fetch | `cd smart-web-fetch && python scripts/smart_fetcher.py <URL>` |

### 作为 AI Agent 技能集成

如果你在使用支持自定义 Skills 的 AI Agent 平台（如 Claude Code、Cline、Cursor 等），可将技能目录放入对应的 skills 目录下：

```
# 以 Claude Code 为例：
cp -r binance-token-analysis ~/.claude/commands/
cp -r smart-web-fetch ~/.claude/commands/

# 其他平台请参照各自文档的 skills/commands 配置方式
```

每个技能目录中的 `SKILL.md` 是技能描述文件，Agent 会根据它理解技能的用途和用法。

---

## 📋 环境要求

- Python 3.8+
- `requests` 库（Smart Web Fetch 依赖）

## License

MIT
