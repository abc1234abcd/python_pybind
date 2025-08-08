import time
import logging
import asyncio
import numpy as np
from typing import List
from pathlib import Path
from dotenv import dotenv_values
from collections import deque
from utils.security import SecurityManager
from utils.data_class import OrderSide, OrderType
from core.market_data_streamer import MarketDataStreamer
from core.mexc_api import MexcApiClient
from numba import njit
#C extention
from proto_wrapper_mexc import PushDataV3ApiWrapper
from rsi import RSICalculator


class OrderBookCache:
    __slots__ = ['bids', 'asks', 'last_update']
    
    def __init__(self):
        self.bids = {}
        self.asks = {}
        self.last_update = 0
        
    def update(self, bid: float, ask: float):
        self.bids = bid
        self.asks = ask
        self.last_update = time.time_ns()
        
    def is_thin(self) -> bool:
        return (self.asks - self.bids) > (self.asks * 0.0005) 

class TakeProfit(MarketDataStreamer):
    __slots__ = ['api_client', 'msg_parser', 'rsi_calculator', 'price_buffer', 'position', 'buy_order', 'sell_order', 'last_latency']
    def __init__(self, exchange: str, topics: List[dict], api_client: MexcApiClient):
        super().__init__(exchange, topics)
        self.api_client = api_client
        self.msg_parser = PushDataV3ApiWrapper()

        #rsi index 
        self.rsi_calculator = RSICalculator(window = 14)
        self.price_buffer = np.zeros(50, dtype=np.float32)
        self.volume_buffer = np.zeros(20, dtype=np.float32)
        self.ob_cache = OrderBookCache()

        #pre-allocate buy/sell order
        self._buy_order = {
            "symbol": "SOLUSDT",
            "side": OrderSide.BUY.value,
            "type": OrderType.MARKET.value,
            "quiteOrderQty": 10.0,
            "timestamp": None
        }
        self._sell_order = {
            "symbol": "SOLUSDT",
            "side": OrderSide.BUY.value,
            "type": OrderType.MARKET.value,
            "quantity": None,
            "timestamp": None
        }

        #strategy based buffer
        self.stop_loss_pct = 0.008  
        self.oversold_threshold = 28
        self.overbought_threshold = 72
        self.trend_confirmation_bars = 3  

        self.min_spread = 0.0002
        self.max_position = 10.0 #hardcoded position size 10USDT
        self.base_qty = 2
        self.position = None
        self.last_latency = 0

    async def _message_handler(self):
        while self._is_active and self.ws:
            try:
                #binary protobuf
                msg = await asyncio.wait_for(self.ws.recv(), timeout=0.001)                
                if isinstance(msg, bytes):
                    if self.msg_parser.parse(msg):
                        if self.msg_parser.has_book_ticker():
                            book = self.msg_parser.book_ticker()
                            self.ob_cache.update(
                                bid=float(book.bid_price()),
                                ask=float(book.ask_price())
                            )
                        elif self.msg_parser.has_kline():
                            kline = self.msg_parser.kline()
                            price = float(kline.closing_price())
                            self.price_buffer[:-1] = self.price_buffer[1:]
                            self.price_buffer[-1] = price
                            rsi_value = self.rsi_calculator.update(price)
                            await self._execute_strategy(rsi_value)
                        else:
                            logging.error(f"{self.msg_parser} type is not recognized.")
                    else:
                        logging.error(f"parse protobuf msg {self.msg_parser} failed.")
                else:
                     logging.warning(f"Non-bytes message: {msg}")
            except Exception as e:
                logging.error(f"cplus msg decoder fail on exception: {e}.")
                raise
    async def auto_exec(self, rsi_value, book_ticker):
        rsi_deque = deque(maxlen = 14)
        position = None
        while True:
            curr_rsi = rsi_value 
            rsi_deque.append(curr_rsi)
            if len(rsi_deque) < 2:
                await asyncio.sleep(0)
                continue 

            rsi_lag_one = rsi_deque[-2]
            momentum = curr_rsi - rsi_lag_one

            if position != 'LONG':
                #buy when rsi crosses above its lagged value: rising trend
                if momentum > 1 and rsi_lag_one < 40:
                    entry_price = book_ticker.ask_price()
                    self._buy_order['timestamp'] = int(time.time()*1000)
                    buy_order_response= await self.api_client.submit_orders(self._buy_order)
                    buy_order_id = buy_order_response['orderId']
                    buy_order_status = await self.api_client.order_status(orderId= buy_order_id)
                    if buy_order_status['status'] in ['FILLED', 'PARTIALLY_FILLED']:
                        filled_buy_price = buy_order_status['price']
                        filled_qty = buy_order_status['executedQty']
                    elif buy_order_status == "NEW":
                        cancel_order = await self.api_client.cancel_order(symbol = 'SOLUSDT', orderId = buy_order_id)
                        if cancel_order['status'] == 'CANCELED':
                            position = None
            if position == "LONG ":
                #sell when rsi drops
                if momentum < -1:
                    #here can add on sell price control e.g current bid price > filled_price.
                    target_sell_price = book_ticker.bid_price()
                    if filled_buy_price and filled_qty:
                        self._sell_order["quantity"] = filled_qty 
                        self._sell_order['timestamp'] = int(time.time()*1000)
                        sell_order_response = await self.api_client.submit_orders(self._sell_order) 
                        sell_order_id = sell_order_response['orderId']
                        sell_order_status = await self.api_client.order_status(orderId = sell_order_id)
                        if sell_order_status['status'] in ['FILLED', 'PARTIALLY_FILLED']:
                            filled_sell_price = sell_order_status['price']
                            filled_sell_qty = sell_order_status['executedQty']
                        position = None

            
  
   
async def main(exchange: str, api_key: SecurityManager, api_secret: SecurityManager, topics: List[dict]):
    mexc_api_client = MexcApiClient(api_key = api_key, api_secret=api_secret)
    sol_take_profit_instance = TakeProfit(exchange = exchange, topics = topics, api_client = mexc_api_client)
    await asyncio.gather(
        sol_take_profit_instance.connect(),
    )

if __name__=='__main__':
    exchange = 'mexc'
    topics = [{"method": "SUBSCRIPTION", "params":["spot@public.aggre.bookTicker.v3.api.pb@100ms@SOLUSDT", "spot@public.kline.v3.api.pb@SOLUSDT@Min1"]}]
    api_key = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f"{exchange.upper()}_API_KEY"])
    api_secret = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f"{exchange.upper()}_SECRET"])
    asyncio.run(main(exchange = exchange, api_key=api_key, api_secret=api_secret, topics=topics))



