#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import io
import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import concurrent.futures
import numpy as np
import os
from decimal import Decimal, ROUND_HALF_UP

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def round_float(value):
    """将浮点数四舍五入到6位小数"""
    if pd.isna(value):
        return value
    return float(f"{value:.6f}")

def round_series(series):
    """将Series中的所有浮点数四舍五入到6位小数"""
    return series.apply(round_float)

def calculate_technical_indicators(df):
    """计算技术指标"""
    # 确保价格数据精度
    df['Close'] = round_series(df['Close'])
    df['High'] = round_series(df['High'])
    df['Low'] = round_series(df['Low'])
    
    # 计算价格变化百分比
    df['price_change'] = round_series(df['Close'].pct_change() * 100)
    
    # 计算RSI
    for period in [6, 12, 24]:
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.where(~rs.isna(), np.nan)  # 处理除以0的情况
        df[f'RSI{period}'] = round_series(rsi)
    
    # 计算KDJ
    low_9 = df['Low'].rolling(window=9, min_periods=9).min()
    high_9 = df['High'].rolling(window=9, min_periods=9).max()
    close_low = df['Close'] - low_9
    high_low = high_9 - low_9
    
    # 处理分母为0的情况
    rsv = close_low / high_low * 100
    rsv = rsv.where(high_low != 0, np.nan)
    
    # 计算KDJ
    k = round_series(rsv.rolling(window=3, min_periods=3).mean())
    d = round_series(k.rolling(window=3, min_periods=3).mean())
    j = round_series(3 * k - 2 * d)
    
    df['K'] = k
    df['D'] = d
    df['J'] = j
    
    # 替换所有无穷值为NaN
    df = df.replace([np.inf, -np.inf], np.nan)
    
    # 确保所有技术指标在开始的N-1行都是NaN
    # RSI需要N+1行数据才能计算第N个RSI值
    for period in [6, 12, 24]:
        df.iloc[:period+1, df.columns.get_loc(f'RSI{period}')] = np.nan
    
    # KDJ需要9行数据计算RSV，然后再需要3行数据计算K值
    kdj_cols = ['K', 'D', 'J']
    for col in kdj_cols:
        df.iloc[:12, df.columns.get_loc(col)] = np.nan
    
    # 价格变化百分比第一行应该是NaN
    df.iloc[0, df.columns.get_loc('price_change')] = np.nan
    
    return df

def fetch_stock_history(symbol, start_date, end_date, append=False):
    """获取股票历史数据"""
    print(f"\n开始获取股票数据...")
    print(f"股票代码：{symbol}")
    print(f"开始日期：{start_date}")
    print(f"结束日期：{end_date}")
    print(f"追加模式：{append}")
    
    # 使用相对于当前文件的路径
    current_dir = Path(__file__).parent
    cache_dir = current_dir / 'cache/history'
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{symbol}.csv"
    
    print(f"缓存文件：{cache_file}")
    
    # 转换日期格式
    start_date = start_date.replace('.', '-')
    if end_date != 'now':
        end_date = end_date.replace('.', '-')
    else:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    # 如果追加模式且文件存在，读取现有数据
    existing_df = None
    if append and cache_file.exists():
        try:
            print(f"读取现有数据文件：{cache_file}")
            existing_df = pd.read_csv(cache_file)
            # 确保日期列是字符串格式
            existing_df['Date'] = pd.to_datetime(existing_df['Date']).dt.strftime('%Y-%m-%d')
            last_date = pd.to_datetime(existing_df['Date'].max())
            print(f"现有数据最后日期：{last_date.strftime('%Y-%m-%d')}")
            if pd.to_datetime(start_date) <= last_date:
                print(f"警告：开始日期 {start_date} 早于或等于现有数据的最后日期 {last_date.strftime('%Y-%m-%d')}")
                return True  # 已经有数据，视为成功
            start_date = (last_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
            print(f"调整后的开始日期：{start_date}")
        except Exception as e:
            print(f"警告：读取现有数据时出错 - {str(e)}")
            # 如果读取失败，删除文件并重新开始
            cache_file.unlink(missing_ok=True)
            existing_df = None
    
    try:
        # 获取数据
        print(f"正在获取 {symbol} 从 {start_date} 到 {end_date} 的数据...")
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date, auto_adjust=True)
        
        # 检查数据是否为空
        if df.empty:
            print(f"警告：未获取到 {symbol} 的数据")
            return False
        
        print(f"获取到 {len(df)} 行数据")
        print("数据列：", df.columns.tolist())
        
        # 重置索引并保存
        df = df.reset_index()
        # 确保日期列是字符串格式
        df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        
        # 只保留原始数据列
        original_columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
        df = df[original_columns]
        
        if append and existing_df is not None:
            # 追加模式：合并数据并去重
            print("合并现有数据和新数据...")
            print(f"现有数据行数：{len(existing_df)}")
            print(f"新数据行数：{len(df)}")
            
            # 确保现有数据也只包含原始列
            existing_df = existing_df[original_columns]
            
            # 合并数据
            df = pd.concat([existing_df, df], ignore_index=True)
            df = df.drop_duplicates(subset=['Date'])
            df = df.sort_values('Date').reset_index(drop=True)
            print(f"合并后总行数：{len(df)}")
        
        # 保存原始数据（不包含技术指标）
        df.to_csv(cache_file, index=False)
        print(f"原始数据已保存到：{cache_file}")
        return True
    except Exception as e:
        print(f"错误：获取 {symbol} 数据时发生异常 - {str(e)}")
        return False

def process_stock_list(symbols, start_date, end_date, max_workers=5):
    """并行处理多个股票"""
    # 使用相对于当前文件的路径
    current_dir = Path(__file__).parent
    cache_dir = current_dir / 'cache/history'
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_symbol = {
            executor.submit(fetch_stock_history, symbol, start_date, end_date, True): symbol 
            for symbol in symbols
        }
        
        # 获取结果
        results = {}
        for future in concurrent.futures.as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                success = future.result()
                results[symbol] = success
            except Exception as e:
                print(f"处理 {symbol} 时出错: {str(e)}", file=sys.stderr)
                results[symbol] = False
    
    return results

def test_data_append():
    """测试数据追加功能"""
    print("\n开始测试数据追加功能...")
    # 使用相对于当前文件的路径
    current_dir = Path(__file__).parent
    cache_dir = current_dir / 'cache/history'
    test_file = cache_dir / "TSM.csv"  # 直接使用TSM.csv作为测试文件
    test_file_direct = cache_dir / "test_TSM_direct.csv"
    
    print(f"缓存目录：{cache_dir}")
    print(f"测试文件：{test_file}")
    print(f"直接获取文件：{test_file_direct}")
    
    # 清除测试文件
    for file in [test_file, test_file_direct]:
        if file.exists():
            try:
                file.unlink()
            except Exception as e:
                print(f"警告：删除文件 {file} 时出错 - {str(e)}")
    
    # 第一次获取数据
    print("\n第一次获取数据（2024.1.2-2024.1.15）：")
    success = fetch_stock_history('TSM', '2024.1.2', '2024.1.15', False)  # 不使用append模式
    if not success:
        print("获取数据失败")
        return
    
    # 第二次获取数据（追加）
    print("\n第二次获取数据（2024.1.16-2024.1.31）：")
    success = fetch_stock_history('TSM', '2024.1.16', '2024.1.31', True)  # 使用append模式
    if not success:
        print("追加数据失败")
        return
    
    # 保存追加后的数据副本
    df_append = pd.read_csv(test_file)
    
    # 直接获取完整数据
    print("\n直接获取完整数据（2024.1.2-2024.1.31）：")
    success = fetch_stock_history('TSM', '2024.1.2', '2024.1.31', False)  # 不使用append模式
    if not success:
        print("获取数据失败")
        return
    
    # 保存直接获取的数据副本
    df_direct = pd.read_csv(test_file)
    
    # 比较数据
    print("\n开始比较数据...")
    print(f"追加文件行数：{len(df_append)}")
    print(f"直接获取文件行数：{len(df_direct)}")
    
    # 确保日期列存在且为datetime类型
    df_append['Date'] = pd.to_datetime(df_append['Date'])
    df_direct['Date'] = pd.to_datetime(df_direct['Date'])
    
    # 按日期排序
    df_append = df_append.sort_values('Date').reset_index(drop=True)
    df_direct = df_direct.sort_values('Date').reset_index(drop=True)
    
    # 获取数值列
    numeric_columns = df_append.select_dtypes(include=[np.number]).columns.tolist()
    print(f"\n数值列：{numeric_columns}")
    
    # 检查数据是否基本相同（考虑浮点数精度）
    test_passed = True
    differences = []
    
    # 首先检查行数是否相同
    if len(df_append) != len(df_direct):
        test_passed = False
        differences.append(f"行数不同：追加文件 {len(df_append)} 行，直接获取文件 {len(df_direct)} 行")
    else:
        # 检查每一列
        for col in numeric_columns:
            # 对于价格变化百分比和技术指标，使用更大的容差
            if col in ['price_change', 'RSI6', 'RSI12', 'RSI24', 'K', 'D', 'J']:
                rtol = 1e-3  # 相对容差 0.1%
                atol = 1e-3  # 绝对容差 0.001
            else:
                rtol = 1e-5  # 相对容差 0.001%
                atol = 1e-5  # 绝对容差 0.00001
            
            # 处理NaN值
            mask_append = df_append[col].isna()
            mask_direct = df_direct[col].isna()
            if not (mask_append == mask_direct).all():
                test_passed = False
                differences.append(f"{col} 列的NaN值位置不同")
                continue
            
            # 比较非NaN值
            valid_append = df_append[col][~mask_append]
            valid_direct = df_direct[col][~mask_direct]
            if not np.allclose(valid_append, valid_direct, rtol=rtol, atol=atol):
                test_passed = False
                # 找出不同的位置
                diff_indices = ~np.isclose(valid_append, valid_direct, rtol=rtol, atol=atol)
                if diff_indices.any():
                    diff_count = diff_indices.sum()
                    max_diff = np.max(np.abs(valid_append[diff_indices] - valid_direct[diff_indices]))
                    differences.append(f"{col} 列有 {diff_count} 个值超出容差范围，最大差异：{max_diff}")
    
    if test_passed:
        print("\n测试通过：两个文件内容在容差范围内相同")
    else:
        print("\n测试失败：发现以下差异：")
        for diff in differences:
            print(f"- {diff}")

def read_stock_list():
    """从stock_list.txt读取股票列表"""
    try:
        # 使用相对于当前文件的路径
        current_dir = Path(__file__).parent
        stock_list_file = current_dir / 'stock_list.txt'
        
        if not stock_list_file.exists():
            print(f"警告：找不到股票列表文件 {stock_list_file}")
            return []
        
        stocks = []
        with open(stock_list_file, 'r', encoding='utf-8') as f:
            for line in f:
                # 跳过空行和注释行
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # 分割并处理每个股票代码
                for stock in line.split(','):
                    stock = stock.strip()
                    if stock:  # 确保股票代码不为空
                        stocks.append(stock)
        
        if not stocks:
            print("警告：股票列表文件为空")
            return []
        
        print(f"从文件中读取到 {len(stocks)} 只股票：{', '.join(stocks)}")
        return stocks
    except Exception as e:
        print(f"读取股票列表文件时出错：{str(e)}")
        return []

def main():
    parser = argparse.ArgumentParser(description='获取股票历史数据')
    parser.add_argument('symbols', nargs='*', help='股票代码列表（可选，如果不提供则从stock_list.txt读取）')
    parser.add_argument('--workers', type=int, default=5, help='并行处理的线程数')
    parser.add_argument('--test', action='store_true', help='运行数据追加测试')
    parser.add_argument('--start', type=str, default='2024-01-01', help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default='now', help='结束日期 (YYYY-MM-DD 或 "now")')
    args = parser.parse_args()

    if args.test:
        test_data_append()
    else:
        # 如果没有提供股票代码，则从文件读取
        symbols = args.symbols if args.symbols else read_stock_list()
        
        if not symbols:
            print("错误：没有找到任何股票代码", file=sys.stderr)
            return
        
        print(f"准备获取 {len(symbols)} 只股票的数据...")
        print(f"时间范围：{args.start} 到 {args.end}")
        
        # 处理股票列表（始终使用append模式）
        results = process_stock_list(symbols, args.start, args.end, args.workers)
        
        # 输出统计信息
        success_count = sum(1 for result in results.values() if result)
        print(f"\n成功获取 {success_count} 只股票的数据")
        if success_count < len(symbols):
            print(f"失败 {len(symbols) - success_count} 只股票")
            # 输出失败的股票代码
            failed_symbols = [symbol for symbol, success in results.items() if not success]
            print("失败的股票：", ", ".join(failed_symbols))

if __name__ == '__main__':
    main() 