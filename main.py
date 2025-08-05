import logging
import asyncio
from dotenv import dotenv_values
from queue import Queue
from pathlib import Path
from typing import List
from core.mexc_api import MexcApiClient
from utils.security import SecurityManager
from log_config import configure_logging
from core.market_data_streamer import MarketDataStreamer
from core.user_data_streamer import UserDataStreamer


async def shutdown(data_streamers):
    logging.info("Initiating shutdown...")
    await asyncio.gather(
        *(data_streamer.safe_close() for data_streamer in data_streamers)
    )
    logging.info('Showdown complete.')
    logging.shutdown()

async def main(exchange: str, market_data_topics: List, user_data_topics: List, api_key: SecurityManager, api_secret: SecurityManager):
    kline_queue = Queue()
    trades_queue = Queue()
    book_ticker_queue = Queue()
    market_data_streamer_instance = MarketDataStreamer(exchange = exchange, kline_queue=kline_queue, trades_queue = trades_queue, book_ticker_queue=book_ticker_queue, topics=market_data_topics)
    #user_data_queue = Queue()
    #user_data_streamer_instance = UserDataStreamer(exchange = exchange, queue = user_data_queue, topics = user_data_topics, api_key=api_key, api_secret=api_secret)
    try:
        await asyncio.gather(
            #user_data_streamer_instance.connect(),
            market_data_streamer_instance.connect()
        )
    except KeyboardInterrupt:
        logging.info("Receved KeyboardInterrupt, shutting down gracefully...")
        market_data_streamer_instance._is_active = False
        #user_data_streamer_instance._is_active = False
        await asyncio.gather(
            market_data_streamer_instance.safe_close(),
            #user_data_streamer_instance.safe_close()
        )
    except Exception as e:
        logging.error(f"main script throw error on exception:{e}.")
        await asyncio.gather(
            market_data_streamer_instance.safe_close(),
            #user_data_streamer_instance.safe_close()
        )
        raise
if __name__=='__main__':
    #logging
    configure_logging()

    exchange = "mexc"

    # topics
    market_data_topics= [{"method": "SUBSCRIPTION", "params": ["spot@public.kline.v3.api.pb@BTCUSDT@Min1", "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT", "spot@public.aggre.deals.v3.api.pb@100ms@BTCUSDT"]}]
    user_data_topics =  [{"method": "SUBSCRIPTION", "params": ["spot@private.account.v3.api.pb", "spot@private.deals.v3.api.pb", "spot@private.orders.v3.api.pb"]}]

    #encrypted secrets
    api_key = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f"{exchange.upper()}_API_KEY"])
    api_secret = SecurityManager(dotenv_values(Path(__file__).parent/".env")[f"{exchange.upper()}_SECRET"])


    #if type == market, quantity or quanteORderQty is mandatory: 
    #e.g BTCUSDT: BUY side: the order will buy as many BTC as quiteOrderQty USDT can.
    #.            Sell side: the order will see the quantity of BTC.
    #market order only for now:

    asyncio.run(main(exchange = exchange, market_data_topics=market_data_topics, user_data_topics = user_data_topics, api_key=api_key, api_secret=api_secret))
   