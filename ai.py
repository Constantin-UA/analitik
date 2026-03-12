import xml.etree.ElementTree as ET
import aiohttp
import logging
from config import ai_model

async def fetch_news(symbol: str = "ETH") -> str:
    tags = {"ETH": "ethereum", "BTC": "bitcoin"}
    tag = tags.get(symbol, "cryptocurrency")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://cointelegraph.com/rss/tag/{tag}', timeout=5) as response:
                xml_data = await response.text()
                root = ET.fromstring(xml_data)
                news = [f"- {item.find('title').text}" for item in root.findall('./channel/item')[:5]]
                return "\n".join(news)
    except Exception as e:
        logging.error(f"Ошибка парсинга новостей: {e}")
        return "Не вдалося отримати свіжі новини."

async def fetch_fear_and_greed() -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.alternative.me/fng/?limit=1', timeout=5) as response:
                data = await response.json()
                return f"{data['data'][0]['value']}/100 ({data['data'][0]['value_classification']})"
    except Exception as e:
        logging.error(f"Ошибка получения Fear & Greed: {e}")
        return "Невідомо"

async def get_ai_forecast(symbol, price, daily_low, daily_high, position_pct, rsi_1d, macd_hist, guide_macd_hist, guide_name, fng_index, news, funding_rate, ema50, cur_vol, avg_vol, poc_price, fibo_618):
    trend_50 = "ВИЩЕ (Глобальний бичачий тренд)" if price > ema50 else "НИЖЧЕ (Глобальний ведмежий тренд)"
    vol_status = "АНОМАЛЬНИЙ РІСТ" if cur_vol > avg_vol * 1.5 else ("ПАДАЮТЬ" if cur_vol < avg_vol * 0.8 else "В межах норми")

    prompt = f"""
    Ти — алгоритмічний ризик-менеджер та Chief AI Architect. Твоя спеціалізація — СВІНГ-ТРЕЙДИНГ (утримання 1-3 дні).
    Твоє завдання — провести детермінований аналіз ринкової ситуації та видати чіткий вердикт.

    ДАНІ РИНКУ (АКТИВ: {symbol}/USDT):
    - Поточна ціна: {price:.2f}
    - Глобальний тренд (vs EMA 50): Ціна {trend_50}
    - Денний коридор ATR: Підтримка {daily_low:.2f} | Опір {daily_high:.2f}
    - Позиція ціни в коридорі: {position_pct:.1f}% (0% = на підтримці, 100% = на опорі, 50% = рівно посередині)
    - Об'ємний кластер POC (Point of Control за 30 днів): {poc_price:.2f}
    - Рівень Фібоначчі 0.618 (за 30 днів): {fibo_618:.2f}
    - RSI (1D): {rsi_1d:.1f}
    - Локальний імпульс (MACD 4H): {'Бичачий (Вгору)' if macd_hist > 0 else 'Ведмежий (Вниз)'}
    - Ставка фінансування (Funding): {funding_rate * 100:.4f}%
    - Макро-поводир ({guide_name}): {'Зростає (Підтримка лонгів)' if guide_macd_hist > 0 else 'Падає (Тиск вниз)'}
    
    СВІЖІ НОВИНИ:
    {news}
    
    СУВОРИЙ АЛГОРИТМ МІРКУВАНЬ (Chain of Thought):
    1. [Аналіз Ризику]: Оціни Позицію ціни в коридорі ({position_pct:.1f}%). Якщо значення між 30% та 70%, ризик відкриття позиції максимальний (невигідне R/R).
    2. [Аналіз Ліквідності]: Зістав поточну ціну, межі ATR, POC та Фібоначчі 0.618. Якщо межа ATR знаходиться поруч із POC або Фібо — це надзвичайно сильний магніт/стіна.
    3. [Синтез трендів]: Чи немає конфлікту між локальним імпульсом, макро-поводирем та глобальним трендом?
    
    ФОРМАТ ВІДПОВІДІ:
    Напиши відповідь суворо за шаблоном нижче.
    
    **🔍 [Аналіз Ризику та Ліквідності]**: (2-3 речення)
    **⚖️ [Синтез факторів]**: (2-3 речення)
    **💡 Свінг-вердикт (1-3 дні)**: (Чіткий заклик: ЛОНГ від рівня X / ШОРТ від рівня Y / ПОЗА РИНКОМ (Чекати)).
    """
    try:
        response = await ai_model.generate_content_async(prompt, generation_config={"temperature": 0.1})
        return response.text
    except Exception as e:
        logging.error(f"Ошибка Gemini API: {e}")
        return "Нейромережа зараз недоступна."