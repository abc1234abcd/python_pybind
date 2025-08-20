from dataclasses import dataclass, field
from typing import Any
from enum import Enum
from utils.config_loader import ExchangeConfigLoader
import time

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

@dataclass
class Exchange:
    name: str
    ping_message: str = field(default = None)
    ping_interval: Any = field(default = None)
    available_kline_intervals: list[str] = field(default = None)
    public_socket_url: str = field(default = None)
    private_socket_url_template: str = field(default = None)
    def __post_init__(self):
        self.name = self.name.lower()
        self.__load_config()
    def __load_config(self):
        config = ExchangeConfigLoader.load_exchange_config(self.name)
        self.ping_message = config['ping_message']
        self.ping_interval = config['ping_interval']
        self.public_socket_url = config['public_socket_url']
        self.private_socket_url_template = config['private_socket_url']
        self.available_kline_intervals = config['available_kline_intervals']
@dataclass
class OrderBookCache:
    __slots__ = ['bids', 'asks', 'last_update']
    def __init__(self):
        self.bids = None
        self.asks = None
        self.last_update = None 
    def update(self, bid: float, ask: float):
        self.bids = bid
        self.asks = ask
        self.last_update = int(time.time()*1000)
    def is_thin(self) -> bool:
        return (self.asks - self.bids) > (self.asks * 0.005) 
@dataclass
class KlineCache:
    __slots__ = ['closing_price', 'highest_price', 'lowest_price', 'opening_price', 'window_start']
    def __init__(self):
        self.closing_price = None
        self.highest_price = None
        self.lowest_price = None
        self.opening_price = None
        self.window_start = None
    def update(self, closing_price: float, hightest_price: float, lowest_price: float, opening_price: float, window_start: int):
        self.closing_price = closing_price
        self.highest_price = hightest_price
        self.lowest_price = lowest_price
        self.opening_price = opening_price
        self.window_start = window_start
@dataclass
class OrderFlowCache:
    __slots__ = ['bid_volume', 'ask_volume', 'net_flow', 'price_delta', 'normalized_net_flow' ]
    def __init__(self):
        self.bid_volume = None
        self.ask_volume = None
        self.net_flow = None
        self.price_delta = None
        self.normalized_net_flow = None
    def update(self, bid_volume: float, ask_volume: float, net_flow: float, price_delta: float, normalized_net_flow: float):
        self.bid_volume = bid_volume
        self.ask_volume = ask_volume
        self.net_flow = net_flow
        self.price_delta = price_delta
        self.normalized_net_flow = normalized_net_flow

