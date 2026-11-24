import os
import requests
import yfinance as yf
import feedparser
from google import genai

TG_TOKEN = os.environ["TG_TOKEN"].strip()
CHAT_ID = os.environ["CHAT_ID"].strip()
GEMINI_KEY = os.environ["GEMINI_KEY"].strip()

# Расширенный список фундаментально сильных компаний ("голубых фишек")
WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    "JPM", "V", "MA", "KO", "PEP", "WMT", "COST", "DIS",
    "AMD", "INTC", "NFLX", "CRM", "ADBE", "ORCL", "MCD", "NKE", "BA", "XOM"
]
DROP_THRESHOLD = -1.5  # Показывать все акции, которые упали на 1.5% и сильнее

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    # Разбиваем сообщение, если оно вдруг длиннее лимита Telegram (4096 символов)
    for i in range(0, len(text), 4000):
        chunk = text[i:i+4000]
        response = requests.post(url, json={"chat_id": CHAT_ID, "text": chunk})
        print("Ответ Telegram:", response.status_code, response.text)

def check_stocks():
    drops = []
    all_changes = []
    
    for ticker in WATCHLIST:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            if len(hist) >= 2:
                prev_close = hist["Close"].iloc[-2]
                current_price = hist["Close"].iloc[-1]
                change_pct = ((current_price - prev_close) / prev_close) * 100
                
                all_changes.append((ticker, change_pct, current_price))
                
                if change_pct <= DROP_THRESHOLD:
                    drops.append((ticker, change_pct, current_price))
        except Exception as e:
            print(f"Ошибка по {ticker}: {e}")
            
    # Сортируем от самого сильного падения к меньшему
    drops.sort(key=lambda x: x[1])
    all_changes.sort(key=lambda x: x[1])
    return drops, all_changes

def analyze_market(drops, all_changes):
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

    # Формируем сводку по ценам для нейросети
    market_data = "\n".join([f"{t}: {pct:+.2f}% (${p:.2f})" for t, pct, p in all_changes])
    news_text = "\n".join(headlines) if headlines else "Свежих заголовков нет."

    client = genai.Client(api_key=GEMINI_KEY)
    prompt = (
        "Ты опытный портфельный управляющий и финансовый аналитик. Проанализируй текущую ситуацию на рынке.\n\n"
        f"ДИНАМИКА НАШИХ АКЦИЙ ЗА ДЕНЬ:\n{market_data}\n\n"
        f"ГЛАВНЫЕ НОВОСТИ:\n{news_text}\n\n"
        "Сделай структурированный отчет на русском языке строго без использования звездочек (*) и Markdown-разметки:\n"
        "1. 📰 ГЛАВНЫЕ НОВОСТИ: выбери 3 самые важные новости, влияющие на рынок, и объясни их суть в 1-2 предложениях.\n"
        "2. 💡 ИДЕИ ДЛЯ ПОКУПКИ (СКИДКИ): на основе новостей и сегодняшних просадок посоветуй 2-3 сильные акции из списка выше, которые сейчас выгодно подобрать на спаде (или которые имеют сильный драйвер роста). Для каждой напиши: тикер, почему стоит присмотреться и какие есть риски. В конце добавь короткую пометку, что это аналитика, а не индивидуальная инвест-рекомендация."
    )

    for model_name in ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash"]:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            return response.text
        except Exception as e:
            print(f"Модель {model_name} не подошла: {e}")

    return "Не удалось получить аналитику от нейросети."

if __name__ == "__main__":
    drops, all_changes = check_stocks()
    
    message = "📉 УПАВШИЕ АКЦИИ ЗА ДЕНЬ:\n"
    if drops:
        for ticker, pct, price in drops:
            message += f"• {ticker}: {pct:.2f}% (текущая цена: ${price:.2f})\n"
    else:
        message += "Сегодня среди отслеживаемых компаний падений сильнее -1.5% нет.\n"
        if all_changes:
            # Покажем топ-3 самых слабых за день, даже если падение небольшое
            weakest = [f"{t} ({pct:+.2f}%)" for t, pct, _ in all_changes[:3]]
            message += f"Самые слабые за день: {', '.join(weakest)}\n"
            
    message += "\n" + analyze_market(drops, all_changes)
    
    send_telegram(message)
