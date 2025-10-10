import asyncio
from string import Any, List
import logging
from pathlib import Path
from dotenv import dotenv_values

from core.future_data_streamer import FutureMarketDataStreamer
from core.aioapiclient import AioMexcApiClient
from utils.security import SafeString, SecurityManager

from proto_wrapper_mexc import PushDataV3ApiWrapper

class FutureMarketRunner(FutureMarketDataStreamer):
    def __init__(self, exchange: str, topics: List[Any], api_client: AioMexcApiClient):
        super().__init__(exchange, topics)
        self.msg_parser = PushDataV3ApiWrapper()
        self.api_client = api_client

    async def _message_handler(self):  
            while self._is_active and self.ws:
                try:
                    #binary protobuf
                    msg = await self.ws.recv()                
                    if isinstance(msg, bytes):
                        if self.msg_parser.parse(msg):
                            print(self.msg_parser())
                except Exception as e:
                     logging.error(f"future marekt runner fails on msg hander exception: {e}.")

    async def main(exchange: str, api_key: SecurityManager, api_secret: SecurityManager,topics: List[Any], timeout:tuple):
         mexc_aio_client_instance = AioMexcApiClient(api_key = api_key, api_secret = api_secret, timeout = timeout)
         future_market_runner_instance = FutureMarketRunner(exchange, topics)
         try:
              await asyncio.gather(
                future_market_runner_instance.connect(),
                mexc_aio_client_instance.create_session()
                )
         finally:
              await asyncio.gather(
                   future_market_runner_instance.safe_close(),
                   mexc_aio_client_instance.close_session()
              )


if __name__=='__main__':
     exchange = 'mexc'
     symbol = 'SUIUSDT'
     timeout = tuple((6,3))
     topics =[{"method":"sub.funding.rate","param":{"symbol":"BTC_USDT"}}]
     api_key = SecurityManager(dotenv_values(Path(__file__).parent/".env"))[f'{exchange.upper()}_API_KEY']
     api_secret = SecurityManager(dotenv_values(Path(__file__).parent/".env"))[f'{exchange.upper()}_SECRET']
     asyncio.run(exchange = exchange, api_key = api_key, api_secret = api_secret, topics = topics, timeout = timeout)
    
         

