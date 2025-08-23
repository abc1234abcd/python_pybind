import time
import logging
import asyncio
import numpy as np
from typing import List
from pathlib import Path
from dotenv import dotenv_values
from utils.security import SecurityManager
from utils.data_class import OrderSide, OrderType, KlineCache, OrderBookCache, OrderFlowCache
from core.market_data_streamer import MarketDataStreamer
from core.mexc_api import MexcApiClient
from numba import njit

#C++ extention
from proto_wrapper_mexc import PushDataV3ApiWrapper
from rsi_calculator import RSICalculator
from slope_calculator import calculate_slope
from order_flow import compute_order_flow
'''

very bad

'''

class TakeProfit(MarketDataStreamer):

    def __init__(self, exchange: str, topics: List[dict], api_client: MexcApiClient):
        super().__init__(exchange, topics)
        self.api_client = api_client
        self.msg_parser = PushDataV3ApiWrapper()
        #rsi 
        self.rsi_calculator = RSICalculator(7)
        self.kline_cache = KlineCache()
        self.rsi_value = None

        self.ob_cache = OrderBookCache()
        self.order_flow_cache = OrderFlowCache()

        #buffer
        self.price_buffer = []

        #pre-allocate buy/sell order
        self.filled_entry_price = 0.0
        self.filled_qty = 0.0
        self.max_position = "9" 
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
        self.oversold_threshold = 0.0
        self.overbrought_threshold = 0.0
        self.position = None
        self.slope = 0.0
        self.filled_rsi = 0.0
        self.cummulated_price_delta = 0.0
        self.pnl_threshold = 0.0
        self.prev_window_start = None
        self.prev_kline_slope = None
        self.kline_slope = 0.0
        self.enter_timing = 0.0
        self.kline_slope_delta = 0.0
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
                                bids=float(book.bid_price()),
                                asks=float(book.ask_price()),
                                bids_qty = float(book.bid_quantity()),
                                asks_qty = float(book.ask_quantity())
                            )
                        #kline and rsi
                        if self.msg_parser.has_kline():
                            kline = self.msg_parser.kline()
                            self.kline_cache.update(kline.closing_price(), kline.highest_price(), kline.lowest_price(), kline.opening_price(), kline.window_start())
                            self.rsi_value = self.rsi_calculator.update(np.float32(self.kline_cache.closing_price))
                            #slope: kline slope 
                            if self.prev_window_start is None:
                                self.prev_window_start = self.kline_cache.window_start
                                self.price_buffer.append(self.kline_cache.closing_price)
                            else:
                                if self.prev_window_start == self.kline_cache.window_start:
                                    self.price_buffer.append(self.kline_cache.closing_price)
                                else:
                                    self.price_buffer = [self.kline_cache.closing_price]
                                    self.prev_window_start = self.kline_cache.window_start
                            self.kline_slope = calculate_slope(self.price_buffer)
                        #order_flow
                        if self.msg_parser.has_public_aggredeals():
                                trades = self.msg_parser.trades()
                                if trades and trades.deals():
                                    order_flow= compute_order_flow(trades.deals())
                                    self.order_flow_cache.update(order_flow.bid_volume, order_flow.ask_volume, order_flow.net_flow, order_flow.price_delta, order_flow.normalized_net_flow)
                        if self.ob_cache is not None and self.kline_slope != 0 and self.rsi_value:
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
        #kline slope momentum
        curr_kline_slope = self.kline_slope
        if self.prev_kline_slope is None:
            self.kline_slope_delta = 0
        else:
            self.kline_slope_delta = curr_kline_slope - self.prev_kline_slope
        self.prev_kline_slope = curr_kline_slope
        print(f"rsi: {self.rsi_value}, slope:{curr_kline_slope}, slope delta:{self.kline_slope_delta}, closing: {self.kline_cache.closing_price}, bid/ask: {self.ob_cache.bids_qty/self.ob_cache.asks_qty}, net flwo:{self.order_flow_cache.normalized_net_flow}")

        upward_treding = (self.kline_slope_delta >= 0 and self.order_flow_cache.normalized_net_flow >=0  and self.ob_cache.bids_qty/self.ob_cache.asks_qty >= 1) or(curr_kline_slope > 0 and self.kline_slope_delta >0 and self.order_flow_cache.normalized_net_flow != -1)
        strong_upward = (curr_kline_slope > 0.01 )
        strong_dropping = (curr_kline_slope < -0.01)

        if self.position is None and self.prev_kline_slope is not None and curr_kline_slope:
            entry_position =(
              upward_treding and
              not strong_dropping and 
              self.rsi_value < 60 
            )
            if entry_position:
                print("****************entry*****************")
                print(self.prev_kline_slope, curr_kline_slope, self.rsi_value, self.ob_cache.bids_qty/self.ob_cache.asks_qty)
                self._buy_order['timestamp'] = str(int(time.time() * 1000))
                # exec order
                try:
                    buy_order_response= self.api_client.submit_orders(params = self._buy_order)
                    buy_order_id = buy_order_response.get('orderId')
                    if buy_order_id:
                        try:
                            buy_order_status = self.api_client.order_status(orderId= buy_order_id)
                            if buy_order_status.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                                self.filled_qty = float(buy_order_status['executedQty'])
                                self.filled_entry_price = float(buy_order_status['cummulativeQuoteQty'])/self.filled_qty
                                self.filled_rsi = self.rsi_value
                                self.position = 'LONG'
                                self.enter_timing = time.time_ns()
                                print(f"buy order filled: entry price : {self.filled_entry_price}")
                            elif buy_order_status.get('status') == "NEW":
                                print("order exec failed.")
                                cancel_order = self.api_client.cancel_order(symbol = 'SOLUSDT', orderId = buy_order_id)
                                if cancel_order['status'] == 'CANCELED':
                                    self.position = None
                                    self.filled_entry_price = None
                                    self.filled_qty = None
                                    self.filled_rsi = None
                                    self.prev_kline_slope = None 
                                    self.price_buffer = []
                                    self.enter_timing = 0.0
                        except Exception as e:
                            raise f"buy oder status failed on exception: {e}"
                except Exception as e:
                    raise f"buy order exec faile on exception:{e}"
        elif self.position == "LONG":
                curr_pnl = (self.ob_cache.bids- self.filled_entry_price)/self.filled_entry_price
                holding_time = (time.time_ns() - self.enter_timing)/1e9
                take_profit_condition = (
                    (curr_pnl > 0.0001 and not strong_upward))
                if take_profit_condition:
                    print("********exit*******")
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
                                self.filled_rsi = 0.0
                                self.enter_timing = 0.0
                            else:
                                print("position is not cleared in full.")
                    except Exception as e:
                        logging.error(f"submit market order exec failed on exception: {e}.")
                elif self.ob_cache.bids - self.filled_entry_price < -(self.filled_entry_price*0.1):
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
                        self.filled_rsi = 0.0
                        self.enter_timing = 0.0
                    except Exception as e:
                        logging.error(f"stop loss order exec failed on exception: {e}.")
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



