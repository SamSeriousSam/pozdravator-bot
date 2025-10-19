import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import openai
from datetime import datetime, timedelta
import random

# --- НАЧАЛО: Импорт и настройка кэширования для лимита запросов ---
# pip install aiocache (если будет использоваться)
# from aiocache import cached, Cache
# cache = Cache(Cache.MEMORY)

# Для простоты без Redis, используем словарь (данные потеряются при перезапуске)
# В реальном проекте - используйте Redis
request_times = {}
# --- КОНЕЦ: Лимит запросов ---

# Читаем токены из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Проверяем, что токены загружены
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не найден в переменных окружения")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не найден в переменных окружения")

# Установка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Подавляем httpx логи
logging.getLogger("httpx").setLevel(logging.WARNING)

# Подавляем PTBUserWarning для per_message
import warnings
from telegram.warnings import PTBUserWarning
warnings.filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

# Определяем шаги разговора
CATEGORY, SUBCATEGORY, EMOJIS, NAME, GENERATE, FEEDBACK = range(6)

# --- НАЧАЛО: Организация категорий ---
# Основные категории
MAIN_CATEGORIES = {
    "toast": "🥂 Тосты",
    "birthday": "🎂 Дни рождения",
    "professional": "💼 Рабочие и профессиональные",
    "seasonal": "🎄 Календарные / сезонные",
    "personal": "❤️ Личные поводы и достижения",
    "family": "👨‍👩‍👧‍👦 Семейные",
    "donate": "☕ Поддержать проект",
    "feedback": "✉️ Обратная связь",
}

# Подкатегории
SUBCATEGORIES = {
    "toast": {
        "toast_corporate": "На корпоративе",
        "toast_wedding": "На свадьбе",
        "toast_new_year": "На Новый год",
        "toast_birthday": "На день рождения",
        "toast_farewell": "Прощальный",
        "toast_cocktail": "Коктейльный час",
        "toast_romantic": "Романтический",
        "toast_funny": "С юмором",
    },
    "birthday": {
        "bd_gen": "универсальное",
        "bd_friend": "для друзей",
        "bd_relatives": "для родных",
        "bd_colleague": "для коллег",
        "bd_mother": "для мамы",
        "bd_father": "для папы",
        "bd_grandmother": "для бабушки",
        "bd_grandfather": "для дедушки",
        "bd_sister": "для сестры",
        "bd_brother": "для брата",
        "bd_child": "для ребёнка",
        "bd_girlfriend": "для девушки",
        "bd_boyfriend": "для молодого человека",
    },
    "professional": {
        "defender_day": "С днём защитника Отечества",
        "womens_day": "С 8 марта",
        "teachers_day": "С днём учителя",
        "doctors_day": "С днём врача",
        "programmers_day": "С днём программиста",
        "police_day": "С днём полиции",
        "prosecutor_day": "С днём прокуратуры",
        "lawyers_day": "С днём юриста",
        "company_day": "С днём компании",
        "promotion": "С повышением",
        "retirement": "С выходом на пенсию",
        "project_success": "С успешным проектом",
        "report_submitted": "С сдачей отчёта",
        "vacation_start": "С началом отпуска",
        "vacation_end": "С окончанием отпуска",
    },
    "seasonal": {
        "new_year": "С Новым годом",
        "xmas": "С Рождеством",
        "easter": "С Пасхой",
        "victory_day": "С Днём Победы",
        "city_day": "С Днём города",
        "independence_day": "С Днём независимости",
        "spring_start": "С началом весны",
        "summer_start": "С началом лета",
        "autumn_start": "С началом осени",
        "winter_start": "С началом зимы",
        "sep_1": "С 1 сентября",
    },
    "personal": {
        "graduation": "С окончанием учёбы",
        "diploma": "С получением диплома",
        "car_purchase": "С покупкой машины",
        "apartment_purchase": "С покупкой квартиры",
        "house_purchase": "С покупкой дома",
        "victory": "С победой",
        "award": "С наградой",
        "sports_success": "Со спортивным успехом",
        "recovery": "С выздоровлением",
        "discharge": "С выпиской",
        "relations_anniversary": "С годовщиной отношений",
        "friendship_anniversary": "С годовщиной дружбы",
        "move": "С переездом",
        "new_job": "С новой работой",
    },
    "family": {
        "birth_child": "С рождением ребёнка",
        "wedding": "Со свадьбой",
        "engagement": "С помолвкой",
        "proposal": "С предложением руки и сердца",
        "wedding_anniversary": "С годовщиной свадьбы",
        "mothers_day": "С днём матери",
        "fathers_day": "С днём отца",
        "family_day": "С днём семьи",
        "valentines_day": "С днём святого Валентина",
        "name_day": "С днём ангела",
        "new_home": "С новосельем",
    },
}

# Внутренние значения для GPT
CATEGORY_INTERNAL = {
    "toast_corporate": "тост на корпоративе",
    "toast_wedding": "тост на свадьбе",
    "toast_new_year": "тост на Новый год",
    "toast_birthday": "тост на день рождения",
    "toast_farewell": "прощальный тост",
    "toast_cocktail": "тост на коктейльном часу",
    "toast_romantic": "романтический тост",
    "toast_funny": "тост с юмором",
    "bd_gen": "день рождения",
    "bd_friend": "день рождения для друзей",
    "bd_relatives": "день рождения для родных",
    "bd_colleague": "день рождения для коллег",
    "bd_mother": "день рождения для мамы",
    "bd_father": "день рождения для папы",
    "bd_grandmother": "день рождения для бабушки",
    "bd_grandfather": "день рождения для дедушки",
    "bd_sister": "день рождения для сестры",
    "bd_brother": "день рождения для брата",
    "bd_child": "день рождения для ребёнка",
    "bd_girlfriend": "день рождения для девушки",
    "bd_boyfriend": "день рождения для молодого человека",
    "defender_day": "23 февраля",
    "womens_day": "8 марта",
    "teachers_day": "день учителя",
    "doctors_day": "день врача",
    "programmers_day": "день программиста",
    "police_day": "день полиции",
    "prosecutor_day": "день прокуратуры",
    "lawyers_day": "день юриста",
    "company_day": "день компании",
    "promotion": "повышение",
    "retirement": "выход на пенсию",
    "project_success": "успешный проект",
    "report_submitted": "сдача отчёта",
    "vacation_start": "начало отпуска",
    "vacation_end": "окончание отпуска",
    "new_year": "Новый год",
    "xmas": "Рождество",
    "easter": "Пасха",
    "victory_day": "9 мая",
    "city_day": "день города",
    "independence_day": "день независимости",
    "spring_start": "начало весны",
    "summer_start": "начало лета",
    "autumn_start": "начало осени",
    "winter_start": "начало зимы",
    "sep_1": "1 сентября",
    "graduation": "окончание учёбы",
    "diploma": "получение диплома",
    "car_purchase": "покупка машины",
    "apartment_purchase": "покупка квартиры",
    "house_purchase": "покупка дома",
    "victory": "победа",
    "award": "награда",
    "sports_success": "спортивный успех",
    "recovery": "выздоровление",
    "discharge": "выписка",
    "relations_anniversary": "годовщина отношений",
    "friendship_anniversary": "годовщина дружбы",
    "move": "переезд",
    "new_job": "новая работа",
    "birth_child": "рождение ребёнка",
    "wedding": "свадьба",
    "engagement": "помолвка",
    "proposal": "предложение руки и сердца",
    "wedding_anniversary": "годовщина свадьбы",
    "mothers_day": "день матери",
    "fathers_day": "день отца",
    "family_day": "день семьи",
    "valentines_day": "День святого Валентина",
    "name_day": "день ангела",
    "new_home": "новоселье",
}

# --- КОНЕЦ: Организация категорий ---

# --- НАЧАЛО: Смайлики для категорий ---
EMOJI_MAP = {
    "toast_corporate": "🥂🍻👨‍💼👩‍💼🎉",
    "toast_wedding": "🥂💍👰🤵💐",
    "toast_new_year": "🥂🍾🎆🎉",
    "toast_birthday": "🥂🎂🎈🎁",
    "toast_farewell": "🥂👋✈️🎉",
    "toast_cocktail": "🥂🍸🍹",
    "toast_romantic": "🥂💕🌹",
    "toast_funny": "🥂😂🎉",
    "birthday": "🎉🎂🎈🎁🎊",
    "new_year": "🎄❄️⛄🎁✨",
    "wedding": "💍👰🤵💐💒",
    "wedding_anniversary": "💍💕🥂🎉",
    "graduation": "🎓🎓📚🎉",
    "car_purchase": "🚗💨🏁",
    "apartment_purchase": "🏠🔑🎊",
    "house_purchase": "🏠🏡🎊",
    "victory": "🏆🎯🎉",
    "award": "🏆🏅🎉",
    "sports_success": "🏆⚽🏀🎾",
    "recovery": "🩹💊✅",
    "discharge": "🏥✅🩺",
    "relations_anniversary": "💕🌹🥂",
    "friendship_anniversary": "🤝💕🎉",
    "move": "🏠🚚📦",
    "new_job": "💼👔🎉",
    "promotion": "💼📈🎉",
    "retirement": "🎉🏖️👴👵",
    "project_success": "🚀🎯🎉",
    "report_submitted": "📋✅🎉",
    "vacation_start": "✈️🏖️☀️",
    "vacation_end": "🏠💼📅",
    "valentines_day": "💕🌹🍫💝",
    "name_day": "🎂🎉🎈",
    "new_home": "🏠🎉🎊",
    "mothers_day": "👩💐💕",
    "fathers_day": "👨💼🎉",
    "family_day": "👨‍👩‍👧‍👦💕🎉",
    "defender_day": "🎖️👨‍✈️🎉",
    "womens_day": "🌷👩🎉",
    "teachers_day": "📚👩‍🏫🍎",
    "doctors_day": "🏥👨‍⚕️💊",
    "programmers_day": "💻⌨️👨‍💻",
    "police_day": "🚔👮‍♂️🎖️",
    "prosecutor_day": "⚖️👨‍💼🎉",
    "lawyers_day": "⚖️👨‍💼🎉",
    "company_day": "🏢🎉💼",
    "birth_child": "👶🍼💕",
    "engagement": "💍💕👰🤵",
    "proposal": "💍💕🌹",
    "xmas": "🎄🎁🎅❄️",
    "easter": "🐰🥚🌸✝️",
    "victory_day": "🎉🎖️🇷🇺",
    "city_day": "🏙️🎊🎉",
    "independence_day": "🎉🎆🇺🇸",
    "spring_start": "🌸🌼☀️",
    "summer_start": "☀️🏖️🏊‍♂️",
    "autumn_start": "🍁🍃☕",
    "winter_start": "❄️⛄🎿",
    "sep_1": "📚🎒🎓",
    "diploma": "🎓📜🎉",
    # Общие смайлики
    "default": "🎉✨🎊"
}
# --- КОНЕЦ: Смайлики ---

# --- НАЧАЛО: Лимит запросов ---
REQUEST_LIMIT_PER_MINUTE = 3
def is_rate_limited(user_id):
    now = datetime.now()
    user_requests = request_times.get(user_id, [])
    # Удаляем старые запросы (старше 1 минуты)
    user_requests = [req_time for req_time in user_requests if now - req_time < timedelta(minutes=1)]
    if len(user_requests) >= REQUEST_LIMIT_PER_MINUTE:
        return True, now + timedelta(minutes=1) - user_requests[0] # Возвращаем время сброса
    user_requests.append(now)
    request_times[user_id] = user_requests
    return False, None
# --- КОНЕЦ: Лимит запросов ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Приветственное сообщение
    welcome_text = (
        "Привет! 👋\n\n"
        "Я помогу вам быстро и красиво поздравить кого угодно.\n"
        "Выберите, что вас интересует:"
    )
    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in MAIN_CATEGORIES.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Проверяем, это команда /start или callback
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup)
    
    return CATEGORY

async def choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    category_key = query.data

    if category_key == "donate":
        bot_username = os.getenv("BOT_USERNAME")
        if bot_username:
            donate_url = f"https://t.me/{bot_username}?start=donate"
            keyboard = [
                [InlineKeyboardButton("Поддержать проект", url=donate_url)],
                [InlineKeyboardButton("Назад", callback_data="back_to_main_category")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Спасибо, что хотите поддержать проект! 🙏\n\n"
                "Этот бот не содержит рекламы и разрабатывается на личные средства.\n"
                "Ваш вклад поможет покрыть расходы на хостинг и дальнейшее развитие.\n\n"
                "Нажмите кнопку ниже, чтобы поддержать проект через Telegram Stars.",
                reply_markup=reply_markup
            )
        else:
            keyboard = [[InlineKeyboardButton("Назад", callback_data="back_to_main_category")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Спасибо, что хотите поддержать проект! 🙏\n\n"
                "К сожалению, пока невозможно поддержать проект через Telegram Stars. Мы работаем над этим.\n\n"
                "Установите переменную окружения BOT_USERNAME для активации донатов.",
                reply_markup=reply_markup
            )
        return CATEGORY

    if category_key == "feedback":
        keyboard = [[InlineKeyboardButton("Назад", callback_data="back_to_main_category")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Напишите ваше сообщение для обратной связи:", reply_markup=reply_markup)
        return FEEDBACK

    context.user_data['main_category'] = category_key

    subcats = SUBCATEGORIES.get(category_key, {})
    if not subcats:
        # Если подкатегорий нет, перейти к выбору смайликов
        context.user_data['subcategory_key'] = category_key
        if category_key == "toast":
            # Для тостов сразу спрашиваем про смайлики
            keyboard = [
                [InlineKeyboardButton("Да", callback_data="emojis_yes")],
                [InlineKeyboardButton("Нет", callback_data="emojis_no")],
                [InlineKeyboardButton("Назад", callback_data="back_to_main_category")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Добавить смайлики в тост?", reply_markup=reply_markup)
            return EMOJIS
        else:
            # Для других - сразу к смайликам
            keyboard = [
                [InlineKeyboardButton("Да", callback_data="emojis_yes")],
                [InlineKeyboardButton("Нет", callback_data="emojis_no")],
                [InlineKeyboardButton("Назад", callback_data="back_to_main_category")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Добавить смайлики?", reply_markup=reply_markup)
            return EMOJIS

    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in subcats.items()
    ]
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_main_category")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"Выбрана категория: {MAIN_CATEGORIES[category_key]}\nВыберите подкатегорию:", reply_markup=reply_markup)
    return SUBCATEGORY

async def choose_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    subcategory_key = query.data
    context.user_data['subcategory_key'] = subcategory_key

    # Для всех категорий спрашиваем про смайлики
    keyboard = [
        [InlineKeyboardButton("Да", callback_data="emojis_yes")],
        [InlineKeyboardButton("Нет", callback_data="emojis_no")],
        [InlineKeyboardButton("Назад", callback_data="back_to_category")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if context.user_data.get('main_category') == 'toast':
        await query.edit_message_text("Добавить смайлики в тост?", reply_markup=reply_markup)
    else:
        await query.edit_message_text("Добавить смайлики?", reply_markup=reply_markup)
    
    return EMOJIS

async def choose_emojis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    emoji_choice = query.data
    if emoji_choice == "emojis_yes":
        context.user_data['emojis'] = True
    else:
        context.user_data['emojis'] = False

    keyboard = [
        [InlineKeyboardButton("Пропустить", callback_data="skip_name")],
        [InlineKeyboardButton("Назад", callback_data="back_to_emojis")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Введите имя или уточнение (например, 'для коллеги', 'для мамы'), или нажмите 'Пропустить':", reply_markup=reply_markup)
    return NAME

async def back_to_main_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    welcome_text = (
        "Привет! 👋\n\n"
        "Я помогу вам быстро и красиво поздравить кого угодно.\n"
        "Выберите, что вас интересует:"
    )
    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in MAIN_CATEGORIES.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(welcome_text, reply_markup=reply_markup)
    return CATEGORY

async def back_to_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    category_key = context.user_data.get('main_category')
    if category_key:
        subcats = SUBCATEGORIES.get(category_key, {})
        if subcats:
            keyboard = [
                [InlineKeyboardButton(text, callback_data=key)] for key, text in subcats.items()
            ]
            keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_main_category")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"Выбрана категория: {MAIN_CATEGORIES[category_key]}\nВыберите подкатегорию:", reply_markup=reply_markup)
            return SUBCATEGORY
        else:
            # Если подкатегорий нет, вернуться к главному меню
            return await back_to_main_category(update, context)
    else:
        return await back_to_main_category(update, context)

async def back_to_emojis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    # Возвращаемся к выбору смайликов
    keyboard = [
        [InlineKeyboardButton("Да", callback_data="emojis_yes")],
        [InlineKeyboardButton("Нет", callback_data="emojis_no")],
        [InlineKeyboardButton("Назад", callback_data="back_to_category")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if context.user_data.get('main_category') == 'toast':
        await query.edit_message_text("Добавить смайлики в тост?", reply_markup=reply_markup)
    else:
        await query.edit_message_text("Добавить смайлики?", reply_markup=reply_markup)
    
    return EMOJIS

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text
    context.user_data['name'] = name
    
    # Отправляем сообщение о генерации
    sent_message = await update.message.reply_text("Генерирую... ⏳")
    context.user_data['generating_message_id'] = sent_message.message_id
    
    await generate_message(update, context)
    return GENERATE

async def skip_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['name'] = None
    await query.edit_message_text("Генерирую... ⏳")
    await generate_message_callback(update, context)
    return GENERATE

async def generate_message_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await generate_message(query, context)
    return GENERATE

async def generate_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Проверяем, является ли update объектом CallbackQuery
    if hasattr(update, 'from_user') and hasattr(update, 'message'):
        # Это CallbackQuery
        user_id = update.from_user.id
        message_obj = update.message
    else:
        # Это обычный Update
        user_id = update.effective_user.id
        message_obj = update.message

    # Проверка лимита
    is_limited, reset_time = is_rate_limited(user_id)
    if is_limited:
        if reset_time:
            minutes_left = int(reset_time.total_seconds() // 60)
            seconds_left = int(reset_time.total_seconds() % 60)
            await message_obj.reply_text(f"Превышен лимит запросов. Попробуйте через {minutes_left} мин {seconds_left} сек.")
        else:
            await message_obj.reply_text("Превышен лимит запросов. Попробуйте позже.")
        return GENERATE

    subcategory_key = context.user_data.get('subcategory_key')
    name = context.user_data.get('name', "друга")
    emojis = context.user_data.get('emojis', False)

    category_internal = CATEGORY_INTERNAL.get(subcategory_key, "праздник")

    # Выбираем смайлики на основе подкатегории
    emoji_string = EMOJI_MAP.get(subcategory_key, EMOJI_MAP.get(category_internal.split()[0], EMOJI_MAP["default"])) if emojis else ""
    emoji_instruction = f"Разрешено использовать следующие смайлики: {emoji_string}. Распредели их равномерно по всем трём вариантам, от 10 до 20 штук в каждом, чтобы они были уместны и не повторялись часто внутри одного варианта." if emojis else "Не использовать смайлы."

    name_part = f"поздравь {name}" if name else "поздравление для друга"

    # Промт для тостов
    if subcategory_key.startswith('toast_'):
        prompt = f"""
Создай 3 разных популярных {category_internal}, которые существуют и часто используются.
{emoji_instruction}
Адресат: {name_part}.
Язык: русский.
Требования:
- Это должны быть **реальные**, **существующие** тосты, **не придуманные**.
- Без повторов фраз между вариантами.
- Без клише "желаю счастья, здоровья".
- Сохрани естественный ритм речи.
- Избегай длинных тире (—), используй короткие (-) или просто пробел.
- Пиши от первого лица ("Поздравляю", "От всей души", "С теплом в сердце").
- Не использовать "ChatGPT", "OpenAI" или подобные обращения.
- Варианты должны быть короткими и по делу.
- Всегда возвращай 3 варианта в виде пронумерованного списка.
"""
        system_prompt = "Ты — профессиональный автор тостов. Пиши на русском языке. Возвращай 3 популярных, существующих тоста в виде пронумерованного списка. Используй короткие тире (-). Если разрешены смайлики, распредели их равномерно по всем трём вариантам, от 10 до 20 штук в каждом, чтобы они были уместны и не повторялись часто внутри одного варианта."
    else:
        # Промт для поздравлений
        prompt = f"""
Создай 3 разных {category_internal} в прозе или стихе.
{emoji_instruction}
Адресат: {name_part}.
Язык: русский.
Требования:
- Без повторов фраз между вариантами.
- Без клише "желаю счастья, здоровья".
- Сохрани естественный ритм речи.
- Избегай длинных тире (—), используй короткие (-) или просто пробел.
- Пиши от первого лица ("Поздравляю", "От всей души", "С теплом в сердце").
- Не использовать "ChatGPT", "OpenAI" или подобные обращения.
- Варианты должны быть короткими и по делу.
- Всегда возвращай 3 варианта в виде пронумерованного списка.
"""
        system_prompt = "Ты — профессиональный автор поздравлений и тостов. Пиши на русском языке. Не используй восклицательные знаки подряд (макс. 1), избегай шаблонов 'желаю счастья, здоровья'. Всегда возвращай 3 варианта в виде пронумерованного списка. Используй короткие тире (-). Если разрешены смайлики, распредели их равномерно по всем трём вариантам, от 10 до 20 штук в каждом, чтобы они были уместны и не повторялись часто внутри одного варианта."

    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.7
        )

        message_text = response.choices[0].message.content
        # Отправляем 3 сообщения отдельно
        parts = message_text.split("\n\n")
        for part in parts:
            if part.strip():
                # Убираем нумерацию, если она есть
                clean_part = part.strip()
                if clean_part.startswith(("1.", "2.", "3.")):
                    clean_part = clean_part[2:].strip()
                await message_obj.reply_text(clean_part)

    except Exception as e:
        logger.error(f"Ошибка при генерации: {e}")
        await message_obj.reply_text("Ошибка при генерации поздравления. Попробуйте ещё раз.")

    # Кнопки "Ещё" и "Начать сначала"
    keyboard = [
        [InlineKeyboardButton("Ещё варианты", callback_data="generate_again")],
        [InlineKeyboardButton("Начать сначала", callback_data="restart_bot")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message_obj.reply_text("Дополнительные действия:", reply_markup=reply_markup)
    
    # Возвращаем GENERATE, чтобы кнопки работали
    return GENERATE

async def generate_again(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Генерирую новые... ⏳")
    await generate_message(query, context)
    return GENERATE

async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Перезапуск бота - возврат к главному меню"""
    query = update.callback_query
    await query.answer()
    
    # Очищаем user_data
    context.user_data.clear()
    
    welcome_text = (
        "Привет! 👋\n\n"
        "Я помогу вам быстро и красиво поздравить кого угодно.\n"
        "Выберите, что вас интересует:"
    )
    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in MAIN_CATEGORIES.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(welcome_text, reply_markup=reply_markup)
    return CATEGORY

async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    feedback_text = update.message.text
    user = update.effective_user
    logger.info(f"Feedback from {user.id} (@{user.username}): {feedback_text}")

    # Отправляем админу
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    if admin_id:
        try:
            await context.bot.send_message(
                chat_id=int(admin_id), 
                text=f"Обратная связь от @{user.username} (ID: {user.id}):\n\n{feedback_text}"
            )
            await update.message.reply_text("Спасибо за ваше сообщение! Мы его получили. ✅")
        except Exception as e:
            logger.error(f"Ошибка при отправке обратной связи админу: {e}")
            await update.message.reply_text("Спасибо за ваше сообщение! (Ошибка при отправке админу)")
    else:
        logger.warning(f"Feedback received, but ADMIN_TELEGRAM_ID not set. Message: {feedback_text}")
        await update.message.reply_text(
            "Спасибо за ваше сообщение! ✅\n\n"
            "⚠️ Внимание администратору: установите переменную окружения ADMIN_TELEGRAM_ID для получения сообщений обратной связи."
        )

    return ConversationHandler.END

# --- НАЧАЛО: Обработчик доната ---
async def handle_donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_username = os.getenv("BOT_USERNAME")
    if bot_username:
        donate_url = f"https://t.me/{bot_username}?start=donate"
        keyboard = [
            [InlineKeyboardButton("Поддержать проект", url=donate_url)],
            [InlineKeyboardButton("Назад", callback_data="back_to_main_category")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Спасибо, что хотите поддержать проект! 🙏\n\n"
            "Этот бот не содержит рекламы и разрабатывается на личные средства.\n"
            "Ваш вклад поможет покрыть расходы на хостинг и дальнейшее развитие.\n\n"
            "Нажмите кнопку ниже, чтобы поддержать проект через Telegram Stars.",
            reply_markup=reply_markup
        )
    else:
        keyboard = [[InlineKeyboardButton("Назад", callback_data="back_to_main_category")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Спасибо, что хотите поддержать проект! 🙏\n\n"
            "К сожалению, пока невозможно поддержать проект через Telegram Stars. Мы работаем над этим.\n\n"
            "⚠️ Внимание администратору: установите переменную окружения BOT_USERNAME для активации донатов.",
            reply_markup=reply_markup
        )
# --- КОНЕЦ: Обработчик доната ---

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CATEGORY: [
                CallbackQueryHandler(choose_category),
                CallbackQueryHandler(back_to_main_category, pattern="^back_to_main_category$"),
            ],
            SUBCATEGORY: [
                CallbackQueryHandler(choose_subcategory),
                CallbackQueryHandler(back_to_main_category, pattern="^back_to_main_category$"),
            ],
            EMOJIS: [
                CallbackQueryHandler(choose_emojis, pattern="^emojis_(yes|no)$"),
                CallbackQueryHandler(back_to_category, pattern="^back_to_category$"),
                CallbackQueryHandler(back_to_main_category, pattern="^back_to_main_category$"),
            ],
            NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name),
                CallbackQueryHandler(skip_name, pattern="^skip_name$"),
                CallbackQueryHandler(back_to_emojis, pattern="^back_to_emojis$"),
                CallbackQueryHandler(back_to_category, pattern="^back_to_category$"),
                CallbackQueryHandler(back_to_main_category, pattern="^back_to_main_category$"),
            ],
            GENERATE: [
                CallbackQueryHandler(generate_again, pattern="^generate_again$"),
                CallbackQueryHandler(restart_bot, pattern="^restart_bot$"),
                CallbackQueryHandler(back_to_main_category, pattern="^back_to_main_category$"),
            ],
            FEEDBACK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_feedback),
                CallbackQueryHandler(back_to_main_category, pattern="^back_to_main_category$"),
            ],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(handle_donate, pattern="^donate_stars$"))

    logger.info("Бот запущен и готов к работе!")
    application.run_polling()

if __name__ == '__main__':
    main()
