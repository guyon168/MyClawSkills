# MyClawSkills 🐾

WorkBuddy 技能（Skills）合集 — 一键安装，开箱即用。

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

## 🚀 安装技能到 WorkBuddy

### 方式一：克隆整个仓库（推荐）

```bash
git clone https://github.com/guyon168/MyClawSkills.git
```

将对应的 skill 目录复制到 WorkBuddy 的 skills 目录：

```bash
# 用户级安装（所有项目可用）
cp -r binance-token-analysis ~/.workbuddy/skills/
cp -r smart-web-fetch ~/.workbuddy/skills/

# 或 项目级安装（仅当前项目可用）
cp -r binance-token-analysis <你的项目>/.workbuddy/skills/
cp -r smart-web-fetch <你的项目>/.workbuddy/skills/
```

### 方式二：单独安装某个技能

只需将对应文件夹（含 `SKILL.md`）放入 skills 目录即可：

| 技能 | 目录 |
|------|------|
| Binance Token Analysis | `binance-token-analysis/` |
| Smart Web Fetch | `smart-web-fetch/` |

### 验证安装

在 WorkBuddy 中输入 `/skills` 或查看技能列表，确认已加载。

---

## 📋 环境要求

- Python 3.8+
- `requests` 库（Smart Web Fetch 依赖）

## License

MIT
