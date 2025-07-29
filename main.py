import os
import logging
from datetime import datetime
from pathlib import Path
import logging
from queue import Queue
import asyncio
from core.market_data_streamer import MarketDataStreamer


async def main(market_data_topics):
    queue = Queue()
    mexc_market_data_streamer = MarketDataStreamer(exchange = 'mexc', queue=queue, topics=market_data_topics)
    await asyncio.gather(
        mexc_market_data_streamer.connect(),
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
    market_data_topics= [{"method": "SUBSCRIPTION", "params": ["spot@public.kline.v3.api.pb@BTCUSDT@Min1", "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"]}]
    user_data_topics =  [{"method": "SUBSCRIPTION", "params": ["spot@private.account.v3.api.pb", "spot@private.deals.v3.api.pb", "spot@private.orders.v3.api.pb"]}]
    asyncio.run(main(market_data_topics))
   

    
