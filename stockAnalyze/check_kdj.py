# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import io
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

def find_last_cross_index(kdj_df):
    """
    找到最近的KDJ交叉点位置
    
    参数:
    kdj_df (DataFrame): 包含KDJ指标的DataFrame
    
    返回:
    int: 最近交叉点的索引位置
    """
    # 计算K线和D线的差值
    diff = kdj_df['K'] - kdj_df['D']
    # 找到交叉点（差值号数改变的位置）
    cross_points = ((diff.shift(1) * diff) < 0)
    if not cross_points.any():
        return 0
    # 返回最后一个交叉点的位置
    return cross_points[cross_points].index[-1]

def find_divergence(df, kdj, mid_term_days=30):
    """
    检测KDJ指标与价格之间的背离现象
    
    参数:
    df (DataFrame): 包含价格数据的DataFrame
    kdj (DataFrame): 包含KDJ指标的DataFrame
    mid_term_days (int): 分析天数
    
    返回:
    tuple: (顶背离信号, 底背离信号, 背离信息)
    """
    messages = []
    periods = [
        ("", mid_term_days)
    ]
    
    # 获取当前日期（最后一个交易日）
    current_date = df['Date'].max()
    
    # 过滤掉未来数据
    df = df[df['Date'] <= current_date]
    kdj = kdj[kdj['Date'] <= current_date]
    
    def find_last_cross_index(k_series, d_series):
        """找到最近的KD交叉点"""
        for i in range(len(k_series)-2, 0, -1):
            # 检查是否发生交叉（上穿或下穿）
            if ((k_series.iloc[i] > d_series.iloc[i] and k_series.iloc[i-1] < d_series.iloc[i-1]) or
                (k_series.iloc[i] < d_series.iloc[i] and k_series.iloc[i-1] > d_series.iloc[i-1])):
                return i
        return 0
    
    for period_name, days in periods:
        try:
            # 获取最近N天的数据
            recent_df = df.tail(days)
            recent_kdj = kdj.tail(days)
            
            if len(recent_df) < days:
                messages.append(f"数据不足{days}天，无法进行完整分析")
                continue
                
            # 获取当前值
            current_price = recent_df['Close'].iloc[-1]
            current_j = recent_kdj['J'].iloc[-1]
            
            # 找到最近的KD交叉点
            last_cross_idx = find_last_cross_index(recent_kdj['K'], recent_kdj['D'])
            if last_cross_idx > 0:
                # 只使用交叉点之后的数据
                recent_df = recent_df.iloc[last_cross_idx:]
                recent_kdj = recent_kdj.iloc[last_cross_idx:]
                messages.append(f"\n从最近的KD交叉点({recent_df['Date'].iloc[0].strftime('%Y-%m-%d')})开始分析背离")
                messages.append(f"分析区间: {recent_df['Date'].iloc[0].strftime('%Y-%m-%d')} 至 {recent_df['Date'].iloc[-1].strftime('%Y-%m-%d')}")
            else:
                messages.append("\n在分析周期内未发现KD交叉点，使用全部数据进行分析")
                messages.append(f"分析区间: {recent_df['Date'].iloc[0].strftime('%Y-%m-%d')} 至 {recent_df['Date'].iloc[-1].strftime('%Y-%m-%d')}")
            
            # 分析所有数据点
            price_series = recent_df['Close']
            j_series = recent_kdj['J']
            date_series = recent_df['Date']
            
            # 找到所有价格低点（比邻近点都低的点）
            price_lows = []
            j_at_price_lows = []
            dates_at_price_lows = []
            
            for i in range(1, len(price_series)-1):
                if (price_series.iloc[i] < price_series.iloc[i-1] and 
                    price_series.iloc[i] < price_series.iloc[i+1]):
                    price_lows.append(price_series.iloc[i])
                    j_at_price_lows.append(j_series.iloc[i])
                    dates_at_price_lows.append(date_series.iloc[i])
            
            # 找到所有价格高点
            price_highs = []
            j_at_price_highs = []
            dates_at_price_highs = []
            
            for i in range(1, len(price_series)-1):
                if (price_series.iloc[i] > price_series.iloc[i-1] and 
                    price_series.iloc[i] > price_series.iloc[i+1]):
                    price_highs.append(price_series.iloc[i])
                    j_at_price_highs.append(j_series.iloc[i])
                    dates_at_price_highs.append(date_series.iloc[i])
            
            # 找到所有J值低点和高点
            j_lows = []
            price_at_j_lows = []
            dates_at_j_lows = []
            
            j_highs = []
            price_at_j_highs = []
            dates_at_j_highs = []
            
            for i in range(1, len(j_series)-1):
                if (j_series.iloc[i] < j_series.iloc[i-1] and 
                    j_series.iloc[i] < j_series.iloc[i+1]):
                    j_lows.append(j_series.iloc[i])
                    price_at_j_lows.append(price_series.iloc[i])
                    dates_at_j_lows.append(date_series.iloc[i])
                elif (j_series.iloc[i] > j_series.iloc[i-1] and 
                      j_series.iloc[i] > j_series.iloc[i+1]):
                    j_highs.append(j_series.iloc[i])
                    price_at_j_highs.append(price_series.iloc[i])
                    dates_at_j_highs.append(date_series.iloc[i])
            
            messages.append(f"\n当前状态:")
            messages.append(f"当前价格: {current_price:.2f}, J值: {current_j:.2f}")
            
            # 检查底背离
            bottom_divergence = False
            if j_lows:  # 只要有J值低点就检查
                # 找到最近的J值低点
                recent_j_low = j_lows[-1]
                recent_j_low_price = price_at_j_lows[-1]
                recent_j_low_date = dates_at_j_lows[-1]
                
                # 如果当前价格低于最近低点价格，但J值高于最近低点J值
                if current_price < recent_j_low_price and current_j > recent_j_low:
                    messages.append(f"\n检测到底背离:")
                    messages.append(f"当前: 价格{current_price:.2f}, J值{current_j:.2f}")
                    messages.append(f"对比点({recent_j_low_date.strftime('%Y-%m-%d')}): 价格{recent_j_low_price:.2f}, J值{recent_j_low:.2f}")
                    messages.append("建议: 可能存在反弹机会")
                    bottom_divergence = True
            
            # 检查顶背离
            top_divergence = False
            if j_highs:  # 只要有J值高点就检查
                # 找到最近的J值高点
                recent_j_high = j_highs[-1]
                recent_j_high_price = price_at_j_highs[-1]
                recent_j_high_date = dates_at_j_highs[-1]
                
                # 如果当前价格高于最近高点价格，但J值低于最近高点J值
                if current_price > recent_j_high_price and current_j < recent_j_high:
                    messages.append(f"\n检测到顶背离:")
                    messages.append(f"当前: 价格{current_price:.2f}, J值{current_j:.2f}")
                    messages.append(f"对比点({recent_j_high_date.strftime('%Y-%m-%d')}): 价格{recent_j_high_price:.2f}, J值{recent_j_high:.2f}")
                    messages.append("建议: 注意可能的回调风险")
                    top_divergence = True
            
            # 如果没有发现明显背离，检查潜在背离
            if not (bottom_divergence or top_divergence):
                # 检查潜在底背离
                if j_lows:
                    recent_j_low = j_lows[-1]
                    recent_j_low_price = price_at_j_lows[-1]
                    recent_j_low_date = dates_at_j_lows[-1]
                    if (abs(current_price - recent_j_low_price) / recent_j_low_price < 0.01 and  # 价格接近低点
                        current_j > recent_j_low * 1.1):  # J值明显高于低点
                        messages.append(f"\n可能形成底背离:")
                        messages.append(f"当前: 价格{current_price:.2f}, J值{current_j:.2f}")
                        messages.append(f"对比点({recent_j_low_date.strftime('%Y-%m-%d')}): 价格{recent_j_low_price:.2f}, J值{recent_j_low:.2f}")
                        messages.append("建议: 关注可能的反弹机会")
                
                # 检查潜在顶背离
                if j_highs:
                    recent_j_high = j_highs[-1]
                    recent_j_high_price = price_at_j_highs[-1]
                    recent_j_high_date = dates_at_j_highs[-1]
                    if (abs(current_price - recent_j_high_price) / recent_j_high_price < 0.01 and  # 价格接近高点
                        current_j < recent_j_high * 0.9):  # J值明显低于高点
                        messages.append(f"\n可能形成顶背离:")
                        messages.append(f"当前: 价格{current_price:.2f}, J值{current_j:.2f}")
                        messages.append(f"对比点({recent_j_high_date.strftime('%Y-%m-%d')}): 价格{recent_j_high_price:.2f}, J值{recent_j_high:.2f}")
                        messages.append("建议: 注意可能的回调风险")
            
            if not (bottom_divergence or top_divergence) and not (j_lows or j_highs):
                messages.append("\n在分析区间内未发现明显的高点或低点，无法判断背离")
        
        except Exception as e:
            messages.append(f"\n分析数据时发生错误: {str(e)}")
    
    if not messages:
        messages.append("未发现明显的背离现象")
    
    return None, None, "\n".join(messages)

def calculate_kdj(df, n=9, m1=3, m2=3):
    """
    计算KDJ指标
    
    参数:
    df: DataFrame，包含High, Low, Close数据
    n: RSV周期，默认9
    m1: K值平滑系数，默认3
    m2: D值平滑系数，默认3
    
    返回:
    DataFrame，包含K、D、J值
    """
    # 确保数据按日期排序
    df = df.sort_values('Date').reset_index(drop=True)
    
    # 计算RSV
    low_list = df['Low'].rolling(window=n, min_periods=1).min()
    high_list = df['High'].rolling(window=n, min_periods=1).max()
    rsv = (df['Close'] - low_list) / (high_list - low_list) * 100
    
    # 计算K值
    k = pd.Series(index=df.index, dtype=float)
    k.iloc[0] = 50.0  # 初始值设为50
    for i in range(1, len(df)):
        k.iloc[i] = (m1-1) * k.iloc[i-1] / m1 + rsv.iloc[i] / m1
    
    # 计算D值
    d = pd.Series(index=df.index, dtype=float)
    d.iloc[0] = 50.0  # 初始值设为50
    for i in range(1, len(df)):
        d.iloc[i] = (m2-1) * d.iloc[i-1] / m2 + k.iloc[i] / m2
    
    # 计算J值
    j = 3 * k - 2 * d
    
    # 创建结果DataFrame，使用Date作为索引
    result = pd.DataFrame({
        'Date': df['Date'],
        'K': k,
        'D': d,
        'J': j
    })
    
    return result

def check_kdj(symbol, end_date=None, manager=None):
    """
    检查股票的KDJ指标
    
    参数:
    symbol (str): 股票代码
    end_date (str or datetime): 分析日期，格式为YYYY-MM-DD
    manager (StockDataManager): 数据管理器实例
    
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
            
        # 为了计算KDJ指标，我们需要获取足够的历史数据
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
        
        # 确保有足够的历史数据来计算KDJ指标
        if target_idx < 9:  # 需要至少9个交易日的数据
            debug_print(f"历史数据不足，无法计算KDJ指标。当前数据点: {target_idx + 1}")
            return ""
            
        # 计算KDJ指标
        kdj_df = calculate_kdj(df)
        
        # 获取目标日期的KDJ值
        k = kdj_df['K'].iloc[target_idx]
        d = kdj_df['D'].iloc[target_idx]
        j = kdj_df['J'].iloc[target_idx]
        
        # 构建输出结果
        output = []
        output.append(f"\n{symbol} KDJ指标分析:")
        output.append(f"分析日期: {target_date}")
        output.append(f"K值: {k:.2f}")
        output.append(f"D值: {d:.2f}")
        output.append(f"J值: {j:.2f}")
        
        # 判断KDJ状态
        status = "正常"
        if j > 90:
            status = "严重超买"
        elif j > 80:
            status = "超买"
        elif j < 10:
            status = "严重超卖"
        elif j < 20:
            status = "超卖"
            
        output.append(f"\nKDJ状态: {status}")
        
        # 检查背离
        _, _, divergence_msg = find_divergence(df, kdj_df)
        if divergence_msg:
            output.append(divergence_msg)
        
        result = "\n".join(output)
        info_print(result)
        return result
            
    except Exception as e:
        error_msg = f"分析过程中出现错误: {str(e)}"
        debug_print(error_msg)
        return ""

def analyze_stock(symbol, target_date=None, manager=None):
    """
    分析股票的KDJ指标
    
    参数:
    symbol (str): 股票代码
    target_date (str): 分析日期，格式为YYYY-MM-DD
    manager (StockDataManager): 数据管理器实例
    
    返回:
    str: 分析结果
    """
    return check_kdj(symbol, target_date, manager=manager)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='KDJ指标分析工具')
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
                check_kdj(stock_code, analysis_date, manager=manager)
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