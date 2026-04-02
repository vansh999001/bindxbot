import requests
import json
import hashlib
import os
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ==================== CONFIG ====================
BOT_TOKEN = "8482216839:AAE9zgd6rBNDsOmMn9JB7uBUwFpfEIim0w0"
OWNER_USERNAME = "@sexy_boyhere"
BASE_URL = "https://100067.connect.garena.com"
HEADERS = {
    "User-Agent": "GarenaMSDK/4.0.39 (M2007J22C; Android 10; en; US;)",
    "Content-Type": "application/x-www-form-urlencoded",
}
APP_ID = "100067"
REFRESH_TOKEN = "1380dcb63ab3a077dc05bdf0b25ba4497c403a5b4eae96d7203010eafa6c83a8"

# ==================== DATABASE ====================
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    approved INTEGER DEFAULT 0,
    request_date TEXT,
    approved_date TEXT
)''')
conn.commit()

user_sessions = {}
OWNER_ID = None

# ==================== DB FUNCTIONS ====================
def add_user(user_id, username, first_name):
    cursor.execute('INSERT OR IGNORE INTO users VALUES (?,?,?,0,?,?)',
                   (user_id, username, first_name, datetime.now().isoformat(), None))
    conn.commit()

def approve_user(user_id):
    cursor.execute('UPDATE users SET approved=1, approved_date=? WHERE user_id=?',
                   (datetime.now().isoformat(), user_id))
    conn.commit()

def is_approved(user_id):
    cursor.execute('SELECT approved FROM users WHERE user_id=?', (user_id,))
    r = cursor.fetchone()
    return r and r[0] == 1

def get_pending_users():
    cursor.execute('SELECT user_id, username, first_name, request_date FROM users WHERE approved=0')
    return cursor.fetchall()

def sha256_hash(s):
    return hashlib.sha256(s.encode()).hexdigest()

# ==================== API CALLS ====================
def api_call(endpoint, token=None, data=None, method='GET'):
    url = f"{BASE_URL}{endpoint}"
    params = {"app_id": APP_ID}
    if token:
        params["access_token"] = token
    if method == 'GET':
        return requests.get(url, headers=HEADERS, params=params)
    return requests.post(url, headers=HEADERS, params=params, data=data)

def get_bind_info(token): return api_call('/game/account_security/bind:get_bind_info', token)
def send_otp(token, email): return api_call('/game/account_security/bind:send_otp', token, {"email": email, "locale": "en_PK", "region": "PK"}, 'POST')
def verify_otp(token, email, otp): return api_call('/game/account_security/bind:verify_otp', token, {"email": email, "otp": otp}, 'POST')
def verify_identity_with_otp(token, email, otp): return api_call('/game/account_security/bind:verify_identity', token, {"email": email, "otp": otp}, 'POST')
def verify_identity_with_security_code(token, code): return api_call('/game/account_security/bind:verify_identity', token, {"secondary_password": sha256_hash(code)}, 'POST')
def create_rebind_request(token, identity_token, verifier_token, new_email): return api_call('/game/account_security/bind:create_rebind_request', token, {"identity_token": identity_token, "verifier_token": verifier_token, "email": new_email}, 'POST')
def cancel_request(token): return api_call('/game/account_security/bind:cancel_request', token, {}, 'POST')
def unbind_identity(token, identity_token): return api_call('/game/account_security/bind:unbind_identity', token, {"identity_token": identity_token}, 'POST')
def get_platforms(token): return api_call('/bind/app/platform/info/get', token)

def get_user_info(token):
    try:
        r = requests.get("https://prod-api.reward.ff.garena.com/redemption/api/auth/inspect_token/",
                         headers={"access-token": token, "User-Agent": "Mozilla/5.0"}, timeout=10)
        return r.json() if r.status_code == 200 else None
    except: return None

def revoke_token(token):
    try:
        r = requests.get("https://100067.connect.garena.com/oauth/logout",
                         params={"access_token": token, "refresh_token": REFRESH_TOKEN}, timeout=10)
        return r.status_code == 200 and "error" not in r.text.lower()
    except: return False

# ==================== BOT HANDLERS ====================
async def start(update, context):
    global OWNER_ID
    user = update.effective_user
    if user.username and user.username.lower() == 'sexy_boyhere':
        OWNER_ID = user.id
        add_user(user.id, user.username, user.first_name)
        approve_user(user.id)
        await update.message.reply_text(f"👑 Welcome Owner!\nID: `{user.id}`\nUse /owner", parse_mode='Markdown')
        return
    if not is_approved(user.id):
        add_user(user.id, user.username, user.first_name)
        kb = [[InlineKeyboardButton("📞 Contact Owner", url="https://t.me/sexy_boyhere")]]
        await update.message.reply_text("❌ Access Denied!\nContact @sexy_boyhere", reply_markup=InlineKeyboardMarkup(kb))
        if OWNER_ID:
            await context.bot.send_message(OWNER_ID, f"🆕 Request from {user.first_name}\nID: `{user.id}`", parse_mode='Markdown')
        return
    kb = [
        [InlineKeyboardButton("📧 Bind Change", callback_data='bc')],
        [InlineKeyboardButton("🔓 UnBind Email", callback_data='ub')],
        [InlineKeyboardButton("📋 Check Bind Info", callback_data='ci')],
        [InlineKeyboardButton("❌ Cancel Bind", callback_data='cb')],
        [InlineKeyboardButton("🆕 Bind New Email", callback_data='bn')],
        [InlineKeyboardButton("🔗 Check Links", callback_data='cl')],
        [InlineKeyboardButton("🚫 Revoke Token", callback_data='rt')],
        [InlineKeyboardButton("📞 Contact Owner", url="https://t.me/sexy_boyhere")]
    ]
    await update.message.reply_text("🤖 *Garena Bot*\nSelect option:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def owner_panel(update, context):
    if update.effective_user.id != OWNER_ID:
        return
    kb = [[InlineKeyboardButton("📋 Pending", callback_data='pending'), InlineKeyboardButton("📊 Stats", callback_data='stats')]]
    await update.message.reply_text("👑 Owner Panel", reply_markup=InlineKeyboardMarkup(kb))

async def button_handler(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    action = q.data

    if action == 'pending' and uid == OWNER_ID:
        pending = get_pending_users()
        if not pending:
            await q.edit_message_text("No pending requests")
            return
        kb = []
        for uid2, uname, fname, date in pending:
            kb.append([InlineKeyboardButton(f"✅ {fname}", callback_data=f'app_{uid2}'), InlineKeyboardButton(f"❌", callback_data=f'den_{uid2}')])
        await q.edit_message_text("Pending:", reply_markup=InlineKeyboardMarkup(kb))
        return
    if action.startswith('app_') and uid == OWNER_ID:
        target = int(action.split('_')[1])
        approve_user(target)
        await q.edit_message_text(f"✅ Approved!")
        await context.bot.send_message(target, "✅ Access Granted!\nSend /start")
        return
    if action.startswith('den_') and uid == OWNER_ID:
        target = int(action.split('_')[1])
        cursor.execute('DELETE FROM users WHERE user_id=?', (target,))
        conn.commit()
        await q.edit_message_text(f"❌ Denied")
        return
    if action == 'stats' and uid == OWNER_ID:
        cursor.execute('SELECT COUNT(*) FROM users')
        total = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM users WHERE approved=1')
        approved = cursor.fetchone()[0]
        await q.edit_message_text(f"Stats:\nTotal: {total}\nApproved: {approved}\nPending: {total-approved}")
        return
    if not is_approved(uid):
        await q.edit_message_text("❌ Access denied")
        return
    user_sessions[uid] = {'action': action}
    await q.edit_message_text("Send your Access Token:")

async def handle_message(update, context):
    uid = update.message.from_user.id
    text = update.message.text.strip()
    if uid not in user_sessions:
        await update.message.reply_text("Use /start")
        return
    action = user_sessions[uid]['action']
    token = text
    del user_sessions[uid]
    await update.message.reply_text("Processing...")

    if action == 'ci':
        r = get_bind_info(token)
        await update.message.reply_text(f"```json\n{json.dumps(r.json(), indent=2)}\n```", parse_mode='Markdown')
    elif action == 'cb':
        r = cancel_request(token)
        await update.message.reply_text("✅ Cancelled" if r.json().get('result')==0 else "❌ Failed")
    elif action == 'cl':
        r = get_platforms(token)
        platforms = r.json().get('bounded_accounts', [])
        msg = "\n".join([f"• {p.get('platform_name')}" for p in platforms]) or "None"
        await update.message.reply_text(f"Linked:\n{msg}")
    elif action == 'rt':
        info = get_user_info(token)
        if info:
            await update.message.reply_text(f"UID: {info.get('uid')}\nName: {info.get('nickname')}")
        await update.message.reply_text("✅ Revoked" if revoke_token(token) else "❌ Failed")
    elif action == 'bc':
        await update.message.reply_text("Send security code (or 'no' for OTP):")
        user_sessions[uid] = {'action': 'bc_step2', 'token': token}
    elif action == 'ub':
        await update.message.reply_text("Send security code:")
        user_sessions[uid] = {'action': 'ub_step2', 'token': token}
    elif action == 'bn':
        await update.message.reply_text("Fetching current email...")
        r = get_bind_info(token)
        if r.status_code != 200:
            await update.message.reply_text("Failed")
            return
        old_email = r.json().get('email')
        if not old_email:
            await update.message.reply_text("No email found. Send security code:")
            user_sessions[uid] = {'action': 'bn_seccode', 'token': token}
        else:
            user_sessions[uid] = {'action': 'bn_otp', 'token': token, 'old_email': old_email}
            await update.message.reply_text(f"Sending OTP to {old_email}...")
            r = send_otp(token, old_email)
            if r.status_code != 200 or r.json().get('result') != 0:
                await update.message.reply_text("Failed to send OTP")
                del user_sessions[uid]

# Step 2 handlers
async def handle_step2(update, context):
    uid = update.message.from_user.id
    text = update.message.text.strip()
    if uid not in user_sessions:
        return
    session = user_sessions[uid]
    action = session['action']
    token = session['token']

    if action == 'bc_step2':
        if text.lower() == 'no':
            r = get_bind_info(token)
            old_email = r.json().get('email')
            if not old_email:
                await update.message.reply_text("No email found")
                del user_sessions[uid]
                return
            await update.message.reply_text(f"Sending OTP to {old_email}...")
            r = send_otp(token, old_email)
            if r.status_code != 200 or r.json().get('result') != 0:
                await update.message.reply_text("Failed")
                del user_sessions[uid]
                return
            user_sessions[uid] = {'action': 'bc_otp', 'token': token, 'old_email': old_email}
            await update.message.reply_text("Enter OTP:")
        else:
            r = verify_identity_with_security_code(token, text)
            if r.status_code != 200 or r.json().get('result') != 0:
                await update.message.reply_text("Invalid code")
                del user_sessions[uid]
                return
            user_sessions[uid] = {'action': 'bc_newemail', 'token': token, 'identity': r.json().get('identity_token')}
            await update.message.reply_text("Send new email:")
    elif action == 'bc_otp':
        r = verify_identity_with_otp(token, session['old_email'], text)
        if r.status_code != 200 or r.json().get('result') != 0:
            await update.message.reply_text("Invalid OTP")
            del user_sessions[uid]
            return
        user_sessions[uid] = {'action': 'bc_newemail', 'token': token, 'identity': r.json().get('identity_token')}
        await update.message.reply_text("Send new email:")
    elif action == 'bc_newemail':
        new_email = text
        await update.message.reply_text(f"Sending OTP to {new_email}...")
        r = send_otp(token, new_email)
        if r.status_code != 200 or r.json().get('result') != 0:
            await update.message.reply_text("Failed")
            del user_sessions[uid]
            return
        user_sessions[uid] = {'action': 'bc_verify', 'token': token, 'identity': session['identity'], 'new_email': new_email}
        await update.message.reply_text("Enter OTP from new email:")
    elif action == 'bc_verify':
        r = verify_otp(token, session['new_email'], text)
        if r.status_code != 200 or r.json().get('result') != 0:
            await update.message.reply_text("Invalid OTP")
            del user_sessions[uid]
            return
        r = create_rebind_request(token, session['identity'], r.json().get('verifier_token'), session['new_email'])
        await update.message.reply_text("✅ Email changed!" if r.json().get('result')==0 else "❌ Failed")
        del user_sessions[uid]
    elif action == 'ub_step2':
        r = verify_identity_with_security_code(token, text)
        if r.status_code != 200 or r.json().get('result') != 0:
            await update.message.reply_text("Invalid code")
            del user_sessions[uid]
            return
        r = unbind_identity(token, r.json().get('identity_token'))
        await update.message.reply_text("✅ Unbound!" if r.json().get('result')==0 else "❌ Failed")
        del user_sessions[uid]
    elif action == 'bn_seccode':
        r = verify_identity_with_security_code(token, text)
        if r.status_code != 200 or r.json().get('result') != 0:
            await update.message.reply_text("Invalid code")
            del user_sessions[uid]
            return
        user_sessions[uid] = {'action': 'bn_newemail', 'token': token, 'identity': r.json().get('identity_token')}
        await update.message.reply_text("Send new email:")
    elif action == 'bn_otp':
        r = verify_identity_with_otp(token, session['old_email'], text)
        if r.status_code != 200 or r.json().get('result') != 0:
            await update.message.reply_text("Invalid OTP")
            del user_sessions[uid]
            return
        user_sessions[uid] = {'action': 'bn_newemail', 'token': token, 'identity': r.json().get('identity_token')}
        await update.message.reply_text("Send new email:")
    elif action == 'bn_newemail':
        new_email = text
        await update.message.reply_text(f"Sending OTP to {new_email}...")
        r = send_otp(token, new_email)
        if r.status_code != 200 or r.json().get('result') != 0:
            await update.message.reply_text("Failed")
            del user_sessions[uid]
            return
        user_sessions[uid] = {'action': 'bn_verify', 'token': token, 'identity': session['identity'], 'new_email': new_email}
        await update.message.reply_text("Enter OTP:")
    elif action == 'bn_verify':
        r = verify_otp(token, session['new_email'], text)
        if r.status_code != 200 or r.json().get('result') != 0:
            await update.message.reply_text("Invalid OTP")
            del user_sessions[uid]
            return
        r = create_rebind_request(token, session['identity'], r.json().get('verifier_token'), session['new_email'])
        await update.message.reply_text("✅ Email bound!" if r.json().get('result')==0 else "❌ Failed")
        del user_sessions[uid]

# ==================== MAIN ====================
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("owner", owner_panel))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_step2))
    print("✅ Bot Running!")
    app.run_polling()