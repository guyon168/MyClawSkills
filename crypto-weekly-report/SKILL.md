---
name: crypto-weekly-workbuddy
description: 使用项目内 Python 只抓取真实加密市场、新闻和宏观日历数据，并由当前 WorkBuddy 对话模型基于可审计 JSON 生成加密市场周度分析。
agent_created: true
---

# Crypto Weekly WorkBuddy Skill

## 触发场景

当用户提出以下意图时使用本 Skill：

- “运行加密周报”
- “生成周报”
- “用 WorkBuddy LLM 生成周报”
- “不要用外部 LLM”
- “只抓取真实数据，由当前对话模型写周报”
- “新闻和宏观日历必须真实抓取”

## 工作流

1. 在包含 `crypto_bot/main.py` 的项目根目录下运行数据导出脚本：

   ```bash
   python .workbuddy/skills/crypto-weekly-workbuddy/scripts/export_weekly_data.py
   ```

   如将本 Skill 安装在其他目录，请保持脚本相对路径不变，或从任意位置直接传入脚本路径运行。脚本会在运行时向上查找包含 `crypto_bot/main.py` 的项目根目录。

2. 脚本只执行项目现有真实数据采集逻辑，不调用外部大模型。
3. 读取导出的结构化数据文件：`crypto_bot/output/weekly_data_current.json`。
4. 生成周报前必须检查数据中的：
   - `source_status.news`：逐个新闻源的 `status/count/url/fetched_at/error`。
   - `source_status.macro`：逐个宏观日历源的 `status/count/url/fetched_at/error`。
   - `errors`：所有失败源或步骤错误。
   - `calendar`：只允许使用真实抓取事件；如果为空，需要在周报中透明说明宏观日历源抓取失败或无可解析事件。
5. 由当前 WorkBuddy 对话模型生成完整 Markdown 周报，必须包含 6 大板块：
   - `### 一、本周行情回顾 + 结构判断`
   - `### 二、本周热点复盘（3条主线）`
   - `### 三、下周展望 + 宏观日历`
   - `### 四、下周操作策略`
   - `### 五、Twitter热议（情绪温度计）`
   - `### 六、下周行动清单`
6. 将生成的 Markdown 保存到项目根目录，可使用格式化周报文件名。
7. 保存后运行验证脚本，确认 6 个章节标题均存在且每章标题后都有非空正文：

   ```bash
   python .workbuddy/skills/crypto-weekly-workbuddy/scripts/validate_report.py "weekly-report.md"
   ```

## 数据真实性要求

- 禁止模拟数据、编造数据或用示例数据替代真实抓取结果。
- 新闻必须来自真实 RSS/API/网页抓取；中文源只有真实解析成功才纳入 `news`。
- 宏观日历必须来自真实 RSS/API/网页抓取；禁止使用 FOMC/CPI/非农等规律推算作为 `calendar` 数据。
- 如果宏观真实抓取失败，`calendar` 必须为空或只保留已明确标注 `source/url/fetched_at` 的真实抓取事件，并在 `errors` 或 `source_status.macro` 中记录失败原因。
- 周报正文分析只能基于导出的结构化数据文件中的真实抓取数据。
- 如果某个数据源为空或抓取失败，必须在对应板块透明说明，例如：新闻源为空、宏观日历源失败、KOL 推文为空、ETF 数据不可用等。
- 不得在 Python 脚本中调用 WorkBuddy 模型或任何外部 LLM；Python 只负责真实数据导出和报告结构验证。

## 输出文件

- Raw data JSON：`crypto_bot/output/weekly_data_current.json`
- 最终周报：项目根目录下的 Markdown 文件
