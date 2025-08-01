import os
import logging
from datetime import datetime
from pathlib import Path
import logging
from queue import Queue
import asyncio
from dotenv import dotenv_values
from core.market_data_streamer import MarketDataStreamer
from core.user_data_streamer import create_user_data_streamer
from security import SecuirtyManager


async def main(market_data_topics, user_data_topics, api_key, api_secret):
    market_data_queue = Queue()
    user_data_queue = Queue()
    mexc_market_data_streamer = MarketDataStreamer(exchange = 'mexc', queue=market_data_queue, topics=market_data_topics)
    mexc_user_data_streamer = create_user_data_streamer(SecuirtyManager(secret=dotenv_values(".env")["MEXC_API_KEY"]).get_secret(), SecuirtyManager(secret=dotenv_values(".env")["MEXC_SECRET"]).get_secret())
    await asyncio.gather(
        mexc_market_data_streamer.connect(),
        mexc_user_data_streamer.connect(),
    )

if __name__=='__main__':
    #logging
    log_file_path = Path(__file__).parent/'logs'/f"bot_{datetime.now().strftime('%Y-%m-%d')}.log"
    logging.basicConfig(
        filename = str(log_file_path),
        format = "%(asctime)s %(levelname)-7s %(message)s",
        level = logging.INFO,
        datefmt = "%Y-%m-%d %H:%M:%S"
    )

    # generate topics to make subscriptions to all required live data stream.
    market_data_topics= [{"method": "SUBSCRIPTION", "params": ["spot@public.kline.v3.api.pb@BTCUSDT@Min1", "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT", "spot@public.aggre.deals.v3.api.pb@100ms@BTCUSDT"]}]
    user_data_topics =  [{"method": "SUBSCRIPTION", "params": ["spot@private.account.v3.api.pb", "spot@private.deals.v3.api.pb", "spot@private.orders.v3.api.pb"]}]


    #key protections
    
    x = SecuirtyManager(secret=dotenv_values(".env")["MEXC_API_KEY"]).get_secret()
    print(x)


    #asyncio.run(main(market_data_topics))
   

    
