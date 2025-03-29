# -*- coding: utf-8 -*-
import sys
import io
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta
from tabulate import tabulate
import importlib.util
import subprocess
import re
import os
import argparse
from Utils.param_utils import validate_and_normalize_params
from Utils.stock_data_manager import StockDataManager
import traceback

# 定义当前版本号
CURRENT_VERSION = "1.0.0"

# 确保stdout和stderr使用UTF-8编码
if not isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if not isinstance(sys.stderr, io.TextIOWrapper):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def ensure_cache_dir(date_str: str) -> Path:
    """确保缓存目录存在"""
    # 使用脚本所在目录的相对路径
    script_dir = Path(__file__).parent
    cache_dir = script_dir / "cache" / date_str
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir

def save_to_cache(cache_dir, stock_code, content):
    """保存分析结果到缓存文件"""
    cache_file = cache_dir / f"{stock_code}.md"
    with open(cache_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"分析结果已保存到: {cache_file}", file=sys.stderr)

def import_script(script_name):
    """导入指定的分析脚本作为模块"""
    script_path = Path(__file__).parent / f"{script_name}.py"
    if not script_path.exists():
        raise ImportError(f"找不到脚本 {script_path}")
    
    spec = importlib.util.spec_from_file_location(script_name, script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def check_cache_version(cache_dir: Path, stock_code: str) -> bool:
    """检查缓存版本是否匹配"""
    cache_file = cache_dir / f"{stock_code}.md"
    if not cache_file.exists():
        return False
        
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            content = f.read()
            version_match = re.search(r'版本: ([\d.]+)', content)
            if version_match:
                cached_version = version_match.group(1)
                print(f"缓存版本: {cached_version}, 当前版本: {CURRENT_VERSION}", file=sys.stderr)
                return cached_version == CURRENT_VERSION
            else:
                print("缓存文件中未找到版本号", file=sys.stderr)
                return False
    except Exception as e:
        print(f"检查缓存版本时出错: {str(e)}", file=sys.stderr)
        return False

def run_analysis(script_name, stock_code, date=None, manager=None):
    """运行分析脚本并返回输出结果"""
    try:
        # 导入对应的分析模块
        module = import_script(script_name)
        
        # 获取分析函数
        analyze_func = getattr(module, 'analyze_stock')
        
        # 打印调试信息
        print(f"开始分析 {stock_code} 的 {script_name} 指标...", file=sys.stderr)
        print(f"分析日期: {date}", file=sys.stderr)
        
        # 调用分析函数
        if date:
            result = analyze_func(stock_code, date, manager)
        else:
            result = analyze_func(stock_code, manager)
            
        # 检查结果
        if not result:
            print(f"警告: {script_name} 分析未返回结果", file=sys.stderr)
            return ""
            
        return result
            
    except ImportError as e:
        print(f"导入 {script_name} 模块时出错: {str(e)}", file=sys.stderr)
        return ""
    except AttributeError as e:
        print(f"在 {script_name} 模块中未找到 analyze_stock 函数: {str(e)}", file=sys.stderr)
        return ""
    except Exception as e:
        print(f"运行 {script_name} 时发生异常: {str(e)}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return ""

def parse_demark_output(output):
    """解析Demark信号输出"""
    data = {
        'signals': [],
        'up_count_9': 0,
        'up_count_13': 0,
        'down_count_9': 0,
        'down_count_13': 0
    }
    
    try:
        # 解析计数
        up_count_9_match = re.search(r'上升9计数: (\d+)', output)
        up_count_13_match = re.search(r'上升13计数: (\d+)/4', output)
        down_count_9_match = re.search(r'下降9计数: (\d+)', output)
        down_count_13_match = re.search(r'下降13计数: (\d+)/4', output)
        
        if up_count_9_match:
            data['up_count_9'] = int(up_count_9_match.group(1))
            print(f"解析到上升9计数: {data['up_count_9']}", file=sys.stderr)
        if up_count_13_match:
            data['up_count_13'] = int(up_count_13_match.group(1))
            print(f"解析到上升13计数: {data['up_count_13']}", file=sys.stderr)
        if down_count_9_match:
            data['down_count_9'] = int(down_count_9_match.group(1))
            print(f"解析到下降9计数: {data['down_count_9']}", file=sys.stderr)
        if down_count_13_match:
            data['down_count_13'] = int(down_count_13_match.group(1))
            print(f"解析到下降13计数: {data['down_count_13']}", file=sys.stderr)
        
        # 解析信号
        if data['up_count_9'] == 9:
            data['signals'].append('上升Demark警告(9计数: 9/9)')
            print("检测到上升Demark警告", file=sys.stderr)
        if data['down_count_9'] == 9:
            data['signals'].append('下降Demark警告(9计数: 9/9)')
            print("检测到下降Demark警告", file=sys.stderr)
        if data['up_count_13'] == 4:
            data['signals'].append('上升Demark警告(13计数: 4/4)')
            print("检测到上升Demark警告(13计数)", file=sys.stderr)
        if data['down_count_13'] == 4:
            data['signals'].append('下降Demark警告(13计数: 4/4)')
            print("检测到下降Demark警告(13计数)", file=sys.stderr)
            
    except Exception as e:
        print(f"解析Demark输出时发生错误: {str(e)}", file=sys.stderr)
    
    return data

def parse_ma_output(output):
    """解析均线输出"""
    data = {
        'current_price': 0.0,
        'ma_data': {
            'MA20': {'price': 0.0, 'diff': 0.0},
            'MA50': {'price': 0.0, 'diff': 0.0},
            'MA120': {'price': 0.0, 'diff': 0.0},
            'MA200': {'price': 0.0, 'diff': 0.0}
        },
        'daily_change': 0.0,
        'volume_status': '正常',
        'volume_ratio': 0.0,
        'ma_trend': '混乱排列'
    }
    
    try:
        # 解析当前价格
        current_price_match = re.search(r'当前收盘价: \$?([\d.]+)', output)
        if current_price_match:
            data['current_price'] = float(current_price_match.group(1))
            print(f"解析到当前价格: {data['current_price']}", file=sys.stderr)
            
        # 解析均线数据
        ma_lines = re.findall(r'MA(\d+): \$?([\d.]+) \(价格(高于|低于)MA\d+ ([\d.]+)%\)', output)
        for ma_num, price, direction, diff_str in ma_lines:
            ma_name = f'MA{ma_num}'
            if price and float(price) > 0:
                diff = float(diff_str)
                diff = diff if direction == '高于' else -diff
                data['ma_data'][ma_name] = {
                    'price': float(price),
                    'diff': diff
                }
                print(f"解析到{ma_name}: 价格={float(price)}, 差距={diff}%", file=sys.stderr)
            
        # 解析日涨跌幅
        change_match = re.search(r'当日涨跌幅: ([+-]?[\d.]+)%', output)
        if change_match:
            data['daily_change'] = float(change_match.group(1))
            print(f"解析到日涨跌幅: {data['daily_change']}%", file=sys.stderr)
            
        # 解析成交量状态
        volume_ratio_match = re.search(r'成交量较20日均量: ([+-]?[\d.]+)%', output)
        if volume_ratio_match:
            data['volume_ratio'] = float(volume_ratio_match.group(1))
            if data['volume_ratio'] > 50:
                data['volume_status'] = '显著高于20日平均水平'
            elif data['volume_ratio'] > 20:
                data['volume_status'] = '高于20日平均水平'
            elif data['volume_ratio'] < -50:
                data['volume_status'] = '显著低于20日平均水平'
            elif data['volume_ratio'] < -20:
                data['volume_status'] = '低于20日平均水平'
            else:
                data['volume_status'] = '接近20日平均水平'
            print(f"解析到成交量状态: {data['volume_status']}", file=sys.stderr)
            
        # 解析均线趋势
        trend_match = re.search(r'均线排列: (.+?)(?=\n|$)', output)
        if trend_match:
            data['ma_trend'] = trend_match.group(1).strip()
            print(f"解析到均线趋势: {data['ma_trend']}", file=sys.stderr)
            
    except Exception as e:
        print(f"解析均线输出时发生错误: {str(e)}", file=sys.stderr)
        
    return data

def parse_kdj_output(output):
    """解析KDJ指标输出"""
    data = {
        'K': 0.0,
        'D': 0.0,
        'J': 0.0,
        'status': '正常',
        'divergence': None
    }
    
    # 解析KDJ值
    k_match = re.search(r'K值: ([\d.]+)', output)
    d_match = re.search(r'D值: ([\d.]+)', output)
    j_match = re.search(r'J值: ([\d.]+)', output)
    
    if k_match:
        data['K'] = float(k_match.group(1))
    if d_match:
        data['D'] = float(d_match.group(1))
    if j_match:
        data['J'] = float(j_match.group(1))
        
    # 判断状态
    if '处于严重超买区间' in output:
        data['status'] = '严重超买'
    elif '处于严重超卖区间' in output:
        data['status'] = '严重超卖'
    elif '处于超买区间' in output:
        data['status'] = '超买'
    elif '处于超卖区间' in output:
        data['status'] = '超卖'
    else:
        data['status'] = '正常'
        
    # 解析背离信息
    if '检测到顶背离' in output:
        data['divergence'] = '顶背离'
    elif '检测到底背离' in output:
        data['divergence'] = '底背离'
        
    return data

def parse_rsi_output(output):
    """解析RSI指标输出"""
    data = {
        'RSI6': None,
        'RSI12': None,
        'RSI24': None,
        'status': '正常',
        'divergence': None
    }
    
    try:
        # 解析RSI值
        rsi6_match = re.search(r'RSI\(6\): ([\d.]+)', output)
        rsi12_match = re.search(r'RSI\(12\): ([\d.]+)', output)
        rsi24_match = re.search(r'RSI\(24\): ([\d.]+)', output)
        
        if rsi6_match:
            data['RSI6'] = float(rsi6_match.group(1))
            print(f"解析到RSI(6): {data['RSI6']}", file=sys.stderr)
        if rsi12_match:
            data['RSI12'] = float(rsi12_match.group(1))
            print(f"解析到RSI(12): {data['RSI12']}", file=sys.stderr)
        if rsi24_match:
            data['RSI24'] = float(rsi24_match.group(1))
            print(f"解析到RSI(24): {data['RSI24']}", file=sys.stderr)
            
        # 判断状态
        if data['RSI6'] is not None and data['RSI12'] is not None and data['RSI24'] is not None:
            if data['RSI6'] > 95 or data['RSI12'] > 90 or data['RSI24'] > 85:
                data['status'] = '严重超买'
                print("检测到严重超买状态", file=sys.stderr)
            elif data['RSI6'] > 85 or data['RSI12'] > 80 or data['RSI24'] > 75:
                data['status'] = '超买'
                print("检测到超买状态", file=sys.stderr)
            elif data['RSI6'] < 5 or data['RSI12'] < 10 or data['RSI24'] < 15:
                data['status'] = '严重超卖'
                print("检测到严重超卖状态", file=sys.stderr)
            elif data['RSI6'] < 15 or data['RSI12'] < 20 or data['RSI24'] < 25:
                data['status'] = '超卖'
                print("检测到超卖状态", file=sys.stderr)
            else:
                data['status'] = '正常'
                print("检测到正常状态", file=sys.stderr)
                
        # 解析背离信息
        if '检测到顶背离' in output:
            data['divergence'] = '顶背离'
            print("检测到顶背离", file=sys.stderr)
        elif '检测到底背离' in output:
            data['divergence'] = '底背离'
            print("检测到底背离", file=sys.stderr)
            
    except Exception as e:
        print(f"解析RSI输出时发生错误: {str(e)}", file=sys.stderr)
        
    return data

def parse_bollinger_output(output):
    """解析布林带输出"""
    data = {
        'current_price': None,
        'middle_band': None,
        'upper_band': None,
        'lower_band': None,
        'position': None,
        'bandwidth': None,
        'bandwidth_trend': None,
        'breakthrough': None,
        'market_status': None
    }
    
    try:
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 解析价格信息
            if line.startswith('当前价格:'):
                match = re.search(r'\$?([\d.]+)', line)
                if match:
                    data['current_price'] = float(match.group(1))
                    print(f"解析到当前价格: {data['current_price']}", file=sys.stderr)
            elif line.startswith('中轨:'):
                match = re.search(r'\$?([\d.]+)', line)
                if match:
                    data['middle_band'] = float(match.group(1))
                    print(f"解析到中轨: {data['middle_band']}", file=sys.stderr)
            elif line.startswith('上轨:'):
                match = re.search(r'\$?([\d.]+)', line)
                if match:
                    data['upper_band'] = float(match.group(1))
                    print(f"解析到上轨: {data['upper_band']}", file=sys.stderr)
            elif line.startswith('下轨:'):
                match = re.search(r'\$?([\d.]+)', line)
                if match:
                    data['lower_band'] = float(match.group(1))
                    print(f"解析到下轨: {data['lower_band']}", file=sys.stderr)
            # 解析位置分析
            elif line.startswith('带内位置:'):
                match = re.search(r'([\d.]+)%', line)
                if match:
                    data['position'] = float(match.group(1))
                    print(f"解析到带内位置: {data['position']}%", file=sys.stderr)
            elif line.startswith('带宽:'):
                match = re.search(r'([\d.]+)%', line)
                if match:
                    data['bandwidth'] = float(match.group(1))
                    print(f"解析到带宽: {data['bandwidth']}%", file=sys.stderr)
            elif line.startswith('带宽趋势:'):
                parts = line.split(': ')
                if len(parts) > 1:
                    data['bandwidth_trend'] = parts[1]
                    print(f"解析到带宽趋势: {data['bandwidth_trend']}", file=sys.stderr)
            elif line.startswith('突破状态:'):
                parts = line.split(': ')
                if len(parts) > 1:
                    data['breakthrough'] = parts[1]
                    print(f"解析到突破状态: {data['breakthrough']}", file=sys.stderr)
            elif line.startswith('市场状态:'):
                parts = line.split(': ')
                if len(parts) > 1:
                    data['market_status'] = parts[1]
                    print(f"解析到市场状态: {data['market_status']}", file=sys.stderr)
    except Exception as e:
        print(f"解析布林带输出时发生错误: {str(e)}", file=sys.stderr)
    
    return data

def parse_psar_output(output):
    """解析PSAR指标输出"""
    data = {
        'current_price': 0.0,
        'psar': 0.0,
        'trend': '未知',
        'trend_days': 0,
        'trend_strength': '弱',
        'distance': 0.0,
        'trend_change': '无'
    }
    
    try:
        # 解析价格和PSAR值
        price_lines = re.findall(r'(当前价格|当前SAR): \$?([\d.]+)', output)
        for name, value in price_lines:
            if '当前价格' in name:
                data['current_price'] = float(value)
                print(f"解析到当前价格: {data['current_price']}", file=sys.stderr)
            elif '当前SAR' in name:
                data['psar'] = float(value)
                print(f"解析到SAR价格: {data['psar']}", file=sys.stderr)
        
        # 解析趋势信息
        trend_lines = output.split('\n')
        for line in trend_lines:
            if line.startswith('当前趋势:'):
                trend = line.split(':', 1)[1].strip()
                data['trend'] = trend
                print(f"解析到当前趋势: {data['trend']}", file=sys.stderr)
            elif line.startswith('趋势持续:'):
                days = re.search(r'(\d+)天', line)
                if days:
                    data['trend_days'] = int(days.group(1))
                    print(f"解析到趋势持续天数: {data['trend_days']}", file=sys.stderr)
            elif line.startswith('趋势强度:'):
                strength = line.split(':', 1)[1].strip()
                data['trend_strength'] = strength
                print(f"解析到趋势强度: {data['trend_strength']}", file=sys.stderr)
            elif line.startswith('趋势转换:'):
                change = line.split(':', 1)[1].strip()
                if change and change != '无':
                    data['trend_change'] = change
                    print(f"解析到趋势转换: {data['trend_change']}", file=sys.stderr)
                    
        # 计算价格与SAR的距离
        if data['current_price'] > 0 and data['psar'] > 0:
            data['distance'] = abs((data['current_price'] - data['psar']) / data['psar'] * 100)
            print(f"计算价格与SAR距离: {data['distance']:.2f}%", file=sys.stderr)
                    
    except Exception as e:
        print(f"解析PSAR输出时发生错误: {str(e)}", file=sys.stderr)
    
    return data

def check_cache_exists(cache_dir: Path, stock_code: str) -> bool:
    """检查缓存是否存在"""
    cache_file = cache_dir / f"{stock_code}.md"
    return cache_file.exists()

def analyze_single_stock(stock_code: str, date: str, clear_cache: bool = False) -> str:
    """
    分析单只股票
    
    参数:
    stock_code (str): 股票代码
    date (str): 分析日期，格式为YYYY-MM-DD
    clear_cache (bool): 是否清除缓存
    
    返回:
    str: 分析报告内容
    """
    try:
        print(f"开始分析股票: {stock_code}", file=sys.stderr)
        print(f"分析日期: {date}", file=sys.stderr)
        
        # 确保缓存目录存在
        cache_dir = ensure_cache_dir(date)
        print(f"缓存目录: {cache_dir}", file=sys.stderr)
        
        # 检查缓存是否存在且版本匹配
        if not clear_cache and check_cache_exists(cache_dir, stock_code) and check_cache_version(cache_dir, stock_code):
            print(f"使用缓存的分析结果: {cache_dir}/{stock_code}.md", file=sys.stderr)
            with open(cache_dir / f"{stock_code}.md", 'r', encoding='utf-8') as f:
                content = f.read()
                print(content)
                return content
        
        # 创建数据管理器实例
        manager = StockDataManager()
        print("已创建数据管理器实例", file=sys.stderr)
        
        # 运行各项分析
        print("\n开始运行各项技术指标分析...", file=sys.stderr)
        
        # Demark分析
        print("\n运行Demark分析...", file=sys.stderr)
        demark_output = run_analysis("check_demark", stock_code, date, manager)
        if not demark_output:
            print("警告: Demark分析未返回结果", file=sys.stderr)
            
        # 均线分析
        print("\n运行均线分析...", file=sys.stderr)
        ma_output = run_analysis("check_ma", stock_code, date, manager)
        if not ma_output:
            print("警告: 均线分析未返回结果", file=sys.stderr)
            
        # KDJ分析
        print("\n运行KDJ分析...", file=sys.stderr)
        kdj_output = run_analysis("check_kdj", stock_code, date, manager)
        if not kdj_output:
            print("警告: KDJ分析未返回结果", file=sys.stderr)
            
        # RSI分析
        print("\n运行RSI分析...", file=sys.stderr)
        rsi_output = run_analysis("check_rsi", stock_code, date, manager)
        if not rsi_output:
            print("警告: RSI分析未返回结果", file=sys.stderr)
            
        # 布林带分析
        print("\n运行布林带分析...", file=sys.stderr)
        bollinger_output = run_analysis("check_bollinger", stock_code, date, manager)
        if not bollinger_output:
            print("警告: 布林带分析未返回结果", file=sys.stderr)
            
        # PSAR分析
        print("\n运行PSAR分析...", file=sys.stderr)
        psar_output = run_analysis("check_psar", stock_code, date, manager)
        if not psar_output:
            print("警告: PSAR分析未返回结果", file=sys.stderr)

        # 解析各个指标的输出
        print("\n开始解析各项指标的输出...", file=sys.stderr)
        
        demark_data = parse_demark_output(demark_output)
        print("已解析Demark数据", file=sys.stderr)
        
        ma_data = parse_ma_output(ma_output)
        print("已解析均线数据", file=sys.stderr)
        
        kdj_data = parse_kdj_output(kdj_output)
        print("已解析KDJ数据", file=sys.stderr)
        
        rsi_data = parse_rsi_output(rsi_output)
        print("已解析RSI数据", file=sys.stderr)
        
        bollinger_data = parse_bollinger_output(bollinger_output)
        print("已解析布林带数据", file=sys.stderr)
        
        psar_data = parse_psar_output(psar_output)
        print("已解析PSAR数据", file=sys.stderr)

        # 生成报告
        print("\n开始生成分析报告...", file=sys.stderr)
        report = []
        report.append(f"版本: {CURRENT_VERSION}")
        report.append(f"股票代码: {stock_code}")
        report.append(f"分析日期: {date}")
        report.append("-" * 50)
        
        # 价格信息
        if bollinger_data and bollinger_data['current_price'] is not None:
            report.append(f"当前价格: ${bollinger_data['current_price']:.2f}")
            report.append(f"日涨跌幅: {ma_data['daily_change']:+.2f}%")
            report.append("")
        else:
            print("警告: 无法获取当前价格信息", file=sys.stderr)
        
        # 关键信号
        report.append("关键信号:")
        
        # PSAR信号
        if psar_data:
            if psar_data['trend_change'] != '无':
                report.append(f"- PSAR: [转换] {psar_data['trend_change']}")
            report.append(f"- PSAR: [{psar_data['trend']}趋势] {psar_data['trend_strength']}势 ({psar_data['trend_days']}天)")
        else:
            print("警告: 无法获取PSAR信号", file=sys.stderr)
        
        # Demark信号
        if demark_data and demark_data['signals']:
            report.append("- Demark:")
            for signal in demark_data['signals']:
                report.append(f"  - {signal}")
        else:
            print("警告: 无法获取Demark信号", file=sys.stderr)
        
        # 均线状态
        if ma_data:
            report.append(f"- 均线排列: [{ma_data['ma_trend']}]")
            
            # 各均线差距
            for ma_name, data in ma_data['ma_data'].items():
                diff = data['diff']
                if abs(diff) >= 1:  # 只显示差距超过1%的均线
                    direction = "高于" if diff > 0 else "低于"
                    report.append(f"- {ma_name}: [{direction}{ma_name}:{abs(diff):.2f}%] 价格{direction}{ma_name} {abs(diff):.2f}%")
        else:
            print("警告: 无法获取均线状态", file=sys.stderr)
        
        # 布林带信号
        if bollinger_data:
            if bollinger_data['breakthrough'] != '无':
                report.append(f"- 布林带: [突破] {bollinger_data['breakthrough']}")
            elif bollinger_data['market_status'] != '正常波动区间':
                report.append(f"- 布林带: [{bollinger_data['market_status']}]")
            if bollinger_data['bandwidth_trend'] != '正常':
                report.append(f"- 波动性: [{bollinger_data['bandwidth_trend']}]")
        else:
            print("警告: 无法获取布林带信号", file=sys.stderr)
        
        # KDJ信号
        if kdj_data:
            if kdj_data['status'] != '正常' or kdj_data['divergence']:
                status_text = []
                if kdj_data['status'] == '严重超买':
                    status_text.append('严重超买')
                elif kdj_data['status'] == '严重超卖':
                    status_text.append('严重超卖')
                elif kdj_data['status'] != '正常':
                    status_text.append(kdj_data['status'])
                if kdj_data['divergence']:
                    status_text.append(kdj_data['divergence'])
                report.append(f"- KDJ: [{', '.join(status_text)}]")
        else:
            print("警告: 无法获取KDJ信号", file=sys.stderr)
        
        # RSI信号
        if rsi_data:
            if rsi_data['status'] != '正常' or rsi_data['divergence']:
                status_text = []
                if rsi_data['status'] == '严重超买':
                    status_text.append('严重超买')
                elif rsi_data['status'] == '严重超卖':
                    status_text.append('严重超卖')
                elif rsi_data['status'] != '正常':
                    status_text.append(rsi_data['status'])
                if rsi_data['divergence']:
                    status_text.append(rsi_data['divergence'])
                report.append(f"- RSI: [{', '.join(status_text)}]")
        else:
            print("警告: 无法获取RSI信号", file=sys.stderr)
        
        # 成交量状态
        if ma_data and 'volume_status' in ma_data:
            volume_status = ma_data['volume_status']
            if '高于' in volume_status:
                report.append(f"- 成交量: [放量] {volume_status}")
            elif '低于' in volume_status:
                report.append(f"- 成交量: [缩量] {volume_status}")
        else:
            print("警告: 无法获取成交量状态", file=sys.stderr)
        
        report.append("")
        
        # 风险提示
        risks = []
        if kdj_data and rsi_data:
            if kdj_data['status'] == '严重超买' or rsi_data['status'] == '严重超买':
                risks.append("[严重警告] 多个指标显示严重超买，极有可能出现显著回调")
            elif kdj_data['status'] == '超买' or rsi_data['status'] == '超买':
                risks.append("[警告] 短期超买风险")
            if kdj_data['status'] == '严重超卖' or rsi_data['status'] == '严重超卖':
                risks.append("[重要机会] 多个指标显示严重超卖，极有可能出现显著反弹")
            elif kdj_data['status'] == '超卖' or rsi_data['status'] == '超卖':
                risks.append("[机会] 可能存在反弹机会")
            if kdj_data['divergence'] == '顶背离' or rsi_data['divergence'] == '顶背离':
                risks.append("[警告] 检测到顶背离信号，注意回调风险")
            if kdj_data['divergence'] == '底背离' or rsi_data['divergence'] == '底背离':
                risks.append("[机会] 检测到底背离信号，可能存在反弹机会")
            
        # 添加均线相关的风险提示
        if ma_data:
            if ma_data['ma_trend'] == '多头排列':
                risks.append("[强势] 均线呈多头排列，趋势向上")
            elif ma_data['ma_trend'] == '空头排列':
                risks.append("[弱势] 均线呈空头排列，趋势向下")
            elif ma_data['ma_trend'] == '均线纠缠':
                risks.append("[盘整] 均线交织，可能处于转折点")
            
        # 添加布林带相关的风险提示
        if bollinger_data:
            if bollinger_data['breakthrough'] == '向上突破':
                risks.append("[强势] 突破布林带上轨，注意回调风险")
            elif bollinger_data['breakthrough'] == '向下突破':
                risks.append("[弱势] 跌破布林带下轨，关注超卖反弹")
            elif bollinger_data['market_status'] == '超买区间' or bollinger_data['market_status'] == '接近超买':
                risks.append("[警告] 布林带显示超买风险")
            elif bollinger_data['market_status'] == '超卖区间' or bollinger_data['market_status'] == '接近超卖':
                risks.append("[机会] 布林带显示超卖机会")
        
        if risks:
            report.append("风险提示:")
            for risk in risks:
                report.append(f"  {risk}")
            report.append("")
        
        # 技术指标摘要
        report.append("技术指标摘要:")
        
        # PSAR指标（放在第一位）
        if psar_data:
            report.append(f"1. PSAR指标:")
            report.append(f"   - 当前趋势: {psar_data['trend']}")
            report.append(f"   - 趋势持续: {psar_data['trend_days']}天")
            report.append(f"   - 趋势强度: {psar_data['trend_strength']}")
            report.append(f"   - SAR价格: ${psar_data['psar']:.2f}")
            report.append(f"   - 价格距离: {psar_data['distance']:.2f}%")
            if psar_data['trend_change'] != '无':
                report.append(f"   - 趋势转换: {psar_data['trend_change']}")
        
        # Demark指标
        if demark_data:
            report.append(f"2. Demark指标:")
            if demark_data['signals']:
                report.append("   - 信号:")
                for signal in demark_data['signals']:
                    report.append(f"     - {signal}")
        
        # 均线指标
        if ma_data:
            report.append(f"3. 均线指标:")
            report.append(f"   - 均线排列: {ma_data['ma_trend']}")
            for ma_name, data in ma_data['ma_data'].items():
                diff = data['diff']
                if abs(diff) >= 1:  # 只显示差距超过1%的均线
                    direction = "高于" if diff > 0 else "低于"
                    report.append(f"   - {ma_name}: ${data['price']:.2f} (价格{direction}{ma_name} {abs(diff):.2f}%)")
                else:
                    report.append(f"   - {ma_name}: ${data['price']:.2f} (接近{ma_name})")
            report.append(f"   - 成交量状态: {ma_data['volume_status']}")
        
        # 布林带指标
        if bollinger_data:
            report.append("4. 布林带指标:")
            if bollinger_data['current_price'] is not None:
                report.append(f"   - 当前价格: ${bollinger_data['current_price']:.2f}")
            if bollinger_data['upper_band'] is not None:
                report.append(f"   - 上轨: ${bollinger_data['upper_band']:.2f}")
            if bollinger_data['middle_band'] is not None:
                report.append(f"   - 中轨: ${bollinger_data['middle_band']:.2f}")
            if bollinger_data['lower_band'] is not None:
                report.append(f"   - 下轨: ${bollinger_data['lower_band']:.2f}")
            if bollinger_data['bandwidth'] is not None:
                report.append(f"   - 带宽: {bollinger_data['bandwidth']:.1f}%")
            if bollinger_data['position'] is not None:
                report.append(f"   - 价格位置: {bollinger_data['position']:.1f}%")
            if bollinger_data['bandwidth_trend'] is not None:
                report.append(f"   - 带宽趋势: {bollinger_data['bandwidth_trend']}")
            if bollinger_data['market_status'] is not None:
                report.append(f"   - 市场状态: {bollinger_data['market_status']}")
            if bollinger_data['breakthrough'] is not None and bollinger_data['breakthrough'] != '无':
                report.append(f"   - 突破状态: {bollinger_data['breakthrough']}")
        
        # KDJ指标
        if kdj_data:
            report.append(f"5. KDJ指标:")
            report.append(f"   - K值: {kdj_data['K']:.2f}")
            report.append(f"   - D值: {kdj_data['D']:.2f}")
            report.append(f"   - J值: {kdj_data['J']:.2f}")
            report.append(f"   - 状态: {kdj_data['status']}")
            if kdj_data['divergence']:
                report.append(f"   - 背离: {kdj_data['divergence']}")
        
        # RSI指标
        if rsi_data:
            report.append(f"6. RSI指标:")
            if rsi_data['RSI6'] is not None:
                report.append(f"   - RSI(6): {rsi_data['RSI6']:.2f}")
            if rsi_data['RSI12'] is not None:
                report.append(f"   - RSI(12): {rsi_data['RSI12']:.2f}")
            if rsi_data['RSI24'] is not None:
                report.append(f"   - RSI(24): {rsi_data['RSI24']:.2f}")
            report.append(f"   - 状态: {rsi_data['status']}")
            if rsi_data['divergence']:
                report.append(f"   - 背离: {rsi_data['divergence']}")
        
        # 输出报告
        report_content = "\n".join(report)
        
        # 保存到缓存
        save_to_cache(cache_dir, stock_code, report_content)
        print(f"分析报告已保存到: {cache_dir}/{stock_code}.md", file=sys.stderr)
        
        print(report_content)
        return report_content
    except Exception as e:
        error_msg = f"分析股票 {stock_code} 时发生错误: {str(e)}"
        print(error_msg, file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return error_msg

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='股票技术分析工具')
    parser.add_argument('args', nargs='+', help='股票代码和日期参数（日期可选，支持YYYY-MM-DD、YYYY.MM.DD、YYYY/MM/DD、YYYYMMDD格式）')
    parser.add_argument('--clear-cache', action='store_true', help='清除缓存数据')
    
    args = parser.parse_args()
    
    try:
        # 验证并标准化参数
        normalized_codes, analysis_date = validate_and_normalize_params(args.args)
        
        # 分析每个股票
        for stock_code in normalized_codes:
            try:
                analyze_single_stock(stock_code, analysis_date, args.clear_cache)
                if stock_code != normalized_codes[-1]:  # 如果不是最后一个股票，添加分隔线
                    print("\n" + "="*60 + "\n")
            except Exception as e:
                print(f"分析股票 {stock_code} 时发生错误: {str(e)}", file=sys.stderr)
                continue
                
    except Exception as e:
        print(f"程序执行出错: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main() 