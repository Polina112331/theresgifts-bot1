from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio
import os
from datetime import datetime

#GOOGLE SHEETS INTEGRATION
import json
from google.oauth2.service_account import Credentials
import gspread

raw_sheet = None      # Первый лист: сырые события
analytics_sheet = None  # Второй лист: для аналитики

# Агрегированные данные 
unique_users = set()
category_counts = {}
item_counts = {}

try:
    creds_json_str = os.getenv("CREDENTIALS_JSON")
    if not creds_json_str:
        raise ValueError("CREDENTIALS_JSON не задана")

    creds_info = json.loads(creds_json_str)
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    client = gspread.authorize(creds)
    
    spreadsheet = client.open("theresgifts-stats")
    raw_sheet = spreadsheet.sheet1  # Лист1: Статистика
    analytics_sheet = spreadsheet.worksheet("Аналитика")  # Лист2: Аналитика
    
    print("✅ Google Sheets подключён (2 листа)")
except Exception as e:
    print(f"⚠️ Google Sheets НЕ подключён: {e}")
    raw_sheet = None
    analytics_sheet = None

def write_detailed_analytics():
    if not analytics_sheet:
        return
    try:
        
        analytics_sheet.clear()
        analytics_sheet.update([[
            "Тип", "Имя", "Количество", "Категория"
        ]])

        # Уникальные пользователи
        analytics_sheet.append_row(["Уникальные пользователи", "", len(unique_users), ""])

        # Категории
        for cat, cnt in sorted(category_counts.items()):
            analytics_sheet.append_row(["Категория", cat, cnt, ""])

        # Подарки
        for item, cnt in sorted(item_counts.items()):
            # Определяем категорию по имени (простой способ — искать в GIFTS)
            found_cat = ""
            for cat, gifts in GIFTS.items():
                for g in gifts:
                    if g["caption"] == item:
                        found_cat = cat
                        break
                if found_cat:
                    break
            analytics_sheet.append_row(["Подарок", item, cnt, found_cat])

        print("✅ Детальная аналитика записана в лист 'Аналитика'")
    except Exception as e:
        print(f"❌ Ошибка записи детальной аналитики: {e}")

def log_to_sheet(user_id, action, category=None, item_name=None):
    """Логирует событие и обновляет агрегированную аналитику"""
    timestamp = datetime.now().isoformat()
    row = [timestamp, str(user_id), action, category or "", item_name or ""]
    
    # Запись в первый лист (сырые данные)
    if raw_sheet:
        try:
            raw_sheet.append_row(row)
        except Exception as e:
            print(f"❌ Ошибка записи в Статистику: {e}")

    # Обновление агрегатов в памяти
    unique_users.add(str(user_id))
    if action == "view":
        if category:
            category_counts[category] = category_counts.get(category, 0) + 1
        if item_name:
            item_counts[item_name] = item_counts.get(item_name, 0) + 1

    # Запись структурированной аналитики
    write_detailed_analytics()

# === TELEGRAM BOT SETUP ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ Переменная окружения BOT_TOKEN не задана!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

#Категории
CATEGORIES = {
    "home": "🏡 Для дома",
    "sport": "⚽️ Спорт",
    "travel": "🗺️ Путешественникам",
    "hobbies": "🧩 Увлечения",
    "style": "👜 Стиль",
    "health": "🧘‍♀️ Здоровье и красота",
}

#Подарки 
GIFTS = {
    "home": [
        {
            "photo": "https://optim.tildacdn.com/stor3533-3938-4764-b831-663332343431/-/format/webp/74328538.jpg.webp",
            "caption": "Уютный плед для дома 🏡",
            "url": "https://papershoot.ru/catalog"
        }
    ],
    "style": [
        {
            "photo": "https://ir.ozone.ru/s3/multimedia-1-h/7512943697.jpg",
            "caption": "Чёрный фон",
            "url": "https://www.ozon.ru/product/fotofon-hromakey-1-5h2-metra-chernyy-606611928/?at=OgtEX4pAVIklpXl4T30ZLGJFk0kLVwt1r9pvlUkkm3K2"
        }
    ],
    "hobbies": [
        {
            "photo": "https://optim.tildacdn.com/stor6638-3064-4331-b233-613063636338/-/format/webp/63972773.png.webp",
            "caption": "Бумажная камера со сменными кейсами",
            "url": "https://papershoot.ru/catalog"
        }
    ],
    "sport": [
        {
            "photo": "https://img-edg.joomcdn.net/eb767a9d1cf723fbc9cb3cd3682484a14a8ab921_original.jpeg",
            "caption": "Мягкая фляга для бега и походов",
            "url": "https://www.ozon.ru/product/butylka-dlya-vody-sportivnaya-250-ml-myagkaya-flyaga-dlya-bega-325671713/?at=QktJqrk6GcGWBVQ9tGAWV1QtynXlM6hPR0j7yHZAq6pQ"
        },
        {
            "photo": "https://ae04.alicdn.com/kf/S9c6601c12b87435abd95c850f1ca5db3k.jpg_640x640.jpg",
            "caption": "Ручной тренажер для большого тенниса",
            "url": "https://www.ozon.ru/product/nabor-dlya-bolshogo-tennisa-1762914482/?at=oZt6GZrXNT588m8wsBYLwp7TW3m0oKID3PEG3CgJp4n4"
        }
    ],
    "health": [],  # пустая категория 
}

class GiftState(StatesGroup):
    choosing_category = State()
    showing_gifts = State()

def categories_kb():
    builder = InlineKeyboardBuilder()
    for key, label in CATEGORIES.items():
        if key in GIFTS and GIFTS[key]:
            builder.button(text=label, callback_data=f"cat:{key}")
    builder.adjust(2)
    return builder.as_markup()

def gift_nav_kb(category: str, index: int, total: int):
    builder = InlineKeyboardBuilder()
    if index > 0:
        builder.button(text="🔙 Назад", callback_data=f"gift:{category}:{index-1}")
    builder.button(text="💳 Купить", url=GIFTS[category][index]["url"])
    if index < total - 1:
        builder.button(text="▶️ Вперёд", callback_data=f"gift:{category}:{index+1}")
    builder.button(text="🏠 Главное меню", callback_data="main_menu")
    if total == 1:
        builder.adjust(1, 1)
    elif index == 0 or index == total - 1:
        builder.adjust(2, 1)
    else:
        builder.adjust(2, 1, 1)
    return builder.as_markup()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    log_to_sheet(message.from_user.id, "start")
    await message.answer(
        "Привет! Это бот Telegram-канала «Что тебе подарить?». "
        "Здесь есть добрые и нужные подарки на весь год 🪄\n\n"
        "Какой ищем подарок?",
        reply_markup=categories_kb()
    )
    await state.set_state(GiftState.choosing_category)

@router.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "Привет! Это бот Telegram-канала «Что тебе подарить?». "
        "Здесь есть добрые и нужные подарки на весь год 🪄\n\n"
        "Какой ищем подарок?",
        reply_markup=categories_kb()
    )
    await state.set_state(GiftState.choosing_category)

@router.callback_query(GiftState.choosing_category, F.data.startswith("cat:"))
async def show_first_gift(callback: CallbackQuery, state: FSMContext):
    cat = callback.data.split(":")[1]
    if cat not in GIFTS or not GIFTS[cat]:
        await callback.answer("Подарков в этой категории пока нет 😢", show_alert=True)
        return

    item = GIFTS[cat][0]
    try:
        media = InputMediaPhoto(media=item["photo"], caption=item["caption"])
        await callback.message.edit_media(media=media, reply_markup=gift_nav_kb(cat, 0, len(GIFTS[cat])))
        await state.update_data(category=cat, gifts=GIFTS[cat], gift_index=0)
        await state.set_state(GiftState.showing_gifts)
        log_to_sheet(
            user_id=callback.from_user.id,
            action="view",
            category=cat,
            item_name=item["caption"]
        )
    except Exception as e:
        print(f"Ошибка загрузки фото: {e}")
        await callback.answer("Не удалось загрузить подарок 😕", show_alert=True)

@router.callback_query(GiftState.showing_gifts, F.data.startswith("gift:"))
async def navigate_gifts(callback: CallbackQuery, state: FSMContext):
    _, cat, idx_str = callback.data.split(":")
    index = int(idx_str)
    gifts = GIFTS.get(cat, [])
    if index < 0 or index >= len(gifts):
        return

    item = gifts[index]
    try:
        media = InputMediaPhoto(media=item["photo"], caption=item["caption"])
        await callback.message.edit_media(media=media, reply_markup=gift_nav_kb(cat, index, len(gifts)))
        await state.update_data(gift_index=index)
        
        log_to_sheet(
            user_id=callback.from_user.id,
            action="view",
            category=cat,
            item_name=item["caption"]
        )
    except Exception as e:
        print(f"Ошибка при навигации: {e}")
        await callback.answer("Ошибка загрузки 😕", show_alert=True)

async def main():
    print("✅ Бот запущен!")
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал Ctrl+C. Завершаем...")
    finally:
        await bot.session.close()
        print("👋 Бот остановлен.")

if __name__ == "__main__":
    asyncio.run(main())
