import asyncio
from websockets import connect
from abc import ABC, abstractmethod
from string import List, Any
from utils.data_class import Exchange
import logging
import json

class FutureMarketDataStreamer(ABC):    
    def __init__(self, exchange: str, topics: List[Any]):
        self.exchange = Exchange(exchange.lower())
        self.topics = topics
        self.ws = None
        self._is_active = False
    async def connect(self):
        self._is_active = True
        while self._is_active:
            try:
                async with connect(self.exchange.future_socket_url, ping_interval = None) as websocket:
                    self.ws = websocket 
                    logging.info(f"{self.exchange.name} connects to future websocket success!")
                    await self.subscribe()
                    await asyncio.gather(
                        self._ping_manager(),
                        self._message_handler()
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
                logging.error(f"{self.exchange.name} subscription {topic} failed: {e}.")
                raise
    @abstractmethod
    async def _message_handler(self):
       pass
    async def _ping_manager(self):
        if not (self.exchange.ping_message and self.exchange.ping_interval):
            return
        while self._is_active:
            try:
                await asyncio.gather(
                self.ws.send(json.dumps(self.exchange.ping_message)),
                asyncio.sleep(self.exchange.ping_interval)
                )
            except Exception as e:
                logging.error(f"{self.exchange.name} conenction manager failed pinging (retry immediately).")
                await asyncio.sleep(0)
    async def safe_close(self) -> None:
        self._is_active = False
        if hasattr(self, 'ws') and self.ws:
            try:
                if not hasattr(self.ws, 'closed'):
                    await self.ws.close(code=1000)
                logging.info(f"{self.exchange.name} websocket closed safely.")
            except Exception as e:
                logging.error(f"{self.exchange.name} websocket closing on exception: {e}.")
            finally:
                self.ws = None
