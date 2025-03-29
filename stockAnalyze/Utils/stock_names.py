# -*- coding: utf-8 -*-

# 股票中文名称映射
STOCK_NAMES = {
    # 主要科技股
    'AAPL': '苹果',
    'MSFT': '微软',
    'GOOGL': '谷歌',
    'AMZN': '亚马逊',
    'META': 'Meta',
    'NVDA': '英伟达',
    'TSLA': '特斯拉',
    'NFLX': '奈飞',
    'PLTR': 'Palantir',
    'APP': 'AppLovin',
    'INTU': '财捷软件',
    'FTNT': '飞塔',
    
    # 中概股
    'BABA': '阿里巴巴',
    'PDD': '拼多多',
    'BIDU': '百度',
    'JD': '京东',
    
    # 半导体
    'TSM': '台积电',
    'AMD': 'AMD',
    'INTC': '英特尔',
    'AVGO': '博通',
    'ASML': 'ASML',
    'LRCX': '拉姆研究',
    'AMAT': '应用材料',
    'QCOM': '高通',
    'MU': '美光科技',
    'MRVL': '迈威尔科技',
    
    # 金融股
    'BRK-B': '伯克希尔B',
    'JPM': '摩根大通',
    'BAC': '美国银行',
    'BLK': '贝莱德',
    'MA': 'Mastercard',
    'V': 'Visa',
    'GS': '高盛',
    'MS': '摩根士丹利',
    
    # 其他行业
    'CSCO': '思科',
    'ORCL': '甲骨文',
    'CRM': '赛富时',
    'ADBE': 'Adobe',
    'TXN': '德州仪器',
    'IBM': 'IBM',
    'UBER': '优步',
    'PYPL': 'PayPal',
    'SQ': 'Block',
    'ZM': 'Zoom',
    'SHOP': 'Shopify',
    'COIN': 'Coinbase',
    'SNOW': 'Snowflake',
    'COST': '好市多',
    'SHW': '宣伟涂料',
    'VMC': '火神材料',
    'HD': '家得宝',
    'FDX': '联邦快递',
    'UPX': '联合包裹',
    'KO': '可口可乐',
    'O': 'O',
    'ISRG': '直觉手术',
    'MRK': '默沙东',
    'LLY': '礼来',
    
    # ETF
    'SPY': '标普500ETF',
    'QQQ': '纳指100ETF',
    'DIA': '道指ETF',
    'IWM': '罗素2000ETF',
    'SOXX': '费城半导体ETF',
    'SHY': '1-3年国债ETF',
    'IEI': '3-7年国债ETF',
    'IEF': '7-10年国债ETF',
    'TLT': '20年+国债ETF',
    'GLD': '黄金ETF',
    'IYR': '房地产ETF',
    'IYZ': '电信ETF',
    'XLB': '材料ETF',
    'XLE': '能源ETF',
    'XLF': '金融ETF',
    'XLI': '工业ETF',
    'XLK': '科技ETF',
    'XLP': '必需消费ETF',
    'XLU': '公用事业ETF',
    'XLV': '医疗保健ETF',
    'XLY': '可选消费ETF'
}

def get_stock_name(stock_code):
    """获取股票中文名称"""
    # 首先尝试从映射表获取中文名称
    if stock_code in STOCK_NAMES:
        return STOCK_NAMES[stock_code]
    
    # 如果映射表中没有，则尝试从yfinance获取英文名称
    try:
        import yfinance as yf
        stock = yf.Ticker(stock_code)
        info = stock.info
        name = info.get('shortName', stock_code)
        # 如果名称太长，截取前20个字符
        if len(name) > 20:
            name = name[:17] + '...'
        return name
    except:
        return stock_code 