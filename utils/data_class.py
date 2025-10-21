from dataclasses import dataclass, field
from typing import List
from enum import Enum
import time
import numpy as np

class MarketData(Enum):
    TRADES= 'trades'
    ORDER_BOOK= 'order_book'
    KLINE= 'kline'
    BOOK_TICKER = 'book_ticker'
class UserData(Enum):
    SPOT_ACCOUNT_UPDATE = 'spot_account_upate'
    SPOT_ACCOUNT_DEALS ='spot_account_deals'
    SPOT_ACCOUNT_ORDERS = 'spot_account_orders'
class SubscriptionAction(Enum):
    SUBSCRIBE ='subscribe'
    UNSUBSCRIBE = 'unsubscribe'
class OrderSide(Enum):
    BUY = 'BUY'
    SELL = 'SELL'
class OrderType(Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT ="TAKE_PROFIT_LIMIT"
    LIMIT_MAKER ="LIMIT_MAKER"
class Market(Enum):
    SPOT = "spot"
    FUTURES = "futures"
    BROKER = "broker"
class DataType(Enum):
    PRIVATE = 'private'
    PUBLIC = 'public'

@dataclass
class BookTicker:
    __slots__ = ['bids', 'asks', 'last_update', 'bids_qty', 'asks_qty', 'symbol']
    def __init__(self):
        self.bids =  0.0
        self.asks =  0.0
        self.last_update =  0.0 
        self.bids_qty = 0.0
        self.asks_qty = 0.0
        self.symbol = None
    def update(self, bids: float, asks: float, bids_qty: float, asks_qty: float, symbol: str):
        self.bids = float(bids)
        self.asks = float(asks)
        self.last_update = int(time.time()*1000)
        self.bids_qty = bids_qty
        self.asks_qty = asks_qty
        self.symbol = symbol
    @property
    def is_thin(self) -> bool:
        return (self.asks - self.bids) > 0.001
    @property
    def is_stable(self) ->bool:
        return (self.asks - self.bids) <= 0.0001
    @property
    def vwap(self)->float:
        return (self.bids*self.asks_qty + self.asks*self.bids_qty)/(self.asks_qty + self.bids_qty)
@dataclass
class Kline:
    __slots__ = ['closing_price', 'highest_price', 'lowest_price', 'opening_price', 'window_start','volume']
    def __init__(self):
        self.closing_price = 0.0
        self.highest_price = 0.0
        self.lowest_price = 0.0
        self.opening_price = 0.0
        self.window_start = 0.0
        self.volume = 0.0
    def update(self, closing_price: float, hightest_price: float, lowest_price: float, opening_price: float, window_start: int, volume: float):
        self.closing_price = float(closing_price)
        self.highest_price = float(hightest_price)
        self.lowest_price = float(lowest_price)
        self.opening_price = float(opening_price)
        self.window_start = int(window_start)
        self.volume = float(volume)
@dataclass
class OrderFlow:
    __slots__ = ['bid_volume', 'ask_volume', 'net_flow', 'price_delta', 'normalized_net_flow' ]
    def __init__(self):
        self.bid_volume = 0.0
        self.ask_volume =  0.0
        self.net_flow =  0.0
        self.price_delta =  0.0
        self.normalized_net_flow =  0.0
    def update(self, bid_volume: float, ask_volume: float, net_flow: float, price_delta: float, normalized_net_flow: float):
        self.bid_volume = float(bid_volume)
        self.ask_volume = float(ask_volume)
        self.net_flow = float(net_flow)
        self.price_delta = float(price_delta)
        self.normalized_net_flow = float(normalized_net_flow)
@dataclass
class LimitDepthsOB:
    __slots__=['bids','asks']
    def __init__(self):
        self.asks = np.zeros((20,2), dtype =np.float64)
        self.bids = np.zeros((20,2), dtype = np.float64)
    def update(self, asks: List[List[float]], bids:List[List[float]]):
        self.asks = np.array([[float(item.price()), float(item.quantity())] for item in asks])
        self.bids = np.array([[float(item.price()), float(item.quantity())] for item in bids])
    @property
    def book_buy_pressure(self) -> float:
        total_bids_qty = np.sum(self.bids[:,1])
        print(self.asks[:,1])
        total_asks_qty = np.sum(self.asks[:,1])
        return (total_bids_qty - total_asks_qty)/(total_bids_qty + total_asks_qty)
