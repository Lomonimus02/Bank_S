import logging
import json
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, error  # Добавляем error
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
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
INITIAL_EXCHANGE_RATES = {
    "Русский Музей": 1.0,
    "ЭкоПолис": 1.0,
    "Мариинка": 1.0,
    "Яндекс EdTech": 1.0,
    "Политех": 1.0
}

# Токен бота
TOKEN = "7677941126:AAHc98B6h0rx_twYBtcgyfKWO_F9UFwDMl0"  #  ЗАМЕНИТЕ на свой токен

# ID главного администратора
MAIN_ADMIN_ID = 1115066615  # ЗАМЕНИТЕ на свой ID

# Время простоя до начала сжигания Math (2 часа)
IDLE_TIME_SECONDS = 7200

# Интервал сжигания (1 минута)
BURN_RATE_INTERVAL_SECONDS = 60

# Максимальное количество каждого токена (кроме Math)
MAX_TOKENS = 2500

# Начальные лимиты токенов
INITIAL_TOKEN_LIMITS = {
    "Русский Музей": MAX_TOKENS,
    "ЭкоПолис": MAX_TOKENS,
    "Мариинка": MAX_TOKENS,
    "Яндекс EdTech": MAX_TOKENS,
    "Политех": MAX_TOKENS,
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
            data = json.load(f)
            logger.info(f"Загруженные курсы обмена: {data}")
            if isinstance(data, dict):
                for key, value in INITIAL_EXCHANGE_RATES.items():
                    if key not in data:
                        data[key] = value
                return data
            return INITIAL_EXCHANGE_RATES
    except FileNotFoundError:
        logger.info("Файл exchange_rates.json не найден, используются начальные значения.")
        return INITIAL_EXCHANGE_RATES
    except json.JSONDecodeError:
        logger.error("Ошибка декодирования exchange_rates.json, используются начальные значения.")
        return INITIAL_EXCHANGE_RATES

# Сохранение курсов обмена
def save_exchange_rates(exchange_rates):
    with open(EXCHANGE_RATE_FILE, "w") as f:
        json.dump(exchange_rates, f)

# Загрузка лимитов токенов
def load_token_limits():
    try:
        with open(TOKEN_LIMITS_FILE, "r") as f:
            data = json.load(f)
            logger.info(f"Загруженные лимиты токенов: {data}")
            if isinstance(data, dict):
                for key, value in INITIAL_TOKEN_LIMITS.items():
                    if key not in data:
                        data[key] = value
                return data
            return INITIAL_TOKEN_LIMITS
    except FileNotFoundError:
        logger.info("Файл token_limits.json не найден, используются начальные значения.")
        return INITIAL_TOKEN_LIMITS
    except json.JSONDecodeError:
        logger.error("Ошибка декодирования token_limits.json, используются начальные значения.")
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

# Функция сжигания Math без JobQueue
async def burn_math(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_data = load_user_data()

    if str(user_id) in user_data:
        user = user_data[str(user_id)]
        last_math_update = user.get("last_math_update")
        if last_math_update:
            last_math_update_dt = datetime.datetime.fromisoformat(last_math_update)
            time_since_last_update = datetime.datetime.now() - last_math_update_dt

            if time_since_last_update.total_seconds() >= IDLE_TIME_SECONDS:
                last_burn_check = user.get("last_burn_check")
                if last_burn_check:
                    last_burn_check_dt = datetime.datetime.fromisoformat(last_burn_check)
                    time_since_last_burn = datetime.datetime.now() - last_burn_check_dt

                    if time_since_last_burn.total_seconds() >= BURN_RATE_INTERVAL_SECONDS:
                        if user.get("Math", 0.0) > 0:
                            user["Math"] = max(0.0, user.get("Math", 0.0) - 1.0)
                            user["last_burn_check"] = datetime.datetime.now().isoformat()
                            save_user_data(user_data)
                            try:
                                await context.bot.send_message(user_id, "Сгорел 1 Math из-за длительного бездействия.")
                            except Exception as e:
                                logger.error(f"Ошибка отправки сообщения о сжигании: {e}")
                            logger.info(f"Сгорел 1 Math у пользователя {user_id}. Осталось: {user.get('Math', 0.0)}")
                else:
                    user["last_burn_check"] = datetime.datetime.now().isoformat()
                    save_user_data(user_data)

# --- Обработчики команд ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
    user_id = update.effective_user.id
    user_data = load_user_data()

    if str(user_id) not in user_data:
        await update.message.reply_text("Добро пожаловать! Пожалуйста, введите ваше имя:")
        context.user_data["waiting_for_name"] = True
    else:
        await update.message.reply_text(
            f"С возвращением, {user_data[str(user_id)].get('name','Пользователь')}! Введите /help для команд."
        )

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
    user_id = update.effective_user.id
    if context.user_data.get("waiting_for_name"):
        name = update.message.text
        user_data = load_user_data()
        now = datetime.datetime.now()
        user_data[str(user_id)] = {
            "name": name,
            "Math": 0.0,
            "Русский Музей": 0.0,
            "ЭкоПолис": 0.0,
            "Мариинка": 0.0,
            "Яндекс EdTech": 0.0,
            "Политех": 0.0,
            "last_math_update": now.isoformat(),
            "last_burn_check": None,
        }
        save_user_data(user_data)
        context.user_data["waiting_for_name"] = False
        await update.message.reply_text(
            f"Спасибо, {name}! Вы зарегистрированы. Введите /help для команд."
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
    user_id = update.effective_user.id
    help_text = (
        "Доступные команды:\n"
        "/start - Начать использовать бота\n"
        "/balance - Проверить баланс\n"
        "/totalbalance - Проверить общий баланс в Math\n"
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
            "/give - Выдать Math пользователю\n"
            "/giveeveryone - Выдать Math всем пользователям\n"
            "/addadmin - Назначить администратора\n"
            "/broadcast - Разослать сообщение всем пользователям\n"
        )

    await update.message.reply_text(help_text)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
    user_id = update.effective_user.id
    user_data = load_user_data()
    if str(user_id) in user_data:
        user_balance = user_data[str(user_id)]
        balance_message = (
            f"Ваш баланс, {user_balance.get('name', 'Пользователь')}:\n"
            f"Math: {user_balance.get('Math', 0.0)}\n"
            f"Русский Музей: {user_balance.get('Русский Музей', 0.0)}\n"
            f"ЭкоПолис: {user_balance.get('ЭкоПолис', 0.0)}\n"
            f"Мариинка: {user_balance.get('Мариинка', 0.0)}\n"
            f"Яндекс EdTech: {user_balance.get('Яндекс EdTech', 0.0)}\n"
            f"Политех: {user_balance.get('Политех', 0.0)}\n"
        )
        await update.message.reply_text(balance_message)
    else:
        await update.message.reply_text("Вы не зарегистрированы. Используйте /start.")

async def total_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
    user_id = update.effective_user.id
    user_data = load_user_data()
    if str(user_id) not in user_data:
        await update.message.reply_text("Вы не зарегистрированы. Используйте /start.")
        return

    user_balance = user_data[str(user_id)]
    exchange_rates = load_exchange_rates()

    русский_музей_math = user_balance.get("Русский Музей", 0.0) * exchange_rates.get("Русский Музей", 0.0)
    экополис_math = user_balance.get("ЭкоПолис", 0.0) * exchange_rates.get("ЭкоПолис", 0.0)
    мариинка_math = user_balance.get("Мариинка", 0.0) * exchange_rates.get("Мариинка", 0.0)
    яндекс_edtech_math = user_balance.get("Яндекс EdTech", 0.0) * exchange_rates.get("Яндекс EdTech", 0.0)
    политех_math = user_balance.get("Политех", 0.0) * exchange_rates.get("Политех", 0.0)

    total_math = user_balance.get("Math", 0.0) + русский_музей_math + экополис_math + мариинка_math + яндекс_edtech_math + политех_math

    balance_message = (
        f"Ваш баланс в Math, {user_balance.get('name', 'Пользователь')}:\n"
        f"Math: {user_balance.get('Math', 0.0):.2f}\n"
        f"Русский Музей: {русский_музей_math:.2f} Math\n"
        f"ЭкоПолис: {экополис_math:.2f} Math\n"
        f"Мариинка: {мариинка_math:.2f} Math\n"
        f"Яндекс EdTech: {яндекс_edtech_math:.2f} Math\n"
        f"Политех: {политех_math:.2f} Math\n"
        f"Общий баланс: {total_math:.2f} Math"
    )
    await update.message.reply_text(balance_message)

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
    keyboard = [
        [InlineKeyboardButton("Русский Музей", callback_data="buy_Русский Музей")],
        [InlineKeyboardButton("ЭкоПолис", callback_data="buy_ЭкоПолис")],
        [InlineKeyboardButton("Мариинка", callback_data="buy_Мариинка")],
        [InlineKeyboardButton("Яндекс EdTech", callback_data="buy_Яндекс EdTech")],
        [InlineKeyboardButton("Политех", callback_data="buy_Политех")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите акции для покупки:", reply_markup=reply_markup)

async def button_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
    query = update.callback_query
    await query.answer()
    currency = query.data.split("_")[1]
    context.user_data["selected_currency"] = currency
    context.user_data["operation_type"] = "buy"
    await query.edit_message_text(text=f"Введите количество {currency} для покупки за Math:")
    context.user_data["waiting_for_amount"] = True

async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
    keyboard = [
        [InlineKeyboardButton("Русский Музей", callback_data="sell_Русский Музей")],
        [InlineKeyboardButton("ЭкоПолис", callback_data="sell_ЭкоПолис")],
        [InlineKeyboardButton("Мариинка", callback_data="sell_Мариинка")],
        [InlineKeyboardButton("Яндекс EdTech", callback_data="sell_Яндекс EdTech")],
        [InlineKeyboardButton("Политех", callback_data="sell_Политех")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите акции для продажи:", reply_markup=reply_markup)

async def button_sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
    query = update.callback_query
    await query.answer()
    currency = query.data.split("_")[1]
    context.user_data["selected_currency"] = currency
    context.user_data["operation_type"] = "sell"
    await query.edit_message_text(text=f"Введите количество {currency} для продажи за Math:")
    context.user_data["waiting_for_amount"] = True

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
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
            if user_data[str(user_id)].get("Math", 0.0) < cost:
                await update.message.reply_text("Недостаточно средств.")
                return
            available_tokens = token_limits.get(currency, 0)
            logger.info(f"Покупка {amount} {currency}. Доступно: {available_tokens}, Требуется: {amount}")
            if amount > available_tokens:
                await update.message.reply_text(f"Не хватает {currency}. Доступно: {available_tokens}.")
                return
            user_data[str(user_id)]["Math"] -= cost
            user_data[str(user_id)][currency] = user_data[str(user_id)].get(currency, 0.0) + amount
            token_limits[currency] -= amount
            save_token_limits(token_limits)
            logger.info(f"Успешная покупка {amount} {currency}. Остаток: {token_limits[currency]}")
        elif operation_type == "sell":
            revenue = amount * exchange_rates[currency]
            if user_data[str(user_id)].get(currency, 0.0) < amount:
                await update.message.reply_text(f"Недостаточно {currency} для продажи.")
                return
            user_data[str(user_id)]["Math"] = user_data[str(user_id)].get("Math", 0.0) + revenue
            user_data[str(user_id)][currency] -= amount
            token_limits[currency] += amount
            save_token_limits(token_limits)

        user_data[str(user_id)]["last_math_update"] = datetime.datetime.now().isoformat()
        save_user_data(user_data)
        await update.message.reply_text(
            f"Вы успешно {'купили' if operation_type == 'buy' else 'продали'} {amount} {currency} за {cost if operation_type == 'buy' else revenue:.2f} Math."
        )
        context.user_data["waiting_for_amount"] = False
        context.user_data["selected_currency"] = None
        context.user_data["operation_type"] = None

async def rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
    exchange_rates = load_exchange_rates()
    rates_message = (
        f"Текущие курсы акций:\n"
        f"Русский Музей: {exchange_rates.get('Русский Музей', 'Н/Д')} Math\n"
        f"ЭкоПолис: {exchange_rates.get('ЭкоПолис', 'Н/Д')} Math\n"
        f"Мариинка: {exchange_rates.get('Мариинка', 'Н/Д')} Math\n"
        f"Яндекс EdTech: {exchange_rates.get('Яндекс EdTech', 'Н/Д')} Math\n"
        f"Политех: {exchange_rates.get('Политех', 'Н/Д')} Math\n"
    )
    await update.message.reply_text(rates_message)

async def give(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
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
            user_data[user_id]["Math"] = user_data[user_id].get("Math", 0.0) + amount
            user_data[user_id]["last_math_update"] = datetime.datetime.now().isoformat()
            save_user_data(user_data)
            await update.message.reply_text(
                f"Успешно выдано {amount} Math пользователю {user_data[user_id].get('name', 'Пользователь')} ({user_id})."
            )
        else:
            await update.message.reply_text("Пользователь не найден.")
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /give <имя_или_ID> <количество>")

async def giveeveryone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
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
        user_data[user_id]["Math"] = user_data[user_id].get("Math", 0.0) + amount
        user_data[user_id]["last_math_update"] = datetime.datetime.now().isoformat()
    save_user_data(user_data)
    await update.message.reply_text(f"Успешно выдано {amount} Math всем пользователям.")

async def setrate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("У вас нет разрешения на эту команду.")
        return
    keyboard = [
        [InlineKeyboardButton("Русский Музей", callback_data="setrate_Русский Музей")],
        [InlineKeyboardButton("ЭкоПолис", callback_data="setrate_ЭкоПолис")],
        [InlineKeyboardButton("Мариинка", callback_data="setrate_Мариинка")],
        [InlineKeyboardButton("Яндекс EdTech", callback_data="setrate_Яндекс EdTech")],
        [InlineKeyboardButton("Политех", callback_data="setrate_Политех")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите акцию для установки курса:", reply_markup=reply_markup)

async def button_setrate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
    query = update.callback_query
    await query.answer()
    currency = query.data.split("_")[1]
    if context.user_data.get("waiting_for_setrate_number"):
        return
    context.user_data["selected_currency_setrate"] = currency
    await query.edit_message_text(
        text=f"Введите число от 0 до 100 для курса {currency}\n(0 - снизить на 10%, 1-100 - увеличить на %):"
    )
    context.user_data["waiting_for_setrate_number"] = True

async def get_setrate_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
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

        if number == 0:
            new_rate = current_rate * 0.9  # Снижение на 10%
            change_text = "снижен на 10%"
        else:
            new_rate = current_rate * (1 + number / 100)  # Увеличение на введенный процент
            change_text = f"увеличен на {number}%"

        exchange_rates[currency] = new_rate
        save_exchange_rates(exchange_rates)

        context.user_data["waiting_for_setrate_number"] = False
        context.user_data["selected_currency_setrate"] = None
        await update.message.reply_text(
            f"Курс {currency} {change_text}. Новый курс: {new_rate:.2f} Math"
        )

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания Math
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


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await burn_math(update, context)  # Проверка сжигания
    if not is_admin(update.effective_user.id, main_admin_only=True):
        await update.message.reply_text("У вас нет разрешения на эту команду.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /broadcast <сообщение>")
        return

    message_text = " ".join(context.args)
    user_data = load_user_data()
    successful_sends = 0
    failed_sends = 0
    pinned_messages = 0  # Счетчик закрепленных сообщений

    for user_id in user_data:
        try:
            # Отправляем сообщение и получаем его объект
            sent_message = await context.bot.send_message(chat_id=int(user_id), text=message_text)
            successful_sends += 1

            # Пытаемся закрепить сообщение
            try:
                await context.bot.pin_chat_message(chat_id=int(user_id), message_id=sent_message.message_id)
                pinned_messages += 1
            except error.BadRequest as pin_error: # Более конкретная ошибка
                logger.error(f"Не удалось закрепить сообщение для пользователя {user_id}: {pin_error}")
                failed_sends += 1  # Корректно считаем неудачные закрепления
            except Exception as e:  # Обрабатываем другие возможные ошибки при закреплении
                 logger.error(f"Не удалось закрепить сообщение для пользователя {user_id}: {e}")
                 failed_sends +=1
        except error.TelegramError as send_error: # Обрабатываем ошибки отправки
            logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {send_error}")
            failed_sends += 1 # увеличиваем счетчик ошибок
        except Exception as e:  # Обрабатываем другие возможные ошибки
            logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
            failed_sends += 1 # увеличиваем счетчик ошибок

    await update.message.reply_text(f"Рассылка завершена. Успешно отправлено: {successful_sends}, Неудачно отправлено: {failed_sends}, Закреплено: {pinned_messages}")



def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("totalbalance", total_balance))
    application.add_handler(CommandHandler("buy", buy))
    application.add_handler(CommandHandler("sell", sell))
    application.add_handler(CommandHandler("rates", rates))
    application.add_handler(CommandHandler("give", give))
    application.add_handler(CommandHandler("giveeveryone", giveeveryone))
    application.add_handler(CommandHandler("setrate", setrate))
    application.add_handler(CommandHandler("addadmin", add_admin))
    application.add_handler(CommandHandler("broadcast", broadcast))  # Добавляем обработчик

    application.add_handler(CallbackQueryHandler(button_buy, pattern="^buy_"))
    application.add_handler(CallbackQueryHandler(button_sell, pattern="^sell_"))
    application.add_handler(CallbackQueryHandler(button_setrate, pattern="^setrate_"))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_name), group=1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_setrate_number), group=2)

    exchange_rates = load_exchange_rates()
    if not exchange_rates:
        save_exchange_rates(INITIAL_EXCHANGE_RATES)
        logger.info("Курсы акций инициализированы начальными значениями.")
    else:
        save_exchange_rates(exchange_rates)

    token_limits = load_token_limits()
    if not token_limits or not all(k in token_limits for k in INITIAL_TOKEN_LIMITS):
        save_token_limits(INITIAL_TOKEN_LIMITS)
        logger.info("Лимиты акций инициализированы начальными значениями.")

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