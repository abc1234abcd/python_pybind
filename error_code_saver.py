    async def message_decoder_cplus(self):
        #pre-allocate avoid overhead
        msg_protobuf_holder = PushDataV3ApiWrapper()
        while self._is_active and self.ws:
            try:
                #binary protobuf
                msg = await self.ws.recv()                
                if isinstance(msg, bytes):
                    if msg_protobuf_holder.parse(msg):
                        if msg_protobuf_holder.has_kline():
                            kline = msg_protobuf_holder.kline()
                            kline_dict = {
                                "symbol": msg_protobuf_holder.symbol,
                                "timestamp": int(time.time()*1000),
                                "openingprice": kline.opening_price(),
                                "closingprice": kline.closing_price(),
                                "windowstart": kline.window_start(),
                                "windowend": kline.window_end(),
                            }
                            print(kline_dict)
                        elif msg_protobuf_holder.has_book_ticker():
                            book = msg_protobuf_holder.book_ticker()
                            book_ticker_dict = {
                                "symbol": msg_protobuf_holder.symbol,
                                "timestamp": int(time.time()*1000),
                                "bidprice": book.bid_price(),
                                "bidqty": book.bid_quantity(),
                                "askprice": book.ask_price(),
                                "askqty": book.ask_quantity()
                            }
                            print(book_ticker_dict)
                        elif msg_protobuf_holder.has_public_aggredeals():
                            trades = msg_protobuf_holder.trades()
                            for deal in trades.deals():
                                trade_dict ={
                                    "symbol": msg_protobuf_holder.symbol,
                                    "timestamp": int(time.time()*1000),
                                    "price": deal.price(),
                                    "quantity": deal.quantity(),
                                    "tradetype": deal.trade_type(),
                                    "tradetime": deal.time()
                                }
                                print(trade_dict)
                        else:
                            logging.error(f"{msg} parsed but no recognized data type")
                    else:
                        logging.error("Failed to parse protobuf message")
                else:
                    #pong and subscription confirmation msg etc.
                    logging.warning(f"Non-bytes message: {msg}")
            except Exception as e:
                logging.error(f"cplus message decoder fail on exception:{e}.")
                raise


if __name__=='__main__':
    api_key = SecurityManager(dotenv_values(Path(__file__).parent.parent/".env")["MEXC_API_KEY"])
    api_secret = SecurityManager(dotenv_values(Path(__file__).parent.parent/".env")["MEXC_SECRET"])
    mexc_api_client = MexcApiClient(api_key = api_key, api_secret=api_secret)
    sell_order = {
            "quantity": None,  
            "side": "BUY",
            "symbol": "SOLUSDT",
            "timestamp": None,  
            "type": "MARKET"
        }
    #resp = mexc_api_client.account_balance()
    orderId = 'C02__582526780620046337099'
    default_symbol = mexc_api_client.submit_orders(params = params)
    print(f"order status: {default_symbol}")