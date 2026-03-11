import asyncio
import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, ADMIN_ID, LOG_CHANNEL_ID, logging
from market import get_market_data, create_chart
from ai import fetch_news, fetch_fear_and_greed, get_ai_forecast

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()
alert_state = {} 

class LogState(StatesGroup):
    waiting_for_note = State()

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📈 Analize"), KeyboardButton(text="🧠 AI Прогноз")],
        [KeyboardButton(text="📝 Log")]
    ], resize_keyboard=True
)

def get_asset_keyboard(action_prefix):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="ETH", callback_data=f"{action_prefix}_ETH"),
            InlineKeyboardButton(text="BTC", callback_data=f"{action_prefix}_BTC")
        ]
    ])

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("👋 Привет! Выберите действие в меню.", reply_markup=main_keyboard)

@dp.message(F.text == "📈 Analize")
async def ask_analyze(message: types.Message):
    await message.answer("Выберите актив для технического анализа:", reply_markup=get_asset_keyboard("market"))

@dp.message(F.text == "🧠 AI Прогноз")
async def ask_ai(message: types.Message):
    await message.answer("Выберите актив для ИИ-прогноза:", reply_markup=get_asset_keyboard("ai"))

@dp.message(F.text == "📝 Log")
async def ask_log(message: types.Message):
    await message.answer("Для какого актива пишем лог?", reply_markup=get_asset_keyboard("log"))

@dp.callback_query(F.data.startswith("market_"))
async def market_handler(call: CallbackQuery):
    symbol = call.data.split("_")[1]
    await call.message.edit_text(f"⏳ Собираю данные по {symbol}...")
    
    data = await get_market_data(symbol)
    if data[0] is None:
        return await call.message.edit_text("❌ Ошибка получения данных.")

    price, atr_1d, atr_1w, rsi_1d, funding, df_1d, buy_pct, sell_pct, macd_hist, total_days, green_days, green_pct, guide_macd_hist, guide_name, ema50, cur_vol, avg_vol = data
    
    # --- СТАТИЧНЫЙ КОРИДОР ---
    daily_open = df_1d['open'].iloc[-1]
    daily_high = daily_open + atr_1d
    daily_low = daily_open - atr_1d
    # -------------------------

    chart_buffer = create_chart(df_1d, price, daily_high, daily_low, symbol)
    photo = BufferedInputFile(chart_buffer.getvalue(), filename="chart.png")

    trend_status = "🟢 Выше EMA50" if price > ema50 else "🔴 Ниже EMA50"
    vol_status = "🔥 Аномальные" if cur_vol > avg_vol * 1.5 else ("📉 Падают" if cur_vol < avg_vol * 0.8 else "📊 В норме")

    text = (
        f"📊 **Торговый радар {symbol}/USDT**\n\n"
        f"💰 **Цена:** `${price:,.2f}` ({trend_status})\n"
        f"⛽️ **Funding:** `{funding * 100:.4f}%`\n"
        f"📈 **RSI (1D):** `{rsi_1d:.1f}`\n"
        f"📦 **Объемы:** {vol_status}\n"
        f"🧱 **Стакан:** `{buy_pct:.0f}% / {sell_pct:.0f}%`\n"
        f"🧭 **Тренд 4H:** {symbol} `{'Вверх' if macd_hist > 0 else 'Вниз'}` | {guide_name} `{'Вверх' if guide_macd_hist > 0 else 'Вниз'}`\n"
        f"🎯 **Коридор дня:** `🔽 {daily_low:,.0f} --- 🔼 {daily_high:,.0f}`"
    )
    await call.message.delete()
    await call.message.answer_photo(photo=photo, caption=text, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("ai_"))
async def ai_forecast_handler(call: CallbackQuery):
    symbol = call.data.split("_")[1]
    await call.message.edit_text(f"🧠 Запускаю ИИ для {symbol}...")
    
    data = await get_market_data(symbol)
    news = await fetch_news(symbol)
    fng_index = await fetch_fear_and_greed()
    
    if data[0] is None:
        return await call.message.edit_text("❌ Ошибка данных.")

    price, atr_1d, _, rsi_1d, funding, df_1d, _, _, macd_hist, _, _, _, guide_macd_hist, guide_name, ema50, cur_vol, avg_vol = data
    
    # --- СТАТИЧНЫЙ КОРИДОР ---
    daily_open = df_1d['open'].iloc[-1]
    daily_high = daily_open + atr_1d
    daily_low = daily_open - atr_1d
    # -------------------------
    
    ai_text = await get_ai_forecast(
        symbol=symbol, price=price, daily_low=daily_low, daily_high=daily_high, 
        rsi_1d=rsi_1d, macd_hist=macd_hist, guide_macd_hist=guide_macd_hist, 
        guide_name=guide_name, fng_index=fng_index, news=news, 
        funding_rate=funding, ema50=ema50, cur_vol=cur_vol, avg_vol=avg_vol
    )
    
    max_len = 4000
    chunks = [ai_text[i:i+max_len] for i in range(0, len(ai_text), max_len)]

    await call.message.delete()
    for i, chunk in enumerate(chunks):
        text_to_send = f"🤖 **Анализ AI ({symbol}):**\n\n{chunk}" if i == 0 else chunk
        try:
            await call.message.answer(text_to_send, parse_mode="Markdown")
        except TelegramBadRequest as e:
            if "parse entities" in str(e).lower() or "markdown" in str(e).lower():
                logging.warning(f"Ошибка Markdown. Отправляю текст без форматирования.")
                await call.message.answer(text_to_send)
            else:
                logging.error(f"Неизвестная ошибка Telegram API: {e}")
                await call.message.answer("❌ Произошла системная ошибка при отправке.")

@dp.callback_query(F.data.startswith("log_"))
async def start_log_process(call: CallbackQuery, state: FSMContext):
    symbol = call.data.split("_")[1]
    await state.update_data(symbol=symbol) 
    await state.set_state(LogState.waiting_for_note)
    await call.message.delete()
    await call.message.answer(f"✍️ Опишите мысль по **{symbol}**:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True))

@dp.message(F.text == "❌ Отмена", LogState.waiting_for_note)
async def cancel_log(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_keyboard)

@dp.message(LogState.waiting_for_note)
async def save_log(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    symbol = user_data.get("symbol", "ETH")
    user_note = message.text
    
    wait_msg = await message.answer(f"⏳ Сохраняю лог по {symbol}...")
    await state.clear()
    
    data = await get_market_data(symbol)
    price, atr_1d, _, rsi_1d, _, df_1d, _, _, macd_hist, _, _, _, _, _, _, _, _ = data
    
    # --- СТАТИЧНЫЙ КОРИДОР ---
    daily_open = df_1d['open'].iloc[-1]
    daily_high = daily_open + atr_1d
    daily_low = daily_open - atr_1d
    # -------------------------
    
    chart_buffer = create_chart(df_1d, price, daily_high, daily_low, symbol, "log_chart.png")
    photo = BufferedInputFile(chart_buffer.getvalue(), filename="log_chart.png")

    log_text = (
        f"📖 **ДНЕВНИК СДЕЛКИ ({symbol})** | `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}`\n\n"
        f"📝 **Запись:**\n_{user_note}_\n\n"
        f"💰 Цена: `${price:,.2f}` | RSI: `{rsi_1d:.1f}`"
    )

    await bot.send_photo(chat_id=LOG_CHANNEL_ID, photo=photo, caption=log_text, parse_mode="Markdown")
    await message.answer("✅ В дневнике!", reply_markup=main_keyboard)
    await wait_msg.delete()

async def check_alerts():
    for symbol in ["ETH", "BTC"]:
        data = await get_market_data(symbol)
        if data[0] is None: continue
        
        price, atr_1d, rsi_1d, df_1d = data[0], data[1], data[3], data[5]
        
        # --- СТАТИЧНЫЙ КОРИДОР ДЛЯ АЛЕРТОВ ---
        daily_open = df_1d['open'].iloc[-1]
        daily_high = daily_open + atr_1d
        daily_low = daily_open - atr_1d
        # ------------------------------------
        
        alert_message, current_alert_type = None, None

        if price >= daily_high: current_alert_type, alert_message = "RESISTANCE", f"🚨 ПРОБОЙ ВВЕРХ ({symbol}): {price:.2f}"
        elif price <= daily_low: current_alert_type, alert_message = "SUPPORT", f"🚨 ПРОБОЙ ВНИЗ ({symbol}): {price:.2f}"
        elif rsi_1d >= 75: current_alert_type, alert_message = "RSI_HIGH", f"⚠️ ПЕРЕКУПЛЕННОСТЬ ({symbol}): {rsi_1d:.1f}"
        elif rsi_1d <= 25: current_alert_type, alert_message = "RSI_LOW", f"⚠️ ПЕРЕПРОДАННОСТЬ ({symbol}): {rsi_1d:.1f}"
        else: alert_state[f"last_{symbol}"] = None

        if alert_message and current_alert_type != alert_state.get(f"last_{symbol}"):
            await bot.send_message(chat_id=ADMIN_ID, text=alert_message)
            alert_state[f"last_{symbol}"] = current_alert_type

async def main():
    scheduler.add_job(check_alerts, 'interval', minutes=15)
    scheduler.start()
    
    # Сбрасываем все накопившиеся запросы, если бот был оффлайн
    await bot.delete_webhook(drop_pending_updates=True) 
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())