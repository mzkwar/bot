import os
import sqlite3
import requests
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify
from cryptography.fernet import Fernet

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "mahdi_secure_secret_key_9988")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ENCRYPTION_KEY = Fernet.generate_key()
cipher = Fernet(ENCRYPTION_KEY)

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_secure_verify_token")

# --- إعداد قاعدة البيانات المحلية ---
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

def set_db_value(key, value):
    conn = sqlite3.connect("system_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_decrypted_credential(prefix):
    enc_u = get_db_value(f"{prefix}_user")
    enc_p = get_db_value(f"{prefix}_pass")
    if not enc_u or not enc_p:
        return None, None
    try:
        user = cipher.decrypt(enc_u.encode()).decode()
        pwd = cipher.decrypt(enc_p.encode()).decode()
        return user, pwd
    except:
        return None, None

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

# --- جلب رصيد FTTH مباشرة من الـ API الخاص بك ---
def get_ftth_balance():
    try:
        api_url = "https://war.ct.ws/api_balance.php?api_key=my_super_secret_key_1995"
        response = requests.get(api_url, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            # استخراج الرصيد بالشكل الصحيح من داخل الـ model
            balance = data.get("model", {}).get("balance", 0)
            return int(float(balance))
            
        return "خطأ في الاستجابة من الـ API"
    except Exception as e:
        print(f"API Exception Error: {e}")
        return "خطأ في الاتصال بالخادم"

# --- دالة رصيد الأبراج ---
def get_towers_balance():
    u, p = get_decrypted_credential("towers")
    if not u or not p:
        return "غير مُعرّف"
    return "قيد التحديث"

# --- واجهات الويب (Dashboard & Login) ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة تحكم الأرصدة والشبكات</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; color: #333; }
        .wrapper { max-width: 900px; margin: auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.08); }
        h2 { color: #0066cc; text-align: center; margin-bottom: 25px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 25px; }
        .card { background: #f8f9fa; padding: 20px; border-radius: 8px; border-right: 5px solid #0066cc; }
        .card h3 { margin-top: 0; color: #444; }
        .amount { font-size: 20px; font-weight: bold; color: #28a745; margin-top: 10px; word-break: break-word; }
        .form-section { background: #fff; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; margin-bottom: 20px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 6px; font-weight: 600; }
        input[type="text"], input[type="password"], input[type="number"] { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }
        button { background: #0066cc; color: white; border: none; padding: 12px 25px; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold; width: 100%; }
        button:hover { background: #004d99; }
        .logout { background: #dc3545; width: auto; padding: 8px 15px; float: left; font-size: 14px; text-decoration: none; color: white; border-radius: 6px; }
        .logout:hover { background: #c82333; }
        .alert { padding: 12px; background: #d4edda; color: #155724; border-radius: 6px; margin-bottom: 20px; text-align: center; font-weight: bold; }
    </style>
</head>
<body>
    <div class="wrapper">
        <a href="/logout" class="logout">تسجيل الخروج</a>
        <h2>🛡️ لوحة إدارة ومراقبة أرصدة الشبكات</h2>
        
        {% if msg %}
            <div class="alert">{{ msg }}</div>
        {% endif %}

        <div class="grid">
            <div class="card">
                <h3>📡 رصيد الأبراج (Earthlink)</h3>
                <div class="amount">{{ t_disp }}</div>
            </div>
            <div class="card" style="border-right-color: #28a745;">
                <h3>🌐 رصيد FTTH</h3>
                <div class="amount">{{ f_disp }}</div>
            </div>
        </div>

        <div class="form-section">
            <h3>⚙️ إعدادات الحسابات وحد التنبيه</h3>
            <form method="POST">
                <div class="form-group">
                    <label>حد التنبيه ونفاذ الرصيد (دينار):</label>
                    <input type="number" name="threshold" value="{{ threshold }}">
                </div>

                <hr style="margin: 20px 0; border:0; border-top:1px solid #eee;">

                <div class="form-group">
                    <label>يوزر الأبراج (Earthlink User):</label>
                    <input type="text" name="towers_user" placeholder="أدخل اسم المستخدم للأبراج">
                </div>
                <div class="form-group">
                    <label>كلمة مرور الأبراج (Earthlink Password):</label>
                    <input type="password" name="towers_pass" placeholder="أدخل كلمة المرور">
                </div>

                <button type="submit">حفظ وتحديث الإعدادات</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>تسجيل الدخول للوحة التحكم</title>
    <style>
        body { font-family: Tahoma, sans-serif; background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .box { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); width: 320px; text-align: center; }
        input { width: 100%; padding: 12px; margin: 12px 0; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }
        button { background: #0066cc; color: white; border: none; padding: 12px; width: 100%; border-radius: 6px; font-weight: bold; cursor: pointer; }
        .error { color: #dc3545; font-size: 14px; }
    </style>
</head>
<body>
    <div class="box">
        <h3>تسجيل الدخول للإدارة</h3>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
        <form method="POST">
            <input type="password" name="password" placeholder="أدخل كلمة مرور الإدارة" required>
            <button type="submit">دخول</button>
        </form>
    </div>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    if not session.get("auth"):
        return redirect(url_for("login"))
    
    msg = None
    if request.method == "POST":
        threshold = request.form.get("threshold")
        if threshold:
            set_db_value("threshold_limit", threshold)
            
        t_u = request.form.get("towers_user")
        t_p = request.form.get("towers_pass")
        if t_u and t_p:
            set_db_value("towers_user", cipher.encrypt(t_u.encode()).decode())
            set_db_value("towers_pass", cipher.encrypt(t_p.encode()).decode())
            
        msg = "✅ تم حفظ التحديثات والإعدادات بنجاح!"

    t_bal = get_towers_balance()
    f_bal = get_ftth_balance()
    threshold = get_db_value("threshold_limit") or "300000"
    
    t_disp = f"{t_bal:,.0f} دينار" if isinstance(t_bal, int) else t_bal
    f_disp = f"{f_bal:,.0f} دينار" if isinstance(f_bal, int) else f_bal

    return render_template_string(DASHBOARD_HTML, t_disp=t_disp, f_disp=f_disp, threshold=threshold, msg=msg)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["auth"] = True
            return redirect(url_for("index"))
        else:
            error = "كلمة المرور غير صحيحة!"
    return render_template_string(LOGIN_HTML, error=error)

@app.route("/logout")
def logout():
    session.pop("auth", None)
    return redirect(url_for("login"))

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
                    limit_val = get_db_value("threshold_limit") or "300000"
                    
                    t_str = f"{t_bal:,.0f} دينار" if isinstance(t_bal, int) else t_bal
                    f_str = f"{f_bal:,.0f} دينار" if isinstance(f_bal, int) else f_bal
                    
                    reply = f"📊 **الرصيد الحالي للأنظمة:**\n"
                    reply += f"- الأبراج: {t_str}\n"
                    reply += f"- FTTH: {f_str}\n"
                    reply += f"⚙️ حد التحذير: {int(limit_val):,.0f} دينار"
                    
                    send_fb_message(sender_id, reply)

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
