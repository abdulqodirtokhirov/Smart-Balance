import os, telebot, sqlite3, requests
from telebot import types
from datetime import datetime
from flask import Flask
from threading import Thread

# Render-даги Environment Variable-дан токенни оламиз
TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- 1. БАЗАНИ ТЎЛИҚ СОЗЛАШ ---
def init_db():
    conn = sqlite3.connect('aktiv_pro.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS finance 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, type TEXT, 
         category TEXT, amount REAL, currency TEXT, date TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS debts 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, d_type TEXT, 
         name TEXT, amount REAL, currency TEXT, status TEXT)''')
    conn.commit(); conn.close()

# --- 2. МБ КУРСЛАРИНИ ОЛИШ ---
def get_rates():
    rates = {'UZS': 1.0, 'USD': 12850.0, 'RUB': 145.0, 'CNY': 1800.0}
    try:
        res = requests.get("https://nbu.uz/uz/exchange-rates/json/", timeout=5).json()
        for i in res:
            if i['code'] in rates: rates[i['code']] = float(i['cb_price'])
    except: pass
    return rates

# --- 3. 1-9 ИНЛАЙН КЛАВИАТУРА ---
def get_amount_keyboard(action, current_val=""):
    markup = types.InlineKeyboardMarkup(row_width=3)
    btns = [types.InlineKeyboardButton(str(i), callback_data=f"num_{action}_{current_val}{i}") for i in range(1, 10)]
    markup.add(*btns)
    markup.add(types.InlineKeyboardButton("0", callback_data=f"num_{action}_{current_val}0"),
               types.InlineKeyboardButton("⬅️", callback_data=f"num_{action}_{current_val[:-1]}"),
               types.InlineKeyboardButton("🗑", callback_data=f"num_{action}_"))
    if current_val:
        markup.add(types.InlineKeyboardButton(f"✅ Тасдиқлаш: {current_val}", callback_data=f"confirm_{action}_{current_val}"))
    return markup

# --- 4. АСОСИЙ МЕНЮ (10 ТА ТУГМА) ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row("💸 Харажат", "💰 Даромад")
    markup.add("📊 Статистика", "📅 Ойлик харажат")
    markup.row("🔍 Кунлик ҳисобот")
    markup.row("🤝 Олди-берди")
    markup.row("🏠 Коммунал")
    markup.row("📊 Коммунал Ҳисобот")
    markup.row("⚙️ Валюта танлаш")
    markup.row("📈 Жонли Валюта ва Конвертер")
    return markup

user_view_cur = {} 

@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    user_view_cur[message.chat.id] = "UZS"
    bot.send_message(message.chat.id, "🚀 **Aktiv PRO** тизимига хуш келибсиз!", reply_markup=main_menu())

# --- 5. КИРИТИШ (АВВАЛ СУММА) ---
@bot.message_handler(func=lambda m: m.text in ["💸 Харажат", "💰 Даромад", "🤝 Олди-берди", "🏠 Коммунал"])
def handle_entry_start(message):
    act_map = {"💸 Харажат":"exp", "💰 Даромад":"inc", "🤝 Олди-берди":"debt", "🏠 Коммунал":"com"}
    action = act_map[message.text]
    bot.send_message(message.chat.id, f"🔢 {message.text} суммасини киритинг:", reply_markup=get_amount_keyboard(action))

# --- 6. ҲИСОБОТЛАР (БАТАФСИЛ) ---
@bot.message_handler(func=lambda m: m.text in ["📊 Статистика", "📅 Ойлик харажат", "🔍 Кунлик ҳисобот", "📊 Коммунал Ҳисобот"])
def handle_reports(message):
    conn = sqlite3.connect('aktiv_pro.db'); cursor = conn.cursor()
    v_cur = user_view_cur.get(message.chat.id, "UZS")
    r = get_rates()

    if message.text == "📊 Статистика":
        cursor.execute("SELECT type, amount, currency FROM finance WHERE uid=?", (message.chat.id,))
        rows = cursor.fetchall(); total = 0
        for t, a, c in rows:
            val = (a * r.get(c, 1)) / r.get(v_cur, 1)
            total += val if t == "inc" else -val
        bot.send_message(message.chat.id, f"⚖️ Умумий қолдиқ: {total:,.2f} {v_cur}")
    else:
        cursor.execute("SELECT DISTINCT strftime('%Y-%m', date) FROM finance WHERE uid=? ORDER BY date DESC", (message.chat.id,))
        months = cursor.fetchall()
        if not months: return bot.send_message(message.chat.id, "Ҳозирча маълумот йўқ.")
        m = types.InlineKeyboardMarkup()
        pfx = "mon" if "Ойлик" in message.text else "day" if "Кунлик" in message.text else "comrep"
        for mon in months:
            m.add(types.InlineKeyboardButton(f"📅 {mon[0]}", callback_data=f"{pfx}_{mon[0]}"))
        bot.send_message(message.chat.id, "Ойни танланг:", reply_markup=m)
    conn.close()

# --- 7. ВАЛЮТА ВА КУРС ---
@bot.message_handler(func=lambda m: m.text == "⚙️ Валюта танлаш")
def set_currency_view(message):
    m = types.InlineKeyboardMarkup()
    for c in ["UZS", "USD", "RUB", "CNY"]:
        m.add(types.InlineKeyboardButton(c, callback_data=f"setcur_{c}"))
    bot.send_message(message.chat.id, "Ҳисоботлар қайси валютада кўрсатилсин?", reply_markup=m)

@bot.message_handler(func=lambda m: m.text == "📈 Жонли Валюта ва Конвертер")
def live_currency(message):
    r = get_rates()
    text = f"🏦 МБ Курслари:\n🇺🇿 1 USD = {r['USD']} UZS\n🇷🇺 1 RUB = {r['RUB']} UZS\n🇨🇳 1 CNY = {r['CNY']} UZS\n\nКонвертер учун валютани танланг:"
    m = types.InlineKeyboardMarkup(row_width=2)
    for c in ["USD", "RUB", "CNY"]:
        m.add(types.InlineKeyboardButton(f"🔄 {c}", callback_data=f"calc_{c}"))
    m.add(types.InlineKeyboardButton("⬅️ Ортга", callback_data="back_main"))
    bot.send_message(message.chat.id, text, reply_markup=m)

# --- 8. CALLBACKS ---
@bot.callback_query_handler(func=lambda call: True)
def handle_calls(call):
    d = call.data.split('_')
    r = get_rates()
    v_cur = user_view_cur.get(call.message.chat.id, "UZS")

    if d[0] == 'num':
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_amount_keyboard(d[1], d[2]))
    elif d[0] == 'confirm':
        msg_text = "Энди категорияни ёзинг (Масалан: Бензин, Свет):"
        msg = bot.send_message(call.message.chat.id, f"💰 Сумма: {d[2]}\n\n{msg_text}")
        bot.register_next_step_handler(msg, lambda m: ask_save_currency(m, d[1], d[2]))
    elif d[0] == 'save':
        conn = sqlite3.connect('aktiv_pro.db'); cursor = conn.cursor()
        date_now = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("INSERT INTO finance (uid, type, category, amount, currency, date) VALUES (?,?,?,?,?,?)",
                       (call.message.chat.id, d[1], d[2], float(d[3]), d[4], date_now))
        conn.commit(); conn.close()
        bot.send_message(call.message.chat.id, f"✅ Сақланди: {d[2]} - {d[3]} {d[4]}")
    elif d[0] == 'mon':
        conn = sqlite3.connect('aktiv_pro.db'); cursor = conn.cursor()
        cursor.execute("SELECT amount, currency FROM finance WHERE uid=? AND date LIKE ? AND type IN ('exp','com')", (call.message.chat.id, f"{d[1]}%"))
        rows = cursor.fetchall(); total = sum((a * r.get(c, 1)) / r.get(v_cur, 1) for a, c in rows)
        bot.send_message(call.message.chat.id, f"📅 {d[1]} жами харажат: {total:,.2f} {v_cur}")
    elif d[0] == 'setcur':
        user_view_cur[call.message.chat.id] = d[1]
        bot.send_message(call.message.chat.id, f"✅ Ҳисоботлар энди {d[1]}да.")
    elif d[0] == 'back' and d[1] == 'main':
        bot.send_message(call.message.chat.id, "Асосий меню:", reply_markup=main_menu())

def ask_save_currency(message, action, amount):
    cat = message.text
    m = types.InlineKeyboardMarkup()
    for c in ["UZS", "USD", "RUB", "CNY"]:
        m.add(types.InlineKeyboardButton(c, callback_data=f"save_{action}_{cat}_{amount}_{c}"))
    bot.send_message(message.chat.id, f"Категория: {cat}\nВалютани танланг:", reply_markup=m)

# Render учун Keep-Alive
@app.route('/')
def home(): return "OK"
def run(): app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    init_db()
    Thread(target=run).start()
    bot.polling(none_stop=True)
