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

class TakeProfit(MarketDataStreamer):
    def __init__(self, exchange: str, topics: List[dict], api_client: MexcApiClient):
        super().__init__(exchange, topics)
        self.api_client = api_client
        self.msg_parser = PushDataV3ApiWrapper()
        #rsi 
        self.rsi_calculator = RSICalculator(7)
        self.kline = None
        self.rsi_value = None
        self.rsi_value_buffer = np.zeros(2, dtype=np.float32)
        
        #book ticker cache
        self.ob_cache = OrderBookCache()

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
        self.stop_loss_pct = 0.001 
        self.take_profit = 0.001
        self.oversold_threshold = 38
        self.overbought_threshold = 65
        self.position = None
         
        #latency control notification
        self.last_latency = 0

        #order flow
        self.order_flow = None
        self.price_delta = 0.0
        self.normalized_net_flow = 0.0

    async def _message_handler(self):  
        with open('st_validation.csv', 'w') as file:
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
                                self.kline = self.msg_parser.kline()
                                self.rsi_value = self.rsi_calculator.update(np.float32(self.kline.closing_price()))
                            #market tardes and order_flow
                            if self.msg_parser.has_public_aggredeals():
                                    trades = self.msg_parser.trades()
                                    if trades and trades.deals():
                                        self.order_flow = compute_order_flow(trades.deals())
                                        self.normalized_net_flow = self.order_flow.normalized_net_flow
                                        self.price_delta = self.order_flow.price_delta
                            if (self.order_flow is not None and self.rsi_value is not None and self.ob_cache is not None):
                                 await self._execute_strategy(file)
                        else:
                            logging.error(f"parse protobuf msg {self.msg_parser} failed.")
                    else:
                        logging.warning(f"Non-bytes message: {msg}")
                except Exception as e:
                    logging.error(f"cplus msg decoder fail on exception: {e}.")
                    raise

    @njit(cache=True, nogil=True)
    def _calculate_size(self, price: float, stop_loss: float) -> float:
        risk_amount = self.api_client.account_balance() * 0.01  # 1% risk
        loss_per_unit = abs(price - stop_loss)
        return min(risk_amount / loss_per_unit, self.max_position)
    
    async def _execute_strategy(self, file):
        start_ns = time.time_ns()
        # Micro-structure filter
        if self.ob_cache.is_thin():
            return
        if self.position == None:
            entry_position =( 
                self.normalized_net_flow > 0 and
                self.price_delta > 0 and
                self.kline.closing_price() >= self.kline.lowest_price() and
                self.rsi_value < self.oversold_threshold
            )
            if entry_position:
                self._buy_order['timestamp'] = str(int(time.time() * 1000))
                # exec order
                buy_order_response= self.api_client.submit_orders(params = self._buy_order)
                buy_order_id = buy_order_response.get('orderId')
                buy_order_status = self.api_client.order_status(orderId= buy_order_id)
                if buy_order_status.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                    self.filled_qty = float(buy_order_status['executedQty'])
                    self.filled_entry_price = float(buy_order_status['cummulativeQuoteQty'])/self.filled_qty
                    self.position = 'LONG'
                    print(f"buy order filled: entry price : {self.filled_entry_price}")
                elif buy_order_status.get('status') == "NEW":
                    cancel_order = self.api_client.cancel_order(symbol = 'SOLUSDT', orderId = buy_order_id)
                    if cancel_order['status'] == 'CANCELED':
                        self.position = None
                        self.filled_entry_price = 0.0
                        self.filled_qty = 0.0
        elif self.position == "LONG":
                curr_pnl = (self.ob_cache.bids - self.filled_entry_price)/self.ob_cache.bids
                take_profit_condition = (
                    curr_pnl > 1.008 and
                    self.normalized_net_flow < 0 and
                    self.price_delta < 0 
                )
                if take_profit_condition:
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
                elif self.ob_cache.bids - self.filled_entry_price < -(self.filled_entry_price*self.stop_loss_pct):
                    self._sell_order["quantity"] = self.filled_qty
                    self._sell_order['timestamp'] = int(time.time()*1000)
                    try:
                        sell_order_response = self.api_client.submit_orders(self._sell_order) 
                        sell_order_id = sell_order_response['orderId']
                        sell_order_status =  self.api_client.order_status(orderId = sell_order_id)
                        if sell_order_status['status'] in ['FILLED', 'PARTIALLY_FILLED']:
                            filled_sell_qty = float(sell_order_status['executedQty'])
                            filled_sell_price = float(sell_order_status['cummulativeQuoteQty'])/filled_sell_qty
                            if filled_sell_qty == self.filled_qty:
                                print(f"stop loss order exec: loss: {filled_sell_price*self.filled_qty - 10.0}, entry: {self.filled_entry_price}, exit: {filled_sell_price}")
                        self.position = None
                        self.filled_entry_price = 0.0
                        self.filled_qty = 0.0
                    except Exception as e:
                        logging.error(f"stop loss order exec failed on exception: {e}.")
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



