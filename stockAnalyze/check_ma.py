# -*- coding: utf-8 -*-
import sys
import io
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import argparse
from Utils.param_utils import validate_and_normalize_params
from Utils.stock_data_manager import StockDataManager

# 确保stdout和stderr使用UTF-8编码
if not isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if not isinstance(sys.stderr, io.TextIOWrapper):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def debug_print(*args, **kwargs):
    if 'file' not in kwargs:
        kwargs['file'] = sys.stderr
    print(*args, **kwargs)

def info_print(*args, **kwargs):
    kwargs['flush'] = True
    if 'file' not in kwargs:
        kwargs['file'] = sys.stdout
    print(*args, **kwargs)

def check_ma(symbol, end_date=None, manager=None):
    """
    检查股票当前价格相对于各均线的位置，并分析当日涨跌幅和成交量
    
    参数:
    symbol (str): 股票代码或公司名称
    end_date (str or datetime, optional): 结束日期，格式为'YYYY-MM-DD'，默认为当前日期
    manager (StockDataManager, optional): 数据管理器实例
    
    返回:
    str: 分析结果
    """
    try:
        # 处理结束日期
        if end_date is None:
            end_date = datetime.now()
        elif isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            
        # 检查目标日期是否超过当前日期
        current_date = datetime.now()
        if end_date > current_date:
            debug_print(f"目标日期 {end_date.strftime('%Y-%m-%d')} 超过当前日期 {current_date.strftime('%Y-%m-%d')}，无法获取未来数据。")
            return ""
            
        # 为了确保获取到指定日期的数据，将结束日期延后一天
        query_end_date = end_date + timedelta(days=1)
        
        # 获取股票数据
        if manager is None:
            manager = StockDataManager()
            
        # 为了计算移动平均线，我们需要获取足够的历史数据
        # 计算200天前的日期
        history_start_date = (end_date - timedelta(days=400)).strftime('%Y-%m-%d')
        df, from_yf = manager.get_stock_data(symbol, start_date=history_start_date, end_date=query_end_date.strftime('%Y-%m-%d'))
        
        if df is None or df.empty:
            debug_print(f"无法获取 {symbol} 的数据。")
            return ""
            
        # 确保数据格式正确
        df['Date'] = pd.to_datetime(df['Date'])
        
        # 按日期排序
        df = df.sort_values('Date').reset_index(drop=True)
            
        # 确保我们使用的是指定日期的数据
        target_date = end_date.strftime('%Y-%m-%d')
        df_target = df[df['Date'] == target_date]
        
        if df_target.empty:
            debug_print(f"无法获取 {symbol} 在 {target_date} 的数据。")
            return ""
            
        # 获取指定日期的数据索引
        target_idx = df_target.index[0]
        
        # 确保有足够的历史数据来计算移动平均线
        if target_idx < 200:  # 需要至少200个交易日的数据
            debug_print(f"历史数据不足，无法计算移动平均线。当前数据点: {target_idx + 1}")
            return ""
            
        # 计算各个移动平均线
        ma20 = df['Close'].rolling(window=20).mean()
        ma50 = df['Close'].rolling(window=50).mean()
        ma120 = df['Close'].rolling(window=120).mean()
        ma200 = df['Close'].rolling(window=200).mean()
        
        # 计算20日平均成交量
        volume_ma20 = df['Volume'].rolling(window=20).mean()
        
        # 获取指定日期的数据
        current_price = df_target['Close'].iloc[0]
        ma20_price = ma20.iloc[target_idx]
        ma50_price = ma50.iloc[target_idx]
        ma120_price = ma120.iloc[target_idx]
        ma200_price = ma200.iloc[target_idx]
        
        # 获取前一天的收盘价
        prev_day_data = df[df['Date'] < target_date].iloc[-1]
        prev_close = prev_day_data['Close']
        
        current_volume = df_target['Volume'].iloc[0]
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
        
        # 构建输出结果
        output = []
        output.append(f"\n{symbol} 股价分析:")
        output.append(f"分析日期: {target_date}")
        output.append(f"当前收盘价: ${current_price:.2f}")
        output.append(f"\n均线分析:")
        for ma_name, data in ma_data.items():
            if abs(data['diff']) >= 1:  # 只显示差距超过1%的均线
                direction = "高于" if data['diff'] > 0 else "低于"
                output.append(f"{ma_name}: ${data['price']:.2f} (价格{direction}{ma_name} {abs(data['diff']):.2f}%)")
            else:
                output.append(f"{ma_name}: ${data['price']:.2f} (接近{ma_name})")
        
        output.append(f"\n当日涨跌幅: {daily_change:+.2f}%")
        output.append(f"成交量: {int(current_volume):,}")
        output.append(f"20日平均成交量: {int(avg_volume_20d):,}")
        output.append(f"成交量较20日均量: {volume_ratio:+.2f}%")
        
        # 输出成交量分析结论
        volume_status = "高于20日平均水平" if current_volume > avg_volume_20d else "低于20日平均水平"
        output.append(f"成交量状况: {volume_status}")
        
        # 分析均线排列
        ma_trend = analyze_ma_trend(ma_data)
        output.append(f"\n均线排列: {ma_trend}")
        
        result = "\n".join(output)
        info_print(result)
        return result
            
    except Exception as e:
        error_msg = f"分析过程中出现错误: {str(e)}"
        debug_print(error_msg)
        return ""

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

def analyze_stock(symbol, target_date=None, manager=None):
    """
    分析股票的均线情况
    
    参数:
    symbol (str): 股票代码
    target_date (str): 分析日期，格式为YYYY-MM-DD
    manager (StockDataManager): 数据管理器实例
    
    返回:
    str: 分析结果
    """
    return check_ma(symbol, target_date, manager=manager)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='移动平均线分析工具')
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
                check_ma(stock_code, analysis_date, manager=manager)
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