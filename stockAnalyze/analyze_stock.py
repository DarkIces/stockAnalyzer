# -*- coding: utf-8 -*-
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import pandas as pd
from datetime import datetime, timedelta
from tabulate import tabulate
import importlib.util
import subprocess
from pathlib import Path
import re
import yfinance as yf
import os
import argparse
from param_utils import validate_and_normalize_params

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

def parse_demark_output(output):
    """解析Demark信号输出"""
    data = {
        'signals': [],
        'up_count_9': 0,
        'up_count_13': 0,
        'down_count_9': 0,
        'down_count_13': 0
    }
    
    # 解析计数
    up_count_9_match = re.search(r'上升9计数: (\d+)', output)
    up_count_13_match = re.search(r'上升13计数: (\d+)/4', output)
    down_count_9_match = re.search(r'下降9计数: (\d+)', output)
    down_count_13_match = re.search(r'下降13计数: (\d+)/4', output)
    
    if up_count_9_match:
        data['up_count_9'] = int(up_count_9_match.group(1))
    if up_count_13_match:
        data['up_count_13'] = int(up_count_13_match.group(1))
    if down_count_9_match:
        data['down_count_9'] = int(down_count_9_match.group(1))
    if down_count_13_match:
        data['down_count_13'] = int(down_count_13_match.group(1))
    
    # 解析信号
    signal_pattern = re.compile(r'- (.+)')
    for match in signal_pattern.finditer(output):
        signal = match.group(1)
        data['signals'].append(signal)
    
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
    
    # 解析当前价格
    current_price_match = re.search(r'当前收盘价: \$?([\d.]+)', output)
    if current_price_match:
        data['current_price'] = float(current_price_match.group(1))
        
    # 解析均线数据
    ma_lines = re.findall(r'MA(\d+): \$?([\d.]+) \((接近|价格高于|价格低于)MA\d+(?:[ ]*([\d.]+)%?)?\)', output)
    for ma_num, price, direction, diff_str in ma_lines:
        ma_name = f'MA{ma_num}'
        if price and float(price) > 0:
            diff = float(diff_str) if diff_str else 0.0
            diff = diff if direction == '价格高于' else -diff if direction == '价格低于' else 0.0
            data['ma_data'][ma_name] = {
                'price': float(price),
                'diff': diff
            }
        
    # 解析日涨跌幅
    change_match = re.search(r'当日涨跌幅: ([+-]?[\d.]+)%', output)
    if change_match:
        data['daily_change'] = float(change_match.group(1))
        
    # 解析成交量状态
    volume_match = re.search(r'成交量状况: (.+?)(?=\n|$)', output)
    if volume_match:
        data['volume_status'] = volume_match.group(1).strip()
        
    # 解析均线趋势
    trend_match = re.search(r'均线排列: (.+?)(?=\n|$)', output)
    if trend_match:
        data['ma_trend'] = trend_match.group(1).strip()
        
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
        'RSI6': 0.0,
        'RSI12': 0.0,
        'RSI24': 0.0,
        'status': '正常',
        'divergence': None
    }
    
    # 解析RSI值
    rsi6_match = re.search(r'RSI\(6\): ([\d.]+)', output)
    rsi12_match = re.search(r'RSI\(12\): ([\d.]+)', output)
    rsi24_match = re.search(r'RSI\(24\): ([\d.]+)', output)
    
    if rsi6_match:
        data['RSI6'] = float(rsi6_match.group(1))
    if rsi12_match:
        data['RSI12'] = float(rsi12_match.group(1))
    if rsi24_match:
        data['RSI24'] = float(rsi24_match.group(1))
        
    # 判断状态
    if '严重超买' in output:
        data['status'] = '严重超买'
    elif '严重超卖' in output:
        data['status'] = '严重超卖'
    elif data['RSI6'] > 70 or data['RSI12'] > 70 or data['RSI24'] > 70:
        data['status'] = '超买'
    elif data['RSI6'] < 30 or data['RSI12'] < 30 or data['RSI24'] < 30:
        data['status'] = '超卖'
    else:
        data['status'] = '正常'
        
    # 解析背离信息
    if '检测到看跌背离' in output:
        data['divergence'] = '顶背离'
    elif '检测到看涨背离' in output:
        data['divergence'] = '底背离'
        
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
    
    lines = output.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 解析价格信息
        if line.startswith('当前价格:'):
            data['current_price'] = float(re.search(r'\$?([\d.]+)', line).group(1))
        elif line.startswith('中轨:'):
            match = re.search(r'\$?([\d.]+)', line)
            if match:
                data['middle_band'] = float(match.group(1))
        elif line.startswith('上轨:'):
            data['upper_band'] = float(re.search(r'\$?([\d.]+)', line).group(1))
        elif line.startswith('下轨:'):
            data['lower_band'] = float(re.search(r'\$?([\d.]+)', line).group(1))
        # 解析位置分析
        elif line.startswith('带内位置:'):
            data['position'] = float(re.search(r'([\d.]+)%', line).group(1))
        elif line.startswith('带宽:'):
            data['bandwidth'] = float(re.search(r'([\d.]+)%', line).group(1))
        elif line.startswith('带宽趋势:'):
            data['bandwidth_trend'] = line.split(': ')[1]
        elif line.startswith('突破状态:'):
            data['breakthrough'] = line.split(': ')[1]
        elif line.startswith('市场状态:'):
            data['market_status'] = line.split(': ')[1]
    
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
    
    # 解析价格和PSAR值
    price_lines = re.findall(r'(当前价格|当前SAR): \$?([\d.]+)', output)
    for name, value in price_lines:
        if '当前价格' in name:
            data['current_price'] = float(value)
        elif '当前SAR' in name:
            data['psar'] = float(value)
    
    # 解析趋势信息
    trend_lines = output.split('\n')
    for line in trend_lines:
        if line.startswith('当前趋势:'):
            trend = line.split(':', 1)[1].strip()
            data['trend'] = trend
        elif line.startswith('趋势持续:'):
            days = re.search(r'(\d+)天', line)
            if days:
                data['trend_days'] = int(days.group(1))
        elif line.startswith('趋势强度:'):
            strength = line.split(':', 1)[1].strip()
            data['trend_strength'] = strength
        elif line.startswith('价格与SAR距离:'):
            distance = re.search(r'([\d.]+)%', line)
            if distance:
                data['distance'] = float(distance.group(1))
        elif line.startswith('趋势转换:'):
            change = line.split(':', 1)[1].strip()
            if change and change != '无':
                data['trend_change'] = change
    
    return data

def run_analysis(script_path, stock_code, date=None):
    """运行分析脚本并返回输出结果"""
    try:
        cmd = f"python {script_path} {stock_code}"
        if date:
            cmd += f" {date}"
        
        process = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        if process.returncode != 0:
            print(f"运行 {script_path} 失败: {process.stderr}", file=sys.stderr)
            return ""
            
        return process.stdout
    except Exception as e:
        print(f"运行 {script_path} 时发生异常: {str(e)}", file=sys.stderr)
        return ""

def check_cache_exists(cache_dir: Path, stock_code: str) -> bool:
    """检查缓存是否存在"""
    cache_file = cache_dir / f"{stock_code}.md"
    return cache_file.exists()

def analyze_single_stock(stock_code: str, date: str, clear_cache: bool = False, report_only: bool = False) -> str:
    """
    分析单只股票
    
    参数:
    stock_code (str): 股票代码
    date (str): 分析日期，格式为YYYY-MM-DD
    clear_cache (bool): 是否清除缓存
    report_only (bool): 是否只输出报告部分
    
    返回:
    str: 分析报告内容
    """
    try:
        print(f"分析日期: {date}", file=sys.stderr)
        
        # 确保缓存目录存在
        cache_dir = ensure_cache_dir(date)
        
        # 检查缓存是否存在
        if not clear_cache and check_cache_exists(cache_dir, stock_code):
            print(f"使用缓存的分析结果: {cache_dir}/{stock_code}.md", file=sys.stderr)
            with open(cache_dir / f"{stock_code}.md", 'r', encoding='utf-8') as f:
                content = f.read()
                if not report_only:
                    print(content)
                return content
        
        # 运行各项分析但不直接输出
        demark_output = run_analysis(os.path.join(os.path.dirname(__file__), "check_demark.py"), stock_code, date)
        ma_output = run_analysis(os.path.join(os.path.dirname(__file__), "check_ma.py"), stock_code, date)
        kdj_output = run_analysis(os.path.join(os.path.dirname(__file__), "check_kdj.py"), stock_code, date)
        rsi_output = run_analysis(os.path.join(os.path.dirname(__file__), "check_rsi.py"), stock_code, date)
        bollinger_output = run_analysis(os.path.join(os.path.dirname(__file__), "check_bollinger.py"), stock_code, date)
        psar_output = run_analysis(os.path.join(os.path.dirname(__file__), "check_psar.py"), stock_code, date)

        # 解析各个指标的输出
        demark_data = parse_demark_output(demark_output)
        ma_data = parse_ma_output(ma_output)
        kdj_data = parse_kdj_output(kdj_output)
        rsi_data = parse_rsi_output(rsi_output)
        bollinger_data = parse_bollinger_output(bollinger_output)
        psar_data = parse_psar_output(psar_output)

        # 生成简洁的邮件格式报告
        report = []
        report.append(f"股票代码: {stock_code}")
        report.append(f"分析日期: {date}")
        report.append("-" * 50)
        
        # 价格信息
        report.append(f"当前价格: ${ma_data['current_price']:.2f}")
        report.append(f"日涨跌幅: {ma_data['daily_change']:+.2f}%")
        report.append("")
        
        # 关键信号
        report.append("关键信号:")
        
        # PSAR信号
        if psar_data['trend_change'] != '无':
            report.append(f"- PSAR: [转换] {psar_data['trend_change']}")
        report.append(f"- PSAR: [{psar_data['trend']}趋势] {psar_data['trend_strength']}势 ({psar_data['trend_days']}天)")
        
        # Demark信号
        if demark_data['up_count_9'] > 0 or demark_data['down_count_9'] > 0:
            report.append("- Demark:")
            for signal in demark_data['signals']:
                report.append(f"  - {signal}")
        
        # 均线状态
        report.append(f"- 均线排列: [{ma_data['ma_trend']}]")
        
        # 各均线差距
        for ma_name, data in ma_data['ma_data'].items():
            diff = data['diff']
            if abs(diff) >= 1:  # 只显示差距超过1%的均线
                direction = "高于" if diff > 0 else "低于"
                report.append(f"- {ma_name}: [{direction}{ma_name}:{abs(diff):.2f}%] 价格{direction}{ma_name} {abs(diff):.2f}%")
        
        # 布林带信号
        if bollinger_data['breakthrough'] != '无':
            report.append(f"- 布林带: [突破] {bollinger_data['breakthrough']}")
        elif bollinger_data['market_status'] != '正常波动区间':
            report.append(f"- 布林带: [{bollinger_data['market_status']}]")
        if bollinger_data['bandwidth_trend'] != '正常':
            report.append(f"- 波动性: [{bollinger_data['bandwidth_trend']}]")
        
        # KDJ信号
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
        
        # RSI信号
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
        
        # 成交量状态
        volume_status = ma_data['volume_status']
        if '高于' in volume_status:
            report.append(f"- 成交量: [放量] {volume_status}")
        elif '低于' in volume_status:
            report.append(f"- 成交量: [缩量] {volume_status}")
        
        report.append("")
        
        # 风险提示
        risks = []
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
        if ma_data['ma_trend'] == '多头排列':
            risks.append("[强势] 均线呈多头排列，趋势向上")
        elif ma_data['ma_trend'] == '空头排列':
            risks.append("[弱势] 均线呈空头排列，趋势向下")
        elif ma_data['ma_trend'] == '均线纠缠':
            risks.append("[盘整] 均线交织，可能处于转折点")
            
        # 添加布林带相关的风险提示
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
        report.append(f"1. PSAR指标:")
        report.append(f"   - 当前趋势: {psar_data['trend']}")
        report.append(f"   - 趋势持续: {psar_data['trend_days']}天")
        report.append(f"   - 趋势强度: {psar_data['trend_strength']}")
        report.append(f"   - SAR价格: ${psar_data['psar']:.2f}")
        report.append(f"   - 价格距离: {psar_data['distance']:.2f}%")
        if psar_data['trend_change'] != '无':
            report.append(f"   - 趋势转换: {psar_data['trend_change']}")
        
        # Demark指标
        report.append(f"2. Demark指标:")
        if demark_data['up_count_9'] > 0 or demark_data['down_count_9'] > 0:
            report.append("- 信号:")
            for signal in demark_data['signals']:
                report.append(f"   - {signal}")
        
        # 均线指标
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
            report.append(f"   - 上轨: ${bollinger_data['upper_band']:.2f}")
            report.append(f"   - 中轨: ${bollinger_data['middle_band']:.2f}")
            report.append(f"   - 下轨: ${bollinger_data['lower_band']:.2f}")
            report.append(f"   - 带宽: {bollinger_data['bandwidth']:.1f}%")
            report.append(f"   - 价格位置: {bollinger_data['position']:.1f}%")
            report.append(f"   - 带宽趋势: {bollinger_data['bandwidth_trend']}")
            report.append(f"   - 市场状态: {bollinger_data['market_status']}")
            if bollinger_data['breakthrough'] != '无':
                report.append(f"   - 突破状态: {bollinger_data['breakthrough']}")
        
        # KDJ指标
        report.append(f"5. KDJ指标:")
        report.append(f"   - K值: {kdj_data['K']:.2f}")
        report.append(f"   - D值: {kdj_data['D']:.2f}")
        report.append(f"   - J值: {kdj_data['J']:.2f}")
        report.append(f"   - 状态: {kdj_data['status']}")
        if kdj_data['divergence']:
            report.append(f"   - 背离: {kdj_data['divergence']}")
        
        # RSI指标
        report.append(f"6. RSI指标:")
        report.append(f"   - RSI(6): {rsi_data['RSI6']:.2f}")
        report.append(f"   - RSI(12): {rsi_data['RSI12']:.2f}")
        report.append(f"   - RSI(24): {rsi_data['RSI24']:.2f}")
        report.append(f"   - 状态: {rsi_data['status']}")
        if rsi_data['divergence']:
            report.append(f"   - 背离: {rsi_data['divergence']}")
        
        # 输出报告
        report_content = "\n".join(report)
        
        if not report_only:
            print(report_content)
        
        # 保存到缓存文件
        save_to_cache(cache_dir, stock_code, report_content)
        
        return report_content
    except Exception as e:
        error_msg = f"分析 {stock_code} 时发生错误: {str(e)}"
        print(error_msg)
        return error_msg

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='股票技术分析工具')
    parser.add_argument('args', nargs='+', help='股票代码和日期参数（日期可选，支持YYYY-MM-DD、YYYY.MM.DD、YYYY/MM/DD、YYYYMMDD格式）')
    parser.add_argument('--clear-cache', action='store_true', help='清除缓存数据')
    parser.add_argument('--report-only', action='store_true', help='只输出报告，不显示分析过程')
    
    args = parser.parse_args()
    
    try:
        # 验证并标准化参数
        normalized_codes, analysis_date = validate_and_normalize_params(args.args)
        
        # 分析每个股票
        for stock_code in normalized_codes:
            try:
                analyze_single_stock(stock_code, analysis_date, args.clear_cache, args.report_only)
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