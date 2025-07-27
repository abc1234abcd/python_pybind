import asyncio
import json 
import orjson
import logging 
import time
from queue import Queue
from websockets import connect 
from utils.data_class import Exchange
from typing import List
from mexc_protobuf import PushDataV3ApiWrapper_pb2

#pybind11
from proto_wrapper_mexc import PushDataV3ApiWrapper

class MarketDataStreamer:
    def __init__(self, exchange: str, queue: Queue, topics: List[dict]):
        self.exchange = Exchange(exchange.lower())
        self.queue = queue
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
                        self.message_decoder_cplus_two()
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
                ping_start_time = time.perf_counter()
                await self.ws.send(json.dumps(self.exchange.ping_message))
                elapsed = time.perf_counter() - ping_start_time
                #hardcoded inteval[int] takes seconds as unit
                ping_interval_integer = 60
                ping_precise_sleep_time = max(0, ping_interval_integer - elapsed)
                await asyncio.sleep(ping_precise_sleep_time)
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
                if isinstance(msg, bytes):
                    try:
                        #no copy processing: no need of this if msg tiny
                        with memoryview(msg) as mv:
                            msg_len = int.from_bytes(mv[:4], 'big')
                            msg_type = mv[4]
                            payload = mv[5:5+msg_len]
                            # python parser
                            result.ParseFromString(msg)
                            print(result)
                    except Exception as e:
                        logging.error(f"python message decoder error: {e}")
                        raise
            except Exception as e:
                logging.error(f"either data streamer stopped or websocket lost connection so message_decoder_py failed:{e}.")
                raise
    async def message_decoder_cplus(self):
        msg_protobuf_holder = PushDataV3ApiWrapper()
        while self._is_active and self.ws:
            try:
                msg = await self.ws.recv()                
                if isinstance(msg, bytes):
                    if msg_protobuf_holder.parse(msg):
                        print(f"Channel: {msg_protobuf_holder.channel}")
                        if msg_protobuf_holder.has_kline():
                            kline = msg_protobuf_holder.kline()
                            print(f"Kline: {kline.interval} {kline.opening_price}")
                        elif msg_protobuf_holder.has_book_ticker():
                            book = msg_protobuf_holder.book_ticker()
                            print(f"BookTicker: {book.bid_price}x{book.bid_quantity}")
                        else:
                            logging.error("Message parsed but no recognized data type")
                    else:
                        logging.error("Failed to parse protobuf message")
                else:
                    logging.error(f"Non-bytes message: {msg}")
            except Exception as e:
                logging.error(f"cplus message decoder error:{e}.")
                await asyncio.sleep(1)  
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
        if hasattr(self.redis) and self.redis:
            try:
                self.redis.close()
                await self.redis.wait_closed()
                logging.info(f"{self.exchange} redis connection closed.")
            except Exception as e:
                logging.error(f"error closing redis.")
