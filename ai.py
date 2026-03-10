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

async def get_ai_forecast(symbol, price, daily_low, daily_high, rsi_1d, buy_pct, sell_pct, macd_hist, guide_macd_hist, guide_name, fng_index, news):
    prompt = f"""
    Твоя задача — провести системный анализ вероятностей для {symbol}/USDT. Ты — строгий риск-менеджер. Твой клиент торгует внутри дня (intraday) и держит сделки не более 1-3 дней. Приоритет — сохранение капитала.
    
    ДАННЫЕ РЫНКА:
    - Цена {symbol}: {price:.2f}
    - Дневной ATR коридор: Поддержка {daily_low:.2f}, Сопротивление {daily_high:.2f}
    - RSI (1D): {rsi_1d:.1f}
    - Давление стакана (50 уровней): Покупки {buy_pct:.0f}%, Продажи {sell_pct:.0f}%
    - Локальный тренд {symbol} (MACD 4H): {'Восходящий (Бычий)' if macd_hist > 0 else 'Нисходящий (Медвежий)'}
    - Вектор {guide_name} (Поводырь 4H): {'Растет' if guide_macd_hist > 0 else 'Падает'}
    - Индекс страха и жадности рынка: {fng_index}
    
    СВЕЖИЕ НОВОСТИ ({symbol}):
    {news}
    
    ИНСТРУКЦИЯ (Chain of Thought):
    Проанализируй данные шаг за шагом, рассуждая вслух (очень кратко и емко):
    1. Техническая структура: Оцени запас хода цены до границ коридора и перегретость.
    2. Анализ ликвидности: Кто контролирует стакан? Есть ли аномалии?
    3. Межрыночный анализ: Подтверждает ли вектор {guide_name} локальный тренд {symbol}, или есть раскорреляция?
    4. Мета-анализ фона: Сопоставь новости и Индекс страха. Оправдан ли текущий тренд?
    
    СИНТЕЗ И ВЕРДИКТ (Выведи в конце строгим списком):
    - 🎯 Основной сценарий: [что вероятнее всего произойдет]
    - 💡 Вердикт для сделки: [четкий совет: лонг, шорт или сидеть на заборе]
    - 🛑 Отмена сценария: [при каких условиях этот прогноз станет недействительным - укажи уровень]
    """
    try:
        response = await ai_model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        logging.error(f"Ошибка Gemini API: {e}")
        return "Нейросеть сейчас недоступна."