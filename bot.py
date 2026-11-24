import os
import json
from datetime import datetime, timezone
import requests
import yfinance as yf
import feedparser
from google import genai
from google.genai import types

TG_TOKEN = os.environ["TG_TOKEN"].strip()
CHAT_ID = os.environ["CHAT_ID"].strip()
GEMINI_KEY = os.environ["GEMINI_KEY"].strip()
EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME", "")

WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    "JPM", "V", "MA", "KO", "PEP", "WMT", "COST", "DIS",
    "AMD", "INTC", "NFLX", "CRM", "ADBE", "ORCL", "MCD", "NKE", "BA", "XOM"
]
DROP_THRESHOLD = -1.5
EMERGENCY_DROP = -4.0
MINI_APP_URL = "https://t.me/rshsrghiosbot/obvalaciy"

def send_telegram(text, with_button=True):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    for i in range(0, len(text), 4000):
        chunk = text[i:i+4000]
        payload = {"chat_id": CHAT_ID, "text": chunk}
        if with_button and i + 4000 >= len(text):
            payload["reply_markup"] = {
                "inline_keyboard": [[{"text": "📊 Открыть графики и Мишку", "url": MINI_APP_URL}]]
            }
        response = requests.post(url, json=payload)
        print("Ответ Telegram:", response.status_code, response.text)

def load_existing_data():
    if os.path.exists("data.json"):
        try:
            with open("data.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"stocks": [], "news_7d": [], "updated_at": ""}

def check_stocks():
    stocks_data = []
    drops = []
    emergency_drops = []

    for ticker in WATCHLIST:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="10d")
            if len(hist) >= 2:
                closes = [round(float(x), 2) for x in hist["Close"].tail(7).tolist()]
                dates = [d.strftime("%d.%m") for d in hist.index[-len(closes):]]
                prev_close = closes[-2]
                current_price = closes[-1]
                change_pct = round(((current_price - prev_close) / prev_close) * 100, 2)

                item = {
                    "ticker": ticker,
                    "price": current_price,
                    "change": change_pct,
                    "history": closes,
                    "dates": dates,
                    "verdict": "WAIT",
                    "reason": "Ожидается оценка аналитика"
                }
                stocks_data.append(item)

                if change_pct <= DROP_THRESHOLD:
                    drops.append(item)
                if change_pct <= EMERGENCY_DROP:
                    emergency_drops.append(item)
        except Exception as e:
            print(f"Ошибка по {ticker}: {e}")

    stocks_data.sort(key=lambda x: x["change"])
    drops.sort(key=lambda x: x["change"])
    return stocks_data, drops, emergency_drops

def get_raw_headlines():
    rss_urls = [
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
        "https://feeds.content.dowjones.io/public/rss/mw_topstories"
    ]
    headlines = []
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:12]:
                headlines.append(entry.title)
        except Exception as e:
            print(f"Ошибка RSS {url}: {e}")
    return list(dict.fromkeys(headlines))

def call_gemini_json(prompt):
    client = genai.Client(api_key=GEMINI_KEY)
    for model_name in ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash"]:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"JSON модель {model_name} ошибка: {e}")
    return None

def call_gemini_text(prompt):
    client = genai.Client(api_key=GEMINI_KEY)
    for model_name in ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash"]:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            print(f"Text модель {model_name} ошибка: {e}")
    return ""

def update_ai_data(stocks_data, headlines, existing_data):
    market_summary = "\n".join([f"{s['ticker']}: {s['change']:+.2f}% (${s['price']})" for s in stocks_data])
    news_summary = "\n".join(headlines[:15])

    prompt = f"""
Ты финансовый аналитик. Проанализируй список акций и свежие новости.
АКЦИИ:
{market_summary}

НОВОСТИ:
{news_summary}

Верни строго JSON объект со следующей структурой:
{{
  "stocks_verdicts": {{
    "AAPL": {{"verdict": "BUY", "reason": "Короткая причина на русском в 1 предложение"}},
    ... (для каждого тикера из списка: verdict строго "BUY" если сейчас выгодно брать на просадке/перспективе, или "AVOID" если лучше не брать/ждать)
  }},
  "fresh_news": [
    {{"title": "Заголовок новости на русском", "summary": "Суть в 1-2 предложениях на русском", "tickers": "NVDA, AAPL"}}

    
