# Utils 目录

这个目录包含了股票分析系统的各种工具模块。

## 模块说明

### stock_data_manager.py
股票数据管理模块，负责：
- 从yfinance获取股票数据
- 管理历史数据缓存
- 数据验证和合并
- 并行处理多个股票数据

### stock_names.py
股票名称管理模块，提供：
- 股票代码到中文名称的映射
- 从yfinance获取股票英文名称的功能

### send_error_email.py
错误通知邮件模块，负责：
- 发送错误通知邮件
- 生成错误报告的HTML内容
- 收集系统信息

### param_utils.py
参数处理工具模块，提供：
- 股票代码标准化
- 日期格式验证和转换
- 交易日判断
- 命令行参数解析

### send_report_email.py
报告邮件模块，负责：
- 发送分析报告邮件
- 将Markdown格式转换为HTML
- 处理表格和样式

## 使用示例

```python
from stockAnalyze.Utils import (
    StockDataManager,
    get_stock_name,
    send_error_email,
    validate_and_normalize_params
)

# 使用数据管理器
manager = StockDataManager()
df, from_yf = manager.get_stock_data('AAPL')

# 获取股票名称
name = get_stock_name('AAPL')

# 发送错误通知
send_error_email("发生错误", traceback.format_exc(), ["example@email.com"])

# 验证参数
stock_codes, date = validate_and_normalize_params(['AAPL', '2024-03-28'])
```

## 数据管理器使用注意事项

1. 数据获取：
   - 默认从2024-01-01开始获取数据
   - 自动处理缓存和更新
   - 返回元组(DataFrame, bool)，bool表示是否从yfinance获取

2. 数据格式：
   - 包含基本列：['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
   - 价格数据保留6位小数
   - 日期列需要设置为索引
   - 自动处理时区转换

3. 最佳实践：
   - 在main函数中创建manager实例
   - 将manager传递给分析函数
   - 检查返回数据是否为None或空
   - 确保有足够的历史数据用于技术分析

## 依赖项

- pandas
- yfinance
- markdown2
- smtplib3 (Python标准库) 