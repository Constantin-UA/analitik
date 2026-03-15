import io
import datetime
import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import pandas_ta as ta
import mplfinance as mpf
import yfinance as yf
import logging
from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)
class MarketMetrics:
    """
    DTO для строгой типизации и изоляции рыночных данных.
    Почему frozen=True: иммутабельность защищает от случайных мутаций состояния в других модулях.
    """
    symbol: str
    price: float
    atr_1d: float
    rsi_1d: float
    funding_rate: float
    df_1d: pd.DataFrame
    buy_pressure: float
    sell_pressure: float
    macd_hist: float
    guide_macd_hist: float
    guide_name: str
    ema50: float
    cur_vol: float
    avg_vol: float
    poc_price: float
    fibo_618: float
    is_valid: bool = True

    @property
    def daily_open(self) -> float:
        """Изоляция логики извлечения цены. Защита от IndexError при пустом DataFrame."""
        return float(self.df_1d['open'].iloc[-1]) if not self.df_1d.empty else 0.0

    @property
    def daily_high(self) -> float:
        return self.daily_open + self.atr_1d

    @property
    def daily_low(self) -> float:
        return self.daily_open - self.atr_1d
    
    @property
    def channel_range(self) -> float:
        return self.daily_high - self.daily_low

    @property
    def position_pct(self) -> float:
        """Определяет текущее положение цены в ATR-канале (в процентах)."""
        return ((self.price - self.daily_low) / self.channel_range * 100) if self.channel_range > 0 else 50.0

    def calculate_risk_params(self, risk_usd: float) -> Dict[str, Dict[str, float]]:
        """
        Инкапсулированная математика риск-менеджмента.
        Почему здесь: UI-слой (bot.py) не должен заниматься вычислениями объема сделок.
        """
        long_sl = self.daily_low * 0.998
        long_risk_per_coin = self.price - long_sl
        long_amount = risk_usd / long_risk_per_coin if long_risk_per_coin > 0 else 0.0

        short_sl = self.daily_high * 1.002
        short_risk_per_coin = short_sl - self.price
        short_amount = risk_usd / short_risk_per_coin if short_risk_per_coin > 0 else 0.0

        return {
            "long": {"sl": long_sl, "tp": self.daily_high, "amount": long_amount},
            "short": {"sl": short_sl, "tp": self.daily_low, "amount": short_amount}
        }

def fetch_spy_macd_sync() -> float:
    """Чому синхронно: yfinance не підтримує async з коробки, ізолюємо блокуючий виклик."""
    try:
        spy = yf.Ticker("SPY")
        df = spy.history(period="2mo", interval="1d")
        if df.empty:
            return 0.0
        macd = df.ta.macd()
        return float(macd.iloc[-1, 1])
    except Exception:
        # Чому exception: захоплення Traceback для виявлення проблем з мережею або зміною API Yahoo
        logging.exception("Збій завантаження даних SPY через yfinance")
        return 0.0

async def get_market_data(symbol: str = "ETH", period: int = 14) -> MarketMetrics:
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
        macd_hist = float(macd_indicator.iloc[-1, 1])

        if symbol == "BTC":
            guide_name = "S&P 500 (SPY)"
            guide_macd_hist = await asyncio.to_thread(fetch_spy_macd_sync)
        else:
            guide_name = "Биткоин (BTC)"
            ohlcv_guide_4h = await exchange.fetch_ohlcv("BTC/USDT", timeframe='4h', limit=50)
            df_guide = pd.DataFrame(ohlcv_guide_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            macd_guide = df_guide.ta.macd(append=True)
            guide_macd_hist = float(macd_guide.iloc[-1, 1])

        ohlcv_1d = await exchange.fetch_ohlcv(symbol_spot, timeframe='1d', limit=150)
        df_1d = pd.DataFrame(ohlcv_1d, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_1d['timestamp'] = pd.to_datetime(df_1d['timestamp'], unit='ms')
        df_1d['volume'] = pd.to_numeric(df_1d['volume'])
        df_1d.set_index('timestamp', inplace=True)
        
        df_1d.ta.atr(length=period, append=True)
        df_1d.ta.rsi(length=period, append=True)
        df_1d.ta.ema(length=50, append=True)
        
        daily_atr = float(df_1d[f'ATRr_{period}'].iloc[-1])
        daily_rsi = float(df_1d[f'RSI_{period}'].iloc[-1])
        daily_ema50 = float(df_1d['EMA_50'].iloc[-1])

        current_volume = float(df_1d['volume'].iloc[-1])
        avg_volume_10d = float(df_1d['volume'].rolling(10).mean().iloc[-1])

        recent_30d = df_1d.tail(30)
        recent_high = float(recent_30d['high'].max())
        recent_low = float(recent_30d['low'].min())
        
        fibo_618 = recent_high - (recent_high - recent_low) * 0.618
        
        bins = pd.cut(recent_30d['close'], bins=20)
        volume_by_price = recent_30d.groupby(bins, observed=False)['volume'].sum()
        poc_bin = volume_by_price.idxmax()
        poc_price = float(poc_bin.mid)

        await exchange.close()
        
        return MarketMetrics(
            symbol=symbol, price=current_price, atr_1d=daily_atr, rsi_1d=daily_rsi,
            funding_rate=funding_rate, df_1d=df_1d, buy_pressure=buy_pressure,
            sell_pressure=sell_pressure, macd_hist=macd_hist, guide_macd_hist=guide_macd_hist,
            guide_name=guide_name, ema50=daily_ema50, cur_vol=current_volume,
            avg_vol=avg_volume_10d, poc_price=poc_price, fibo_618=fibo_618
        )
    except Exception:
        await exchange.close()
        # Чому exception: вичерпне логування падіння обчислень pandas або таймаутів Bybit
        logging.exception(f"Критична помилка API Bybit або обробки DataFrame для {symbol}")
        return MarketMetrics(
            symbol=symbol, price=0, atr_1d=0, rsi_1d=0, funding_rate=0,
            df_1d=pd.DataFrame(), buy_pressure=0, sell_pressure=0, macd_hist=0,
            guide_macd_hist=0, guide_name="", ema50=0, cur_vol=0, avg_vol=0,
            poc_price=0, fibo_618=0, is_valid=False
        )

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