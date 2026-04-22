import logging
import json
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
    JobQueue,
)
import datetime

# Включить логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Файлы хранения данных
USER_DATA_FILE = "user_data.json"
EXCHANGE_RATE_FILE = "exchange_rates.json"
TOKEN_LIMITS_FILE = "token_limits.json"
ADMIN_DATA_FILE = "admin_data.json"

# Начальные курсы обмена
INITIAL_EXCHANGE_RATES = {"M": 1.0, "D": 1.0, "L": 1.0, "F": 1.0, "Y": 1.0}

# Токен бота
TOKEN = "7677941126:AAHc98B6h0rx_twYBtcgyfKWO_F9UFwDMl0"

# ID главного администратора
MAIN_ADMIN_ID = 1115066615

# Время простоя до начала сжигания P (2 часа)
IDLE_TIME_SECONDS = 7200

# Интервал сжигания (1 минута)
BURN_RATE_INTERVAL_SECONDS = 60

# Максимальное количество каждого токена (кроме P)
MAX_TOKENS = 2500

# Начальные лимиты токенов
INITIAL_TOKEN_LIMITS = {
    "M": MAX_TOKENS,
    "D": MAX_TOKENS,
    "L": MAX_TOKENS,
    "F": MAX_TOKENS,
    "Y": MAX_TOKENS,
}

# Загрузка данных пользователя
def load_user_data():
    try:
        with open(USER_DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        logger.error("Ошибка: user_data.json поврежден.")
        return {}

# Сохранение данных пользователя
def save_user_data(user_data):
    with open(USER_DATA_FILE, "w") as f:
        json.dump(user_data, f)

# Загрузка курсов обмена
def load_exchange_rates():
    try:
        with open(EXCHANGE_RATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return INITIAL_EXCHANGE_RATES
    except json.JSONDecodeError:
        logger.error("Ошибка декодирования exchange_rates.json.")
        return INITIAL_EXCHANGE_RATES

# Сохранение курсов обмена
def save_exchange_rates(exchange_rates):
    with open(EXCHANGE_RATE_FILE, "w") as f:
        json.dump(exchange_rates, f)

# Загрузка лимитов токенов
def load_token_limits():
    try:
        with open(TOKEN_LIMITS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return INITIAL_TOKEN_LIMITS
    except json.JSONDecodeError:
        logger.error("Ошибка декодирования token_limits.json.")
        return INITIAL_TOKEN_LIMITS

# Сохранение лимитов токенов
def save_token_limits(token_limits):
    with open(TOKEN_LIMITS_FILE, "w") as f:
        json.dump(token_limits, f)

# Загрузка данных администраторов
def load_admin_data():
    try:
        with open(ADMIN_DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"main_admin": MAIN_ADMIN_ID, "secondary_admins": []}
    except json.JSONDecodeError:
        logger.error("Ошибка декодирования admin_data.json.")
        return {"main_admin": MAIN_ADMIN_ID, "secondary_admins": []}

# Сохранение данных администраторов
def save_admin_data(admin_data):
    with open(ADMIN_DATA_FILE, "w") as f:
        json.dump(admin_data, f)

# Проверка прав администратора
def is_admin(user_id, main_admin_only=False):
    admin_data = load_admin_data()
    if main_admin_only:
        return user_id == admin_data["main_admin"]
    return user_id == admin_data["main_admin"] or user_id in admin_data["secondary_admins"]

# Функция сжигания P
async def burn_p(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    user_id = job.chat_id
    user_data = load_user_data()

    if str(user_id) in user_data:
        user = user_data[str(user_id)]
        last_p_update = user.get("last_p_update")
        if last_p_update:
            last_p_update_dt = datetime.datetime.fromisoformat(last_p_update)
            time_since_last_update = datetime.datetime.now() - last_p_update_dt

            if time_since_last_update.total_seconds() >= IDLE_TIME_SECONDS:
                last_burn_check = user.get("last_burn_check")
                if last_burn_check:
                    last_burn_check_dt = datetime.datetime.fromisoformat(last_burn_check)
                    time_since_last_burn = datetime.datetime.now() - last_burn_check_dt

                    if time_since_last_burn.total_seconds() >= BURN_RATE_INTERVAL_SECONDS:
                        if user.get("P", 0.0) > 0:
                            user["P"] = max(0.0, user.get("P", 0.0) - 1.0)
                            user["last_burn_check"] = datetime.datetime.now().isoformat()
                            save_user_data(user_data)
                            try:
                                await context.bot.send_message(user_id, "Сгорел 1 P из-за длительного бездействия.")
                            except Exception as e:
                                logger.error(f"Ошибка отправки сообщения о сжигании: {e}")
                            logger.info(f"Сгорел 1 P у пользователя {user_id}. Осталось: {user.get('P', 0.0)}")
                else:
                    user["last_burn_check"] = datetime.datetime.now().isoformat()
                    save_user_data(user_data)

# Установка таймера сжигания
def set_burn_timer(application: Application, user_id: int) -> None:
    chat_id = user_id
    job_queue = application.job_queue
    if job_queue:
        for job in job_queue.get_jobs_by_name(str(chat_id)):
            job.schedule_removal()
        job_queue.run_repeating(
            burn_p, interval=60, first=1, chat_id=chat_id, name=str(chat_id)
        )

# --- Обработчики команд ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_data = load_user_data()

    if str(user_id) not in user_data:
        await update.message.reply_text("Добро пожаловать! Пожалуйста, введите ваше имя:")
        context.user_data["waiting_for_name"] = True
    else:
        await update.message.reply_text(
            f"С возвращением, {user_data[str(user_id)].get('name','Пользователь')}! Введите /help для команд."
        )
        set_burn_timer(context.application, user_id)

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if context.user_data.get("waiting_for_name"):
        name = update.message.text
        user_data = load_user_data()
        now = datetime.datetime.now()
        user_data[str(user_id)] = {
            "name": name,
            "P": 0.0,
            "M": 0.0,
            "D": 0.0,
            "L": 0.0,
            "F": 0.0,
            "Y": 0.0,
            "last_p_update": now.isoformat(),
            "last_burn_check": None,
        }
        save_user_data(user_data)
        context.user_data["waiting_for_name"] = False
        await update.message.reply_text(
            f"Спасибо, {name}! Вы зарегистрированы. Введите /help для команд."
        )
        set_burn_timer(context.application, user_id)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    help_text = (
        "Доступные команды:\n"
        "/start - Начать использовать бота\n"
        "/balance - Проверить баланс\n"
        "/totalbalance - Проверить общий баланс в P\n"
        "/buy - Купить акции\n"
        "/sell - Продать акции\n"
        "/rates - Посмотреть текущие курсы акций\n"
        "/help - Показать это сообщение\n\n"
    )
    
    if is_admin(user_id):
        help_text += (
            "Команды администратора:\n"
            "/setrate - Установить курс акций\n"
        )
    
    if is_admin(user_id, main_admin_only=True):
        help_text += (
            "Команды главного администратора:\n"
            "/give - Выдать P пользователю\n"
            "/giveeveryone - Выдать P всем пользователям\n"
            "/addadmin - Назначить администратора\n"
        )
    
    await update.message.reply_text(help_text)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_data = load_user_data()
    if str(user_id) in user_data:
        user_balance = user_data[str(user_id)]
        balance_message = (
            f"Ваш баланс, {user_balance.get('name', 'Пользователь')}:\n"
            f"P: {user_balance.get('P', 0.0)} P\n"
            f"M: {user_balance.get('M', 0.0)} M\n"
            f"D: {user_balance.get('D', 0.0)} D\n"
            f"L: {user_balance.get('L', 0.0)} L\n"
            f"F: {user_balance.get('F', 0.0)} F\n"
            f"Y: {user_balance.get('Y', 0.0)} Y\n"
        )
        await update.message.reply_text(balance_message)
    else:
        await update.message.reply_text("Вы не зарегистрированы. Используйте /start.")

# Новая команда /totalbalance
async def total_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_data = load_user_data()
    if str(user_id) not in user_data:
        await update.message.reply_text("Вы не зарегистрированы. Используйте /start.")
        return
    
    user_balance = user_data[str(user_id)]
    exchange_rates = load_exchange_rates()
    
    # Вычисляем общий баланс в P
    total_p = user_balance.get("P", 0.0)
    total_p += user_balance.get("M", 0.0) * exchange_rates.get("M", 0.0)
    total_p += user_balance.get("D", 0.0) * exchange_rates.get("D", 0.0)
    total_p += user_balance.get("L", 0.0) * exchange_rates.get("L", 0.0)
    total_p += user_balance.get("F", 0.0) * exchange_rates.get("F", 0.0)
    total_p += user_balance.get("Y", 0.0) * exchange_rates.get("Y", 0.0)
    
    balance_message = (
        f"Ваш общий баланс в P, {user_balance.get('name', 'Пользователь')}:\n"
        f"Общий баланс: {total_p:.2f} P"
    )
    await update.message.reply_text(balance_message)

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton("M", callback_data="buy_M"),
            InlineKeyboardButton("D", callback_data="buy_D"),
            InlineKeyboardButton("L", callback_data="buy_L"),
            InlineKeyboardButton("F", callback_data="buy_F"),
            InlineKeyboardButton("Y", callback_data="buy_Y"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите акции для покупки:", reply_markup=reply_markup)

async def button_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    currency = query.data.split("_")[1]
    context.user_data["selected_currency"] = currency
    context.user_data["operation_type"] = "buy"
    await query.edit_message_text(text=f"Введите количество {currency} для покупки за P:")
    context.user_data["waiting_for_amount"] = True

async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton("M", callback_data="sell_M"),
            InlineKeyboardButton("D", callback_data="sell_D"),
            InlineKeyboardButton("L", callback_data="sell_L"),
            InlineKeyboardButton("F", callback_data="sell_F"),
            InlineKeyboardButton("Y", callback_data="sell_Y"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите акции для продажи:", reply_markup=reply_markup)

async def button_sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    currency = query.data.split("_")[1]
    context.user_data["selected_currency"] = currency
    context.user_data["operation_type"] = "sell"
    await query.edit_message_text(text=f"Введите количество {currency} для продажи за P:")
    context.user_data["waiting_for_amount"] = True

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if context.user_data.get("waiting_for_amount"):
        amount_str = update.message.text
        currency = context.user_data["selected_currency"]
        operation_type = context.user_data["operation_type"]
        user_data = load_user_data()
        exchange_rates = load_exchange_rates()
        token_limits = load_token_limits()

        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Введите положительное число.")
            return

        if operation_type == "buy":
            cost = amount * exchange_rates[currency]
            if user_data[str(user_id)].get("P", 0.0) < cost:
                await update.message.reply_text("Недостаточно средств.")
                return
            available_tokens = token_limits.get(currency, 0)
            if amount > available_tokens:
                await update.message.reply_text(f"Не хватает {currency}. Доступно: {available_tokens}.")
                return
            user_data[str(user_id)]["P"] -= cost
            user_data[str(user_id)][currency] = user_data[str(user_id)].get(currency, 0.0) + amount
            token_limits[currency] -= amount
            save_token_limits(token_limits)
        elif operation_type == "sell":
            revenue = amount * exchange_rates[currency]
            if user_data[str(user_id)].get(currency, 0.0) < amount:
                await update.message.reply_text(f"Недостаточно {currency} для продажи.")
                return
            user_data[str(user_id)]["P"] = user_data[str(user_id)].get("P", 0.0) + revenue
            user_data[str(user_id)][currency] -= amount
            token_limits[currency] += amount
            save_token_limits(token_limits)

        user_data[str(user_id)]["last_p_update"] = datetime.datetime.now().isoformat()
        save_user_data(user_data)
        await update.message.reply_text(
            f"Вы успешно {'купили' if operation_type == 'buy' else 'продали'} {amount} {currency} за {cost if operation_type == 'buy' else revenue:.2f} P."
        )
        context.user_data["waiting_for_amount"] = False
        context.user_data["selected_currency"] = None
        context.user_data["operation_type"] = None

async def rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    exchange_rates = load_exchange_rates()
    rates_message = (
        f"Текущие курсы акций:\n"
        f"M: {exchange_rates.get('M', 'Н/Д')} P\n"
        f"D: {exchange_rates.get('D', 'Н/Д')} P\n"
        f"L: {exchange_rates.get('L', 'Н/Д')} P\n"
        f"F: {exchange_rates.get('F', 'Н/Д')} P\n"
        f"Y: {exchange_rates.get('Y', 'Н/Д')} P\n"
    )
    await update.message.reply_text(rates_message)

async def give(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id, main_admin_only=True):
        await update.message.reply_text("У вас нет разрешения на эту команду.")
        return
    try:
        user_data = load_user_data()
        user_name_or_id = context.args[0]
        amount = float(context.args[1])
        user_id = None
        for uid, data in user_data.items():
            if data.get("name") == user_name_or_id or uid == user_name_or_id:
                user_id = uid
                break
        if user_id:
            user_data[user_id]["P"] = user_data[user_id].get("P", 0.0) + amount
            user_data[user_id]["last_p_update"] = datetime.datetime.now().isoformat()
            save_user_data(user_data)
            await update.message.reply_text(
                f"Успешно выдано {amount} P пользователю {user_data[user_id].get('name', 'Пользователь')} ({user_id})."
            )
        else:
            await update.message.reply_text("Пользователь не найден.")
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /give <имя_или_ID> <количество>")

async def giveeveryone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id, main_admin_only=True):
        await update.message.reply_text("У вас нет разрешения на эту команду.")
        return
    try:
        amount = float(context.args[0])
        if amount <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /giveeveryone <количество>")
        return
    user_data = load_user_data()
    for user_id in user_data:
        user_data[user_id]["P"] = user_data[user_id].get("P", 0.0) + amount
        user_data[user_id]["last_p_update"] = datetime.datetime.now().isoformat()
    save_user_data(user_data)
    await update.message.reply_text(f"Успешно выдано {amount} P всем пользователям.")

async def setrate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("У вас нет разрешения на эту команду.")
        return
    keyboard = [
        [
            InlineKeyboardButton("M", callback_data="setrate_M"),
            InlineKeyboardButton("D", callback_data="setrate_D"),
            InlineKeyboardButton("L", callback_data="setrate_L"),
            InlineKeyboardButton("F", callback_data="setrate_F"),
            InlineKeyboardButton("Y", callback_data="setrate_Y"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите акцию для установки курса:", reply_markup=reply_markup)

async def button_setrate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    currency = query.data.split("_")[1]
    if context.user_data.get("waiting_for_setrate_number"):
        return
    context.user_data["selected_currency_setrate"] = currency
    await query.edit_message_text(
        text=f"Введите число (множитель относительно P) от 0 до 100 для курса {currency}:"
    )
    context.user_data["waiting_for_setrate_number"] = True

async def get_setrate_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("waiting_for_setrate_number"):
        try:
            number = float(update.message.text)
            if not 0 <= number <= 100:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Введите число от 0 до 100.")
            return
        currency = context.user_data["selected_currency_setrate"]
        exchange_rates = load_exchange_rates()
        current_rate = exchange_rates[currency]
        if number == 75:
            new_rate = current_rate
        elif number > 75:
            new_rate = current_rate * 2
        else:
            new_rate = current_rate * number / 75.0
        exchange_rates[currency] = new_rate
        save_exchange_rates(exchange_rates)
        context.user_data["waiting_for_setrate_number"] = False
        context.user_data["selected_currency_setrate"] = None
        await update.message.reply_text(f"Курс {currency} установлен на {new_rate:.2f}.")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id, main_admin_only=True):
        await update.message.reply_text("Только главный администратор может назначать администраторов.")
        return
    try:
        user_data = load_user_data()
        admin_data = load_admin_data()
        user_name_or_id = context.args[0]
        user_id = None
        for uid, data in user_data.items():
            if data.get("name") == user_name_or_id or uid == user_name_or_id:
                user_id = uid
                break
        if not user_id:
            await update.message.reply_text("Пользователь не найден.")
            return
        if int(user_id) in admin_data["secondary_admins"]:
            await update.message.reply_text("Этот пользователь уже администратор.")
            return
        admin_data["secondary_admins"].append(int(user_id))
        save_admin_data(admin_data)
        await update.message.reply_text(
            f"Пользователь {user_data[user_id].get('name', 'Пользователь')} ({user_id}) назначен администратором."
        )
    except IndexError:
        await update.message.reply_text("Использование: /addadmin <имя_или_ID>")

def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("totalbalance", total_balance))  # Новая команда
    application.add_handler(CommandHandler("buy", buy))
    application.add_handler(CommandHandler("sell", sell))
    application.add_handler(CommandHandler("rates", rates))
    application.add_handler(CommandHandler("give", give))
    application.add_handler(CommandHandler("giveeveryone", giveeveryone))
    application.add_handler(CommandHandler("setrate", setrate))
    application.add_handler(CommandHandler("addadmin", add_admin))

    application.add_handler(CallbackQueryHandler(button_buy, pattern="^buy_"))
    application.add_handler(CallbackQueryHandler(button_sell, pattern="^sell_"))
    application.add_handler(CallbackQueryHandler(button_setrate, pattern="^setrate_"))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_name), group=1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_setrate_number), group=2)

    exchange_rates = load_exchange_rates()
    if not exchange_rates:
        save_exchange_rates(INITIAL_EXCHANGE_RATES)
        logger.info("Курсы акций инициализированы.")

    token_limits = load_token_limits()
    if not token_limits:
        save_token_limits(INITIAL_TOKEN_LIMITS)
        logger.info("Лимиты акций инициализированы.")

    user_data = load_user_data()
    if not user_data:
        save_user_data({})
        logger.info("Данные пользователя инициализированы.")

    admin_data = load_admin_data()
    if not admin_data.get("main_admin"):
        admin_data = {"main_admin": MAIN_ADMIN_ID, "secondary_admins": []}
        save_admin_data(admin_data)
        logger.info("Данные администраторов инициализированы.")

    application.run_polling()

if __name__ == "__main__":
    main()