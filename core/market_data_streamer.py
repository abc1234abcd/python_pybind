import asyncio
import json 
import logging 
import time
from queue import Queue
from websockets import connect 
from utils.data_class import Exchange
from typing import List, Any
from core.mexc_api import MexcApiClient
from mexc_protobuf import PushDataV3ApiWrapper_pb2
from proto_wrapper_mexc import PushDataV3ApiWrapper

class MarketDataStreamer:    
    def __init__(self, exchange: str, kline_queue: Queue, trades_queue: Queue, book_ticker_queue: Queue, topics: List[Any]):
        self.exchange = Exchange(exchange.lower())
        self.kline_queue = kline_queue
        self.trades_queue = trades_queue
        self.book_ticker_queue = book_ticker_queue
        self.topics = topics
        self.ws = None
        self._is_active = False
    async def connect(self):
        self._is_active = True
        while self._is_active:
            try:
                async with connect(self.exchange.public_socket_url, ping_interval = None) as websocket:
                    self.ws = websocket 
                    logging.info(f"{self.exchange.name} connects to public websocket success!")
                    await self.subscribe()
                    await asyncio.gather(
                        self._connection_manager(),
                        self.message_decoder_cplus()
                        )
            except Exception as e:
                logging.error(f"{self.exchange.name} connect failed: {e}. Reconnecting immediately...")
    async def subscribe(self):
        if not self.ws:
            logging.error(f"{self.exchange.name} is not connected yet while trying to make subscription.") 
        if (self.topics and self.ws):
            try:
                for topic in self.topics:
                    await self.ws.send(json.dumps(topic))
            except Exception as e:
                logging.error(f"{self.exchange.name} subscription failed: {e}.")
                raise
    async def _connection_manager(self):
        if not (self.exchange.ping_message and self.exchange.ping_interval):
            return
        while self._is_active:
            try:
                await self.ws.send(json.dumps(self.exchange.ping_message))
                await asyncio.sleep(30)
            except Exception as e:
                logging.error(f"{self.exchange.name} conenction manager failed pinging (retry in 2s).")
                await asyncio.sleep(2)
    async def message_decoder_py(self):
        #pre-allocate avoid overhead
        result = PushDataV3ApiWrapper_pb2.PushDataV3ApiWrapper()
        while (self._is_active and self.ws):
            try:
                #binary protobuf 
                msg = await self.ws.recv()
                result.ParseFromString(msg)
                print(f"python parser: {result}.")
            except Exception as e:
                logging.error(f"either data streamer stopped or websocket lost connection so message_decoder_py failed:{e}.")
                raise
    #no queue re-direct but generate signal as soon as msg is received.
    async def message_decoder_cplus(self):
        msg_protobuf_holder = PushDataV3ApiWrapper()
        while self._is_active and self.ws:
            try:
                msg = await self.ws.recv()                
                if isinstance(msg, bytes):
                    #this msg_protobuf_holder has all msg that subscribed from the 3 topics.
                    if msg_protobuf_holder.parse(msg):
                        #print(f"channel: {msg_protobuf_holder.channel}, symbol: {msg_protobuf_holder.symbol}")
                        if msg_protobuf_holder.has_kline():
                            kline = msg_protobuf_holder.kline()
                            kline_dict = {
                                "symbol": msg_protobuf_holder.symbol,
                                "timestamp": msg_protobuf_holder.send_time(),
                                "openingprice": kline.opening_price(),
                                "closingprice": kline.closing_price(),
                                "windowstart": kline.window_start(),
                                "windowend": kline.window_end(),
                            }
                            print(kline_dict)
                        elif msg_protobuf_holder.has_book_ticker():
                            book = msg_protobuf_holder.book_ticker()
                            book_ticker_dict = {

                            }
                        elif msg_protobuf_holder.has_public_aggredeals():
                            trades = msg_protobuf_holder.trades()
                            #for deal in trades.deals():
                                #print(f"trades {deal.time()} {deal.quantity()} {deal.price()}{deal.trade_type()}")
                        else:
                            logging.error(f"{msg} parsed but no recognized data type")
                    else:
                        logging.error("Failed to parse protobuf message")
                else:
                    logging.warning(f"Non-bytes message: {msg}")
            except Exception as e:
                logging.error(f"cplus message decoder error:{e}.")
                raise
    async def safe_close(self) -> None:
        self._is_active = False
        if hasattr(self, 'ws') and self.ws:
            try:
                if not self.ws.closed:
                    await self.ws.close(code=1000)
                logging.info(f"{self.exchange.name} websocket closed safely.")
            except Exception as e:
                logging.error(f"{self.exchange.name} websocket closing on exception: {e}.")
            finally:
                self.ws = None
 
