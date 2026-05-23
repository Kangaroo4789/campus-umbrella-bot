"""
Campus Shared Umbrella LINE Bot — v4 (Ultimate DSRM Instantiation)
Features:
  • Fixed .env.txt loading and LINE v3 image download bug.
  • Added 'My Status' & 'Task Board' Flex Messages.
  • Registration FSM upgraded: Name -> Department -> ID Card -> Optimistic Release (Idle).
  • Repair FSM added: 報修 -> Select Station -> Upload Photo -> DB.
  • Web Dashboard Expanded:
    - Section D: Registration Verification (with duplicate name warning).
    - Section E: Repair Requests Management.
"""

import os
import re
import sqlite3
import threading
import time
from datetime import datetime

import cv2
from flask import (
    Flask, abort, redirect, render_template_string,
    request, session, url_for,
)

# 👇 1. 環境變數讀取修復
from dotenv import load_dotenv
load_dotenv(".env.txt")

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    FlexContainer,
    FlexMessage,
    MessagingApi,
    PushMessageRequest,
    QuickReply,
    QuickReplyItem,
    MessageAction,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    ImageMessageContent,
    MessageEvent,
    TextMessageContent,
)

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "YOUR_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET       = os.environ.get("LINE_CHANNEL_SECRET",       "YOUR_CHANNEL_SECRET")
ADMIN_PASSWORD       = os.environ.get("ADMIN_PASSWORD",            "nttu007")

UPLOAD_DIR      = "uploads"
OVERDUE_SECONDS = 120
ARUCO_DICT_ID   = cv2.aruco.DICT_4X4_50

os.makedirs(UPLOAD_DIR, exist_ok=True)

app            = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "umbrella-secret-key-change-me")
configuration  = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler        = WebhookHandler(CHANNEL_SECRET)


DB_PATH = "umbrella_v4.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# 👇 2. 資料庫結構擴充 (加入系所、審核狀態與報修表格)
def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id          TEXT PRIMARY KEY,
            status           TEXT    DEFAULT 'unregistered',
            credit           INTEGER DEFAULT 100,
            real_name        TEXT,
            department       TEXT,
            is_verified      INTEGER DEFAULT 0,
            student_id_path  TEXT,
            umbrella_id      TEXT,
            borrow_time      TEXT,
            borrow_station   TEXT,
            return_station   TEXT
        );
        CREATE TABLE IF NOT EXISTS stations (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT UNIQUE,
            umbrella_count INTEGER DEFAULT 0,
            image_url      TEXT
        );
        CREATE TABLE IF NOT EXISTS repairs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        TEXT,
            station        TEXT,
            photo_path     TEXT,
            status         TEXT DEFAULT 'pending',
            report_time    TEXT
        );
        """)
        if conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO stations (name, umbrella_count, image_url) VALUES (?,?,?)",
                [
                    ("圖書館",   8, "https://example.com/library.jpg"),
                    ("活動中心", 5, "https://example.com/activity.jpg"),
                    ("學生宿舍", 3, "https://example.com/dorm.jpg"),
                ],
            )

def get_user(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()

def upsert_user(user_id, **kwargs):
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone() is None:
            conn.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        if kwargs:
            sets   = ", ".join(f"{k}=?" for k in kwargs)
            values = list(kwargs.values()) + [user_id]
            conn.execute(f"UPDATE users SET {sets} WHERE user_id=?", values)

def get_stations():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM stations ORDER BY id").fetchall()

def adjust_station_count(station_name, delta):
    with get_conn() as conn:
        conn.execute(
            "UPDATE stations SET umbrella_count = MAX(0, umbrella_count + ?) WHERE name=?",
            (delta, station_name),
        )

def reply(reply_token, text, quick_reply=None):
    msg = TextMessage(text=text, quick_reply=quick_reply)
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[msg])
        )

def push(user_id, text):
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).push_message(
            PushMessageRequest(to=user_id, messages=[TextMessage(text=text)])
        )

def reply_flex(reply_token, alt_text, contents):
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[FlexMessage(alt_text=alt_text, contents=FlexContainer.from_dict(contents))],
            )
        )

def station_quick_reply():
    items = [
        QuickReplyItem(action=MessageAction(label=s["name"][:20], text=s["name"]))
        for s in get_stations()
    ]
    return QuickReply(items=items)

def decode_aruco(image_path):
    img = cv2.imread(image_path)
    if img is None: return None
    gray     = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    adict    = cv2.aruco.getPredefinedDictionary(ARUCO_DICT_ID)
    detector = cv2.aruco.ArucoDetector(adict, cv2.aruco.DetectorParameters())
    _, ids, _ = detector.detectMarkers(gray)
    if ids is not None and len(ids) > 0:
        return str(int(ids[0][0])).zfill(3)
    return None

def verify_return_image(image_path, user_id, return_station):
    try:
        from ultralytics import YOLO
        model   = YOLO("yolov8n.pt")
        results = model(image_path)
        umbrella_detected = any("umbrella" in model.names[int(c)].lower() for r in results for c in r.boxes.cls.tolist())
        if umbrella_detected:
            adjust_station_count(return_station, +1)
        else:
            with get_conn() as conn:
                conn.execute("UPDATE users SET credit=MAX(0,credit-10) WHERE user_id=?", (user_id,))
            push(user_id, "⚠️ AI 未在全景照片中偵測到雨傘，已扣除 10 信用分。\n請確認您已將雨傘放回黃框區域並拍攝完整照片。")
    except Exception as e:
        app.logger.error(f"[YOLO] {e}")

def overdue_scheduler():
    while True:
        time.sleep(60)
        try:
            now = datetime.now()
            with get_conn() as conn:
                rows = conn.execute("SELECT user_id, borrow_time FROM users WHERE status='borrowing' AND borrow_time IS NOT NULL AND borrow_time!=''").fetchall()
            for row in rows:
                try:
                    borrow_dt = datetime.strptime(row["borrow_time"], "%Y-%m-%d %H:%M:%S")
                except ValueError: continue
                if (now - borrow_dt).total_seconds() > OVERDUE_SECONDS:
                    with get_conn() as conn:
                        conn.execute("UPDATE users SET credit=MAX(0,credit-5), borrow_time=? WHERE user_id=?", (now.strftime("%Y-%m-%d %H:%M:%S"), row["user_id"]))
                    push(row["user_id"], "⏰ 您的雨傘已超時未還！已自動扣除 5 信用分。\n請盡快歸還，避免繼續扣分。")
        except Exception as e:
            app.logger.error(f"[Scheduler] {e}")

# 👇 3. 圖片下載崩潰修復
def download_image(message_id, user_id):
    image_path = os.path.join(UPLOAD_DIR, f"{user_id}_{message_id}.jpg")
    with ApiClient(configuration) as api_client:
        from linebot.v3.messaging import MessagingApiBlob
        blob = MessagingApiBlob(api_client)
        content = blob.get_message_content(message_id=message_id)
        with open(image_path, "wb") as f:
            f.write(content) # 直接寫入，修正 v3 錯誤
    return image_path

# ─────────────────────────────────────────────────────────────────────────────
# HTML templates (Dashboard 擴充區塊 D 與 E)
# ─────────────────────────────────────────────────────────────────────────────
LOGIN_HTML = """
<!doctype html>
<html lang="zh-TW">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>管理員登入 — 校園共享雨傘</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
  <style>body{background:linear-gradient(135deg,#1a3c5e 0%,#2980b9 100%);min-height:100vh;} .login-card{max-width:400px;border-radius:1rem;} .umbrella-icon{font-size:3rem;color:#2980b9;}</style>
</head>
<body class="d-flex align-items-center justify-content-center">
  <div class="card shadow-lg p-4 login-card w-100 mx-3">
    <div class="text-center mb-3"><i class="bi bi-umbrella-fill umbrella-icon"></i><h4 class="mt-2 fw-bold">校園共享雨傘</h4></div>
    {% if error %}<div class="alert alert-danger py-2">{{ error }}</div>{% endif %}
    <form method="post">
      <div class="mb-3">
        <label class="form-label fw-semibold">管理員密碼</label>
        <div class="input-group">
          <span class="input-group-text"><i class="bi bi-lock-fill"></i></span>
          <input type="password" name="password" class="form-control" placeholder="請輸入密碼" autofocus required>
        </div>
      </div>
      <button type="submit" class="btn btn-primary w-100 fw-bold">登入</button>
    </form>
  </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!doctype html>
<html lang="zh-TW">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>管理後台 — 校園共享雨傘</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
  <style>
    body{background-color:#f0f4f8;} .section-card{border-radius:.75rem;border:none;box-shadow:0 2px 12px rgba(0,0,0,.08);}
    .section-header{border-radius:.75rem .75rem 0 0;padding:1rem 1.25rem;color:#fff;font-weight:600;}
    .header-a{background:linear-gradient(90deg,#1a6e3c,#27ae60);} .header-b{background:linear-gradient(90deg,#154776,#2980b9);}
    .header-c{background:linear-gradient(90deg,#6b2d00,#d35400);} .header-d{background:linear-gradient(90deg,#8e44ad,#9b59b6);}
    .header-e{background:linear-gradient(90deg,#c0392b,#e74c3c);}
    .flash-msg{position:fixed;top:70px;right:20px;z-index:9999;min-width:280px;}
  </style>
</head>
<body>

<nav class="navbar navbar-dark bg-dark px-3 sticky-top">
  <span class="navbar-brand"><i class="bi bi-umbrella-fill me-2"></i>共享雨傘管理後台</span>
  <div class="d-flex align-items-center gap-3">
    <a href="{{ url_for('admin_logout') }}" class="btn btn-outline-light btn-sm">登出</a>
  </div>
</nav>

{% if flash %}
<div class="flash-msg alert alert-{{ flash.type }} alert-dismissible shadow fade show">
  {{ flash.msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
</div>
{% endif %}

<div class="container-lg py-4">

  <div class="card section-card mb-4">
    <div class="section-header header-a">Section A：校園雨傘地圖</div>
    <div class="card-body">
      <div class="row g-3">
        {% for s in stations %}
        <div class="col-sm-6 col-lg-4">
          <div class="p-3 border rounded-3 bg-white">
            <span class="fw-semibold">{{ s.name }}</span> : <span class="badge bg-success">{{ s.umbrella_count }} 把</span>
          </div>
        </div>
        {% endfor %}
      </div>
    </div>
  </div>

  <div class="card section-card mb-4">
    <div class="section-header header-d">Section D：註冊審核清單 <span class="badge bg-white text-dark">{{ pending_users|length }} 筆待審核</span></div>
    <div class="card-body p-0">
      <table class="table table-hover mb-0 align-middle">
        <thead class="table-light"><tr><th>姓名</th><th>系所</th><th>學生證</th><th>操作</th></tr></thead>
        <tbody>
          {% for u in pending_users %}
          <tr>
            <td>
                {{ u.real_name }} 
                {% if u.real_name in duplicate_names %}<span class="badge bg-danger ms-1">⚠️ 重複姓名</span>{% endif %}
            </td>
            <td>{{ u.department }}</td>
            <td><a href="/{{ u.student_id_path }}" target="_blank" class="btn btn-sm btn-outline-secondary">查看照片</a></td>
            <td>
              <form method="post" action="{{ url_for('admin_verify') }}" class="d-inline">
                <input type="hidden" name="user_id" value="{{ u.user_id }}"><input type="hidden" name="action" value="approve">
                <button class="btn btn-success btn-sm">✅ 通過</button>
              </form>
              <form method="post" action="{{ url_for('admin_verify') }}" class="d-inline">
                <input type="hidden" name="user_id" value="{{ u.user_id }}"><input type="hidden" name="action" value="reject">
                <button class="btn btn-danger btn-sm">❌ 駁回</button>
              </form>
            </td>
          </tr>
          {% else %}
          <tr><td colspan="4" class="text-center text-muted py-3">目前無待審核資料</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <div class="card section-card mb-4">
    <div class="section-header header-e">Section E：雨傘報修清單 <span class="badge bg-white text-dark">{{ pending_repairs|length }} 筆待處理</span></div>
    <div class="card-body p-0">
      <table class="table table-hover mb-0 align-middle">
        <thead class="table-light"><tr><th>回報時間</th><th>站點</th><th>損壞照片</th><th>操作</th></tr></thead>
        <tbody>
          {% for r in pending_repairs %}
          <tr>
            <td>{{ r.report_time }}</td>
            <td>{{ r.station }}</td>
            <td><a href="/{{ r.photo_path }}" target="_blank" class="btn btn-sm btn-outline-secondary">查看照片</a></td>
            <td>
              <form method="post" action="{{ url_for('admin_repair_resolve') }}">
                <input type="hidden" name="repair_id" value="{{ r.id }}">
                <button class="btn btn-success btn-sm">✅ 標記已處理</button>
              </form>
            </td>
          </tr>
          {% else %}
          <tr><td colspan="4" class="text-center text-muted py-3">目前無待處理報修</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <div class="card section-card mb-4">
    <div class="section-header header-b">Section B：全體使用者與信用管理</div>
    <div class="card-body p-0">
      <table class="table table-hover mb-0 align-middle">
        <thead class="table-light"><tr><th>姓名</th><th>狀態</th><th>信用分</th><th>操作</th></tr></thead>
        <tbody>
          {% for u in users %}
          <tr>
            <td>{{ u.real_name or '未知' }}</td>
            <td>{{ u.status }}</td>
            <td>{{ u.credit }}</td>
            <td>
              <form method="post" action="{{ url_for('admin_credit') }}" class="d-inline">
                <input type="hidden" name="user_id" value="{{ u.user_id }}"><input type="hidden" name="delta" value="-30"><button class="btn btn-danger btn-sm">扣 30</button>
              </form>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────────────────────
# Dashboard Routes
# ─────────────────────────────────────────────────────────────────────────────
def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"): return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        error = "密碼錯誤，請再試一次。"
    return render_template_string(LOGIN_HTML, error=error)

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    with get_conn() as conn:
        stations = conn.execute("SELECT * FROM stations ORDER BY id").fetchall()
        users    = conn.execute("SELECT * FROM users ORDER BY real_name").fetchall()
        pending_users = conn.execute("SELECT * FROM users WHERE is_verified=0 AND real_name IS NOT NULL").fetchall()
        pending_repairs = conn.execute("SELECT * FROM repairs WHERE status='pending' ORDER BY report_time DESC").fetchall()
        
        # 找重複姓名
        name_counts = {}
        for u in users:
            if u["real_name"]: name_counts[u["real_name"]] = name_counts.get(u["real_name"], 0) + 1
        duplicate_names = [name for name, count in name_counts.items() if count > 1]

    flash = session.pop("flash", None)
    
    # 👇 1. 補上抓取現在時間的程式碼
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
    
    return render_template_string(
        DASHBOARD_HTML,
        stations=stations, users=users, pending_users=pending_users, 
        pending_repairs=pending_repairs, duplicate_names=duplicate_names, flash=flash,
        now=now_str # 👇 2. 記得把 now 傳進網頁裡！
    )
@app.route("/admin/verify", methods=["POST"])
@admin_required
def admin_verify():
    user_id = request.form.get("user_id")
    action = request.form.get("action")
    if action == "approve":
        with get_conn() as conn:
            conn.execute("UPDATE users SET is_verified=1 WHERE user_id=?", (user_id,))
        push(user_id, "✅ 您的註冊資料已通過人工審核！")
    else:
        with get_conn() as conn:
            conn.execute("UPDATE users SET is_verified=-1, credit=0 WHERE user_id=?", (user_id,))
        push(user_id, "❌ 您的註冊資料審核不通過，請聯繫系辦公室。")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/repair_resolve", methods=["POST"])
@admin_required
def admin_repair_resolve():
    repair_id = request.form.get("repair_id")
    with get_conn() as conn:
        conn.execute("UPDATE repairs SET status='resolved' WHERE id=?", (repair_id,))
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/credit", methods=["POST"])
@admin_required
def admin_credit():
    user_id, delta = request.form.get("user_id"), int(request.form.get("delta", 0))
    with get_conn() as conn:
        conn.execute("UPDATE users SET credit=MAX(0, credit + ?) WHERE user_id=?", (delta, user_id))
    push(user_id, f"📋 信用分數異動通知：已扣除 {abs(delta)} 分。")
    return redirect(url_for("admin_dashboard"))

# 提供圖片靜態訪問
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    from flask import send_from_directory
    return send_from_directory(UPLOAD_DIR, filename)

@app.route("/")
def index(): return redirect(url_for("admin_login"))

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body      = request.get_data(as_text=True)
    try: handler.handle(body, signature)
    except InvalidSignatureError: abort(400)
    return "OK"

# ─────────────────────────────────────────────────────────────────────────────
# LINE Flex Messages & Handlers
# ─────────────────────────────────────────────────────────────────────────────
def send_umbrella_map(reply_token):
    stations = get_stations()
    rows = []
    for s in stations:
        count, color = s["umbrella_count"], "#27AE60" if s["umbrella_count"] > 0 else "#E74C3C"
        avail_text = f"{count} 把可借" if count > 0 else "暫無庫存"
        rows.append({
            "type":"box","layout":"horizontal","paddingAll":"10px",
            "contents":[
                {"type":"box","layout":"vertical","flex":4,"contents":[
                    {"type":"text","text":s["name"],"weight":"bold","size":"md"},
                    {"type":"text","text":avail_text,"size":"sm","color":color,"weight":"bold"},
                ]},
                {"type":"box","layout":"vertical","flex":1,"justifyContent":"center",
                 "contents":[{"type":"text","text":"☂" if count>0 else "✖","size":"xl","color":color,"align":"end"}]},
            ],
        })
    flex = {
        "type":"bubble","size":"mega",
        "header":{"type":"box","layout":"vertical","backgroundColor":"#1A3C5E","paddingAll":"16px",
                  "contents":[{"type":"text","text":"☂ 雨傘地圖","color":"#FFFFFF","weight":"bold","size":"xl"}]},
        "body":{"type":"box","layout":"vertical","spacing":"none","contents":rows}
    }
    reply_flex(reply_token, "校園雨傘地圖", flex)

# 👇 4. 補回我的狀態 Flex Message
def send_my_status(reply_token, user):
    credit, umbrella = user["credit"], user["umbrella_id"] or "無"
    status_text = "☂️ 借用中" if user["status"] == "borrowing" else "✅ 閒置中"
    flex = {
        "type": "bubble",
        "body": {
            "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                {"type": "text", "text": f"👤 {user['real_name'] or '未知'} 的帳戶", "weight": "bold", "size": "xl"},
                {"type": "text", "text": f"💳 信用分：{credit} 分", "color": "#27AE60" if credit >= 60 else "#E74C3C"},
                {"type": "text", "text": f"📊 系統狀態：{status_text}"},
                {"type": "text", "text": f"🔍 綁定傘號：{umbrella}"}
            ]
        }
    }
    reply_flex(reply_token, "我的狀態", flex)

def handle_text(event, text):
    reply_token, user_id = event.reply_token, event.source.user_id
    upsert_user(user_id)
    user, status = get_user(user_id), get_user(user_id)["status"]

    if text in ("地圖", "map", "雨傘地圖"):
        send_umbrella_map(reply_token); return
    if text in ("狀態", "我的狀態", "個人資料"):
        send_my_status(reply_token, user); return
    
    # 👇 5. 任務看板
    if text in ("任務", "任務看板"):
        reply(reply_token, "🚨 【動態任務看板】\n當前需求：將傘從「學生宿舍」移至「圖書館」。\n獎勵：還傘驗證成功可獲 +15 信用分！"); return

    if status == "unregistered":
        if text in ("註冊", "register"):
            upsert_user(user_id, status="wait_name")
            reply(reply_token, "歡迎使用校園共享雨傘！\n請輸入您的真實姓名：")
        return

    if status == "wait_name":
        upsert_user(user_id, real_name=text, status="wait_department")
        reply(reply_token, f"謝謝 {text}！\n請接著輸入您的「系所」（例如：資管系）：")
        return

    # 👇 6. 註冊 FSM 新增系所
    if status == "wait_department":
        upsert_user(user_id, department=text, status="wait_id_card")
        reply(reply_token, f"系所已記錄為 {text}。\n最後一步，請上傳您的「學生證照片」以供後台備查：")
        return

    if status == "idle":
        if text in ("借傘", "borrow"):
            if user["credit"] < 60: reply(reply_token, "⚠️ 信用低於 60 分，無法借傘。")
            else:
                upsert_user(user_id, status="wait_borrow_station")
                reply(reply_token, "📍 請選擇借傘站點：", quick_reply=station_quick_reply())
        elif text in ("還傘", "return"): reply(reply_token, "您目前沒有借用中的雨傘。")
        # 👇 7. 報修起手式
        elif text == "報修":
            upsert_user(user_id, status="wait_repair_station")
            reply(reply_token, "🔧 請問發生損壞的是哪個站點？", quick_reply=station_quick_reply())
        return

    # 報修 FSM
    if status == "wait_repair_station":
        upsert_user(user_id, borrow_station=text, status="wait_repair_photo") # 借用 borrow_station 欄位暫存
        reply(reply_token, f"已記錄站點 {text}。請拍攝「損壞的雨傘或傘架狀況」上傳：")
        return

    if status == "wait_borrow_station":
        upsert_user(user_id, borrow_station=text, status="wait_borrow_aruco")
        reply(reply_token, f"📍 已選擇：{text}\n📸 請拍攝雨傘握柄黑白碼：")
        return

    if status == "borrowing":
        if text in ("還傘", "return"):
            upsert_user(user_id, status="wait_return_station")
            reply(reply_token, "📍 請選擇還傘站點：", quick_reply=station_quick_reply())
        return

    if status == "wait_return_station":
        upsert_user(user_id, return_station=text, status="wait_return_aruco")
        reply(reply_token, f"📍 站點：{text}\n📸 第 1 步：拍傘柄黑白碼確認傘號。")
        return

    reply(reply_token, "請依據系統提示操作或上傳照片。")

def handle_image(event):
    reply_token, user_id, message_id = event.reply_token, event.source.user_id, event.message.id
    upsert_user(user_id)
    user, status = get_user(user_id), get_user(user_id)["status"]
    image_path = download_image(message_id, user_id)

    # 👇 8. 註冊完成：先放行機制
    if status == "wait_id_card":
        upsert_user(user_id, student_id_path=image_path, status="idle", is_verified=0)
        reply(reply_token, "✅ 註冊資料已送出審核！\n(系統採信任先放行機制，您現在已可點選「借傘」開始使用 🎉)")
        return

    # 👇 9. 報修完成
    if status == "wait_repair_photo":
        station = user["borrow_station"] or "未知"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_conn() as conn:
            conn.execute("INSERT INTO repairs (user_id, station, photo_path, report_time) VALUES (?,?,?,?)",
                         (user_id, station, image_path, now_str))
        upsert_user(user_id, status="idle")
        reply(reply_token, "✅ 報修已成功回報至管理員後台，感謝您的熱心協助！")
        return

    if status == "wait_borrow_aruco":
        aruco_id = decode_aruco(image_path)
        if not aruco_id: reply(reply_token, "❌ 未能辨識，請重拍。"); return
        now_str, station = datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user["borrow_station"]
        upsert_user(user_id, umbrella_id=aruco_id, borrow_time=now_str, status="borrowing")
        adjust_station_count(station, -1)
        reply(reply_token, f"✅ 成功借出 #{aruco_id}！\n請於 3 天內歸還。")
        return

    if status == "wait_return_aruco":
        aruco_id = decode_aruco(image_path)
        if not aruco_id or aruco_id != user["umbrella_id"]:
            reply(reply_token, "❌ 辨識失敗或傘號不符。"); return
        upsert_user(user_id, status="wait_return_yolo")
        reply(reply_token, f"✅ 傘號 #{aruco_id} 正確！\n📸 第 2 步：請退後拍攝「傘放回傘架黃線區」的全景照。")
        return

    if status == "wait_return_yolo":
        return_station = user["return_station"]
        upsert_user(user_id, status="idle", umbrella_id=None, borrow_time=None, borrow_station=None, return_station=None)
        reply(reply_token, "✅ 初步歸還完成，計時停止。\n背景 AI 驗證中☂")
        threading.Thread(target=verify_return_image, args=(image_path, user_id, return_station), daemon=True).start()
        return

@handler.add(MessageEvent, message=TextMessageContent)
def on_text(event): handle_text(event, event.message.text.strip())

@handler.add(MessageEvent, message=ImageMessageContent)
def on_image(event): handle_image(event)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=overdue_scheduler, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)