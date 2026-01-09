import os
import logging
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ChatJoinRequest
from aiogram.filters import Command
import asyncio

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_SCRIPT_URL = os.getenv("GOOGLE_SCRIPT_URL")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

user_data = {}

# ========================================================
# ✅ АВТО-ОДОБРЕНИЕ + ПОДТВЕРЖДЕНИЕ ПОЛЬЗОВАТЕЛЮ
# ========================================================

@router.chat_join_request()
async def auto_approve(chat_join: ChatJoinRequest):
    user_id = chat_join.from_user.id
    user_id_str = str(user_id)
    
    async with aiohttp.ClientSession() as session:
        try:
            # Проверяем верификацию в таблице
            check_url = f"{GOOGLE_SCRIPT_URL}?action=check_user&telegram_id={user_id_str}"
            async with session.get(check_url, timeout=10) as resp:
                status = await resp.text()
                
                if status.strip() == "registered":
                    # 1. Одобряем заявку
                    await chat_join.approve()
                    logger.info(f"✅ Пользователь {user_id} одобрен автоматически.")
                    
                    # 2. Шлём подтверждение в личку
                    try:
                        await bot.send_message(
                            user_id, 
                            "<b>Ваша заявка одобрена!</b> 🎉\n\n"
                            "Добро пожаловать в закрытую группу RAI. "
                            "Теперь вам доступен весь обучающий контент и поддержка команды.",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.warning(f"Не удалось отправить уведомление в личку {user_id}: {e}")
                else:
                    logger.warning(f"⏳ Юзер {user_id} подал заявку без верификации.")
                    # Опционально: можно написать ему в личку, чтобы прошел анкету
        except Exception as e:
            logger.error(f"Ошибка в процессе одобрения: {e}")

# ========================================================
# 🛡️ РЕЖИМ ТИШИНЫ И СЕРВИСНЫЕ ФУНКЦИИ
# ========================================================

@router.message(F.chat.type.in_({"group", "supergroup"}))
async def silence_in_groups(message: Message):
    return

@router.message(F.chat.type == "private", F.photo | F.animation | F.video)
async def get_media_id(message: Message):
    if message.photo:
        await message.answer(f"ID фото: <code>{message.photo[-1].file_id}</code>", parse_mode="HTML")
    elif message.animation:
        await message.answer(f"ID GIF: <code>{message.animation.file_id}</code>", parse_mode="HTML")
    elif message.video:
        await message.answer(f"ID VIDEO: <code>{message.video.file_id}</code>", parse_mode="HTML")

# ========================================================
# 📝 АНКЕТА И СОХРАНЕНИЕ
# ========================================================

@router.message(F.chat.type == "private", Command("start"))
async def start(message: Message):
    user_id = str(message.from_user.id)
    async with aiohttp.ClientSession() as session:
        try:
            check_url = f"{GOOGLE_SCRIPT_URL}?action=check_user&telegram_id={user_id}"
            async with session.get(check_url, timeout=10) as resp:
                if (await resp.text()).strip() == "registered":
                    await message.answer("✅ Вы уже верифицированы! Ссылка на группу: https://t.me/RAI_service_group")
                    return 
        except Exception: pass

    WELCOME_VIDEO_ID = "BAACAgIAAxkBAAIEA2lb6OOI4SgnsGqibms4cbfJCQWzAAJvkQAC5bngSoh4P26VZWLsOAQ"
    await message.answer_video(
        video=WELCOME_VIDEO_ID,
        caption="👋 Привет! Пройдите короткую анкету для доступа к RAI.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Начать", callback_data="paid")]]),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "paid")
async def start_anketa(callback: CallbackQuery):
    user_data[callback.from_user.id] = {"step": 1}
    await callback.message.answer("<b>Как вас зовут?</b>", parse_mode="HTML")

@router.message(F.chat.type == "private")
async def handle_message(message: Message):
    user_id = message.from_user.id
    if user_id not in user_data: return
    text = message.text.strip() if message.text else ""
    step = user_data[user_id].get("step", 0)

    # Простая логика переключения шагов
    if step == 1:
        user_data[user_id]["name"] = text
        user_data[user_id]["step"] = 2
        await message.answer("<b>Введите ваш номер телефона:</b>", parse_mode="HTML")
    elif step == 2:
        user_data[user_id]["phone"] = text
        user_data[user_id]["step"] = 3
        await message.answer("<b>Ваш никнейм в Telegram:</b>", parse_mode="HTML")
    elif step == 3:
        user_data[user_id]["nickname"] = text
        user_data[user_id]["step"] = 4
        await message.answer("<b>В каком городе вы работаете?</b>", parse_mode="HTML")
    elif step == 4:
        user_data[user_id]["city"] = text
        user_data[user_id]["step"] = 5
        await message.answer("<b>Есть ли клиент на покупку недвижимости? (Да/Нет)</b>", parse_mode="HTML")
    elif step == 5:
        user_data[user_id]["has_client_in_thailand"] = text.capitalize()
        user_data[user_id]["telegram_id"] = str(user_id)
        user_data[user_id]["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        await message.answer("⌛ Сохраняю ваши данные...")
        async with aiohttp.ClientSession() as session:
            try:
                # Отправляем JSON в Google Script
                await session.post(GOOGLE_SCRIPT_URL, json=user_data[user_id], timeout=15)
                await message.answer(
                    "✅ Данные сохранены!\n\n"
                    "Теперь нажмите кнопку <b>'Подать заявку'</b> по ссылке ниже. "
                    "Я одобрю её автоматически в течение секунды!", 
                    parse_mode="HTML"
                )
                await message.answer("https://t.me/RAI_service_group")
            except Exception as e:
                logger.error(f"Ошибка сохранения: {e}")
                await message.answer("❌ Ошибка связи с базой. Попробуйте подать заявку позже.")
        
        user_data.pop(user_id, None)

# ========================================================
# 🚀 ЗАПУСК
# ========================================================

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    # Слушаем сообщения, кнопки и заявки на вступление
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_join_request"])

if __name__ == "__main__":
    asyncio.run(main())
