## Stock Analysis

The stock analysis tools provide comprehensive technical analysis capabilities for stocks. All commands support both single stock analysis and batch processing.

### Basic Stock Analysis Commands

1. `check_ma.py`: Check stock's position relative to moving averages
```bash
python stockAnalyze/check_ma.py <stock_codes> [date]
```
Output includes:
- Current closing price
- MA200 price
- Percentage difference
- Daily price change
- Volume comparison with 20-day average
- MA position status

2. `check_kdj.py`: Analyze KDJ indicator
```bash
python stockAnalyze/check_kdj.py <stock_codes> [date]
```
Output includes:
- K value (period=9, signal=3)
- D value (period=9, signal=3)
- J value (period=9, signal=3, J=3)
- Technical analysis of KDJ indicator

3. `check_rsi.py`: Analyze RSI indicator
```bash
python stockAnalyze/check_rsi.py <stock_codes> [date]
```
Output includes:
- RSI value
- Overbought/Oversold status
- Divergence analysis (if any)
- Technical signals

4. `check_demark.py`: Analyze Demark indicators
```bash
python stockAnalyze/check_demark.py <stock_codes> [date]
```
Output includes:
- TD Sequential counts
- TD Setup and Countdown signals
- Technical analysis based on Demark indicators

5. `check_bollinger.py`: Analyze Bollinger Bands
```bash
python stockAnalyze/check_bollinger.py <stock_codes> [date]
```
Output includes:
- Upper and lower bands
- Band width
- Price position relative to bands
- Technical signals

6. `check_psar.py`: Analyze Parabolic SAR
```bash
python stockAnalyze/check_psar.py <stock_codes> [date]
```
Output includes:
- Current PSAR value
- Trend direction
- Acceleration factor
- Technical signals

### Advanced Analysis Commands

1. `analyze_stock.py`: Comprehensive single stock analysis
```bash
python stockAnalyze/analyze_stock.py <stock_codes> [date] [--clear-cache]
```
Output includes:
- Stock code and analysis date
- Current price and daily change
- Key signals with emoji indicators:
  * Demark signals
  * MA200 status
  * KDJ signals
  * RSI signals
  * Volume status
- Risk warnings
- Detailed technical indicators summary

2. `compare_stocks.py`: Compare multiple stocks
```bash
python stockAnalyze/compare_stocks.py <stock_codes> [date] [--clear-cache]
```
Output includes:
- Stock comparison table
- Price and daily change
- MA200 difference
- KDJ status
- RSI(6) value
- Comprehensive technical signals
- Market strength analysis
- Market risk assessment
- Market trend analysis
- Signal legend

3. `analyze_groups.py`: Analyze predefined stock groups
```bash
python stockAnalyze/analyze_groups.py [date] [--clear]
```
Output includes:
- Group performance summary
- Individual stock analysis within groups
- Group-level technical indicators
- Market sector analysis

### Utility Commands

1. `auto_report.py`: Generate automated analysis reports
```bash
python stockAnalyze/auto_report.py [date] [--clear]
```
Features:
- Scheduled report generation
- Customizable report templates
- Multiple output formats
- Email distribution

2. `send_report_email.py`: Send analysis reports via email
```bash
python stockAnalyze/send_report_email.py [date] [--test]
```
Features:
- HTML formatted reports
- Multiple recipient support
- Attachment handling
- Error logging
- Requires environment variables:
  * SMTP_SERVER
  * SMTP_PORT
  * SENDER_EMAIL
  * SENDER_PASSWORD

3. `send_error_email.py`: Send error notifications
```bash
python stockAnalyze/send_error_email.py
```
Features:
- Error details formatting
- Stack trace inclusion
- Priority levels
- Error categorization
- Reads recipient list from pipeline_alert_email_list.txt
- Requires environment variables:
  * SMTP_SERVER
  * SMTP_PORT
  * SENDER_EMAIL
  * SENDER_PASSWORD

### Technical Indicators Rules

1. Demark Indicators:
   - TD Sequential Rules:
     * Setup 9: Count increases when price is higher than 4 days ago and 2 days ago
     * Setup 13: Count increases after Setup 9 completion when price is higher than 4 days ago and 2 days ago
     * Countdown: Starts after Setup completion
   - Signal Conditions:
     * Setup 9: Triggers at count 9
     * Setup 13: Triggers at count 4
   - Reset Rules:
     * Count resets when conditions not met
     * Countdown resets after completion

2. RSI Rules:
   - Calculation:
     * RSI = 100 - (100 / (1 + RS))
     * RS = Average gain / Average loss
     * Uses RMA for moving averages
   - Interpretation:
     * RSI > 80: Overbought
     * RSI < 20: Oversold
     * 20-80: Normal range
   - Divergence Analysis:
     * Medium-term: 30 trading days
     * Price new high, RSI not: Bearish divergence
     * Price new low, RSI not: Bullish divergence

3. Date Handling Rules:
   - Date Format Support:
     * YYYY-MM-DD
     * YYYY.MM.DD
     * YYYY/MM/DD
     * YYYYMMDD
   - When specified date data is unavailable:
     * Try previous trading day
     * Maximum 5 days back
     * Skip weekends and holidays
     * No fallback to previous year
   - Error Handling:
     * Clear error messages
     * Date attempt logging
     * Solution suggestions

### Signal Emoji Legend
- 📈 Upward trend
- 📉 Downward trend
- ⚠️ Warning signal
- 🔥 Overbought
- ❄️ Oversold
- 📊 Volume related
- 🔄 Sideways/Choppy
- ⚡ Strong signal
- 💡 Bullish signal
- 🚫 Bearish signal
