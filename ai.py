import xml.etree.ElementTree as ET
import aiohttp
import logging
from config import ai_model

async def fetch_news(symbol="ETH"):
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

async def get_ai_forecast(symbol, price, daily_low, daily_high, rsi_1d, macd_hist, guide_macd_hist, guide_name, fng_index, news, funding_rate, ema50, cur_vol, avg_vol):
    trend_50 = "ВЫШЕ (Глобальный бычий тренд)" if price > ema50 else "НИЖЕ (Глобальный медвежий тренд)"
    vol_status = "АНОМАЛЬНЫЙ РОСТ" if cur_vol > avg_vol * 1.5 else ("ПАДАЮТ" if cur_vol < avg_vol * 0.8 else "В пределах нормы")

    prompt = f"""
    Ты — прагматичный криптоаналитик и строгий риск-менеджер. Твоя специализация — СВИНГ-ТРЕЙДИНГ (удержание позиции 1-3 дня).
    Микро-колебания и внутридневной шум стакана тебя не интересуют. Твоя цель — поймать уверенное движение от одной границы дневного коридора до другой, жестко контролируя риски.

    ДАННЫЕ РЫНКА (АКТИВ: {symbol}/USDT):
    - Текущая цена: {price:.2f}
    - Коридор (ATR): Поддержка {daily_low:.2f}, Сопротивление {daily_high:.2f}
    - Глобальный тренд (Цена vs EMA 50): Цена {trend_50}
    - RSI (1D): {rsi_1d:.1f}
    - Среднесрочный импульс (MACD 4H): {'Вверх' if macd_hist > 0 else 'Вниз'}
    - Объемы торгов: {vol_status}
    - Ставка финансирования (Funding): {funding_rate * 100:.4f}%
    - Вектор макро-поводыря ({guide_name}): {'Тянет рынок вверх' if guide_macd_hist > 0 else 'Давит вниз'}
    - Индекс страха и жадности: {fng_index}
    
    СВЕЖИЕ НОВОСТИ:
    {news}
    
    ИНСТРУКЦИЯ (Chain of Thought):
    1. Оцени сетап ИСКЛЮЧИТЕЛЬНО для удержания сделки на 1-3 дня. 
    2. Правило глобального тренда: Если цена ниже EMA 50, агрессивные лонги запрещены (можно шортить от сопротивления).
    3. Правило риска: Если цена находится в середине коридора ATR — рекомендуй ждать. Свинг-трейдер не заходит в центре.
    4. Оцени фандинг: если ставка > 0.015%, предупреди о риске лонг-сквиза (толпа перегрета в лонгах).
    5. Сделай сухой вывод из 3-4 предложений.
    6. Закончи текст вердиктом: "💡 Свинг-вердикт (1-3 дня): [Четкий план действий]".
    """
    try:
        response = await ai_model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        logging.error(f"Ошибка Gemini API: {e}")
        return "Нейросеть сейчас недоступна."