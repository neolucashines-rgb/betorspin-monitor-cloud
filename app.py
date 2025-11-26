import os
import threading
import time
import requests
from flask import Flask

# Flask web uygulaması (Render bunu web service olarak çalıştıracak)
app = Flask(__name__)

# === AYARLAR ===
BOT_TOKEN = os.environ["BOT_TOKEN"]              # Render'da env olarak vereceğiz
CHAT_ID = int(os.environ["CHAT_ID"])             # Render env
DOMAIN_URL = os.environ.get("DOMAIN_URL", "https://betorspin101.com/pt-br/")
CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL_SECONDS", "60"))

EXPECTED_KEYWORD = os.environ.get("EXPECTED_KEYWORD", "Betorspin")
MIN_HTML_LENGTH = int(os.environ.get("MIN_HTML_LENGTH", "5000"))

# Domain durumu (UP/DOWN) hafızada tutulacak
last_status = {DOMAIN_URL: None}

def send_telegram_message(text: str):
    """Telegram botuna mesaj gönder."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Telegram mesajı gönderilemedi: {e}", flush=True)

def check_domain(domain: str) -> bool:
    """Site gerçekten çalışıyor mu? 503 dahil her türlü sıkıntıyı DOWN say."""
    try:
        r = requests.get(domain, timeout=10)
    except Exception as e:
        print(f"İstek hatası: {e}", flush=True)
        return False

    if r.status_code != 200:
        print(f"HTTP status {r.status_code} → DOWN", flush=True)
        return False

    html = r.text or ""

    if len(html) < MIN_HTML_LENGTH:
        print(f"HTML çok kısa ({len(html)} chars) → DOWN", flush=True)
        return False

    if EXPECTED_KEYWORD.lower() not in html.lower():
        print(f"'{EXPECTED_KEYWORD}' bulunamadı → DOWN", flush=True)
        return False

    return True

def monitor_loop():
    """Arka planda domaini sürekli kontrol eden döngü."""
    global last_status
    print("Monitor loop başladı...", flush=True)

    while True:
        up = check_domain(DOMAIN_URL)
        before = last_status[DOMAIN_URL]

       if before is None:
    # İlk kontrol → UP ya da DOWN neyse Telegram'a haber ver
    last_status[DOMAIN_URL] = up

    if up:
        send_telegram_message(f"✅ {DOMAIN_URL} çalışıyor (ilk kontrol)")
    else:
        send_telegram_message(f"⚠️ {DOMAIN_URL} şu anda ULAŞILAMIYOR! (ilk kontrol)")

    print(f"{DOMAIN_URL} ilk kontrol → {'UP' if up else 'DOWN'}", flush=True)

        elif up != before:
            # Durum değişti
            last_status[DOMAIN_URL] = up
            if not up:
                send_telegram_message(f"⚠️ {DOMAIN_URL} ULAŞILAMIYOR!")
            else:
                send_telegram_message(f"✅ {DOMAIN_URL} tekrar çalışıyor!")
            print(f"{DOMAIN_URL} DURUM DEĞİŞTİ → {'UP' if up else 'DOWN'}", flush=True)
        else:
            # Durum aynı
            print(f"{DOMAIN_URL} → {'UP' if up else 'DOWN'}", flush=True)

        time.sleep(CHECK_INTERVAL_SECONDS)

# Flask route – Render bunu HTTP için kullanacak
@app.route("/")
def index():
    return "Betorspin monitor up and running ✅", 200

# Uygulama ayağa kalkınca monitor thread'ini başlat
def start_monitor_thread():
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()

start_monitor_thread()

if __name__ == "__main__":
    # Local test için
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
