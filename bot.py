import os
import requests
import yfinance as yf
import feedparser
from google import genai

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
    rss_urls = [
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
        "https://feeds.content.dowjones.io/public/rss/mw_topstories"
    ]
    headlines = []
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                headlines.append(entry.title)
        except Exception as e:
            print(f"Ошибка RSS {url}: {e}")
            
    if not headlines:
        return "Не удалось загрузить ленту новостей."
        
    client = genai.Client(api_key=GEMINI_KEY)
    prompt = (
        "Ты финансовый аналитик. Из этого списка заголовков выбери максимум 3 самые важные новости, "
        "которые реально влияют на фондовый рынок, экономику или крупные компании. "
        "Переведи их на русский язык и кратко (в 1-2 предложения) объясни суть каждой. "
        "Не используй звездочки и Markdown-разметку.\n\n"
        + "\n".join(headlines)
    )
    
    # Пробуем актуальные модели по очереди, чтобы 100% сработало
    for model_name in ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash"]:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            return response.text
        except Exception as e:
            print(f"Модель {model_name} не подошла: {e}")
            
    return "Не удалось обработать новости через Gemini."

if __name__ == "__main__":
    stock_alerts = check_stocks()
    news_summary = get_top_news()
    
    message = ""
    if stock_alerts:
        message += "🚨 ПАДЕНИЕ ХОРОШИХ АКЦИЙ:\n" + "\n".join(stock_alerts) + "\n\n"
    else:
        message += "✅ Сильных падений (>3%) среди отслеживаемых акций нет.\n\n"
    
    if news_summary:
        message += "📰 ГЛАВНЫЕ НОВОСТИ РЫНКА:\n" + news_summary
        
    send_telegram(message)
