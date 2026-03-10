import xml.etree.ElementTree as ET
import aiohttp
import logging
from config import ai_model

async def fetch_eth_news():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://cointelegraph.com/rss/tag/ethereum', timeout=5) as response:
                xml_data = await response.text()
                root = ET.fromstring(xml_data)
                news = [f"- {item.find('title').text}" for item in root.findall('./channel/item')[:5]]
                return "\n".join(news)
    except Exception as e:
        logging.error(f"Ошибка парсинга новостей: {e}")
        return "Не удалось получить свежие новости."

async def fetch_fear_and_greed():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.alternative.me/fng/?limit=1', timeout=5) as response:
                data = await response.json()
                return f"{data['data'][0]['value']}/100 ({data['data'][0]['value_classification']})"
    except Exception as e:
        logging.error(f"Ошибка получения Fear & Greed: {e}")
        return "Неизвестно"

async def get_ai_forecast(price, daily_low, daily_high, rsi_1d, buy_pct, sell_pct, macd_hist, btc_macd_hist, fng_index, news):
    prompt = f"""
    Ты — строгий риск-менеджер. Твой клиент торгует ETH внутри дня (intraday) и держит сделки не более 1-3 дней. 
    Его приоритет — сохранение капитала.
    
    ДАННЫЕ РЫНКА:
    - Цена ETH: {price:.2f}
    - Коридор: Поддержка {daily_low:.2f}, Сопротивление {daily_high:.2f}
    - RSI (1D): {rsi_1d:.1f}
    - Давление стакана: Покупки {buy_pct:.0f}%, Продажи {sell_pct:.0f}%
    - Тренд ETH (MACD 4H): {'Вверх' if macd_hist > 0 else 'Вниз'}
    - Тренд BTC (Поводырь): {'Тянет рынок вверх' if btc_macd_hist > 0 else 'Давит вниз'}
    - Индекс страха и жадности: {fng_index}
    
    СВЕЖИЕ НОВОСТИ:
    {news}
    
    ИНСТРУКЦИЯ:
    1. Проанализируй данные. Учти настроение толпы.
    2. Если толпа в эйфории, а цена у сопротивления — запрещай лонги.
    3. Выдай краткий анализ (3-4 предложения).
    4. Закончи вердиктом в формате: "💡 Вердикт: [Твой четкий совет]".
    """
    try:
        response = await ai_model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        logging.error(f"Ошибка Gemini API: {e}")
        return "Нейросеть сейчас недоступна."