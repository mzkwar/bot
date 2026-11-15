import os
import sqlite3
import threading
import time
import urllib.request
import requests
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session
from cryptography.fernet import Fernet

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super_secure_admin_secret_key_123")

# إعدادات فيسبوك أساسية
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_secure_verify_token")
ADMIN_FB_ID = os.getenv("ADMIN_FB_ID")
WEB_ADMIN_PASSWORD = os.getenv("WEB_ADMIN_PASSWORD", "admin123") # كلمة مرور لوحة التحكم

ENCRYPTION_KEY = Fernet.generate_key()
cipher = Fernet(ENCRYPTION_KEY)

# --- إعداد قاعدة البيانات المحلية ---
def init_db():
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS groups (id TEXT PRIMARY KEY)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('threshold_limit', '300000')")
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=(), fetch=False):
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = None
    if fetch:
        result = cursor.fetchall()
    conn.commit()
    conn.close()
    return result

def get_setting(key):
    res = db_execute("SELECT value FROM settings WHERE key = ?", (key,), fetch=True)
    if res:
        return res[0][0]
    return None

def set_setting(key, value):
    db_execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

def send_fb_message(recipient_id, text):
    if not PAGE_ACCESS_TOKEN:
        return
    url = f"https://graph.facebook.com/v18.0/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "access_token": PAGE_ACCESS_TOKEN
    }
    requests.post(url, json=payload)

def get_credentials(system_prefix):
    encrypted_user = get_setting(f"{system_prefix}_user")
    encrypted_pass = get_setting(f"{system_prefix}_pass")
    if not encrypted_user or not encrypted_pass:
        return None, None
    try:
        username = cipher.decrypt(encrypted_user.encode()).decode()
        password = cipher.decrypt(encrypted_pass.encode()).decode()
        return username, password
    except:
        return None, None

# --- محاكاة جلب الأرصدة (أو دمج الطريقة الخاصة بك) ---
def get_towers_balance():
    u, p = get_credentials("towers")
    if not u or not p:
        return "غير مُعرّف"
    # يمكنك وضع كود الجلب الفعلي هنا، سنضع قيمة تجريبية كمثال أو نعيد الرقم
    return 2765000

def get_ftth_balance():
    u, p = get_credentials("ftth")
    if not u or not p:
        return "غير مُعرّف"
    return 1450000

# --- صفحة لوحة التحكم التفاعلية (HTML الداخليه) ---
ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة تحكم بوت المراقبة</title>
    <style>
        body { font-family: Tahoma, sans-serif; background-color: #f4f7f6; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 800px; margin: auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        h2 { color: #007bff; text-align: center; }
        .card { background: #e9ecef; padding: 15px; margin: 15px 0; border-radius: 8px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type="text"], input[type="password"], input[type="number"] { width: 100%; padding: 10px; box-sizing: border-box; border: 1px solid #ccc; border-radius: 5px; }
        button { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-size: 16px; }
        button:hover { background: #0056b3; }
        .logout { float: left; background: #dc3545; }
        .logout:hover { background: #c82333; }
        .alert { padding: 10px; background: #d4edda; color: #155724; border-radius: 5px; margin-bottom: 15px; text-align: center; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/logout"><button class="logout">تسجيل الخروج</button></a>
        <h2>📊 لوحة تحكم شبكات إيرثلنك و FTTH</h2>
        
        {% if msg %}
            <div class="alert">{{ msg }}</div>
        {% endif %}

        <div class="card">
            <h3>📈 حالة الأرصدة الحالية</h3>
            <p><strong>رصيد الأبراج:</strong> {{ t_bal }} دينار</p>
            <p><strong>رصيد FTTH:</strong> {{ f_bal }} دينار</p>
            <p><strong>حد التحذير والتنبيه:</strong> {{ threshold }} دينار</p>
        </div>

        <div class="card">
            <h3>⚙️ تحديث إعدادات النظام والأرصدة</h3>
            <form method="POST">
                <div class="form-group">
                    <label>حد التنبيه ونفاذ الرصيد (دينار):</label>
                    <input type="number" name="threshold" value="{{ threshold }}">
                </div>
                
                <hr style="margin: 20px 0;">
                
                <h4>🔑 بيانات نظام الأبراج (Earthlink)</h4>
                <div class="form-group">
                    <label>اسم المستخدم (User):</label>
                    <input type="text" name="towers_user" placeholder="أدخل يوزر الأبراج">
                </div>
                <div class="form-group">
                    <label>كلمة المرور (Password):</label>
                    <input type="password" name="towers_pass" placeholder="أدخل كلمة المرور">
                </div>

                <hr style="margin: 20px 0;">

                <h4>🔑 بيانات نظام FTTH</h4>
                <div class="form-group">
                    <label>اسم المستخدم (User):</label>
                    <input type="text" name="ftth_user" placeholder="أدخل يوزر FTTH">
                </div>
                <div class="form-group">
                    <label>كلمة المرور (Password):</label>
                    <input type="password" name="ftth_pass" placeholder="أدخل كلمة المرور">
                </div>

                <button type="submit">حفظ التغييرات وتشفير البيانات</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>تسجيل الدخول لوحة التحكم</title>
    <style>
        body { font-family: Tahoma, sans-serif; background: #f4f7f6; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); width: 300px; text-align: center; }
        input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; }
        button { background: #007bff; color: white; border: none; padding: 10px; width: 100%; border-radius: 5px; cursor: pointer; }
        .error { color: red; font-size: 14px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h3>تسجيل الدخول للإدارة</h3>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
        <form method="POST">
            <input type="password" name="password" placeholder="أدخل كلمة المرور" required>
            <button type="submit">دخول</button>
        </form>
    </div>
</body>
</html>
"""

# --- مسارات الويب (Web Routes) ---
@app.route("/", methods=["GET", "POST"])
def admin_dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    msg = None
    if request.method == "POST":
        threshold = request.form.get("threshold")
        if threshold:
            set_setting("threshold_limit", threshold)
            
        t_u = request.form.get("towers_user")
        t_p = request.form.get("towers_pass")
        if t_u and t_p:
            set_setting("towers_user", cipher.encrypt(t_u.encode()).decode())
            set_setting("towers_pass", cipher.encrypt(t_p.encode()).decode())
            
        f_u = request.form.get("ftth_user")
        f_p = request.form.get("ftth_pass")
        if f_u and f_p:
            set_setting("ftth_user", cipher.encrypt(f_u.encode()).decode())
            set_setting("ftth_pass", cipher.encrypt(f_p.encode()).decode())
            
        msg = "✅ تم حفظ وتحديث الإعدادات بنجاح!"

    t_bal = get_towers_balance()
    f_bal = get_ftth_balance()
    threshold = get_setting("threshold_limit") or "300000"

    return render_template_string(ADMIN_TEMPLATE, t_bal=t_bal, f_bal=f_bal, threshold=threshold, msg=msg)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == WEB_ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            error = "كلمة المرور غير صحيحة!"
    return render_template_string(LOGIN_TEMPLATE, error=error)

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

# --- مستقبل رسائل فيسبوك (Messenger Webhook) ---
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode and token and mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def handle_messages():
    data = request.json
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender_id = messaging.get("sender", {}).get("id")
                message_text = messaging.get("message", {}).get("text", "").strip()
                
                if not message_text:
                    continue
                
                if message_text.lower() in ["رصيد", "الرصيد", "balance"]:
                    t_bal = get_towers_balance()
                    f_bal = get_ftth_balance()
                    limit_val = get_setting("threshold_limit")
                    
                    reply = f"📊 **الرصيد الحالي للأنظمة:**\n"
                    reply += f"- الأبراج: {t_bal:,.0f} دينار\n" if isinstance(t_bal, (int, float)) else f"- الأبراج: {t_bal}\n"
                    reply += f"- FTTH: {f_bal:,.0f} دينار\n" if isinstance(f_bal, (int, float)) else f"- FTTH: {f_bal}\n"
                    reply += f"⚙️ حد التحذير: {int(limit_val):,.0f} دينار"
                    
                    send_fb_message(sender_id, reply)

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
