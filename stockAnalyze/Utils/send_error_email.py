# -*- coding: utf-8 -*-
import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import traceback
from datetime import datetime
from pathlib import Path
import platform
import psutil

def read_email_list(filename):
    """读取邮件列表"""
    # 获取脚本所在目录的绝对路径
    script_dir = Path(__file__).parent.parent
    email_list_path = script_dir / 'Settings' / filename
    
    with open(email_list_path, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]
        return lines

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

/* 错误消息样式 */
.error-message {
    color: #d63031;
    padding: 15px;
    background-color: rgba(255, 118, 117, 0.1);
    border-radius: 4px;
    margin: 10px 0;
    border-left: 4px solid #d63031;
}

/* 堆栈跟踪样式 */
.traceback {
    background-color: #f8f9fa;
    padding: 15px;
    border-radius: 4px;
    margin: 10px 0;
    font-family: monospace;
    white-space: pre-wrap;
    overflow-x: auto;
}

/* 时间戳样式 */
.timestamp {
    color: #666;
    font-size: 0.9em;
    margin-bottom: 10px;
}

/* 系统信息样式 */
.system-info {
    background-color: #f8f9fa;
    padding: 15px;
    border-radius: 4px;
    margin: 10px 0;
}

.system-info-item {
    margin: 5px 0;
}

/* 响应式布局 */
@media (max-width: 768px) {
    body {
        padding: 10px;
    }
}
</style>
"""

def generate_error_html(error_message, traceback_info, system_info=None):
    """生成错误通知的HTML内容"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>错误通知</title>
    {get_html_style()}
</head>
<body>
    <h1>错误通知</h1>
    
    <div class="timestamp">
        发生时间: {timestamp}
    </div>
    
    <div class="error-message">
        <h2>错误信息</h2>
        {error_message}
    </div>
    
    <div class="traceback">
        <h2>堆栈跟踪</h2>
        {traceback_info}
    </div>
    
    {f'''
    <div class="system-info">
        <h2>系统信息</h2>
        {system_info}
    </div>
    ''' if system_info else ''}
</body>
</html>
"""
    return html

def get_system_info():
    """获取系统信息"""
    info = []
    info.append(f"操作系统: {sys.platform}")
    info.append(f"Python版本: {sys.version}")
    info.append(f"工作目录: {os.getcwd()}")
    info.append(f"环境变量:")
    for key, value in os.environ.items():
        if key in ['PATH', 'PYTHONPATH', 'PYTHONHOME']:
            info.append(f"  {key}: {value}")
    return "<br>".join(info)

def send_error_email(error_message, traceback_info, to_list):
    """发送错误通知邮件"""
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
    msg['Subject'] = Header('[Stock Analyze] 错误通知', 'utf-8')
    
    # 获取系统信息
    system_info = get_system_info()
    
    # 生成HTML内容
    html_content = generate_error_html(error_message, traceback_info, system_info)
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))
    
    try:
        # 连接SMTP服务器并发送
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_list, msg.as_string())
            
        print(f"错误通知邮件发送成功！收件人: {len(to_list)}人")
        return True
    except Exception as e:
        print(f"发送错误通知邮件时出错: {str(e)}")
        traceback.print_exc()
        return False

def main():
    """主函数"""
    try:
        # 读取邮件列表
        to_list = read_email_list('pipeline_alert_email_list.txt')
        
        if not to_list:
            print("错误：邮件列表为空")
            return
            
        # 获取错误信息和堆栈跟踪
        error_message = "Stock Analyze 发生错误"
        traceback_info = traceback.format_exc()
        
        # 发送错误通知邮件
        if send_error_email(error_message, traceback_info, to_list):
            sys.exit(0)
        else:
            sys.exit(1)
            
    except Exception as e:
        print(f"发生错误: {str(e)}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    # 设置标准输出编码为UTF-8
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    main() 