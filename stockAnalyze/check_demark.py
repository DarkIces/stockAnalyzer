# -*- coding: utf-8 -*-
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import argparse
from param_utils import validate_and_normalize_params

def debug_print(*args, **kwargs):
    pass

def info_print(*args, **kwargs):
    kwargs['flush'] = True
    if 'file' not in kwargs:
        print(*args, **kwargs)

def calculate_demark_signals(df):
    """
    计算Demark信号:
    - 上升9信号：连续9天收盘价高于4天前的收盘价
    - 上升13信号：在满足9信号后，当天收盘价仍高于满足9的那天之前4天的收盘价且高于两天前收盘价，计数加1（非连续）
    - 下降9信号：连续9天收盘价低于4天前的收盘价
    - 下降13信号：在满足9信号后，当天收盘价仍低于满足9的那天之前4天的收盘价且低于两天前收盘价，计数加1（非连续）
    
    当满足9或13信号时，13信号计数重置为0
    当价格不满足参考条件时，13信号计数也重置为0
    """
    try:
        # 计算4天前和2天前的收盘价
        df['Close_4d_ago'] = df['Close'].shift(4)
        df['Close_2d_ago'] = df['Close'].shift(2)
        
        # 计算信号条件
        df['Above_4d'] = df['Close'] > df['Close_4d_ago']
        df['Below_4d'] = df['Close'] < df['Close_4d_ago']
        df['Above_2d'] = df['Close'] > df['Close_2d_ago']
        df['Below_2d'] = df['Close'] < df['Close_2d_ago']
        
        # 初始化计数列和辅助变量
        df['Up_Count_9'] = 0
        df['Up_Count_13'] = 0
        df['Down_Count_9'] = 0
        df['Down_Count_13'] = 0
        
        # 计算连续计数
        up_count_9 = 0
        down_count_9 = 0
        
        # 记录满足9信号后的额外计数（13-9=4）
        up_extra_count = 0
        down_extra_count = 0
        
        # 记录满足9信号时的参考价格
        up_signal9_ref_price = None
        down_signal9_ref_price = None
        
        # 记录最近一次9信号和13信号触发日期
        last_up_signal9_date = None
        last_down_signal9_date = None
        last_up_signal13_date = None
        last_down_signal13_date = None
        
        # 创建信号触发日期字典
        up_signal9_dates = {}
        down_signal9_dates = {}
        up_signal13_dates = {}
        down_signal13_dates = {}
        
        for i in range(len(df)):
            current_date = df.index[i]
            current_price = df['Close'].iloc[i]
            
            # 处理NaN值
            if pd.isna(df['Close_4d_ago'].iloc[i]) or pd.isna(df['Close_2d_ago'].iloc[i]):
                continue
            
            # 上升9计数
            if df['Above_4d'].iloc[i]:
                up_count_9 += 1
            else:
                up_count_9 = 0
            
            # 下降9计数
            if df['Below_4d'].iloc[i]:
                down_count_9 += 1
            else:
                down_count_9 = 0
            
            # 检测是否刚满足9信号
            if up_count_9 == 9:
                up_signal9_ref_price = df['Close_4d_ago'].iloc[i]
                last_up_signal9_date = current_date
                up_signal9_dates[current_date] = True
                
            if down_count_9 == 9:
                down_signal9_ref_price = df['Close_4d_ago'].iloc[i]
                last_down_signal9_date = current_date
                down_signal9_dates[current_date] = True
            
            # 计算上升13信号
            if last_up_signal9_date is not None and current_date > last_up_signal9_date:
                can_start_up13_count = (last_up_signal13_date is None or 
                                      (current_date > last_up_signal13_date and last_up_signal9_date > last_up_signal13_date))
                
                if can_start_up13_count:
                    if up_extra_count == 0:
                        if current_price > up_signal9_ref_price and df['Above_2d'].iloc[i]:
                            up_extra_count = 1
                    elif current_price > up_signal9_ref_price:
                        if df['Above_2d'].iloc[i]:
                            if up_extra_count < 4:
                                up_extra_count += 1
                                if up_extra_count == 4:
                                    last_up_signal13_date = current_date
                                    up_signal13_dates[current_date] = True
                                    up_extra_count = 4
                    elif current_price <= up_signal9_ref_price:
                        up_extra_count = 0
                else:
                    up_extra_count = 0
            
            # 计算下降13信号
            if last_down_signal9_date is not None and current_date > last_down_signal9_date:
                can_start_down13_count = (last_down_signal13_date is None or 
                                        (current_date > last_down_signal13_date and last_down_signal9_date > last_down_signal13_date))
                
                if can_start_down13_count:
                    if down_extra_count == 0:
                        if current_price < down_signal9_ref_price and df['Below_2d'].iloc[i]:
                            down_extra_count = 1
                    elif current_price < down_signal9_ref_price:
                        if df['Below_2d'].iloc[i]:
                            if down_extra_count < 4:
                                down_extra_count += 1
                                if down_extra_count == 4:
                                    last_down_signal13_date = current_date
                                    down_signal13_dates[current_date] = True
                                    down_extra_count = 4
                    elif current_price >= down_signal9_ref_price:
                        down_extra_count = 0
                else:
                    down_extra_count = 0
            
            # 更新DataFrame
            df.loc[df.index[i], 'Up_Count_9'] = up_count_9
            df.loc[df.index[i], 'Up_Count_13'] = up_extra_count
            df.loc[df.index[i], 'Down_Count_9'] = down_count_9
            df.loc[df.index[i], 'Down_Count_13'] = down_extra_count
        
        # 创建信号触发日期列
        df['Up_Signal9_Date'] = pd.Series(False, index=df.index)
        df['Down_Signal9_Date'] = pd.Series(False, index=df.index)
        df['Up_Signal13_Date'] = pd.Series(False, index=df.index)
        df['Down_Signal13_Date'] = pd.Series(False, index=df.index)
        
        # 填充信号触发日期
        for date in up_signal9_dates:
            if date in df.index:
                df.loc[date, 'Up_Signal9_Date'] = True
        
        for date in down_signal9_dates:
            if date in df.index:
                df.loc[date, 'Down_Signal9_Date'] = True
        
        for date in up_signal13_dates:
            if date in df.index:
                df.loc[date, 'Up_Signal13_Date'] = True
        
        for date in down_signal13_dates:
            if date in df.index:
                df.loc[date, 'Down_Signal13_Date'] = True
        
        # 计算信号
        df['Up_Signal_9'] = df['Up_Count_9'] == 9
        df['Up_Signal_13'] = df['Up_Count_13'] == 4
        df['Down_Signal_9'] = df['Down_Count_9'] == 9
        df['Down_Signal_13'] = df['Down_Count_13'] == 4
        
        return df, last_up_signal9_date, last_down_signal9_date, last_up_signal13_date, last_down_signal13_date
    except Exception as e:
        debug_print(f"发生错误: {e}")
        return None, None, None, None, None

def check_demark(symbol, target_date=None, days=30, report_only=False):
    """
    检查指定股票的Demark信号
    """
    try:
        # 如果没有指定日期，使用当前日期
        if target_date is None:
            target_date = datetime.now().strftime('%Y-%m-%d')
        
        # 确保target_date是datetime对象
        if isinstance(target_date, str):
            try:
                target_date = pd.to_datetime(target_date)
            except Exception as e:
                return
        
        # 计算查询日期范围
        query_end_date = target_date + timedelta(days=1)
        query_start_date = target_date - timedelta(days=days)
        
        try:
            # 获取数据
            stock = yf.Ticker(symbol)
            df = stock.history(start=query_start_date, end=query_end_date)
            
            if df.empty:
                return
            
            # 计算Demark信号
            df, last_up_signal9_date, last_down_signal9_date, last_up_signal13_date, last_down_signal13_date = calculate_demark_signals(df)
            
            # 获取目标日期的数据
            target_data = df[df.index.date == target_date.date()]
            
            if target_data.empty:
                return
            
            # 输出分析结果
            info_print(f"\n{symbol} Demark信号分析:")
            info_print(f"分析日期: {target_date.strftime('%Y-%m-%d')}")
            info_print(f"当前价格: {target_data['Close'].iloc[0]:.2f}")
            info_print(f"4天前价格: {target_data['Close_4d_ago'].iloc[0]:.2f}")
            info_print(f"2天前价格: {target_data['Close_2d_ago'].iloc[0]:.2f}")
            
            # 打印计数情况
            info_print(f"\nDemark指标计数:")
            info_print(f"上升9计数: {target_data['Up_Count_9'].iloc[0]:.0f}")
            info_print(f"上升13计数: {target_data['Up_Count_13'].iloc[0]:.0f}/4")
            info_print(f"下降9计数: {target_data['Down_Count_9'].iloc[0]:.0f}")
            info_print(f"下降13计数: {target_data['Down_Count_13'].iloc[0]:.0f}/4")
            
            # 显示最近信号触发情况
            info_print("\n最近信号触发情况:")
            if last_up_signal9_date is not None:
                info_print(f"上升9信号最近触发于: {last_up_signal9_date.strftime('%Y-%m-%d')}")
            
            if last_down_signal9_date is not None:
                info_print(f"下降9信号最近触发于: {last_down_signal9_date.strftime('%Y-%m-%d')}")
            
            if last_up_signal13_date is not None:
                info_print(f"上升13信号最近触发于: {last_up_signal13_date.strftime('%Y-%m-%d')}")
            
            if last_down_signal13_date is not None:
                info_print(f"下降13信号最近触发于: {last_down_signal13_date.strftime('%Y-%m-%d')}")
            
            # 输出信号状态
            signals_detected = False
            signals = []
            
            if target_data['Up_Count_9'].iloc[0] >= 6:
                signals.append(f"上升Demark警告(9计数: {target_data['Up_Count_9'].iloc[0]}/9)")
                signals_detected = True
            elif target_data['Up_Signal_9'].iloc[0]:
                signals.append("上升Demark9信号")
                signals_detected = True
                
            if target_data['Up_Count_13'].iloc[0] >= 2:
                signals.append(f"上升Demark警告(13计数: {target_data['Up_Count_13'].iloc[0]}/4)")
                signals_detected = True
            elif target_data['Up_Signal_13'].iloc[0]:
                signals.append("上升Demark13信号")
                signals_detected = True
                
            if target_data['Down_Count_9'].iloc[0] >= 6:
                signals.append(f"下降Demark警告(9计数: {target_data['Down_Count_9'].iloc[0]}/9)")
                signals_detected = True
            elif target_data['Down_Signal_9'].iloc[0]:
                signals.append("下降Demark9信号")
                signals_detected = True
                
            if target_data['Down_Count_13'].iloc[0] >= 2:
                signals.append(f"下降Demark警告(13计数: {target_data['Down_Count_13'].iloc[0]}/4)")
                signals_detected = True
            elif target_data['Down_Signal_13'].iloc[0]:
                signals.append("下降Demark13信号")
                signals_detected = True
                
            if signals:
                info_print("\nDemark信号:")
                for signal in signals:
                    info_print(f"- {signal}")
            else:
                info_print("\n当前未形成完整的Demark信号")
            
            # 输出趋势分析
            up_count = target_data['Up_Count_9'].iloc[0] + target_data['Up_Count_13'].iloc[0]
            down_count = target_data['Down_Count_9'].iloc[0] + target_data['Down_Count_13'].iloc[0]
            
            if up_count > down_count:
                info_print("趋势分析: 上升趋势占优")
            elif down_count > up_count:
                info_print("趋势分析: 下降趋势占优")
            else:
                info_print("趋势分析: 趋势不明显")
            
            # 输出价格位置
            if target_data['Close'].iloc[0] > target_data['Close_4d_ago'].iloc[0]:
                info_print(f"价格位置: 当前价格高于4天前价格 (+{target_data['Close'].iloc[0] - target_data['Close_4d_ago'].iloc[0]:.2f})")
            else:
                info_print(f"价格位置: 当前价格低于4天前价格 ({target_data['Close'].iloc[0] - target_data['Close_4d_ago'].iloc[0]:.2f})")
        
        except Exception as e:
            debug_print(f"发生错误: {e}")
    except Exception as e:
        debug_print(f"发生错误: {e}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Demark指标分析工具')
    parser.add_argument('args', nargs='+', help='股票代码和日期参数（日期可选，支持YYYY-MM-DD、YYYY.MM.DD、YYYY/MM/DD、YYYYMMDD格式）')
    
    args = parser.parse_args()
    
    try:
        # 验证并标准化参数
        normalized_codes, analysis_date = validate_and_normalize_params(args.args)
        
        # 分析每个股票
        for stock_code in normalized_codes:
            try:
                check_demark(stock_code, analysis_date)
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