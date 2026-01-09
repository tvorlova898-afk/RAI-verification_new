import os
import asyncio
import aiohttp
import logging
from datetime import datetime
from dotenv import load_dotenv
import pytz
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ChatJoinRequest
from aiogram.filters import Command

# 1. Настройки и инициализация
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
APPS_SCRIPT_URL = os.getenv("GOOGLE_SCRIPT_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
moscow_tz = pytz.timezone('Europe/Moscow')
WEEKDAYS_RU = {0:"Понедельник", 1:"Вторник", 2:"Среда", 3:"Четверг", 4:"Пятница", 5:"Суббота", 6:"Воскресенье"}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Временное хранилище анкет
user_data = {}
DB_FILE = "sent_tasks.txt"

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def load_sent_tasks():
    if not os.path.exists(DB_FILE): return set()
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_sent_task(task_key):
    with open(DB_FILE, "a", encoding="utf-8") as f:
        f.write(f"{task_key}\n")

def normalize_time(time_str):
    try:
        parts = str(time_str).strip().split(':')
        if len(parts) < 2: return None
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}"
    except Exception: return None

# ========================================================
# ✅ АВТО-ОДОБРЕНИЕ ЗАЯВОК В ГРУППУ
# ========================================================

@router.chat_join_request()
async def auto_approve(chat_join: ChatJoinRequest):
    user_id = chat_join.from_user.id
    user_id_str = str(user_id)
    logger.info(f"Заявка на вход от {user_id}")
    
    async with aiohttp.ClientSession() as session:
        try:
            check_url = f"{APPS_SCRIPT_URL}?action=check_user&telegram_id={user_id_str}"
            async with session.get(check_url, timeout=10) as resp:
                status = await resp.text()
                
                if status.strip() == "registered":
                    await chat_join.approve()
                    logger.info(f"✅ Одобрен: {user_id}")
                    try:
                        await bot.send_message(user_id, "<b>Ваша заявка одобрена!</b> 🎉\nДобро пожаловать в RAI.", parse_mode="HTML")
                    except: pass
                else:
                    logger.warning(f"⏳ Юзер {user_id} не верифицирован.")
        except Exception as e:
            logger.error(f"Ошибка в автоодобрении: {e}")

# ========================================================
# 🛡️ ФИЛЬТРЫ И СЕРВИСНЫЕ ФУНКЦИИ
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
# 📝 АНКЕТА И ПРОВЕРКА
# ========================================================

@router.message(F.chat.type == "private", Command("start"))
async def start(message: Message):
    user_id = str(message.from_user.id)
    async with aiohttp.ClientSession() as session:
        try:
            check_url = f"{APPS_SCRIPT_URL}?action=check_user&telegram_id={user_id}"
            async with session.get(check_url, timeout=10) as resp:
                if (await resp.text()).strip() == "registered":
                    await message.answer("✅ Вы уже верифицированы!\nГруппа: https://t.me/RAI_service_group")
                    return 
        except Exception: pass

    WELCOME_VIDEO_ID = "BAACAgIAAxkBAAIEA2lb6OOI4SgnsGqibms4cbfJCQWzAAJvkQAC5bngSoh4P26VZWLsOAQ"
    await message.answer_video(
        video=WELCOME_VIDEO_ID,
        caption="👋 Привет! Пройдите анкету для доступа.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Начать", callback_data="paid")]]),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "paid")
async def start_anketa(callback: CallbackQuery):
    user_data[callback.from_user.id] = {"step": 1}
    await callback.message.answer("<b>Как вас зовут?</b>", parse_mode="HTML")

@router.message(F.chat.type == "private")
async def handle_anketa(message: Message):
    user_id = message.from_user.id
    if user_id not in user_data: return
    text = message.text.strip() if message.text else ""
    step = user_data[user_id].get("step", 0)

    if step == 1:
        user_data[user_id]["name"] = text
        user_data[user_id]["step"] = 2
        await message.answer("<b>Ваш номер телефона:</b>", parse_mode="HTML")
    elif step == 2:
        user_data[user_id]["phone"] = text
        user_data[user_id]["step"] = 3
        await message.answer("<b>Ваш никнейм в Telegram:</b>", parse_mode="HTML")
    elif step == 3:
        user_data[user_id]["nickname"] = text
        user_data[user_id]["step"] = 4
        await message.answer("<b>Ваш город:</b>", parse_mode="HTML")
    elif step == 4:
        user_data[user_id]["city"] = text
        user_data[user_id]["step"] = 5
        await message.answer("<b>Есть клиент? (Да/Нет):</b>", parse_mode="HTML")
    elif step == 5:
        user_data[user_id]["has_client_in_thailand"] = text.capitalize()
        user_data[user_id]["telegram_id"] = str(user_id)
        user_data[user_id]["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        await message.answer("⌛ Сохраняю...")
        async with aiohttp.ClientSession() as session:
            try:
                await session.post(APPS_SCRIPT_URL, json=user_data[user_id], timeout=15)
                await message.answer("✅ Сохранено! Подайте заявку в группу:\nhttps://t.me/RAI_service_group")
            except:
                await message.answer("❌ Ошибка связи, подайте заявку позже.")
        user_data.pop(user_id, None)

# ========================================================
# 🚀 РАССЫЛКА И ЗАПУСК
# ========================================================

async def check_and_send():
    async with aiohttp.ClientSession() as session:
        while True:
            now = datetime.now(moscow_tz)
            today_str = now.strftime("%Y-%m-%d")
            curr_day = WEEKDAYS_RU[now.weekday()]
            sent_tasks = load_sent_tasks()
            try:
                async with session.get(f"{APPS_SCRIPT_URL}?action=get_all_schedule", timeout=30) as resp:
                    if resp.status == 200:
                        schedule = await resp.json()
                        for job in schedule:
                            job_id = str(job.get('job_id'))
                            table_time_str = normalize_time(job.get('time', ''))
                            if str(job.get('day', '')).strip() == curr_day and table_time_str:
                                task_key = f"{today_str}_{job_id}"
                                if task_key in sent_tasks: continue
                                
                                t_h, t_m = map(int, table_time_str.split(':'))
                                now_dt = datetime.now(moscow_tz).replace(second=0, microsecond=0)
                                job_dt = now_dt.replace(hour=t_h, minute=t_m)
                                if 0 <= (now_dt - job_dt).total_seconds() / 60 <= 15:
                                    logger.info(f"🚀 Рассылка {job_id}")
                                    async with session.get(f"{APPS_SCRIPT_URL}?action=get_leads") as l_resp:
                                        leads = (await l_resp.json()).get("ids", [])
                                    for uid in leads:
                                        try:
                                            if int(uid) < 0: continue
                                            await bot.send_message(uid, job.get('text', ''), parse_mode="HTML")
                                            await asyncio.sleep(0.05)
                                        except: continue
                                    save_sent_task(task_key)
            except Exception as e:
                logger.error(f"Ошибка рассылки: {e}")
            await asyncio.sleep(60)

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(check_and_send())
    logger.info("Бот запущен!")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_join_request"])

if __name__ == "__main__":
    asyncio.run(main())
