# -*- coding: utf-8 -*-
import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path
import traceback
from typing import Optional, Tuple, List, Dict
import concurrent.futures
import numpy as np
from decimal import Decimal, ROUND_HALF_UP

def round_float(value):
    """将浮点数四舍五入到6位小数"""
    if pd.isna(value):
        return value
    return float(f"{value:.6f}")

def round_series(series):
    """将Series中的所有浮点数四舍五入到6位小数"""
    return series.apply(round_float)

class StockDataManager:
    # 类级别的常量
    DEFAULT_START_DATE = "2024-01-01"
    
    def __init__(self):
        """初始化数据管理器"""
        # 获取脚本所在目录的绝对路径
        self.script_dir = Path(__file__).parent.parent
        self.cache_dir = self.script_dir / 'cache/history'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
    def get_cache_file_path(self, stock_code: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{stock_code}.csv"
        
    def is_trading_day(self, date: str) -> bool:
        """检查是否为交易日"""
        try:
            # 获取指定日期的数据
            ticker = yf.Ticker("AAPL")  # 使用AAPL作为参考
            df = ticker.history(start=date, end=(datetime.strptime(date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d'))
            return not df.empty
        except Exception as e:
            print(f"检查交易日时出错: {str(e)}", file=sys.stderr)
            return False
            
    def get_stock_data(self, stock_code: str, start_date: str = None, end_date: str = None, force_yf: bool = False) -> Tuple[Optional[pd.DataFrame], bool]:
        """
        从缓存或yfinance获取股票数据
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期，默认为2024-01-01
            end_date: 结束日期，默认为今天
            force_yf: 是否强制从yfinance获取数据
            
        Returns:
            Tuple[DataFrame, bool]: (数据DataFrame, 是否从yfinance获取)
        """
        try:
            # 设置默认日期
            if start_date is None:
                start_date = self.DEFAULT_START_DATE
            if end_date is None:
                end_date = datetime.now().strftime('%Y-%m-%d')
                
            # 获取缓存文件路径
            cache_file = self.get_cache_file_path(stock_code)
            
            # 检查缓存文件是否存在
            if cache_file.exists():
                print(f"从缓存读取 {stock_code} 的数据")
                df = pd.read_csv(cache_file)
                df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
                
                # 检查是否需要更新数据
                last_date = df['Date'].max()
                today = datetime.now().strftime('%Y-%m-%d')
                end_date_dt = pd.to_datetime(end_date)
                start_date_dt = pd.to_datetime(start_date)
                
                # 检查是否需要获取新数据
                need_update = False
                fetch_start = None
                fetch_end = None
                
                if last_date < end_date_dt:
                    print(f"{stock_code} 需要获取更新的数据")
                    need_update = True
                    fetch_start = last_date.strftime('%Y-%m-%d')
                    fetch_end = end_date
                    
                if start_date_dt < df['Date'].min():
                    print(f"{stock_code} 需要获取更早的数据")
                    need_update = True
                    # 如果start_date晚于default日期,使用default日期
                    fetch_start = min(start_date, self.DEFAULT_START_DATE)
                    if fetch_end is None:
                        fetch_end = df['Date'].min().strftime('%Y-%m-%d')
                        
                if need_update:
                    new_data = self._fetch_from_yf(stock_code, fetch_start, fetch_end)
                    if new_data is not None and not new_data.empty:
                        df = pd.concat([df, new_data], ignore_index=True)
                        df = df.drop_duplicates(subset=['Date'])
                        df = df.sort_values('Date')
                        df_to_save = df.copy()
                        df_to_save['Date'] = df_to_save['Date'].dt.strftime('%Y-%m-%d')
                        df_to_save.to_csv(cache_file, index=False)
                        print(f"已更新 {stock_code} 的数据")
                    
                # 过滤日期范围
                mask = (df['Date'] >= start_date_dt) & (df['Date'] <= end_date_dt)
                return df[mask], False
                
            else:
                # 缓存文件不存在，从yfinance获取数据，使用默认开始日期
                print(f"缓存文件不存在，从yfinance获取 {stock_code} 的数据，从 {self.DEFAULT_START_DATE} 开始")
                return self._fetch_from_yf(stock_code, self.DEFAULT_START_DATE, end_date), True
                
        except Exception as e:
            print(f"获取 {stock_code} 数据时出错: {str(e)}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            return None, False
            
    def _fetch_from_yf(self, stock_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """从yfinance获取数据"""
        try:
            ticker = yf.Ticker(stock_code)
            
            # 为了确保获取到指定日期的数据，将开始日期提前1天
            start_date_dt = pd.to_datetime(start_date)
            extended_start_date = (start_date_dt - timedelta(days=1)).strftime('%Y-%m-%d')
            
            df = ticker.history(start=extended_start_date, end=end_date, auto_adjust=True)
            
            if df.empty:
                print(f"未获取到 {stock_code} 的数据", file=sys.stderr)
                return None
                
            # 重置索引并保存
            df = df.reset_index()
            df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
            
            # 只保留原始数据列
            original_columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            df = df[original_columns]
            
            # 确保数据精度
            for col in ['Open', 'High', 'Low', 'Close']:
                df[col] = round_series(df[col])
            
            # 保存到缓存
            df_to_save = df.copy()
            df_to_save['Date'] = df_to_save['Date'].dt.strftime('%Y-%m-%d')
            cache_file = self.get_cache_file_path(stock_code)
            df_to_save.to_csv(cache_file, index=False)
            print(f"已保存 {stock_code} 的数据到缓存")
            
            return df
            
        except Exception as e:
            print(f"从yfinance获取 {stock_code} 数据时出错: {str(e)}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            return None
            
    def update_history_cache(self, stock_code: str, new_data: pd.DataFrame) -> bool:
        """使用新数据更新历史数据缓存"""
        try:
            cache_file = self.get_cache_file_path(stock_code)
            
            if cache_file.exists():
                # 读取现有数据
                existing_df = pd.read_csv(cache_file)
                existing_df['Date'] = pd.to_datetime(existing_df['Date'])
                
                # 合并数据
                df = pd.concat([existing_df, new_data], ignore_index=True)
                df = df.drop_duplicates(subset=['Date'])
                df = df.sort_values('Date')
            else:
                df = new_data
                
            # 保存更新后的数据
            df.to_csv(cache_file, index=False)
            print(f"已更新 {stock_code} 的缓存数据")
            return True
            
        except Exception as e:
            print(f"更新 {stock_code} 缓存数据时出错: {str(e)}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            return False
            
    def validate_data(self, data: pd.DataFrame) -> bool:
        """验证数据完整性"""
        try:
            if data is None or data.empty:
                return False
                
            # 检查必要的列是否存在
            required_columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            if not all(col in data.columns for col in required_columns):
                return False
                
            # 检查数据类型
            if not pd.api.types.is_datetime64_any_dtype(data['Date']):
                data['Date'] = pd.to_datetime(data['Date'])
                
            # 检查日期是否连续
            date_diff = data['Date'].diff().dt.days
            if date_diff.max() > 5:  # 允许最多5天的间隔
                return False
                
            # 检查数值是否合理
            if (data['High'] < data['Low']).any():
                return False
            if (data['Close'] > data['High']).any() or (data['Close'] < data['Low']).any():
                return False
            if (data['Open'] > data['High']).any() or (data['Open'] < data['Low']).any():
                return False
                
            return True
            
        except Exception as e:
            print(f"验证数据时出错: {str(e)}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            return False
            
    def process_stock_list(self, symbols: List[str], start_date: str, end_date: str, max_workers: int = 5) -> Dict[str, bool]:
        """并行处理多个股票"""
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_symbol = {
                executor.submit(self._fetch_from_yf, symbol, start_date, end_date): symbol 
                for symbol in symbols
            }
            
            # 获取结果
            for future in concurrent.futures.as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    df = future.result()
                    results[symbol] = df is not None and not df.empty
                except Exception as e:
                    print(f"处理 {symbol} 时出错: {str(e)}", file=sys.stderr)
                    results[symbol] = False
        
        return results
        
    def read_stock_list(self) -> List[str]:
        """从stock_list.txt读取股票列表"""
        try:
            stock_list_file = self.script_dir / 'Settings' / 'stock_list.txt'
            
            if not stock_list_file.exists():
                print(f"找不到股票列表文件 {stock_list_file}", file=sys.stderr)
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
                print("股票列表文件为空", file=sys.stderr)
                return []
            
            print(f"从文件中读取到 {len(stocks)} 只股票：{', '.join(stocks)}")
            return stocks
        except Exception as e:
            print(f"读取股票列表文件时出错：{str(e)}", file=sys.stderr)
            return []

def test_data_manager():
    """测试数据管理器"""
    manager = StockDataManager()
    
    # 测试获取数据
    print("\n测试获取数据...")
    df, from_yf = manager.get_stock_data('AAPL', '2024-03-01', '2024-03-27')
    if df is not None:
        print(f"成功获取数据，行数: {len(df)}")
        print(f"数据范围: {df['Date'].min()} 到 {df['Date'].max()}")
        print(f"是否从yfinance获取: {from_yf}")
    else:
        print("获取数据失败")
        
    # 测试数据验证
    print("\n测试数据验证...")
    if df is not None:
        is_valid = manager.validate_data(df)
        print(f"数据验证结果: {'通过' if is_valid else '失败'}")
        
    # 测试更新缓存
    print("\n测试更新缓存...")
    if df is not None:
        success = manager.update_history_cache('AAPL', df)
        print(f"更新缓存结果: {'成功' if success else '失败'}")
        
    # 测试数据合并
    print("\n测试数据合并...")
    # 获取较早的数据
    early_df, _ = manager.get_stock_data('AAPL', '2024-02-01', '2024-02-29')
    if early_df is not None:
        print(f"获取到较早数据，行数: {len(early_df)}")
        print(f"数据范围: {early_df['Date'].min()} 到 {early_df['Date'].max()}")
        
        # 合并数据
        success = manager.update_history_cache('AAPL', early_df)
        print(f"合并数据结果: {'成功' if success else '失败'}")
        
        # 验证合并后的数据
        merged_df, _ = manager.get_stock_data('AAPL', '2024-02-01', '2024-03-27')
        if merged_df is not None:
            print(f"合并后数据，行数: {len(merged_df)}")
            print(f"数据范围: {merged_df['Date'].min()} 到 {merged_df['Date'].max()}")
            print(f"数据验证结果: {'通过' if manager.validate_data(merged_df) else '失败'}")

if __name__ == "__main__":
    test_data_manager() 