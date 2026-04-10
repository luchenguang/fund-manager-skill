#!/usr/bin/env python3
"""
基金报告生成主脚本

功能：
1. 从基金池获取基金代码
2. 批量查询基金信息
3. 生成综合报告
"""

import json
import os
import subprocess
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 获取脚本所在目录，确保能找到fund_pools.json和query_fund.py
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# 确定使用的 Python 解释器（优先使用虚拟环境）
venv_python = os.path.join(script_dir, "..", "venv", "bin", "python3")
if os.path.exists(venv_python):
    PYTHON_BIN = venv_python
    logger.debug(f"使用虚拟环境 Python: {PYTHON_BIN}")
else:
    PYTHON_BIN = sys.executable
    logger.warning(f"未找到虚拟环境，使用系统 Python: {PYTHON_BIN}")

class FundReportGenerator:
    """基金报告生成器"""

    def __init__(self):
        self.fund_pool_manager = None
        self.query_fund_script = "query_fund.py"
        self.report_template = "assets/report_template.html"
        self.tmp_dir = "tmp"

        # 确保临时目录存在（仅在需要时创建）
        if not os.path.exists(self.tmp_dir):
            os.makedirs(self.tmp_dir)
            logger.debug(f"创建临时目录: {self.tmp_dir}")

        # 初始化基金池管理器
        try:
            from fund_pool_manager import FundPoolManager
            self.fund_pool_manager = FundPoolManager()
            logger.info("基金池管理器初始化成功")
        except ImportError as e:
            logger.error(f"导入基金池管理器失败: {e}")
            sys.exit(1)

    def get_fund_codes_from_pool(self, pool_name: str = "我的基金池") -> List[str]:
        """从基金池获取基金代码列表"""
        if not self.fund_pool_manager:
            logger.error("基金池管理器未初始化")
            return []

        if pool_name not in self.fund_pool_manager.pools:
            logger.error(f"基金池 '{pool_name}' 不存在")
            return []

        fund_codes = self.fund_pool_manager.get_all_fund_codes(pool_name)
        logger.info(f"从基金池 '{pool_name}' 获取到 {len(fund_codes)} 个基金代码: {fund_codes}")
        return fund_codes

    def get_fund_info_from_pool(self, pool_name: str, fund_code: str) -> Dict:
        """从基金池获取基金的静态信息"""
        if not self.fund_pool_manager:
            return {}
        return self.fund_pool_manager.get_fund_info(pool_name, fund_code) or {}

    def update_fund_info_in_pool(self, pool_name: str, fund_code: str, fund_info: Dict) -> bool:
        """更新基金池中的基金静态信息"""
        if not self.fund_pool_manager:
            return False
        return self.fund_pool_manager.update_fund_info(pool_name, fund_code, fund_info)

    def query_fund_data(self, fund_code: str, cached_info: Dict = None, pool_name: str = None) -> Dict:
        """调用query_fund.py查询基金数据
        Args:
            fund_code: 基金代码
            cached_info: 从基金池缓存的静态信息
            pool_name: 基金池名称（用于更新缓存）
        """
        try:
            logger.info(f"开始查询基金 {fund_code}...")

            # 构建命令，指定输出到临时目录
            output_file = os.path.join(self.tmp_dir, f"fund_{fund_code}_data.json")
            cmd = [PYTHON_BIN, self.query_fund_script, fund_code, "--save", "--output", output_file]
            
            # 添加缓存参数
            if cached_info:
                if cached_info.get('name'):
                    cmd.extend(["--cached-name", cached_info['name']])
                if cached_info.get('type'):
                    cmd.extend(["--cached-type", cached_info['type']])
                if cached_info.get('company'):
                    cmd.extend(["--cached-company", cached_info['company']])

            # 执行查询
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60  # 设置超时时间为60秒
            )

            if result.returncode != 0:
                logger.error(f"查询基金 {fund_code} 失败: {result.stderr}")
                return {"fund_code": fund_code, "status": "failed", "error": result.stderr}

            # 尝试从输出文件中读取数据
            if os.path.exists(output_file):
                with open(output_file, 'r', encoding='utf-8') as f:
                    fund_data = json.load(f)
                logger.info(f"成功获取基金 {fund_code} 数据")
                
                # 更新基金池的静态信息
                if pool_name and fund_data.get('_static_info'):
                    self.update_fund_info_in_pool(pool_name, fund_code, fund_data['_static_info'])
                    logger.debug(f"已更新基金 {fund_code} 的静态信息到基金池")
                
                return {"fund_code": fund_code, "status": "success", "data": fund_data}
            else:
                # 如果没有生成文件，尝试从标准输出解析
                logger.warning(f"未找到数据文件，尝试从输出解析: {result.stdout[:200]}...")
                return {"fund_code": fund_code, "status": "success", "data": {"raw_output": result.stdout}}

        except subprocess.TimeoutExpired:
            logger.error(f"查询基金 {fund_code} 超时")
            return {"fund_code": fund_code, "status": "timeout", "error": "查询超时"}
        except Exception as e:
            logger.error(f"查询基金 {fund_code} 时发生异常: {e}")
            return {"fund_code": fund_code, "status": "error", "error": str(e)}

    def batch_query_funds(self, fund_codes: List[str], fund_cached_info: Dict = None, pool_name: str = None) -> Dict:
        """批量查询多个基金（并行查询）
        Args:
            fund_codes: 基金代码列表
            fund_cached_info: 基金静态信息缓存 {code: {name, type, company}}
            pool_name: 基金池名称（用于更新静态信息）
        """
        if fund_cached_info is None:
            fund_cached_info = {}
            
        results = {
            "total_funds": len(fund_codes),
            "successful_funds": 0,
            "failed_funds": 0,
            "fund_details": {},
            "query_timestamp": datetime.now().isoformat()
        }

        logger.info(f"开始并行查询 {len(fund_codes)} 个基金...")

        # 使用线程池并行查询，最多同时3个线程
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_code = {
                executor.submit(self.query_fund_data, code, fund_cached_info.get(code), pool_name): code 
                for code in fund_codes
            }
            
            for future in as_completed(future_to_code):
                fund_code = future_to_code[future]
                try:
                    fund_result = future.result()
                    
                    if fund_result["status"] == "success":
                        results["successful_funds"] += 1
                        if "data" in fund_result:
                            results["fund_details"][fund_code] = fund_result["data"]
                    else:
                        results["failed_funds"] += 1
                        results["fund_details"][fund_code] = {"status": "failed", "error": fund_result.get("error", "未知错误")}
                except Exception as e:
                    results["failed_funds"] += 1
                    results["fund_details"][fund_code] = {"status": "error", "error": str(e)}
                    logger.error(f"查询基金 {fund_code} 时发生异常: {e}")

        logger.info(f"批量查询完成: 成功 {results['successful_funds']} 个, 失败 {results['failed_funds']} 个")
        return results

    def generate_portfolio_summary(self, fund_results: Dict) -> Dict:
        """生成投资组合摘要"""
        summary = {
            "total_funds": fund_results["total_funds"],
            "successful_funds": fund_results["successful_funds"],
            "portfolio_change": 0.0,
            "fund_performance": []
        }

        total_change = 0.0
        valid_funds = 0

        for fund_code, details in fund_results["fund_details"].items():
            if "current_info" in details and "日增长率" in details["current_info"]:
                change_rate = details["current_info"]["日增长率"]
                if change_rate:
                    try:
                        # 清理百分比符号并转换为浮点数
                        change_val = float(str(change_rate).replace('%', ''))
                        total_change += change_val
                        valid_funds += 1

                        summary["fund_performance"].append({
                            "fund_code": fund_code,
                            "change_percent": change_val,
                            "current_price": details["current_info"].get("单位净值"),
                            "fund_name": details.get("fund_name", "未知")
                        })
                    except (ValueError, TypeError):
                        logger.warning(f"无法解析基金 {fund_code} 的涨跌幅: {change_rate}")

        # 计算平均涨跌幅
        if valid_funds > 0:
            summary["portfolio_change"] = total_change / valid_funds

        # 按涨跌幅排序
        summary["fund_performance"].sort(key=lambda x: x["change_percent"], reverse=True)

        logger.info(f"投资组合摘要: 平均涨跌幅 {summary['portfolio_change']:+.2f}%")
        return summary

    def save_fund_data(self, fund_results: Dict, filename: str = None) -> str:
        """保存基金数据到JSON文件"""
        if filename is None:
            filename = "../fund_report_data.json"  # 保存到根目录

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(fund_results, f, ensure_ascii=False, indent=2)
            logger.info(f"基金数据已保存到 {filename}")
            return filename
        except Exception as e:
            logger.error(f"保存基金数据失败: {e}")
            return ""

    def load_report_generator(self):
        """加载报告生成器模块"""
        try:
            from generate_report import FundReportGenerator as ReportGenerator
            return ReportGenerator()
        except ImportError as e:
            logger.error(f"导入报告生成器失败: {e}")
            return None

    def generate_html_report(self, fund_results: Dict, output_file: str = None) -> str:
        """生成HTML格式的报告"""
        if output_file is None:
            output_file = "../fund_analysis_report.html"  # 保存到根目录

        # 加载报告生成器
        report_generator = self.load_report_generator()
        if not report_generator:
            logger.error("无法加载报告生成器，尝试使用模板生成基础报告")
            return self.generate_basic_html_report(fund_results, output_file)

        try:
            # 准备数据格式
            fund_data = {
                "total_funds": fund_results["total_funds"],
                "successful_funds": fund_results["successful_funds"],
                "portfolio_change": fund_results.get("portfolio_summary", {}).get("portfolio_change", 0),
                "fund_details": {}
            }

            # 整理基金详情
            for fund_code, details in fund_results["fund_details"].items():
                if "current_info" in details:
                    fund_data["fund_details"][fund_code] = {
                        "current_price": details["current_info"].get("单位净值", 0),
                        "change_percent": 0.0,
                        "change_amount": 0.0,
                        "volume": 0
                    }

                    # 解析涨跌幅
                    change_rate = details["current_info"].get("日增长率", "0%")
                    if change_rate:
                        try:
                            fund_data["fund_details"][fund_code]["change_percent"] = float(str(change_rate).replace('%', ''))
                        except (ValueError, TypeError):
                            pass

            # 生成报告
            html_content = report_generator.generate_html_report(
                fund_data=fund_data,
                performance_analysis={},
                optimization_suggestions=self.generate_suggestions(fund_results)
            )

            # 保存报告
            report_path = report_generator.save_report(html_content, output_file)
            logger.info(f"HTML报告已生成: {report_path}")
            return report_path

        except Exception as e:
            logger.error(f"生成HTML报告失败: {e}")
            return self.generate_basic_html_report(fund_results, output_file)

    def load_template(self) -> str:
        """从文件加载HTML模板"""
        template_path = os.path.join(script_dir, "assets", "report_template.html")
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"模板文件未找到: {template_path}")
            return ""

    def generate_basic_html_report(self, fund_results: Dict, output_file: str) -> str:
        """生成基础的HTML报告（当报告生成器不可用时）"""
        try:
            # 从文件加载模板
            template = self.load_template()
            if not template:
                logger.error("无法加载模板")
                return ""

            # 填充数据
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 基金详细信息内容
            fund_details_html = ""
            for fund_code, details in fund_results["fund_details"].items():
                if "current_info" in details:
                    fund_name = details.get("fund_name", "未知")
                    current_info = details["current_info"]
                    cumulative_returns = details.get("cumulative_returns", {})
                    max_drawdowns = details.get("max_drawdowns", {})

                    # 确定日增长率样式（优先使用今日涨跌幅，其次昨日涨跌幅）
                    today_data = current_info.get("今日涨跌幅") or {}
                    yesterday_data = current_info.get("昨日涨跌幅") or {}
                    
                    today_value = today_data.get('value') if isinstance(today_data, dict) else None
                    yesterday_value = yesterday_data.get('value') if isinstance(yesterday_data, dict) else None
                    
                    day_change_rate = today_value if today_value else (yesterday_value if yesterday_value else "--")
                    day_change_class = "neutral"
                    if day_change_rate and day_change_rate != "--":
                        try:
                            change_val = float(str(day_change_rate).replace('%', '').replace('+', ''))
                            if change_val > 0:
                                day_change_class = "positive"
                            elif change_val < 0:
                                day_change_class = "negative"
                            else:
                                day_change_rate = "--"
                        except:
                            day_change_rate = "--"
                    else:
                        day_change_rate = "--"

                    # 构建历史业绩表格（合并收益率和最大回撤）
                    period_order = ['近1月', '近3月', '近6月', '近1年', '近3年', '近5年', '今年以来', '成立以来']
                    history_table_html = ""
                    for period in period_order:
                        return_val = cumulative_returns.get(period)
                        drawdown_val = max_drawdowns.get(period)
                        
                        return_class = "positive" if return_val and return_val >= 0 else "negative"
                        return_str = f"{return_val:+.2f}%" if return_val is not None else "-"
                        drawdown_str = f"-{drawdown_val:.2f}%" if drawdown_val is not None else "-"
                        
                        history_table_html += f"""
                            <tr>
                                <td class="period">{period}</td>
                                <td class="{return_class}">{return_str}</td>
                                <td class="negative">{drawdown_str}</td>
                            </tr>
                        """

                    if not history_table_html:
                        history_table_html = '<tr><td colspan="3">暂无历史业绩数据</td></tr>'

                    # 构建基金详情HTML
                    fund_details_html += f"""
                        <div class="fund-card">
                            <div class="fund-header">
                                <h3>{fund_code} - {fund_name}</h3>
                                <span class="data-source">数据源: {details.get('data_source', '未知')}</span>
                            </div>

                            <div class="fund-basic-info">
                                <div class="info-grid">
                                    <div class="info-item">
                                        <span class="label">单位净值:</span>
                                        <span class="value">{current_info.get('单位净值', 'N/A')}</span>
                                    </div>
                                    <div class="info-item">
                                        <span class="label">日增长率:</span>
                                        <span class="{day_change_class}">{day_change_rate}</span>
                                    </div>
                                    <div class="info-item">
                                        <span class="label">净值日期:</span>
                                        <span class="value">{current_info.get('净值日期', 'N/A')}</span>
                                    </div>
                                </div>

                                <div class="status-info">
                                    <div class="status-item">
                                        <span class="label">申购状态:</span>
                                        <span class="status-badge open">{current_info.get('申购状态', '未知')}</span>
                                    </div>
                                    <div class="status-item">
                                        <span class="label">赎回状态:</span>
                                        <span class="status-badge open">{current_info.get('赎回状态', '未知')}</span>
                                    </div>
                                    <div class="status-item">
                                        <span class="label">手续费:</span>
                                        <span class="value">{current_info.get('手续费', '未知')}</span>
                                    </div>
                                </div>
                            </div>

                            <div class="history-table-container">
                                <h4>📈 历史业绩</h4>
                                <table class="history-table">
                                    <thead>
                                        <tr>
                                            <th>周期</th>
                                            <th>收益率</th>
                                            <th>最大回撤</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {history_table_html}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    """

            if not fund_details_html:
                fund_details_html = '<div class="no-funds">暂无有效基金数据</div>'

            # 替换模板中的占位符
            html_content = template.replace('<!-- 基金详情 -->', fund_details_html)

            # 构建基金组合列表HTML
            portfolio_funds_html = ""
            for fund_code, details in fund_results["fund_details"].items():
                if "current_info" in details:
                    fund_name = details.get("fund_name", fund_code)
                    # 读取嵌套的昨日/今日涨跌幅
                    yesterday_data = details["current_info"].get("昨日涨跌幅") or {}
                    today_data = details["current_info"].get("今日涨跌幅") or {}
                    
                    yesterday_value = yesterday_data.get('value') if isinstance(yesterday_data, dict) else None
                    yesterday_date = yesterday_data.get('date') if isinstance(yesterday_data, dict) else None
                    today_value = today_data.get('value') if isinstance(today_data, dict) else None
                    today_date = today_data.get('date') if isinstance(today_data, dict) else None
                    
                    # 判断今日涨跌幅样式
                    today_class = "neutral"
                    if today_value and today_value != "--":
                        try:
                            val = float(str(today_value).replace('%', '').replace('+', ''))
                            if val > 0:
                                today_class = "positive"
                            elif val < 0:
                                today_class = "negative"
                        except:
                            pass
                    
                    # 判断昨日涨跌幅样式
                    yesterday_class = "neutral"
                    if yesterday_value and yesterday_value != "--":
                        try:
                            val = float(str(yesterday_value).replace('%', '').replace('+', ''))
                            if val > 0:
                                yesterday_class = "positive"
                            elif val < 0:
                                yesterday_class = "negative"
                        except:
                            pass
                    
                    portfolio_funds_html += f"""
                        <tr>
                            <td class="fund-code">{fund_code}</td>
                            <td class="fund-name">{fund_name}</td>
                            <td class="{yesterday_class}">{yesterday_value if yesterday_value else '--'}</td>
                            <td class="{today_class}">{today_value if today_value else '--'}</td>
                        </tr>
                    """

            if not portfolio_funds_html:
                portfolio_funds_html = '<tr><td colspan="4">暂无数据</td></tr>'

            # 替换基金组合列表占位符
            html_content = html_content.replace('<!-- 基金组合列表 -->', portfolio_funds_html)

            # 从基金数据中获取日期来生成动态表头
            yesterday_date_in_data = None
            today_date_in_data = None
            
            for fund_code, details in fund_results["fund_details"].items():
                if "current_info" in details:
                    yesterday_data = details["current_info"].get("昨日涨跌幅") or {}
                    today_data = details["current_info"].get("今日涨跌幅") or {}
                    if isinstance(yesterday_data, dict):
                        yesterday_date_in_data = yesterday_data.get('date')
                    if isinstance(today_data, dict):
                        today_date_in_data = today_data.get('date')
                    break
            
            yesterday_str = yesterday_date_in_data or (datetime.now() - timedelta(days=1)).strftime("%m-%d")
            today_str = today_date_in_data or datetime.now().strftime("%m-%d")
            
            # 替换动态日期表头
            html_content = html_content.replace('<th>昨日涨跌幅 (04-07)</th>', f'<th>昨日涨跌幅 ({yesterday_str})</th>')
            html_content = html_content.replace('<th>今日涨跌幅 (04-08)</th>', f'<th>今日涨跌幅 ({today_str})</th>')

            # 计算并显示平均涨跌幅
            avg_change = 0.0
            valid_changes = 0
            for fund_code, details in fund_results["fund_details"].items():
                if "current_info" in details and "今日涨跌幅" in details["current_info"]:
                    change_rate = details["current_info"]["今日涨跌幅"]
                    if change_rate:
                        try:
                            change_val = float(str(change_rate).replace('%', '').replace('+', ''))
                            avg_change += change_val
                            valid_changes += 1
                        except:
                            pass

            if valid_changes > 0:
                avg_change = avg_change / valid_changes

            change_class = "positive" if avg_change >= 0 else "negative"
            html_content = html_content.replace('<span class="value" id="total-funds">--</span>', f'<span class="value" id="total-funds">{fund_results["total_funds"]}</span>')
            html_content = html_content.replace('<span class="value" id="successful-funds">--</span>', f'<span class="value" id="successful-funds">{fund_results["successful_funds"]}</span>')
            html_content = html_content.replace('<span class="value" id="portfolio-change">--</span>',
                f'<span class="value {change_class}" id="portfolio-change">{avg_change:+.2f}%</span>')
            
            # 替换日期到标题后面
            html_content = html_content.replace('<span id="report-date"></span>', f'<span id="report-date">{timestamp}</span>')
            html_content = html_content.replace('<span id="timestamp"></span>', f'<span id="timestamp">{timestamp}</span>')

            # 生成投资建议HTML
            suggestions = self.generate_suggestions(fund_results)
            suggestions_html = ""
            for suggestion in suggestions:
                suggestions_html += f'<div class="suggestion-item">{suggestion}</div>'

            if not suggestions_html:
                suggestions_html = '<div class="suggestion-item">💡 建议关注基金市场动态，做好风险管理</div>'

            html_content = html_content.replace('<div id="suggestions-container">', f'<div id="suggestions-container">{suggestions_html}')

            # 保存报告
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)

            logger.info(f"基础HTML报告已生成: {output_file}")
            return output_file

        except Exception as e:
            logger.error(f"生成基础HTML报告失败: {e}")
            return ""

    def generate_suggestions(self, fund_results: Dict) -> List[str]:
        """生成投资建议"""
        suggestions = []

        # 基于成功查询的基金数量给出建议
        successful = fund_results["successful_funds"]
        total = fund_results["total_funds"]

        if successful == 0:
            suggestions.append("⚠️ 无法获取任何基金数据，请检查基金代码是否正确")
        elif successful < total:
            suggestions.append(f"⚠️ 只有 {successful}/{total} 个基金数据获取成功，建议检查失败的基金代码")

        # 基于涨跌幅给出建议
        positive_count = 0
        negative_count = 0
        total_change = 0.0
        valid_changes = 0

        for fund_code, details in fund_results["fund_details"].items():
            if "current_info" in details and "日增长率" in details["current_info"]:
                change_rate = details["current_info"]["日增长率"]
                if change_rate:
                    try:
                        change_val = float(str(change_rate).replace('%', ''))
                        total_change += change_val
                        valid_changes += 1
                        if change_val > 0:
                            positive_count += 1
                        elif change_val < 0:
                            negative_count += 1
                    except:
                        pass

        avg_change = total_change / valid_changes if valid_changes > 0 else 0

        if avg_change >= 1.0:
            suggestions.append("🚀 投资组合表现强劲，平均涨幅超过1%，建议关注强势基金的持续表现")
        elif avg_change >= 0.5:
            suggestions.append("📈 投资组合表现良好，平均涨幅在0.5%以上，配置相对合理")
        elif avg_change > 0:
            suggestions.append("⚡ 投资组合小幅上涨，建议关注市场趋势和个股机会")
        elif avg_change > -0.5:
            suggestions.append("➡️ 投资组合相对稳定，小幅下跌在可接受范围内，建议保持耐心")
        else:
            suggestions.append("📉 投资组合跌幅较大，建议关注市场风险，考虑分散投资或调整配置")

        # 基于基金表现给出建议
        if positive_count > negative_count * 1.5:
            suggestions.append("🏆 大部分基金表现积极，当前投资组合配置较为合理，可考虑继续持有")
        elif negative_count > positive_count * 1.5:
            suggestions.append("⚠️ 较多基金出现下跌，建议关注市场整体风险，考虑适当减仓或调整持仓结构")
        else:
            suggestions.append("⚖️ 基金表现相对平衡，建议保持关注，适时进行结构性优化")

        # 基于累计收益率给出建议
        strong_performance_funds = 0
        for fund_code, details in fund_results["fund_details"].items():
            cumulative_returns = details.get("cumulative_returns", {})
            # 检查是否有多个时间段的累计收益率为正
            positive_returns = sum(1 for return_val in cumulative_returns.values() if return_val and return_val > 0)
            if positive_returns >= 5:  # 如果有5个以上时间段为正收益
                strong_performance_funds += 1

        if strong_performance_funds > 0:
            suggestions.append(f"📊 {strong_performance_funds}只基金长期表现良好，建议重点关注这些优质基金")
        else:
            suggestions.append("📊 基金长期表现有待观察，建议关注基本面和业绩持续性")

        # 通用建议
        suggestions.append("💡 建议定期跟踪基金表现，根据市场情况适时调整投资策略")
        suggestions.append("🔍 可进一步分析各基金的历史表现和风险指标，优化投资组合")
        suggestions.append("💰 建议根据个人风险承受能力，合理配置不同风险等级的基金产品")
        suggestions.append("⏰ 投资需要耐心，建议长期持有优质基金，避免频繁操作")

        return suggestions

    def cleanup_tmp_dir(self):
        """清理临时目录中的文件"""
        try:
            import glob
            tmp_files = glob.glob(os.path.join(self.tmp_dir, "fund_*_data.json"))
            for file in tmp_files:
                try:
                    os.remove(file)
                    logger.debug(f"已删除临时文件: {os.path.basename(file)}")
                except Exception as e:
                    logger.warning(f"无法删除临时文件 {file}: {e}")

            # 如果临时目录为空，则删除目录本身
            if os.path.exists(self.tmp_dir) and not os.listdir(self.tmp_dir):
                os.rmdir(self.tmp_dir)
                logger.debug(f"已删除空临时目录: {self.tmp_dir}")

        except Exception as e:
            logger.error(f"清理临时目录时出错: {e}")

    def check_and_refresh_pool(self, pool_name: str = "我的基金池") -> bool:
        """检查基金池是否需要更新，如果超过1天未更新则刷新
        
        Returns:
            bool: 是否进行了更新
        """
        if not self.fund_pool_manager or pool_name not in self.fund_pool_manager.pools:
            return False
        
        pool_data = self.fund_pool_manager.pools[pool_name]
        updated_at_str = pool_data.get("updated_at", "")
        
        if not updated_at_str:
            logger.warning(f"基金池 '{pool_name}' 无更新时间记录")
            return False
        
        try:
            updated_at = datetime.fromisoformat(updated_at_str)
            now = datetime.now()
            days_diff = (now - updated_at).total_seconds() / 86400
            
            if days_diff > 1:
                logger.info(f"基金池 '{pool_name}' 已超过1天未更新 (上次更新: {updated_at_str})，正在刷新...")
                from fund_pool_manager import FundPoolManager
                self.fund_pool_manager = FundPoolManager()
                logger.info(f"✅ 基金池已刷新，最新更新时间: {self.fund_pool_manager.pools[pool_name].get('updated_at', '未知')}")
                return True
            else:
                logger.info(f"基金池 '{pool_name}' 最近已更新 (更新时间: {updated_at_str})，无需刷新")
                return False
        except Exception as e:
            logger.warning(f"检查基金池更新时间失败: {e}")
            return False

    def run(self, pool_name: str = "我的基金池", output_dir: str = None):
        """运行完整的报告生成流程"""
        try:
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            logger.info("=" * 60)
            logger.info("开始生成基金分析报告")
            logger.info("=" * 60)

            # 0. 检查并可能刷新基金池
            refreshed = self.check_and_refresh_pool(pool_name)

            # 1. 获取基金代码
            fund_codes = self.get_fund_codes_from_pool(pool_name)
            if not fund_codes:
                logger.error("未获取到基金代码，退出")
                return False

            # 2. 获取基金池中的静态信息缓存
            fund_cached_info = {}
            for code in fund_codes:
                cached = self.get_fund_info_from_pool(pool_name, code)
                if cached:
                    # 提取静态信息（去除 code 字段）
                    static_info = {k: v for k, v in cached.items() if k != 'code'}
                    if static_info:
                        fund_cached_info[code] = static_info
                        logger.debug(f"基金 {code} 找到缓存静态信息: {static_info}")

            # 3. 批量查询基金数据（传入缓存信息）
            fund_results = self.batch_query_funds(fund_codes, fund_cached_info, pool_name)

            # 3. 生成投资组合摘要
            portfolio_summary = self.generate_portfolio_summary(fund_results)
            fund_results["portfolio_summary"] = portfolio_summary

            # 4. 保存原始数据
            if output_dir:
                data_file = os.path.join(output_dir, "fund_data.json")
            else:
                data_file = None

            self.save_fund_data(fund_results, data_file)

            # 5. 生成HTML报告
            if output_dir:
                report_file = os.path.join(output_dir, "fund_report.html")
            else:
                report_file = None

            report_path = self.generate_html_report(fund_results, report_file)

            if report_path:
                logger.info("=" * 60)
                logger.info(f"✅ 报告生成完成！")
                logger.info(f"📄 报告路径: {report_path}")
                logger.info("=" * 60)

                # 在终端显示摘要信息
                print("\n📊 投资组合表现摘要:")
                print(f"   总基金数: {fund_results['total_funds']}")
                print(f"   成功获取: {fund_results['successful_funds']}")
                print(f"   平均涨跌幅: {portfolio_summary['portfolio_change']:+.2f}%")

                if portfolio_summary['fund_performance']:
                    print("\n🏆 表现最佳基金:")
                    for i, fund in enumerate(portfolio_summary['fund_performance'][:3], 1):
                        print(f"   {i}. {fund['fund_code']} ({fund['fund_name']}): {fund['change_percent']:+.2f}%")

                return True
            else:
                logger.error("报告生成失败")
                return False
        finally:
            # 确保清理临时目录
            self.cleanup_tmp_dir()

    def run_all_pools(self, output_dir: str = None):
        """运行所有基金池，生成汇总报告"""
        try:
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            logger.info("=" * 60)
            logger.info("开始生成所有组合的汇总报告")
            logger.info("=" * 60)

            # 0. 获取所有组合列表
            all_pools = self.fund_pool_manager.pools
            if not all_pools:
                logger.error("未找到任何基金组合")
                return False

            logger.info(f"找到 {len(all_pools)} 个组合: {list(all_pools.keys())}")

            # 存储所有组合的数据
            all_results = {}

            # 1. 遍历每个组合获取数据
            for pool_name in all_pools.keys():
                logger.info(f"\n--- 处理组合: {pool_name} ---")

                # 检查并可能刷新基金池
                self.check_and_refresh_pool(pool_name)

                # 获取基金代码
                fund_codes = self.get_fund_codes_from_pool(pool_name)
                if not fund_codes:
                    logger.warning(f"组合 '{pool_name}' 无基金代码，跳过")
                    continue

                # 获取静态信息缓存
                fund_cached_info = {}
                for code in fund_codes:
                    cached = self.get_fund_info_from_pool(pool_name, code)
                    if cached:
                        static_info = {k: v for k, v in cached.items() if k != 'code'}
                        if static_info:
                            fund_cached_info[code] = static_info

                # 批量查询
                fund_results = self.batch_query_funds(fund_codes, fund_cached_info, pool_name)

                # 生成摘要
                portfolio_summary = self.generate_portfolio_summary(fund_results)
                fund_results["portfolio_summary"] = portfolio_summary

                # 保存原始数据
                if output_dir:
                    data_file = os.path.join(output_dir, f"fund_data_{pool_name}.json")
                else:
                    data_file = None
                self.save_fund_data(fund_results, data_file)

                # 存储结果
                all_results[pool_name] = {
                    "fund_results": fund_results,
                    "portfolio_summary": portfolio_summary,
                    "pool_description": all_pools[pool_name].get("description", "")
                }

            if not all_results:
                logger.error("没有任何组合数据")
                return False

            # 2. 生成汇总HTML报告
            if output_dir:
                report_file = os.path.join(output_dir, "fund_report.html")
            else:
                report_file = None

            report_path = self.generate_multi_pool_report(all_results, report_file)

            if report_path:
                logger.info("=" * 60)
                logger.info("✅ 汇总报告生成完成！")
                logger.info(f"📄 报告路径: {report_path}")
                logger.info("=" * 60)

                # 打印汇总摘要
                print("\n📊 各组合表现摘要:")
                for pool_name, data in all_results.items():
                    summary = data["portfolio_summary"]
                    print(f"   {pool_name}: {summary['successful_funds']}/{summary['total_funds']} 只, 平均 {summary['portfolio_change']:+.2f}%")

                return True
            else:
                logger.error("汇总报告生成失败")
                return False
        finally:
            self.cleanup_tmp_dir()

    def generate_multi_pool_report(self, all_results: Dict, output_file: str = None) -> str:
        """生成多组合汇总HTML报告（数据注入模板，UI逻辑在模板中处理）"""
        if output_file is None:
            output_file = "../fund_analysis_report.html"

        try:
            template = self.load_template()
            if not template:
                logger.error("无法加载模板")
                return ""

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 构建各组合的数据
            pools_data = {}
            for pool_name, data in all_results.items():
                fund_results = data["fund_results"]
                summary = data["portfolio_summary"]

                # 提取基金数据（扁平化结构供 JS 使用）
                funds_list = []
                for fund_code, details in fund_results["fund_details"].items():
                    if "current_info" in details:
                        funds_list.append({
                            "fund_code": fund_code,
                            "fund_name": details.get("fund_name", "未知"),
                            "data_source": details.get("data_source", "未知"),
                            "current_info": details.get("current_info", {}),
                            "cumulative_returns": details.get("cumulative_returns", {}),
                            "max_drawdowns": details.get("max_drawdowns", {})
                        })

                pools_data[pool_name] = {
                    "funds": funds_list,
                    "summary": {
                        "total_funds": summary["total_funds"],
                        "successful_funds": summary["successful_funds"],
                        "portfolio_change": summary["portfolio_change"]
                    }
                }

            # 替换模板中的占位符
            html_content = template

            # 替换日期
            html_content = html_content.replace('<span id="report-date"></span>', f'<span id="report-date">{timestamp}</span>')
            html_content = html_content.replace('<span id="timestamp"></span>', f'<span id="timestamp">{timestamp}</span>')

            # 注入多组合 JSON 数据
            pool_json = json.dumps(pools_data, ensure_ascii=False)
            html_content = html_content.replace(
                '<script type="application/json" id="pool-data"></script>',
                f'<script type="application/json" id="pool-data">{pool_json}</script>'
            )

            # 保存报告
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)

            logger.info(f"多组合汇总报告已生成: {output_file}")
            return output_file

        except Exception as e:
            logger.error(f"生成多组合汇总报告失败: {e}")
            return ""


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='基金报告生成工具')
    parser.add_argument('--pool', '-p', help='指定基金池名称 (默认生成所有组合的汇总报告)')
    parser.add_argument('--output', '-o', help='输出目录')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 创建报告生成器并运行
    generator = FundReportGenerator()
    
    if args.pool:
        # 指定单个组合
        success = generator.run(pool_name=args.pool, output_dir=args.output)
    else:
        # 默认生成所有组合的汇总报告
        success = generator.run_all_pools(output_dir=args.output)

    if success:
        print("\n✅ 基金分析报告生成成功！")
        sys.exit(0)
    else:
        print("\n❌ 基金分析报告生成失败！")
        sys.exit(1)


if __name__ == "__main__":
    main()