import os
import requests
import yfinance as yf
import feedparser
from google import genai

# Подтягиваем ключи из настроек GitHub
TG_TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
GEMINI_KEY = os.environ["GEMINI_KEY"]

# Список "хороших" акций для отслеживания (можете менять тикеры)
WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", 
    "META", "TSLA", "JPM", "V", "KO", "AMD", "NFLX"
]
DROP_THRESHOLD = -3.0  # Уведомлять, если падение сильнее -3% за день

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})

def check_stocks():
    alerts = []
    for ticker in WATCHLIST:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if len(hist) >= 2:
                prev_close = hist["Close"].iloc[-2]
                current_price = hist["Close"].iloc[-1]
                change_pct = ((current_price - prev_close) / prev_close) * 100
                
                if change_pct <= DROP_THRESHOLD:
                    alerts.append(f"📉 <b>{ticker}</b> упала на <b>{change_pct:.2f}%</b> (Цена: ${current_price:.2f})")
        except Exception as e:
            print(f"Ошибка по {ticker}: {e}")
    return alerts

def get_top_news():
    # Берем свежие новости Yahoo Finance
    feed = feedparser.parse("https://finance.yahoo.com/news/rssindex")
    headlines = [entry.title for entry in feed.entries[:25]]
    
    if not headlines:
        return ""
        
    client = genai.Client(api_key=GEMINI_KEY)
    prompt = (
        "Ты финансовый аналитик. Из этого списка заголовков выбери максимум 3 самые важные новости, "
        "которые реально влияют на фондовый рынок, экономику или крупные компании. "
        "Переведи их на русский язык и кратко (в 1-2 предложения) объясни суть каждой.\n\n"
        + "\n".join(headlines)
    )
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return response.text

if __name__ == "__main__":
    stock_alerts = check_stocks()
    news_summary = get_top_news()
    
    message = ""
    if stock_alerts:
        message += "🚨 <b>ПАДЕНИЕ ХОРОШИХ АКЦИЙ:</b>\n" + "\n".join(stock_alerts) + "\n\n"
    
    if news_summary:
        message += "📰 <b>ГЛАВНЫЕ НОВОСТИ РЫНКА:</b>\n" + news_summary
        
    if message:
        send_telegram(message)
      
