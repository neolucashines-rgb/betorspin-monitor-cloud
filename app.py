import os
import threading
import time
import requests
from flask import Flask

# =======================================
#  Flask Uygulaması (Render burayı çalıştırıyor)
# =======================================
app = Flask(__name__)

# =======================================
#  AYARLAR (ENV DEĞİŞKENLERİNDEN OKUNUR)
# =======================================

# Telegram bot token (Render -> Environment -> BOT_TOKEN)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# Telegram chat id (Render -> Environment -> CHAT_ID)
_raw_chat_id = os.environ.get("CHAT_ID", "").strip()
try:
    CHAT_ID = int(_raw_chat_id)
except ValueError:
    CHAT_ID = _raw_chat_id  # string kalırsa da Telegram kabul ediyor

# İzlenecek domain (Render -> Environment -> DOMAIN_URL)
DOMAIN_URL = os.environ.get(
    "DOMAIN_URL",
    "https://betorspin101.com/pt-br/"
).strip()

# Kaç saniyede bir kontrol edilecek (değişken yoksa 60 saniye)
CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL_SECONDS", "60"))

# HTML içinde mutlaka bulunması gereken anahtar kelime
EXPECTED_KEYWORD = os.environ.get("EXPECTED_KEYWORD", "Betorspin").strip()

# HTML minimum uzunluk (çok kısa ise DOWN say)
MIN_HTML_LENGTH = int(os.environ.get("MIN_HTML_LENGTH", "5000"))

# Render servis URL'in (uykuya düşmemesi için burayı ping’liyoruz)
MY_SERVICE_URL = "https://betorspin-monitor-cloud.onrender.com/"

# Domain son durumunu hafızada tut (UP/DOWN)
last_status = {DOMAIN_URL: None}

# =======================================
#  Telegram Yardımcı Fonksiyonu
# =======================================
def send_telegram_message(text: str):
    """Telegram botuna mesaj gönder."""
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram ayarları eksik, mesaj gönderilemedi.", flush=True)
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code != 200:
            print(
                f"Telegram hatası (HTTP {r.status_code}): {r.text}",
                flush=True
            )
        else:
            print("Telegram mesajı gönderildi.", flush=True)
    except Exception as e:
        print(f"Telegram mesajı gönderilemedi: {e}", flush=True)


# =======================================
#  Domain Kontrol Fonksiyonu
# =======================================
def check_domain(domain: str) -> bool:
    """
    Site gerçekten çalışıyor mu?
    - HTTP 200 değilse DOWN
    - HTML çok kısaysa DOWN
    - EXPECTED_KEYWORD yoksa DOWN
    """
    try:
        r = requests.get(domain, timeout=10)
    except Exception as e:
        print(f"[CHECK] İstek hatası: {e}", flush=True)
        return False

    if r.status_code != 200:
        print(f"[CHECK] HTTP status {r.status_code} → DOWN", flush=True)
        return False

    html = r.text or ""
    if len(html) < MIN_HTML_LENGTH:
        print(f"[CHECK] HTML çok kısa ({len(html)} chars) → DOWN", flush=True)
        return False

    if EXPECTED_KEYWORD.lower() not in html.lower():
        print(
            f"[CHECK] '{EXPECTED_KEYWORD}' bulunamadı → DOWN",
            flush=True
        )
        return False

    return True


# =======================================
#  Ana Monitor Döngüsü (Arka Plan Thread)
# =======================================
def monitor_loop():
    """Arka planda domaini sürekli kontrol eden döngü."""
    global last_status
    print("Monitor loop başladı...", flush=True)

    while True:
        up = check_domain(DOMAIN_URL)
        before = last_status[DOMAIN_URL]

        # -----------------------------
        # İlk kontrol → HER ZAMAN Telegram bildirimi
        # -----------------------------
        if before is None:
            last_status[DOMAIN_URL] = up

            if up:
                send_telegram_message(
                    f"✅ İlk kontrol: {DOMAIN_URL} şu anda ÇALIŞIYOR (UP)."
                )
            else:
                send_telegram_message(
                    f"⚠️ İlk kontrol: {DOMAIN_URL} şu anda ULAŞILAMIYOR (DOWN)!"
                )

            print(
                f"{DOMAIN_URL} ilk kontrol → {'UP' if up else 'DOWN'}",
                flush=True
            )

        # -----------------------------
        # Durum değişti (UP → DOWN veya DOWN → UP)
        # -----------------------------
        elif up != before:
            last_status[DOMAIN_URL] = up

            if not up:
                send_telegram_message(f"⚠️ {DOMAIN_URL} ULAŞILAMIYOR!")
            else:
                send_telegram_message(f"✅ {DOMAIN_URL} tekrar çalışıyor!")

            print(
                f"{DOMAIN_URL} DURUM DEĞİŞTİ → {'UP' if up else 'DOWN'}",
                flush=True
            )

        # -----------------------------
        # Durum aynı (sadece log’a yaz)
        # -----------------------------
        else:
            print(
                f"{DOMAIN_URL} → {'UP' if up else 'DOWN'}",
                flush=True
            )

        time.sleep(CHECK_INTERVAL_SECONDS)


# =======================================
#  Keep-Alive Döngüsü (Render Free Sleep Hack)
# =======================================
def keep_alive():
    """
    Render free plan'in servisi uyku moduna almasını engellemek için
    periyodik olarak kendi URL'imize istek atar.
    """
    while True:
        try:
            requests.get(MY_SERVICE_URL, timeout=5)
            print("Keep-alive ping gönderildi", flush=True)
        except Exception as e:
            print(f"Keep-alive hata: {e}", flush=True)
        # 4 dakikada bir kendi kendine ping at
        time.sleep(240)


# =======================================
#  Flask Route'ları
# =======================================
@app.route("/")
def index():
    """Ana healthcheck endpoint — Render burayı HTTP 200 görünce 'sağlıklı' der."""
    return "Betorspin monitor up and running ✅", 200


@app.route("/ping")
def ping():
    """Basit ping endpoint'i, debug için."""
    return "pong", 200


@app.route("/test")
def test():
    """Telegram'a manuel test mesajı gönder."""
    send_telegram_message("🧪 TEST: Betorspin monitor'dan deneme bildirimi.")
    return "Test mesajı gönderildi.", 200


# =======================================
#  Başlangıç Bildirimi
# =======================================
def notify_startup():
    msg = (
        "🚀 Betorspin monitor YENİDEN BAŞLATILDI.\n\n"
        f"🌐 DOMAIN: {DOMAIN_URL}\n"
        f"⏱️ KONTROL ARALIĞI: {CHECK_INTERVAL_SECONDS} saniye\n"
        f"🔍 EXPECTED_KEYWORD: {EXPECTED_KEYWORD}"
    )
    send_telegram_message(msg)


# =======================================
#  Uygulama Başlangıcı
# =======================================
def start_background_threads():
    """Monitor ve Keep-Alive thread'lerini başlat."""
    t_monitor = threading.Thread(target=monitor_loop, daemon=True)
    t_monitor.start()

    t_alive = threading.Thread(target=keep_alive, daemon=True)
    t_alive.start()


# Önce Telegram'a "yeniden başlatıldı" mesajı at
notify_startup()

# Sonra arka plan thread'lerini başlat
start_background_threads()


if __name__ == "__main__":
    # Local test için çalıştırma ayarı
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
