import time
import logging
import asyncio
import numpy as np
from typing import List
from pathlib import Path
from dotenv import dotenv_values
from utils.security import SecurityManager
from utils.data_class import OrderSide, OrderType
from core.market_data_streamer import MarketDataStreamer
from core.mexc_api import MexcApiClient
from numba import njit

#C++ extention
from proto_wrapper_mexc import PushDataV3ApiWrapper
from rsi_calculator import RSICalculator
from slope_calculator import calculate_slope
from order_flow import compute_order_flow

'''
1. buy 2. sell
parameters: 

a. market.is_thin = True if (best_asks - best_bid)/best_asks > 0.5% ;
b. the trading strategy is designed to work in one minute timeframe, so price slope is the coefficiency of the past "one minute" trades price, which is dynamically correlated with below sub-params:
    b.1. 

'''

class OrderBookCache:
    __slots__ = ['bids', 'asks', 'last_update']
    
    def __init__(self):
        self.bids = 0.0
        self.asks = 0.0
        self.last_update = 0
        
    def update(self, bid: float, ask: float):
        self.bids = bid
        self.asks = ask
        self.last_update = int(time.time()*1000)
        
    def is_thin(self) -> bool:
        return (self.asks - self.bids) > (self.asks * 0.005) 

class KlineCache:
    __slots__ = ['closing_price', 'highest_price', 'lowest_price', 'opening_price', 'window_start']

    def __init__(self):
        self.closing_price = 0.0
        self.highest_price = 0.0
        self.lowest_price = 0.0
        self.opening_price = 0.0
        self.window_start = 0
    def update(self, closing_price: float, hightest_price: float, lowest_price: float, opening_price: float, window_start: int):
        self.closing_price = closing_price
        self.highest_price = hightest_price
        self.lowest_price = lowest_price
        self.opening_price = opening_price
        self.window_start = window_start

class OrderFlowCache:
    __slots__ = ['bid_volume', 'ask_volume', 'net_flow', 'price_delta', 'normalized_net_flow' ]
    def __init__(self):
        self.bid_volume = 0.0
        self.ask_volume = 0.0
        self.net_flow = 0.0
        self.price_delta = 0.0
        self.normalized_net_flow = 0.0
    def update(self, bid_volume: float, ask_volume: float, net_flow: float, price_delta: float, normalized_net_flow: float):
        self.bid_volume = bid_volume
        self.ask_volume = ask_volume
        self.net_flow = net_flow
        self.price_delta = price_delta
        self.normalized_net_flow = normalized_net_flow

class TakeProfit(MarketDataStreamer):
    def __init__(self, exchange: str, topics: List[dict], api_client: MexcApiClient):
        super().__init__(exchange, topics)
        self.api_client = api_client
        self.msg_parser = PushDataV3ApiWrapper()
        #rsi 
        self.rsi_calculator = RSICalculator(7)
        self.kline_cache = KlineCache()
        self.rsi_value = None
        self.filled_rsi = 0.0

        #book ticker cache
        self.ob_cache = OrderBookCache()

        #order flow
        self.order_flow_cache = OrderFlowCache()

        #price buffer
        self.price_buffer = np.zeros(10, np.float64)

        #prev filled price
        self.prev_filled_price = None

        #rsi buffer
        self.rsi_buffer = np.zeros(100, np.float64)

        #pre-allocate buy/sell order
        self.filled_entry_price = 0.0
        self.filled_qty = 0.0
        self.max_position = "10" 
        self._buy_order = {
            "quoteOrderQty":  self.max_position,  
            "side": OrderSide.BUY.value,
            "symbol": "SOLUSDT",
            "timestamp": None,  
            "type": OrderType.MARKET.value
        }
        self._sell_order = {
            "quantity": None,  
            "side": OrderSide.SELL.value,
            "symbol": "SOLUSDT",
            "timestamp": None,  
            "type": OrderType.MARKET.value
        }

        #strategy based buffer
        self.oversold_threshold = 40
        self.overbought_threshold = 68
        self.position = None

         
        #latency control notification
        self.last_latency = 0

    async def _message_handler(self):  
        while self._is_active and self.ws:
            try:
                #binary protobuf
                msg = await self.ws.recv()                
                if isinstance(msg, bytes):
                    if self.msg_parser.parse(msg):
                        #ob cache
                        if self.msg_parser.has_book_ticker():
                            book = self.msg_parser.book_ticker()
                            self.ob_cache.update(
                                bid=float(book.bid_price()),
                                ask=float(book.ask_price())
                            )
                        #kline and rsi
                        if self.msg_parser.has_kline():
                            kline = self.msg_parser.kline()
                            self.kline_cache.update(kline.closing_price(), kline.highest_price(), kline.lowest_price(), kline.opening_price(), kline.window_start())
                            self.rsi_value = self.rsi_calculator.update(np.float32(self.kline_cache.closing_price))
                            self.rsi_buffer = np.roll(self.rsi_buffer, -1)
                            self.rsi_buffer[-1] = self.rsi_value
                            self.rsi_buffer[1] = self.rsi_value
                            self.price_buffer = np.roll(self.price_buffer, -1)
                            self.price_buffer[-1] = self.kline_cache.closing_price
                        #order_flow
                        if self.msg_parser.has_public_aggredeals():
                                trades = self.msg_parser.trades()
                                if trades and trades.deals():
                                    order_flow= compute_order_flow(trades.deals())
                                    self.order_flow_cache.update(order_flow.bid_volume, order_flow.ask_volume, order_flow.net_flow, order_flow.price_delta, order_flow.normalized_net_flow)
                        if (self.order_flow_cache is not None and self.rsi_value is not None and self.ob_cache is not None) and all(item != 0.0 for item in self.rsi_buffer):
                                await self._execute_strategy()
                    else:
                        logging.error(f"parse protobuf msg {self.msg_parser} failed.")
                else:
                    logging.warning(f"Non-bytes message: {msg}")
            except Exception as e:
                logging.error(f"cplus msg decoder fail on exception: {e}.")
                raise
    
    async def _execute_strategy(self):
        start_ns = time.time_ns()
        # Micro-structure filter
        if self.ob_cache.is_thin():
            return
        if all(item != 0.0 for item in self.rsi_buffer):
            rsi_mean = np.mean(self.rsi_buffer)
            rsi_std = np.std(self.rsi_buffer)
            print(f"mean: {rsi_mean}, std: {rsi_std}, rsi: {self.rsi_value}, close: {self.kline_cache.closing_price}")
        
        if (self.position is None and rsi_mean and rsi_std and self.prev_filled_price is None):
            entry_position =( 
              self.rsi_buffer[-2] < rsi_mean - rsi_std and
              self.rsi_buffer[-1] < rsi_mean and
              self.rsi_buffer[-1] >self.rsi_buffer[-2] and
              self.order_flow_cache.normalized_net_flow != -1 
            )
        if (self.position is None and rsi_mean and rsi_std and self.prev_filled_price):
            entry_position =(
              self.rsi_buffer[-2] < rsi_mean - rsi_std and
              self.rsi_buffer[-1] < rsi_mean and
              self.rsi_buffer[-1] >self.rsi_buffer[-2] and
              self.order_flow_cache.normalized_net_flow != -1 and
              self.ob_cache.asks <= self.prev_filled_price
            )
            if entry_position:
                print("*******entry********")
                print(f"buy sigal: prev rsi: {self.rsi_buffer[-2]},  curr rsi: {self.rsi_value},normalized flow: {self.order_flow_cache.normalized_net_flow}, price delta: {self.order_flow_cache.price_delta}")
                self._buy_order['timestamp'] = str(int(time.time() * 1000))
                self.filled_rsi = self.rsi_buffer[-1]
                # exec order
                buy_order_response= self.api_client.submit_orders(params = self._buy_order)
                buy_order_id = buy_order_response.get('orderId')
                buy_order_status = self.api_client.order_status(orderId= buy_order_id)
                if buy_order_status.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                    self.filled_qty = float(buy_order_status['executedQty'])
                    self.filled_entry_price = float(buy_order_status['cummulativeQuoteQty'])/self.filled_qty
                    self.position = 'LONG'
                    self.prev_filled_price = self.filled_entry_price
                    print(f"buy order filled: entry price : {self.filled_entry_price}")
                elif buy_order_status.get('status') == "NEW":
                    cancel_order = self.api_client.cancel_order(symbol = 'SOLUSDT', orderId = buy_order_id)
                    if cancel_order['status'] == 'CANCELED':
                        self.position = None
                        self.filled_entry_price = 0.0
                        self.filled_qty = 0.0
                        self.filled_rsi = 0.0
        if self.position == "LONG":
                curr_pnl = (self.ob_cache.bids - self.filled_entry_price)/self.filled_entry_price
                take_profit_condition = (
                    curr_pnl > 0.00025 and
                    self.rsi_buffer[-1] - self.filled_rsi > rsi_std and
                    self.order_flow_cache.normalized_net_flow != 1
                )
                if take_profit_condition:
                    print("********exit*******")
                    print(f"sell signal: rsi: {self.rsi_value}, normalized flow: {self.order_flow_cache.normalized_net_flow}, price delta: {self.order_flow_cache.price_delta}")
                    self._sell_order["quantity"] = str(self.filled_qty)
                    self._sell_order['timestamp'] = str(int(time.time() * 1000))
                    try:
                        sell_order_response =  self.api_client.submit_orders(params = self._sell_order) 
                        sell_order_id = sell_order_response.get('orderId')
                        sell_order_status =  self.api_client.order_status(orderId = sell_order_id)
                        if sell_order_status.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                            filled_sell_qty = float(sell_order_status['executedQty'])
                            filled_sell_price = float(sell_order_status['cummulativeQuoteQty'])/filled_sell_qty
                            print(f"sell order filled: exit price:{filled_sell_price}")
                            if filled_sell_qty == self.filled_qty:
                                print(f"position cleared: profit: {filled_sell_price*self.filled_qty - self.filled_qty*self.filled_entry_price}, entry: {self.filled_entry_price},  exit: {filled_sell_price}")
                                self.position = None
                                self.filled_entry_price = 0.0
                                self.filled_qty = 0.0
                            else:
                                print("position is not cleared in full.")
                    except Exception as e:
                        logging.error(f"submit market order exec failed on exception: {e}.")
        else:
            pass
        #latency checks
        self.last_latency = (time.time_ns() - start_ns) / 1e6
        if self.last_latency > 2.0:  # 2ms threshold
            logging.warning(f"Slow execution: {self.last_latency:.2f}ms")  
   
async def main(exchange: str, api_key: SecurityManager, api_secret: SecurityManager, topics: List[dict]):
    mexc_api_client = MexcApiClient(api_key = api_key, api_secret=api_secret)
    sol_take_profit_instance = TakeProfit(exchange = exchange, topics = topics, api_client = mexc_api_client)
    await asyncio.gather(
        sol_take_profit_instance.connect(),
    )

if __name__=='__main__':
    exchange = 'mexc'
    topics = [{"method": "SUBSCRIPTION", "params":["spot@public.aggre.bookTicker.v3.api.pb@100ms@SOLUSDT", "spot@public.kline.v3.api.pb@SOLUSDT@Min1", "spot@public.aggre.deals.v3.api.pb@100ms@SOLUSDT"]}]
    api_key = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f"{exchange.upper()}_API_KEY"])
    api_secret = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f"{exchange.upper()}_SECRET"])
    asyncio.run(main(exchange = exchange, api_key=api_key, api_secret=api_secret, topics=topics))



