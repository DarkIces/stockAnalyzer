# -*- coding: utf-8 -*-
from analyze_stock import (
    analyze_single_stock,
    ensure_cache_dir,
    check_cache_exists
)
from param_utils import validate_and_normalize_params
from datetime import datetime
import pandas as pd
from tabulate import tabulate
import os
import traceback
import sys
import wcwidth
from stock_names import get_stock_name
from pathlib import Path
import concurrent.futures
from typing import List, Dict, Any
import io
import argparse

def wc_ljust(string, width):
    """使用wcwidth计算字符串实际宽度并左对齐"""
    str_width = wcwidth.wcswidth(string)
    padding = width - str_width if width > str_width else 0
    return string + ' ' * padding

def wc_rjust(string, width):
    """使用wcwidth计算字符串实际宽度并右对齐"""
    str_width = wcwidth.wcswidth(string)
    padding = width - str_width if width > str_width else 0
    return ' ' * padding + string

def wc_center(string, width):
    """使用wcwidth计算字符串实际宽度并居中对齐"""
    str_width = wcwidth.wcswidth(string)
    padding = width - str_width if width > str_width else 0
    left_padding = padding // 2
    right_padding = padding - left_padding
    return ' ' * left_padding + string + ' ' * right_padding

def read_cache_file(cache_dir, stock_code):
    """读取缓存文件内容"""
    cache_file = cache_dir / f"{stock_code}.md"
    with open(cache_file, 'r', encoding='utf-8') as f:
        return f.read()

def extract_value(lines, start_text, end_text=None, default=None):
    """从文本行中提取值"""
    try:
        for line in lines:
            if line.startswith(start_text):
                if end_text:
                    return line.split(end_text)[0].split(start_text)[1].strip()
                return line.split(start_text)[1].strip()
    except Exception:
        return default
    return default

def analyze_single_stock_wrapper(args: tuple) -> Dict[str, Any]:
    """
    包装函数，用于并行处理时分析单只股票
    
    参数:
    args: (stock_code, date, clear_cache, cache_dir, order, report_only)
    
    返回:
    Dict: 包含股票分析结果的字典
    """
    stock_code, date, clear_cache, cache_dir, order, report_only = args
    try:
        # 检查缓存是否存在
        if not clear_cache and check_cache_exists(cache_dir, stock_code):
            print(f"使用缓存的分析结果: {cache_dir}/{stock_code}.md", file=sys.stderr)
            content = read_cache_file(cache_dir, stock_code)
        else:
            # 如果没有缓存或需要清除缓存，运行分析
            content = analyze_single_stock(stock_code, date, clear_cache, report_only)
        
        # 从内容中提取关键信息
        lines = content.split('\n')
        
        # 提取价格和涨跌幅
        current_price = float(extract_value(lines, '当前价格: $', default='0'))
        daily_change = float(extract_value(lines, '日涨跌幅: ', '%', default='0'))
        
        # 提取成交量状态
        volume_status = '成交量正常'
        for line in lines:
            if line.startswith('- 成交量: ['):
                try:
                    status = line.split(']')[1].strip()
                    if '低于20日平均水平' in status:
                        volume_status = '成交量低于20日均值'
                    elif '高于20日平均水平' in status:
                        volume_status = '成交量高于20日均值'
                    elif '显著低于20日平均水平' in status:
                        volume_status = '成交量显著低于20日均值'
                    elif '显著高于20日平均水平' in status:
                        volume_status = '成交量显著高于20日均值'
                except IndexError:
                    continue
                break
        
        # 提取MA趋势和相关信号
        ma_signals = []
        ma_trend = '混乱排列'
        for line in lines:
            if '均线排列: [' in line:
                try:
                    ma_trend = line.split('[')[1].split(']')[0]
                except IndexError:
                    continue
            elif 'MA' in line and '[' in line and ']' in line:
                try:
                    signal = line.split('[')[1].split(']')[0]
                    if 'MA' in signal:
                        ma_signals.append(f"[{signal}]")
                except IndexError:
                    continue
        ma_trend = f"[{ma_trend}]{''.join(ma_signals)}" if ma_signals else f"[{ma_trend}]"
        
        # 提取布林带位置和相关信号
        bb_position = 50.0
        bb_signals = []
        for line in lines:
            if '价格位置: ' in line:
                try:
                    bb_position = float(line.split(': ')[1].rstrip('%'))
                except (ValueError, IndexError):
                    pass
            elif ('布林带: [' in line or '波动性: [' in line) and ']' in line:
                try:
                    signal = line.split('[')[1].split(']')[0]
                    bb_signals.append(f"[{signal}]")
                except IndexError:
                    continue
        bb_status = f"[BB位置{bb_position:.0f}%]{''.join(bb_signals)}" if bb_signals else f"[BB位置{bb_position:.0f}%]"
        
        # 提取PSAR信息
        psar_trend = '未知'
        psar_strength = '未知'
        psar_days = 0
        
        for line in lines:
            if line.startswith('- PSAR: [') and '趋势]' in line:
                try:
                    psar_info = line.split('趋势]')[1].strip()
                    # 提取趋势
                    if '上升趋势' in line:
                        psar_trend = '上升'
                    elif '下降趋势' in line:
                        psar_trend = '下降'
                    
                    # 提取强度
                    if '强势' in psar_info:
                        psar_strength = '强'
                    elif '弱势' in psar_info:
                        psar_strength = '弱'
                    else:
                        psar_strength = '中等'
                    
                    # 提取天数
                    for part in psar_info.split(' '):
                        if '天' in part:
                            try:
                                psar_days = int(part.strip('()').split('天')[0])
                                break
                            except (ValueError, IndexError):
                                continue
                except Exception as e:
                    print(f"解析PSAR信息时发生错误: {e}", file=sys.stderr)
                break
        
        # 提取KDJ状态和相关信号
        kdj_signals = []
        kdj_status = ''
        k_value = d_value = j_value = None
        kdj_state = None
        kdj_divergence = None
        
        for line in lines:
            if line.startswith('   - K值: '):
                try:
                    k_value = float(line.split(': ')[1])
                except (ValueError, IndexError):
                    pass
            elif line.startswith('   - D值: '):
                try:
                    d_value = float(line.split(': ')[1])
                except (ValueError, IndexError):
                    pass
            elif line.startswith('   - J值: '):
                try:
                    j_value = float(line.split(': ')[1])
                except (ValueError, IndexError):
                    pass
            elif line.startswith('   - 状态: '):
                kdj_state = line.split(': ')[1].strip()
            elif line.startswith('   - 背离: '):
                kdj_divergence = line.split(': ')[1].strip()
        
        # 添加KDJ具体值的信号
        if k_value is not None:
            kdj_signals.append(f"[K={k_value:.1f}]")
            if k_value > 80:
                kdj_signals.append(f"[K超买]")
            elif k_value < 20:
                kdj_signals.append(f"[K超卖]")
            
        if d_value is not None:
            kdj_signals.append(f"[D={d_value:.1f}]")
            if d_value > 80:
                kdj_signals.append(f"[D超买]")
            elif d_value < 20:
                kdj_signals.append(f"[D超卖]")
            
        if j_value is not None:
            kdj_signals.append(f"[J={j_value:.1f}]")
            if j_value > 120:  # 严重超买
                kdj_signals.append(f"[J严重超买]")
            elif j_value > 100:  # 超买
                kdj_signals.append(f"[J超买]")
            elif j_value < -20:  # 严重超卖
                kdj_signals.append(f"[J严重超卖]")
            elif j_value < 0:  # 超卖
                kdj_signals.append(f"[J超卖]")
        
        # 添加状态和背离信号
        if kdj_state and kdj_state != '正常':
            kdj_signals.insert(0, f"[{kdj_state}]")
        if kdj_divergence:
            kdj_signals.insert(1 if kdj_state and kdj_state != '正常' else 0, f"[{kdj_divergence}]")
        
        # 去除重复的信号
        seen_signals = set()
        unique_signals = []
        for signal in kdj_signals:
            if signal not in seen_signals:
                seen_signals.add(signal)
                unique_signals.append(signal)
        kdj_signals = unique_signals
        
        kdj_status = ''.join(kdj_signals)
        
        # 提取RSI状态和相关信号
        rsi_signals = []
        rsi6_value = rsi12_value = rsi24_value = None
        rsi_state = None
        
        for line in lines:
            if line.startswith('   - RSI(6): '):
                try:
                    rsi6_value = float(line.split(': ')[1])
                except (ValueError, IndexError):
                    pass
            elif line.startswith('   - RSI(12): '):
                try:
                    rsi12_value = float(line.split(': ')[1])
                except (ValueError, IndexError):
                    pass
            elif line.startswith('   - RSI(24): '):
                try:
                    rsi24_value = float(line.split(': ')[1])
                except (ValueError, IndexError):
                    pass
            elif line.startswith('   - 状态: '):
                rsi_state = line.split(': ')[1].strip()
        
        # 添加RSI具体值的信号
        if rsi6_value is not None:
            if rsi6_value > 80:
                rsi_signals.append(f"[RSI6严重超买{rsi6_value:.1f}]")
            elif rsi6_value > 70:
                rsi_signals.append(f"[RSI6超买{rsi6_value:.1f}]")
            elif rsi6_value < 20:
                rsi_signals.append(f"[RSI6严重超卖{rsi6_value:.1f}]")
            elif rsi6_value < 30:
                rsi_signals.append(f"[RSI6超卖{rsi6_value:.1f}]")
                
        if rsi12_value is not None:
            if rsi12_value > 80:
                rsi_signals.append(f"[RSI12严重超买{rsi12_value:.1f}]")
            elif rsi12_value > 70:
                rsi_signals.append(f"[RSI12超买{rsi12_value:.1f}]")
            elif rsi12_value < 20:
                rsi_signals.append(f"[RSI12严重超卖{rsi12_value:.1f}]")
            elif rsi12_value < 30:
                rsi_signals.append(f"[RSI12超卖{rsi12_value:.1f}]")
                
        if rsi24_value is not None:
            if rsi24_value > 80:
                rsi_signals.append(f"[RSI24严重超买{rsi24_value:.1f}]")
            elif rsi24_value > 70:
                rsi_signals.append(f"[RSI24超买{rsi24_value:.1f}]")
            elif rsi24_value < 20:
                rsi_signals.append(f"[RSI24严重超卖{rsi24_value:.1f}]")
            elif rsi24_value < 30:
                rsi_signals.append(f"[RSI24超卖{rsi24_value:.1f}]")
        
        # 添加状态信号
        if rsi_state and rsi_state != '正常':
            rsi_signals.insert(0, f"[{rsi_state}]")
        
        # 去除重复的信号
        seen_signals = set()
        unique_signals = []
        for signal in rsi_signals:
            if signal not in seen_signals:
                seen_signals.add(signal)
                unique_signals.append(signal)
        rsi_signals = unique_signals
        
        rsi_status = ''.join(rsi_signals)
        
        # 返回结果
        return {
            '股票': f"[{stock_code}][{get_stock_name(stock_code)}]",
            '走势': f"[${current_price:.2f}][{daily_change:+.2f}%][{volume_status}]",
            'MA趋势': ma_trend,
            '布林带': bb_status,
            'PSAR': f"{psar_trend}/{psar_strength}({psar_days}天)",
            'KDJ': kdj_status,
            'RSI': rsi_status,
            'order': order
        }
        
    except Exception as e:
        print(f"分析 {stock_code} 时发生错误:")
        traceback.print_exc()
        return None

def analyze_stocks(stock_codes: List[str], date: str = None, clear_cache: bool = False, report_only: bool = False) -> None:
    """
    分析多只股票并生成对比报告
    
    参数:
    stock_codes: 股票代码列表
    date: 分析日期，默认为最近的交易日
    clear_cache: 是否清除缓存
    report_only: 是否只生成报告
    """
    try:
        # 确保缓存目录存在
        cache_dir = ensure_cache_dir(date)
        
        # 准备参数
        args_list = [(code, date, clear_cache, cache_dir, i, report_only) 
                    for i, code in enumerate(stock_codes)]
        
        # 并行处理股票分析
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(analyze_single_stock_wrapper, args_list))
        
        # 过滤掉None结果
        results = [r for r in results if r is not None]
        if not results:
            raise ValueError("没有可用的分析结果")
        
        # 创建DataFrame
        df = pd.DataFrame(results)
        
        # 按order排序
        df = df.sort_values('order')
        df = df.drop('order', axis=1)  # 删除order列
        
        # 设置列名映射
        col_names = {
            '股票': '股票',
            '走势': '走势',
            'MA趋势': 'MA趋势',
            '布林带': '布林带',
            'PSAR': 'PSAR',
            'KDJ': 'KDJ',
            'RSI': 'RSI'
        }
        
        # 设置列宽
        col_widths = {
            '股票': 25,
            '走势': 35,
            'MA趋势': 60,
            '布林带': 25,
            'PSAR': 12,
            'KDJ': 45,
            'RSI': 25
        }
        
        # 对齐数据
        df_aligned = df.copy()
        for col in df.columns:
            if col in ['股票', '走势']:
                df_aligned[col] = df_aligned[col].apply(lambda x: wc_ljust(str(x), col_widths[col]))
        
        # 处理表头
        headers = [col_names.get(col, col) for col in df.columns]
        
        # 打印分析日期
        if not report_only:
            print(f"\n分析日期: {date}\n")
        
        # 打印股票对比表格
        print("股票对比分析:")
        print(tabulate(df_aligned, headers=headers, tablefmt='grid', showindex=False))
        
        print("\n市场整体分析:")
        
        # 统计涨跌家数
        def extract_change(x):
            try:
                parts = x.split(']')
                change_part = parts[1].strip('[').rstrip('%')
                return float(change_part)
            except (IndexError, ValueError):
                return 0.0
        
        up_count = sum(1 for x in df['走势'] if extract_change(x) > 0)
        down_count = sum(1 for x in df['走势'] if extract_change(x) < 0)
        print(f"1. 涨跌分布: 上涨{up_count}只, 下跌{down_count}只")
        
        # 统计均线趋势
        bull_count = sum(1 for x in df['MA趋势'] if '多头排列' in x)
        bear_count = sum(1 for x in df['MA趋势'] if '空头排列' in x)
        mix_count = sum(1 for x in df['MA趋势'] if '均线纠缠' in x)
        print(f"2. 均线趋势: 多头{bull_count}只, 空头{bear_count}只, 交织{mix_count}只")
        
        # 统计布林带位置
        bb_high = sum(1 for x in df['布林带'] if float(x.split('%]')[0].split('位置')[1]) > 80)
        bb_low = sum(1 for x in df['布林带'] if float(x.split('%]')[0].split('位置')[1]) < 20)
        print(f"3. 布林带位置: 超买区间{bb_high}只, 超卖区间{bb_low}只")
        
        # 统计KDJ状态
        kdj_high = sum(1 for x in df['KDJ'] if '超买' in x)
        kdj_low = sum(1 for x in df['KDJ'] if '超卖' in x)
        print(f"4. KDJ状态: 超买{kdj_high}只, 超卖{kdj_low}只")
        
        # 统计RSI状态
        rsi_high = sum(1 for x in df['RSI'] if '超买' in x)
        rsi_low = sum(1 for x in df['RSI'] if '超卖' in x)
        print(f"5. RSI状态: 超买{rsi_high}只, 超卖{rsi_low}只")
        
        # 市场综合判断
        print("\n市场综合判断:")
        
        # 根据涨跌分布判断市场强弱
        if up_count > down_count * 2:
            print("1. 市场强度: 非常强势 [🔥🔥]")
        elif up_count > down_count:
            print("1. 市场强度: 偏强 [🔥]")
        elif down_count > up_count * 2:
            print("1. 市场强度: 非常弱势 [❄️❄️]")
        elif down_count > up_count:
            print("1. 市场强度: 偏弱 [❄️]")
        else:
            print("1. 市场强度: 平衡 [⚖️]")
        
        # 根据技术指标判断市场风险
        risk_high = bb_high + kdj_high + rsi_high
        risk_low = bb_low + kdj_low + rsi_low
        if risk_high > risk_low * 2:
            print("2. 市场风险: 超买严重，调整风险高 [⚠️⚠️]")
        elif risk_high > risk_low:
            print("2. 市场风险: 偏向超买，需要注意 [⚠️]")
        elif risk_low > risk_high * 2:
            print("2. 市场风险: 超卖严重，反弹机会大 [💡💡]")
        elif risk_low > risk_high:
            print("2. 市场风险: 偏向超卖，可以关注 [💡]")
        else:
            print("2. 市场风险: 风险适中 [⚖️]")
        
        # 根据MA趋势判断市场趋势
        if bull_count > bear_count * 2:
            print("3. 市场趋势: 强势上涨 [📈📈]")
        elif bull_count > bear_count:
            print("3. 市场趋势: 温和上涨 [📈]")
        elif bear_count > bull_count * 2:
            print("3. 市场趋势: 强势下跌 [📉📉]")
        elif bear_count > bull_count:
            print("3. 市场趋势: 温和下跌 [📉]")
        else:
            print("3. 市场趋势: 横盘整理 [➡️]")
        
    except Exception as e:
        # 将错误信息打印到stderr
        print(f"生成报告时发生错误: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        # 重新抛出异常，让auto_report.py处理
        raise

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='股票对比分析工具')
    parser.add_argument('args', nargs='+', help='股票代码和日期参数（日期可选，支持YYYY-MM-DD、YYYY.MM.DD、YYYY/MM/DD、YYYYMMDD格式）')
    parser.add_argument('--clear-cache', action='store_true', help='清除缓存数据')
    parser.add_argument('--report-only', action='store_true', help='只输出报告，不显示分析过程')
    
    args = parser.parse_args()
    
    try:
        # 验证并标准化参数
        normalized_codes, analysis_date = validate_and_normalize_params(args.args)
        
        # 分析股票
        analyze_stocks(normalized_codes, analysis_date, args.clear_cache, args.report_only)
                
    except Exception as e:
        # 将错误信息打印到stderr
        print(f"程序执行出错: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        # 重新抛出异常，让auto_report.py处理
        raise

if __name__ == "__main__":
    main() 