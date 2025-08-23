import logging
from pathlib import Path 
from datetime import datetime

def configure_logging():
    log_file_path = Path(__file__).parent/'logs'/f"bot_{datetime.now().strftime('%Y-%m-%d')}.log"
    logging.basicConfig(
        filename = str(log_file_path),
        format = "%(asctime)s %(levelname)-7s%(message)s",
        level = logging.INFO,
        datefmt="%Y-%m-%D %H:%M:%S"
    )
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(console_handler)



'''

 #kline slope 
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
                            print(f"{self.kline_cache.window_start}, slope: {self.kline_slope} rsi: {self.rsi_value}, asks: {self.ob_cache.asks}, bids:{self.ob_cache.bids},close: {self.kline_cache.closing_price},price_delta:{self.order_flow_cache.price_delta}, net flow: {self.order_flow_cache.normalized_net_flow}")
                        #order_flow

'''