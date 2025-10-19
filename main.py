# main.py
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
import hashlib

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

# Определяем шаги разговора
CATEGORY, SUBCATEGORY, STYLE, EMOJIS, NAME, GENERATE = range(6)

# --- НАЧАЛО: Организация категорий ---
# Основные категории
MAIN_CATEGORIES = {
    "birthday": "🎂 Дни рождения",
    "professional": "💼 Рабочие и профессиональные",
    "seasonal": "🎄 Календарные / сезонные",
    "personal": "❤️ Личные поводы и достижения",
    "family": "👨‍👩‍👧‍👦 Семейные",
}

# Подкатегории
SUBCATEGORIES = {
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

STYLES = {
    "formal": "Формальный",
    "humor": "С юмором",
    "short": "Короткий",
    "solemn": "Торжественный",
    "verse": "Стих",
    "prose": "Проза",
    "warm": "Тёплый душевный",
    "detailed": "Развёрнутый",
}

STYLE_INTERNAL = {
    "formal": "формальный",
    "humor": "с юмором",
    "short": "короткий",
    "solemn": "торжественный",
    "verse": "стих",
    "prose": "проза",
    "warm": "тёплый душевный",
    "detailed": "развёрнутый",
}
# --- КОНЕЦ: Организация категорий ---

# --- НАЧАЛО: Лимит запросов ---
REQUEST_LIMIT_PER_MINUTE = 3
def is_rate_limited(user_id):
    now = datetime.now()
    user_requests = request_times.get(user_id, [])
    # Удаляем старые запросы (старше 1 минуты)
    user_requests = [req_time for req_time in user_requests if now - req_time < timedelta(minutes=1)]
    if len(user_requests) >= REQUEST_LIMIT_PER_MINUTE:
        return True
    user_requests.append(now)
    request_times[user_id] = user_requests
    return False
# --- КОНЕЦ: Лимит запросов ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in MAIN_CATEGORIES.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите категорию поздравления:", reply_markup=reply_markup)
    return CATEGORY

async def choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    category_key = query.data
    context.user_data['main_category'] = category_key

    subcats = SUBCATEGORIES.get(category_key, {})
    if not subcats:
        # Если подкатегорий нет, перейти к стилю
        context.user_data['subcategory_key'] = category_key # Используем ключ основной категории как подкатегорию
        keyboard = [
            [InlineKeyboardButton(text, callback_data=key)] for key, text in STYLES.items()
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Теперь выберите стиль:", reply_markup=reply_markup)
        return STYLE

    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in subcats.items()
    ]
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
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Теперь выберите стиль:", reply_markup=reply_markup)
    return STYLE

async def choose_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    style_key = query.data
    context.user_data['style_key'] = style_key

    # Спрашиваем про смайлики
    keyboard = [
        [InlineKeyboardButton("Да", callback_data="emojis_yes")],
        [InlineKeyboardButton("Нет", callback_data="emojis_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Добавить смайлики в поздравление?", reply_markup=reply_markup)
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
        [InlineKeyboardButton("Назад", callback_data="back_to_style")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Введите имя или уточнение (например, 'для коллеги', 'для мамы'), или нажмите 'Пропустить':", reply_markup=reply_markup)
    return NAME

async def back_to_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in STYLES.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Теперь выберите стиль:", reply_markup=reply_markup)
    return STYLE

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text
    context.user_data['name'] = name
    await generate_message(update, context)
    return ConversationHandler.END

async def skip_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['name'] = None
    await generate_message_callback(update, context)
    return ConversationHandler.END

async def generate_message_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.edit_message_text("Генерирую поздравления...")
    # Передаём query (CallbackQuery), а не update (Update)
    # Но внутри generate_message нам нужен user_id. Он доступен как query.from_user.id
    # Поэтому вызываем generate_message с query и context
    # Но generate_message ожидает update (Update), чтобы получить update.effective_user.id
    # Нам нужно изменить generate_message, чтобы он работал с CallbackQuery или Update
    await generate_message(query, context) # Передаём query, как и раньше, но исправим generate_message

async def generate_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Проверяем, является ли update объектом CallbackQuery
    # Если да, используем query.from_user.id, иначе update.effective_user.id
    if hasattr(update, 'from_user'):
        # Это CallbackQuery
        user_id = update.from_user.id
        # Для отправки сообщения используем query.message.reply_text
        message_obj = update.message
    else:
        # Это обычный Update
        user_id = update.effective_user.id
        # Для отправки сообщения используем update.message.reply_text
        message_obj = update.message

    # Проверка лимита
    if is_rate_limited(user_id):
        # Используем message_obj для отправки сообщения
        await message_obj.reply_text("Превышен лимит запросов. Попробуйте позже.")
        return ConversationHandler.END

    subcategory_key = context.user_data.get('subcategory_key')
    style_key = context.user_data.get('style_key')
    name = context.user_data.get('name', "друга")
    emojis = context.user_data.get('emojis', False)

    category_internal = CATEGORY_INTERNAL.get(subcategory_key, "праздник")
    style_internal = STYLE_INTERNAL.get(style_key, "обычный")

    # Подготовка промта
    emoji_instruction = "Разрешено использовать смайлы по смыслу." if emojis else "Не использовать смайлы."
    name_part = f"поздравь {name}" if name else "поздравление для друга"
    prompt = f"""
Создай 3 разных поздравления в прозе или стихе (в зависимости от стиля) по случаю "{category_internal}".
Стиль поздравления: {style_internal}.
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

    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini", # Используем более умную модель
            messages=[
                {"role": "system", "content": "Ты — профессиональный автор поздравлений и тостов. Пиши на русском языке. Не используй восклицательные знаки подряд (макс. 1), избегай шаблонов 'желаю счастья, здоровья'. Всегда возвращай 3 варианта в виде пронумерованного списка. Используй короткие тире (-)."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
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
                await message_obj.reply_text(clean_part) # Используем message_obj

    except Exception as e:
        logger.error(f"Ошибка при генерации: {e}")
        await message_obj.reply_text("Ошибка при генерации поздравления. Попробуйте ещё раз.")

    # Кнопки "Ещё" и "Назад"
    keyboard = [
        [InlineKeyboardButton("Ещё варианты", callback_data="generate_again")],
        [InlineKeyboardButton("Назад", callback_data="back_to_category")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message_obj.reply_text("Дополнительные действия:", reply_markup=reply_markup) # Используем message_obj
    return GENERATE

async def generate_again(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Генерирую новые поздравления...")
    await generate_message(query, context)

async def back_to_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in MAIN_CATEGORIES.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите категорию поздравления:", reply_markup=reply_markup)
    return CATEGORY

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CATEGORY: [CallbackQueryHandler(choose_category)],
            SUBCATEGORY: [CallbackQueryHandler(choose_subcategory)],
            STYLE: [CallbackQueryHandler(choose_style)],
            EMOJIS: [CallbackQueryHandler(choose_emojis)],
            NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name),
                CallbackQueryHandler(skip_name, pattern="^skip_name$"),
                CallbackQueryHandler(back_to_style, pattern="^back_to_style$"),
            ],
            GENERATE: [
                CallbackQueryHandler(generate_again, pattern="^generate_again$"),
                CallbackQueryHandler(back_to_category, pattern="^back_to_category$"),
            ],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    application.add_handler(conv_handler)

    application.run_polling()

if __name__ == '__main__':
    main()
