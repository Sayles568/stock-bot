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

    prompt = (
        "Ты финансовый аналитик. Проанализируй список акций и свежие новости.\n"
        "АКЦИИ:\n" + market_summary + "\n\n"
        "НОВОСТИ:\n" + news_summary + "\n\n"
        "Верни строго JSON объект со следующей структурой:\n"
        "{\n"
        '  "stocks_verdicts": {\n'
        '    "AAPL": {"verdict": "BUY", "reason": "Короткая причина на русском в 1 предложение"}\n'
        "  },\n"
        '  "fresh_news": [\n'
        '    {"title": "Заголовок новости на русском", "summary": "Суть в 1-2 предложениях на русском", "tickers": "NVDA, AAPL"}\n'
        "  ]\n"
        "}\n"
        "В stocks_verdicts добавь каждый тикер из списка выше: verdict строго BUY (если сейчас выгодно брать на просадке или перспективе) или AVOID (если лучше не брать или ждать). "
        "В fresh_news выбери до 5 самых важных новостей о компаниях и рынке."
    )

    ai_res = call_gemini_json(prompt)
    if ai_res:
        verdicts = ai_res.get("stocks_verdicts", {})
        for s in stocks_data:
            v = verdicts.get(s["ticker"])
            if v:
                s["verdict"] = "BUY" if v.get("verdict") == "BUY" else "AVOID"
                s["reason"] = v.get("reason", s["reason"])

        now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")
        now_ts = datetime.now(timezone.utc).timestamp()
        old_news = existing_data.get("news_7d", [])
        seven_days_ago = now_ts - 7 * 86400
        valid_old_news = [n for n in old_news if n.get("ts", now_ts) >= seven_days_ago]

        existing_titles = {n["title"] for n in valid_old_news}
        new_items = []
        for n in ai_res.get("fresh_news", []):
            if n.get("title") and n["title"] not in existing_titles:
                new_items.append({
                    "title": n["title"],
                    "summary": n.get("summary", ""),
                    "tickers": n.get("tickers", "Рынок"),
                    "date": now_str,
                    "ts": now_ts
                })
        combined_news = (new_items + valid_old_news)[:40]
    else:
        combined_news = existing_data.get("news_7d", [])

    final_data = {
        "updated_at": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC"),
        "stocks": stocks_data,
        "news_7d": combined_news
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
    return final_data


def check_emergency_news(headlines):
    if not headlines:
        return None
    prompt = (
        "Ты риск-менеджер. Посмотри на заголовки:\n" + "\n".join(headlines) +
        "\n\nЕсть ли тут ЭКСТРЕННАЯ ситуация: начало войны, экстренное решение ФРС, банкротство крупного банка, обвал рынков? "
        "Если НЕТ — ответь строго: НЕТ\n"
        "Если ЕСТЬ — опиши в 2 предложениях на русском без звездочек."
    )
    res = call_gemini_text(prompt)
    if not res or res.strip(".").upper() == "НЕТ":
        return None
    return res


if __name__ == "__main__":
    current_hour_utc = datetime.now(timezone.utc).hour
    is_scheduled = (current_hour_utc % 5 == 0) or (EVENT_NAME == "workflow_dispatch")

    existing_data = load_existing_data()
    stocks_data, drops, emergency_drops = check_stocks()
    headlines = get_raw_headlines()

    final_data = update_ai_data(stocks_data, headlines, existing_data)

    if is_scheduled:
        buy_list = [s for s in final_data["stocks"] if s["verdict"] == "BUY"][:4]
        msg = "📊 ПЛАНОВАЯ СВОДКА РЫНКА\n\n📉 УПАВШИЕ АКЦИИ:\n"
        if drops:
            for s in drops[:6]:
                msg += f"• {s['ticker']}: {s['change']}% (${s['price']})\n"
        else:
            msg += "Сильных падений (>1.5%) сегодня нет.\n"

        if buy_list:
            msg += "\n✅ ЧТО СЕЙЧАС НУЖНО БРАТЬ (МНЕНИЕ ИИ):\n"
            for s in buy_list:
                msg += f"• {s['ticker']} (${s['price']}): {s['reason']}\n"

        msg += "\n👇 Графики всех 25 акций, новости за 7 дней и чат с Мишкой внутри приложения:"
        send_telegram(msg, with_button=True)
    else:
        urgent_news = check_emergency_news(headlines)
        if emergency_drops or urgent_news:
            alert_msg = "🚨 ЭКСТРЕННОЕ СООБЩЕНИЕ ПО РЫНКУ!\n\n"
            if emergency_drops:
                alert_msg += "💥 СИЛЬНЫЙ ОБВАЛ (>4%):\n"
                for s in emergency_drops:
                    alert_msg += f"• {s['ticker']}: {s['change']}% (${s['price']})\n"
                alert_msg += "\n"
            if urgent_news:
                alert_msg += f"⚡ СРОЧНАЯ НОВОСТЬ:\n{urgent_news}\n"
            send_telegram(alert_msg, with_button=True)
        else:
            print("Экстренных событий нет, данные для Mini App обновлены.")
            
