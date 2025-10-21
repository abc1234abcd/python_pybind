import asyncio
from typing import List
import logging
from pathlib import Path
from dotenv import dotenv_values

from core.future_data_streamer import FutureDataStreamer
from core.aioapiclient import AioMexcApiClient
from utils.security import SecurityManager


class FutureMarketRunner(FutureDataStreamer):
    def __init__(self, exchange: str, topics: List[dict], api_client: AioMexcApiClient):
        super().__init__(exchange, topics)
        self.api_client = api_client

    async def _message_handler(self):  
            while self._is_active and self.ws:
                try:
                    #binary protobuf
                    msg = await self.ws.recv()           
                    ticker_raw = msg['data']
                    
                except Exception as e:
                     logging.error(f"future marekt runner fails on msg hander exception: {e}.")

async def main(exchange: str, api_key: SecurityManager, api_secret: SecurityManager,topics: List[dict], timeout:tuple):
        mexc_aio_client_instance = AioMexcApiClient(api_key = api_key, api_secret = api_secret, timeout = timeout)
        future_market_runner_instance = FutureMarketRunner(exchange = exchange, topics = topics, api_client = mexc_aio_client_instance)
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
     symbol = 'SUI_USDT'
     timeout = tuple((6,3))
     topics =[{"method": "sub.ticker", "param": {"symbol":f"{symbol}"}}]
     api_key = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f'{exchange.upper()}_API_KEY'])
     api_secret = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f'{exchange.upper()}_SECRET'])
     asyncio.run(main(exchange = exchange, api_key = api_key, api_secret = api_secret, topics = topics, timeout = timeout))
    
         
