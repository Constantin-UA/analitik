import asyncio
import datetime
import json
import logging
import aiofiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, ADMIN_ID, LOG_CHANNEL_ID, TRADE_DEPOSIT, TRADE_RISK_PCT, SWING_WATCHLIST
from market import get_market_data, create_chart
from ai import fetch_news, fetch_fear_and_greed, get_ai_forecast

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

STATE_FILE = "alert_state.json"
alert_state: dict = {}

async def init_state() -> None:
    """
    Асинхронная гидратация состояния при запуске бота.
    Почему асинхронно: предотвращает блокировку Event Loop на старте, 
    соблюдая чистоту жизненного цикла asyncio.
    """
    global alert_state
    try:
        async with aiofiles.open(STATE_FILE, "r") as f:
            content = await f.read()
            alert_state = json.loads(content)
    except FileNotFoundError:
        alert_state = {}

async def save_state(state: dict) -> None:
    """
    Неблокирующая запись на диск.
    Делегирует I/O операции пулу потоков ОС, сохраняя отзывчивость Telegram-бота 
    даже во время массовой записи алертов.
    """
    async with aiofiles.open(STATE_FILE, "w") as f:
        await f.write(json.dumps(state))

class LogState(StatesGroup):
    waiting_for_note = State()

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📈 Analize"), KeyboardButton(text="🧠 AI Прогноз")],
        [KeyboardButton(text="📝 Log")]
    ], resize_keyboard=True
)

def get_asset_keyboard(action_prefix: str) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(text=coin, callback_data=f"{action_prefix}_{coin}") for coin in SWING_WATCHLIST]
    keyboard = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("👋 Привіт! Оберіть дію в меню.", reply_markup=main_keyboard)

@dp.message(F.text == "📈 Analize")
async def ask_analyze(message: types.Message):
    await message.answer("Оберіть актив для технічного аналізу:", reply_markup=get_asset_keyboard("market"))

@dp.message(F.text == "🧠 AI Прогноз")
async def ask_ai(message: types.Message):
    await message.answer("Оберіть актив для ШІ-прогнозу:", reply_markup=get_asset_keyboard("ai"))

@dp.message(F.text == "📝 Log")
async def ask_log(message: types.Message):
    await message.answer("Для якого активу пишемо лог?", reply_markup=get_asset_keyboard("log"))

@dp.callback_query(F.data.startswith("market_"))
async def market_handler(call: CallbackQuery):
    await call.answer()
    symbol = call.data.split("_")[1]
    await call.message.edit_text(f"⏳ Збираю дані по {symbol}...")
    
    metrics = await get_market_data(symbol)
    if not metrics.is_valid:
        return await call.message.edit_text("❌ Помилка отримання даних.")

    chart_buffer = create_chart(metrics.df_1d, metrics.price, metrics.daily_high, metrics.daily_low, symbol)
    photo = BufferedInputFile(chart_buffer.getvalue(), filename="chart.png")

    trend_status = "🟢 Вище EMA50" if metrics.price > metrics.ema50 else "🔴 Нижче EMA50"
    
    text = (
        f"📊 **Торговий радар {symbol}/USDT**\n\n"
        f"💰 **Ціна:** `${metrics.price:,.2f}` ({trend_status})\n"
        f"🎯 **Коридор дня:** `🔽 {metrics.daily_low:,.0f} --- 🔼 {metrics.daily_high:,.0f}`\n\n"
        f"🧲 **POC (Об'єм 30d):** `{metrics.poc_price:,.0f}`\n"
        f"📐 **Fibo 0.618:** `{metrics.fibo_618:,.0f}`\n"
        f"📈 **RSI (1D):** `{metrics.rsi_1d:.1f}`\n"
        f"⛽️ **Funding:** `{metrics.funding_rate * 100:.4f}%`\n"
        f"🧭 **Тренд 4H:** {symbol} `{'Вгору' if metrics.macd_hist > 0 else 'Вниз'}` | {metrics.guide_name} `{'Вгору' if metrics.guide_macd_hist > 0 else 'Вниз'}`"
    )
    await call.message.delete()
    await call.message.answer_photo(photo=photo, caption=text, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("ai_"))
async def ai_forecast_handler(call: CallbackQuery):
    await call.answer()
    symbol = call.data.split("_")[1]
    await call.message.edit_text(f"🧠 Запускаю ШІ для {symbol}...")
    
    metrics = await get_market_data(symbol)
    if not metrics.is_valid:
        return await call.message.edit_text("❌ Помилка даних.")

    news = await fetch_news(symbol)
    fng_index = await fetch_fear_and_greed()
    
    risk_usd = TRADE_DEPOSIT * (TRADE_RISK_PCT / 100)
    risks = metrics.calculate_risk_params(risk_usd)
    
    ai_text = await get_ai_forecast(metrics, risks, fng_index, news, risk_usd)
    
    await call.message.delete()
    await call.message.answer(f"🤖 **Аналіз AI ({symbol}):**\n\n{ai_text}", parse_mode="Markdown")

@dp.callback_query(F.data.startswith("log_"))
async def start_log_process(call: CallbackQuery, state: FSMContext):
    await call.answer()
    symbol = call.data.split("_")[1]
    await state.update_data(symbol=symbol) 
    await state.set_state(LogState.waiting_for_note)
    await call.message.delete()
    await call.message.answer(f"✍️ Опишіть думку по **{symbol}**:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Скасувати")]], resize_keyboard=True))

@dp.message(F.text == "❌ Скасувати", LogState.waiting_for_note)
async def cancel_log(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Скасовано.", reply_markup=main_keyboard)

@dp.message(LogState.waiting_for_note)
async def save_log(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    symbol = user_data.get("symbol", "ETH")
    user_note = message.text
    
    wait_msg = await message.answer(f"⏳ Зберігаю лог по {symbol}...")
    await state.clear()
    
    metrics = await get_market_data(symbol)
    if not metrics.is_valid:
        return await message.answer("❌ Помилка збору даних для логу.")
    
    chart_buffer = create_chart(metrics.df_1d, metrics.price, metrics.daily_high, metrics.daily_low, symbol, "log_chart.png")
    photo = BufferedInputFile(chart_buffer.getvalue(), filename="log_chart.png")

    log_text = (
        f"📖 **ЩОДЕННИК УГОДИ ({symbol})** | `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}`\n\n"
        f"📝 **Запис:**\n_{user_note}_\n\n"
        f"💰 Ціна: `${metrics.price:,.2f}` | RSI: `{metrics.rsi_1d:.1f}`"
    )

    await bot.send_photo(chat_id=LOG_CHANNEL_ID, photo=photo, caption=log_text, parse_mode="Markdown")
    await message.answer("✅ У щоденнику!", reply_markup=main_keyboard)
    await wait_msg.delete()

async def check_alerts() -> None:
    try:
        for symbol in SWING_WATCHLIST: 
            metrics = await get_market_data(symbol)
            if not metrics.is_valid: 
                continue 
            
            alert_message, current_alert_type = None, None
            is_volume_anomaly: bool = metrics.cur_vol > (metrics.avg_vol * 1.5)
            vol_tag = "⚠️ [ІСТИННИЙ ПРОБІЙ З ОБ'ЄМОМ]" if is_volume_anomaly else "[Локальний вихід]"

            if metrics.price >= metrics.daily_high and is_volume_anomaly: 
                current_alert_type, alert_message = "TRUE_RESISTANCE", f"🚨 МАКРО-ПРОБІЙ ВГОРУ ({symbol}): {metrics.price:,.2f}. {vol_tag}"
            elif metrics.price <= metrics.daily_low and is_volume_anomaly: 
                current_alert_type, alert_message = "TRUE_SUPPORT", f"🚨 МАКРО-ПРОБІЙ ВНИЗ ({symbol}): {metrics.price:,.2f}. {vol_tag}"
            elif metrics.rsi_1d >= 80: 
                current_alert_type, alert_message = "RSI_HIGH", f"🔥 ЕКСТРЕМАЛЬНА ПЕРЕКУПЛЕНІСТЬ ({symbol}): {metrics.rsi_1d:.1f}"
            elif metrics.rsi_1d <= 20: 
                current_alert_type, alert_message = "RSI_LOW", f"🧊 ЕКСТРЕМАЛЬНА ПЕРЕПРОДАНІСТЬ ({symbol}): {metrics.rsi_1d:.1f}"
            else: 
                alert_state[f"last_{symbol}"] = None
                await save_state(alert_state)

            if alert_message and current_alert_type != alert_state.get(f"last_{symbol}"):
                await bot.send_message(chat_id=ADMIN_ID, text=alert_message)
                
                alert_state[f"last_{symbol}"] = current_alert_type
                await save_state(alert_state)
                
                if current_alert_type in ["TRUE_RESISTANCE", "TRUE_SUPPORT"]:
                    await bot.send_message(chat_id=ADMIN_ID, text=f"🧠 Запускаю авто-аналіз Свінг-плану для {symbol}...")
                    
                    news = await fetch_news(symbol)
                    fng_index = await fetch_fear_and_greed()
                    
                    risk_usd = TRADE_DEPOSIT * (TRADE_RISK_PCT / 100)
                    risks = metrics.calculate_risk_params(risk_usd)

                    ai_text = await get_ai_forecast(metrics, risks, fng_index, news, risk_usd)
                    
                    await bot.send_message(chat_id=ADMIN_ID, text=f"🤖 **Auto Swing AI ({symbol}):**\n\n{ai_text}", parse_mode="Markdown")
                    await asyncio.sleep(5)
            
            await asyncio.sleep(1.5) 
            
    except Exception as e:
        logging.error(f"Critical error in check_alerts: {e}")
        try:
            await bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ **СИСТЕМНИЙ ЗБІЙ У ФОНОВОМУ ПРОЦЕСІ СВІНГ-БОТА:**\n`{e}`\nМодуль продовжує роботу, але потребує уваги.", parse_mode="Markdown")
        except:
            pass

async def main():
    # Явная инициализация состояния до запуска фоновых задач
    await init_state()
    
    scheduler.add_job(check_alerts, 'interval', minutes=15)
    scheduler.start()
    
    await bot.delete_webhook(drop_pending_updates=True) 
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())