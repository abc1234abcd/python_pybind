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
elif curr_pnl < -self.avg_true_range*2:
                    self._sell_order["quantity"] = str(self.filled_qty)
                    self._sell_order['timestamp'] = str(int(time.time() * 1000))
                    try:
                        sell_order_response =  self.api_client.submit_orders(params = self._sell_order) 
                        sell_order_id = sell_order_response.get('orderId')
                        sell_order_status =  self.api_client.order_status(orderId = sell_order_id)
                        if sell_order_status.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                            filled_sell_qty = float(sell_order_status['executedQty'])
                            filled_sell_price = float(sell_order_status['cummulativeQuoteQty'])/filled_sell_qty
                            print(f"sell order filled: exit price:{filled_sell_price}")
                            if filled_sell_qty == self.filled_qty:
                                print(f"stop loss triggered, loss: {filled_sell_price*self.filled_qty - self.filled_qty*self.filled_entry_price}, entry: {self.filled_entry_price},  exit: {filled_sell_price}")
                                self.prev_exit_price = filled_sell_price
                                await self._reset_position()
                    except Exception as e:
                        logging.error(f"stop loss order failed on exception: {e}.")

'''