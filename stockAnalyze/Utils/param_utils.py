# -*- coding: utf-8 -*-
import yfinance as yf
from datetime import datetime, timedelta
import sys
import pandas as pd
from pathlib import Path

def normalize_stock_code(stock_code: str) -> str:
    """
    标准化股票代码（转换为大写）
    
    参数:
    stock_code (str): 输入的股票代码
    
    返回:
    str: 标准化后的股票代码（大写）
    """
    return stock_code.upper()

def get_last_trading_day(date_str: str = None) -> str:
    """
    获取指定日期的最近有效交易日
    
    参数:
    date_str (str): 日期字符串，格式为YYYY-MM-DD，如果为None则使用当前日期
    
    返回:
    str: 有效的交易日期，格式为YYYY-MM-DD
    """
    try:
        # 获取当前日期
        current_date = pd.Timestamp.now()
        
        # 如果没有提供日期，使用当前日期
        if not date_str:
            target_date = current_date
        else:
            # 解析输入的日期字符串
            target_date = pd.Timestamp(date_str)
            
            # 如果目标日期大于当前日期，使用当前日期并输出日志
            if target_date.date() > current_date.date():
                print(f"警告：目标日期 {date_str} 大于当前日期，将使用当前日期 {current_date.strftime('%Y-%m-%d')}", file=sys.stderr)
                target_date = current_date
        
        # 获取SPY的历史数据来验证交易日
        # 使用比目标日期更大的范围来确保能找到最近的交易日
        start_date = target_date - pd.Timedelta(days=10)
        end_date = target_date + pd.Timedelta(days=1)
        
        spy = yf.Ticker("SPY")
        df = spy.history(start=start_date.strftime('%Y-%m-%d'), 
                        end=end_date.strftime('%Y-%m-%d'))
        
        if df.empty:
            print(f"错误：无法获取交易日期数据", file=sys.stderr)
            sys.exit(1)
        
        # 获取不大于目标日期的最后一个交易日
        valid_dates = df.index[df.index.date <= target_date.date()]
        if len(valid_dates) == 0:
            print(f"错误：在指定日期范围内没有找到有效的交易日", file=sys.stderr)
            sys.exit(1)
        
        last_trading_day = valid_dates[-1].strftime('%Y-%m-%d')
        # 如果最后交易日与目标日期不同，输出日志
        if last_trading_day != target_date.strftime('%Y-%m-%d'):
            print(f"警告：目标日期 {target_date.strftime('%Y-%m-%d')} 不是交易日，将使用最近的交易日 {last_trading_day}", file=sys.stderr)
        return last_trading_day
        
    except ValueError as e:
        print(f"错误：日期格式无效，请使用YYYY-MM-DD格式", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误：获取交易日期时发生错误：{str(e)}", file=sys.stderr)
        sys.exit(1)

def is_date_string(s: str) -> bool:
    """
    判断字符串是否为日期格式
    
    参数:
    s (str): 输入的字符串
    
    返回:
    bool: 如果是日期格式返回True，否则返回False
    """
    # 支持的日期格式
    date_formats = [
        '%Y-%m-%d',
        '%Y.%m.%d',
        '%Y/%m/%d',
        '%Y%m%d'
    ]
    
    for fmt in date_formats:
        try:
            datetime.strptime(s, fmt)
            return True
        except ValueError:
            continue
    return False

def parse_input_args(args: list[str]) -> tuple[list[str], str]:
    """
    解析输入参数，自动识别股票代码和日期
    
    参数:
    args (list[str]): 输入参数列表
    
    返回:
    tuple[list[str], str]: 股票代码列表和日期字符串
    """
    stock_codes = []
    date_str = None
    
    for arg in args:
        if is_date_string(arg):
            if date_str is not None:
                print(f"警告：检测到多个日期参数，将使用最后一个日期 {arg}", file=sys.stderr)
            date_str = arg
        else:
            stock_codes.append(arg)
    
    if not stock_codes:
        print("错误：未提供有效的股票代码", file=sys.stderr)
        sys.exit(1)
        
    return stock_codes, date_str

def validate_and_normalize_params(args: list[str]) -> tuple[list[str], str]:
    """
    验证并标准化输入参数
    
    参数:
    args (list[str]): 输入参数列表
    
    返回:
    tuple[list[str], str]: 标准化后的股票代码列表和有效的交易日期
    """
    # 解析输入参数
    stock_codes, date_str = parse_input_args(args)
    
    # 标准化股票代码
    normalized_codes = [normalize_stock_code(code) for code in stock_codes]
    
    # 获取有效交易日期
    valid_date = get_last_trading_day(date_str)
    
    return normalized_codes, valid_date

def validate_and_normalize_date(args: list[str]) -> str:
    """
    验证并标准化日期参数
    
    参数:
    args (list[str]): 命令行参数列表
    
    返回:
    str: 标准化后的日期字符串（YYYY-MM-DD格式）
    """
    if not args:
        return get_last_trading_day()
        
    # 尝试解析日期参数
    date_str = args[0]
    try:
        # 尝试不同的日期格式
        for fmt in ['%Y-%m-%d', '%Y.%m.%d', '%Y/%m/%d', '%Y%m%d']:
            try:
                date = datetime.strptime(date_str, fmt)
                return date.strftime('%Y-%m-%d')
            except ValueError:
                continue
                
        raise ValueError(f"不支持的日期格式: {date_str}")
    except Exception as e:
        print(f"日期参数错误: {str(e)}", file=sys.stderr)
        return get_last_trading_day() 