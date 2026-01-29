import asyncio
import time
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InputMediaPhoto,
    InputMediaVideo
)
from aiogram.filters import CommandStart

# ====== НАСТРОЙКИ ======
TOKEN = "8572538615:AAHUm_2BsgjG6LMEI0NSXLiXGwFtlTRj2kQ"
CHANNEL_ID = "@asianlalaland"
ADMINS = [7053972867, 1679781763]   # список ID админов
SPAM_TIME = 10                     # антиспам в секундах
# =======================

bot = Bot(TOKEN)
dp = Dispatcher()

user_posts = {}
last_time = {}

# ---------- АНТИСПАМ ----------
def anti_spam(user_id: int) -> bool:
    now = time.time()
    if user_id in last_time and now - last_time[user_id] < SPAM_TIME:
        return False
    last_time[user_id] = now
    return True

# ---------- /START ----------
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Привеет! 👋\n"
        "Сюда ты можешь отправить любое видео / фото / текст\n"
        "по тематике канала, не нарушающее правила 🫶🏻"
    )

# ---------- ПРИЁМ СООБЩЕНИЙ ----------
@dp.message((F.text | F.photo | F.video | F.media_group_id) & ~F.command())
async def get_post(message: Message):
    if not anti_spam(message.from_user.id):
        await message.answer("Слишком часто. Подожди ⏳")
        return

    # --- Проверка медиа ---
    media = None
    media_type = "text"

    if message.media_group_id:
        media = []
        if getattr(message, 'photo', None):
            for m in message.photo:
                media.append({"id": m.file_id, "type": "photo"})
        if getattr(message, 'video', None):
            media.append({"id": message.video.file_id, "type": "video"})
    elif message.photo:
        media = {"id": message.photo[-1].file_id, "type": "photo"}
        media_type = "photo"
    elif getattr(message, 'video', None):
        media = {"id": message.video.file_id, "type": "video"}
        media_type = "video"

    user_posts[message.from_user.id] = {
        "text": message.caption or message.text,
        "media": media,
        "media_type": media_type,
        "user": message.from_user,
        "done": False,
        "admins_msgs": []  # сохраняем message_id для всех админов
    }

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Анонимно", callback_data="anon"),
            InlineKeyboardButton(text="С именем", callback_data="name")
        ],
        [
            InlineKeyboardButton(text="Отмена", callback_data="cancel")
        ]
    ])

    await message.answer("Как публикуем?", reply_markup=kb)

# ---------- ВЫБОР АНОНИМНОСТИ ----------
@dp.callback_query(F.data.in_(["anon", "name"]))
async def send_to_admins(callback: CallbackQuery):
    data = user_posts.get(callback.from_user.id)
    if not data:
        await callback.answer("Данные не найдены", show_alert=True)
        return

    anon = callback.data == "anon"
    caption = data["text"] or ""
    if not anon:
        u = data["user"]
        caption += f"\n\nОт: @{u.username or u.full_name}"

    data["final_text"] = caption

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Опубликовать",
                callback_data=f"post:{callback.from_user.id}"
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"decline:{callback.from_user.id}"
            )
        ]
    ])

    for admin in ADMINS:
        media = data.get("media")
        if isinstance(media, list):
            input_media = []
            for m in media:
                if m["type"] == "photo":
                    input_media.append(InputMediaPhoto(media=m["id"]))
                elif m["type"] == "video":
                    input_media.append(InputMediaVideo(media=m["id"]))
            if input_media:
                await bot.send_media_group(admin, input_media)
            msg = await bot.send_message(admin, caption, reply_markup=kb)
        elif media:
            if data["media_type"] == "video":
                msg = await bot.send_video(admin, media["id"], caption=caption, reply_markup=kb)
            else:
                msg = await bot.send_photo(admin, media["id"], caption=caption, reply_markup=kb)
        else:
            msg = await bot.send_message(admin, caption, reply_markup=kb)

        data["admins_msgs"].append(msg.message_id)

    await callback.message.edit_text("Отправлено на модерацию 🫡")

# ---------- ПУБЛИКАЦИЯ ----------
@dp.callback_query(F.data.startswith("post:"))
async def publish(callback: CallbackQuery):
    uid = int(callback.data.split(":")[1])
    data = user_posts.get(uid)

    if not data:
        await callback.answer("Пост не найден", show_alert=True)
        return

    if data.get("done"):
        await callback.answer("Уже обработано ✅", show_alert=True)
        return
    data["done"] = True

    text = data.get("final_text", data["text"])
    media = data.get("media")

    if isinstance(media, list):
        input_media = []
        for m in media:
            if m["type"] == "photo":
                input_media.append(InputMediaPhoto(media=m["id"]))
            elif m["type"] == "video":
                input_media.append(InputMediaVideo(media=m["id"]))
        await bot.send_media_group(CHANNEL_ID, input_media)
    elif media:
        if data["media_type"] == "video":
            await bot.send_video(CHANNEL_ID, media["id"], caption=text)
        else:
            await bot.send_photo(CHANNEL_ID, media["id"], caption=text)
    else:
        await bot.send_message(CHANNEL_ID, text)

    # Автоответ пользователю
    await bot.send_message(uid, "Твое предложение опубликовано ❤️")

    # Обновляем все админские сообщения
    for i, admin in enumerate(ADMINS):
        try:
            await bot.edit_message_text(
                chat_id=admin,
                message_id=data["admins_msgs"][i],
                text="✅ Уже опубликовано"
            )
        except:
            pass

# ---------- ОТКЛОНЕНИЕ ----------
@dp.callback_query(F.data.startswith("decline:"))
async def decline(callback: CallbackQuery):
    uid = int(callback.data.split(":")[1])
    data = user_posts.get(uid)

    if not data:
        await callback.answer("Пост не найден", show_alert=True)
        return

    if data.get("done"):
        await callback.answer("Уже обработано ❌", show_alert=True)
        return
    data["done"] = True

    # Автоответ пользователю
    await bot.send_message(uid, "К сожалению, предложение не прошло модерацию 😔")

    # Обновляем все админские сообщения
    for i, admin in enumerate(ADMINS):
        try:
            await bot.edit_message_text(
                chat_id=admin,
                message_id=data["admins_msgs"][i],
                text="❌ Отклонено"
            )
        except:
            pass

# ---------- ОТМЕНА ----------
@dp.callback_query(F.data == "cancel")
async def cancel(callback: CallbackQuery):
    user_posts.pop(callback.from_user.id, None)
    await callback.message.edit_text("Отменено ❎")

# ---------- ЗАПУСК ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())