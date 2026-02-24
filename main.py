import os, telebot, sqlite3, requests, re, logging
from telebot import types
from datetime import datetime
from flask import Flask
from threading import Thread

# --- ЛОГГИНГ (Тизимни кузатиш учун) ---
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- БАЗАНИ МУСТАҲКАМЛАШ ---
def init_db():
    try:
        conn = sqlite3.connect('smart_balance_v4.db', check_same_thread=False)
        cursor = conn.cursor()
        # Ҳар бир жадвал учун аниқ структура
        cursor.execute('''CREATE TABLE IF NOT EXISTS finance 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, type TEXT, cat TEXT, amt REAL, cur TEXT, date TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS communal 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, type TEXT, amt REAL, cur TEXT, date TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS debts 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, d_type TEXT, name TEXT, amt REAL, cur TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
            (uid INTEGER PRIMARY KEY, main_cur TEXT DEFAULT "UZS", lang TEXT DEFAULT "UZ")''')
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Базада хатолик: {e}")

def get_rates():
    # Заҳира курслари (агар интернет ишламаса)
    rates = {'UZS': 1.0, 'USD': 12850.0, 'RUB': 145.0, 'CNY': 1800.0}
    try:
        res = requests.get("https://nbu.uz/uz/exchange-rates/json/", timeout=7).json()
        for i in res:
            if i['code'] in rates:
                rates[i['code']] = float(i['cb_price'])
    except Exception:
        logging.warning("Марказий банк билан алоқа йўқ, заҳира курслари ишлатилмоқда.")
    return rates

# --- МЕНЮ ТИЗИМИ (8 ТА ТУГМА) ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add("💸 Харажат", "💰 Даромад", "📊 Статистика", "📅 Ойлик харажат", 
          "🔍 Кунлик ҳисобот", "🤝 Олди-берди", "🏠 Коммунал", "📈 Валюта/Конвертер")
    return m

@bot.message_handler(commands=['start'])
def start_cmd(message):
    init_db()
    welcome_text = (
        "🌟 **SMART BALANCE ТИЗИМИГА ХУШ КЕЛИБСИЗ!**\n\n"
        "Бу тизим Сизнинг шахсий молиявий экспертизга айланади. "
        "Қуйидаги 8 та бўлим орқали пулларингизни назорат қилинг."
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_menu(), parse_mode="Markdown")

# --- 1 & 2. КИРИМ-ЧИҚИМ ВА АҚЛЛИ ҲИМОЯ ---
@bot.message_handler(func=lambda m: m.text in ["💸 Харажат", "💰 Даромад"])
def finance_init(message):
    is_exp = "Харажат" in message.text
    act_type = "exp" if is_exp else "inc"
    prompt = "💸 Харажат" if is_exp else "💰 Даромад"
    
    msg = bot.send_message(message.chat.id, 
        f"📋 **{prompt} бўлими**\n\nСумма ва мақсадни ёзинг.\n"
        f"💡 **Намуна:** `Обед 55000` ёки `Маош 1200`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda m: finance_save_step(m, act_type))

def finance_save_step(message, act_type):
    txt = message.text
    nums = re.findall(r'\d+', txt)
    
    if not nums:
        # Мустаҳкам ҳимоя: Хато киритилса қайта сўраш ёки тушунтириш
        error_msg = (
            "⚠️ **Хатолик юз берди!**\n\n"
            "Сиз сумма киритишни унутдингиз ёки нотўғри формат ишлатдингиз.\n"
            "✅ **Тўғри формат:** `Категория` + `Сумма` (Масалан: `Бензин 200000`)\n\n"
            "Илтимос, тугмани қайта босиб уриниб кўринг."
        )
        bot.send_message(message.chat.id, error_msg, parse_mode="Markdown")
        return

    amount = float(nums[0])
    words = re.findall(r'[a-zA-Zа-яА-Яўғшч]+', txt)
    category = words[0] if words else "Бошқа"
    
    # Валюта танлаш тугмалари
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [types.InlineKeyboardButton(c, callback_data=f"fin|{act_type}|{category}|{amount}|{c}") for c in ["UZS", "USD", "RUB", "CNY"]]
    markup.add(*btns)
    
    bot.send_message(message.chat.id, 
        f"📊 **Тасдиқлаш:**\n\n🔹 Тури: {'Чиқим' if act_type=='exp' else 'Кирим'}\n"
        f"🔹 Мақсад: {category}\n🔹 Сумма: {amount:,.0f}\n\nВалютани танланг:", reply_markup=markup, parse_mode="Markdown")

# --- 7. КОММУНАЛ (ЕР СОЛИҒИ + МУСТАҲКАМ ИЕРАРХИЯ) ---
@bot.message_handler(func=lambda m: m.text == "🏠 Коммунал")
def communal_main(message):
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add("➕ Ҳисоб қўшиш", "📊 Коммунал Ҳисобот", "⬅️ Ортга")
    bot.send_message(message.chat.id, "🏠 **Коммунал тўловлар бошқаруви:**", reply_markup=m, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "➕ Ҳисоб қўшиш")
def communal_add_list(message):
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add("⚡️ Свет", "🔥 Газ", "💧 Сув", "🌱 Ер солиғи", "🏠 Уй солиғи", "⬅️ Ортга")
    msg = bot.send_message(message.chat.id, "Қайси тўловни амалга оширдингиз?", reply_markup=m)
    bot.register_next_step_handler(msg, communal_amount_step)

def communal_amount_step(message):
    if message.text == "⬅️ Ортга": return communal_main(message)
    service_type = message.text
    msg = bot.send_message(message.chat.id, f"💰 **{service_type}** учун тўланган суммани киритинг:")
    bot.register_next_step_handler(msg, lambda m: communal_currency_step(m, service_type))

def communal_currency_step(message, service_type):
    nums = re.findall(r'\d+', message.text)
    if not nums:
        bot.send_message(message.chat.id, "❌ Сумма фақат рақамларда бўлиши керак!")
        return
    
    amount = nums[0]
    markup = types.InlineKeyboardMarkup()
    for cur in ["UZS", "USD", "RUB", "CNY"]:
        markup.add(types.InlineKeyboardButton(cur, callback_data=f"com|{service_type}|{amount}|{cur}"))
    bot.send_message(message.chat.id, "Тўлов қайси валютада қилинди?", reply_markup=markup)

# --- 3. СТАТИСТИКА (МУКАММАЛ ҲИСОБ) ---
@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def stats_engine(message):
    bot.send_chat_action(message.chat.id, 'typing')
    conn = sqlite3.connect('smart_balance_v4.db')
    c = conn.cursor()
    c.execute("SELECT type, amt, cur FROM finance WHERE uid=?", (message.chat.id,))
    rows = c.fetchall()
    
    rates = get_rates()
    total_inc, total_exp = 0.0, 0.0
    
    for t, a, cur in rows:
        val_uzs = a * rates.get(cur, 1.0)
        if t == "inc": total_inc += val_uzs
        else: total_exp += val_uzs
    
    balance = total_inc - total_exp
    status = "💹 Сиз фойдадасиз" if balance >= 0 else "⚠️ Харажат даромаддан кўп"
    
    report = (
        f"📊 **УМУМИЙ ҲИСОБОТ (Сўмда):**\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 Жами Даромад:  {total_inc:,.0f} UZS\n"
        f"💸 Жами Харажат:  {total_exp:,.0f} UZS\n"
        f"━━━━━━━━━━━━━━\n"
        f"⚖️ Соф Баланс:    {balance:,.0f} UZS\n\n"
        f"📌 Ҳолат: {status}"
    )
    bot.send_message(message.chat.id, report, parse_mode="Markdown")
    conn.close()

# --- CALLBACKЛАР (МАЪЛУМОТНИ БАЗАГА МУҲРЛАШ) ---
@bot.callback_query_handler(func=lambda call: True)
def global_callback(call):
    data = call.data.split('|')
    conn = sqlite3.connect('smart_balance_v4.db')
    c = conn.cursor()
    
    if data[0] == "fin": # Finance сақлаш
        _, t, cat, amt, cur = data
        c.execute("INSERT INTO finance (uid, type, cat, amt, cur, date) VALUES (?,?,?,?,?,?)",
                  (call.message.chat.id, t, cat, amt, cur, datetime.now().strftime("%Y-%m-%d")))
        bot.answer_callback_query(call.id, "Маълумот сақланди ✅")
        bot.edit_message_text(f"✅ Сақланди: {cat} ({amt} {cur})", call.message.chat.id, call.message.message_id)

    elif data[0] == "com": # Communal сақлаш
        _, t, amt, cur = data
        c.execute("INSERT INTO communal (uid, type, amt, cur, date) VALUES (?,?,?,?,?)",
                  (call.message.chat.id, t, amt, cur, datetime.now().strftime("%Y-%m-%d")))
        bot.answer_callback_query(call.id, "Коммунал сақланди 🏠")
        bot.edit_message_text(f"🏠 {t} тўлови сақланди: {amt} {cur}", call.message.chat.id, call.message.message_id)

    conn.commit()
    conn.close()

# --- 8. ВАЛЮТА ВА АҚЛЛИ КОНВЕРТЕР ---
@bot.message_handler(func=lambda m: re.search(r'\d+', m.text) and any(x in m.text.upper() for x in ["USD", "CNY", "RUB", "ЮАНЬ", "ДОЛЛАР"]))
def smart_converter(message):
    txt = message.text.upper()
    nums = re.findall(r'\d+', txt)
    rates = get_rates()
    
    amount = float(nums[0])
    target = "USD"
    if "CNY" in txt or "ЮАНЬ" in txt: target = "CNY"
    elif "RUB" in txt or "РУБЛЬ" in txt: target = "RUB"
    
    res = amount * rates[target]
    bot.reply_to(message, f"🔄 **Конвертация:**\n\n{amount} {target} = {res:,.2f} UZS\n(Курс: 1 {target} = {rates[target]} UZS)")

@bot.message_handler(func=lambda m: m.text == "⬅️ Ортга")
def back_to_main(message):
    bot.send_message(message.chat.id, "Асосий менюга қайтдингиз:", reply_markup=main_menu())

@app.route('/')
def home(): return "Smart Balance System is Online"

if __name__ == "__main__":
    init_db()
    # Серверда узлуксиз ишлаш учун Thread
    Thread(target=lambda: app.run(host='0.0.0.0', port=10000)).start()
    bot.polling(none_stop=True)
