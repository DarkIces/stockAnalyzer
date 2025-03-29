# -*- coding: utf-8 -*-
import sys
import io
from Utils.param_utils import validate_and_normalize_params, get_last_trading_day
from Utils.stock_data_manager import StockDataManager
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import argparse

# 确保stdout和stderr使用UTF-8编码
if not isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if not isinstance(sys.stderr, io.TextIOWrapper):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def debug_print(*args, **kwargs):
    """打印调试信息"""
    kwargs['flush'] = True
    if 'file' not in kwargs:
        kwargs['file'] = sys.stderr
    print(*args, **kwargs)

def info_print(*args, **kwargs):
    """打印信息"""
    kwargs['flush'] = True
    if 'file' not in kwargs:
        kwargs['file'] = sys.stdout
    print(*args, **kwargs)

def check_bollinger(stock_code, date=None, days=30, period=20, std_dev=2, manager=None):
    """检查股票的布林带指标
    
    Args:
        stock_code (str): 股票代码
        date (str, optional): 分析日期. Defaults to None.
        days (int, optional): 分析天数. Defaults to 30.
        period (int, optional): 布林带周期. Defaults to 20.
        std_dev (int, optional): 标准差倍数. Defaults to 2.
        manager (StockDataManager, optional): 数据管理器实例. Defaults to None.
    """
    try:
        # 使用传入的日期
        analysis_date = date
        if not analysis_date:
            print("无法获取最近交易日数据。", file=sys.stderr)
            return
        
        # 计算开始日期（获取更多数据以计算指标）
        end_date = pd.Timestamp(analysis_date)
        start_date = (end_date - pd.Timedelta(days=days*2)).strftime('%Y-%m-%d')
        
        # 获取股票数据
        if manager is None:
            manager = StockDataManager()
        df, from_yf = manager.get_stock_data(stock_code, start_date=start_date, end_date=analysis_date)
        
        if df is None or df.empty:
            print(f"无法获取 {stock_code} 的数据。", file=sys.stderr)
            return
        
        # 确保数据足够计算指标
        if len(df) < period:
            print(f"数据量不足以计算指标，需要至少{period}个交易日的数据。", file=sys.stderr)
            return
        
        # 计算布林带
        df['MA20'] = df['Close'].rolling(window=period).mean()
        df['STD20'] = df['Close'].rolling(window=period).std()
        df['Upper'] = df['MA20'] + (df['STD20'] * std_dev)
        df['Lower'] = df['MA20'] - (df['STD20'] * std_dev)
        
        # 获取最新数据
        current_price = df['Close'].iloc[-1]
        middle_band = df['MA20'].iloc[-1]
        upper_band = df['Upper'].iloc[-1]
        lower_band = df['Lower'].iloc[-1]
        
        # 计算带宽
        bandwidth = ((upper_band - lower_band) / middle_band) * 100
        
        # 计算价格在带内的位置
        position = ((current_price - lower_band) / (upper_band - lower_band)) * 100
        
        # 判断带宽趋势
        prev_bandwidth = ((df['Upper'].iloc[-2] - df['Lower'].iloc[-2]) / df['MA20'].iloc[-2]) * 100
        bandwidth_trend = '布林带收窄' if bandwidth < prev_bandwidth else '布林带扩大' if bandwidth > prev_bandwidth else '布林带稳定'
        
        # 判断突破状态
        if current_price > upper_band:
            breakthrough = '向上突破'
        elif current_price < lower_band:
            breakthrough = '向下突破'
        else:
            breakthrough = '无'
        
        # 判断市场状态
        if position > 80:
            market_status = '超买区间'
        elif position > 70:
            market_status = '接近超买'
        elif position < 20:
            market_status = '超卖区间'
        elif position < 30:
            market_status = '接近超卖'
        else:
            market_status = '正常波动区间'
        
        # 输出分析结果
        print(f"\n{stock_code} 布林带分析:")
        print(f"分析日期: {analysis_date}")
        
        print(f"\n价格信息:")
        print(f"当前价格: ${current_price:.2f}")
        print(f"中轨: ${middle_band:.2f}")
        print(f"上轨: ${upper_band:.2f}")
        print(f"下轨: ${lower_band:.2f}")
        
        print(f"\n位置分析:")
        print(f"带内位置: {position:.1f}%")
        print(f"带宽: {bandwidth:.1f}%")
        print(f"带宽趋势: {bandwidth_trend}")
        print(f"突破状态: {breakthrough}")
        print(f"\n市场状态: {market_status}")
        
        # 返回分析数据
        return {
            'current_price': current_price,
            'middle_band': middle_band,
            'upper_band': upper_band,
            'lower_band': lower_band,
            'bandwidth': bandwidth,
            'position': position,
            'breakthrough': breakthrough,
            'bandwidth_trend': bandwidth_trend,
            'market_status': market_status
        }
        
    except Exception as e:
        print(f"分析过程中出现错误: {str(e)}", file=sys.stderr)
        return None

def analyze_stock(stock_code, date=None, manager=None):
    """分析股票的布林带指标并返回结果
    
    Args:
        stock_code (str): 股票代码
        date (str, optional): 分析日期. Defaults to None.
        manager (StockDataManager, optional): 数据管理器实例. Defaults to None.
        
    Returns:
        str: 分析结果
    """
    try:
        result = check_bollinger(stock_code, date, manager=manager)
        if result is None:
            return ""
            
        # 构建输出字符串
        output = []
        output.append(f"\n{stock_code} 布林带分析:")
        output.append(f"分析日期: {date}")
        
        output.append(f"\n价格信息:")
        output.append(f"当前价格: ${result['current_price']:.2f}")
        output.append(f"中轨: ${result['middle_band']:.2f}")
        output.append(f"上轨: ${result['upper_band']:.2f}")
        output.append(f"下轨: ${result['lower_band']:.2f}")
        
        output.append(f"\n位置分析:")
        output.append(f"带内位置: {result['position']:.1f}%")
        output.append(f"带宽: {result['bandwidth']:.1f}%")
        output.append(f"带宽趋势: {result['bandwidth_trend']}")
        output.append(f"突破状态: {result['breakthrough']}")
        output.append(f"\n市场状态: {result['market_status']}")
        
        return "\n".join(output)
        
    except Exception as e:
        print(f"分析过程中出现错误: {str(e)}", file=sys.stderr)
        return ""

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='布林带分析工具')
    parser.add_argument('args', nargs='+', help='股票代码和日期参数（日期可选，支持YYYY-MM-DD、YYYY.MM.DD、YYYY/MM/DD、YYYYMMDD格式）')
    
    args = parser.parse_args()
    
    try:
        # 验证并标准化参数
        normalized_codes, analysis_date = validate_and_normalize_params(args.args)
        
        # 创建数据管理器实例
        manager = StockDataManager()
        
        # 分析每个股票
        for stock_code in normalized_codes:
            try:
                check_bollinger(stock_code, analysis_date, manager=manager)
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