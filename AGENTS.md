# AGENTS.md

## Quick Start
```bash
cd scripts
source ../venv/bin/activate
python fund_report_generator.py -p <池名称>    # 生成单个组合报告
python fund_report_generator.py                 # 生成所有组合汇总报告
python fund_report_generator.py -f markdown    # 生成 Markdown 格式报告
```

## Directory Structure
- `scripts/` - 所有 Python 脚本入口
- `scripts/fund_pools.json` - 基金池配置（修改后自动保存）
- `venv/` - Python 虚拟环境（必须激活）

## Key Commands
```bash
# 基金池管理
python fund_pool_manager.py list                 # 列出所有组合
python fund_pool_manager.py show <池名称>        # 查看组合详情
python fund_pool_manager.py add <池名称> <基金代码>  # 添加基金

# 单基金查询
python query_fund.py <基金代码> --save --output <文件>
```

## Important Notes
- **必须激活虚拟环境**：`source ../venv/bin/activate`（否则缺少 akshare 等依赖）
- 数据源：AKShare API，网络不稳定时会失败
- 报告输出：`fund_analysis_report.html` 或 `fund_analysis_report.md`
- 基金池更新：超过1天未更新会自动刷新

## 技术细节
- JSON数据结构：`昨日涨跌幅`/`今日涨跌幅` 是嵌套对象 `{"value": "+0.28%", "date": "04-08"}`
- 并行查询：最多3个线程同时查询
- 报告模板：`scripts/assets/report_template.html`
- Markdown模板：`scripts/assets/report_template.md`

## Git 提交规则
- 提交前必须先展示修改摘要并询问用户确认
- 得到明确回复后再执行 git add / commit / push