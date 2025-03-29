# -*- coding: utf-8 -*-
import sys
from datetime import datetime
import os
from compare_stocks import analyze_stocks
from io import StringIO
import contextlib
import argparse
import yfinance as yf
import pandas as pd
import numpy as np
from Utils.param_utils import get_last_trading_day, validate_and_normalize_date

def read_stock_groups(filename):
    """读取股票分组列表"""
    groups = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # 按逗号分割股票代码
            stocks = [s.strip() for s in line.split(',') if s.strip()]
            if stocks:
                groups.append(stocks)
    return groups

def generate_report(groups, date=None, clear_cache=False):
    """为每个股票组生成分析报告"""
    analysis_date = date if date else datetime.now().strftime('%Y-%m-%d')
    
    # 确保输出目录存在
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, 'market_analysis')
    os.makedirs(output_dir, exist_ok=True)
    
    output_filename = os.path.join(output_dir, f"market_analysis_{analysis_date}.md")
    
    # 如果不清除缓存且报告已存在，直接返回
    if not clear_cache and os.path.exists(output_filename):
        print(f"使用缓存的报告: {output_filename}")
        # 打印报告内容
        with open(output_filename, 'r', encoding='utf-8') as f:
            print(f.read())
        return
    
    # 创建报告
    report = []
    report.append(f"# 市场分析报告 ({analysis_date})\n")
    
    # 分析每个组的股票
    fixed_group_names = ["指数ETF", "债券和黄金", "行业ETF"]
    
    # 收集所有自选股
    custom_stocks = []
    
    # 处理所有组
    for i, stocks in enumerate(groups):
        # 确定组名
        if i < len(fixed_group_names):
            group_name = fixed_group_names[i]
        else:
            group_name = f"自选股 (组{i-2})"  # 从第4组开始编号为1
            custom_stocks.extend(stocks)  # 收集自选股
        
        report.append(f"\n## {group_name}\n")
        
        # 运行分析并获取报告内容
        group_report = analyze_stocks(stocks, date, clear_cache)
        if group_report:
            report.extend(group_report.split('\n'))
        
        # 添加分隔线
        report.append("\n---\n")
    
    # 如果有自选股，添加自选股整体分析
    if custom_stocks:
        report.append("\n# 自选股整体分析\n")
        
        # 运行自选股分析并获取报告内容
        custom_report = analyze_stocks(custom_stocks, date, clear_cache)
        if custom_report:
            # 只保留市场整体分析部分
            report_lines = custom_report.split('\n')
            market_analysis_start = False
            for line in report_lines:
                if line.startswith('市场整体分析:'):
                    market_analysis_start = True
                    report.append(line)
                elif market_analysis_start:
                    report.append(line)
                    if line.startswith('市场综合判断:'):
                        break
    
    # 写入文件
    report_content = '\n'.join(report)
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(report_content)
    
    print(f"报告已生成: {output_filename}")
    # 打印报告内容
    print(report_content)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='股票组分析工具')
    parser.add_argument('args', nargs='*', help='日期参数（可选，支持YYYY-MM-DD、YYYY.MM.DD、YYYY/MM/DD、YYYYMMDD格式）')
    parser.add_argument('--clear', action='store_true', help='清除缓存数据')
    
    args = parser.parse_args()
    
    # 读取股票列表
    script_dir = os.path.dirname(os.path.abspath(__file__))
    stock_list_path = os.path.join(script_dir, 'Settings', 'stock_list.txt')
    
    try:
        # 验证并标准化日期参数
        normalized_date = validate_and_normalize_date(args.args) if args.args else None
        analysis_date = get_last_trading_day(normalized_date) if normalized_date else None
        
        if not analysis_date:
            analysis_date = get_last_trading_day()
            print(f"未指定日期，使用最近的交易日: {analysis_date}", file=sys.stderr)
        elif normalized_date and analysis_date != normalized_date:
            print(f"警告：目标日期 {normalized_date} 不是交易日，将使用最近的交易日 {analysis_date}", file=sys.stderr)

        # 分析股票组
        groups = read_stock_groups(stock_list_path)
        generate_report(groups, analysis_date, args.clear)
                
    except Exception as e:
        print(f"程序执行出错: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main() 