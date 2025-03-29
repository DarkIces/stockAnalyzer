#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import io
import numpy as np
from pathlib import Path
import re
import argparse
from typing import Dict, List, Tuple
import pandas as pd
from datetime import datetime, timedelta
from fetch_history import fetch_stock_history

def log_message(msg, level='INFO', file=sys.stdout, show_timestamp=True):
    """统一的日志输出函数"""
    if show_timestamp:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [{level}] {msg}", file=file, flush=True)
    else:
        print(msg, file=file, flush=True)

def debug_print(msg):
    """打印调试信息"""
    if hasattr(debug_print, 'enabled') and debug_print.enabled:
        log_message(msg, level='DEBUG', file=sys.stderr)

# 权重配置
WEIGHTS = {
    'price_momentum': 0.20,  # 价格动量
    'volume': 0.15,         # 成交量
    'trend': 0.25,         # 趋势（PSAR + MA）
    'oscillators': 0.25,    # 震荡指标（RSI + KDJ）
    'volatility': 0.15      # 波动性（布林带）
}

# 历史数据配置
HISTORY_DAYS = 60  # 历史数据天数
MARKET_INDICES = ['SPY', 'QQQ', 'DIA']  # 市场指数

class TradingHeatScorer:
    """股票交易热度评分系统"""
    
    def __init__(self):
        """初始化评分系统"""
        self.current_dir = Path(__file__).parent
        self.cache_dir = self.current_dir / 'cache/history'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def ensure_data_exists(self, symbol, start_date=None, end_date=None):
        """确保数据存在且是最新的"""
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
            
        cache_file = self.cache_dir / f"{symbol}.csv"
        
        # 如果文件不存在，获取数据
        if not cache_file.exists():
            log_message(f"缓存文件不存在，获取{symbol}的历史数据...")
            success = fetch_stock_history(symbol, start_date, end_date, False)
            if not success:
                raise Exception(f"获取{symbol}的历史数据失败")
            return
        
        # 检查数据是否最新
        try:
            df = pd.read_csv(cache_file)
            if 'Date' not in df.columns:
                raise Exception("数据文件格式错误：没有Date列")
            
            latest_date = pd.to_datetime(df['Date'], utc=True).max()
            target_date = pd.to_datetime(end_date, utc=True)
            
            # 如果数据不是最新的，追加获取
            if latest_date < target_date:
                log_message(f"数据不是最新的（最新：{latest_date.strftime('%Y-%m-%d')}），更新{symbol}的历史数据...")
                new_start_date = (latest_date + timedelta(days=1)).strftime('%Y-%m-%d')
                success = fetch_stock_history(symbol, new_start_date, end_date, True)
                if not success:
                    raise Exception(f"更新{symbol}的历史数据失败")
        except Exception as e:
            log_message(f"检查数据时出错：{str(e)}")
            log_message("重新获取完整数据...")
            success = fetch_stock_history(symbol, start_date, end_date, False)
            if not success:
                raise Exception(f"获取{symbol}的历史数据失败")
    
    def calculate_technical_indicators(self, df):
        """计算技术指标"""
        # 确保价格数据精度
        df['Close'] = df['Close'].round(6)
        df['High'] = df['High'].round(6)
        df['Low'] = df['Low'].round(6)
        
        # 计算价格变化百分比
        df['price_change'] = (df['Close'].pct_change() * 100).round(6)
        
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
            df[f'RSI{period}'] = rsi.round(6)
        
        # 计算KDJ
        low_9 = df['Low'].rolling(window=9, min_periods=9).min()
        high_9 = df['High'].rolling(window=9, min_periods=9).max()
        close_low = df['Close'] - low_9
        high_low = high_9 - low_9
        
        # 处理分母为0的情况
        rsv = close_low / high_low * 100
        rsv = rsv.where(high_low != 0, np.nan)
        
        # 计算KDJ
        k = rsv.rolling(window=3, min_periods=3).mean()
        d = k.rolling(window=3, min_periods=3).mean()
        j = 3 * k - 2 * d
        
        df['K'] = k.round(6)
        df['D'] = d.round(6)
        df['J'] = j.round(6)
        
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
    
    def load_data(self, symbol, days=30):
        """加载指定天数的历史数据并计算技术指标"""
        cache_file = self.cache_dir / f"{symbol}.csv"
        if not cache_file.exists():
            raise Exception(f"找不到{symbol}的历史数据文件")
        
        # 读取原始数据
        df = pd.read_csv(cache_file)
        df['Date'] = pd.to_datetime(df['Date'], utc=True)
        df = df.sort_values('Date').reset_index(drop=True)
        
        # 只保留最近的days天数据
        if len(df) > days:
            df = df.tail(days)
        
        # 计算技术指标
        df = self.calculate_technical_indicators(df)
        
        return df
    
    def calculate_rsi_score(self, df):
        """计算RSI评分（总权重：30%）"""
        scores = {}
        
        # 计算RSI值（使用calculate_technical_indicators中计算的值）
        rsi_6 = df['RSI_6'].iloc[-1]
        rsi_12 = df['RSI_12'].iloc[-1]
        rsi_24 = df['RSI_24'].iloc[-1]
        
        # RSI 6评分（权重：10%）
        if pd.isna(rsi_6):
            scores['rsi_6'] = 0
        else:
            if rsi_6 > 80:  # 严重超买
                scores['rsi_6'] = 20
            elif rsi_6 > 70:  # 超买
                scores['rsi_6'] = 40
            elif rsi_6 > 30:  # 正常
                scores['rsi_6'] = 60
            elif rsi_6 > 20:  # 超卖
                scores['rsi_6'] = 80
            else:  # 严重超卖
                scores['rsi_6'] = 100
        
        # RSI 12评分（权重：10%）
        if pd.isna(rsi_12):
            scores['rsi_12'] = 0
        else:
            if rsi_12 > 80:
                scores['rsi_12'] = 20
            elif rsi_12 > 70:
                scores['rsi_12'] = 40
            elif rsi_12 > 30:
                scores['rsi_12'] = 60
            elif rsi_12 > 20:
                scores['rsi_12'] = 80
            else:
                scores['rsi_12'] = 100
        
        # RSI 24评分（权重：10%）
        if pd.isna(rsi_24):
            scores['rsi_24'] = 0
        else:
            if rsi_24 > 80:
                scores['rsi_24'] = 20
            elif rsi_24 > 70:
                scores['rsi_24'] = 40
            elif rsi_24 > 30:
                scores['rsi_24'] = 60
            elif rsi_24 > 20:
                scores['rsi_24'] = 80
            else:
                scores['rsi_24'] = 100
        
        # 计算加权得分
        final_score = (
            scores['rsi_6'] * 0.1 +
            scores['rsi_12'] * 0.1 +
            scores['rsi_24'] * 0.1
        )
        
        return final_score, scores
    
    def calculate_kdj_score(self, df):
        """计算KDJ评分（总权重：30%）"""
        scores = {}
        
        # 获取KDJ值（使用calculate_technical_indicators中计算的值）
        k = df['K'].iloc[-1]
        d = df['D'].iloc[-1]
        j = df['J'].iloc[-1]
        
        # K值评分（权重：10%）
        if pd.isna(k):
            scores['k'] = 0
        else:
            if k > 80:  # 超买
                scores['k'] = 20
            elif k > 70:
                scores['k'] = 40
            elif k > 30:
                scores['k'] = 60
            elif k > 20:
                scores['k'] = 80
            else:  # 超卖
                scores['k'] = 100
        
        # D值评分（权重：10%）
        if pd.isna(d):
            scores['d'] = 0
        else:
            if d > 80:
                scores['d'] = 20
            elif d > 70:
                scores['d'] = 40
            elif d > 30:
                scores['d'] = 60
            elif d > 20:
                scores['d'] = 80
            else:
                scores['d'] = 100
        
        # J值评分（权重：10%）
        if pd.isna(j):
            scores['j'] = 0
        else:
            if j > 100:  # 极度超买
                scores['j'] = 0
            elif j > 80:
                scores['j'] = 20
            elif j > 70:
                scores['j'] = 40
            elif j > 30:
                scores['j'] = 60
            elif j > 20:
                scores['j'] = 80
            elif j > 0:
                scores['j'] = 100
            else:  # 极度超卖
                scores['j'] = 100
        
        # 计算加权得分
        final_score = (
            scores['k'] * 0.1 +
            scores['d'] * 0.1 +
            scores['j'] * 0.1
        )
        
        return final_score, scores
    
    def calculate_trend_score(self, df):
        """计算趋势评分（总权重：25%）"""
        scores = {}
        
        # 计算不同周期的价格变化率
        price_changes = {
            'short': df['Close'].pct_change(periods=3).iloc[-1],  # 3天（权重：10%）
            'medium': df['Close'].pct_change(periods=7).iloc[-1],  # 7天（权重：8%）
            'long': df['Close'].pct_change(periods=14).iloc[-1]   # 14天（权重：7%）
        }
        
        # 评分标准
        for period, change in price_changes.items():
            if pd.isna(change):
                scores[period] = 0
            else:
                change_percent = change * 100
                if change_percent > 15:  # 强势上涨
                    scores[period] = 90
                elif change_percent > 10:  # 中度上涨
                    scores[period] = 75
                elif change_percent > 5:  # 小幅上涨
                    scores[period] = 60
                elif change_percent > -5:  # 震荡
                    scores[period] = 50
                elif change_percent > -10:  # 小幅下跌
                    scores[period] = 40
                elif change_percent > -15:  # 中度下跌
                    scores[period] = 25
                else:  # 强势下跌
                    scores[period] = 10
        
        # 计算趋势强度（基于斜率）
        ma_slopes = {}
        for ma_period in [5, 10, 20, 60]:
            ma = df['Close'].rolling(window=ma_period).mean()
            if len(ma) >= 2:
                slope = (ma.iloc[-1] - ma.iloc[-2]) / ma.iloc[-2] * 100
                ma_slopes[f'MA{ma_period}'] = slope
        
        # 计算趋势强度得分
        trend_strength = 0
        if ma_slopes:
            # 计算短期和长期趋势
            short_trend = np.mean([ma_slopes.get('MA5', 0), ma_slopes.get('MA10', 0)])
            long_trend = np.mean([ma_slopes.get('MA20', 0), ma_slopes.get('MA60', 0)])
            
            if short_trend > 1 and long_trend > 0.5:  # 强势上涨
                trend_strength = 15
            elif short_trend > 0.5 and long_trend > 0:  # 上涨
                trend_strength = 10
            elif short_trend < -1 and long_trend < -0.5:  # 强势下跌
                trend_strength = -15
            elif short_trend < -0.5 and long_trend < 0:  # 下跌
                trend_strength = -10
        
        # 计算加权得分
        base_score = (
            scores['short'] * 0.10 +
            scores['medium'] * 0.08 +
            scores['long'] * 0.07
        )
        
        # 应用趋势强度调整
        final_score = max(10, min(90, base_score + trend_strength))
        
        return final_score, scores
    
    def calculate_volume_score(self, df):
        """计算成交量评分（总权重：30%）"""
        scores = {}
        
        # 计算成交量变化（权重：15%）
        volume = df['Volume'].iloc[-1]
        volume_ma5 = df['Volume'].rolling(window=5).mean().iloc[-1]
        volume_ma20 = df['Volume'].rolling(window=20).mean().iloc[-1]
        
        # 与5日均量比较（权重：7.5%）
        if pd.isna(volume) or pd.isna(volume_ma5):
            scores['volume_ma5'] = 0
        else:
            ratio_ma5 = volume / volume_ma5 * 100
            if ratio_ma5 > 300:  # 大幅放量
                scores['volume_ma5'] = 90
            elif ratio_ma5 > 200:  # 中度放量
                scores['volume_ma5'] = 75
            elif ratio_ma5 > 150:  # 小幅放量
                scores['volume_ma5'] = 60
            elif ratio_ma5 > 80:  # 正常
                scores['volume_ma5'] = 50
            elif ratio_ma5 > 50:  # 小幅缩量
                scores['volume_ma5'] = 40
            elif ratio_ma5 > 30:  # 中度缩量
                scores['volume_ma5'] = 35
            else:  # 大幅缩量
                scores['volume_ma5'] = 25
        
        # 与20日均量比较（权重：7.5%）
        if pd.isna(volume) or pd.isna(volume_ma20):
            scores['volume_ma20'] = 0
        else:
            ratio_ma20 = volume / volume_ma20 * 100
            if ratio_ma20 > 300:
                scores['volume_ma20'] = 90
            elif ratio_ma20 > 200:
                scores['volume_ma20'] = 75
            elif ratio_ma20 > 150:
                scores['volume_ma20'] = 60
            elif ratio_ma20 > 80:
                scores['volume_ma20'] = 50
            elif ratio_ma20 > 50:
                scores['volume_ma20'] = 40
            elif ratio_ma20 > 30:
                scores['volume_ma20'] = 35
            else:
                scores['volume_ma20'] = 25
        
        # 计算成交量趋势（权重：15%）
        volume_trend_5 = df['Volume'].pct_change(periods=5).iloc[-1]
        volume_trend_20 = df['Volume'].pct_change(periods=20).iloc[-1]
        
        # 5日成交量趋势（权重：7.5%）
        if pd.isna(volume_trend_5):
            scores['volume_trend_5'] = 0
        else:
            trend_5_percent = volume_trend_5 * 100
            if trend_5_percent > 200:
                scores['volume_trend_5'] = 90
            elif trend_5_percent > 100:
                scores['volume_trend_5'] = 75
            elif trend_5_percent > 50:
                scores['volume_trend_5'] = 60
            elif trend_5_percent > 0:
                scores['volume_trend_5'] = 50
            elif trend_5_percent > -30:
                scores['volume_trend_5'] = 40
            elif trend_5_percent > -50:
                scores['volume_trend_5'] = 35
            else:
                scores['volume_trend_5'] = 25
        
        # 20日成交量趋势（权重：7.5%）
        if pd.isna(volume_trend_20):
            scores['volume_trend_20'] = 0
        else:
            trend_20_percent = volume_trend_20 * 100
            if trend_20_percent > 200:
                scores['volume_trend_20'] = 90
            elif trend_20_percent > 100:
                scores['volume_trend_20'] = 75
            elif trend_20_percent > 50:
                scores['volume_trend_20'] = 60
            elif trend_20_percent > 0:
                scores['volume_trend_20'] = 50
            elif trend_20_percent > -30:
                scores['volume_trend_20'] = 40
            elif trend_20_percent > -50:
                scores['volume_trend_20'] = 35
            else:
                scores['volume_trend_20'] = 25
        
        # 计算加权得分
        final_score = (
            scores['volume_ma5'] * 0.075 +
            scores['volume_ma20'] * 0.075 +
            scores['volume_trend_5'] * 0.075 +
            scores['volume_trend_20'] * 0.075
        )
        
        return final_score, scores
    
    def calculate_volatility_score(self, df):
        """计算波动性评分（总权重：15%）"""
        scores = {}
        reasons = []
        
        # 计算布林带参数
        window = 20
        std_dev = 2
        
        # 计算布林带
        ma = df['Close'].rolling(window=window).mean()
        std = df['Close'].rolling(window=window).std()
        upper = ma + (std * std_dev)
        lower = ma - (std * std_dev)
        
        # 计算带宽
        bandwidth = ((upper - lower) / ma * 100).iloc[-1]
        
        # 获取最新价格
        current_price = df['Close'].iloc[-1]
        
        # 计算价格位置
        if pd.notna(current_price) and pd.notna(upper.iloc[-1]) and pd.notna(lower.iloc[-1]):
            price_position = (current_price - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1])
            
            # 基于价格位置的得分（权重：40%）
            if price_position > 1:  # 超过上轨
                scores['position'] = 90
                reasons.append("价格突破上轨")
            elif price_position > 0.8:
                scores['position'] = 75
                reasons.append("价格接近上轨")
            elif price_position > 0.6:
                scores['position'] = 60
                reasons.append("价格在上半区间")
            elif price_position > 0.4:
                scores['position'] = 50
                reasons.append("价格在中间区间")
            elif price_position > 0.2:
                scores['position'] = 40
                reasons.append("价格在下半区间")
            elif price_position > 0:
                scores['position'] = 25
                reasons.append("价格接近下轨")
            else:  # 低于下轨
                scores['position'] = 10
                reasons.append("价格跌破下轨")
        else:
            scores['position'] = 50
        
        # 带宽评分（权重：30%）
        if pd.notna(bandwidth):
            if bandwidth > 30:
                scores['bandwidth'] = 90
                reasons.append(f"带宽显著扩大 ({bandwidth:.1f}%)")
            elif bandwidth > 20:
                scores['bandwidth'] = 75
                reasons.append(f"带宽扩大 ({bandwidth:.1f}%)")
            elif bandwidth > 15:
                scores['bandwidth'] = 60
                reasons.append(f"带宽适中偏大 ({bandwidth:.1f}%)")
            elif bandwidth > 10:
                scores['bandwidth'] = 50
                reasons.append(f"带宽适中 ({bandwidth:.1f}%)")
            elif bandwidth > 5:
                scores['bandwidth'] = 40
                reasons.append(f"带宽适中偏小 ({bandwidth:.1f}%)")
            elif bandwidth > 3:
                scores['bandwidth'] = 25
                reasons.append(f"带宽收窄 ({bandwidth:.1f}%)")
            else:
                scores['bandwidth'] = 10
                reasons.append(f"带宽显著收窄 ({bandwidth:.1f}%)")
        else:
            scores['bandwidth'] = 50
        
        # 计算突破强度（权重：30%）
        if len(df) >= 2:
            prev_price = df['Close'].iloc[-2]
            prev_upper = upper.iloc[-2]
            prev_lower = lower.iloc[-2]
            
            # 检查是否发生突破
            if current_price > upper.iloc[-1] and prev_price <= prev_upper:
                scores['breakthrough'] = 90
                reasons.append("向上突破布林带")
            elif current_price < lower.iloc[-1] and prev_price >= prev_lower:
                scores['breakthrough'] = 10
                reasons.append("向下突破布林带")
            elif current_price > ma.iloc[-1] and prev_price <= ma.iloc[-2]:
                scores['breakthrough'] = 75
                reasons.append("向上突破中轨")
            elif current_price < ma.iloc[-1] and prev_price >= ma.iloc[-2]:
                scores['breakthrough'] = 25
                reasons.append("向下突破中轨")
            else:
                scores['breakthrough'] = 50
        else:
            scores['breakthrough'] = 50
        
        # 计算最终得分
        final_score = (
            scores['position'] * 0.4 +
            scores['bandwidth'] * 0.3 +
            scores['breakthrough'] * 0.3
        )
        
        return final_score, reasons
    
    def calculate_total_score(self, symbol, days=30):
        """计算总评分"""
        try:
            # 确保数据存在且是最新的
            self.ensure_data_exists(symbol)
            
            # 加载数据
            df = self.load_data(symbol, days)
            
            # 计算各项评分
            rsi_score, rsi_details = self.calculate_rsi_score(df)
            kdj_score, kdj_details = self.calculate_kdj_score(df)
            trend_score, trend_details = self.calculate_trend_score(df)
            volume_score, volume_details = self.calculate_volume_score(df)
            volatility_score, volatility_reasons = self.calculate_volatility_score(df)
            
            # 计算总分
            total_score = rsi_score + kdj_score + trend_score + volume_score + volatility_score
            
            # 准备评分详情
            score_details = {
                'symbol': symbol,
                'date': df['Date'].iloc[-1].strftime('%Y-%m-%d'),
                'total_score': round(total_score, 2),
                'rsi_score': round(rsi_score, 2),
                'kdj_score': round(kdj_score, 2),
                'trend_score': round(trend_score, 2),
                'volume_score': round(volume_score, 2),
                'volatility_score': round(volatility_score, 2),
                'details': {
                    'rsi': rsi_details,
                    'kdj': kdj_details,
                    'trend': trend_details,
                    'volume': volume_details,
                    'volatility': volatility_reasons
                }
            }
            
            return score_details
            
        except Exception as e:
            log_message(f"计算{symbol}的评分时出错：{str(e)}")
            return None

def sigmoid(x: float) -> float:
    """Sigmoid函数，用于归一化"""
    return 1 / (1 + np.exp(-x))

def normalize_score(score: float, min_score: float = 0, max_score: float = 100) -> float:
    """使用sigmoid函数进行归一化，并映射到指定区间"""
    # 将基准分数50映射到0
    adjusted_score = (score - 50) / 25  # 除以25使得分数变化更平滑
    sigmoid_val = sigmoid(adjusted_score)
    normalized = (sigmoid_val - 0.5) * 2  # 转换到[-1, 1]区间
    final_score = (normalized + 1) * (max_score - min_score) / 2 + min_score
    return round(final_score, 1)

def calculate_z_score(value: float, mean: float, std: float) -> float:
    """计算Z-Score"""
    if std == 0:
        return 0
    return (value - mean) / std

def load_historical_data(stock_code: str, days: int = HISTORY_DAYS) -> pd.DataFrame:
    """从MD文件中加载历史数据"""
    try:
        # 从cache目录加载MD文件
        cache_dir = Path('stockAnalyze/cache')
        today = datetime.now().strftime('%Y-%m-%d')
        md_file = cache_dir / today / f"{stock_code}.md"
        
        if not md_file.exists():
            return None
            
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 初始化数据字典
        data = {
            'date': [],
            'close': [],
            'volume': [],
            'RSI6': [],
            'RSI12': [],
            'RSI24': [],
            'K': [],
            'D': [],
            'J': [],
            'price_change': []
        }
        
        # 解析历史数据
        history_pattern = r'(\d{4}-\d{2}-\d{2}):\s*收盘价:\s*\$?([\d.]+)\s*成交量:\s*([\d.]+)\s*RSI\(6\):\s*([\d.]+)\s*RSI\(12\):\s*([\d.]+)\s*RSI\(24\):\s*([\d.]+)\s*K:\s*([\d.]+)\s*D:\s*([\d.]+)\s*J:\s*([\d.]+)\s*涨跌幅:\s*([+-]?[\d.]+)%'
        matches = re.finditer(history_pattern, content)
        
        for match in matches:
            date_str = match.group(1)
            close = float(match.group(2))
            volume = float(match.group(3))
            rsi6 = float(match.group(4))
            rsi12 = float(match.group(5))
            rsi24 = float(match.group(6))
            k = float(match.group(7))
            d = float(match.group(8))
            j = float(match.group(9))
            price_change = float(match.group(10))
            
            data['date'].append(date_str)
            data['close'].append(close)
            data['volume'].append(volume)
            data['RSI6'].append(rsi6)
            data['RSI12'].append(rsi12)
            data['RSI24'].append(rsi24)
            data['K'].append(k)
            data['D'].append(d)
            data['J'].append(j)
            data['price_change'].append(price_change)
        
        if not data['date']:
            return None
            
        # 创建DataFrame
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'], utc=True)
        df = df.sort_values('date')
        
        # 只保留最近N天的数据
        if len(df) > days:
            df = df.tail(days)
            
        return df
    except Exception as e:
        log_message(f"加载历史数据失败: {str(e)}", file=sys.stderr)
        return None

def calculate_dynamic_thresholds(df: pd.DataFrame) -> Dict:
    """计算动态阈值"""
    if df is None or len(df) < 20:
        return None
        
    thresholds = {
        'rsi': {
            'overbought': df['RSI6'].quantile(0.8),
            'oversold': df['RSI6'].quantile(0.2)
        },
        'kdj': {
            'overbought': df['J'].quantile(0.8),
            'oversold': df['J'].quantile(0.2)
        },
        'volume': {
            'high': df['volume'].quantile(0.8),
            'low': df['volume'].quantile(0.2)
        },
        'price_change': {
            'high': df['price_change'].quantile(0.8),
            'low': df['price_change'].quantile(0.2)
        }
    }
    return thresholds

def calculate_market_relative_score(stock_code: str, df: pd.DataFrame) -> float:
    """计算相对于市场的表现"""
    if df is None:
        return 50.0
        
    try:
        # 计算个股的收益率
        stock_return = df['close'].pct_change().mean() * 100
        
        # 计算市场指数的收益率
        market_returns = []
        for index in MARKET_INDICES:
            index_df = load_historical_data(index)
            if index_df is not None:
                market_returns.append(index_df['close'].pct_change().mean() * 100)
        
        if not market_returns:
            return 50.0
            
        # 计算相对表现
        market_return = np.mean(market_returns)
        relative_return = stock_return - market_return
        
        # 将相对表现转换为分数
        if relative_return > 2:
            return 100.0
        elif relative_return > 1:
            return 80.0
        elif relative_return > 0:
            return 60.0
        elif relative_return > -1:
            return 40.0
        elif relative_return > -2:
            return 20.0
        else:
            return 0.0
            
    except Exception as e:
        log_message(f"计算市场相对表现失败: {str(e)}", file=sys.stderr)
        return 50.0

def calculate_price_momentum(data: Dict) -> Tuple[float, List[str]]:
    """计算价格动量分数"""
    score = 50
    reasons = []
    
    # 日涨跌幅
    price_change = data['price_change']
    if price_change > 2:
        score += 20
        reasons.append(f"大幅上涨 ({price_change:.2f}%)")
    elif price_change > 0:
        score += 10
        reasons.append(f"小幅上涨 ({price_change:.2f}%)")
    elif price_change < -2:
        score -= 20
        reasons.append(f"大幅下跌 ({price_change:.2f}%)")
    elif price_change < 0:
        score -= 10
        reasons.append(f"小幅下跌 ({price_change:.2f}%)")
    
    # MA差距
    ma_weights = {'MA20': 0.4, 'MA50': 0.3, 'MA120': 0.2, 'MA200': 0.1}
    ma_score = 0
    for ma, weight in ma_weights.items():
        if ma in data['ma_diffs']:
            diff = data['ma_diffs'][ma]
            ma_score += diff * weight
            if abs(diff) > 5:
                reasons.append(f"{ma}差距显著 ({diff:.2f}%)")
    
    score += ma_score * 10
    
    return normalize_score(score, 0, 100), reasons

def calculate_volume_score(data: Dict) -> Tuple[float, List[str]]:
    """计算成交量分数"""
    score = 50
    reasons = []
    
    volume_status = data['volume_status']
    if '显著放量' in volume_status:
        score += 25
        reasons.append("成交量显著放大")
    elif '放量' in volume_status:
        score += 15
        reasons.append("成交量放大")
    elif '显著缩量' in volume_status:
        score -= 25
        reasons.append("成交量显著萎缩")
    elif '缩量' in volume_status:
        score -= 15
        reasons.append("成交量萎缩")
    
    return normalize_score(score, 0, 100), reasons

def calculate_trend_score(data: Dict) -> Tuple[float, List[str]]:
    """计算趋势分数"""
    score = 50
    reasons = []
    
    # PSAR趋势
    if data['psar_trend'] == '上升趋势':
        base_score = 10
        if data['psar_strength'] == '强':
            base_score += 10
        elif data['psar_strength'] == '中等':
            base_score += 5
        if data['psar_days'] > 10:
            base_score += 5
        score += base_score
        reasons.append(f"{data['psar_strength']}势上升趋势 ({data['psar_days']}天)")
    elif data['psar_trend'] == '下降趋势':
        base_score = -10
        if data['psar_strength'] == '强':
            base_score -= 10
        elif data['psar_strength'] == '中等':
            base_score -= 5
        if data['psar_days'] > 10:
            base_score -= 5
        score += base_score
        reasons.append(f"{data['psar_strength']}势下降趋势 ({data['psar_days']}天)")
    
    # 均线排列
    ma_trend = data['ma_trend']
    if ma_trend == '多头排列':
        score += 20
        reasons.append("均线多头排列")
    elif ma_trend == '空头排列':
        score -= 20
        reasons.append("均线空头排列")
    elif ma_trend == '均线纠缠':
        score -= 5
        reasons.append("均线交织")
    
    return normalize_score(score, 0, 100), reasons

def calculate_oscillator_score(data: Dict) -> Tuple[float, List[str]]:
    """计算震荡指标分数"""
    score = 50
    reasons = []
    
    # RSI
    rsi = data['rsi']
    rsi6, rsi12, rsi24 = rsi['RSI6'], rsi['RSI12'], rsi['RSI24']
    
    # RSI6权重最大
    if rsi6 > 80:
        score += 15
        reasons.append(f"RSI(6)超买 ({rsi6:.1f})")
    elif rsi6 < 20:
        score -= 15
        reasons.append(f"RSI(6)超卖 ({rsi6:.1f})")
    
    # RSI12和RSI24作为确认
    if rsi12 > 70 and rsi24 > 60:
        score += 10
        reasons.append("RSI多周期超买确认")
    elif rsi12 < 30 and rsi24 < 40:
        score -= 10
        reasons.append("RSI多周期超卖确认")
    
    # KDJ
    kdj = data['kdj']
    k, d, j = kdj['K'], kdj['D'], kdj['J']
    
    if j > 100:
        score += 15
        reasons.append(f"KDJ超买 (J={j:.1f})")
    elif j < 0:
        score -= 15
        reasons.append(f"KDJ超卖 (J={j:.1f})")
    
    if kdj['status'] == '严重超买':
        score += 10
        reasons.append("KDJ严重超买")
    elif kdj['status'] == '严重超卖':
        score -= 10
        reasons.append("KDJ严重超卖")
    
    # 背离信号
    if kdj['divergence'] == '顶背离':
        score -= 20
        reasons.append("KDJ顶背离")
    elif kdj['divergence'] == '底背离':
        score += 20
        reasons.append("KDJ底背离")
    
    return normalize_score(score, 0, 100), reasons

def calculate_volatility_score(data: Dict) -> Tuple[float, List[str]]:
    """计算波动性分数"""
    score = 50
    reasons = []
    
    # 布林带状态
    status = data['bollinger_status']
    if status == '超买区间':
        score += 15
        reasons.append("布林带超买")
    elif status == '超卖区间':
        score -= 15
        reasons.append("布林带超卖")
    
    # 布林带突破
    breakthrough = data.get('bollinger_breakthrough', '无')
    if breakthrough == '向上突破':
        score += 20
        reasons.append("布林带向上突破")
    elif breakthrough == '向下突破':
        score -= 20
        reasons.append("布林带向下突破")
    
    # 布林带带宽
    bandwidth = data.get('bollinger_bandwidth', 0)
    if bandwidth > 20:
        score -= 15
        reasons.append(f"布林带带宽过大 ({bandwidth:.1f}%)")
    elif bandwidth < 10:
        score += 10
        reasons.append(f"布林带带宽收窄 ({bandwidth:.1f}%)")
    
    return normalize_score(score, 0, 100), reasons

def get_score_description(score: float) -> str:
    """获取分数说明"""
    if score >= 90:
        return "极度强势，可能存在过热风险"
    elif score >= 80:
        return "强势，注意回调风险"
    elif score >= 70:
        return "偏强，可以关注"
    elif score >= 60:
        return "中性偏强"
    elif score >= 45:
        return "中性"
    elif score >= 35:
        return "中性偏弱"
    elif score >= 25:
        return "偏弱，可以关注"
    elif score >= 15:
        return "弱势，注意反弹机会"
    else:
        return "极度弱势，可能存在超跌机会"

def calculate_final_score(components: Dict[str, Tuple[float, List[str]]]) -> Tuple[float, Dict]:
    """计算最终得分"""
    weighted_score = 0
    all_reasons = []
    component_scores = {}
    
    for name, (score, reasons) in components.items():
        weight = WEIGHTS.get(name, 0)
        weighted_score += score * weight
        all_reasons.extend(reasons)
        component_scores[name] = score
    
    final_score = round(weighted_score, 1)
    return final_score, {
        'description': get_score_description(final_score),
        'reasons': all_reasons,
        'components': component_scores
    }

def parse_md_file(file_path):
    """解析MD文件内容，提取关键信息"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 初始化数据字典
    data = {
        'price_change': 0.0,
        'volume_status': '正常',
        'psar_trend': '未知',
        'psar_strength': '弱',
        'psar_days': 0,
        'ma_trend': '混乱排列',
        'ma_diffs': {},
        'bollinger_status': '正常波动区间',
        'bollinger_breakthrough': '无',
        'bollinger_bandwidth': 0,
        'kdj': {
            'K': 0.0,
            'D': 0.0,
            'J': 0.0,
            'status': '正常',
            'divergence': None
        },
        'rsi': {
            'RSI6': 0.0,
            'RSI12': 0.0,
            'RSI24': 0.0,
            'status': '正常',
            'divergence': None
        }
    }
    
    # 解析日涨跌幅
    change_match = re.search(r'日涨跌幅: ([+-]?[\d.]+)%', content)
    if change_match:
        data['price_change'] = float(change_match.group(1))
    
    # 解析成交量状态
    volume_match = re.search(r'成交量: \[(.+?)\]', content)
    if volume_match:
        data['volume_status'] = volume_match.group(1).strip()
    
    # 解析PSAR信息
    psar_trend_match = re.search(r'PSAR: \[(.+?)\]', content)
    if psar_trend_match:
        trend_text = psar_trend_match.group(1)
        if '上升趋势' in trend_text:
            data['psar_trend'] = '上升趋势'
        elif '下降趋势' in trend_text:
            data['psar_trend'] = '下降趋势'
        
        if '强' in trend_text:
            data['psar_strength'] = '强'
        elif '中等' in trend_text:
            data['psar_strength'] = '中等'
        
        days_match = re.search(r'(\d+)天', trend_text)
        if days_match:
            data['psar_days'] = int(days_match.group(1))
    
    # 解析均线排列
    ma_trend_match = re.search(r'均线排列: \[(.+?)\]', content)
    if ma_trend_match:
        data['ma_trend'] = ma_trend_match.group(1).strip()
    
    # 解析均线差距
    ma_diffs_matches = re.findall(r'MA(\d+): \[(?:低于|高于)MA\d+:(?:[ ]*([\d.]+)%?)?\]', content)
    for ma_num, diff_str in ma_diffs_matches:
        diff = float(diff_str) if diff_str else 0.0
        data['ma_diffs'][f'MA{ma_num}'] = diff
    
    # 解析布林带信息
    bollinger_status_match = re.search(r'市场状态: (.+?)(?=\n|$)', content)
    if bollinger_status_match:
        data['bollinger_status'] = bollinger_status_match.group(1).strip()
    
    bollinger_breakthrough_match = re.search(r'突破状态: (.+?)(?=\n|$)', content)
    if bollinger_breakthrough_match:
        data['bollinger_breakthrough'] = bollinger_breakthrough_match.group(1).strip()
    
    bandwidth_match = re.search(r'带宽: ([\d.]+)%', content)
    if bandwidth_match:
        data['bollinger_bandwidth'] = float(bandwidth_match.group(1))
    
    # 解析KDJ信息
    k_match = re.search(r'K值: ([\d.]+)', content)
    d_match = re.search(r'D值: ([\d.]+)', content)
    j_match = re.search(r'J值: ([\d.]+)', content)
    
    if k_match:
        data['kdj']['K'] = float(k_match.group(1))
    if d_match:
        data['kdj']['D'] = float(d_match.group(1))
    if j_match:
        data['kdj']['J'] = float(j_match.group(1))
    
    kdj_status_match = re.search(r'KDJ: \[(.+?)\]', content)
    if kdj_status_match:
        status_text = kdj_status_match.group(1)
        if '严重超买' in status_text:
            data['kdj']['status'] = '严重超买'
        elif '严重超卖' in status_text:
            data['kdj']['status'] = '严重超卖'
        elif '超买' in status_text:
            data['kdj']['status'] = '超买'
        elif '超卖' in status_text:
            data['kdj']['status'] = '超卖'
        if '顶背离' in status_text:
            data['kdj']['divergence'] = '顶背离'
        elif '底背离' in status_text:
            data['kdj']['divergence'] = '底背离'
    
    # 解析RSI信息
    rsi6_match = re.search(r'RSI\(6\): ([\d.]+)', content)
    rsi12_match = re.search(r'RSI\(12\): ([\d.]+)', content)
    rsi24_match = re.search(r'RSI\(24\): ([\d.]+)', content)
    
    if rsi6_match:
        data['rsi']['RSI6'] = float(rsi6_match.group(1))
    if rsi12_match:
        data['rsi']['RSI12'] = float(rsi12_match.group(1))
    if rsi24_match:
        data['rsi']['RSI24'] = float(rsi24_match.group(1))
    
    rsi_status_match = re.search(r'RSI: \[(.+?)\]', content)
    if rsi_status_match:
        status_text = rsi_status_match.group(1)
        if '严重超买' in status_text:
            data['rsi']['status'] = '严重超买'
        elif '严重超卖' in status_text:
            data['rsi']['status'] = '严重超卖'
        elif '超买' in status_text:
            data['rsi']['status'] = '超买'
        elif '超卖' in status_text:
            data['rsi']['status'] = '超卖'
        if '顶背离' in status_text:
            data['rsi']['divergence'] = '顶背离'
        elif '底背离' in status_text:
            data['rsi']['divergence'] = '底背离'
    
    return data

def parse_csv_file(file_path):
    """解析CSV文件内容，提取关键信息"""
    try:
        df = pd.read_csv(file_path)
        df['Date'] = pd.to_datetime(df['Date'], utc=True)
        df = df.sort_values('Date')
        
        # 获取最新一天的数据
        latest = df.iloc[-1]
        
        # 计算价格变化
        price_change = latest['price_change'] if 'price_change' in df.columns else 0.0
        
        # 计算成交量状态
        volume_ma5 = df['volume'].rolling(window=5).mean()
        volume_ma20 = df['volume'].rolling(window=20).mean()
        latest_volume = df['volume'].iloc[-1]
        
        if latest_volume > volume_ma20.iloc[-1] * 2:
            volume_status = '显著放量'
        elif latest_volume > volume_ma20.iloc[-1] * 1.5:
            volume_status = '放量'
        elif latest_volume < volume_ma20.iloc[-1] * 0.5:
            volume_status = '显著缩量'
        elif latest_volume < volume_ma20.iloc[-1] * 0.8:
            volume_status = '缩量'
        else:
            volume_status = '正常'
        
        # 初始化数据字典
        data = {
            'price_change': price_change,
            'volume_status': volume_status,
            'psar_trend': '上升趋势' if price_change > 0 else '下降趋势',
            'psar_strength': '强' if abs(price_change) > 2 else '中等' if abs(price_change) > 1 else '弱',
            'psar_days': 1,  # 简化处理
            'ma_trend': '多头排列' if price_change > 0 else '空头排列',
            'ma_diffs': {},
            'bollinger_status': '超买区间' if price_change > 2 else '超卖区间' if price_change < -2 else '正常波动区间',
            'bollinger_breakthrough': '向上突破' if price_change > 2 else '向下突破' if price_change < -2 else '无',
            'bollinger_bandwidth': 10,  # 简化处理
            'kdj': {
                'K': latest['K'],
                'D': latest['D'],
                'J': latest['J'],
                'status': '正常',
                'divergence': None
            },
            'rsi': {
                'RSI6': latest['RSI6'],
                'RSI12': latest['RSI12'],
                'RSI24': latest['RSI24'],
                'status': '正常',
                'divergence': None
            }
        }
        
        # 设置KDJ状态
        if data['kdj']['J'] > 100:
            data['kdj']['status'] = '严重超买'
        elif data['kdj']['J'] > 80:
            data['kdj']['status'] = '超买'
        elif data['kdj']['J'] < 0:
            data['kdj']['status'] = '严重超卖'
        elif data['kdj']['J'] < 20:
            data['kdj']['status'] = '超卖'
        
        # 设置RSI状态
        if data['rsi']['RSI6'] > 80:
            data['rsi']['status'] = '严重超买'
        elif data['rsi']['RSI6'] > 70:
            data['rsi']['status'] = '超买'
        elif data['rsi']['RSI6'] < 20:
            data['rsi']['status'] = '严重超卖'
        elif data['rsi']['RSI6'] < 30:
            data['rsi']['status'] = '超卖'
        
        return data
    except Exception as e:
        debug_print(f"解析CSV文件时出错：{str(e)}")
        raise

def process_file(file_path):
    """处理单个文件并返回评分结果"""
    try:
        debug_print(f"开始处理文件：{file_path}")
        
        # 只处理md文件
        if file_path.suffix.lower() != '.md':
            raise Exception(f"不支持的文件格式：{file_path.suffix}，只支持.md文件")
            
        # 从文件路径获取日期和股票代码
        # 预期路径格式: .../cache/YYYY-MM-DD/STOCK_CODE.md
        date_str = file_path.parent.name
        stock_code = file_path.stem
        target_date = pd.to_datetime(date_str, utc=True)
        
        # 使用前一天作为历史数据的截止日期
        history_end_date = (target_date - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        debug_print(f"处理日期：{date_str}，使用历史数据截止日期：{history_end_date}，股票代码：{stock_code}")
        
        # 检查历史数据
        history_cache_dir = Path(__file__).parent / 'cache/history'
        history_file = history_cache_dir / f"{stock_code}.csv"
        
        # 确保历史数据目录存在
        history_cache_dir.mkdir(parents=True, exist_ok=True)
        
        need_update = False
        start_date = None
        
        if not history_file.exists():
            debug_print(f"历史数据文件不存在：{history_file}")
            need_update = True
            start_date = "2024-01-01"  # 如果文件不存在，从2024年1月1日开始
        else:
            try:
                df = pd.read_csv(history_file)
                if 'Date' not in df.columns:
                    debug_print("历史数据文件格式错误：没有Date列")
                    need_update = True
                    start_date = "2024-01-01"
                else:
                    df['Date'] = pd.to_datetime(df['Date'], utc=True)
                    latest_date = df['Date'].max()
                    history_end = pd.to_datetime(history_end_date, utc=True)
                    
                    if latest_date < history_end:
                        debug_print(f"历史数据不是最新的（最新：{latest_date.strftime('%Y-%m-%d')}，目标：{history_end_date}）")
                        need_update = True
                        # 如果文件存在，从最后日期开始更新
                        start_date = (latest_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
                        
            except Exception as e:
                debug_print(f"读取历史数据文件时出错：{str(e)}")
                need_update = True
                start_date = "2024-01-01"  # 如果文件读取出错，从2024年1月1日开始
        
        # 如果需要更新历史数据
        if need_update:
            debug_print(f"开始更新历史数据，起始日期：{start_date}，截止日期：{history_end_date}")
            success = fetch_stock_history(stock_code, start_date, history_end_date, True)  # 使用append模式
            if not success:
                raise Exception(f"获取{stock_code}的历史数据失败")
        
        # 解析MD文件数据
        data = parse_md_file(file_path)
        debug_print(f"解析数据：{data}")
        
        # 计算各组件得分
        components = calculate_component_scores(data)
        debug_print(f"计算组件分数：{components}")
        
        # 计算总分
        component_scores = {k: v[0] for k, v in components.items()}
        reasons = [reason for _, reasons in components.values() for reason in reasons]
        score = calculate_final_score(component_scores)
        debug_print(f"最终得分：{score}")
        
        # 确定评级描述
        description = get_score_description(score)
        
        result = {
            'file': stock_code,
            'score': score,
            'description': description,
            'reasons': reasons,
            'components': component_scores
        }
        debug_print(f"处理结果：{result}")
        return result
        
    except Exception as e:
        debug_print(f"处理文件时出错：{str(e)}")
        return {
            'file': file_path.stem,
            'score': None,
            'description': str(e),
            'reasons': [],
            'components': {}
        }

def calculate_component_scores(data):
    """计算各组件得分"""
    scores = {}
    
    # 价格动量得分 (20%)
    price_change = float(data['price_change'])
    if abs(price_change) > 5:
        momentum_score = 90 if price_change > 0 else 10
        change_desc = f"{'大幅上涨' if price_change > 0 else '大幅下跌'} ({price_change:.2f}%)"
    elif abs(price_change) > 2:
        momentum_score = 75 if price_change > 0 else 25
        change_desc = f"{'显著上涨' if price_change > 0 else '显著下跌'} ({price_change:.2f}%)"
    elif abs(price_change) > 1:
        momentum_score = 60 if price_change > 0 else 40
        change_desc = f"{'小幅上涨' if price_change > 0 else '小幅下跌'} ({price_change:.2f}%)"
    else:
        momentum_score = 50
        change_desc = f"横盘整理 ({price_change:.2f}%)"
    scores['price_momentum'] = (momentum_score, [change_desc])
    
    # 成交量得分 (15%)
    volume_score = {
        '显著放量': 90,
        '放量': 75,
        '正常': 50,
        '缩量': 35,
        '显著缩量': 20
    }.get(data['volume_status'], 50)
    scores['volume'] = (volume_score, [f"成交量{'放大' if volume_score > 50 else '萎缩' if volume_score < 50 else '正常'}"])
    
    # 趋势得分 (25%)
    trend_score, trend_details = self.calculate_trend_score(df)
    scores['trend'] = (trend_score, trend_details)
    
    # 震荡指标得分 (25%)
    oscillator_score, oscillator_reasons = self.calculate_oscillator_score(data)
    scores['oscillators'] = (oscillator_score, oscillator_reasons)
    
    # 波动性得分 (15%)
    volatility_score, volatility_reasons = self.calculate_volatility_score(df)
    scores['volatility'] = (volatility_score, volatility_reasons)
    
    return scores

def calculate_final_score(components):
    """计算最终得分"""
    weights = {
        'price_momentum': 0.20,
        'volume': 0.15,
        'trend': 0.25,
        'oscillators': 0.25,
        'volatility': 0.15
    }
    
    score = sum(float(components.get(k, 50)) * w for k, w in weights.items())
    return score

def get_score_description(score):
    """根据得分返回评级描述"""
    if score >= 90:
        return '极度强势'
    elif score >= 80:
        return '强势'
    elif score >= 70:
        return '偏强'
    elif score >= 60:
        return '中性偏强'
    elif score >= 45:
        return '中性'
    elif score >= 35:
        return '中性偏弱'
    elif score >= 25:
        return '偏弱'
    elif score >= 15:
        return '弱势'
    else:
        return '极度弱势'

def format_component_scores(components):
    """格式化分项得分"""
    result = []
    for name, score in components.items():
        if isinstance(score, (int, float, np.number)):
            formatted_name = {
                'price_momentum': '价格动量',
                'volume': '成交量',
                'trend': '趋势',
                'oscillators': '震荡指标',
                'volatility': '波动性'
            }.get(name, name)
            result.append(f"{formatted_name}: {float(score):.1f}")
    return '\n'.join(result)

def output_result(result, is_summary=False, is_table_row=False):
    """输出评分结果"""
    if result is None or result.get('score') is None:
        if is_table_row:
            return [result.get('file', 'N/A'), 'N/A', '处理失败', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        log_message("没有可用的评分结果", level='WARNING')
        return
    
    if is_table_row:
        # 输出表格行格式
        name_map = {
        'price_momentum': '价格动量',
        'volume': '成交量',
        'trend': '趋势',
        'oscillators': '震荡指标',
        'volatility': '波动性'
    }
        components = [f"{result['components'].get(k, 0):.1f}" for k in name_map.keys()]
        row = [
            result['file'],
            f"{result['score']:.1f}",
            result['description']
        ] + components
        return row
    
    if is_summary:
        # 输出简要信息
        log_message("-" * 50, show_timestamp=False)
        log_message(f"股票代码：{result['file']}", show_timestamp=False)
        log_message(f"总分：{result['score']:.1f} ({result['description']})", show_timestamp=False)
        log_message("组件得分：", show_timestamp=False)
        for name, score in result['components'].items():
            name_map = {
                'price_momentum': '价格动量',
                'volume': '成交量',
                'trend': '趋势',
                'oscillators': '震荡指标',
                'volatility': '波动性'
            }
            log_message(f"  - {name_map.get(name, name)}: {score:.1f}", show_timestamp=False)
        log_message("-" * 50, show_timestamp=False)
    else:
        # 输出详细信息
        log_message("=" * 50, show_timestamp=False)
        log_message(f"股票代码：{result['file']}", show_timestamp=False)
        log_message(f"总分：{result['score']:.1f}", show_timestamp=False)
        log_message(f"评级：{result['description']}", show_timestamp=False)
        log_message("-" * 30, show_timestamp=False)
        log_message("组件得分：", show_timestamp=False)
        for name, score in result['components'].items():
            name_map = {
                'price_momentum': '价格动量',
                'volume': '成交量',
                'trend': '趋势',
                'oscillators': '震荡指标',
                'volatility': '波动性'
            }
            log_message(f"  - {name_map.get(name, name)}: {score:.1f}", show_timestamp=False)
        log_message("-" * 30, show_timestamp=False)
        log_message("评分原因：", show_timestamp=False)
        for reason in result['reasons']:
            log_message(f"  - {reason}", show_timestamp=False)
        log_message("=" * 50, show_timestamp=False)

def print_table(results):
    """以表格形式打印结果"""
    # 表头
    headers = ['股票代码', '总分', '评级', '价格动量', '成交量', '趋势', '震荡指标', '波动性']
    
    # 获取每列的最大宽度
    widths = [len(h) * 2 for h in headers]  # 中文字符宽度为2
    rows = []
    for result in results:
        row = output_result(result, is_table_row=True)
        rows.append(row)
        for i, cell in enumerate(row):
            # 计算实际显示宽度（中文字符计为2个宽度）
            cell_width = sum(2 if ord(c) > 127 else 1 for c in str(cell))
            widths[i] = max(widths[i], cell_width)
    
    # 打印表头
    separator = '+' + '+'.join('-' * (w + 2) for w in widths) + '+'
    log_message(separator, show_timestamp=False)
    
    # 构建格式化字符串，考虑中文字符宽度
    header_cells = []
    for h, w in zip(headers, widths):
        padding = w - sum(2 if ord(c) > 127 else 1 for c in h)
        header_cells.append(h + ' ' * padding)
    header = '| ' + ' | '.join(header_cells) + ' |'
    log_message(header, show_timestamp=False)
    log_message(separator, show_timestamp=False)
    
    # 打印数据行
    for row in rows:
        row_cells = []
        for cell, w in zip(row, widths):
            cell_str = str(cell)
            padding = w - sum(2 if ord(c) > 127 else 1 for c in cell_str)
            row_cells.append(cell_str + ' ' * padding)
        data_row = '| ' + ' | '.join(row_cells) + ' |'
        log_message(data_row, show_timestamp=False)
    
    log_message(separator, show_timestamp=False)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='计算股票交易热度评分')
    parser.add_argument('path', help='股票数据文件或目录的路径', nargs='?')
    parser.add_argument('--debug', action='store_true', help='启用调试输出')
    parser.add_argument('--rules', action='store_true', help='显示评分规则')
    args = parser.parse_args()
    
    # 设置调试模式
    debug_print.enabled = args.debug
    
    # 显示评分规则
    if args.rules:
        log_message("=" * 60, show_timestamp=False)
        log_message("股票交易热度评分系统 - 评分规则说明", show_timestamp=False)
        log_message("=" * 60, show_timestamp=False)
        log_message("1. 价格动量 (20%权重):", show_timestamp=False)
        log_message("   - 日涨跌幅", show_timestamp=False)
        log_message("   - 均线位置关系", show_timestamp=False)
        log_message("2. 成交量 (15%权重):", show_timestamp=False)
        log_message("   - 成交量状态", show_timestamp=False)
        log_message("   - 与均线比较", show_timestamp=False)
        log_message("3. 趋势 (25%权重):", show_timestamp=False)
        log_message("   - PSAR趋势", show_timestamp=False)
        log_message("   - 均线排列", show_timestamp=False)
        log_message("4. 震荡指标 (25%权重):", show_timestamp=False)
        log_message("   - RSI指标", show_timestamp=False)
        log_message("   - KDJ指标", show_timestamp=False)
        log_message("   - 背离信号", show_timestamp=False)
        log_message("5. 波动性 (15%权重):", show_timestamp=False)
        log_message("   - 布林带状态", show_timestamp=False)
        log_message("   - 突破信号", show_timestamp=False)
        log_message("=" * 60, show_timestamp=False)
        log_message("最终分数说明:", show_timestamp=False)
        log_message("90-100: 极度强势，可能存在过热风险", show_timestamp=False)
        log_message("80-89: 强势，注意回调风险", show_timestamp=False)
        log_message("70-79: 偏强，可以关注", show_timestamp=False)
        log_message("60-69: 中性偏强", show_timestamp=False)
        log_message("45-59: 中性", show_timestamp=False)
        log_message("35-44: 中性偏弱", show_timestamp=False)
        log_message("25-34: 偏弱，可以关注", show_timestamp=False)
        log_message("15-24: 弱势，注意反弹机会", show_timestamp=False)
        log_message("0-14: 极度弱势，可能存在超跌机会", show_timestamp=False)
        log_message("=" * 60, show_timestamp=False)
        return
    
    # 如果没有提供路径参数且不是显示规则，显示帮助信息
    if not args.path:
        parser.print_help()
        return
    
    try:
        path = Path(args.path)
        log_message(f"处理路径：{path}")
        
        if not path.exists():
            raise Exception(f"路径不存在：{path}")
        
        if path.is_file():
            # 处理单个文件
            result = process_file(path)
            if debug_print.enabled:
                log_message(f"处理结果：{result}")
            output_result(result)
        else:
            # 处理目录
            files = list(path.glob('*.csv')) + list(path.glob('*.md'))
            if debug_print.enabled:
                log_message(f"找到的文件：{files}")
            
            if not files:
                raise Exception(f"目录中没有找到CSV或MD文件：{path}")
            
            results = []
            for file in files:
                result = process_file(file)
                if result:
                results.append(result)
            
            # 按股票代码排序
            results.sort(key=lambda x: x['file'])
            if debug_print.enabled:
                log_message(f"所有结果：{results}")
            
            # 输出结果
            log_message("\n评分结果汇总：", show_timestamp=False)
            print_table(results)
        
    except Exception as e:
        log_message(f"发生错误：{str(e)}", level='ERROR', file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main() 