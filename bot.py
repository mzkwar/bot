import os
import sqlite3
import threading
import time
import urllib.request
import requests
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from cryptography.fernet import Fernet

app = Flask(__name__)

# إعدادات فيسبوك أساسية
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_secure_verify_token")
ADMIN_FB_ID = os.getenv("ADMIN_FB_ID")

# مفتاح تشفير تلقائي لحماية بيانات الاعتماد داخل قاعدة البيانات
ENCRYPTION_KEY = Fernet.generate_key()
cipher = Fernet(ENCRYPTION_KEY)

# --- إعداد قاعدة البيانات المحلية ---
def init_db():
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS groups (id TEXT PRIMARY KEY)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    
    # حد التحذير الافتراضي للأنظمة (300 ألف)
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

# --- إرسال الرسائل عبر Facebook Graph API ---
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

# --- فك تشفير بيانات الاعتماد لأي نظام ---
def get_credentials(system_prefix):
    encrypted_user = get_setting(f"{system_prefix}_user")
    encrypted_pass = get_setting(f"{system_prefix}_pass")
    
    if not encrypted_user or not encrypted_pass:
        return None, None
        
    username = cipher.decrypt(encrypted_user.encode()).decode()
    password = cipher.decrypt(encrypted_pass.encode()).decode()
    return username, password

# --- 1. دالة جلب رصيد الأبراج (إيرثلنك) ---
def get_towers_balance():
    username, password = get_credentials("towers")
    if not username or not password:
        return None

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(options=options)
    try:
        driver.get("https://admin.earthlink.iq/Home.aspx")
        time.sleep(2)
        
        driver.find_element(By.ID, "Login1_UserName").send_keys(username)
        driver.find_element(By.ID, "Login1_Password").send_keys(password)
        driver.find_element(By.ID, "Login1_LoginButton").click()
        
        time.sleep(5)
        
        balance_element = driver.find_element(By.ID, "ctl00_ctl00_HeaderTopNavControl_balanacelabel")
        balance_text = balance_element.text.strip()
        return int(''.join(filter(str.isdigit, balance_text)))
    except Exception as e:
        print(f"Error fetching towers balance: {e}")
        return None
    finally:
        driver.quit()

# --- 2. دالة جلب رصيد الـ FTTH ---
def get_ftth_balance():
    username, password = get_credentials("ftth")
    if not username or not password:
        return None

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(options=options)
    try:
        driver.get("https://admin.ftth.iq")
        time.sleep(2)
        
        driver.find_element(By.ID, "Login1_UserName").send_keys(username)
        driver.find_element(By.ID, "Login1_Password").send_keys(password)
        driver.find_element(By.ID, "Login1_LoginButton").click()
        
        time.sleep(5)
        
        balance_element = driver.find_element(By.ID, "ctl00_ctl00_HeaderTopNavControl_balanacelabel")
        return int(''.join(filter(str.isdigit, balance_element.text.strip())))
    except Exception as e:
        print(f"Error fetching FTTH balance: {e}")
        return None
    finally:
        driver.quit()

# --- المراقب الدوري المزدوج في الخلفية ---
def background_monitor():
    while True:
        try:
            limit_val = get_setting("threshold_limit")
            current_threshold = int(limit_val) if limit_val else 300000
            
            # فحص الأبراج
            t_balance = get_towers_balance()
            if t_balance is not None and t_balance <= current_threshold:
                alert_msg = f"⚠️ تنبيه نفاذ رصيد [الأبراج]!\nرصيدك الحالي: {t_balance:,.0f} دينار فقط.\nيرجى إعادة التعبئة."
                broadcast_alert(alert_msg)

            # فحص FTTH
            f_balance = get_ftth_balance()
            if f_balance is not None and f_balance <= current_threshold:
                alert_msg = f"⚠️ تنبيه نفاذ رصيد [FTTH]!\nرصيدك الحالي: {f_balance:,.0f} دينار فقط.\nيرجى إعادة التعبئة."
                broadcast_alert(alert_msg)
                    
        except Exception as e:
            print(f"Error in background monitor: {e}")
            
        time.sleep(21600) # فحص كل 6 ساعات

def broadcast_alert(msg):
    users = db_execute("SELECT id FROM users", fetch=True)
    for user in users:
        send_fb_message(user[0], msg)
    groups = db_execute("SELECT id FROM groups", fetch=True)
    for group in groups:
        send_fb_message(group[0], msg)

threading.Thread(target=background_monitor, daemon=True).start()

# --- خيط الإيقاظ الذاتي (Self-Ping) لمنع السكون على Render ---
def self_ping():
    while True:
        time.sleep(300)
        app_url = os.getenv("RENDER_EXTERNAL_URL")
        if app_url:
            try:
                urllib.request.urlopen(app_url)
                print("Self-ping sent successfully!")
            except Exception as e:
                print(f"Self-ping error: {e}")

if os.getenv("RENDER_EXTERNAL_URL"):
    threading.Thread(target=self_ping, daemon=True).start()

# --- مستقبل رسائل فيسبوك (Webhook) ---
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
                recipient_id = messaging.get("recipient", {}).get("id")
                message_text = messaging.get("message", {}).get("text", "").strip()
                
                if not message_text:
                    continue
                
                is_private_chat = "message" in messaging and "is_echo" not in messaging and sender_id != recipient_id
                
                # أمر معرف الـ ID
                if message_text.lower() == "id":
                    send_fb_message(sender_id, f"معرفك الشخصي هو: {sender_id}")
                    continue

                # فحص إذا كان المدير في وضع إدخال بيانات معلقة
                current_state = get_setting(f"state_{sender_id}")
                
                if sender_id == ADMIN_FB_ID and is_private_chat and current_state:
                    lines = message_text.splitlines()
                    if len(lines) >= 2:
                        u, p = lines[0].strip(), lines[1].strip()
                        if current_state == "waiting_towers":
                            set_setting("towers_user", cipher.encrypt(u.encode()).decode())
                            set_setting("towers_pass", cipher.encrypt(p.encode()).decode())
                            send_fb_message(sender_id, "✅ تم حفظ وتشفير حساب الأبراج بنجاح!")
                        elif current_state == "waiting_ftth":
                            set_setting("ftth_user", cipher.encrypt(u.encode()).decode())
                            set_setting("ftth_pass", cipher.encrypt(p.encode()).decode())
                            send_fb_message(sender_id, "✅ تم حفظ وتشفير حساب FTTH بنجاح!")
                        
                        # مسح الحالة بعد الحفظ
                        set_setting(f"state_{sender_id}", "")
                        continue
                    else:
                        send_fb_message(sender_id, "❌ يرجى إرسال اليوزر وكلمة المرور في سطرين منفصلين كما طلبنا.")
                        continue

                # 1. الاستجابة لكلمة "رصيد"
                if message_text.lower() in ["رصيد", "الرصيد", "balance"]:
                    t_bal = get_towers_balance()
                    f_bal = get_ftth_balance()
                    limit_val = get_setting("threshold_limit")
                    current_threshold = int(limit_val) if limit_val else 300000
                    
                    reply = "📊 **الرصيد الحالي للأنظمة:**\n"
                    reply += f"- الأبراج: {t_bal:,.0f} دينار\n" if t_bal is not None else "- الأبراج: ⚠️ غير مُعرّف\n"
                    reply += f"- FTTH: {f_bal:,.0f} دينار\n" if f_bal is not None else "- FTTH: ⚠️ غير مُعرّف\n"
                    reply += f"⚙️ حد التحذير: {current_threshold:,.0f} دينار"
                    
                    send_fb_message(sender_id, reply)
                
                # 2. أوامر الإدارة وتفعيل الحالات الخاصة
                elif sender_id == ADMIN_FB_ID and is_private_chat:
                    if message_text.lower() == "تعيين الأبراج":
                        set_setting(f"state_{sender_id}", "waiting_towers")
                        send_fb_message(sender_id, "يرجى إرسال يوزر وكلمة السر بهذا الشكل:\nuser\npass")
                    elif message_text.lower() == "تعيين ftth":
                        set_setting(f"state_{sender_id}", "waiting_ftth")
                        send_fb_message(sender_id, "يرجى إرسال يوزر وكلمة السر بهذا الشكل:\nuser\npass")
                    else:
                        parts = message_text.split()
                        if not parts:
                            continue
                        
                        if parts[0] == "تعيين" and parts[1] == "الحد" and len(parts) > 2:
                            try:
                                new_limit = int(parts[2])
                                set_setting("threshold_limit", str(new_limit))
                                send_fb_message(sender_id, f"✅ تم تحديث حد التحذير ليصبح: {new_limit:,.0f} دينار")
                            except ValueError:
                                send_fb_message(sender_id, "❌ خطأ: يرجى إرسال رقم صحيح. مثال: `تعيين الحد 300000`")
                                
                        elif len(parts) >= 2 and f"{parts[0]} {parts[1]}" == "إضافة مجموعة":
                            db_execute("INSERT OR IGNORE INTO groups (id) VALUES (?)", (parts[2],))
                            send_fb_message(sender_id, f"✅ تمت إضافة المجموعة برقم: {parts[2]}")
                            
                        elif len(parts) >= 2 and f"{parts[0]} {parts[1]}" == "حذف مجموعة":
                            db_execute("DELETE FROM groups WHERE id = ?", (parts[2],))
                            send_fb_message(sender_id, f"🗑️ تم حذف المجموعة برقم: {parts[2]}")
                            
                        elif message_text.lower() == "عرض المجموعات":
                            groups = db_execute("SELECT id FROM groups", fetch=True)
                            g_list = "\n".join([g[0] for g in groups]) or "لا توجد مجموعات مضافة."
                            send_fb_message(sender_id, f"📋 المجموعات المضافة:\n{g_list}")

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
