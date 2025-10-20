#此策略部分内容删减，仅供学习参考

from jqdata import *
from jqfactor import *
import numpy as np
import pandas as pd
import talib

# 初始化函数
def initialize(context):
    # 设定基准
    set_benchmark('000985.XSHG')
    # 用真实价格交易
    set_option('use_real_price', True)
    # 打开防未来函数
    set_option("avoid_future_data", True)
    # 设置交易成本
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001, open_commission=0.0003, 
                           close_commission=0.0003, close_today_commission=0, min_commission=5), type='stock')
    
    # 初始化全局变量
    g.stock_num = 3  # 持仓股票数量
    g.hold_list = []  # 当前持仓
    g.yesterday_HL_list = []  # 昨日涨停股票
    g.pass_months = [1, 4]  # 空仓月份
    
    # 设置交易运行时间
    run_daily(prepare_stock_list, '9:05')
    run_weekly(weekly_adjustment, 1, '9:30')
    run_daily(check_limit_up, '14:00')

# 准备股票池
def prepare_stock_list(context):
    # 获取已持有列表
    g.hold_list = list(context.portfolio.positions.keys())
    
    # 获取昨日涨停列表
    if g.hold_list:
        df = get_price(g.hold_list, end_date=context.previous_date, frequency='daily', 
                      fields=['close', 'high_limit'], count=1, panel=False, fill_paused=False)
        df = df[df['close'] == df['high_limit']]
        g.yesterday_HL_list = list(df.code)
    else:
        g.yesterday_HL_list = []
    
    # 判断今天是否为交易日
    g.trading_signal = today_is_between(context)

# 选股模块 - 关键逻辑已移除
def get_stock_list(context):
    """
    选股逻辑示例框架
    """
    # 获取基础股票池
    initial_list = get_index_stocks('000985.XSHG', context.current_dt)
    
    # 应用基础过滤器
    stocks = filter_kcbj_stock(initial_list)
    stocks = filter_st_stock(stocks)
    stocks = filter_new_stock(context, stocks)
    
    # 示例：简单的市值筛选（实际策略使用更复杂的因子）
    q = query(
        valuation.code,
        valuation.market_cap
    ).filter(
        valuation.code.in_(stocks)
    ).order_by(
        valuation.market_cap.asc()
    ).limit(g.stock_num * 2) 
    
    df = get_fundamentals(q)
    if len(df) == 0:
        return []
    
    candidate_list = list(df.code)
    
    # 应用交易过滤器
    candidate_list = filter_paused_stock(candidate_list)
    candidate_list = filter_limitup_stock(context, candidate_list)
    candidate_list = filter_limitdown_stock(context, candidate_list)
    
    # 随机选择最终股票（实际策略应使用特定的选股逻辑）
    import random
    if len(candidate_list) > g.stock_num:
        final_list = random.sample(candidate_list, g.stock_num)
    else:
        final_list = candidate_list
    
    return final_list

# 周度调仓
def weekly_adjustment(context):
    if not g.trading_signal:
        return
        
    target_stocks = get_stock_list(context)
    
    # 卖出不在目标列表中的股票（除昨日涨停外）
    for stock in g.hold_list:
        if stock not in target_stocks and stock not in g.yesterday_HL_list:
            position = context.portfolio.positions[stock]
            close_position(position)
    
    # 计算需要买入的股票数量
    current_position_count = len(context.portfolio.positions)
    buy_num = min(len(target_stocks), g.stock_num - current_position_count)
    
    if buy_num > 0:
        cash_per_stock = context.portfolio.cash / buy_num
        for stock in target_stocks:
            if stock not in context.portfolio.positions:
                if open_position(stock, cash_per_stock):
                    if len(context.portfolio.positions) >= g.stock_num:
                        break

# 检查涨停股
def check_limit_up(context):
    if not g.yesterday_HL_list:
        return
        
    for stock in g.yesterday_HL_list:
        current_data = get_price(stock, end_date=context.current_dt, frequency='1m', 
                               fields=['close', 'high_limit'], count=1, panel=False, 
                               fill_paused=True)
        if current_data.iloc[0, 0] < current_data.iloc[0, 1]:
            log.info("[%s]涨停打开，卖出" % (stock))
            position = context.portfolio.positions[stock]
            close_position(position)

# 判断是否在交易月份
def today_is_between(context):
    month = context.current_dt.month
    return month not in g.pass_months

# 交易函数
def open_position(security, value):
    order = order_target_value(security, value)
    return order is not None and order.filled > 0

def close_position(position):
    security = position.security
    order = order_target_value(security, 0)
    return order is not None

# 过滤器函数
def filter_paused_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]

def filter_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list
            if not current_data[stock].is_st
            and 'ST' not in current_data[stock].name
            and '*' not in current_data[stock].name
            and '退' not in current_data[stock].name]

def filter_kcbj_stock(stock_list):
    return [stock for stock in stock_list 
            if not (stock[0] in ['4', '8'] or stock[:2] == '68' or stock[0] == '3')]

def filter_limitup_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list 
            if stock in context.portfolio.positions.keys()
            or last_prices[stock][-1] < current_data[stock].high_limit]

def filter_limitdown_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list 
            if stock in context.portfolio.positions.keys()
            or last_prices[stock][-1] > current_data[stock].low_limit]

def filter_new_stock(context, stock_list):
    yesterday = context.previous_date
    return [stock for stock in stock_list if
            not yesterday - get_security_info(stock).start_date < datetime.timedelta(days=375)]