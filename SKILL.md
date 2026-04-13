---
name: fund-manager-skill
description: 管理基金资产组合，获取实时数据、分析表现并生成投资报告。
compatibility:
  - Bash
  - Read
  - Write
---

# 基金资产管理技能

## 功能

- 实时净值和涨跌幅查询
- 历史表现分析（收益率、最大回撤）
- HTML投资报告生成
- Markdown投资报告生成

## 文件结构

```
fund-manager-skill/
├── SKILL.md
├── scripts/
│   ├── query_fund.py        # 单只基金数据查询
│   ├── fund_pool_manager.py # 基金池管理
│   ├── fund_report_generator.py # 报告生成
│   ├── fund_pools.json      # 基金池配置
│   └── assets/
│       ├── report_template.html # HTML模板
│       └── report_template.md   # Markdown模板
├── fund_analysis_report.html # 生成的HTML报告
└── fund_analysis_report.md   # 生成的Markdown报告
```

## 基金池配置

基金池定义在 `scripts/fund_pools.json`：
```json
{
  "池名称": {
    "description": "说明",
    "funds": ["基金代码", ...]
  }
}
```

## 使用

### 生成报告
```bash
cd scripts
source ../venv/bin/activate
python fund_report_generator.py -p <池名称>    # 生成单个组合报告 (默认HTML)
python fund_report_generator.py                 # 生成所有组合汇总报告
python fund_report_generator.py -f markdown  # 生成Markdown格式报告
```

### 基金池管理
```bash
# 列出所有基金池
python scripts/fund_pool_manager.py list

# 查看指定基金池
python scripts/fund_pool_manager.py show <池名称>

# 添加基金到基金池
python scripts/fund_pool_manager.py add <池名称> <基金代码>
```

### 单基金查询
```bash
python scripts/query_fund.py <基金代码>
```

## 数据说明

### JSON数据结构
- `昨日涨跌幅`: `{"value": "+0.28%", "date": "04-08"}` - 嵌套结构包含值和日期
- `今日涨跌幅`: `{"value": "-0.61%", "date": "04-09"}` 或 `{"value": None, "date": None}`（未更新）

### 报告表头
- 昨日/今日列标题动态生成，基于实际数据的日期

## 技术

- 数据源：AKShare
- 虚拟环境：`venv/bin/activate`
- 运行前需激活虚拟环境