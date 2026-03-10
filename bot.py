import asyncio
import datetime
from aiogram.exceptions import TelegramBadRequest
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Импорты из наших модулей
from config import BOT_TOKEN, ADMIN_ID, LOG_CHANNEL_ID, logging
from market import get_market_data, create_chart
from ai import fetch_eth_news, fetch_fear_and_greed, get_ai_forecast

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()
alert_state = {"last_alert_type": None}

class LogState(StatesGroup):
    waiting_for_note = State()

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📈 Analize"), KeyboardButton(text="🧠 AI Прогноз")],
        [KeyboardButton(text="📝 Log")]
    ], resize_keyboard=True
)

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("👋 Привет!", reply_markup=main_keyboard)

@dp.message(Command("eth"))
@dp.message(F.text == "📈 Analize")
async def eth_handler(message: types.Message):
    wait_msg = await message.answer("⏳ Собираю данные рынка...")
    data = await get_market_data()
    if data[0] is None:
        return await message.answer("❌ Ошибка получения данных.")

    price, atr_1d, atr_1w, rsi_1d, funding, df_1d, buy_pct, sell_pct, macd_hist, total_days, green_days, green_pct, btc_macd_hist = data
    daily_high, daily_low = price + atr_1d, price - atr_1d

    chart_buffer = create_chart(df_1d, price, daily_high, daily_low)
    photo = BufferedInputFile(chart_buffer.getvalue(), filename="chart.png")

    text = (
        f"📊 **Торговый радар ETH/USDT**\n\n"
        f"💰 **Цена:** `${price:,.2f}`\n"
        f"📈 **RSI (1D):** `{rsi_1d:.1f}`\n"
        f"🧱 **Стакан:** `{buy_pct:.0f}% / {sell_pct:.0f}%`\n"
        f"🧭 **Тренд 4H:** ETH `{'Вверх' if macd_hist > 0 else 'Вниз'}` | BTC `{'Вверх' if btc_macd_hist > 0 else 'Вниз'}`\n"
        f"🎯 **Коридор дня:** `🔽 {daily_low:,.0f} --- 🔼 {daily_high:,.0f}`"
    )
    await message.answer_photo(photo=photo, caption=text, parse_mode="Markdown")
    await wait_msg.delete()

@dp.message(F.text == "🧠 AI Прогноз")
async def ai_forecast_handler(message: types.Message):
    wait_msg = await message.answer("🧠 Запускаю ИИ...")
    data = await get_market_data()
    news = await fetch_eth_news()
    fng_index = await fetch_fear_and_greed()
    
    if data[0] is None:
        return await message.answer("❌ Ошибка данных.")

    price, atr_1d, _, rsi_1d, _, _, buy_pct, sell_pct, macd_hist, _, _, _, btc_macd_hist = data
    ai_text = await get_ai_forecast(price, price - atr_1d, price + atr_1d, rsi_1d, buy_pct, sell_pct, macd_hist, btc_macd_hist, fng_index, news)
    
    # --- ЛОВЦЫ ЛОВУШЕК (SAFEGUARDS) ---
    # 1. Защита от переполнения (разбиваем на куски по 4000 символов)
    max_len = 4000
    chunks = [ai_text[i:i+max_len] for i in range(0, len(ai_text), max_len)]

    for i, chunk in enumerate(chunks):
        text_to_send = f"🤖 **Анализ AI:**\n\n{chunk}" if i == 0 else chunk
        
        # 2. Защита от сломанного Markdown
        try:
            await message.answer(text_to_send, parse_mode="Markdown")
        except TelegramBadRequest as e:
            if "parse entities" in str(e).lower() or "markdown" in str(e).lower():
                logging.warning("⚠️ Ошибка Markdown, ИИ выдал неверные спецсимволы. Отправляю чистым текстом.")
                await message.answer(text_to_send) # Отправка без форматирования
            else:
                logging.error(f"❌ Неизвестная ошибка Telegram API: {e}")
                await message.answer("❌ Произошла системная ошибка при отправке сообщения.")

    await wait_msg.delete()
    
@dp.message(Command("log"))
@dp.message(F.text == "📝 Log")
async def start_log(message: types.Message, state: FSMContext):
    await state.set_state(LogState.waiting_for_note)
    await message.answer("✍️ Опишите мысль:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True))

@dp.message(F.text == "❌ Отмена", LogState.waiting_for_note)
async def cancel_log(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_keyboard)

@dp.message(LogState.waiting_for_note)
async def save_log(message: types.Message, state: FSMContext):
    user_note = message.text
    wait_msg = await message.answer("⏳ Сохраняю...")
    await state.clear()
    
    data = await get_market_data()
    price, atr_1d, _, rsi_1d, _, df_1d, buy_pct, sell_pct, macd_hist, _, _, _, btc_macd_hist = data
    chart_buffer = create_chart(df_1d, price, price + atr_1d, price - atr_1d, "log_chart.png")
    photo = BufferedInputFile(chart_buffer.getvalue(), filename="log_chart.png")

    log_text = (
        f"📖 **ДНЕВНИК СДЕЛКИ** | `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}`\n\n"
        f"📝 **Запись:**\n_{user_note}_\n\n"
        f"💰 Цена: `${price:,.2f}` | RSI: `{rsi_1d:.1f}`"
    )

    await bot.send_photo(chat_id=LOG_CHANNEL_ID, photo=photo, caption=log_text, parse_mode="Markdown")
    await message.answer("✅ В дневнике!", reply_markup=main_keyboard)
    await wait_msg.delete()

async def check_alerts():
    data = await get_market_data()
    if data[0] is None: return
    price, atr_1d, _, rsi_1d = data[0], data[1], data[2], data[3]
    daily_high, daily_low = price + atr_1d, price - atr_1d
    
    alert_message, current_alert_type = None, None

    if price >= daily_high: current_alert_type, alert_message = "RESISTANCE", f"🚨 ПРОБОЙ ВВЕРХ: {price:.2f}"
    elif price <= daily_low: current_alert_type, alert_message = "SUPPORT", f"🚨 ПРОБОЙ ВНИЗ: {price:.2f}"
    elif rsi_1d >= 75: current_alert_type, alert_message = "RSI_HIGH", f"⚠️ ПЕРЕКУПЛЕННОСТЬ: {rsi_1d:.1f}"
    elif rsi_1d <= 25: current_alert_type, alert_message = "RSI_LOW", f"⚠️ ПЕРЕПРОДАННОСТЬ: {rsi_1d:.1f}"
    else: alert_state["last_alert_type"] = None

    if alert_message and current_alert_type != alert_state["last_alert_type"]:
        await bot.send_message(chat_id=ADMIN_ID, text=alert_message)
        alert_state["last_alert_type"] = current_alert_type

async def main():
    scheduler.add_job(check_alerts, 'interval', minutes=15)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())