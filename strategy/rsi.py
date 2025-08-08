'''

relative strength index:

< 30: oversold -> buy signal.
>70: overbuy -> sell signal.

False signal verification:

1. linear regression based on very recenet data: slop = np.ployfit(price, rsi, 1)[0]

expecting if: slop > 0 uptrend. slop < 0 downtrend.

drawbacks: wihpsaw small slop hard to tell the trend. aka. hard to decide the slop threshold so that an effective signal can be judged.


2. multiple rsi: general oversold but bouncing uptrend at the smallest interval.

def should_enter(rsi_1m: float, rsi_3m: float, rsi_5m: float) -> bool:
    # All timeframes must agree
    return (rsi_1m < 25 and 
            rsi_3m < 30 and 
            rsi_5m < 35 and
            rsi_1m > rsi_3m > rsi_5m)  # Momentum alignment.


3. Liquidity Void:

combine with EMA20.


4. Indicator Saturation



def should_enter(..., ema_20_trend: float) -> bool:
    # 增加趋势方向判断（EMA20向下时禁止做多）
    return (original_conditions and ema_20_trend > 0)



async def scalp_trade(entry_price: float):
    take_profit = entry_price * 1.0015  # 0.15% target
    stop_loss = entry_price * 0.9995    # 0.05% stop
    
    while True:
        current_bid = get_best_bid()
        if current_bid >= take_profit:
            await submit_order("SELL", current_bid)
            return True  # Win
        elif current_bid <= stop_loss:
            await submit_order("SELL", current_bid)
            return False  # Loss
        await asyncio.sleep(0.01)  # 10ms check

bid vol > ask vol : buy pressure

'''