# main.py
import os
import logging
import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
    ContextTypes,
)
from telegram.error import Conflict
import openai

# --- НАЧАЛО: Google Sheets ---
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Инициализация Google Sheets клиента
def init_google_sheets():
    """Инициализация подключения к Google Sheets"""
    try:
        # Получаем credentials из переменной окружения
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        
        if not creds_json or not sheet_id:
            logger.warning("⚠️ Google Sheets не настроены. Аналитика отключена.")
            return None, None
        
        # Создаём временный файл с credentials
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
            temp_file.write(creds_json)
            temp_file_path = temp_file.name
        
        # Настройка авторизации
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        creds = ServiceAccountCredentials.from_json_keyfile_name(temp_file_path, scope)
        client = gspread.authorize(creds)
        
        # Удаляем временный файл
        os.unlink(temp_file_path)
        
        # Открываем таблицу
        sheet = client.open_by_key(sheet_id)
        
        logger.info("✅ Google Sheets успешно подключены!")
        return sheet, sheet_id
        
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Google Sheets: {e}")
        return None, None

# Глобальные переменные для Google Sheets
GOOGLE_SHEET = None
GOOGLE_SHEET_ID = None

# Функции для записи в Google Sheets
def log_to_sheets(worksheet_name, data):
    """Записать данные в указанный лист Google Sheets"""
    try:
        if not GOOGLE_SHEET:
            return
        
        worksheet = GOOGLE_SHEET.worksheet(worksheet_name)
        worksheet.append_row(data)
        logger.info(f"📊 Записано в {worksheet_name}: {data}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка записи в Google Sheets ({worksheet_name}): {e}")

def log_user(user):
    """Записать/обновить информацию о пользователе"""
    try:
        if not GOOGLE_SHEET:
            return
        
        worksheet = GOOGLE_SHEET.worksheet("Пользователи")
        
        # Ищем пользователя
        try:
            cell = worksheet.find(str(user.id))
            row_num = cell.row
            
            # Обновляем последний визит и счётчик генераций
            current_count = int(worksheet.cell(row_num, 6).value or 0)
            worksheet.update_cell(row_num, 5, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))  # Последний визит
            worksheet.update_cell(row_num, 6, current_count + 1)  # Увеличиваем счётчик
            
        except gspread.CellNotFound:
            # Добавляем нового пользователя
            data = [
                user.id,
                user.username or "без username",
                f"{user.first_name or ''} {user.last_name or ''}".strip(),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Первый визит
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Последний визит
                1  # Всего генераций
            ]
            worksheet.append_row(data)
            logger.info(f"👤 Новый пользователь: {user.id} (@{user.username})")
            
    except Exception as e:
        logger.error(f"❌ Ошибка логирования пользователя: {e}")

def log_generation(user, category, subcategory, style, emojis, name_provided, success):
    """Записать генерацию поздравления"""
    data = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user.id,
        user.username or "без username",
        category,
        subcategory,
        style,
        "Да" if emojis else "Нет",
        "Да" if name_provided else "Нет",
        "Успех" if success else "Ошибка"
    ]
    log_to_sheets("Генерации", data)

def log_donation(user, amount, payload):
    """Записать донат"""
    data = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user.id,
        user.username or "без username",
        amount,
        payload
    ]
    log_to_sheets("Донаты", data)

def log_feedback(user, message):
    """Записать обратную связь"""
    data = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user.id,
        user.username or "без username",
        message
    ]
    log_to_sheets("Обратная связь", data)

def log_rate_limit(user, seconds_left):
    """Записать превышение лимита"""
    data = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user.id,
        user.username or "без username",
        seconds_left
    ]
    log_to_sheets("Лимиты", data)

# --- КОНЕЦ: Google Sheets ---

# --- НАЧАЛО: Лимит запросов ---
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

# Подавляем PTBUserWarning
import warnings
from telegram.warnings import PTBUserWarning
warnings.filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

# Определяем шаги разговора
CATEGORY, SUBCATEGORY, STYLE, EMOJIS, NAME, GENERATE, FEEDBACK = range(7)

# --- НАЧАЛО: Организация категорий ---
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

STYLES = {
    "standard": "📝 Стандартное / универсальное",
    "short": "✂️ Короткое / лаконичное",
    "funny": "😄 Смешное / с юмором",
    "warm": "❤️ Душевное / тёплое",
    "formal": "💼 Официальное / деловое",
    "romantic": "💕 Романтическое",
}

STYLE_DESCRIPTIONS = {
    "standard": "нейтральное, вежливое, универсальное поздравление",
    "short": "очень короткое, лаконичное, 1-2 предложения, без лишних слов",
    "funny": "с юмором, лёгкая ирония, забавное, но не оскорбительное",
    "warm": "душевное, тёплое, от сердца, с акцентом на чувства и эмоции",
    "formal": "официальное, деловое, строгое, уважительный тон без шуток",
    "romantic": "романтическое, нежное, мягкое, с акцентом на чувства",
}

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
    "default": "🎉✨🎊"
}

# --- НАЧАЛО: Лимит запросов ---
REQUEST_LIMIT_PER_MINUTE = 3

def is_rate_limited(user_id):
    now = datetime.now()
    user_requests = request_times.get(user_id, [])
    
    user_requests = [req_time for req_time in user_requests if now - req_time < timedelta(minutes=1)]
    
    if len(user_requests) >= REQUEST_LIMIT_PER_MINUTE:
        time_to_reset = user_requests[0] + timedelta(minutes=1) - now
        return True, time_to_reset
    
    user_requests.append(now)
    request_times[user_id] = user_requests
    return False, None
# --- КОНЕЦ: Лимит запросов ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    
    # АНАЛИТИКА: Логируем нового пользователя или /start
    log_user(user)
    
    welcome_text = (
        "Привет! 👋\n\n"
        "Я помогу вам быстро и красиво поздравить кого угодно.\n"
        "Выберите, что вас интересует:"
    )
    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in MAIN_CATEGORIES.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
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
        keyboard = [
            [InlineKeyboardButton("⭐ 50 Stars", callback_data="donate_50")],
            [InlineKeyboardButton("⭐ 100 Stars", callback_data="donate_100")],
            [InlineKeyboardButton("⭐ 200 Stars", callback_data="donate_200")],
            [InlineKeyboardButton("⭐ 500 Stars", callback_data="donate_500")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main_category")],
            [InlineKeyboardButton("🏠 Начать сначала", callback_data="restart_bot")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Спасибо, что хотите поддержать проект! 🙏\n\n"
            "Этот бот не содержит рекламы и разрабатывается на личные средства.\n"
            "Ваш вклад поможет покрыть расходы на хостинг и дальнейшее развитие.\n\n"
            "Выберите сумму для поддержки через Telegram Stars:",
            reply_markup=reply_markup
        )
        return CATEGORY

    if category_key == "feedback":
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main_category")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Напишите ваше сообщение для обратной связи:", reply_markup=reply_markup)
        return FEEDBACK

    context.user_data['main_category'] = category_key

    subcats = SUBCATEGORIES.get(category_key, {})
    if not subcats:
        context.user_data['subcategory_key'] = category_key
        keyboard = [
            [InlineKeyboardButton(text, callback_data=key)] for key, text in STYLES.items()
        ]
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main_category")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите стиль поздравления:", reply_markup=reply_markup)
        return STYLE

    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in subcats.items()
    ]
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main_category")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"Выбрана категория: {MAIN_CATEGORIES[category_key]}\nВыберите подкатегорию:", reply_markup=reply_markup)
    return SUBCATEGORY

async def choose_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    subcategory_key = query.data
    context.user_data['subcategory_key'] = subcategory_key

    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in STYLES.items()
    ]
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_category")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите стиль поздравления:", reply_markup=reply_markup)
    
    return STYLE

async def choose_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    style_key = query.data
    context.user_data['style'] = style_key

    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data="emojis_yes")],
        [InlineKeyboardButton("❌ Нет", callback_data="emojis_no")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_style")]
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
    elif emoji_choice == "emojis_no":
        context.user_data['emojis'] = False
    else:
        return EMOJIS

    keyboard = [
        [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_name")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_emojis")]
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
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main_category")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"Выбрана категория: {MAIN_CATEGORIES[category_key]}\nВыберите подкатегорию:", reply_markup=reply_markup)
            return SUBCATEGORY
        else:
            return await back_to_main_category(update, context)
    else:
        return await back_to_main_category(update, context)

async def back_to_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in STYLES.items()
    ]
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_category")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите стиль поздравления:", reply_markup=reply_markup)
    
    return STYLE

async def back_to_emojis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data="emojis_yes")],
        [InlineKeyboardButton("❌ Нет", callback_data="emojis_no")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_style")]
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
    if hasattr(update, 'from_user') and hasattr(update, 'message'):
        user_id = update.from_user.id
        user = update.from_user
        message_obj = update.message
    else:
        user_id = update.effective_user.id
        user = update.effective_user
        message_obj = update.message

    is_limited, reset_time = is_rate_limited(user_id)
    if is_limited:
        if reset_time:
            seconds_left = int(reset_time.total_seconds())
            minutes_left = seconds_left // 60
            seconds_remainder = seconds_left % 60
            
            # АНАЛИТИКА: Логируем превышение лимита
            log_rate_limit(user, seconds_left)
            
            if minutes_left > 0:
                await message_obj.reply_text(f"⏳ Превышен лимит запросов.\nПопробуйте через {minutes_left} мин {seconds_remainder} сек.")
            else:
                await message_obj.reply_text(f"⏳ Превышен лимит запросов.\nПопробуйте через {seconds_left} сек.")
        else:
            await message_obj.reply_text("⏳ Превышен лимит запросов. Попробуйте позже.")
        return GENERATE

    subcategory_key = context.user_data.get('subcategory_key')
    name = context.user_data.get('name')
    emojis = context.user_data.get('emojis', False)
    style = context.user_data.get('style', 'standard')

    category_internal = CATEGORY_INTERNAL.get(subcategory_key, "праздник")
    style_description = STYLE_DESCRIPTIONS.get(style, "стандартное")

    emoji_string = EMOJI_MAP.get(subcategory_key, EMOJI_MAP.get(category_internal.split()[0], EMOJI_MAP["default"])) if emojis else ""
    emoji_instruction = f"Разрешено использовать следующие смайлики: {emoji_string}. Распредели их равномерно по всем трём вариантам, от 20 до 35 штук в каждом. Смайлики должны быть в разных местах текста: в начале, в середине, в конце. Чередуй их разнообразно, чтобы текст был живым и не однообразным." if emojis else "Не использовать смайлы."

    name_part = f"поздравь {name}" if name else "поздравление для друга"

    if subcategory_key.startswith('toast_'):
        prompt = f"""
Создай 3 разных популярных {category_internal}, которые существуют и часто используются.
Стиль: {style_description}.
{emoji_instruction}
Адресат: {name_part}.
Язык: русский.
Требования:
- Это должны быть **реальные**, **существующие** тосты, **не придуманные**.
- Соблюдай выбранный стиль: {style_description}.
- Без повторов фраз между вариантами.
- Без клише "желаю счастья, здоровья".
- Сохрани естественный ритм речи.
- Избегай длинных тире (—), используй короткие (-) или просто пробел.
- Пиши от первого лица ("Поздравляю", "От всей души", "С теплом в сердце").
- Не использовать "ChatGPT", "OpenAI" или подобные обращения.
- Всегда возвращай 3 варианта в виде пронумерованного списка.
"""
        system_prompt = f"Ты — профессиональный автор тостов. Пиши на русском языке в стиле: {style_description}. Возвращай 3 популярных, существующих тоста в виде пронумерованного списка. Используй короткие тире (-). Если разрешены смайлики, распредели их равномерно по всем трём вариантам, от 20 до 35 штук в каждом, размещая их в разных частях текста для разнообразия."
    else:
        prompt = f"""
Создай 3 разных {category_internal} в прозе или стихе.
Стиль: {style_description}.
{emoji_instruction}
Адресат: {name_part}.
Язык: русский.
Требования:
- Соблюдай выбранный стиль: {style_description}.
- Без повторов фраз между вариантами.
- Без клише "желаю счастья, здоровья".
- Сохрани естественный ритм речи.
- Избегай длинных тире (—), используй короткие (-) или просто пробел.
- Пиши от первого лица ("Поздравляю", "От всей души", "С теплом в сердце").
- Не использовать "ChatGPT", "OpenAI" или подобные обращения.
- Всегда возвращай 3 варианта в виде пронумерованного списка.
"""
        system_prompt = f"Ты — профессиональный автор поздравлений и тостов. Пиши на русском языке в стиле: {style_description}. Не используй восклицательные знаки подряд (макс. 1), избегай шаблонов 'желаю счастья, здоровья'. Всегда возвращай 3 варианта в виде пронумерованного списка. Используй короткие тире (-). Если разрешены смайлики, распредели их равномерно по всем трём вариантам, от 20 до 35 штук в каждом, размещая их в разных частях текста для разнообразия."

    generation_success = False
    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2500,
            temperature=0.8
        )

        message_text = response.choices[0].message.content
        parts = message_text.split("\n\n")
        for part in parts:
            if part.strip():
                clean_part = part.strip()
                if clean_part.startswith(("1.", "2.", "3.", "1)", "2)", "3)")):
                    clean_part = clean_part[2:].strip()
                if clean_part:
                    await message_obj.reply_text(clean_part)
        
        generation_success = True

    except Exception as e:
        logger.error(f"Ошибка при генерации: {e}")
        await message_obj.reply_text("❌ Ошибка при генерации поздравления. Попробуйте ещё раз.")
    
    # АНАЛИТИКА: Логируем генерацию
    log_generation(
        user=user,
        category=context.user_data.get('main_category', 'unknown'),
        subcategory=subcategory_key,
        style=style,
        emojis=emojis,
        name_provided=bool(name),
        success=generation_success
    )

    keyboard = [
        [InlineKeyboardButton("🔄 Ещё варианты", callback_data="generate_again")],
        [InlineKeyboardButton("🏠 Начать сначала", callback_data="restart_bot")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message_obj.reply_text("Дополнительные действия:", reply_markup=reply_markup)
    
    return GENERATE

async def generate_again(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Генерирую новые... ⏳")
    await generate_message(query, context)
    return GENERATE

async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
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
    
    # АНАЛИТИКА: Логируем обратную связь
    log_feedback(user, feedback_text)
    
    logger.info(f"📩 Получена обратная связь от {user.id} (@{user.username}): {feedback_text}")

    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    
    if admin_id:
        try:
            await context.bot.send_message(
                chat_id=int(admin_id), 
                text=f"📩 **Обратная связь**\n\n"
                     f"От: @{user.username if user.username else 'без username'}\n"
                     f"ID: `{user.id}`\n"
                     f"Имя: {user.first_name} {user.last_name if user.last_name else ''}\n\n"
                     f"Сообщение:\n{feedback_text}",
                parse_mode="Markdown"
            )
            await update.message.reply_text("Спасибо за ваше сообщение! Мы его получили. ✅")
            logger.info(f"✅ Обратная связь успешно отправлена админу {admin_id}")
        except ValueError as ve:
            logger.error(f"❌ ADMIN_TELEGRAM_ID имеет некорректное значение: {admin_id}. Ошибка: {ve}")
            await update.message.reply_text("Спасибо за ваше сообщение! ✅")
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке обратной связи админу: {e}")
            await update.message.reply_text("Спасибо за ваше сообщение! ✅")
    else:
        logger.warning(f"⚠️ ADMIN_TELEGRAM_ID не установлен. Обратная связь не отправлена: {feedback_text}")
        await update.message.reply_text("Спасибо за ваше сообщение! Мы его получили. ✅")

    keyboard = [[InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_main_category")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Хотите вернуться в меню?", reply_markup=reply_markup)
    
    return CATEGORY

# --- НАЧАЛО: Донаты через Telegram Stars ---
async def handle_donate_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    amount_map = {
        "donate_50": 50,
        "donate_100": 100,
        "donate_200": 200,
        "donate_500": 500,
    }
    
    stars_amount = amount_map.get(query.data, 50)
    
    try:
        await context.bot.send_invoice(
            chat_id=query.from_user.id,
            title=f"Поддержка проекта",
            description=f"Спасибо за вашу поддержку! Вы помогаете развитию бота.",
            payload=f"donate_{stars_amount}_stars",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("Поддержка проекта", stars_amount)],
        )
        await query.edit_message_text(
            f"Отправлен счёт на {stars_amount} ⭐ Stars.\n"
            "Проверьте сообщение с инвойсом выше. 👆"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке инвойса: {e}")
        await query.edit_message_text(
            "❌ Извините, произошла ошибка при создании платежа.\n"
            "Попробуйте позже или свяжитесь с разработчиком через обратную связь."
        )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    payment = update.message.successful_payment
    
    # АНАЛИТИКА: Логируем донат
    log_donation(user, payment.total_amount, payment.invoice_payload)
    
    logger.info(f"💰 Donation received from {user.id} (@{user.username}): {payment.total_amount} Stars")
    
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    if admin_id:
        try:
            await context.bot.send_message(
                chat_id=int(admin_id),
                text=f"💰 Получен донат!\n"
                     f"От: @{user.username} (ID: {user.id})\n"
                     f"Сумма: {payment.total_amount} ⭐ Stars\n"
                     f"Payload: {payment.invoice_payload}"
            )
        except Exception as e:
            logger.error(f"Ошибка при уведомлении админа о донате: {e}")
    
    await update.message.reply_text(
        "🎉 Огромное спасибо за вашу поддержку!\n\n"
        "Ваш вклад очень важен для развития проекта. ❤️\n\n"
        "Если у вас есть идеи или пожелания — пишите в обратную связь!"
    )
# --- КОНЕЦ: Донаты через Telegram Stars ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update: {context.error}")
    
    if isinstance(context.error, Conflict):
        logger.critical("⚠️ CONFLICT ERROR: Запущено несколько экземпляров бота! Остановите старые экземпляры.")

def main():
    global GOOGLE_SHEET, GOOGLE_SHEET_ID
    
    # Инициализация Google Sheets
    GOOGLE_SHEET, GOOGLE_SHEET_ID = init_google_sheets()
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CATEGORY: [
                CallbackQueryHandler(back_to_main_category, pattern="^back_to_main_category$"),
                CallbackQueryHandler(restart_bot, pattern="^restart_bot$"),
                CallbackQueryHandler(handle_donate_amount, pattern="^donate_(50|100|200|500)$"),
                CallbackQueryHandler(choose_category),
            ],
            SUBCATEGORY: [
                CallbackQueryHandler(back_to_main_category, pattern="^back_to_main_category$"),
                CallbackQueryHandler(choose_subcategory),
            ],
            STYLE: [
                CallbackQueryHandler(back_to_category, pattern="^back_to_category$"),
                CallbackQueryHandler(back_to_main_category, pattern="^back_to_main_category$"),
                CallbackQueryHandler(choose_style),
            ],
            EMOJIS: [
                CallbackQueryHandler(back_to_style, pattern="^back_to_style$"),
                CallbackQueryHandler(back_to_category, pattern="^back_to_category$"),
                CallbackQueryHandler(back_to_main_category, pattern="^back_to_main_category$"),
                CallbackQueryHandler(choose_emojis),
            ],
            NAME: [
                CallbackQueryHandler(skip_name, pattern="^skip_name$"),
                CallbackQueryHandler(back_to_emojis, pattern="^back_to_emojis$"),
                CallbackQueryHandler(back_to_style, pattern="^back_to_style$"),
                CallbackQueryHandler(back_to_category, pattern="^back_to_category$"),
                CallbackQueryHandler(back_to_main_category, pattern="^back_to_main_category$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name),
            ],
            GENERATE: [
                CallbackQueryHandler(generate_again, pattern="^generate_again$"),
                CallbackQueryHandler(restart_bot, pattern="^restart_bot$"),
                CallbackQueryHandler(back_to_main_category, pattern="^back_to_main_category$"),
            ],
            FEEDBACK: [
                CallbackQueryHandler(back_to_main_category, pattern="^back_to_main_category$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_feedback),
            ],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    application.add_handler(conv_handler)
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    application.add_error_handler(error_handler)

    logger.info("🚀 Бот запущен и готов к работе!")
    logger.info(f"💰 Донаты через Telegram Stars: ВКЛЮЧЕНЫ")
    logger.info(f"📊 Google Sheets: {'ВКЛЮЧЕНЫ' if GOOGLE_SHEET else 'ОТКЛЮЧЕНЫ'}")
    admin_id_status = os.getenv('ADMIN_TELEGRAM_ID', 'НЕ УСТАНОВЛЕН')
    logger.info(f"📧 Admin ID: {admin_id_status}")
    
    if admin_id_status == 'НЕ УСТАНОВЛЕН':
        logger.warning("⚠️ ВНИМАНИЕ: ADMIN_TELEGRAM_ID не установлен! Обратная связь не будет отправляться.")
    
    application.run_polling()

if __name__ == '__main__':
    main()
