import os
import sqlite3
import time
import cloudscraper
import urllib3
from flask import Flask, render_template_string, request, jsonify

# إيقاف تحذيرات الشهادات الأمنية
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "EAArK8Mlf8H4BS2PaVN9bh8mS3A3TsZCFhET7Jf5koMIGxykLgOTzO7c7rKWbnukhIzyMUfgZBMVvXUtjfZAPQ5ZCFK6sTDFGuHWiUhRW1J8iahNRnqIjCwf8bXBc3C0pIz1m4jzmns71VIe5ZBZAJK3BZCsur6Vasp72Gen5ZBZCOH5ngZBDrvZBoLSZBVXi69nxIaJag9XQvJGu3bKiZCLzejA6M")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_secure_verify_token")

SYSTEM_LOGS = []

def add_log(message):
    global SYSTEM_LOGS
    print(message)
    SYSTEM_LOGS.insert(0, message)
    if len(SYSTEM_LOGS) > 50:
        SYSTEM_LOGS.pop()

def init_db():
    conn = sqlite3.connect("system_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('threshold_limit', '300000')")
    conn.commit()
    conn.close()

init_db()

def get_db_value(key):
    conn = sqlite3.connect("system_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

def send_fb_message(recipient_id, text):
    if not PAGE_ACCESS_TOKEN:
        add_log("Error: PAGE_ACCESS_TOKEN is not set.")
        return
    url = f"https://graph.facebook.com/v18.0/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "access_token": PAGE_ACCESS_TOKEN
    }
    # استخدام cloudscraper حتى لإرسال رسائل فيسبوك إن أردت أو requests العادي
    import requests
    response = requests.post(url, json=payload)
    add_log(f"FB Send Response: {response.status_code}, {response.text}")

# --- جلب رصيد FTTH باستخدام Cloudscraper لتجاوز حماية aes.js ---
def get_ftth_balance():
    api_url = "https://war.ct.ws/api_balance.php?api_key=my_super_secret_key_1995"
    retries = 3
    
    # إنشاء مشغل سكرابر لتجاوز الحماية
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
    
    for attempt in range(retries):
        try:
            response = scraper.get(api_url, timeout=15)
            add_log(f"Cloudscraper Attempt {attempt + 1} Status: {response.status_code}")
            add_log(f"Cloudscraper Raw Text: {response.text[:100]}")
            
            if response.status_code == 200 and response.text.strip():
                data = response.json()
                balance = data.get("model", {}).get("balance", 0)
                return int(float(balance))
        except Exception as e:
            add_log(f"Cloudscraper Attempt {attempt + 1} failed: {e}")
            time.sleep(2)
            
    return "خطأ في الاتصال بالخادم"

def get_towers_balance():
    return "قيد التحديث"

LOGS_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>سجلات النظام - Logs</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body { font-family: 'Courier New', Courier, monospace; background: #1e1e1e; color: #00ff66; margin: 0; padding: 20px; }
        .wrapper { max-width: 900px; margin: auto; background: #2d2d2d; padding: 25px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        h2 { color: #fff; text-align: center; border-bottom: 2px solid #444; padding-bottom: 10px; }
        .log-box { background: #000; padding: 15px; border-radius: 5px; height: 400px; overflow-y: scroll; border: 1px solid #444; font-size: 14px; line-height: 1.6; }
        .footer { text-align: center; margin-top: 15px; color: #aaa; font-size: 12px; }
    </style>
</head>
<body>
    <div class="wrapper">
        <h2>🖥️ Live System Logs (مباشر)</h2>
        <div class="log-box">
            {% for log in logs %}
                <div>> {{ log }}</div>
            {% endfor %}
        </div>
        <div class="footer">تتحدث الصفحة تلقائياً كل 5 ثوانٍ لعرض النشاطات الواردة وصادرات البوت.</div>
    </div>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    return render_template_string(LOGS_HTML, logs=SYSTEM_LOGS)

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode and token and mode == "subscribe" and token == VERIFY_TOKEN:
        add_log("Webhook verified successfully by Facebook!")
        return challenge, 200
    add_log("Webhook verification failed!")
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def handle_messages():
    try:
        data = request.json
        add_log(f"Webhook Received: {data}")
        if data.get("object") == "page":
            for entry in data.get("entry", []):
                for messaging in entry.get("messaging", []):
                    sender_id = messaging.get("sender", {}).get("id")
                    
                    if "message" in messaging and "text" in messaging["message"]:
                        message_text = messaging["message"]["text"].strip().lower()
                        add_log(f"Message from {sender_id}: {message_text}")
                        
                        if message_text in ["رصيد", "الرصيد", "balance", "ftth"]:
                            try:
                                t_bal = get_towers_balance()
                                f_bal = get_ftth_balance()
                            except Exception as inner_e:
                                add_log(f"Balance Fetch Error: {inner_e}")
                                f_bal = "خطأ في الاتصال بالخادم"
                                t_bal = "خطأ في الاتصال بالخادم"

                            limit_val = get_db_value("threshold_limit") or "300000"
                            
                            t_str = f"{t_bal:,.0f} دينار" if isinstance(t_bal, (int, float)) else str(t_bal)
                            f_str = f"{f_bal:,.0f} دينار" if isinstance(f_bal, (int, float)) else str(f_bal)
                            
                            reply = f"📊 **الرصيد الحالي للأنظمة:**\n"
                            reply += f"- الأبراج: {t_str}\n"
                            reply += f"- FTTH: {f_str}\n"
                            reply += f"⚙️ حد التحذير: {int(limit_val):,.0f} دينار"
                            
                            send_fb_message(sender_id, reply)
                            
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        add_log(f"Webhook Global Error: {e}")
        return jsonify({"status": "error"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
