#!/usr/bin/env python3
"""
基金池管理功能
支持新建、删除基金池，添加、删除基金代码
数据以JSON形式存储
"""

import json
import os
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Union


class FundPoolManager:
    """基金池管理器"""

    def __init__(self, data_file: str = "fund_pools.json"):
        """初始化基金池管理器"""
        self.data_file = data_file
        self.pools = self._load_pools()

    def _load_pools(self) -> Dict:
        """从JSON文件加载基金池数据"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"✅ 已从 {self.data_file} 加载基金池数据")
                    return data
            else:
                print(f"📝 创建新的基金池数据文件: {self.data_file}")
                return {}
        except Exception as e:
            print(f"❌ 加载基金池数据失败: {e}")
            return {}

    def _save_pools(self) -> bool:
        """保存基金池数据到JSON文件"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.pools, f, ensure_ascii=False, indent=2)
            print(f"💾 基金池数据已保存到 {self.data_file}")
            return True
        except Exception as e:
            print(f"❌ 保存基金池数据失败: {e}")
            return False

    def _normalize_fund(self, fund: Union[str, Dict]) -> Dict:
        """标准化基金数据格式"""
        if isinstance(fund, str):
            return {"code": fund}
        return fund

    def create_pool(self, pool_name: str, description: str = "") -> bool:
        """新建基金池"""
        if pool_name in self.pools:
            print(f"❌ 基金池 '{pool_name}' 已存在")
            return False

        self.pools[pool_name] = {
            "description": description,
            "funds": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        print(f"✅ 已创建基金池 '{pool_name}'")
        if description:
            print(f"   描述: {description}")

        return self._save_pools()

    def delete_pool(self, pool_name: str) -> bool:
        """删除基金池"""
        if pool_name not in self.pools:
            print(f"❌ 基金池 '{pool_name}' 不存在")
            return False

        del self.pools[pool_name]
        print(f"✅ 已删除基金池 '{pool_name}'")
        return self._save_pools()

    def add_fund(self, pool_name: str, fund_code: str, fund_info: Dict = None) -> bool:
        """向基金池添加基金代码"""
        if pool_name not in self.pools:
            print(f"❌ 基金池 '{pool_name}' 不存在")
            return False

        # 检查是否已存在
        funds = self.pools[pool_name]["funds"]
        for fund in funds:
            fund_dict = self._normalize_fund(fund)
            if fund_dict["code"] == fund_code:
                print(f"⚠️  基金代码 '{fund_code}' 已在基金池 '{pool_name}' 中")
                return True

        # 添加基金（支持带静态信息）
        if fund_info:
            new_fund = {"code": fund_code, **fund_info}
        else:
            new_fund = {"code": fund_code}

        funds.append(new_fund)
        self.pools[pool_name]["updated_at"] = datetime.now().isoformat()

        print(f"✅ 已将基金代码 '{fund_code}' 添加到基金池 '{pool_name}'")
        return self._save_pools()

    def update_fund_info(self, pool_name: str, fund_code: str, fund_info: Dict) -> bool:
        """更新基金静态信息"""
        if pool_name not in self.pools:
            return False

        funds = self.pools[pool_name]["funds"]
        for i, fund in enumerate(funds):
            fund_dict = self._normalize_fund(fund)
            if fund_dict["code"] == fund_code:
                # 直接替换整个元素
                funds[i] = {"code": fund_code, **fund_info}
                self.pools[pool_name]["updated_at"] = datetime.now().isoformat()
                return self._save_pools()

        return False

    def get_fund_info(self, pool_name: str, fund_code: str) -> Optional[Dict]:
        """获取基金静态信息"""
        if pool_name not in self.pools:
            return None

        funds = self.pools[pool_name]["funds"]
        for fund in funds:
            fund_dict = self._normalize_fund(fund)
            if fund_dict["code"] == fund_code:
                return fund_dict

        return None

    def adjust_amount(self, pool_name: str, fund_code: str, amount: float, operation: str = "set") -> bool:
        """调整基金金额
        
        Args:
            pool_name: 基金池名称
            fund_code: 基金代码
            amount: 金额
            operation: 操作类型
                - "set": 设置为指定金额（覆盖）
                - "add": 加仓（增加金额）
                - "reduce": 减仓（减少金额）
        """
        if pool_name not in self.pools:
            print(f"❌ 基金池 '{pool_name}' 不存在")
            return False

        funds = self.pools[pool_name]["funds"]
        found = False
        
        for i, fund in enumerate(funds):
            fund_dict = self._normalize_fund(fund)
            if fund_dict["code"] == fund_code:
                found = True
                current_amount = fund_dict.get("amount", 0)
                
                if operation == "set":
                    new_amount = amount
                elif operation == "add":
                    new_amount = current_amount + amount
                elif operation == "reduce":
                    new_amount = current_amount - amount
                    if new_amount < 0:
                        print(f"❌ 减仓后金额不能为负: {new_amount}")
                        return False
                else:
                    print(f"❌ 未知的操作类型: {operation}")
                    return False
                
                funds[i]["amount"] = new_amount
                self.pools[pool_name]["updated_at"] = datetime.now().isoformat()
                
                op_names = {"set": "设置", "add": "加仓", "reduce": "减仓"}
                print(f"✅ {op_names.get(operation, operation)} {fund_code}: {current_amount:,.0f} -> {new_amount:,.0f} 元")
                return self._save_pools()
        
        if not found:
            print(f"❌ 基金代码 '{fund_code}' 不在基金池 '{pool_name}' 中")
            return False
        
        return False

    def get_all_fund_codes(self, pool_name: str) -> List[str]:
        """获取基金池中所有基金代码"""
        if pool_name not in self.pools:
            return []

        return [self._normalize_fund(f)["code"] for f in self.pools[pool_name]["funds"]]

    def remove_fund(self, pool_name: str, fund_code: str) -> bool:
        """从基金池中删除基金代码"""
        if pool_name not in self.pools:
            print(f"❌ 基金池 '{pool_name}' 不存在")
            return False

        funds = self.pools[pool_name]["funds"]
        new_funds = []
        found = False
        for fund in funds:
            fund_dict = self._normalize_fund(fund)
            if fund_dict["code"] == fund_code:
                found = True
            else:
                new_funds.append(fund)

        if not found:
            print(f"❌ 基金代码 '{fund_code}' 不在基金池 '{pool_name}' 中")
            return False

        self.pools[pool_name]["funds"] = new_funds
        self.pools[pool_name]["updated_at"] = datetime.now().isoformat()

        print(f"✅ 已将基金代码 '{fund_code}' 从基金池 '{pool_name}' 中删除")
        return self._save_pools()

    def list_pools(self) -> None:
        """列出所有基金池"""
        if not self.pools:
            print("📭 暂无基金池")
            return

        print("📋 基金池列表:")
        print("=" * 60)
        for pool_name, pool_data in self.pools.items():
            print(f"🏷️  {pool_name}")
            print(f"   描述: {pool_data.get('description', '无描述')}")
            print(f"   基金数量: {len(pool_data['funds'])}")
            print(f"   创建时间: {pool_data['created_at']}")
            print(f"   更新时间: {pool_data['updated_at']}")
            if pool_data['funds']:
                fund_list = []
                for f in pool_data['funds']:
                    fund_dict = self._normalize_fund(f)
                    name = fund_dict.get('name', '')
                    code = fund_dict['code']
                    if name:
                        fund_list.append(f"{code} ({name})")
                    else:
                        fund_list.append(code)
                print(f"   基金: {', '.join(fund_list)}")
            print()

    def show_pool(self, pool_name: str) -> None:
        """显示指定基金池的详细信息"""
        if pool_name not in self.pools:
            print(f"❌ 基金池 '{pool_name}' 不存在")
            return

        pool_data = self.pools[pool_name]
        print(f"📋 基金池 '{pool_name}' 详细信息:")
        print("=" * 60)
        print(f"描述: {pool_data.get('description', '无描述')}")
        print(f"基金数量: {len(pool_data['funds'])}")
        print(f"创建时间: {pool_data['created_at']}")
        print(f"更新时间: {pool_data['updated_at']}")

        if pool_data['funds']:
            print("\n📈 基金列表:")
            for i, fund in enumerate(pool_data['funds'], 1):
                fund_dict = self._normalize_fund(fund)
                code = fund_dict['code']
                name = fund_dict.get('name', '未知')
                info_parts = [name]
                if fund_dict.get('type'):
                    info_parts.append(fund_dict['type'])
                if fund_dict.get('company'):
                    info_parts.append(fund_dict['company'])
                print(f"   {i}. {code} - {' | '.join(info_parts)}")
        else:
            print("\n📭 该基金池暂无基金")


def main():
    """主函数 - 命令行界面"""
    parser = argparse.ArgumentParser(description='基金池管理工具')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # 创建基金池命令
    create_parser = subparsers.add_parser('create', help='创建新的基金池')
    create_parser.add_argument('pool_name', help='基金池名称')
    create_parser.add_argument('--description', '-d', default="", help='基金池描述')

    # 删除基金池命令
    delete_parser = subparsers.add_parser('delete', help='删除基金池')
    delete_parser.add_argument('pool_name', help='基金池名称')

    # 添加基金命令
    add_parser = subparsers.add_parser('add', help='向基金池添加基金')
    add_parser.add_argument('pool_name', help='基金池名称')
    add_parser.add_argument('fund_code', help='基金代码')

    # 删除基金命令
    remove_parser = subparsers.add_parser('remove', help='从基金池删除基金')
    remove_parser.add_argument('pool_name', help='基金池名称')
    remove_parser.add_argument('fund_code', help='基金代码')

    # 列出所有基金池命令
    list_parser = subparsers.add_parser('list', help='列出所有基金池')

    # 显示基金池详情命令
    show_parser = subparsers.add_parser('show', help='显示基金池详情')
    show_parser.add_argument('pool_name', help='基金池名称')

    # 调整金额命令
    adjust_parser = subparsers.add_parser('adjust', help='调整基金金额')
    adjust_parser.add_argument('pool_name', help='基金池名称')
    adjust_parser.add_argument('fund_code', help='基金代码')
    adjust_parser.add_argument('amount', type=float, help='金额')
    adjust_parser.add_argument('--operation', '-o', choices=['set', 'add', 'reduce'], default='set',
                           help='操作类型: set=设置金额, add=加仓, reduce=减仓 (默认: set)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 初始化基金池管理器
    manager = FundPoolManager()

    # 执行命令
    if args.command == 'create':
        manager.create_pool(args.pool_name, args.description)
    elif args.command == 'delete':
        manager.delete_pool(args.pool_name)
    elif args.command == 'add':
        manager.add_fund(args.pool_name, args.fund_code)
    elif args.command == 'remove':
        manager.remove_fund(args.pool_name, args.fund_code)
    elif args.command == 'list':
        manager.list_pools()
    elif args.command == 'show':
        manager.show_pool(args.pool_name)
    elif args.command == 'adjust':
        amount = args.amount
        if amount is None:
            print("❌ 请指定金额")
        else:
            manager.adjust_amount(args.pool_name, args.fund_code, args.amount, args.operation)


if __name__ == "__main__":
    main()
