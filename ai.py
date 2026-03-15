import xml.etree.ElementTree as ET
import aiohttp
import logging
from typing import Dict
from config import ai_model
from market import MarketMetrics

async def fetch_news(symbol: str = "ETH") -> str:
    tags = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "BNB": "binance-coin",
        "XRP": "ripple",
        "ADA": "cardano"
    } 
    tag = tags.get(symbol, "cryptocurrency")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://cointelegraph.com/rss/tag/{tag}', timeout=5) as response:
                xml_data = await response.text()
                root = ET.fromstring(xml_data)
                news = [f"- {item.find('title').text}" for item in root.findall('./channel/item')[:5]]
                return "\n".join(news)
    except Exception:
        # Захоплюємо стек викликів, якщо RSS-фід недоступний або змінив структуру
        logging.exception(f"Збій парсингу RSS Cointelegraph для {symbol}")
        return "Не вдалося отримати свіжі новини."

async def fetch_fear_and_greed() -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.alternative.me/fng/?limit=1', timeout=5) as response:
                data = await response.json()
                return f"{data['data'][0]['value']}/100 ({data['data'][0]['value_classification']})"
    except Exception:
        # Логуємо таймаути або помилки JSON при зміні API
        logging.exception("Помилка отримання індексу Fear & Greed з alternative.me")
        return "Невідомо"

async def get_ai_forecast(metrics: MarketMetrics, risks: Dict[str, Dict[str, float]], fng_index: str, news: str, risk_usd: float) -> str:
    trend_50 = "ВИЩЕ (Бичачий)" if metrics.price > metrics.ema50 else "НИЖЧЕ (Ведмежий)"
    
    # Визначаємо аномалії об'єму для ШІ
    vol_anomaly = "АНОМАЛЬНИЙ СПЛЕСК" if metrics.cur_vol > (metrics.avg_vol * 1.5) else "В межах норми"
    
    # Розрахунок R:R (Risk/Reward) для лонга і шорта. Захист від ділення на нуль.
    long_risk = metrics.price - risks['long']['sl']
    long_rr = (risks['long']['tp'] - metrics.price) / long_risk if long_risk > 0 else 0
    
    short_risk = risks['short']['sl'] - metrics.price
    short_rr = (metrics.price - risks['short']['tp']) / short_risk if short_risk > 0 else 0

    prompt = f"""
    Ти — Senior AI-Квант та Ризик-менеджер інвестиційного фонду. Твій горизонт — СВІНГ-ТРЕЙДИНГ (1-3 дні).
    Твоє завдання — синтезувати технічні дані, сантимент натовпу та новинний фон, щоб ухвалити жорстке рішення про вхід у ринок.

    [1. СТРУКТУРА РИНКУ: {metrics.symbol}/USDT]
    - Ціна: {metrics.price:.2f}
    - EMA 50 (Глобальний тренд): {trend_50}
    - Позиція в ATR-каналі (0% підтримка, 100% опір): {metrics.position_pct:.1f}%
    - POC (Point of Control 30d): {metrics.poc_price:.2f}
    - Fibo 0.618: {metrics.fibo_618:.2f}
    - Локальний імпульс (MACD 4H): {'Вгору' if metrics.macd_hist > 0 else 'Вниз'}
    - Об'ємний фактор: {vol_anomaly}
    
    [2. САНТИМЕНТ ТА ФУНДАМЕНТАЛ]
    - Індекс Страху та Жадібності (FNG): {fng_index}
    - Funding Rate (Стан натовпу): {metrics.funding_rate * 100:.4f}% (Високий плюс = ризик корекції вниз)
    - Останні новини:
    {news}

    [3. МАТЕМАТИКА ПОЗИЦІЇ (Ризик ${risk_usd:.2f})]
    - Сценарій LONG: Вхід {metrics.price:.2f} | Stop-Loss {risks['long']['sl']:.2f} | Take-Profit {risks['long']['tp']:.2f} | Risk/Reward = 1:{long_rr:.2f}
    - Сценарій SHORT: Вхід {metrics.price:.2f} | Stop-Loss {risks['short']['sl']:.2f} | Take-Profit {risks['short']['tp']:.2f} | Risk/Reward = 1:{short_rr:.2f}
    
    СУВОРИЙ АЛГОРИТМ УХВАЛЕННЯ РІШЕННЯ:
    1. Перевір Risk/Reward. Якщо для обраного напрямку він менший ніж 1:1.5 — суворо відхиляй угоду (ПОЗА РИНКОМ).
    2. Якщо новини відверто суперечать технічному тренду (наприклад, злам біржі при висхідному MACD) — угода скасовується.
    3. Зістав позицію в ATR з Funding Rate. Якщо всі "в лонгах" (високий фандінг) і ми біля опору — шукай шорт або ігноруй.

    ФОРМАТ ВІДПОВІДІ (Жодної води, тільки суть):
    **🧠 [Синтез Сантименту та Новин]**: (1-2 речення: як новини і FNG впливають на технічну картину)
    **⚖️ [Оцінка R:R та Ліквідності]**: (1 речення)
    **💡 Свінг-вердикт**: (ЛОНГ / ШОРТ / ПОЗА РИНКОМ)
    
    **🎯 Торговий План**:
    (Якщо ПОЗА РИНКОМ — поясни причину: поганий R:R, погані новини, або середина каналу).
    (Якщо ЛОНГ або ШОРТ — виведи дані):
    - 🛡 Вхід: {metrics.price:.2f}
    - ⚖️ Об'єм: [Відповідний об'єм] {metrics.symbol}
    - 🛑 Stop-Loss: [Відповідний SL]
    - 🏁 Take-Profit: [Відповідний TP]
    """
    try:
        response = await ai_model.generate_content_async(prompt, generation_config={"temperature": 0.1})
        return response.text
    except Exception:
        logging.exception(f"Помилка генерації прогнозу Gemini API для {metrics.symbol}")
        return "Нейромережа зараз недоступна."