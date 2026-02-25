import os, telebot, sqlite3, requests, re, logging
from telebot import types
from datetime import datetime
from flask import Flask
from threading import Thread

# 1. ТИЗИМ СОЗЛАМАЛАРИ ВА ХАВФСИЗЛИК
TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
logging.basicConfig(level=logging.INFO)

# --- 🟢 RENDER УЧУН КИЧИК ВЕБ-СЕРВЕР ---
app = Flask('')

@app.route('/')
def home():
    return "Smart Balance тизими фаол!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_server)
    t.start()

# --- 2. БАЗАНИ ТЎЛИҚ ИНИЦИАЛИЗАЦИЯ ҚИЛИШ ---
def init_db():
    conn = sqlite3.connect('smart_balance_final.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS finance 
        (uid INTEGER, type TEXT, cat TEXT, amt REAL, cur TEXT, date TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS communal 
        (uid INTEGER, type TEXT, amt REAL, cur TEXT, date TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS debts 
        (uid INTEGER, d_type TEXT, name TEXT, amt REAL, cur TEXT)''')
    conn.commit()
    conn.close()

# --- 3. ВАЛЮТА КУРСЛАРИНИ ОЛИШ ---
def get_rates():
    rates = {'UZS': 1.0, 'USD': 12850.0, 'RUB': 145.0, 'CNY': 1850.0}
    try:
        res = requests.get("https://nbu.uz/uz/exchange-rates/json/", timeout=3).json()
        for i in res:
            if i['code'] in rates:
                rates[i['code']] = float(i['cb_price'])
    except:
        pass
    return rates

# --- 4. АСОСИЙ МЕНЮ (8 ТА ТУГМА) ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add("💸 Харажат", "💰 Даромад", "📊 Статистика", "📅 Ойлик харажат", 
          "🔍 Кунлик ҳисобот", "🤝 Олди-берди", "🏠 Коммунал", "📈 Валюта/Конвертер")
    return m

@bot.message_handler(commands=['start'])
def start_cmd(message):
    init_db()
    bot.send_message(message.chat.id, "🌟 **Smart Balance** тизимига хуш келибсиз!", 
                     reply_markup=main_menu(), parse_mode="Markdown")

# --- 5. 💸 ХАРАЖАТ ВА 💰 ДАРОМАД ---
@bot.message_handler(func=lambda m: m.text in ["💸 Харажат", "💰 Даромад"])
def finance_init(message):
    act = "exp" if "Харажат" in message.text else "inc"
    msg = bot.send_message(message.chat.id, f"📝 **{message.text}** бўлими.\n\nСумма ва мақсадни ёзинг.\n💡 *Мисол:* `Обед 50000` ёки `Ойлик 500`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda m: finance_process(m, act))

def finance_process(message, act):
    nums = re.findall(r'\d+', message.text)
    words = re.findall(r'[a-zA-Zа-яА-Яўғшч]+', message.text)
    
    if not nums:
        msg = bot.send_message(message.chat.id, "⚠️ **Хато!** Суммани рақамда ёзинг.\n\nҚайтадан уриниб кўринг:")
        bot.register_next_step_handler(msg, lambda m: finance_process(m, act))
        return

    amt = float(nums[0])
    cat = words[0] if words else "Бошқа"
    
    m = types.InlineKeyboardMarkup()
    for c in ["UZS", "USD", "RUB", "CNY"]:
        m.add(types.InlineKeyboardButton(c, callback_data=f"sf_{act}_{cat}_{amt}_{c}"))
    bot.send_message(message.chat.id, f"📌 Категория: {cat}\n💰 Сумма: {amt:,.0f}\n\nВалютани танланг:", reply_markup=m)

# --- 6. 📊 СТАТИСТИКА ---
def get_stats_text(uid):
    conn = sqlite3.connect('smart_balance_final.db'); c = conn.cursor()
    c.execute("SELECT type, amt, cur FROM finance WHERE uid=?", (uid,))
    rows = c.fetchall()
    r = get_rates(); inc, exp = 0.0, 0.0
    
    for t, a, cur in rows:
        val = a * r.get(cur, 1.0)
        if t == "inc": inc += val
        else: exp += val
    conn.close()
    
    return (f"📊 **Сизнинг умумий статистикангиз:**\n━━━━━━━━━━━━━━\n"
            f"💰 Жами Даромад: {inc:,.0f} UZS\n💸 Жами Харажат: {exp:,.0f} UZS\n━━━━━━━━━━━━━━\n"
            f"⚖️ Соф Фойда: {inc-exp:,.0f} UZS")

@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def statistics_view(message):
    text = get_stats_text(message.chat.id)
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# --- 7. 📅 ОЙЛИК ХАРАЖАТ ---
@bot.message_handler(func=lambda m: m.text == "📅 Ойлик харажат")
def month_report_start(message):
    conn = sqlite3.connect('smart_balance_final.db'); c = conn.cursor()
    c.execute("SELECT DISTINCT strftime('%Y-%m', date) FROM finance WHERE uid=? AND type='exp'", (message.chat.id,))
    months = c.fetchall()
    
    if not months:
        return bot.send_message(message.chat.id, "📭 Харажатлар ҳали киритилмаган.")
    
    m = types.InlineKeyboardMarkup()
    for mon in months:
        m.add(types.InlineKeyboardButton(f"📅 {mon[0]}", callback_data=f"viewmon_{mon[0]}"))
    bot.send_message(message.chat.id, "Ҳисоботни кўриш учун ойни танланг:", reply_markup=m)

# --- 8. 🔍 КУНЛИК ҲИСОБОТ ---
@bot.message_handler(func=lambda m: m.text == "🔍 Кунлик ҳисобот")
def daily_report_start(message):
    msg = bot.send_message(message.chat.id, "Қайси кунни кўрмоқчисиз?\nМисол: `24` (жорий ойнинг 24-куни учун)")
    bot.register_next_step_handler(msg, daily_report_finish)

def daily_report_finish(message):
    try:
        day = message.text.zfill(2)
        target = datetime.now().strftime(f"%Y-%m-{day}")
        conn = sqlite3.connect('smart_balance_final.db'); c = conn.cursor()
        c.execute("SELECT type, cat, amt, cur FROM finance WHERE uid=? AND date=?", (message.chat.id, target))
        rows = c.fetchall()
        
        if not rows:
            return bot.send_message(message.chat.id, f"📅 {target} санасида маълумот йўқ.")
        
        txt = f"🔍 **Ҳисобот: {target}**\n━━━━━━━━━━━━━━\n"
        for t, cat, amt, cur in rows:
            icon = "➕" if t == "inc" else "➖"
            txt += f"{icon} {cat}: {amt:,.0f} {cur}\n"
        bot.send_message(message.chat.id, txt, parse_mode="Markdown")
        conn.close()
    except:
        bot.send_message(message.chat.id, "❌ Санани киритишда хатолик.")

# --- 9. 🤝 ОЛДИ-БЕРДИ ---
@bot.message_handler(func=lambda m: m.text == "🤝 Олди-берди")
def debt_main_menu(message):
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add("🟢 Ҳаққим бор", "🔴 Қарздорман", "📜 Кимда нимам бор", "⬅️ Ортга")
    bot.send_message(message.chat.id, "🤝 **Олди-берди бўлими**\nБу ерда қарзларни назорат қилишингиз мумкин.", 
                     reply_markup=m, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text in ["🟢 Ҳаққим бор", "🔴 Қарздорман"])
def debt_add_start(message):
    dtype = "plus" if "Ҳаққим" in message.text else "minus"
    msg = bot.send_message(message.chat.id, "Исм ва суммани ёзинг.\n💡 *Мисол:* `Али 100`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda m: debt_save_step1(m, dtype))

def debt_save_step1(message, dtype):
    nums = re.findall(r'\d+', message.text)
    words = re.findall(r'[a-zA-Zа-яА-Яўғшч]+', message.text)
    if not nums or not words:
        return bot.send_message(message.chat.id, "❌ Хато! Исм ва суммани тўғри ёзинг.")
    name, amt = words[0], float(nums[0])
    
    m = types.InlineKeyboardMarkup()
    for c in ["UZS", "USD", "RUB", "CNY"]:
        m.add(types.InlineKeyboardButton(c, callback_data=f"sd_{dtype}_{name}_{amt}_{c}"))
    bot.send_message(message.chat.id, f"👤 {name}, 💰 {amt:,.0f}\nВалютани танланг:", reply_markup=m)

@bot.message_handler(func=lambda m: m.text == "📜 Кимда нимам бор")
def debt_list_view(message):
    conn = sqlite3.connect('smart_balance_final.db'); c = conn.cursor()
    c.execute("SELECT d_type, name, amt, cur FROM debts WHERE uid=?", (message.chat.id,))
    rows = c.fetchall()
    if not rows: return bot.send_message(message.chat.id, "📜 Рўйхат ҳозирча бўш.")
    txt = "📜 **Қарзлар ва Ҳақдорликлар:**\n\n"
    for t, n, a, cur in rows:
        icon = "🟢 Ҳаққим:" if t == "plus" else "🔴 Қарзим:"
        txt += f"{icon} {n} — {a:,.0f} {cur}\n"
    bot.send_message(message.chat.id, txt, parse_mode="Markdown")
    conn.close()

# --- 10. 🏠 КОММУНАЛ ---
@bot.message_handler(func=lambda m: m.text == "🏠 Коммунал")
def communal_main(message):
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add("➕ Ҳисоб қўшиш", "⬅️ Ортга")
    bot.send_message(message.chat.id, "🏠 **Коммунал хизматлар ва солиқлар**", reply_markup=m, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "➕ Ҳисоб қўшиш")
def communal_add_list(message):
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("⚡️ Свет", "🔥 Газ", "💧 Сув", "🌱 Ер солиғи", "🏠 Уй солиғи", "⬅️ Ортга")
    msg = bot.send_message(message.chat.id, "Тўлов турини танланг:", reply_markup=m)
    bot.register_next_step_handler(msg, communal_amt_step)

def communal_amt_step(message):
    if message.text == "⬅️ Ортга": return communal_main(message)
    t = message.text
    msg = bot.send_message(message.chat.id, f"💰 {t} учун суммани ёзинг:")
    bot.register_next_step_handler(msg, lambda m: communal_cur_step(m, t))

def communal_cur_step(message, t):
    nums = re.findall(r'\d+', message.text)
    if not nums: return bot.send_message(message.chat.id, "❌ Суммани рақамда ёзинг.")
    amt = nums[0]
    m = types.InlineKeyboardMarkup()
    for c in ["UZS", "USD", "RUB", "CNY"]:
        m.add(types.InlineKeyboardButton(c, callback_data=f"sc_{t}_{amt}_{c}"))
    bot.send_message(message.chat.id, "Валютани танланг:", reply_markup=m)

# --- 11. 📈 ВАЛЮТА / КОНВЕРТЕР (СИЗ АЙТГАНДЕК ЯНГИЛАНДИ) ---
@bot.message_handler(func=lambda m: m.text == "📈 Валюта/Конвертер")
def converter_start(message):
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("USD", "RUB", "CNY", "⬅️ Ортга")
    msg = bot.send_message(message.chat.id, "Қайси валютани UZS га айлантирамиз?", reply_markup=m)
    bot.register_next_step_handler(msg, converter_amt_step)

def converter_amt_step(message):
    cur = message.text
    if cur == "⬅️ Ортга": return start_cmd(message)
    if cur not in ["USD", "RUB", "CNY"]:
        return bot.send_message(message.chat.id, "Илтимос, тугмалардан бирини танланг.")
    msg = bot.send_message(message.chat.id, f"💰 {cur} суммасини киритинг:")
    bot.register_next_step_handler(msg, lambda m: converter_finish(m, cur))

def converter_finish(message, cur):
    nums = re.findall(r'\d+', message.text)
    if not nums:
        msg = bot.send_message(message.chat.id, "⚠️ Суммани рақамда ёзинг:")
        bot.register_next_step_handler(msg, lambda m: converter_finish(m, cur))
        return
    amt = float(nums[0])
    r = get_rates()
    res = amt * r[cur]
    bot.send_message(message.chat.id, f"🔄 {amt:,.0f} {cur} = **{res:,.0f} UZS**", reply_markup=main_menu(), parse_mode="Markdown")

# --- 12. CALLBACK ҲАММА ТУГМАЛАР УЧУН ---
@bot.callback_query_handler(func=lambda call: True)
def universal_callback(call):
    d = call.data.split('_')
    conn = sqlite3.connect('smart_balance_final.db'); c = conn.cursor()

    if d[0] == "sf":
        c.execute("INSERT INTO finance VALUES (?,?,?,?,?,?)", (call.message.chat.id, d[1], d[2], d[3], d[4], datetime.now().strftime("%Y-%m-%d")))
        bot.edit_message_text(f"✅ Сақланди: {d[2]} ({d[3]} {d[4]})", call.message.chat.id, call.message.message_id)
        
    elif d[0] == "sd":
        c.execute("INSERT INTO debts VALUES (?,?,?,?,?)", (call.message.chat.id, d[1], d[2], d[3], d[4]))
        bot.edit_message_text(f"🤝 Қарз рўйхатга олинди: {d[2]} ({d[3]} {d[4]})", call.message.chat.id, call.message.message_id)

    elif d[0] == "sc":
        c.execute("INSERT INTO communal VALUES (?,?,?,?,?)", (call.message.chat.id, d[1], d[2], d[3], datetime.now().strftime("%Y-%m-%d")))
        bot.edit_message_text(f"🏠 Тўлов сақланди: {d[1]} ({d[2]} {d[3]})", call.message.chat.id, call.message.message_id)

    elif d[0] == "viewmon":
        c.execute("SELECT cat, SUM(amt), cur FROM finance WHERE uid=? AND type='exp' AND date LIKE ? GROUP BY cat, cur", (call.message.chat.id, f"{d[1]}%"))
        rows = c.fetchall()
        txt = f"📅 **{d[1]} ойи бўйича харажатлар:**\n\n"
        for ct, am, cr in rows: txt += f"🔸 {ct}: {am:,.0f} {cr}\n"
        bot.edit_message_text(txt if rows else "📭 Бу ойда маълумот йўқ.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

    conn.commit(); conn.close()
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.text == "⬅️ Ортга")
def back_home(message):
    start_cmd(message)

# --- 13. БОТНИ ИШГА ТУШИРИШ ---
if __name__ == "__main__":
    init_db()
    keep_alive()
    bot.polling(none_stop=True)
