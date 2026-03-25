from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
import asyncio
import os
from datetime import datetime

#GOOGLE SHEETS INTEGRATION 
import json
from google.oauth2.service_account import Credentials
import gspread

raw_sheet = None
analytics_sheet = None

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
    raw_sheet = spreadsheet.sheet1
    analytics_sheet = spreadsheet.worksheet("Аналитика")
    
    print("✅ Google Sheets подключён")
except Exception as e:
    print(f"⚠️ Google Sheets НЕ подключён: {e}")
    raw_sheet = None
    analytics_sheet = None

#TELEGRAM BOT SETUP
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не задан!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

#ПАРАМЕТРЫ КАНАЛА 
CHANNEL_USERNAME = "goodwishlist"

async def is_user_subscribed(user_id: int) -> bool:
    try:
        chat_member = await bot.get_chat_member(chat_id=f"@{CHANNEL_USERNAME}", user_id=user_id)
        return chat_member.status not in ("left", "kicked")
    except Exception:
        return False

#MIDDLEWARE 
@dp.message.middleware()
async def subscription_middleware(handler, event: Message, data):
    if event.text and event.text.startswith("/start"):
        return await handler(event, data)
    if not await is_user_subscribed(event.from_user.id):
        await event.answer(
            f"🔒 Подпишитесь на [@{CHANNEL_USERNAME}](https://t.me/{CHANNEL_USERNAME}), чтобы пользоваться ботом.",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        return
    return await handler(event, data)

@dp.callback_query.middleware()
async def subscription_callback_middleware(handler, event: CallbackQuery, data):
    if not await is_user_subscribed(event.from_user.id):
        await event.answer("❌ Вы не подписаны на канал.", show_alert=True)
        return
    return await handler(event, data)

#АНАЛИТИКА 
_analytics_update_task = None

def write_detailed_analytics():
    if not analytics_sheet:
        return
    try:
        analytics_sheet.clear()
        analytics_sheet.update([["Тип", "Имя", "Количество", "Категория"]])
        
        analytics_sheet.append_row(["Уникальные пользователи", "", len(unique_users), ""])
        for cat, cnt in sorted(category_counts.items()):
            analytics_sheet.append_row(["Категория", cat, cnt, ""])
        for item, cnt in sorted(item_counts.items()):
            found_cat = ""
            for cat, gifts in GIFTS.items():
                for g in gifts:
                    if g["caption"] == item:
                        found_cat = cat
                        break
                if found_cat:
                    break
            analytics_sheet.append_row(["Подарок", item, cnt, found_cat])
        print("✅ Аналитика обновлена")
    except Exception as e:
        print(f"❌ Ошибка аналитики: {e}")

async def delayed_analytics_update():
    await asyncio.sleep(15)
    write_detailed_analytics()

def log_to_sheet(user_id, action, category=None, item_name=None):
    global _analytics_update_task
    timestamp = datetime.now().isoformat()
    row = [timestamp, str(user_id), action, category or "", item_name or ""]
    
    if raw_sheet:
        try:
            raw_sheet.append_row(row)
        except Exception as e:
            print(f"❌ Ошибка записи в Статистику: {e}")

    unique_users.add(str(user_id))
    if action == "view":
        if category:
            category_counts[category] = category_counts.get(category, 0) + 1
        if item_name:
            item_counts[item_name] = item_counts.get(item_name, 0) + 1

    if _analytics_update_task:
        _analytics_update_task.cancel()
    _analytics_update_task = asyncio.create_task(delayed_analytics_update())

#КАТЕГОРИИ И ПОДАРКИ 
CATEGORIES = {
    "home": "🏡 Для дома",
    "sport": "⚽️ Спорт",
    "travel": "🗺️ Путешественникам",
    "hobbies": "🧩 Увлечения",
    "style": "👜 Стиль",
    "health": "🧘‍♀️ Здоровье и красота",
    "pets": "🐶 Питомцы",
    "date": "🍸 Куда сводить",
}

GIFTS = {
    "home": [
        {
            "photo": "https://basket-27.wbbasket.ru/vol4940/part494024/494024695/images/big/7.webp",
            "caption": "Кружка-домик как из Pinterest. Делает любую кухню в сто раз уютнее — отлично подойдет друзьям на новоселье",
            "url": "https://www.wildberries.ru/catalog/494024695/detail.aspx"
        },
        {
            "photo": "https://optim.tildacdn.biz/stor6264-3964-4563-a365-313361343435/-/format/webp/7243e82075f0e91271261965de4fec61.jpg.webp",
            "caption": "Мини-вазочки на магните. Дает вторую жизнь увядающему букету — можно обрезать хорошие цветы и украсить холодильник, например",
            "url": "https://lubiceramics.shop/"
        },
        {
            "photo": "https://basket-25.wbbasket.ru/vol4498/part449876/449876738/images/big/9.webp",
            "caption": "Винтажная чайная пара на 250 мл. Есть с молочным и синим рисунком",
            "url": "https://www.wildberries.ru/catalog/449876738/detail.aspx"
        },
        {
            "photo": "https://shop.goldenmandarin.ru/upload/iblock/bff/bffd5b5af6cb43340337cb5a4ddc14fc.jpg",
            "caption": "Подушка от отеков и ранних морщин. Кстати, это целая серия: есть подушки от акне, для увлажнения и охлаждения. Или наволочки из шелка с гиалуроновой кислотой...",
            "url": "https://beautysleep.ru/omnia"
        },
        {
            "photo": "https://basket-30.wbbasket.ru/vol5958/part595890/595890645/images/big/5.webp",
            "caption": "Реалистичная свеча-тарталетка с голубикой, пахнет ванилью и корицей. Как и к многим свечкам на вб нужно докупить подставку, чтобы воск не растекался",
            "url": "https://www.wildberries.ru/catalog/595890645/detail.aspx"
        },
        {
            "photo": "https://vinyla.com/files/products/8b/121/77945/vinilovi-plativki-radiohead-ok-computer.1280x1280.jpg?af57fa2cb7f098ae88a424ecea65d8a8",
            "caption": "Виниловые пластинки. Бывает трудно найти слова поддержки, особенно если случившееся не исправить. А когда слова излишни, лучше дать человеку погоревать с правильной музыкой — поверьте, эта пластинка будет напоминать, что ваш близкий не остался один",
            "url": "https://clck.ru/3Sjw9F"
        },
        {
            "photo": "https://basket-19.wbbasket.ru/vol3151/part315119/315119516/images/big/1.webp",
            "caption": "Керамическая кружка с бантиком, покрытая радужной глазурью. Ее, кстати, можно мыть в посудомойке(не заставляйте своих ballet core бэстис мыть посуду...)",
            "url": "https://www.wildberries.ru/catalog/315119516/detail.aspx"
        },
        {
            "photo": "https://eurofashions.ru/wa-data/public/shop/products/44/04/10444/images/19347/19347.970.jpeg",
            "caption": "Чайный набор Hermes Passifolia из костяного фарфора. Принт очень яркий и качественный, неубиваемый даже посудомойкой",
            "url": "https://eurofashions.ru/nabor-chajnyh-par-hermes-passifolia-160-ml-10444/"
        },
        {
            "photo": "https://avatars.mds.yandex.net/get-mpic/17392064/2a000001988d574833abf44f5e817f3a009c/optimize",
            "caption": "Декоративная лампа в японском стиле под рисовую бумагу",
            "url": "https://clck.ru/3Sk243"
        }
    ],
    "style": [
        {
            "photo": "https://optim.tildacdn.com/stor3334-3462-4465-b564-396137623061/-/format/webp/5b94497c1c50ad6eb7fea7e596bd634d.jpg.webp",
            "caption": "Сумка Pauchok.",
            "url": "https://pauchok.store/hairybagxxl"
        },
        {
            "photo": "https://optim.tildacdn.com/stor3266-3132-4663-b561-363835636335/-/format/webp/e30e3aa027bff2d48a50d53aeb44d956.jpg.webp",
            "caption": "Брелок-обвес Wu-Sin/Five Elements.",
            "url": "https://deusplatform.ru/accessories/tproduct/1573202481-891732185002-brelok-wu-sin-five-elements"
        },
        {
            "photo": "https://optim.tildacdn.com/stor6462-6332-4866-b530-353135646531/-/format/webp/86a5ac270f232f54152b0a11a5c04c9d.png.webp",
            "caption": "Подарочная карта Deus Platform. Оч классный сайт с русскими дизайнерами.",
            "url": "https://deusplatform.ru/gifts/tproduct/1573180411-167590489292-podarochnaya-kartochka"
        },
        {
            "photo": "https://rerajewels.com/cdn/shop/files/C7CCE68D-CEF4-409A-B031-95CEBFA90820.jpg?v=1762536835",
            "caption": "Ангельский стак Rera. Посмотрите на сайте все комбинации, их много!",
            "url": "https://rerajewels.com/products/heaven-bound-earring-stack"
        },
        {
            "photo": "https://www.dionisjewelry.ru/wp-content/uploads/2026/03/img_2997-scaled-e1773135453936.webp",
            "caption": "Мужской браслет из серебра Dionis Jewelry.",
            "url": "https://www.dionisjewelry.ru/product/браслет-3/"
        }
    ],
    "hobbies": [
        {
            "photo": "https://www.igrotime.ru/upload/t/800-700im/large_foto/monopoly-attack-on-titan-final-season-eng.jpg",
            "caption": "Коллекционное издание Монополии(есть с Ведьмаком, Сумерками, Звездным Войнам, а также от брендов, например Juicy Couture). Инвестировать в недвижимость aot я особо не рекомендую...",
            "url": "https://valimo.ru/magazin/product/monopoliya-attack-on-titan-the-final-season-ataka-titanov-na-anglijskom-yazyke"
        },
        {
            "photo": "https://ir.ozone.ru/s3/multimedia-h/wc2500/6015006653.jpg",
            "caption": "Кассетный проигрыватель, если IPod недостаточно нишевый для вашего не-такого-как-все друга. Оч круто дополнить его кастомной кассетой с плейлистом вашей дружбы или песнями-ассоциациями с ним.",
            "url": "https://www.ozon.ru/product/kassetnyy-mp3-player-dlya-otsifrovki-audiokasset-175277300/"
        },
        {
            "photo": "https://mir-kubikov.ru/upload/iblock/bbe/bbe92260843323e1cd8beb78f8a003af.jpg",
            "caption": "Набор Lego. Можно поискать что-то для интерьера или по фандомам, их тоже много.",
            "url": "https://mir-kubikov.ru/catalog/10311/"
        },
        {
            "photo": "https://sun9-81.userapi.com/s/v1/ig2/rnoGYexv9PJrxJcvzqTWL6pVQ2RxPCdPvr6eEJFY56mZTOb6-eLql69OoRV9AvD0tdjM68DvmxtyNLZZhWUaAFam.jpg?quality=95",
            "caption": "Кастомные дайсы для настольных игр.",
            "url": "https://vk.com/market/product/dnd-days-d20-quotutiny-obryad-quot-227022586-13084523"
        },
        {
            "photo": "https://cs2.livemaster.ru/storage/3f/35/b93dcfe80d035f8cdaaf16596718--dlya-doma-i-interera-rumboks-po-foto-na-zakaz.jpg",
            "caption": "Румбокс на заказ по вашему фото. Например, если ваш друг скучает по дому или скоро переезжает, и хочет забрать частичку дома с собой. Или это фанат фандома, который узнает ту самую комнату из сотни других. Такой румбокс можно сделать, в целом, и самим.",
            "url": "https://livemaster.ru/item/51027960-dlya-doma-i-interera-rumboks-po-foto-na-zakaz"
        }
    ],
    "sport": [
        {
            "photo": "https://sport-marafon.ru/upload/iblock/3e1/2080-001.jpg",
            "caption": "Стропа для слэклайна(балансировки).",
            "url": "https://www.wildberries.ru/catalog/143294808/detail.aspx"
        },
        {
            "photo": "https://avatars.mds.yandex.net/get-mpic/15199813/2a0000019a7ccae435c0bfcb340df0d25a03/orig",
            "caption": "Тренажер для бокса с подключением к колонке.",
            "url": "https://clck.ru/3Sk2VC"
        },
        {
            "photo": "https://avatars.mds.yandex.net/get-mpic/12438903/2a00000196346f2f7cff80452c10e486e358/optimize",
            "caption": "Полотенце для спорта из микрофибры. В комплекте идет мешок",
            "url": "https://clck.ru/3Sk2hr"
        },
        {
            "photo": "https://foxpox.ru/upload/iblock/b24/gv3wr604zqmhpx4r8a7mvrzjdnk49cvy.jpg",
            "caption": "Умная скакалка с регулировкой длины и подсчетом калорий, прыжков и времени.",
            "url": "https://clck.ru/3Sk379"
        },
        {
            "photo": "https://avatars.mds.yandex.net/get-mpic/11477103/2a0000018c5003ee412b8e0a5bc45736d632/orig",
            "caption": "Спортивная сумка в розовом, бордовом, голубом и серых цветах — всегда пригодится под разные аутфиты.",
            "url": "https://clck.ru/3Sk3hH"
        },
        {
            "photo": "https://soccer-store.ru/images/gallery/originals/1667821886.jpg",
            "caption": "Тактическая доска для футбольного тренера. Интересно попробовать обычному игроку, полезно для профессионалов.",
            "url": "https://clck.ru/3Sk3zW"
        },
        {
            "photo": "https://avatars.mds.yandex.net/get-mpic/16286835/2a00000198e41c9e8ff2b20672a0eb775944/optimize",
            "caption": "Сумка для большого тенниса с местом под ракетку.",
            "url": "https://clck.ru/3Sk4Qc"
        },
        {
            "photo": "https://rus-tennis.ru/wp-content/uploads/2021/07/k-max-used_b38284bb-95b7-4a54-8f88-50badf2d2589.jpg",
            "caption": "Собиратель для теннисных мячей.",
            "url": "https://www.ozon.ru/product/korzina-dlya-tennisnyh-myachey-2608912067/"
        },
        {
            "photo": "https://sputnik.kg/img/101452/78/1014527858_243:0:3894:4016_1920x0_80_0_0_49888dacaefbf50b4ef03e7a5d0f9d35.jpg",
            "caption": "Традиционный лук для стрельбы, если в их плейлисте много монгольского горлового пения и группы The HU....",
            "url": "https://clck.ru/3Sk57h"
        }
    ],
    "health": [
        {
            "photo": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSnkmnZq8UTyXB0L83Aq6OOEKJTLRGYwtvmIw&s",
            "caption": "Умные наушники Incora. Серьги-сенсоры из золота 18k и титана. Отслеживают гормональный фон, фазу цикла, температуру тела, и помогают персонализировать сон, восстановление, тренировки и фертильность.",
            "url": "https://incorahealth.com/"
        },
        {
            "photo": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQtL9edosq7F2N_gbrEDRt3L64pTPxBdnwk_g&s",
            "caption": "Анализатор дыхания Foodmarble, который с помощью измерения водорода и метана определяет, какие продукты вызывают вздутие, воспаление, СИБР и другие проблемы с пищеварением.",
            "url": "https://foodmarble.com/store/foodmarble-aire-2"
        },
        {
            "photo": "https://theragunrussia.ru/images/cms/pictures/theragun5/smartgoggles_g2.jpg",
            "caption": "Очки Therabody с компрессией, вибрацией и легким теплом. Снижают напряжение, помогают при головной боли, расслабляют мышцы лица и ускоряют засыпание.",
            "url": "https://theragunrussia.ru/eye-mask-smart-goggles/"
        },
        {
            "photo": "https://vernik.me/upload/resize_cache/iblock/34f/rjyexqlw6fchu4d4dcdt9xpg3cqllgz6/900_900_1/3409109a-4f60-49d0-98cb-7557de8bf567_imageid.png",
            "caption": "Умный дыхательный тренажер Inex-Air, который помогает улучшить функцию легких, снизить стресс, сформировать здоровые дыхательные привычки и бросить курить.",
            "url": "https://vernik.me/catalog/umnyy_dyhatelnyy_trenazher_air_smart_lung_trainer_inex_air/"
        },
        {
            "photo": "https://predubezhdai.ru/images/resize:fill:1000:1200/aHR0cHM6Ly9iYzhlNGQ1Yi1kZmFjLTRjNTEtYjBjNi1mZGNmNDk5MGE1M2Yuc2Vsc3RvcmFnZS5ydS9EZXRzdHZvJTIwbWFzay9wcmUxLmpwZw==",
            "caption": "Маска-блин от Predubezhdai. Маска, блин.",
            "url": "https://predubezhdai.ru/product/mask-detstvo-98982401"
        }
    ], 
    "travel": [
        {
            "photo": "https://avatars.mds.yandex.net/get-mpic/7764504/img_id7115796403347315795.jpeg/optimize",
            "caption": "Складной стол с набором посуды. Поверьте, через пару дней жизни в палатке этот островок цивилизации вам поднимет настроение",
            "url": "https://clck.ru/3SkEwK"
        },
        {
            "photo": "https://optim.tildacdn.com/stor6638-3064-4331-b233-613063636338/-/format/webp/63972773.png.webp",
            "caption": "Бумажная камера со сменными кейсами(посмотрите, там оч большой выбор принтов)",
            "url": "https://papershoot.ru/catalog"
        },
        {
            "photo": "https://avatars.mds.yandex.net/get-mpic/15131989/2a00000196d8c6247d1bad2cd44603dfbe74/optimize",
            "caption": "Это складной стул, очень компактный и помещается в кармане. Ниче, пусть все смеются — посмотрим на них в двухчасовой очереди в завирусившийся рестик.",
            "url": "https://clck.ru/3SkJQe"
        },
        {
            "photo": "https://www.vx-shop.ru/upload/imgPodarki/0.6223.T24G/0.6223.T24G.jpg",
            "caption": "Швейцарский ножик с отверткой, пилкой, ножницами и прочим в любимом цвете. Для друзей, которые все время проходят сайд квесты в ирл.",
            "url": "https://www.vx-shop.ru/product/nozh_brelok_classic_sd_colors_tropical_surf_victorinox_0_6223_t24g/"
        },
        {
            "photo": "https://trendoptom.ru/image/cache/catalog/novinki/krasota-i-zdorove/uhod-za-volosami/stajlery/multistajler-besprovodnaya-plojka-dlya-zavivki-volos-4-500x500.jpg",
            "caption": "Беспроводной стайлер для волос. Пользовалась сама, держит заряд пару дней, быстро нагревается и ничего не весит. Альтернатива для прямых волос — портативный утюжок.",
            "url": "https://www.wildberries.ru/catalog/863749537/detail.aspx"
        },
        {
            "photo": "https://www.retyche.com/cdn/shop/files/RETYCHE_ECOM_BAG.ACC_04.02.20247653_146.jpg?v=1712154891",
            "caption": "Кастомная обложка на паспорт Louis Vuitton. Это обычная обложка, на которую можно ставить штампы из магазинов Louis Vuitton разных стран. Так же можно закастомить кошельки, записные книжки и так далее, но загранник кажется логичнее.",
            "url": "https://thesortage.com/products/passport-cover-monogram"
        },
        {
            "photo": "https://ir.ozone.ru/s3/multimedia-1-l/wc2500/9089190849.jpg",
            "caption": "Атомайзер для любимых духов в дорогу.",
            "url": "https://www.ozon.ru/product/atomayzer-dlya-duhov-5ml-2sht-1967730446/"
        },
        {
            "photo": "https://pcdn.goldapple.ru/p/p/19000455124/web/696d67416464335064705f35363233386235336432643834393065613565323166656334653630313734648de21f90fa8e115fullhd.webp",
            "caption": "Спрей-санитайзер для рук.",
            "url": "https://goldapple.ru/19000455124-black-vetiver-amber"
        },
        {
            "photo": "https://pcdn.goldapple.ru/p/p/19000448280/web/696d67416464335064705f36666339643939373138373034323438613033633431393439383635633939628ddf74ae95a3399fullhd.webp",
            "caption": "Набор ухода от Caudalie — идеальный подбор увлажняющих средств для долгих перелетов, плюс милая косметичка.",
            "url": "https://goldapple.ru/19000448280-your-hydration-ritual"
        }
    ],  
    "pets": [
        {
            "photo": "https://duepuntootto.com/cdn/shop/files/Margaret-Dog-Bag-Casentino-Wool-3.jpg?v=1746538940&width=1000",
            "caption": "Сумка-переноска для собак из натуральной кожи, шерсти овцы и альпаки.",
            "url": "https://duepuntootto.com/products/margaret-casentino-bag"
        },
        {
            "photo": "https://cdn-sh1.vigbo.com/shops/7536/products/26270972/images/3-029f6fa43d4a3ccdaae44d19ef6494f9.jpg",
            "caption": "Парный дождевик для собаки и вас!.",
            "url": "https://sharik-dog.com/shop/raincoat-any-weather-grey"
        },
        {
            "photo": "https://cdn-sh1.vigbo.com/shops/7536/products/23794598/images/3-2aff27f21743f4283cee19da636a10c6.jpg",
            "caption": "Бальзам-воск для лап. Маст-хэв! Увлажняет кожу, защищает от реагентов, а в версии, которую прикрепляю я, добавили эвкалипт — натуральный репеллент от комаров и блох.",
            "url": "https://sharik-dog.com/shop/paw-wax-eucalyptus"
        },
        {
            "photo": "https://cdn-st2.vigbo.com/u256397/142969/blog/6759222/6565840/86198627/1000-b9a91c0a80efd0e405c946979f253fb9.jpg",
            "caption": "Псумка DOGIBOGI. Непромокаемая, доступная и подходит большим собакам(и сильным хозяевам)",
            "url": "https://dogibogi.ru/shop/psumka-grafit"
        },
        {
            "photo": "https://optim.tildacdn.com/stor3163-3666-4466-b137-303762663533/-/format/webp/549546ea61e086ea0211550d32a4b3d8.jpg.webp",
            "caption": "Дрип-кофе с фото питомца. Если будете в Питере — приезжайте, фоткайтесь, получайте! Онлайн тоже можно, но от 50 штук",
            "url": "https://luco.site/drip/tproduct/974521021-262603882582-drip"
        }
    ], 
    "date": [
        {
            "photo": "https://tblr.blob.core.windows.net/images/74597472-5319-39d7-8d5c-62fec136ba95.jpg",
            "caption": "Aaark, м. Чистые Пруды/Китай-город. Подходит для рабочих встреч, первых свиданий и другого кэжуал-формата. Мой топ — сэндвич с мортаделлой и бриошь с яблоком. Вообще это одно из редких мест, где все hit, никогда не miss: меню, атмосфера, интерьер. Забронировать столик нельзя, по много выходным людей — учитывайте это.",
            "url": "https://aaark-cafe.clients.site/"
        },
        {
            "photo": "https://img.restoclub.ru/uploads/place/f/0/e/3/f0e389e376d090eff22c3208b6b8bd75_w1230_h820--no-cut.webp?v=3",
            "caption": "Dry&Wet, м. Маяковская. Бар без меню, вам делают коктейль по вашему запросу(можно даже выбрать запах из съедобных духов). В центре, но в тихой подворотне, с приятной камерной обстановкой, speak-easy.",
            "url": "https://yandex.ru/maps/org/dry_wet/59651958737/"
        }
    ], 
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
    user_id = message.from_user.id
    if not await is_user_subscribed(user_id):
        await message.answer(
            f"🔒 Подпишитесь на [@{CHANNEL_USERNAME}](https://t.me/{CHANNEL_USERNAME}), чтобы пользоваться ботом.",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        return

    await state.clear()
    log_to_sheet(user_id, "start")
    await message.answer(
        "Привет! Это бот Telegram-канала «Что тебе подарить?». "
        "Здесь есть добрые и нужные подарки на весь год 🪄\n\n"
        "Какой ищем подарок?",
        reply_markup=categories_kb()
    )
    await state.set_state(GiftState.choosing_category)

@router.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    if not await is_user_subscribed(callback.from_user.id):
        return
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
    if not await is_user_subscribed(callback.from_user.id):
        return
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
        log_to_sheet(callback.from_user.id, "view", category=cat, item_name=item["caption"])
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            await callback.answer()
        else:
            raise
    except Exception as e:
        print(f"Ошибка загрузки фото: {e}")
        await callback.answer("Не удалось загрузить подарок 😕", show_alert=True)

@router.callback_query(GiftState.showing_gifts, F.data.startswith("gift:"))
async def navigate_gifts(callback: CallbackQuery, state: FSMContext):
    if not await is_user_subscribed(callback.from_user.id):
        return
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
        log_to_sheet(callback.from_user.id, "view", category=cat, item_name=item["caption"])
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            await callback.answer()
        else:
            raise
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
