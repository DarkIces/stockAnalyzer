# -*- coding: utf-8 -*-
import os
import sys
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import traceback
import markdown2
import re
import argparse
from pathlib import Path

# 添加父目录到Python路径
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.append(str(parent_dir))

from Utils.param_utils import validate_and_normalize_date

# 获取脚本所在目录的绝对路径
script_dir = Path(__file__).parent.parent
email_list_path = script_dir / 'Settings' / 'stock_analysis_email_list.txt'

def read_email_list(filename):
    """读取邮件列表，第一行为收件人，第二行为密送人"""
    # 获取脚本所在目录的绝对路径
    script_dir = Path(__file__).parent.parent
    email_list_path = script_dir / 'Settings' / filename
    
    with open(email_list_path, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]
        to_list = lines[0].split(',') if lines else []
        bcc_list = lines[1].split(',') if len(lines) > 1 else []
        return to_list, bcc_list

def read_report(date=None):
    """读取指定日期的报告内容"""
    analysis_date = date if date else datetime.now().strftime('%Y-%m-%d')
    # 获取脚本所在目录的绝对路径
    script_dir = Path(__file__).parent.parent
    report_path = script_dir / 'market_analysis' / f'market_analysis_{analysis_date}.md'
    
    if not report_path.exists():
        raise FileNotFoundError(f"找不到报告文件: {report_path}")
    
    with open(report_path, 'r', encoding='utf-8') as f:
        return f.read()

def get_html_style():
    """获取HTML样式"""
    return """
<style>
/* 全局样式 */
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

/* 表格样式 */
.stock-table {
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
    background-color: #fff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}

.stock-table th {
    background-color: #f8f9fa;
    padding: 12px;
    text-align: left;
    border-bottom: 2px solid #dee2e6;
    font-weight: 600;
}

.stock-table td {
    padding: 12px;
    border-bottom: 1px solid #dee2e6;
    vertical-align: top;
}

.stock-table tr:hover {
    background-color: #f8f9fa;
}

/* 股票代码和名称 */
.stock-code {
    font-weight: bold;
    color: #2c3e50;
    margin-bottom: 4px;
}

.stock-name {
    color: #666;
    font-size: 0.9em;
}

/* 价格和涨跌幅 */
.price {
    font-weight: bold;
    color: #2c3e50;
    margin-bottom: 4px;
}

.change {
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.9em;
    margin-bottom: 4px;
    font-weight: bold;
}

.price-up {
    color: #00b894;  /* 绿色 */
    background-color: rgba(0, 184, 148, 0.1);
}

.price-down {
    color: #d63031;  /* 红色 */
    background-color: rgba(255, 118, 117, 0.1);
}

.price-unchanged {
    color: #636e72;
    background-color: rgba(99, 110, 114, 0.1);
}

/* 成交量 */
.volume {
    color: #666;
    font-size: 0.9em;
    padding: 2px 6px;
    border-radius: 3px;
}

.volume-up {
    color: #d63031;
    background-color: rgba(255, 118, 117, 0.1);
}

.volume-down {
    color: #00b894;
    background-color: rgba(0, 184, 148, 0.1);
}

/* 指标样式 */
.indicator {
    margin-bottom: 4px;
}

.indicator-name {
    color: #666;
}

.indicator-value {
    font-weight: bold;
    color: #2c3e50;
}

.value-overbought {
    color: #d63031;
}

.value-oversold {
    color: #00b894;
}

/* PSAR指标 */
.psar {
    margin-bottom: 4px;
    padding: 2px 6px;
    border-radius: 3px;
    display: inline-block;
}

.trend-up {
    color: #00b894;  /* 绿色 */
    font-weight: bold;
}

.trend-down {
    color: #d63031;  /* 红色 */
    font-weight: bold;
}

.strength {
    color: #666;
    font-size: 0.9em;
    margin-left: 4px;
}

.strength-strong {
    color: #d63031;
    font-weight: bold;
}

.strength-weak {
    color: #00b894;
}

.strength-medium {
    color: #fdcb6e;
}

/* 百分比值 */
.percentage {
    padding: 2px 6px;
    border-radius: 3px;
    margin-bottom: 4px;
    font-weight: bold;
}

.value-positive {
    color: #00b894;  /* 绿色 */
    background-color: rgba(0, 184, 148, 0.1);
}

.value-negative {
    color: #d63031;  /* 红色 */
    background-color: rgba(255, 118, 117, 0.1);
}

.value-neutral {
    color: #636e72;
    background-color: rgba(99, 110, 114, 0.1);
}

/* 信号指标 */
.signal {
    padding: 2px 6px;
    border-radius: 3px;
    margin-bottom: 4px;
    font-weight: bold;
}

.signal-overbought {
    color: #d63031;
    background-color: rgba(255, 118, 117, 0.1);
}

.signal-oversold {
    color: #00b894;
    background-color: rgba(0, 184, 148, 0.1);
}

/* 文本内容 */
.text {
    margin-bottom: 4px;
    color: #2c3e50;
}

.text.value-positive {
    color: #00b894;  /* 绿色 */
    background-color: rgba(0, 184, 148, 0.1);
}

.text.value-negative {
    color: #d63031;  /* 红色 */
    background-color: rgba(255, 118, 117, 0.1);
}

/* 突破样式 */
.text.breakthrough {
    color: #2c3e50;  /* 黑色 */
    font-weight: bold;
}

/* 市场分析样式 */
.market-analysis-title {
    font-size: 1.2em;
    font-weight: bold;
    color: #2c3e50;
    margin: 20px 0 10px;
}

.market-analysis-item {
    margin: 10px 0;
    padding: 10px;
    background-color: #f8f9fa;
    border-radius: 4px;
}

.market-summary-title {
    font-size: 1.1em;
    font-weight: bold;
    color: #2c3e50;
    margin: 20px 0 10px;
}

/* 错误消息 */
.error-message {
    color: #d63031;
    padding: 10px;
    background-color: rgba(255, 118, 117, 0.1);
    border-radius: 4px;
    margin: 10px 0;
}

/* 响应式布局 */
@media (max-width: 768px) {
    .stock-table {
        display: block;
        overflow-x: auto;
        white-space: nowrap;
    }
    
    body {
        padding: 10px;
    }
}
</style>
"""

def generate_html_report(title, content):
    """生成HTML报告"""
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    {get_html_style()}
</head>
<body>
    <h1>{title}</h1>
    {content}
</body>
</html>
"""
    return html

def format_markdown_for_email(markdown_content):
    """将Markdown格式转换为HTML格式"""
    try:
        if not markdown_content:
            return '<p class="error-message">报告内容为空</p>'
            
        css = get_html_style()
        # 预处理表格
        lines = markdown_content.split('\n')
        processed_lines = []
        table_lines = []
        in_table = False
        
        for line in lines:
            line = line.strip()
            if not line:  # 跳过空行
                continue
                
            # 检测表格开始和结束
            if line.startswith('|'):
                if not in_table:
                    in_table = True
                    table_lines = []  # 清空表格行列表
                table_lines.append(line)
            elif line.startswith(('+', '=')):  # 忽略表格分隔行
                continue
            elif in_table:
                # 如果不是表格行且之前在表格中，说明表格结束
                if table_lines:
                    # 处理表格
                    table_html = process_table(table_lines)
                    processed_lines.append(table_html)
                    table_lines = []
                in_table = False
                if line:  # 如果当前行不为空，添加到处理后的行中
                    processed_lines.append(line)
            else:
                # 处理市场整体分析和市场综合判断部分
                if line.startswith('市场整体分析:'):
                    processed_lines.append('<div class="market-analysis-title">')
                    processed_lines.append(line)
                    processed_lines.append('</div>')
                elif line.startswith('市场综合判断:'):
                    processed_lines.append('<div class="market-summary-title">')
                    processed_lines.append(line)
                    processed_lines.append('</div>')
                elif line.startswith(('1.', '2.', '3.', '4.', '5.', '6.')):
                    processed_lines.append('<div class="market-analysis-item">')
                    processed_lines.append(line)
                    processed_lines.append('</div>')
                else:
                    processed_lines.append(line)
        
        # 处理最后一个表格（如果有）
        if table_lines:
            table_html = process_table(table_lines)
            processed_lines.append(table_html)
        
        # 将处理后的内容重新组合
        processed_content = '\n'.join(processed_lines)
        
        # 使用markdown2转换为HTML
        html_content = markdown2.markdown(processed_content, extras=['tables', 'fenced-code-blocks'])
        
        # 添加HTML样式
        html = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            {css}
        </head>
        <body>
            <div class="content">
                {html_content}
            </div>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        error_msg = f'处理Markdown内容时发生错误: {str(e)}\n{traceback.format_exc()}'
        return f'<p class="error-message">{error_msg}</p>'

def detect_table_structure(table_data):
    """检测表格结构，返回列数和每列的类型"""
    if not table_data:
        return 0, {}
        
    # 获取表头行
    header_line = table_data[0].strip()
    if header_line.startswith('|'):
        header_line = header_line[1:]
    if header_line.endswith('|'):
        header_line = header_line[:-1]
    headers = [h.strip() for h in header_line.split('|')]
    
    # 分析每列的类型
    column_types = {}
    for i, header in enumerate(headers):
        if '股票' in header:
            column_types[i] = 'stock'
        elif '走势' in header:
            column_types[i] = 'trend'
        elif 'MA' in header:
            column_types[i] = 'ma'
        elif '布林带' in header:
            column_types[i] = 'bollinger'
        elif 'PSAR' in header:
            column_types[i] = 'psar'
        elif 'KDJ' in header:
            column_types[i] = 'kdj'
        elif 'RSI' in header:
            column_types[i] = 'rsi'
        else:
            column_types[i] = 'text'
            
    return len(headers), column_types

def process_cell_content(cell_text, cell_type):
    """统一处理单元格内容"""
    try:
        if not cell_text or cell_text.isspace():
            return ''
            
        parts = []
        # 移除方括号并分割
        items = [item.strip() for item in cell_text.strip('[]').split('][')]
        
        for item in items:
            if not item:
                continue
                
            if cell_type == 'stock':
                # 处理股票代码和名称
                code_parts = item.split(' ', 1)
                code = code_parts[0]
                name = code_parts[1] if len(code_parts) > 1 else ''
                parts.append(f'<div class="stock-code">{code}</div>')
                if name:
                    parts.append(f'<div class="stock-name">{name}</div>')
                    
            elif cell_type == 'trend':
                # 处理价格、涨跌幅和成交量
                trend_parts = item.split(' ')
                if trend_parts:
                    if '$' in trend_parts[0]:  # 价格
                        parts.append(f'<div class="price">{trend_parts[0]}</div>')
                    elif '%' in trend_parts[0]:  # 涨跌幅
                        change = trend_parts[0].strip()
                        # 确保有值且第一个字符是+或-
                        if change and change[0] in ['+', '-']:
                            change_class = 'price-up' if change[0] == '+' else 'price-down'
                        else:
                            change_class = 'price-unchanged'
                        parts.append(f'<div class="change {change_class}">{change}</div>')
                    elif '成交量' in trend_parts[0] or any(x in trend_parts[0] for x in ['放量', '缩量', '平量']):  # 成交量
                        volume_class = ''
                        if '成交量高于20日均值' in item:
                            volume_class = 'value-positive'  # 成交量高于均值显示为绿色
                        elif '成交量低于20日均值' in item:
                            volume_class = 'value-negative'  # 成交量低于均值显示为红色
                        elif '放量' in trend_parts[0]:
                            volume_class = 'volume-up'
                        elif '缩量' in trend_parts[0]:
                            volume_class = 'volume-down'
                        parts.append(f'<div class="volume {volume_class}">{item}</div>')
                    else:
                        parts.append(f'<div class="text">{item}</div>')
                    
            elif cell_type in ['ma', 'bollinger']:
                # 处理MA和布林带数据
                if '排列' in item:  # 处理排列
                    if '空头排列' in item:
                        parts.append(f'<div class="text value-negative">{item}</div>')  # 空头排列显示为红色
                    elif '多头排列' in item:
                        parts.append(f'<div class="text value-positive">{item}</div>')  # 多头排列显示为绿色
                    else:
                        parts.append(f'<div class="text">{item}</div>')
                elif '突破' in item:  # 处理突破
                    parts.append(f'<div class="text breakthrough">{item}</div>')  # 突破显示为黑色粗体
                elif '超买区间' in item or '超卖区间' in item or '接近超买' in item or '接近超卖' in item:  # 处理超买超卖区间
                    if '超买区间' in item or '接近超买' in item:
                        parts.append(f'<div class="text value-negative">{item}</div>')  # 超买显示为红色
                    else:
                        parts.append(f'<div class="text value-positive">{item}</div>')  # 超卖显示为绿色
                elif 'BB位置' in item:  # 处理布林带位置
                    try:
                        # 提取百分比值
                        value_str = item.split('BB位置')[-1].strip().rstrip('%')
                        value = float(value_str)
                        if value >= 80:
                            parts.append(f'<div class="text value-negative">{item}</div>')  # 超买显示为红色
                        elif value <= 20:
                            parts.append(f'<div class="text value-positive">{item}</div>')  # 超卖显示为绿色
                        else:
                            parts.append(f'<div class="text">{item}</div>')
                    except ValueError:
                        parts.append(f'<div class="text">{item}</div>')
                elif '%' in item:
                    try:
                        # 提取百分比值
                        value_str = item.split(':')[-1].strip('%')  # 从冒号后面提取数值
                        value = float(value_str)
                        # 根据值的正负和关键词判断
                        if '低于MA' in item:
                            value_class = 'value-negative'  # MA低于为红色
                        elif '高于MA' in item:
                            value_class = 'value-positive'  # MA高于为绿色
                        else:
                            value_class = 'value-neutral'
                        parts.append(f'<div class="percentage {value_class}">{item}</div>')
                    except ValueError:
                        parts.append(f'<div class="text">{item}</div>')
                else:
                    parts.append(f'<div class="text">{item}</div>')
                    
            elif cell_type == 'psar':
                # 处理PSAR数据
                if '/' in item:
                    trend, strength = item.split('/')
                    trend_class = 'trend-up' if '上升' in trend else 'trend-down'  # 上升为绿色，下降为红色
                    strength_class = ''
                    if '强' in strength:
                        strength_class = 'strength-strong'
                    elif '弱' in strength:
                        strength_class = 'strength-weak'
                    elif '中等' in strength:
                        strength_class = 'strength-medium'
                    parts.append(f'<div class="psar"><span class="{trend_class}">{trend}</span>/<span class="strength {strength_class}">{strength}</span></div>')
                else:
                    parts.append(f'<div class="text">{item}</div>')
                    
            elif cell_type in ['kdj', 'rsi']:
                # 处理KDJ和RSI数据
                if '=' in item:
                    indicator, value = item.split('=')
                    try:
                        value_float = float(value)
                        value_class = ''
                        if cell_type == 'rsi':
                            if value_float > 70:
                                value_class = 'value-overbought'
                            elif value_float < 30:
                                value_class = 'value-oversold'
                        parts.append(f'<div class="indicator"><span class="indicator-name">{indicator}</span>=<span class="indicator-value {value_class}">{value}</span></div>')
                    except ValueError:
                        parts.append(f'<div class="indicator"><span class="indicator-name">{indicator}</span>=<span class="indicator-value">{value}</span></div>')
                elif '超买' in item or '超卖' in item:
                    signal_class = 'signal-overbought' if '超买' in item else 'signal-oversold'
                    parts.append(f'<div class="signal {signal_class}">{item}</div>')
                elif '背离' in item:
                    if '顶背离' in item:
                        parts.append(f'<div class="signal value-negative">{item}</div>')  # 顶背离显示为红色
                    elif '底背离' in item:
                        parts.append(f'<div class="signal value-positive">{item}</div>')  # 底背离显示为绿色
                    else:
                        parts.append(f'<div class="signal">{item}</div>')
                else:
                    parts.append(f'<div class="text">{item}</div>')
                    
            else:
                # 默认文本处理
                parts.append(f'<div class="text">{item}</div>')
                
        return '\n'.join(parts)
        
    except Exception as e:
        return f'<div class="error">{str(e)}</div>'

def process_table(table_data):
    """处理表格数据"""
    try:
        if not table_data:
            return '<p class="error-message">无表格数据</p>'
            
        # 如果table_data是字符串，按行分割
        if isinstance(table_data, str):
            lines = [line.strip() for line in table_data.strip().split('\n')]
        # 如果table_data是列表，直接使用
        elif isinstance(table_data, list):
            lines = [str(line).strip() for line in table_data]
        else:
            return '<p class="error-message">不支持的表格数据格式</p>'
            
        if len(lines) < 3:  # 至少需要表头行、分隔行和一行数据
            return '<p class="error-message">表格数据不完整</p>'
            
        # 检测表格结构
        num_columns, column_types = detect_table_structure(lines)
        if num_columns == 0:
            return '<p class="error-message">无法检测表格结构</p>'
            
        # 提取表头
        header_line = lines[0].strip()
        if header_line.startswith('|'):
            header_line = header_line[1:]
        if header_line.endswith('|'):
            header_line = header_line[:-1]
        headers = [h.strip() for h in header_line.split('|')]
        
        # 生成HTML表格
        html = ['<table class="stock-table">']
        
        # 添加表头
        html.append('<thead><tr>')
        for header in headers:
            html.append(f'<th>{header}</th>')
        html.append('</tr></thead>')
        
        # 添加数据行
        html.append('<tbody>')
        # 跳过表头和分隔行，同时过滤空行和分隔行
        data_lines = []
        for line in lines:
            line = line.strip()
            # 跳过空行、分隔行和表头行
            if not line or line.startswith(('+', '=', '| 股票')):
                continue
            # 处理数据行
            if line.startswith('|'):
                line = line[1:]
            if line.endswith('|'):
                line = line[:-1]
            cells = [cell.strip() for cell in line.split('|')]
            if len(cells) == num_columns:
                data_lines.append(cells)
        
        for cells in data_lines:
            html.append('<tr>')
            for i, cell in enumerate(cells):
                cell_type = column_types.get(i, 'text')
                formatted_cell = process_cell_content(cell, cell_type)
                html.append(f'<td>{formatted_cell}</td>')
            html.append('</tr>')
                    
        html.append('</tbody>')
        html.append('</table>')
        
        return '\n'.join(html)
        
    except Exception as e:
        import traceback
        error_msg = f'处理表格时发生错误: {str(e)}\n{traceback.format_exc()}'
        return f'<p class="error-message">{error_msg}</p>'

def process_stock_group(group_name, stocks_data):
    if not stocks_data:
        return f'<p>分析 {group_name} 时没有数据</p>'
    
    try:
        content = []
        content.append(f'<h2>{group_name}</h2>')
        
        # 检查是否有错误信息
        if isinstance(stocks_data, str) and "error" in stocks_data.lower():
            content.append(f'<p class="error-message">{stocks_data}</p>')
            return '\n'.join(content)
            
        content.append(f'<p>分析日期: {stocks_data["date"]}</p>')
        content.append('<p>股票对比分析:</p>')
        
        # 处理表格数据
        if "table" in stocks_data:
            try:
                content.append(process_table(stocks_data["table"]))
            except Exception as e:
                content.append(f'<p class="error-message">处理表格数据时发生错误: {str(e)}</p>')
        else:
            content.append('<p class="error-message">无法获取表格数据</p>')
            
        # 处理市场分析
        if "market_analysis" in stocks_data:
            try:
                market_analysis = stocks_data["market_analysis"]
                if isinstance(market_analysis, dict):
                    content.append(process_market_analysis(market_analysis))
                else:
                    content.append('<p class="error-message">市场分析数据格式错误</p>')
            except Exception as e:
                content.append(f'<p class="error-message">处理市场分析数据时发生错误: {str(e)}</p>')
        else:
            content.append('<p class="error-message">无法获取市场分析数据</p>')
            
        return '\n'.join(content)
    except Exception as e:
        return f'<h2>{group_name}</h2>\n<p class="error-message">分析时发生错误: {str(e)}</p>'

def process_market_analysis(market_analysis):
    """处理市场分析数据"""
    try:
        if not market_analysis:
            return '<p class="error-message">无市场分析数据</p>'
            
        content = []
        
        # 处理市场整体分析
        if "market_overall" in market_analysis:
            content.append('<div class="market-analysis-title">市场整体分析:</div>')
            for item in market_analysis["market_overall"]:
                content.append(f'<div class="market-analysis-item">{item}</div>')
                
        # 处理市场综合判断
        if "market_summary" in market_analysis:
            content.append('<div class="market-summary-title">市场综合判断:</div>')
            content.append(f'<div class="market-analysis-item">{market_analysis["market_summary"]}</div>')
            
        return '\n'.join(content)
        
    except Exception as e:
        return f'<p class="error-message">处理市场分析数据时发生错误: {str(e)}</p>'

def send_email(to_list, bcc_list, report_content, date=None, test=False):
    """发送邮件"""
    analysis_date = date if date else datetime.now().strftime('%Y-%m-%d')
    
    # 从环境变量获取邮件配置
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('SENDER_PASSWORD')
    
    if not all([smtp_server, smtp_port, sender_email, sender_password]):
        raise ValueError("请设置所需的环境变量: SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD")
    
    # 创建邮件
    msg = MIMEMultipart('alternative')
    msg['From'] = sender_email
    msg['To'] = ', '.join(to_list)
    msg['Subject'] = Header(f'市场分析报告 ({analysis_date})', 'utf-8')
    
    # 将markdown内容转换为HTML并添加到邮件中
    html_content = format_markdown_for_email(report_content)
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))
    
    if test:
        # 生成测试HTML文件
        with open('test_report.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        print("已生成测试HTML文件: test_report.html")
        return True
        
    try:
        # 连接SMTP服务器并发送
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            
            # 发送给所有收件人（包括密送）
            all_recipients = to_list + bcc_list
            server.sendmail(sender_email, all_recipients, msg.as_string())
            
        print(f"邮件发送成功！收件人: {len(to_list)}人, 密送: {len(bcc_list)}人")
        return True
    except Exception as e:
        print(f"发送邮件时出错: {str(e)}")
        traceback.print_exc()
        return False

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='发送股票分析报告邮件')
    parser.add_argument('args', nargs='+', help='日期参数（可选，支持YYYY-MM-DD、YYYY.MM.DD、YYYY/MM/DD、YYYYMMDD格式）')
    parser.add_argument('--test', action='store_true', help='测试模式，不实际发送邮件')
    
    args = parser.parse_args()
    
    try:
        # 验证并标准化日期参数
        analysis_date = validate_and_normalize_date(args.args)
        
        # 读取邮件列表
        to_list, bcc_list = read_email_list('stock_analysis_email_list.txt')
        
        # 读取报告内容
        report_content = read_report(analysis_date)
        
        # 发送邮件
        if send_email(to_list, bcc_list, report_content, analysis_date, args.test):
            print("\n✓ 邮件发送成功！")
            print(f"- 报告日期: {analysis_date}")
            print(f"- 收件人数量: {len(to_list)}")
            print(f"- 密送人数量: {len(bcc_list)}")
            if args.test:
                print("- 测试模式: 邮件未实际发送")
        else:
            print("\n✗ 邮件发送失败！")
            
    except Exception as e:
        print(f"\n发生错误: {str(e)}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    # 设置标准输出编码为UTF-8
    import sys
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    main() 