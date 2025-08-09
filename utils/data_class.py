from dataclasses import dataclass, field
from typing import Any
from enum import Enum
from utils.config_loader import ExchangeConfigLoader

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


