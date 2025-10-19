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
CATEGORY, STYLE, NAME, GENERATE = range(4)

# --- НАЧАЛО: Изменённые словари ---
# Ключи - это короткие строки, которые будут использоваться в callback_data
# Значения - это отображаемые названия и внутренние значения
CATEGORIES = {
    "bd": "С днём рождения",
    "new_year": "С Новым годом",
    "wedding": "Со свадьбой",
    "jubilee": "С юбилеем",
    "promotion": "С повышением",
    "bd_colleague": "С днём рождения (для коллеги)",
    "bd_friend": "С днём рождения (для друга)",
    "bd_relatives": "С днём рождения (для родных)",
    "bd_mother": "С днём рождения (для мамы)",
    "bd_father": "С днём рождения (для папы)",
    "bd_grandmother": "С днём рождения (для бабушки)",
    "bd_grandfather": "С днём рождения (для дедушки)",
    "bd_sister": "С днём рождения (для сестры)",
    "bd_brother": "С днём рождения (для брата)",
    "bd_child": "С днём рождения (для ребёнка)",
    "bd_girlfriend": "С днём рождения (для девушки)",
    "bd_boyfriend": "С днём рождения (для молодого человека)",
    "birth_child": "С рождением ребёнка",
    "new_home": "С новосельем",
    "name_day": "С днём ангела",
    "mothers_day": "С днём матери",
    "fathers_day": "С днём отца",
    "family_day": "С днём семьи",
    "defender_day": "С днём защитника Отечества",
    "womens_day": "С 8 марта",
    "teachers_day": "С днём учителя",
    "doctors_day": "С днём врача",
    "programmers_day": "С днём программиста",
    "police_day": "С днём полиции",
    "prosecutor_day": "С днём прокуратуры",
    "lawyers_day": "С днём юриста",
    "company_day": "С днём компании",
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
    "retirement": "С выходом на пенсию",
    "project_success": "С успешным проектом",
    "release": "С релизом",
    "report_submitted": "С сдачей отчёта",
    "vacation_start": "С началом отпуска",
    "vacation_end": "С окончанием отпуска",
    "valentines_day": "С днём святого Валентина",
    "engagement": "С помолвкой",
    "proposal": "С предложением руки и сердца",
    "wedding_anniversary": "С годовщиной свадьбы",
}

# Внутренние значения для GPT
CATEGORY_INTERNAL = {
    "bd": "день рождения",
    "new_year": "Новый год",
    "wedding": "свадьба",
    "jubilee": "юбилей",
    "promotion": "повышение",
    "bd_colleague": "день рождения для коллеги",
    "bd_friend": "день рождения для друга",
    "bd_relatives": "день рождения для родных",
    "bd_mother": "день рождения для мамы",
    "bd_father": "день рождения для папы",
    "bd_grandmother": "день рождения для бабушки",
    "bd_grandfather": "день рождения для дедушки",
    "bd_sister": "день рождения для сестры",
    "bd_brother": "день рождения для брата",
    "bd_child": "день рождения для ребёнка",
    "bd_girlfriend": "день рождения для девушки",
    "bd_boyfriend": "день рождения для молодого человека",
    "birth_child": "рождение ребёнка",
    "new_home": "новоселье",
    "name_day": "день ангела",
    "mothers_day": "день матери",
    "fathers_day": "день отца",
    "family_day": "день семьи",
    "defender_day": "23 февраля",
    "womens_day": "8 марта",
    "teachers_day": "день учителя",
    "doctors_day": "день врача",
    "programmers_day": "день программиста",
    "police_day": "день полиции",
    "prosecutor_day": "день прокуратуры",
    "lawyers_day": "день юриста",
    "company_day": "день компании",
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
    "retirement": "выход на пенсию",
    "project_success": "успешный проект",
    "release": "релиз",
    "report_submitted": "сдача отчёта",
    "vacation_start": "начало отпуска",
    "vacation_end": "окончание отпуска",
    "valentines_day": "День святого Валентина",
    "engagement": "помолвка",
    "proposal": "предложение руки и сердца",
    "wedding_anniversary": "годовщина свадьбы",
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
# --- КОНЕЦ: Изменённые словари ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in CATEGORIES.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите категорию поздравления:", reply_markup=reply_markup)
    return CATEGORY

async def choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    category_key = query.data
    context.user_data['category_key'] = category_key
    category_display = CATEGORIES[category_key]
    context.user_data['category_display'] = category_display
    category_internal = CATEGORY_INTERNAL[category_key]
    context.user_data['category_internal'] = category_internal

    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in STYLES.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"Вы выбрали: {category_display}\nТеперь выберите стиль:", reply_markup=reply_markup)
    return STYLE

async def choose_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    style_key = query.data
    context.user_data['style_key'] = style_key
    style_internal = STYLE_INTERNAL[style_key]
    context.user_data['style_internal'] = style_internal

    keyboard = [
        [InlineKeyboardButton("Пропустить", callback_data="skip_name")],
        [InlineKeyboardButton("Назад", callback_data="back_to_category")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Введите имя или уточнение (например, 'для коллеги', 'для мамы'), или нажмите 'Пропустить':", reply_markup=reply_markup)
    return NAME

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

async def back_to_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(text, callback_data=key)] for key, text in CATEGORIES.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите категорию поздравления:", reply_markup=reply_markup)
    return CATEGORY

async def generate_message_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.edit_message_text("Генерирую поздравления...")
    await generate_message(query, context)

async def generate_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    category_internal = context.user_data.get('category_internal')
    style_internal = context.user_data.get('style_internal')
    name = context.user_data.get('name', "без указания имени")
    category_display = context.user_data.get('category_display')

    # Подготовка промта
    prompt = f"""
Создай 3 варианта поздравления по поводу '{category_internal}'.
Стиль: {style_internal}.
Адресат: {name}.
Язык: русский.
Требования:
- Без повторов фраз между вариантами
- Без клише "желаю счастья, здоровья"
- Сохрани естественный ритм речи
- Раздели варианты нумерацией
"""

    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты — профессиональный автор поздравлений и тостов. Пиши на русском языке. Не используй восклицательные знаки подряд (макс. 1), избегай шаблонов 'желаю счастья, здоровья'. Всегда возвращай 3 варианта в виде пронумерованного списка."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )

        message = response.choices[0].message.content

    except Exception as e:
        logger.error(f"Ошибка при генерации: {e}")
        message = "Ошибка при генерации поздравления. Попробуйте ещё раз."

    keyboard = [
        [InlineKeyboardButton("Ещё варианты", callback_data="generate_again")],
        [InlineKeyboardButton("Назад", callback_data="back_to_category")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(message, reply_markup=reply_markup)

async def generate_again(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Генерирую новые поздравления...")
    await generate_message(query, context)

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CATEGORY: [CallbackQueryHandler(choose_category)],
            STYLE: [CallbackQueryHandler(choose_style)],
            NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name),
                CallbackQueryHandler(skip_name, pattern="^skip_name$"),
                CallbackQueryHandler(back_to_category, pattern="^back_to_category$"),
            ],
            GENERATE: [CallbackQueryHandler(generate_again, pattern="^generate_again$")]
        },
        fallbacks=[CommandHandler('start', start)]  # Исправлено: теперь передаёт функцию start
    )

    application.add_handler(conv_handler)

    application.run_polling()

if __name__ == '__main__':
    main()
