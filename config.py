import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from google import genai

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TRADE_DEPOSIT = float(os.getenv("TRADE_DEPOSIT", 1000))
TRADE_RISK_PCT = float(os.getenv("TRADE_RISK_PCT", 2))

SWING_WATCHLIST_RAW = os.getenv("SWING_WATCHLIST", "BTC,ETH,SOL,BNB,XRP")
SWING_WATCHLIST = [coin.strip() for coin in SWING_WATCHLIST_RAW.split(",")]

if not all([BOT_TOKEN, ADMIN_ID, LOG_CHANNEL_ID, GEMINI_API_KEY]):
    raise ValueError("Відсутні токени в .env!")

# --- АРХІТЕКТУРА НАБЛЮДАЕМОСТІ (OBSERVABILITY) ---
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s')

file_handler = RotatingFileHandler(
    "bot_errors.log", 
    maxBytes=5 * 1024 * 1024, # 5 MB
    backupCount=3,
    encoding="utf-8"
)
file_handler.setLevel(logging.ERROR)
file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)
# --------------------------------------------------

# Ініціалізація нового клієнта Google GenAI
ai_client = genai.Client(api_key=GEMINI_API_KEY)