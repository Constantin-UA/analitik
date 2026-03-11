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

async def get_ai_forecast(symbol, price, daily_low, daily_high, position_pct, rsi_1d, macd_hist, guide_macd_hist, guide_name, fng_index, news, funding_rate, ema50, cur_vol, avg_vol):
    trend_50 = "ВЫШЕ (Глобальный бычий тренд)" if price > ema50 else "НИЖЕ (Глобальный медвежий тренд)"
    vol_status = "АНОМАЛЬНЫЙ РОСТ" if cur_vol > avg_vol * 1.5 else ("ПАДАЮТ" if cur_vol < avg_vol * 0.8 else "В пределах нормы")

    prompt = f"""
    Ты — алгоритмический риск-менеджер и Chief AI Architect. Твоя специализация — СВИНГ-ТРЕЙДИНГ (удержание 1-3 дня).
    Твоя задача — провести детерминированный анализ рыночной ситуации и выдать четкий вердикт.

    ДАННЫЕ РЫНКА (АКТИВ: {symbol}/USDT):
    - Текущая цена: {price:.2f}
    - Глобальный тренд (vs EMA 50): Цена {trend_50}
    - Дневной коридор ATR: Поддержка {daily_low:.2f} | Сопротивление {daily_high:.2f}
    - Позиция цены в коридоре: {position_pct:.1f}% (0% = на поддержке, 100% = на сопротивлении, 50% = ровно посередине)
    - RSI (1D): {rsi_1d:.1f}
    - Локальный импульс (MACD 4H): {'Бычий (Вверх)' if macd_hist > 0 else 'Медвежий (Вниз)'}
    - Объемы торгов (относительно 10 дней): {vol_status}
    - Ставка финансирования (Funding): {funding_rate * 100:.4f}%
    - Макро-поводырь ({guide_name}): {'Растет (Поддержка лонгов)' if guide_macd_hist > 0 else 'Падает (Давление вниз)'}
    - Индекс страха и жадности: {fng_index}
    
    СВЕЖИЕ НОВОСТИ:
    {news}
    
    СТРОГИЙ АЛГОРИТМ РАССУЖДЕНИЙ (Chain of Thought):
    1. [Анализ Риска]: Оцени Позицию цены в коридоре ({position_pct:.1f}%). Если значение между 30% и 70%, риск открытия позиции максимальный (невыгодное R/R).
    2. [Анализ Ликвидности и Толпы]: Оцени Funding и RSI. Есть ли перегрев толпы? Угрожает ли лонг/шорт сквиз?
    3. [Синтез трендов]: Сопоставь Глобальный тренд, Макро-поводыря и Локальный импульс. Нет ли между ними конфликта?
    
    ФОРМАТ ОТВЕТА:
    Напиши ответ строго по шаблону ниже. Не придумывай лишних вводных слов.
    
    **🔍 [Анализ Риска]**: (1-2 предложения)
    **⚖️ [Синтез факторов]**: (2-3 предложения)
    **💡 Свинг-вердикт (1-3 дня)**: (Четкий призыв: ЛОНГ от уровня X / ШОРТ от уровня Y / ВНЕ РЫНКА (Ждать)).
    """
    try:
        # Снижаем температуру для системной предсказуемости
        response = await ai_model.generate_content_async(
            prompt,
            generation_config={"temperature": 0.1}
        )
        return response.text
    except Exception as e:
        logging.error(f"Ошибка Gemini API: {e}")
        return "Нейросеть сейчас недоступна."