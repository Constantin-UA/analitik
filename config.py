import os
import logging
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not all([BOT_TOKEN, ADMIN_ID, LOG_CHANNEL_ID, GEMINI_API_KEY]):
    raise ValueError("Отсутствуют токены в .env!")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

genai.configure(api_key=GEMINI_API_KEY)
# ИСПОЛЬЗУЕМ АКТУАЛЬНУЮ И СУЩЕСТВУЮЩУЮ МОДЕЛЬ
ai_model = genai.GenerativeModel('gemini-2.0-flash')