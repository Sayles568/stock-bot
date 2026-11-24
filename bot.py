import os
import requests
import yfinance as yf
import feedparser
from google import genai

print("1. Скрипт запущен")

TG_TOKEN = os.environ["TG_TOKEN"].strip()
CHAT_ID = os.environ["CHAT_ID"].strip()
GEMINI_KEY = os.environ["GEMINI_KEY"].strip()

WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", 
    "META", "TSLA", "JPM", "V", "KO", "AMD", "NFLX"
]
DROP_THRESHOLD = -3.0

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    response = requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    print("Ответ Telegram:", response.status_code, response.text)

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
                    alerts.append(f"📉 {ticker} упала на {change_pct:.2f}% (Цена: ${current_price:.2f})")
        except Exception as e:
            print(f"Ошибка по {ticker}: {e}")
    return alerts

def get_top_news():
    feed = feedparser.parse("https://finance.yahoo.com/news/rssindex")
    headlines = [entry.title for entry in feed.entries[:25]]
    print(f"2. Найдено новостей в RSS: {len(headlines)}")
    
    if not headlines:
        return "Новости не найдены"
        
    client = genai.Client(api_key=GEMINI_KEY)
    prompt = (
        "Ты финансовый аналитик. Из этого списка заголовков выбери максимум 3 самые важные новости, "
        "которые реально влияют на фондовый рынок, экономику или крупные компании. "
        "Переведи их на русский язык и кратко (в 1-2 предложения) объясни суть каждой. "
        "Не используй звездочки и Markdown-разметку.\n\n"
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
        message += "🚨 ПАДЕНИЕ ХОРОШИХ АКЦИЙ:\n" + "\n".join(stock_alerts) + "\n\n"
    
    if news_summary:
        message += "📰 ГЛАВНЫЕ НОВОСТИ РЫНКА:\n" + news_summary
        
    print("3. Отправляем сообщение в Telegram...")
    send_telegram(message)
