import io
import datetime
import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import pandas_ta as ta
import mplfinance as mpf
import yfinance as yf
import logging

def fetch_spy_macd_sync():
    """Синхронная функция для загрузки S&P 500 (SPY) через Yahoo Finance"""
    try:
        df = yf.download("SPY", period="2mo", interval="1d", progress=False)
        macd = df.ta.macd()
        return macd.iloc[-1, 1] # Гистограмма MACD
    except Exception as e:
        logging.error(f"yfinance error: {e}")
        return 0

async def get_market_data(symbol="ETH", period=14):
    symbol_spot = f"{symbol}/USDT"
    symbol_perp = f"{symbol}/USDT:USDT"

    exchange = ccxt.bybit({'enableRateLimit': True})
    try:
        ticker = await exchange.fetch_ticker(symbol_spot)
        current_price = ticker['last']
        funding_data = await exchange.fetch_funding_rate(symbol_perp)
        funding_rate = funding_data['fundingRate']

        order_book = await exchange.fetch_order_book(symbol_spot, limit=50)
        bids_volume = sum([bid[1] for bid in order_book['bids']])
        asks_volume = sum([ask[1] for ask in order_book['asks']])
        total_volume = bids_volume + asks_volume
        buy_pressure = (bids_volume / total_volume) * 100 if total_volume > 0 else 50
        sell_pressure = (asks_volume / total_volume) * 100 if total_volume > 0 else 50

        ohlcv_4h = await exchange.fetch_ohlcv(symbol_spot, timeframe='4h', limit=50)
        df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        macd_indicator = df_4h.ta.macd(append=True)
        macd_hist = macd_indicator.iloc[-1, 1]

        # --- НОВАЯ ЛОГИКА ПОВОДЫРЯ ---
        if symbol == "BTC":
            guide_name = "S&P 500 (SPY)"
            # Вызываем синхронный yfinance в отдельном потоке, чтобы не блокировать бота
            guide_macd_hist = await asyncio.to_thread(fetch_spy_macd_sync)
        else:
            guide_name = "Биткоин (BTC)"
            ohlcv_guide_4h = await exchange.fetch_ohlcv("BTC/USDT", timeframe='4h', limit=50)
            df_guide = pd.DataFrame(ohlcv_guide_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            macd_guide = df_guide.ta.macd(append=True)
            guide_macd_hist = macd_guide.iloc[-1, 1]
        # -----------------------------

        ohlcv_1d = await exchange.fetch_ohlcv(symbol_spot, timeframe='1d', limit=60)
        df_1d = pd.DataFrame(ohlcv_1d, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_1d['timestamp'] = pd.to_datetime(df_1d['timestamp'], unit='ms')
        df_1d['volume'] = pd.to_numeric(df_1d['volume'])
        df_1d.set_index('timestamp', inplace=True)
        
        df_1d.ta.atr(length=period, append=True)
        df_1d.ta.rsi(length=period, append=True)
        
        daily_atr = df_1d[f'ATRr_{period}'].iloc[-1]
        daily_rsi = df_1d[f'RSI_{period}'].iloc[-1]

        current_date_utc = datetime.datetime.now(datetime.timezone.utc)
        current_month, current_year = current_date_utc.month, current_date_utc.year
        this_month_df = df_1d[(df_1d.index.month == current_month) & (df_1d.index.year == current_year)]
        
        if not this_month_df.empty:
            total_days_in_month = len(this_month_df)
            green_days = (this_month_df['close'] > this_month_df['open']).sum()
            green_days_pct = (green_days / total_days_in_month) * 100
        else:
            total_days_in_month, green_days, green_days_pct = 0, 0, 0

        ohlcv_1w = await exchange.fetch_ohlcv(symbol_spot, timeframe='1w', limit=30)
        df_1w = pd.DataFrame(ohlcv_1w, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_1w.ta.atr(length=period, append=True)
        weekly_atr = df_1w[f'ATRr_{period}'].iloc[-1]

        await exchange.close()
        return (current_price, daily_atr, weekly_atr, daily_rsi, funding_rate, df_1d, 
                buy_pressure, sell_pressure, macd_hist, total_days_in_month, green_days, green_days_pct, guide_macd_hist, guide_name)
    except Exception as e:
        await exchange.close()
        logging.error(f"Ошибка API: {e}")
        return (None,) * 14

def create_chart(df, current_price, daily_high, daily_low, symbol="ETH", filename="chart.png"):
    df_plot = df.tail(45)
    buf = io.BytesIO()
    mpf.plot(
        df_plot, type='candle', style='charles', 
        hlines=dict(hlines=[daily_high, daily_low, current_price], colors=['r', 'g', 'b'], linestyle='--', alpha=0.6),
        title=f'\n{symbol}/USDT Daily (Bybit)', ylabel='Price', volume=True, ylabel_lower='Volume',
        savefig=dict(fname=buf, dpi=120, bbox_inches='tight', format='png')
    )
    buf.seek(0)
    return buf