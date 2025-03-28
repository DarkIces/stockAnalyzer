# -*- coding: utf-8 -*-
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import io
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
    current_date = df.index[-1]
    
    # 过滤掉未来数据
    df = df[df.index <= current_date]
    kdj = kdj[kdj.index <= current_date]
    
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
                messages.append(f"\n分析从最近的KD交叉点({recent_df.index[0].strftime('%Y-%m-%d')})开始")
            
            # 分析所有数据点
            price_series = recent_df['Close']
            j_series = recent_kdj['J']
            
            # 找到所有价格低点（比邻近点都低的点）
            price_lows = []
            j_at_price_lows = []
            dates_at_price_lows = []
            
            for i in range(1, len(price_series)-1):
                if (price_series.iloc[i] < price_series.iloc[i-1] and 
                    price_series.iloc[i] < price_series.iloc[i+1]):
                    price_lows.append(price_series.iloc[i])
                    j_at_price_lows.append(j_series.iloc[i])
                    dates_at_price_lows.append(price_series.index[i])
            
            # 找到所有价格高点
            price_highs = []
            j_at_price_highs = []
            dates_at_price_highs = []
            
            for i in range(1, len(price_series)-1):
                if (price_series.iloc[i] > price_series.iloc[i-1] and 
                    price_series.iloc[i] > price_series.iloc[i+1]):
                    price_highs.append(price_series.iloc[i])
                    j_at_price_highs.append(j_series.iloc[i])
                    dates_at_price_highs.append(price_series.index[i])
            
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
                    dates_at_j_lows.append(j_series.index[i])
                elif (j_series.iloc[i] > j_series.iloc[i-1] and 
                      j_series.iloc[i] > j_series.iloc[i+1]):
                    j_highs.append(j_series.iloc[i])
                    price_at_j_highs.append(price_series.iloc[i])
                    dates_at_j_highs.append(j_series.index[i])
            
            messages.append(f"\n背离分析:")
            messages.append(f"分析周期: 最近{len(recent_df)}个交易日")
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
                    if (abs(current_price - recent_j_low_price) / recent_j_low_price < 0.01 and  # 价格接近低点
                        current_j > recent_j_low * 1.1):  # J值明显高于低点
                        messages.append(f"\n可能形成底背离:")
                        messages.append(f"当前价格接近低点，但J值明显高于前期低点")
                        messages.append("建议: 关注可能的反弹机会")
                
                # 检查潜在顶背离
                if j_highs:
                    recent_j_high = j_highs[-1]
                    recent_j_high_price = price_at_j_highs[-1]
                    if (abs(current_price - recent_j_high_price) / recent_j_high_price < 0.01 and  # 价格接近高点
                        current_j < recent_j_high * 0.9):  # J值明显低于高点
                        messages.append(f"\n可能形成顶背离:")
                        messages.append(f"当前价格接近高点，但J值明显低于前期高点")
                        messages.append("建议: 注意可能的回调风险")
        
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
    
    return pd.DataFrame({'K': k, 'D': d, 'J': j})

def check_kdj(symbol, end_date=None):
    """
    获取并显示股票的KDJ指标值
    
    参数:
    symbol (str): 股票代码或公司名称
    end_date (str or datetime, optional): 结束日期，格式为'YYYY-MM-DD'，默认为当前日期
    """
    try:
        # 处理结束日期
        if end_date is None:
            end_date = datetime.now()
        elif isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            
        # 为了确保获取到指定日期的数据，将结束日期延后一天
        query_end_date = end_date + timedelta(days=1)
        # 获取足够的历史数据以计算指标
        start_date = end_date - timedelta(days=60)  # 扩展数据获取范围以确保有足够的数据计算背离
        
        info_print(f"正在获取 {symbol} 的数据...")
        stock = yf.Ticker(symbol)
        df = stock.history(start=start_date, end=query_end_date)
        
        if df.empty:
            info_print(f"错误：未找到 {symbol} 的数据")
            return None
            
        # 确保我们使用的是指定日期的数据
        target_date = end_date.strftime('%Y-%m-%d')
        if target_date not in df.index:
            info_print(f"错误：未找到 {target_date} 的数据")
            info_print(f"可用的最近交易日期: {df.index[-1].strftime('%Y-%m-%d')}")
            return None
            
        # 计算KDJ指标
        kdj = calculate_kdj(df, n=9, m1=3, m2=3)
        
        # 获取指定日期的数据索引
        target_idx = df.index.get_loc(target_date)
        
        # 获取最新值
        latest_k = kdj['K'].iloc[target_idx]
        latest_d = kdj['D'].iloc[target_idx]
        latest_j = kdj['J'].iloc[target_idx]
        
        # 输出结果
        info_print(f"\n{symbol} KDJ指标分析 (N=9, M1=3, M2=3):")
        info_print(f"分析日期: {target_date}")
        info_print(f"K值: {latest_k:.2f}")
        info_print(f"D值: {latest_d:.2f}")
        info_print(f"J值: {latest_j:.2f}")
        
        # 分析KDJ指标
        info_print("\n技术分析:")
        if latest_k > latest_d:
            info_print("K线在D线上方，显示上升趋势")
        else:
            info_print("K线在D线下方，显示下降趋势")
            
        # 超买超卖分析
        info_print("\n超买超卖分析:")
        
        # K值分析
        if latest_k > 95:
            info_print("K值超过95，处于严重超买区间")
            kdj_status = '严重超买'
        elif latest_k > 85:
            info_print("K值超过85，处于超买区间")
            kdj_status = '超买'
        elif latest_k < 5:
            info_print("K值低于5，处于严重超卖区间")
            kdj_status = '严重超卖'
        elif latest_k < 15:
            info_print("K值低于15，处于超卖区间")
            kdj_status = '超卖'
        else:
            info_print("K值在正常区间")
            kdj_status = '正常'
            
        # D值分析
        if latest_d > 90:
            info_print("D值超过90，处于严重超买区间")
        elif latest_d > 80:
            info_print("D值超过80，处于超买区间")
        elif latest_d < 10:
            info_print("D值低于10，处于严重超卖区间")
        elif latest_d < 20:
            info_print("D值低于20，处于超卖区间")
        else:
            info_print("D值在正常区间")
            
        # J值分析
        if latest_j > 110:
            info_print("J值超过110，处于严重超买区间")
        elif latest_j > 100:
            info_print("J值超过100，处于超买区间")
        elif latest_j < -10:
            info_print("J值低于-10，处于严重超卖区间")
        elif latest_j < 0:
            info_print("J值低于0，处于超卖区间")
        else:
            info_print("J值在正常区间")
            
        # 综合分析
        severe_overbought = sum([
            1 if latest_k > 95 else 0,
            1 if latest_d > 90 else 0,
            1 if latest_j > 110 else 0
        ])
        
        overbought = sum([
            1 if 85 < latest_k <= 95 else 0,
            1 if 80 < latest_d <= 90 else 0,
            1 if 100 < latest_j <= 110 else 0
        ])
        
        severe_oversold = sum([
            1 if latest_k < 5 else 0,
            1 if latest_d < 10 else 0,
            1 if latest_j < -10 else 0
        ])
        
        oversold = sum([
            1 if 5 <= latest_k < 15 else 0,
            1 if 10 <= latest_d < 20 else 0,
            1 if -10 <= latest_j < 0 else 0
        ])
        
        info_print("\n综合诊断:")
        if severe_overbought >= 2:
            info_print("警告：多个指标显示严重超买，极有可能出现显著回调")
        elif overbought >= 2:
            info_print("警告：多个指标显示超买，可能即将回调")
        elif severe_oversold >= 2:
            info_print("提示：多个指标显示严重超卖，极有可能出现显著反弹")
        elif oversold >= 2:
            info_print("提示：多个指标显示超卖，可能即将反弹")
        else:
            info_print("大多数指标在正常区间运行")
            
        # 背离分析
        info_print("\n背离分析:")
        _, _, divergence_message = find_divergence(df.loc[:target_date], kdj.loc[:target_date])
        if divergence_message and divergence_message.strip():
            info_print(divergence_message)
        else:
            info_print("未发现明显的背离现象")
        
        return kdj.iloc[target_idx]
        
    except Exception as e:
        debug_print(f"发生错误: {str(e)}")
        return None

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='KDJ指标分析工具')
    parser.add_argument('args', nargs='+', help='股票代码和日期参数（日期可选，支持YYYY-MM-DD、YYYY.MM.DD、YYYY/MM/DD、YYYYMMDD格式）')
    
    args = parser.parse_args()
    
    try:
        # 验证并标准化参数
        normalized_codes, analysis_date = validate_and_normalize_params(args.args)
        
        # 分析每个股票
        for stock_code in normalized_codes:
            try:
                check_kdj(stock_code, analysis_date)
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