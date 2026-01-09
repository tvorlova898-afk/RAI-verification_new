import os
import logging
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
import asyncio

# 1. Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_SCRIPT_URL = os.getenv("GOOGLE_SCRIPT_URL")

# 2. Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 3. Инициализация бота и роутера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# Временное хранилище данных пользователя
user_data = {}

# ========================================================
# 🛡️ ФИЛЬТР: РЕЖИМ ТИШИНЫ В ГРУППАХ
# ========================================================

# Этот обработчик стоит первым. Если сообщение из группы — бот его просто игнорирует.
@router.message(F.chat.type.in_({"group", "supergroup"}))
async def silence_in_groups(message: Message):
    return

# ========================================================
# 🔐 СЕРВИСНЫЕ ФУНКЦИИ (ПОЛУЧЕНИЕ ID ТОЛЬКО В ЛИЧКЕ)
# ========================================================

@router.message(F.chat.type == "private", F.photo)
async def get_photo_id(message: Message):
    photo_id = message.photo[-1].file_id
    await message.answer(f"<b>ID вашего фото:</b>\n<code>{photo_id}</code>", parse_mode="HTML")

@router.message(F.chat.type == "private", F.animation)
async def get_gif_id(message: Message):
    await message.answer(f"ID вашей GIF: <code>{message.animation.file_id}</code>", parse_mode="HTML")

@router.message(F.chat.type == "private", F.video)
async def get_video_id(message: Message):
    await message.answer(f"ID вашего VIDEO: <code>{message.video.file_id}</code>", parse_mode="HTML")

# ========================================================
# 📝 ПРИВЕТСТВИЕ И АНКЕТА
# ========================================================

@router.message(F.chat.type == "private", Command("start"))
async def start(message: Message):
    user_id = str(message.from_user.id)
    
    await message.answer("🔍 Проверяю статус вашей верификации...")
    
    async with aiohttp.ClientSession() as session:
        try:
            check_url = f"{GOOGLE_SCRIPT_URL}?action=check_user&telegram_id={user_id}"
            async with session.get(check_url, timeout=10) as resp:
                status = await resp.text()
                
                if status.strip() == "registered":
                    await message.answer(
                        "✅ <b>Вы уже проходили верификацию!</b>\n\n"
                        "Все материалы и доступ в группу вам уже открыты. "
                        "Если вы потеряли ссылку на группу, вот она:\n"
                        "https://t.me/RAI_service_group", 
                        parse_mode="HTML"
                    )
                    return 
        except Exception as e:
            logger.error(f"Ошибка при проверке пользователя: {e}")

    WELCOME_VIDEO_ID = "BAACAgIAAxkBAAIEA2lb6OOI4SgnsGqibms4cbfJCQWzAAJvkQAC5bngSoh4P26VZWLsOAQ" 
    
    caption_text = (
        "👋 Привет! Я — ваш помощник для быстрого старта с RAI.\n\n"
        "<b>Что я помогу сделать:</b>\n"
        "✅ Помогу подать заявку на вступление в закрытую группу агентов RAI\n"
        "✅ Приму ваши данные для регистрации как партнёра\n"
        "✅ После верификации вы получите:\n"
        "    • Индивидуальный статус партнёра (ваше имя + RAI)\n"
        "    • Доступ к >100 единиц продающего контента для сторис и рилс\n"
        "    • Готовые материалы и ссылки на обучение\n"
        "    • Высокую комиссию от 250 000 ₽ с выплатой в течение 24 часов\n\n"
        "А главное — вам не нужно закрывать сделки! 💼\n"
        "Вы передаёте заинтересованных клиентов, а RAI берёт всё остальное на себя 😊\n\n"
        "Готовы начать?"
    )
    
    try:
        await message.answer_video(
            video=WELCOME_VIDEO_ID,
            caption=caption_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Давайте знакомиться", callback_data="paid")]
            ]),
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(
            caption_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Давайте знакомиться", callback_data="paid")]
            ]),
            parse_mode="HTML"
        )

@router.callback_query(F.data == "paid")
async def button_handler(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    user_data[user_id] = {"step": 1}
    await callback.message.answer("Хорошо! Первый вопрос:\n\n<b>Как вас зовут?</b>", parse_mode="HTML")

# --- ОБРАБОТЧИК АНКЕТЫ (ТОЛЬКО ЛИЧКА) ---
@router.message(F.chat.type == "private")
async def handle_message(message: Message):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""

    if user_id not in user_data:
        return

    step = user_data[user_id].get("step", 0)

    if step == 1:
        user_data[user_id]["name"] = text
        user_data[user_id]["step"] = 2
        await message.answer("Отлично! Второй вопрос:\n\n<b>Введите ваш номер телефона</b>:", parse_mode="HTML")

    elif step == 2:
        user_data[user_id]["phone"] = text
        user_data[user_id]["step"] = 3
        await message.answer("Третий вопрос:\n\n<b>Укажите ваш никнейм в Telegram</b>:", parse_mode="HTML")

    elif step == 3:
        user_data[user_id]["nickname"] = text
        user_data[user_id]["step"] = 4
        await message.answer("Четвёртый вопрос:\n\n<b>В каком городе вы работаете?</b>", parse_mode="HTML")

    elif step == 4:
        user_data[user_id]["city"] = text
        user_data[user_id]["step"] = 5
        await message.answer("Последний вопрос:\n\n<b>У вас уже есть клиент на покупку недвижимости?</b> (Да / Нет)", parse_mode="HTML")

    elif step == 5:
        answer = text.lower().strip()
        if answer not in ["да", "нет"]:
            await message.answer("Пожалуйста, ответьте «Да» или «Нет».")
            return

        user_data[user_id]["has_client_in_thailand"] = answer.capitalize()
        user_data[user_id]["telegram_id"] = str(user_id)
        user_data[user_id]["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        await message.answer("⌛ Сохраняю данные...")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(GOOGLE_SCRIPT_URL, json=user_data[user_id], timeout=15) as resp:
                    if await resp.text() == "OK":
                        await message.answer("✅ Данные сохранены!")
            except Exception as e:
                logger.error(f"Ошибка таблицы: {e}")

        await message.answer(f"Теперь перейдите по ссылке:\n\nhttps://t.me/RAI_service_group")
        user_data.pop(user_id, None)

# ========================================================
# 🚀 ЗАПУСК
# ========================================================

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Бот запущен (Режим тишины в группах включен)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
