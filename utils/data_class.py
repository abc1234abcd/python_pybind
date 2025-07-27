import os
import re
import logging
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum
from dotenv import load_dotenv
from pathlib import Path
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

@dataclass
class Exchange:
    name: str
    ping_message: str = field(default = None)
    ping_interval: Any = field(default = None)
    available_kline_intervals: list[str] = field(default = None)
    topic_template: str = field(default = None)
    api_key: str = field(default = None)
    api_secret: str = field(default = None)
    public_socket_url: str = field(default = None)
    private_socket_url: str = field(default = None)
    env_path: Path = field(default=Path(__file__).parent.parent/'config', repr=False)
    def __post_init__(self):
        self.name = self.name.lower()
        load_dotenv(self.env_path/'.env')
        self.__load_config()
    def __load_config(self):
        config = ExchangeConfigLoader.load_exchange_config(self.name)
        self.ping_message = config['ping_message']
        self.ping_interval = config['ping_interval']
        self.topic_template = config['topic_template']
        self.public_socket_url = config['public_socket_url']
        self.private_socket_url = config['private_socket_url']
        self.available_kline_intervals = config['available_kline_intervals']
        self.api_key = os.getenv(f"{self.name.upper()}_API_KEY")
        self.api_secret = os.getenv(f"{self.name.upper()}_SECRET")

