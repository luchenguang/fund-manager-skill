#!/usr/bin/env python3
"""
查询基金数据的完整脚本
使用akshare、curl_cffi等库获取基金数据
"""

import sys
import argparse
import json
from datetime import datetime

# 测试所有库是否都能正常导入
print("正在测试库导入...")
try:
    import akshare as ak
    print("✓ akshare 导入成功")
except ImportError as e:
    print(f"✗ akshare 导入失败: {e}")

try:
    from curl_cffi import requests
    print("✓ curl_cffi 导入成功")
except ImportError as e:
    print(f"✗ curl_cffi 导入失败: {e}")

try:
    import pandas as pd
    print("✓ pandas 导入成功")
except ImportError as e:
    print(f"✗ pandas 导入失败: {e}")

try:
    import pycurl
    print("✓ pycurl 导入成功")
except ImportError as e:
    print(f"✗ pycurl 导入失败: {e}")

print("\n" + "="*50 + "\n")

def safe_float_convert(value):
    """安全地转换为float，处理空字符串等异常情况"""
    try:
        if pd.isna(value) or value == '' or value is None:
            return None
        return float(value)
    except (ValueError, TypeError):
        return None

def fetch_fund_data(fund_code, cached_info: dict = None):
    """获取指定基金的详细信息
    Args:
        fund_code: 基金代码
        cached_info: 从基金池缓存的静态信息（可选）
    """
    try:
        print(f"🚀 开始获取基金{fund_code}数据...")

        # 使用 fund_open_fund_info_em 获取净值数据（比 fund_open_fund_daily_em 更高效）
        # 获取单位净值走势
        nav_df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
        
        if nav_df is None or nav_df.empty:
            print(f"❌ 未找到基金{fund_code}的净值数据")
            return None

        # 获取最新数据
        latest_nav = nav_df.iloc[-1]
        nav_date = latest_nav['净值日期']
        current_nav = safe_float_convert(latest_nav['单位净值'])
        daily_growth = safe_float_convert(latest_nav.get('日增长率'))

        print(f"✅ 找到基金{fund_code}数据，最新净值日期: {nav_date}")

        # 获取昨日和今日涨跌幅（复用latest_nav和nav_date）
        is_today = str(nav_date) == datetime.now().strftime("%Y-%m-%d")
        yesterday_idx = -2 if is_today else -1
        yesterday_data = nav_df.iloc[yesterday_idx]
        yesterday_change = safe_float_convert(yesterday_data.get('日增长率'))
        yesterday_date = yesterday_data.get('净值日期')
        today_change = safe_float_convert(latest_nav.get('日增长率')) if is_today else None
        
        # 构建嵌套结构
        yesterday_str = f"{yesterday_change:+.2f}%" if yesterday_change is not None else None
        today_str = f"{today_change:+.2f}%" if today_change is not None else None
        yesterday_date_str = str(yesterday_date)[5:] if yesterday_date else None
        today_date_str = str(nav_date)[5:] if is_today and nav_date else None
        
        print(f"   昨日涨跌幅: {yesterday_str}, 今日涨跌幅: {today_str or '--'}")

        # 初始静态信息（可能被缓存或 API 覆盖）
        static_info = {}
        fund_name = ''
        fund_type = None
        fund_company = None

        # 使用缓存的静态信息（如果存在）
        if cached_info:
            fund_name = cached_info.get('name', '')
            fund_type = cached_info.get('type')
            fund_company = cached_info.get('company')

        fund_data = {
            'fund_code': fund_code,
            'fund_name': fund_name,
            'data_source': 'akshare',
            'fetch_timestamp': datetime.now().isoformat(),
            'current_info': {
                '单位净值': current_nav,
                '日增长率': f"{daily_growth:+.2f}%" if daily_growth is not None else None,
                '昨日涨跌幅': {'value': yesterday_str, 'date': yesterday_date_str},
                '今日涨跌幅': {'value': today_str, 'date': today_date_str} if today_str else {'value': None, 'date': None},
                '净值日期': str(nav_date),
                '申购状态': '开放申购',
                '赎回状态': '开放赎回',
                '手续费': None,
                '基金类型': fund_type,
                '基金公司': fund_company,
            },
            'cumulative_returns': {},
            'max_drawdowns': {}
        }

        # 获取各时间段的累计收益率和最大回撤（使用统一接口 fund_individual_achievement_xq）
        try:
            achievement_data = ak.fund_individual_achievement_xq(symbol=fund_code)
            if achievement_data is not None and not achievement_data.empty:
                for _, row in achievement_data.iterrows():
                    period = row.get('周期')
                    if period:
                        return_val = safe_float_convert(row.get('本产品区间收益'))
                        if return_val is not None:
                            fund_data['cumulative_returns'][period] = return_val
                        
                        max_drawdown = safe_float_convert(row.get('本产品最大回撒'))
                        if max_drawdown is not None:
                            fund_data['max_drawdowns'][period] = max_drawdown
        except Exception:
            pass

        # 获取基金静态信息：优先使用缓存，否则从 API 获取
        static_info = {}
        if not cached_info:
            # 没有缓存，从 API 获取
            try:
                fund_info_df = ak.fund_individual_basic_info_xq(symbol=fund_code)
                if fund_info_df is not None and not fund_info_df.empty:
                    for _, row in fund_info_df.iterrows():
                        if row['item'] == '基金名称':
                            fund_data['fund_name'] = row['value']
                            static_info['name'] = row['value']
                        elif row['item'] == '基金公司':
                            fund_data['current_info']['基金公司'] = row['value']
                            static_info['company'] = row['value']
                        elif row['item'] == '基金类型':
                            fund_data['current_info']['基金类型'] = row['value']
                            static_info['type'] = row['value']
            except Exception:
                pass
        
        # 标记需要更新的静态信息（供调用方保存到基金池）
        fund_data['_static_info'] = static_info

        # 如果无法获取基金名称，使用代码
        if not fund_data['fund_name']:
            fund_data['fund_name'] = f"基金{fund_code}"

        return fund_data
    except Exception as e:
        print(f"获取基金数据时出错: {e}")
        return None

def save_to_json(data, filename):
    """保存数据到JSON文件"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 数据已保存到 {filename}")
        return True
    except Exception as e:
        print(f"❌ 保存数据失败: {e}")
        return False

def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='查询基金数据')
    parser.add_argument('fund_code', help='基金代码（必填）')
    parser.add_argument('--save', action='store_true', help='将数据保存到文件')
    parser.add_argument('--output', '-o', help='指定输出文件路径')
    parser.add_argument('--cached-name', help='缓存的基金名称')
    parser.add_argument('--cached-type', help='缓存的基金类型')
    parser.add_argument('--cached-company', help='缓存的基金公司')
    args = parser.parse_args()

    fund_code = args.fund_code
    save_to_file = args.save
    if args.output:
        output_file = args.output
    else:
        output_file = f'fund_{fund_code}_data.json'

    # 构建缓存信息
    cached_info = {}
    if args.cached_name:
        cached_info['name'] = args.cached_name
    if args.cached_type:
        cached_info['type'] = args.cached_type
    if args.cached_company:
        cached_info['company'] = args.cached_company

    print("=" * 60)
    print(f"基金{fund_code}数据查询工具")
    print("=" * 60)
    print()

    # 获取数据
    fund_data = fetch_fund_data(fund_code, cached_info)

    if fund_data:
        # 显示关键信息
        print("\n📈 基金基本信息:")
        print(f"   基金代码: {fund_data['fund_code']}")
        print(f"   基金名称: {fund_data['fund_name']}")
        print(f"   单位净值: {fund_data['current_info']['单位净值']}")
        print(f"   昨日涨跌幅: {fund_data['current_info'].get('昨日涨跌幅', 'N/A')}")
        print(f"   今日涨跌幅: {fund_data['current_info'].get('今日涨跌幅', 'N/A')}")
        print(f"   净值日期: {fund_data['current_info'].get('净值日期', 'N/A')}")
        print(f"   申购状态: {fund_data['current_info'].get('申购状态', 'N/A')}")
        print(f"   赎回状态: {fund_data['current_info'].get('赎回状态', 'N/A')}")

        # 显示最大回撤（提升到与基金基本信息平级）
        if 'max_drawdowns' in fund_data and fund_data['max_drawdowns']:
            print(f"\n📊 最大回撤:")
            for period, drawdown in fund_data['max_drawdowns'].items():
                if drawdown is not None:
                    print(f"   {period}: {drawdown:.2f}%")

        # 显示累计收益率
        if fund_data['cumulative_returns']:
            print(f"\n📊 累计收益率:")
            for period, return_val in fund_data['cumulative_returns'].items():
                if return_val is not None:
                    print(f"   {period}: {return_val:.2f}%")

        # 保存数据（除非指定了--no-save）
        if save_to_file:
            success = save_to_json(fund_data, output_file)
            if success:
                print("\n✅ 查询完成！")
            else:
                print("\n⚠️  数据获取成功但保存失败")
        else:
            print("\n✅ 查询完成！（未使用--save参数，数据未保存到文件）")
    else:
        print(f"\n❌ 未能获取基金{fund_code}数据")
        sys.exit(1)

if __name__ == "__main__":
    main()