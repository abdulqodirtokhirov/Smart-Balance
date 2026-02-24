import os, telebot, sqlite3, requests
from telebot import types
from datetime import datetime
from flask import Flask
from threading import Thread

# ТОКЕННИ RENDER-ДА BOT_TOKEN ДЕБ КИРИТИНГ
TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- БАЗАНИ СОЗЛАШ ---
def init_db():
    conn = sqlite3.connect('smart_fin_pro.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS finance 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, type TEXT, category TEXT, amount REAL, currency TEXT, date TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS communal 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, type TEXT, amount REAL, currency TEXT, date TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS debts 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, d_type TEXT, name TEXT, amount REAL, currency TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (uid INTEGER PRIMARY KEY, main_cur TEXT)''')
    conn.commit(); conn.close()

def get_rates():
    rates = {'UZS': 1.0, 'USD': 12850.0, 'RUB': 145.0, 'CNY': 1800.0}
    try:
        res = requests.get("https://nbu.uz/uz/exchange-rates/json/", timeout=5).json()
        for i in res:
            if i['code'] in rates: rates[i['code']] = float(i['cb_price'])
    except: pass
    return rates

def get_main_cur(uid):
    conn = sqlite3.connect('smart_fin_pro.db'); c = conn.cursor()
    c.execute("SELECT main_cur FROM settings WHERE uid=?", (uid,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else "UZS"

# --- МЕНЮЛАР ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.row("💸 Харажат", "💰 Даромад")
    m.row("📊 Статистика")
    m.row("📅 Ойлик харажат", "🔍 Кунлик ҳисобот")
    m.row("🤝 Олди-берди", "🏠 Коммунал")
    m.row("📈 Валюта ва Конвертер")
    return m

def communal_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.row("➕ Ҳисоб қўшиш", "📊 Коммунал Ҳисобот")
    m.row("⬅️ Ортга")
    return m

def debt_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    m.row("🟢 Ҳаққим бор", "🔴 Қарздорман")
    m.row("📜 Кимда нимам бор")
    m.row("💰 Қарзни қайтариш")
    m.row("⬅️ Ортга")
    return m

# --- АСОСИЙ ФУНКЦИЯЛАР ---
@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    bot.send_message(message.chat.id, "🚀 Aktiv PRO фаол! Шартлар асосида созланди.", reply_markup=main_menu())

# --- ХАРАЖАТ / ДАРОМАД (АВВАЛ КАТЕГОРИЯ) ---
@bot.message_handler(func=lambda m: m.text in ["💸 Харажат", "💰 Даромад"])
def fin_start(message):
    action = "exp" if "Харажат" in message.text else "inc"
    msg = bot.send_message(message.chat.id, "Категорияни киритинг (Масалан: Овқат, Ойлик):")
    bot.register_next_step_handler(msg, lambda m: ask_fin_amt(m, action))

def ask_fin_amt(message, action):
    cat = message.text if message.text else "Бошқа"
    msg = bot.send_message(message.chat.id, f"[{cat}] суммасини ёзинг:")
    bot.register_next_step_handler(msg, lambda m: ask_fin_cur(m, action, cat))

def ask_fin_cur(message, action, cat):
    try:
        amt = float(message.text)
        m = types.InlineKeyboardMarkup()
        for c in ["UZS", "USD", "RUB", "CNY"]:
            m.add(types.InlineKeyboardButton(c, callback_data=f"f_{action}_{cat}_{amt}_{c}"))
        bot.send_message(message.chat.id, "Валютани танланг:", reply_markup=m)
    except: bot.send_message(message.chat.id, "Хато! Фақат сон ёзинг.")

# --- КОММУНАЛ ---
@bot.message_handler(func=lambda m: m.text == "🏠 Коммунал")
def comm_main(message):
    bot.send_message(message.chat.id, "🏠 Коммунал бўлими:", reply_markup=communal_menu())

@bot.message_handler(func=lambda m: m.text == "➕ Ҳисоб қўшиш")
def comm_add(message):
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add("⚡️ Свет", "🔥 Газ", "💧 Сув", "🗑 Чиқинди", "🏢 Уй солиғи", "🌱 Ер солиғи", "⬅️ Ортга")
    msg = bot.send_message(message.chat.id, "Тўлов турини танланг:", reply_markup=m)
    bot.register_next_step_handler(msg, lambda m: ask_c_amt(m))

def ask_c_amt(message):
    if message.text == "⬅️ Ортга": return comm_main(message)
    t = message.text
    msg = bot.send_message(message.chat.id, f"[{t}] суммасини ёзинг:")
    bot.register_next_step_handler(msg, lambda m: ask_c_cur(m, t))

def ask_c_cur(message, t):
    try:
        amt = float(message.text)
        m = types.InlineKeyboardMarkup()
        for c in ["UZS", "USD", "RUB", "CNY"]:
            m.add(types.InlineKeyboardButton(c, callback_data=f"c_{t}_{amt}_{c}"))
        bot.send_message(message.chat.id, "Валютани танланг:", reply_markup=m)
    except: bot.send_message(message.chat.id, "Хато!")

# --- ВАЛЮТА ВА КОНВЕРТЕР ---
@bot.message_handler(func=lambda m: m.text == "📈 Валюта ва Конвертер")
def cur_section(message):
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton("⚙️ Валюта танлаш (Асосий)", callback_data="set_cur"),
        types.InlineKeyboardButton("📈 Курслар ва Конвертер", callback_data="conv_menu")
    )
    bot.send_message(message.chat.id, "📈 Валюта бўлими:", reply_markup=m)

# --- ОЛДИ-БЕРДИ (5 ТА ТУГМА) ---
@bot.message_handler(func=lambda m: m.text == "🤝 Олди-берди")
def debt_section(message):
    bot.send_message(message.chat.id, "🤝 Олди-берди панели:", reply_markup=debt_menu())

@bot.message_handler(func=lambda m: m.text in ["🟢 Ҳаққим бор", "🔴 Қарздорман"])
def debt_add(message):
    d_type = "plus" if "Ҳаққим" in message.text else "minus"
    msg = bot.send_message(message.chat.id, "Исмни ёзинг:")
    bot.register_next_step_handler(msg, lambda m: ask_d_amt(m, d_type))

def ask_d_amt(message, d_type):
    name = message.text
    msg = bot.send_message(message.chat.id, f"{name} учун суммани ёзинг:")
    bot.register_next_step_handler(msg, lambda m: ask_d_cur(m, d_type, name))

def ask_d_cur(message, d_type, name):
    try:
        amt = float(message.text)
        m = types.InlineKeyboardMarkup()
        for c in ["UZS", "USD", "RUB", "CNY"]:
            m.add(types.InlineKeyboardButton(c, callback_data=f"d_{d_type}_{name}_{amt}_{c}"))
        bot.send_message(message.chat.id, "Валюта:", reply_markup=m)
    except: bot.send_message(message.chat.id, "Хато!")

@bot.message_handler(func=lambda m: m.text == "📜 Кимда нимам бор")
def debt_list(message):
    conn = sqlite3.connect('smart_fin_pro.db'); c = conn.cursor()
    c.execute("SELECT d_type, name, amount, currency FROM debts WHERE uid=?", (message.chat.id,))
    rows = c.fetchall()
    if not rows: return bot.send_message(message.chat.id, "Рўйхат бўш.")
    res = "📜 Қарзлар рўйхати:\n\n"
    for t, n, a, cur in rows:
        icon = "🟢" if t == "plus" else "🔴"
        res += f"{icon} {n}: {a:,.2f} {cur}\n"
    bot.send_message(message.chat.id, res)

# --- CALLBACKS ---
@bot.callback_query_handler(func=lambda call: True)
def calls(call):
    d = call.data.split('_')
    r = get_rates()
    conn = sqlite3.connect('smart_fin_pro.db'); cur = conn.cursor()

    if d[0] == 'f': # Finance
        cur.execute("INSERT INTO finance (uid, type, category, amount, currency, date) VALUES (?,?,?,?,?,?)",
                   (call.message.chat.id, d[1], d[2], float(d[3]), d[4], datetime.now().strftime("%Y-%m-%d")))
        conn.commit(); bot.send_message(call.message.chat.id, "✅ Сақланди!")

    elif d[0] == 'c': # Communal
        cur.execute("INSERT INTO communal (uid, type, amount, currency, date) VALUES (?,?,?,?,?)",
                   (call.message.chat.id, d[1], float(d[2]), d[3], datetime.now().strftime("%Y-%m-%d")))
        conn.commit(); bot.send_message(call.message.chat.id, "✅ Коммунал сақланди!")

    elif d[0] == 'd': # Debts
        cur.execute("INSERT INTO debts (uid, d_type, name, amount, currency) VALUES (?,?,?,?,?)",
                   (call.message.chat.id, d[1], d[2], float(d[3]), d[4]))
        conn.commit(); bot.send_message(call.message.chat.id, "✅ Қарз рўйхатга олинди!")

    elif d[0] == 'conv' and d[1] == 'menu':
        txt = f"🏦 Курслар:\n1 USD = {r['USD']} UZS\n1 RUB = {r['RUB']} UZS\n\nСуммани чақиш учун ёзинг (Масалан: 100 USD):"
        bot.send_message(call.message.chat.id, txt)

    conn.close()

# --- СТАТИСТИКА (ФОЙДА/ЗАРАР) ---
@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def stats(message):
    r = get_rates(); m_c = get_main_cur(message.chat.id)
    conn = sqlite3.connect('smart_fin_pro.db'); c = conn.cursor()
    c.execute("SELECT type, amount, currency FROM finance WHERE uid=?", (message.chat.id,))
    data = c.fetchall()
    inc = sum((a * r[cur]) / r[m_c] for t, a, cur in data if t == 'inc')
    exp = sum((a * r[cur]) / r[m_c] for t, a, cur in data if t == 'exp')
    bot.send_message(message.chat.id, f"📊 Статистика ({m_c}):\n💰 Даромад: {inc:,.2f}\n💸 Харажат: {exp:,.2f}\n⚖️ Натижа: {inc-exp:,.2f}")

# --- ОРТГА ---
@bot.message_handler(func=lambda m: m.text == "⬅️ Ортга")
def back(message):
    bot.send_message(message.chat.id, "Асосий меню:", reply_markup=main_menu())

# RENDER WEB SERVER
@app.route('/')
def home(): return "OK"

if __name__ == "__main__":
    init_db()
    Thread(target=lambda: app.run(host='0.0.0.0', port=10000)).start()
    bot.polling(none_stop=True)
