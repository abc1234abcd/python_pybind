
'''
indicators:

order flow imbalance:

z-score: measures how far a data point is from the average(mean), in terms of standard deviation. 

e.g avg temperature is 20 degree, standard deviation is 5 degree. current temperature is 30, z-score = (30-20)/5 = 2. **this means** today is 2 standard deviation hotter than average.


to assess a line is moving upward or downward, slope (polyfit(x, y, 1)[0]) coefficiency is the best for a general perception of the direction; however, ***if the market is fast-moving, 
, where instance reaction to RSI changes is required as in HFT.***



st 1: 

setting: rsi_window = 7, short_period_price_mean = previous 7 trade price on average. my stop lose pct = 2 times of take profit pct = 0.2%

momentum is the rsi_delta = curr_rsi - prev_rsi. 

entry policy: rsi is upmoving, rsi < oversold threshold, last trade price > short moving average trading price.

identified problems with this entry policy: 

a. i miss strong upward trend as the rsi is too high, ris < oversold threshold is NOT going to met at all, then i am NOT able to enter market.
b. false signal. I will sell when my take profit pct is met, and then re-enter at a higher price, which has a large chance that it leads to trigger a stop loss tnx, as the rsi 


st2:
 
trade as how rsi line goes, use ris_slope to decide entry and exit. 

rsi < overbrough threshol, rsi_slope > 0 , rsi_slope_delta > 0 -> strong buy signal,

momentum > 0 + rsi_value < over_sold_threshold, 


'''

if (momentum > 1 and 
                self.rsi_value_buffer[-1] < 32 and 
                self.price_buffer[-1] > short_period_price_mean):
    "entry"

if target_exit_price - self.filled_entry_price > self.filled_entry_price*0.001 and momentum < 0:

    "exit"