# -*- coding: utf-8 -*-
import yfinance as yf
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

def calculate_rma(series, period):
    """
    计算相对移动平均（RMA）
    RMA = (前一日RMA * (period-1) + 当日值) / period
    """
    alpha = 1.0 / period
    return series.ewm(alpha=alpha, adjust=False).mean()

def calculate_rsi(df, periods=[6, 12, 24]):
    """
    计算RSI指标，使用RMA方法
    
    参数:
    df (DataFrame): 包含价格数据的DataFrame
    periods (list): RSI计算周期列表，默认为[6, 12, 24]
    
    返回:
    DataFrame: 包含不同周期RSI值的DataFrame
    """
    # 计算价格变化
    diff = df['Close'].diff()
    
    # 创建一个空的DataFrame来存储RSI值
    rsi_df = pd.DataFrame()
    
    for period in periods:
        # 分别计算上涨和下跌
        gain = diff.copy()
        loss = diff.copy()
        gain[gain < 0] = 0
        loss[loss > 0] = 0
        loss = abs(loss)
        
        # 使用RMA计算平均上涨和下跌
        avg_gain = calculate_rma(gain, period)
        avg_loss = calculate_rma(loss, period)
        
        # 计算RSI
        rsi = pd.Series(index=df.index)
        
        # 处理分母为0的情况
        rsi[avg_loss == 0] = 100
        rsi[avg_gain == 0] = 0
        
        # 计算其他情况的RSI
        valid_idx = (avg_loss != 0) & (avg_gain != 0)
        rsi[valid_idx] = 100 - (100 / (1 + avg_gain[valid_idx] / avg_loss[valid_idx]))
        
        # 将结果添加到DataFrame中
        rsi_df[f'RSI_{period}'] = rsi.round(2)  # 保留两位小数
        
    return rsi_df

def find_divergence(df, rsi, mid_term_days=30):
    """
    检测RSI指标与价格之间的背离现象
    
    参数:
    df (DataFrame): 包含价格数据的DataFrame
    rsi (DataFrame): 包含RSI指标的DataFrame
    mid_term_days (int): 分析天数
    
    返回:
    tuple: (顶背离信号, 底背离信号, 背离信息)
    """
    messages = []
    periods = [
        ("", mid_term_days)
    ]
    
    # 确保rsi DataFrame也有Date列
    rsi['Date'] = df['Date']
    
    # 获取当前日期（最后一个交易日）
    current_date = df['Date'].max()
    
    # 过滤掉未来数据
    df = df[df['Date'] <= current_date]
    rsi = rsi[rsi['Date'] <= current_date]
    
    # 获取当前日期（最后一个交易日）
    current_date = df['Date'].max()
    current_price = df['Close'].iloc[-1]
    current_rsi = rsi['RSI_6'].iloc[-1]  # 使用RSI_6进行分析
    
    def find_last_cross_index(rsi_6, rsi_12):
        """找到最近的RSI(6)和RSI(12)交叉点"""
        for i in range(len(rsi_6)-2, 0, -1):
            # 检查是否发生交叉
            prev_diff = rsi_6.iloc[i-1] - rsi_12.iloc[i-1]
            curr_diff = rsi_6.iloc[i] - rsi_12.iloc[i]
            next_diff = rsi_6.iloc[i+1] - rsi_12.iloc[i+1]
            
            # 上穿：前一个差值小于0，当前差值大于0
            up_cross = prev_diff < 0 and curr_diff > 0
            
            # 下穿：前一个差值大于0，当前差值小于0
            down_cross = prev_diff > 0 and curr_diff < 0
            
            if up_cross or down_cross:
                return i, up_cross, prev_diff, curr_diff
        return 0, False, None, None
    
    for period_name, days in periods:
        try:
            # 获取最近N天的数据
            recent_df = df.tail(days)
            recent_rsi = rsi.tail(days)
            
            if len(recent_df) < days:
                messages.append(f"数据不足{days}天，无法进行完整分析")
                continue
            
            # 找到最近的RSI交叉点
            last_cross_idx, is_up_cross, prev_diff, curr_diff = find_last_cross_index(
                recent_rsi['RSI_6'], 
                recent_rsi['RSI_12']
            )
            
            if last_cross_idx > 0:
                # 只使用交叉点之后的数据
                recent_df = recent_df.iloc[last_cross_idx:]
                recent_rsi = recent_rsi.iloc[last_cross_idx:]
                cross_type = "上穿" if is_up_cross else "下穿"
                messages.append(f"\n分析从最近的RSI(6){cross_type}RSI(12)点({recent_df['Date'].iloc[0].strftime('%Y-%m-%d')})开始")
                messages.append(f"交叉点差值: {prev_diff:.2f} -> {curr_diff:.2f}")
                messages.append(f"RSI(6): {recent_rsi['RSI_6'].iloc[0]:.2f}, RSI(12): {recent_rsi['RSI_12'].iloc[0]:.2f}")
            
            # 分析所有数据点
            price_series = recent_df['Close']
            rsi_series = recent_rsi['RSI_6']  # 使用RSI_6进行分析
            date_series = recent_df['Date']
            
            # 找到所有局部高点（比前后点都高的点）
            highs = []
            for i in range(1, len(price_series)-1):
                if (price_series.iloc[i] > price_series.iloc[i-1] and 
                    price_series.iloc[i] > price_series.iloc[i+1]):
                    highs.append({
                        'date': date_series.iloc[i],
                        'price': price_series.iloc[i],
                        'rsi': rsi_series.iloc[i]
                    })
            
            # 找到所有局部低点
            lows = []
            for i in range(1, len(price_series)-1):
                if (price_series.iloc[i] < price_series.iloc[i-1] and 
                    price_series.iloc[i] < price_series.iloc[i+1]):
                    lows.append({
                        'date': date_series.iloc[i],
                        'price': price_series.iloc[i],
                        'rsi': rsi_series.iloc[i]
                    })
            
            messages.append(f"\n背离分析:")
            messages.append(f"分析周期: 最近{len(recent_df)}个交易日")
            messages.append(f"当前价格: {current_price:.2f}, RSI值: {current_rsi:.2f}")
            
            # 检查顶背离
            top_divergence = False
            if highs:
                # 遍历所有高点，找出最近的可能形成顶背离的点
                for high in reversed(highs):
                    # 如果当前价格高于高点价格，但RSI低于高点RSI
                    if current_price > high['price'] and current_rsi < high['rsi']:
                        messages.append(f"\n检测到顶背离:")
                        messages.append(f"当前: 价格{current_price:.2f}, RSI值{current_rsi:.2f}")
                        messages.append(f"对比点({high['date'].strftime('%Y-%m-%d')}): 价格{high['price']:.2f}, RSI值{high['rsi']:.2f}")
                        messages.append("建议: 注意可能的回调风险")
                        top_divergence = True
                        break
            
            # 检查底背离
            bottom_divergence = False
            if lows:
                # 遍历所有低点，找出最近的可能形成底背离的点
                for low in reversed(lows):
                    # 如果当前价格低于低点价格，但RSI高于低点RSI
                    if current_price < low['price'] and current_rsi > low['rsi']:
                        messages.append(f"\n检测到底背离:")
                        messages.append(f"当前: 价格{current_price:.2f}, RSI值{current_rsi:.2f}")
                        messages.append(f"对比点({low['date'].strftime('%Y-%m-%d')}): 价格{low['price']:.2f}, RSI值{low['rsi']:.2f}")
                        messages.append("建议: 可能存在反弹机会")
                        bottom_divergence = True
                        break
            
            if not (top_divergence or bottom_divergence):
                messages.append("\n未检测到明显背离")
        
        except Exception as e:
            messages.append(f"\n分析数据时发生错误: {str(e)}")
    
    return top_divergence, bottom_divergence, "\n".join(messages)

def analyze_rsi(symbol, end_date=None, manager=None):
    """
    获取并显示股票的RSI指标值
    
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
            
        # 为了计算RSI指标和进行背离分析，我们需要获取足够的历史数据
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
        
        # 确保有足够的历史数据来计算RSI指标
        if target_idx < 24:  # 需要至少24个交易日的数据
            debug_print(f"历史数据不足，无法计算RSI指标。当前数据点: {target_idx + 1}")
            return ""
            
        # 计算RSI指标
        rsi_df = calculate_rsi(df)
        
        # 获取目标日期的RSI值
        rsi6 = rsi_df['RSI_6'].iloc[target_idx]
        rsi12 = rsi_df['RSI_12'].iloc[target_idx]
        rsi24 = rsi_df['RSI_24'].iloc[target_idx]
        
        # 构建输出结果
        output = []
        output.append(f"\n{symbol} RSI指标分析:")
        output.append(f"分析日期: {target_date}")
        output.append(f"RSI(6): {rsi6:.2f}")
        output.append(f"RSI(12): {rsi12:.2f}")
        output.append(f"RSI(24): {rsi24:.2f}")
        
        # 判断RSI状态
        status = "正常"
        if rsi6 > 95 or rsi12 > 90 or rsi24 > 85:
            status = "严重超买"
        elif rsi6 > 85 or rsi12 > 80 or rsi24 > 75:
            status = "超买"
        elif rsi6 < 5 or rsi12 < 10 or rsi24 < 15:
            status = "严重超卖"
        elif rsi6 < 15 or rsi12 < 20 or rsi24 < 25:
            status = "超卖"
            
        output.append(f"\nRSI状态: {status}")
        
        # 检查背离
        _, _, divergence_msg = find_divergence(df, rsi_df)
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
    分析股票的RSI指标
    
    参数:
    symbol (str): 股票代码
    target_date (str): 分析日期，格式为YYYY-MM-DD
    manager (StockDataManager): 数据管理器实例
    
    返回:
    str: 分析结果
    """
    return analyze_rsi(symbol, target_date, manager=manager)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='RSI指标分析工具')
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
                analyze_rsi(stock_code, analysis_date, manager=manager)
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