# -*- coding: utf-8 -*-
import sys
import os
from datetime import datetime
import traceback
from pathlib import Path

# 添加当前目录到Python路径
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

from analyze_groups import generate_report, read_stock_groups
from Utils.send_report_email import send_email, read_email_list, read_report
from Utils.send_error_email import send_error_email, read_email_list as read_alert_email_list
from Utils.param_utils import get_last_trading_day, validate_and_normalize_date
import argparse

def auto_generate_and_send_report(date=None, clear_cache=False):
    """自动生成并发送市场分析报告"""
    try:
        print("开始自动生成市场分析报告...")
        
        # 设置日期
        analysis_date = date if date else datetime.now().strftime('%Y-%m-%d')
        print(f"分析日期: {analysis_date}")
        
        # 获取脚本目录
        script_dir = Path(__file__).parent
        settings_dir = script_dir / 'Settings'
        
        # 第一步：读取股票列表并生成报告
        print("\n1. 读取股票列表...")
        stock_list_path = settings_dir / 'stock_list.txt'
        groups = read_stock_groups(stock_list_path)
        
        print("2. 生成分析报告...")
        generate_report(groups, analysis_date, clear_cache)
        
        # 第二步：读取邮件列表
        print("\n3. 读取邮件列表...")
        email_list_path = settings_dir / 'stock_analysis_email_list.txt'
        to_list, bcc_list = read_email_list(email_list_path)
        
        # 第三步：读取报告内容
        print("4. 读取报告内容...")
        report_content = read_report(analysis_date)
        
        # 第四步：发送邮件
        print("\n5. 发送报告邮件...")
        if send_email(to_list, bcc_list, report_content, analysis_date):
            print("\n✓ 任务完成！")
            print(f"- 报告日期: {analysis_date}")
            print(f"- 收件人数量: {len(to_list)}")
            print(f"- 密送人数量: {len(bcc_list)}")
            return True
        else:
            print("\n✗ 发送邮件失败！")
            return False
            
    except Exception as e:
        print(f"\n发生错误: {str(e)}")
        traceback.print_exc()
        
        # 发送错误通知邮件
        try:
            # 读取告警邮件列表
            alert_email_list_path = settings_dir / 'pipeline_alert_email_list.txt'
            alert_to_list = read_alert_email_list(alert_email_list_path)
            
            if alert_to_list:
                # 获取错误信息和堆栈跟踪
                error_message = str(e)
                traceback_info = traceback.format_exc()
                
                # 发送错误通知邮件
                send_error_email(error_message, traceback_info, alert_to_list)
        except Exception as email_error:
            print(f"发送错误通知邮件时出错: {str(email_error)}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            
        return False

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='股票技术分析工具 - 自动生成并发送报告')
    parser.add_argument('args', nargs='*', help='日期参数（可选，支持YYYY-MM-DD、YYYY.MM.DD、YYYY/MM/DD、YYYYMMDD格式）')
    parser.add_argument('--clear', action='store_true', help='清除缓存数据')
    
    args = parser.parse_args()
    
    try:
        # 获取脚本目录
        script_dir = Path(__file__).parent
        settings_dir = script_dir / 'Settings'
        
        # 检查日期是否为交易日
        target_date = validate_and_normalize_date(args.args) if args.args else datetime.now().strftime('%Y-%m-%d')
        last_trading_day = get_last_trading_day(target_date)
        
        if target_date != last_trading_day:
            print(f"警告：目标日期 {target_date} 不是交易日，将使用最近的交易日 {last_trading_day}", file=sys.stderr)
            
            # 发送非交易日错误通知
            try:
                # 读取告警邮件列表
                alert_email_list_path = settings_dir / 'pipeline_alert_email_list.txt'
                alert_to_list = read_alert_email_list(alert_email_list_path)
                
                if alert_to_list:
                    error_message = f"目标日期 {target_date} 不是交易日，最近的交易日是 {last_trading_day}"
                    traceback_info = "此错误是由于在非交易日尝试生成报告导致的。\n"
                    traceback_info += "系统将在下一个交易日自动重试。"
                    
                    # 发送错误通知邮件
                    send_error_email(error_message, traceback_info, alert_to_list)
            except Exception as email_error:
                print(f"发送错误通知邮件时出错: {str(email_error)}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
        
        # 继续执行报告生成
        if auto_generate_and_send_report(last_trading_day, args.clear):
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n任务被用户中断", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n发生错误: {str(e)}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 