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

# Категории
CATEGORIES = {
    "С днём рождения": "день рождения",
    "С Новым годом": "Новый год",
    "Со свадьбой": "свадьба",
    "С юбилеем": "юбилей",
    "С повышением": "повышение",
    "С днём рождения (для коллеги)": "день рождения для коллеги",
    "С днём рождения (для друга)": "день рождения для друга",
    "С днём рождения (для родных)": "день рождения для родных",
    "С днём рождения (для мамы)": "день рождения для мамы",
    "С днём рождения (для папы)": "день рождения для папы",
    "С днём рождения (для бабушки)": "день рождения для бабушки",
    "С днём рождения (для дедушки)": "день рождения для дедушки",
    "С днём рождения (для сестры)": "день рождения для сестры",
    "С днём рождения (для брата)": "день рождения для брата",
    "С днём рождения (для ребёнка)": "день рождения для ребёнка",
    "С днём рождения (для девушки)": "день рождения для девушки",
    "С днём рождения (для молодого человека)": "день рождения для молодого человека",
    "С рождением ребёнка": "рождение ребёнка",
    "С новосельем": "новоселье",
    "С днём ангела": "день ангела",
    "С днём матери": "день матери",
    "С днём отца": "день отца",
    "С днём семьи": "день семьи",
    "С днём защитника Отечества": "23 февраля",
    "С 8 марта": "8 марта",
    "С днём учителя": "день учителя",
    "С днём врача": "день врача",
    "С днём программиста": "день программиста",
    "С днём полиции": "день полиции",
    "С днём прокуратуры": "день прокуратуры",
    "С днём юриста": "день юриста",
    "С днём компании": "день компании",
    "С Рождеством": "Рождество",
    "С Пасхой": "Пасха",
    "С Днём Победы": "9 мая",
    "С Днём города": "день города",
    "С Днём независимости": "день независимости",
    "С началом весны": "начало весны",
    "С началом лета": "начало лета",
    "С началом осени": "начало осени",
    "С началом зимы": "начало зимы",
    "С 1 сентября": "1 сентября",
    "С окончанием учёбы": "окончание учёбы",
    "С получением диплома": "получение диплома",
    "С покупкой машины": "покупка машины",
    "С покупкой квартиры": "покупка квартиры",
    "С покупкой дома": "покупка дома",
    "С победой": "победа",
    "С наградой": "награда",
    "Со спортивным успехом": "спортивный успех",
    "С выздоровлением": "выздоровление",
    "С выпиской": "выписка",
    "С годовщиной отношений": "годовщина отношений",
    "С годовщиной дружбы": "годовщиной дружбы",
    "С переездом": "переезд",
    "С новой работой": "новая работа",
    "С выходом на пенсию": "выход на пенсию",
    "С успешным проектом": "успешный проект",
    "С релизом": "релиз",
    "С сдачей отчёта": "сдача отчёта",
    "С началом отпуска": "начало отпуска",
    "С окончанием отпуска": "окончание отпуска",
    "С днём святого Валентина": "День святого Валентина",
    "С помолвкой": "помолвка",
    "С предложением руки и сердца": "предложение руки и сердца",
    "С годовщиной свадьбы": "годовщина свадьбы",
}

# Стили
STYLES = {
    "Формальный": "формальный",
    "С юмором": "с юмором",
    "Короткий": "короткий",
    "Торжественный": "торжественный",
    "Стих": "стих",
    "Проза": "проза",
    "Тёплый душевный": "тёплый душевный",
    "Развёрнутый": "развёрнутый",
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton(cat, callback_data=cat)] for cat in CATEGORIES.keys()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите категорию поздравления:", reply_markup=reply_markup)
    return CATEGORY

async def choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    category = query.data
    context.user_data['category'] = CATEGORIES[category]
    context.user_data['original_category'] = category

    keyboard = [
        [InlineKeyboardButton(sty, callback_data=sty)] for sty in STYLES.keys()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"Вы выбрали: {category}\nТеперь выберите стиль:", reply_markup=reply_markup)
    return STYLE

async def choose_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    style = query.data
    context.user_data['style'] = STYLES[style]

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
        [InlineKeyboardButton(cat, callback_data=cat)] for cat in CATEGORIES.keys()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите категорию поздравления:", reply_markup=reply_markup)
    return CATEGORY

async def generate_message_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.edit_message_text("Генерирую поздравления...")
    await generate_message(query, context)

async def generate_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    category = context.user_data.get('category')
    style = context.user_data.get('style')
    name = context.user_data.get('name', "без указания имени")
    original_category = context.user_data.get('original_category')

    # Подготовка промта
    prompt = f"""
Создай 3 варианта поздравления по поводу '{category}'.
Стиль: {style}.
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
        fallbacks=[CommandHandler('start')]
    )

    application.add_handler(conv_handler)

    application.run_polling()

if __name__ == '__main__':
    main()
