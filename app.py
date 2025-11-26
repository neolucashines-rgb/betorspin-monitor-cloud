import os
import threading
import time
import requests
from flask import Flask
from datetime import datetime

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

# Ana domain (zorunlu) – Brezilya sitesi
DOMAIN_URL = os.environ.get(
    "DOMAIN_URL",
    "https://betorspin101.com/pt-br/"
).strip()

DOMAIN_NAME = os.environ.get("DOMAIN_NAME", "Brazil").strip() or "Brazil"

# Kaç saniyede bir kontrol edilecek (değişken yoksa 60 saniye)
CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL_SECONDS", "60"))

# HTML içinde mutlaka bulunması gereken anahtar kelime
EXPECTED_KEYWORD = os.environ.get("EXPECTED_KEYWORD", "Betorspin").strip()

# HTML minimum uzunluk (çok kısa ise DOWN say)
MIN_HTML_LENGTH = int(os.environ.get("MIN_HTML_LENGTH", "5000"))

# Render servis URL'in (uykuya düşmemesi için burayı ping’liyoruz)
MY_SERVICE_URL = "https://betorspin-monitor-cloud.onrender.com/"

# Brezilya proxy (sadece domain kontrolünde kullanılacak)
PROXY_URL = os.environ.get("PROXY_URL", "").strip()
if PROXY_URL:
    HTTP_PROXIES = {
        "http": PROXY_URL,
        "https": PROXY_URL,
    }
    print(f"Proxy etkin: {PROXY_URL}", flush=True)
else:
    HTTP_PROXIES = None
    print("Proxy KULLANILMIYOR (PROXY_URL boş).", flush=True)

# ==========================
#  Çoklu hedef (şu an pratikte tek hedef: Brazil)
# ==========================
TARGETS = []

# Ana hedef
TARGETS.append(
    {
        "name": DOMAIN_NAME,
        "url": DOMAIN_URL,
    }
)

# İsteğe bağlı ek hedefler (Render ENV'e eklenirse)
for i in range(2, 6):  # TARGET2_..., TARGET3_..., TARGET4_..., TARGET5_...
    name_key = f"TARGET{i}_NAME"
    url_key = f"TARGET{i}_URL"
    t_name = os.environ.get(name_key, "").strip()
    t_url = os.environ.get(url_key, "").strip()
    if t_name and t_url:
        TARGETS.append(
            {
                "name": t_name,
                "url": t_url,
            }
        )

# Domain son durumunu ve son kontrol zamanını hafızada tut (UP/DOWN)
last_status = {t["url"]: None for t in TARGETS}
last_check_at = {t["url"]: None for t in TARGETS}


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
#  Domain Kontrol Fonksiyonu (BREZİLYA PROXY İLE)
# =======================================
def check_domain(domain: str) -> bool:
    """
    Site gerçekten çalışıyor mu?
    - HTTP 200 değilse DOWN
    - HTML çok kısaysa DOWN
    - EXPECTED_KEYWORD yoksa DOWN
    (Tüm istekler mümkünse Brezilya proxy üzerinden gider.)
    """
    try:
        if HTTP_PROXIES:
            r = requests.get(domain, timeout=10, proxies=HTTP_PROXIES)
        else:
            r = requests.get(domain, timeout=10)
    except Exception as e:
        print(f"[CHECK] {domain} istek hatası: {e}", flush=True)
        return False

    if r.status_code != 200:
        print(f"[CHECK] {domain} HTTP status {r.status_code} → DOWN", flush=True)
        return False

    html = r.text or ""
    if len(html) < MIN_HTML_LENGTH:
        print(f"[CHECK] {domain} HTML çok kısa ({len(html)} chars) → DOWN", flush=True)
        return False

    if EXPECTED_KEYWORD.lower() not in html.lower():
        print(
            f"[CHECK] {domain} içinde '{EXPECTED_KEYWORD}' bulunamadı → DOWN",
            flush=True
        )
        return False

    return True


# =======================================
#  Ana Monitor Döngüsü (Arka Plan Thread)
# =======================================
def monitor_loop():
    """Arka planda tüm hedef domainleri sürekli kontrol eden döngü."""
    global last_status, last_check_at
    print("Monitor loop başladı...", flush=True)

    while True:
        now = datetime.utcnow()

        for target in TARGETS:
            name = target["name"]
            url = target["url"]

            up = check_domain(url)
            before = last_status.get(url)
            last_status[url] = up
            last_check_at[url] = now

            # İlk kontrol → HER ZAMAN Telegram bildirimi
            if before is None:
                if up:
                    send_telegram_message(
                        f"✅ İlk kontrol: <b>{name}</b>\n"
                        f"URL: {url}\n"
                        f"Durum: <b>UP</b> (çalışıyor - Brezilya proxy)"
                    )
                else:
                    send_telegram_message(
                        f"⚠️ İlk kontrol: <b>{name}</b>\n"
                        f"URL: {url}\n"
                        f"Durum: <b>DOWN</b> (ulaşılamıyor - Brezilya proxy)"
                    )

                print(
                    f"[FIRST] {name} ({url}) → {'UP' if up else 'DOWN'}",
                    flush=True
                )

            # Durum değişti (UP → DOWN veya DOWN → UP)
            elif up != before:
                if not up:
                    send_telegram_message(
                        f"⚠️ <b>{name}</b> ULAŞILAMIYOR! (Brezilya proxy)\nURL: {url}"
                    )
                else:
                    send_telegram_message(
                        f"✅ <b>{name}</b> tekrar çalışıyor! (Brezilya proxy)\nURL: {url}"
                    )

                print(
                    f"[CHANGE] {name} ({url}) DURUM DEĞİŞTİ → {'UP' if up else 'DOWN'}",
                    flush=True
                )

            # Durum aynı (sadece log’a yaz)
            else:
                print(
                    f"[SAME] {name} ({url}) → {'UP' if up else 'DOWN'}",
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
#  Telegram Komut Döngüsü (/status, /help, /ping)
# =======================================
def handle_command(cmd: str):
    lower = cmd.strip().lower()

    if lower in ("/status", "status"):
        lines = ["📊 <b>Betorspin Monitor Durumu</b>\n(Brezilya proxy bazlı sonuçlar)"]

        now = datetime.utcnow()
        for t in TARGETS:
            name = t["name"]
            url = t["url"]
            status = last_status.get(url)
            last = last_check_at.get(url)

            if status is True:
                s = "UP ✅"
            elif status is False:
                s = "DOWN ❌"
            else:
                s = "bilinmiyor ⏳"

            if last:
                ago = int((now - last).total_seconds())
                lines.append(
                    f"• <b>{name}</b> → {s}  (son kontrol: {ago} sn önce)\n  {url}"
                )
            else:
                lines.append(
                    f"• <b>{name}</b> → {s}  (henüz kontrol edilmedi)\n  {url}"
                )

        send_telegram_message("\n".join(lines))

    elif lower in ("/ping", "ping"):
        send_telegram_message("🏓 Monitor ayakta, komutları alıyorum (Brezilya proxy ile).")

    elif lower in ("/help", "help"):
        send_telegram_message(
            "🤖 <b>Betorspin Monitor Komutları</b>\n\n"
            "/status - Tüm URL'lerin UP/DOWN durumunu gösterir (Brezilya bazlı)\n"
            "/ping - Bot çalışıyor mu kontrol et\n"
            "/help - Bu mesaj\n"
        )
    else:
        send_telegram_message(
            "❓ Bilinmeyen komut.\n\n"
            "/status, /ping veya /help yazabilirsin."
        )


def telegram_command_loop():
    """Telegram getUpdates ile komutları dinleyen döngü."""
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram komut döngüsü başlamadı (ayar eksik).", flush=True)
        return

    print("Telegram komut döngüsü başladı...", flush=True)
    offset = 0

    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            resp = requests.get(
                url,
                params={"timeout": 60, "offset": offset},
                timeout=70,
            )
            data = resp.json()
            results = data.get("result", [])

            for update in results:
                offset = max(offset, update["update_id"] + 1)

                msg = update.get("message")
                if not msg:
                    continue

                chat_id = msg["chat"]["id"]
                text = msg.get("text", "").strip()

                # Sadece bizim belirlediğimiz CHAT_ID'den gelen mesajı işle
                if str(chat_id) != str(CHAT_ID):
                    continue

                if not text:
                    continue

                print(f"[CMD] Telegram komutu alındı: {text}", flush=True)
                handle_command(text)

        except Exception as e:
            print(f"Telegram komut döngüsü hatası: {e}", flush=True)
            time.sleep(5)


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
    send_telegram_message("🧪 TEST: Betorspin monitor'dan deneme bildirimi. (Brezilya proxy)")
    return "Test mesajı gönderildi.", 200


# =======================================
#  Başlangıç Bildirimi
# =======================================
def notify_startup():
    lines = [
        "🚀 Betorspin monitor YENİDEN BAŞLATILDI.\n",
        f"📍 Lokasyon: BREZİLYA PROXY" if HTTP_PROXIES else "📍 Lokasyon: Doğrudan Render (proxy yok)",
        f"⏱️ Kontrol aralığı: {CHECK_INTERVAL_SECONDS} saniye",
        f"🔍 EXPECTED_KEYWORD: {EXPECTED_KEYWORD}",
        "",
        "🎯 İzlenen hedefler:",
    ]
    for t in TARGETS:
        lines.append(f"• {t['name']} → {t['url']}")

    send_telegram_message("\n".join(lines))


# =======================================
#  Uygulama Başlangıcı
# =======================================
def start_background_threads():
    """Monitor, Keep-Alive ve Telegram komut thread'lerini başlat."""
    t_monitor = threading.Thread(target=monitor_loop, daemon=True)
    t_monitor.start()

    t_alive = threading.Thread(target=keep_alive, daemon=True)
    t_alive.start()

    t_cmd = threading.Thread(target=telegram_command_loop, daemon=True)
    t_cmd.start()


# Önce Telegram'a "yeniden başlatıldı" mesajı at
notify_startup()

# Sonra arka plan thread'lerini başlat
start_background_threads()


if __name__ == "__main__":
    # Local test için çalıştırma ayarı
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
