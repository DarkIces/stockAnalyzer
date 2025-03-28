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

def find_divergence(df, kdj, mid_term_days=30):
    """
    检测RSI指标与价格之间的背离现象
    
    参数:
    df (DataFrame): 包含价格数据的DataFrame
    kdj (DataFrame): 包含RSI指标的DataFrame
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
    
    # 获取当前日期（最后一个交易日）
    current_date = df.index[-1]
    current_price = df['Close'].iloc[-1]
    current_rsi = kdj['RSI_6'].iloc[-1]  # 使用RSI_6进行分析
    
    def find_last_cross_index(rsi_series):
        """找到最近的RSI交叉点"""
        for i in range(len(rsi_series)-2, 0, -1):
            # 检查是否发生交叉（上穿或下穿）
            if ((rsi_series.iloc[i] > rsi_series.iloc[i-1] and rsi_series.iloc[i] > rsi_series.iloc[i+1]) or
                (rsi_series.iloc[i] < rsi_series.iloc[i-1] and rsi_series.iloc[i] < rsi_series.iloc[i+1])):
                return i
        return 0
    
    for period_name, days in periods:
        try:
            # 获取最近N天的数据
            recent_df = df.tail(days)
            recent_rsi = kdj.tail(days)
            
            if len(recent_df) < days:
                messages.append(f"数据不足{days}天，无法进行完整分析")
                continue
            
            # 找到最近的RSI交叉点
            last_cross_idx = find_last_cross_index(recent_rsi['RSI_6'])
            if last_cross_idx > 0:
                # 只使用交叉点之后的数据
                recent_df = recent_df.iloc[last_cross_idx:]
                recent_rsi = recent_rsi.iloc[last_cross_idx:]
                messages.append(f"\n分析从最近的RSI交叉点({recent_df.index[0].strftime('%Y-%m-%d')})开始")
            
            # 分析所有数据点
            price_series = recent_df['Close']
            rsi_series = recent_rsi['RSI_6']  # 使用RSI_6进行分析
            
            # 找到所有局部高点（比前后点都高的点）
            highs = []
            for i in range(1, len(price_series)-1):
                if (price_series.iloc[i] > price_series.iloc[i-1] and 
                    price_series.iloc[i] > price_series.iloc[i+1]):
                    highs.append({
                        'date': price_series.index[i],
                        'price': price_series.iloc[i],
                        'rsi': rsi_series.iloc[i]
                    })
            
            # 找到所有局部低点
            lows = []
            for i in range(1, len(price_series)-1):
                if (price_series.iloc[i] < price_series.iloc[i-1] and 
                    price_series.iloc[i] < price_series.iloc[i+1]):
                    lows.append({
                        'date': price_series.index[i],
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

def analyze_rsi(symbol, end_date=None):
    """
    获取并显示股票的RSI指标值
    """
    try:
        # 获取股票数据
        info_print(f"\n正在获取 {symbol} 的数据...")
        
        # 如果没有指定结束日期，使用当前日期
        if end_date is None:
            target_date = datetime.now().date()
        else:
            target_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            
        # 为了确保获取到目标日期的数据，将结束日期延后一天
        query_end_date = (target_date + timedelta(days=1)).strftime('%Y-%m-%d')
        # 计算开始日期（往前推90天）
        start_date = (target_date - timedelta(days=90)).strftime('%Y-%m-%d')
        
        # 使用yfinance获取数据
        stock = yf.Ticker(symbol)
        df = stock.history(start=start_date, end=query_end_date)
        
        if df.empty:
            info_print(f"错误：未找到 {symbol} 的数据")
            return None
            
        # 确保我们使用的是指定日期的数据
        if target_date not in df.index.date:
            info_print(f"错误：未找到 {target_date} 的数据")
            info_print(f"可用的最近交易日期: {df.index[-1].date()}")
            return None
            
        # 计算RSI指标
        rsi = calculate_rsi(df)
        
        # 获取指定日期的数据索引
        target_mask = df.index.date == target_date
        target_idx = df.index.get_loc(df.index[target_mask][0])
        
        # 获取最新值
        rsi_6 = rsi['RSI_6'].iloc[target_idx]
        rsi_12 = rsi['RSI_12'].iloc[target_idx]
        rsi_24 = rsi['RSI_24'].iloc[target_idx]
        
        # 计算RSI背离
        top_divergence, bottom_divergence, divergence_info = find_divergence(df.iloc[:target_idx+1], rsi.iloc[:target_idx+1])
        
        # 输出结果
        info_print(f"\n{symbol} RSI指标分析:")
        info_print(f"分析日期: {target_date}")
        info_print(f"RSI(6): {rsi_6:.2f}")
        info_print(f"RSI(12): {rsi_12:.2f}")
        info_print(f"RSI(24): {rsi_24:.2f}")
        
        # 输出背离分析结果
        info_print("\nRSI背离分析:")
        if top_divergence:
            info_print("检测到看跌背离:")
            info_print(divergence_info)
        elif bottom_divergence:
            info_print("检测到看涨背离:")
            info_print(divergence_info)
        else:
            info_print("未检测到明显背离")
            info_print(divergence_info)
        
        # 分析RSI指标
        info_print("\n趋势分析:")
        if rsi_6 > rsi_12 and rsi_12 > rsi_24:
            info_print("短中长期RSI均显示上升趋势")
        elif rsi_6 < rsi_12 and rsi_12 < rsi_24:
            info_print("短中长期RSI均显示下降趋势")
        else:
            info_print("RSI趋势不明确，可能处于盘整阶段")
            
        # 超买超卖分析
        info_print("\n超买超卖分析:")
        
        # RSI(6)分析
        if rsi_6 > 90:
            info_print("RSI(6)处于严重超买区间，短期极有可能回调")
            rsi_status = '严重超买'
        elif rsi_6 > 80:
            info_print("RSI(6)处于超买区间，短期可能面临回调")
            rsi_status = '超买'
        elif rsi_6 < 10:
            info_print("RSI(6)处于严重超卖区间，短期极有可能反弹")
            rsi_status = '严重超卖'
        elif rsi_6 < 20:
            info_print("RSI(6)处于超卖区间，短期可能出现反弹")
            rsi_status = '超卖'
        else:
            info_print("RSI(6)在正常区间")
            rsi_status = '正常'
            
        # RSI(12)分析
        if rsi_12 > 90:
            info_print("RSI(12)处于严重超买区间，中期极有可能回调")
        elif rsi_12 > 80:
            info_print("RSI(12)处于超买区间，中期可能面临回调")
        elif rsi_12 < 10:
            info_print("RSI(12)处于严重超卖区间，中期极有可能反弹")
        elif rsi_12 < 20:
            info_print("RSI(12)处于超卖区间，中期可能出现反弹")
        else:
            info_print("RSI(12)在正常区间")
            
        # RSI(24)分析
        if rsi_24 > 90:
            info_print("RSI(24)处于严重超买区间，长期极有可能回调")
        elif rsi_24 > 80:
            info_print("RSI(24)处于超买区间，长期可能面临回调")
        elif rsi_24 < 10:
            info_print("RSI(24)处于严重超卖区间，长期极有可能反弹")
        elif rsi_24 < 20:
            info_print("RSI(24)处于超卖区间，长期可能出现反弹")
        else:
            info_print("RSI(24)在正常区间")
            
        # 综合分析
        severe_overbought = sum([
            1 if rsi_6 > 90 else 0,
            1 if rsi_12 > 90 else 0,
            1 if rsi_24 > 90 else 0
        ])
        
        overbought = sum([
            1 if 80 < rsi_6 <= 90 else 0,
            1 if 80 < rsi_12 <= 90 else 0,
            1 if 80 < rsi_24 <= 90 else 0
        ])
        
        severe_oversold = sum([
            1 if rsi_6 < 10 else 0,
            1 if rsi_12 < 10 else 0,
            1 if rsi_24 < 10 else 0
        ])
        
        oversold = sum([
            1 if 10 <= rsi_6 < 20 else 0,
            1 if 10 <= rsi_12 < 20 else 0,
            1 if 10 <= rsi_24 < 20 else 0
        ])
        
        info_print("\n综合诊断:")
        if severe_overbought >= 2:
            info_print("警告：多个RSI指标处于严重超买区间，极有可能出现显著回调")
        elif overbought >= 2:
            info_print("警告：多个RSI指标处于超买区间，建议保持谨慎，注意回调风险")
        elif severe_oversold >= 2:
            info_print("提示：多个RSI指标处于严重超卖区间，极有可能出现显著反弹")
        elif oversold >= 2:
            info_print("提示：多个RSI指标处于超卖区间，可能存在反弹机会")
        else:
            if max(rsi_6, rsi_12, rsi_24) > 70:
                info_print("RSI指标偏高，建议保持谨慎")
                if rsi_6 > 90:
                    info_print("特别提示：短期RSI已达到严重超买水平，极有可能出现回调")
                elif rsi_6 > 80:
                    info_print("特别提示：短期RSI已达到超买水平，注意回调风险")
            elif min(rsi_6, rsi_12, rsi_24) < 30:
                info_print("RSI指标偏低，可能存在反弹机会")
                if rsi_6 < 10:
                    info_print("特别提示：短期RSI已达到严重超卖水平，极有可能出现反弹")
                elif rsi_6 < 20:
                    info_print("特别提示：短期RSI已达到超卖水平，关注反弹机会")
            else:
                info_print("RSI指标处于中性区间，建议观察其他技术指标")
        
        return rsi.iloc[target_idx]
        
    except Exception as e:
        debug_print(f"发生错误: {str(e)}")
        return None

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='RSI指标分析工具')
    parser.add_argument('args', nargs='+', help='股票代码和日期参数（日期可选，支持YYYY-MM-DD、YYYY.MM.DD、YYYY/MM/DD、YYYYMMDD格式）')
    
    args = parser.parse_args()
    
    try:
        # 验证并标准化参数
        normalized_codes, analysis_date = validate_and_normalize_params(args.args)
        
        # 分析每个股票
        for stock_code in normalized_codes:
            try:
                analyze_rsi(stock_code, analysis_date)
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