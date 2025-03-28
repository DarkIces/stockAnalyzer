# -*- coding: utf-8 -*-
import yfinance as yf
from datetime import datetime, timedelta
import sys
import io
import pandas as pd
import numpy as np
import argparse
from param_utils import validate_and_normalize_params

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def debug_print(*args, **kwargs):
    pass

def info_print(*args, **kwargs):
    kwargs['flush'] = True
    if 'file' not in kwargs:
        print(*args, **kwargs)

def check_ma(symbol, end_date=None):
    """
    检查股票当前价格相对于各均线的位置，并分析当日涨跌幅和成交量
    
    参数:
    symbol (str): 股票代码或公司名称
    end_date (str or datetime, optional): 结束日期，格式为'YYYY-MM-DD'，默认为当前日期
    
    返回:
    dict: 包含均线分析结果的字典
    """
    try:
        # 处理结束日期
        if end_date is None:
            end_date = datetime.now()
        elif isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            
        # 为了确保获取到指定日期的数据，将结束日期延后一天
        query_end_date = end_date + timedelta(days=1)
        # 获取250个交易日的数据（为了确保有200个有效的交易日数据）
        start_date = end_date - timedelta(days=400)
        
        stock = yf.Ticker(symbol)
        df = stock.history(start=start_date, end=query_end_date)
        
        if df.empty:
            return None
            
        # 确保我们使用的是指定日期的数据
        target_date = end_date.strftime('%Y-%m-%d')
        if target_date not in df.index:
            return None
            
        # 获取指定日期的数据索引
        target_idx = df.index.get_loc(target_date)
            
        # 计算各个移动平均线
        ma20 = df['Close'].rolling(window=20).mean()
        ma50 = df['Close'].rolling(window=50).mean()
        ma120 = df['Close'].rolling(window=120).mean()
        ma200 = df['Close'].rolling(window=200).mean()
        
        # 计算20日平均成交量
        volume_ma20 = df['Volume'].rolling(window=20).mean()
        
        # 获取指定日期的数据
        current_price = df['Close'].iloc[target_idx]
        ma20_price = ma20.iloc[target_idx]
        ma50_price = ma50.iloc[target_idx]
        ma120_price = ma120.iloc[target_idx]
        ma200_price = ma200.iloc[target_idx]
        prev_close = df['Close'].iloc[target_idx - 1]
        current_volume = df['Volume'].iloc[target_idx]
        avg_volume_20d = volume_ma20.iloc[target_idx]
        
        # 计算价格与各均线的差距百分比
        ma_data = {
            'MA20': {'price': ma20_price, 'diff': ((current_price - ma20_price) / ma20_price) * 100},
            'MA50': {'price': ma50_price, 'diff': ((current_price - ma50_price) / ma50_price) * 100},
            'MA120': {'price': ma120_price, 'diff': ((current_price - ma120_price) / ma120_price) * 100},
            'MA200': {'price': ma200_price, 'diff': ((current_price - ma200_price) / ma200_price) * 100}
        }
        
        # 计算当日涨跌幅
        daily_change = ((current_price - prev_close) / prev_close) * 100
        
        # 计算成交量比较
        volume_ratio = (current_volume / avg_volume_20d - 1) * 100
        
        # 输出结果
        info_print(f"\n{symbol} 股价分析:")
        info_print(f"分析日期: {target_date}")
        info_print(f"当前收盘价: ${current_price:.2f}")
        info_print(f"\n均线分析:")
        for ma_name, data in ma_data.items():
            if abs(data['diff']) >= 1:  # 只显示差距超过1%的均线
                direction = "高于" if data['diff'] > 0 else "低于"
                info_print(f"{ma_name}: ${data['price']:.2f} (价格{direction}{ma_name} {abs(data['diff']):.2f}%)")
            else:
                info_print(f"{ma_name}: ${data['price']:.2f} (接近{ma_name})")
        
        info_print(f"\n当日涨跌幅: {daily_change:+.2f}%")
        info_print(f"成交量: {int(current_volume):,}")
        info_print(f"20日平均成交量: {int(avg_volume_20d):,}")
        info_print(f"成交量较20日均量: {volume_ratio:+.2f}%")
        
        # 输出成交量分析结论
        volume_status = "高于20日平均水平" if current_volume > avg_volume_20d else "低于20日平均水平"
        info_print(f"成交量状况: {volume_status}")
        
        # 分析均线排列
        ma_trend = analyze_ma_trend(ma_data)
        info_print(f"\n均线排列: {ma_trend}")
        
        # 返回分析结果
        return {
            'current_price': current_price,
            'ma_data': ma_data,
            'daily_change': daily_change,
            'volume_status': volume_status,
            'volume_ratio': volume_ratio,
            'ma_trend': ma_trend
        }
            
    except Exception as e:
        debug_print(f"发生错误: {str(e)}")
        return None

def analyze_ma_trend(ma_data):
    """分析均线排列趋势"""
    ma_prices = {
        'MA20': ma_data['MA20']['price'],
        'MA50': ma_data['MA50']['price'],
        'MA120': ma_data['MA120']['price'],
        'MA200': ma_data['MA200']['price']
    }
    
    # 检查是否呈现多头排列（短期均线全部在长期均线之上）
    if ma_prices['MA20'] > ma_prices['MA50'] > ma_prices['MA120'] > ma_prices['MA200']:
        return "多头排列"
    # 检查是否呈现空头排列（短期均线全部在长期均线之下）
    elif ma_prices['MA20'] < ma_prices['MA50'] < ma_prices['MA120'] < ma_prices['MA200']:
        return "空头排列"
    # 检查是否呈现均线纠缠（任意两条均线之间的差距小于1%）
    elif any(abs(price1 - price2) / price2 < 0.01 
            for price1 in ma_prices.values() 
            for price2 in ma_prices.values() 
            if price1 != price2):
        return "均线纠缠"
    else:
        return "混乱排列"

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='移动平均线分析工具')
    parser.add_argument('args', nargs='+', help='股票代码和日期参数（日期可选，支持YYYY-MM-DD、YYYY.MM.DD、YYYY/MM/DD、YYYYMMDD格式）')
    
    args = parser.parse_args()
    
    try:
        # 验证并标准化参数
        normalized_codes, analysis_date = validate_and_normalize_params(args.args)
        
        # 分析每个股票
        for stock_code in normalized_codes:
            try:
                check_ma(stock_code, analysis_date)
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