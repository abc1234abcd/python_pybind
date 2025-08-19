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

elif self.ob_cache.bids - self.filled_entry_price < -(self.filled_entry_price*0.0005):
                    self._sell_order["quantity"] = self.filled_qty
                    self._sell_order['timestamp'] = int(time.time()*1000)
                    try:
                        sell_order_response = self.api_client.submit_orders(self._sell_order) 
                        sell_order_id = sell_order_response['orderId']
                        sell_order_status =  self.api_client.order_status(orderId = sell_order_id)
                        if sell_order_status['status'] in ['FILLED', 'PARTIALLY_FILLED']:
                            filled_sell_qty = float(sell_order_status['executedQty'])
                            filled_sell_price = float(sell_order_status['cummulativeQuoteQty'])/filled_sell_qty
                            if filled_sell_qty == self.filled_qty:
                                print(f"stop loss order exec: loss: {filled_sell_price*self.filled_qty - 10.0}, entry: {self.filled_entry_price}, exit: {filled_sell_price}")
                        self.position = None
                        self.filled_entry_price = 0.0
                        self.filled_qty = 0.0
                    except Exception as e:
                        logging.error(f"stop loss order exec failed on exception: {e}.")

'''
