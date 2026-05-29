first of all there is the markov chains, now the markov chains update each tick so it's essentially just recording the past 100 ticks and seeing how that went, if we continue to go up
then it would record that as UP-UP-UP-UP and it counts the amount of times we went up vs the amount of time we went down and the strength of the direction based off how long the
chains were(that shows momentum in a direction for price)


after that, we wait on the monte carlo simulation. now this one is different it simulates 500 paths of what could happen next based off the chains, 
if we had UP-UP-UP-DOWN and it ends in UP, vs UP UP DOWN UP DOWN DOWN DOWN ends in DOWN, it runs the 500 paths based off of the markov chains and gives us the statistics on what it would usually end up being
it returns a result like (UP 83% DOWN 17%) or something like that

after that we use the tick data from binance to also check on some ICT/SMC concepts such as liquidity sweep, FVG, and BOS to determine what that says


we formulate a trade idea if 2 of 3 checks say YES (markov chains, monte carlo, and SMC concepts checks) and send the trade idea to Claude for validation

claude check out polymarket, checks the odds and then either says yes this is a good trade or NO, this is not a good trade

if yes, we enter, if no, we sit out

each trade window opens up on polymarket every 15 minutes, giving us 96 trade windows and opportunities a day, however majority of them will NOT be fired off on.

ONLY the trade ideas with high conviction get acted on, you can check out [https://polymarket.com/profile/0xce25e214d5cfe4f459cf67f08df581885aae7fdc?via=cvxv666](url) to see how he does it across multiple
different cryptocurrencies.

the trade PnL works like this, you buy however many shares at a certain price(price per share depends on the odds on polymarket) this is pulled from our program to ensure we are testing this process as accurately 
as possible. when you win, each share is worth 1$ and you sell it back to claim your profit. 

