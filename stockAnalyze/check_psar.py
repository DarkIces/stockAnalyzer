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

def calculate_psar(high, low, close, af_start=0.02, af_step=0.02, af_max=0.2):
    """计算PSAR（抛物线指标）"""
    length = len(close)
    psar = close.copy()
    psarbull = pd.Series([None] * length, index=close.index)
    psarbear = pd.Series([None] * length, index=close.index)
    bull = True
    af = af_start
    ep = low.iloc[0]
    hp = high.iloc[0]
    lp = low.iloc[0]
    
    for i in range(2, length):
        if bull:
            psar.iloc[i] = psar.iloc[i - 1] + af * (hp - psar.iloc[i - 1])
        else:
            psar.iloc[i] = psar.iloc[i - 1] + af * (lp - psar.iloc[i - 1])
        
        reverse = False
        
        if bull:
            if low.iloc[i] < psar.iloc[i]:
                bull = False
                reverse = True
                psar.iloc[i] = hp
                lp = low.iloc[i]
                af = af_start
            else:
                if high.iloc[i] > hp:
                    hp = high.iloc[i]
                    af = min(af + af_step, af_max)
                if low.iloc[i - 1] < psar.iloc[i]:
                    psar.iloc[i] = low.iloc[i - 1]
                if low.iloc[i - 2] < psar.iloc[i]:
                    psar.iloc[i] = low.iloc[i - 2]
        else:
            if high.iloc[i] > psar.iloc[i]:
                bull = True
                reverse = True
                psar.iloc[i] = lp
                hp = high.iloc[i]
                af = af_start
            else:
                if low.iloc[i] < lp:
                    lp = low.iloc[i]
                    af = min(af + af_step, af_max)
                if high.iloc[i - 1] > psar.iloc[i]:
                    psar.iloc[i] = high.iloc[i - 1]
                if high.iloc[i - 2] > psar.iloc[i]:
                    psar.iloc[i] = high.iloc[i - 2]
        
        if bull:
            psarbull.iloc[i] = psar.iloc[i]
        else:
            psarbear.iloc[i] = psar.iloc[i]
    
    return psar, psarbull, psarbear

def check_psar(stock_code, date=None, days=30, manager=None):
    """检查股票的PSAR指标
    
    Args:
        stock_code (str): 股票代码
        date (str, optional): 分析日期. Defaults to None.
        days (int, optional): 分析天数. Defaults to 30.
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
        if len(df) < 3:  # PSAR至少需要3个交易日的数据
            print(f"数据量不足以计算指标，需要至少3个交易日的数据。", file=sys.stderr)
            return
        
        # 设置Date为索引
        df = df.set_index('Date')
        
        # 计算PSAR
        psar, psarbull, psarbear = calculate_psar(df['High'], df['Low'], df['Close'])
        
        # 获取最新数据
        current_price = df['Close'].iloc[-1]
        current_psar = psar.iloc[-1]
        
        # 判断趋势
        trend = "上升" if psarbull.iloc[-1] is not None else "下降"
        
        # 计算趋势持续天数
        trend_days = 0
        for i in range(len(df)-1, -1, -1):
            if trend == "上升" and psarbull.iloc[i] is not None:
                trend_days += 1
            elif trend == "下降" and psarbear.iloc[i] is not None:
                trend_days += 1
            else:
                break
        
        # 计算趋势强度
        price_change = (df['Close'].iloc[-1] - df['Close'].iloc[-trend_days if trend_days > 0 else -1]) / df['Close'].iloc[-trend_days if trend_days > 0 else -1] * 100
        if abs(price_change) < 1:
            strength = "弱"
        elif abs(price_change) < 3:
            strength = "中等"
        else:
            strength = "强"
        
        # 计算价格与SAR的距离
        distance = abs(current_price - current_psar) / current_price * 100
        
        # 检查趋势是否刚刚转换
        trend_change = "无"
        if len(df) >= 2:
            prev_trend = "上升" if psarbull.iloc[-2] is not None else "下降"
            if prev_trend != trend:
                trend_change = f"由{prev_trend}转为{trend}"
        
        # 输出分析结果
        print(f"\n{stock_code} PSAR分析:")
        print(f"分析日期: {analysis_date}")
        print(f"\n价格信息:")
        print(f"当前价格: ${current_price:.2f}")
        print(f"当前SAR: ${current_psar:.2f}")
        
        print(f"\n趋势分析:")
        print(f"当前趋势: {trend}")
        print(f"趋势持续: {trend_days}天")
        print(f"趋势强度: {strength}")
        print(f"价格与SAR距离: {distance:.2f}%")
        print(f"趋势转换: {trend_change}")
        
        # 返回分析数据
        return {
            'current_price': current_price,
            'psar': current_psar,
            'trend': trend,
            'trend_days': trend_days,
            'trend_strength': strength,
            'distance': distance,
            'trend_change': trend_change
        }
        
    except Exception as e:
        print(f"分析过程中出现错误: {str(e)}", file=sys.stderr)
        return None

def analyze_stock(stock_code, date=None, manager=None):
    """分析股票的PSAR指标并返回结果
    
    Args:
        stock_code (str): 股票代码
        date (str, optional): 分析日期. Defaults to None.
        manager (StockDataManager, optional): 数据管理器实例. Defaults to None.
        
    Returns:
        str: 分析结果
    """
    try:
        result = check_psar(stock_code, date, manager=manager)
        if result is None:
            return ""
            
        # 构建输出字符串
        output = []
        output.append(f"\n{stock_code} PSAR分析:")
        output.append(f"分析日期: {date}")
        output.append(f"\n价格信息:")
        output.append(f"当前价格: ${result['current_price']:.2f}")
        output.append(f"当前SAR: ${result['psar']:.2f}")
        
        output.append(f"\n趋势分析:")
        output.append(f"当前趋势: {result['trend']}")
        output.append(f"趋势持续: {result['trend_days']}天")
        output.append(f"趋势强度: {result['trend_strength']}")
        output.append(f"价格与SAR距离: {result['distance']:.2f}%")
        output.append(f"趋势转换: {result['trend_change']}")
        
        return "\n".join(output)
        
    except Exception as e:
        print(f"分析过程中出现错误: {str(e)}", file=sys.stderr)
        return ""

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='PSAR指标分析工具')
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
                check_psar(stock_code, analysis_date, manager=manager)
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