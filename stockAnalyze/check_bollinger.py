# -*- coding: utf-8 -*-
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from param_utils import validate_and_normalize_params, get_last_trading_day
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import argparse

def check_bollinger(stock_code, date=None, days=30, period=20, std_dev=2):
    """检查股票的布林带指标"""
    try:
        # 使用传入的日期
        analysis_date = date
        if not analysis_date:
            print("无法获取最近交易日数据。", file=sys.stderr)
            return
        
        # 获取股票数据
        stock = yf.Ticker(stock_code)
        end_date = pd.Timestamp(analysis_date)
        start_date = end_date - pd.Timedelta(days=days*2)  # 获取更多数据以计算指标
        df = stock.history(start=start_date, end=end_date + pd.Timedelta(days=1))
        
        if df.empty:
            print(f"无法获取 {stock_code} 的数据。", file=sys.stderr)
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

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='布林带分析工具')
    parser.add_argument('args', nargs='+', help='股票代码和日期参数（日期可选，支持YYYY-MM-DD、YYYY.MM.DD、YYYY/MM/DD、YYYYMMDD格式）')
    
    args = parser.parse_args()
    
    try:
        # 验证并标准化参数
        normalized_codes, analysis_date = validate_and_normalize_params(args.args)
        
        # 分析每个股票
        for stock_code in normalized_codes:
            try:
                check_bollinger(stock_code, analysis_date)
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