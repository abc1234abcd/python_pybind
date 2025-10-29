import time
import logging
import asyncio
import numpy as np
import thread
from typing import List, Tuple, Any
from pathlib import Path
from dotenv import dotenv_values
from utils.security import SecurityManager
from utils.data_class import OrderSide, OrderType, Kline, BookTicker, OrderFlow, LimitDepthsOB, Market, DataType
from core.data_streamer import DataStreamer
from core.aioapiclient import AioMexcApiClient
from dotenv import load_dotenv
#from numba import njit: consumes too much cache, and re-compile consumes way too much time 
import copy
#C++ extentions
from proto_wrapper_mexc import PushDataV3ApiWrapper
from rsi_calculator import RSICalculator
from slope_calculator import calculate_slope
from order_flow import compute_order_flow


class SOne(DataStreamer):
    def __init__(self, ticker: str, exchange: str,  exchange_client: AioMexcApiClient):
        super().__init__(exchange, market, data_type, topics, exchange_client)
        #protobuf msg parser
        self.msg_parser = PushDataV3ApiWrapper()
        #return data from DataStreame
        self.kline = Kline()
        self.ob_ticker = BookTicker()
        self.order_flow = OrderFlow()
        self.limit_depths_ob = LimitDepthsOB()

        self.exchange_client = exchange_client

        #pre-allocate buy/sell order
        self.max_position = "200" 
        self._buy_order = {
            "quoteOrderQty":  self.max_position,  
            "side": OrderSide.BUY.value,
            "symbol": "XRPUSDT",
            "timestamp": None,  
            "type": OrderType.MARKET.value
        }
        self._sell_order = {
            "quantity": None,  
            "side": OrderSide.SELL.value,
            "symbol": "XRPUSDT",
            "timestamp": None,  
            "type": OrderType.MARKET.value
        }

    async def _message_handler(self):  
            while self._is_active and self.ws:
                try:
                    #binary protobuf
                    msg = await self.ws.recv()                
                    if isinstance(msg, bytes):
                        if self.msg_parser.parse(msg):
                            #ob_ticker: 
                            if self.msg_parser.has_book_ticker():
                                book = self.msg_parser.book_ticker()
                                self.ob_ticker.update(
                                    bids=float(book.bid_price()),
                                    asks=float(book.ask_price()),
                                    bids_qty = float(book.bid_quantity()),
                                    asks_qty = float(book.ask_quantity())
                                )
                                print(f"ob_ticker: {self.ob_ticker}/ {book}")
                            #kline
                            if self.msg_parser.has_kline():
                                kline = self.msg_parser.kline()
                                self.kline.update(kline.closing_price(), kline.highest_price(), kline.lowest_price(), kline.opening_price(), kline.window_start(), kline.volume())
                                print(f"kline: {self.kline} /{kline}")
     
                            #limit depths of order book: 20 levels, generates book dynamic buy pressure based on bid and ask qantity gap in ptc.
                            if self.msg_parser.has_public_limit_depths():
                                temp_limit_depths_ob = self.msg_parser.limit_depths()
                                self.limit_depths_ob.update(temp_limit_depths_ob.bids(), temp_limit_depths_ob.asks())
                                print(f"20 level book: {self.limit_depths_ob} /{temp_limit_depths_ob}")
                                self.book_buy_pressure = self.limit_depths_ob.book_buy_pressure
                                print(f"20 lvel book: {self.book_buy_pressure}")
                            #order flows: based on market order at each push time interval, the bid and ask quantity gap in pct.
                            if self.msg_parser.has_public_aggredeals():
                                    trades = self.msg_parser.trades()
                                    print(f"trades : {trades}")
                                    if trades and trades.deals():
                                        order_flow= compute_order_flow(trades.deals())
                                        self.order_flow.update(order_flow.bid_volume, order_flow.ask_volume, order_flow.net_flow, order_flow.price_delta, order_flow.normalized_net_flow)
                                        print(f"flow: {self.order_flow}/ {trades}")
                        else:
                            logging.error(f"parse protobuf msg {self.msg_parser} failed.")
                    else:
                        logging.warning(f"Non-bytes message: {msg}")
                except Exception as e:
                    logging.error(f"cplus msg decoder fail on exception: {e}.")
                    raise
    async def _execute_strategy(self):
        #latency control
        start_ns = time.time_ns()
        # micro-structure filter: ob.asks - ob.bids > 0.0005, ob.is_stable <= 0.0001
        if self.ob_ticker.is_thin:
            return        
       #rsi threshold
        self.overbrought_threshold = self.rsi_mean + self.rsi_std
        self.oversold_threshold = self.rsi_mean - self.rsi_std
        #take profit parmas turning: 
        if self.kline_hr3_slope >= 0:
            self.take_profit_threshold = 0.001
        else:
            self.take_profit_threshold = 0.0005
        #kline shape signals
        curr_kline = copy.deepcopy(self.kline)
        prev_kline = copy.deepcopy(self.kline_buffer[-2])
        upper_body, _, lower_body = await self.kline_shape()
        prev_kline_is_hammer = False
        prev_kline_is_shooting_star = False

        if upper_body > 0.7:
            prev_kline_is_shooting_star = True
        elif lower_body > 0.7:
            prev_kline_is_hammer = True
        #define strong momentumn: 
        self.is_strong_upward = False
        self.is_strong_dropping = False

        if (self.kline_slope > 0  and curr_kline.highest_price == curr_kline.closing_price) or (self.book_buy_pressure > 0.8 and self.order_flow.normalized_net_flow == 1):
            self.is_strong_upward = True
        elif (self.kline_slope < 0 and curr_kline.lowest_price == curr_kline.closing_price) or self.book_buy_pressure < -0.8:
            self.is_strong_dropping = True
        print(f"is strong up: {self.is_strong_upward}, is strong down: {self.is_strong_dropping}")
        #entry: the self.resist_level is the lowest price in the past 14 minutes, which if the mean price and use martigale "stopping time" to decide my exit strategy.
        #the entry is wrong completely: if i entry when is strong, then strong signal only gets weaker and weaker, 
        strong_entry_condition = (self.rsi_momentum > 0 and self.ob_ticker.asks < self.resist_level - 0.0015 and curr_kline.closing_price > curr_kline.opening_price)
        weak_entry_condition = (self.rsi_momentum > 0 and self.ob_ticker.asks < self.resist_level -0.002 and curr_kline.closing_price > curr_kline.opening_price)
        if self.position is None:
            if self.prev_exit_time is None:
                if self.is_strong_upward:
                    entry_condition = strong_entry_condition
                elif not self.is_strong_upward:
                    entry_condition = weak_entry_condition 
            else: #not None
                curr_time = int(time.time()*1000)
                same_window = (curr_time//60000 == self.prev_exit_time//60000)
                if same_window:
                    if self.is_strong_upward:
                        entry_condition = (
                           strong_entry_condition and
                           self.ob_ticker.asks < self.prev_exit_price - 0.0015
                        )
                    elif not self.is_strong_upward:
                        entry_condition = (
                        weak_entry_condition and 
                        self.ob_ticker.asks < self.prev_exit_price - 0.002
                        )
                else:
                    if self.is_strong_upward:
                        entry_condition = strong_entry_condition
                    elif not self.is_strong_upward:
                        entry_condition = weak_entry_condition
            if entry_condition:
                self._buy_order['timestamp'] = str(int(time.time() * 1000))
                # exec market buy order
                try:
                    buy_order_response= await self.api_client.submit_orders(params = self._buy_order)
                    buy_order_id = buy_order_response.get('orderId')
                    buy_order_status = await self.api_client.order_status(orderId= buy_order_id)
                    if buy_order_status.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                        self.filled_qty = float(buy_order_status['executedQty'])
                        self.filled_entry_price = float(buy_order_status['cummulativeQuoteQty'])/self.filled_qty
                        self.filled_rsi = self.rsi_value
                        self.position = 'LONG'
                        print("**************************************")
                        print("**************entry*******************")
                        print(f"(price:{curr_kline.closing_price}, curr slope:{self.kline_slope},rsi: {self.rsi_value, self.rsi_mean}, buy pressure:{self.book_buy_pressure}, {self.resist_level, self.support_level}")
                        print(f"close: {self.kline.closing_price}, rsi: {self.rsi_value}, rsi_mean: {self.rsi_mean}, entry price : {self.filled_entry_price}")
                        print("**************************************")
                        print("**************************************")
                    elif buy_order_status.get('status') == "NEW":
                        print("order exec failed.")
                        cancel_order = await self.api_client.cancel_order(symbol = 'XRPUSDT', orderId = buy_order_id)
                        if cancel_order['status'] == 'CANCELED':
                            await self._reset_position()         
                except Exception as e:
                    logging.error(f"market buy order exec failed on execption: {e}.")
        elif self.position == "LONG":
                curr_pnl = self.ob_ticker.bids - self.filled_entry_price
                #my exit cannot depends on the future point t+1 as i would never know now. i need either do a prediction based on simple moving average or 
                if self.is_strong_upward:
                    take_profit_condition = (
                        curr_pnl > 0.001 and
                        self.rsi_momentum < 0 )
                else:
                    take_profit_condition = (
                        curr_pnl >  0.001 and
                        self.rsi_momentum < 0
                    )
                if take_profit_condition:
                    self._sell_order["quantity"] = str(self.filled_qty)
                    self._sell_order['timestamp'] = str(int(time.time() * 1000))
                    try:
                        sell_order_response =  await self.api_client.submit_orders(params = self._sell_order) 
                        sell_order_id = sell_order_response.get('orderId')
                        sell_order_status =  await self.api_client.order_status(orderId = sell_order_id)
                        if sell_order_status.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                            filled_sell_qty = float(sell_order_status['executedQty'])
                            filled_sell_price = float(sell_order_status['cummulativeQuoteQty'])/filled_sell_qty
                            self.prev_exit_time = int(time.time()*1000)
                            if filled_sell_qty == self.filled_qty:
                                print("**************************************")
                                print("**************exit********************")
                                print(f"(price:{curr_kline.closing_price}, curr slope:{self.kline_slope},rsi: {self.rsi_value, self.rsi_mean}, buy pressure:{self.book_buy_pressure}, {self.resist_level, self.support_level}")
                                print(f"position cleared: profit: {filled_sell_price*self.filled_qty - self.filled_qty*self.filled_entry_price}, entry: {self.filled_entry_price},  exit: {filled_sell_price}")
                                print("**************************************")
                                print("**************************************")
                                self.prev_exit_price = filled_sell_price
                                await self._reset_position()
                            else:
                                print("position is not cleared in full.")
                    except Exception as e:
                        logging.error(f"buy order failed exec on exception: {e}.")
        #latency checks
        self.last_latency = (time.time_ns() - start_ns) / 1e6
        if self.last_latency > 2.0:  # 2ms threshold
            logging.warning(f"Slow execution: {self.last_latency:.2f}ms")  
    async def _reset_position(self):
        self.position = None
        self.filled_entry_price = 0.0
        self.filled_qty = 0.0
        self.filled_rsi = 0.0
    async def kline_shape(self):
        prev_kline = copy.deepcopy(self.kline_buffer[-2])
        full_body = prev_kline.highest_price - prev_kline.lowest_price
        if full_body < 1e-3:
            return 0.0,0.0,0.0
        else:
            upper_body = (prev_kline.highest_price - max(prev_kline.opening_price, prev_kline.closing_price))/full_body
            middle_body = (min(prev_kline.opening_price, prev_kline.closing_price) - prev_kline.lowest_price)/full_body
            lower_body = 1- upper_body - middle_body
            return upper_body, middle_body, lower_body
async def main(api_key: SecurityManager, api_secret: SecurityManager, timeout: Tuple, spot_public_topics: List[Any], spot_private_topics: List[Any]):
    exchange = "mexc"

    aio_exchange_client = AioMexcApiClient(api_key=api_key, api_secret=api_secret, timeout=timeout)
    mexc_public_streamer = await SOne.public_streamer(exchange, market, data_type, spot_public_topics)
    mexc_private_streamer = await SOne.private_streamer(exchange, market, data_type, spot_private_topics, aio_exchange_client)
    try:
        await asyncio.gather(
            mexc_public_streamer.connect(),
            mexc_private_streamer.connect(),
        )
    finally:
        await asyncio.gather(
            mexc_public_streamer.safe_close(),
            mexc_private_streamer.safe_close(),
        )

if __name__=='__main__':
    exchange = 'mexc'
    symbol = "XRPUSDT"
    ob_depth_level = 20
    timeout = tuple((6, 3))
    market = Market.SPOT
    data_type = DataType.PUBLIC
    mexc_spot_public_topics = [{"method": "SUBSCRIPTION", "params":[f"spot@public.aggre.bookTicker.v3.api.pb@100ms@{symbol}", f"spot@public.kline.v3.api.pb@{symbol}@Min1", f"spot@public.aggre.deals.v3.api.pb@100ms@{symbol}", f"spot@public.limit.depth.v3.api.pb@{symbol}@{ob_depth_level}"]}]

    api_key = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f"{exchange.upper()}_API_KEY"])
    api_secret = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f"{exchange.upper()}_SECRET"])

    asyncio.run(main(exchange = exchange, market = market, data_type=data_type, topics=topics))


'''

mexc_spot_public_streamer = DataStreamer.public_streamer("mexc", Market.SPOT, DataType.PUBLIC, spot_public_topics)

aio_client = ...

mexc_spot_private_streamer = DataStreamer.private_streamer("mexc", Market.SPOT, DataType.PUBLIC, spot_public_topics, aio_client)

mexc_futures_public_streamer = DataStreamer.public_streamer("mexc", Market.FUTURES, DataType.PUBLIC, futures_public_topics)

await asyncio.gather(
    streamer.connect()
)



'''
