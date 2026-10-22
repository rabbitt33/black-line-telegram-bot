
import asyncio
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder



BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 870354242

DB_PATH = BASE_DIR / "black_line.db"
BANNER_PATH = BASE_DIR / "images" / "welcome_banner.png"

if not BOT_TOKEN:
    raise ValueError(
        "BOT_TOKEN не найден. Проверь файл .env рядом с main.py"
    )

SERVICES = {
    "haircut": {
        "name": "✂️ Мужская стрижка",
        "price": 20,
    },
    "beard": {
        "name": "🧔 Оформление бороды",
        "price": 20,
    },
    "combo": {
        "name": "🔥 Стрижка + борода",
        "price": 27,
    },
}

TIME_SLOTS = ["10:00", "12:00", "14:00", "16:00"]

BOOKING_DAYS = 7

dp = Dispatcher(storage=MemoryStorage())
bot = None



class BookingStates(StatesGroup):
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()
    entering_name = State()
    confirming = State()



def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                client_name TEXT NOT NULL,
                service TEXT NOT NULL,
                price INTEGER NOT NULL,
                booking_date TEXT NOT NULL,
                booking_time TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (booking_date, booking_time)
            )
            """
        )




def main_menu():
    builder = InlineKeyboardBuilder()

    builder.button(
        text="💈 Записаться",
        callback_data="new_booking",
    )
    builder.button(
        text="📋 Мои записи",
        callback_data="my_bookings",
    )
    builder.adjust(1)

    return builder.as_markup()


def services_menu():
    builder = InlineKeyboardBuilder()

    for service_id, service in SERVICES.items():
        builder.button(
            text=f"{service['name']} — {service['price']} €",
            callback_data=f"service:{service_id}",
        )

    builder.button(text="⬅️ В главное меню", callback_data="main_menu")
    builder.adjust(1)

    return builder.as_markup()


def dates_menu():
    builder = InlineKeyboardBuilder()
    today = date.today()

    for offset in range(BOOKING_DAYS):
        booking_date = today + timedelta(days=offset)

        if offset == 0:
            label = "Сегодня"
        elif offset == 1:
            label = "Завтра"
        elif offset == 2:
            label = "Послезавтра"
        else:
            label = booking_date.strftime("%d.%m.%Y")

        builder.button(
            text=label,
            callback_data=f"date:{booking_date.isoformat()}",
        )

    builder.button(text="⬅️ Назад", callback_data="back_to_services")
    builder.button(text="🏠 Главное меню", callback_data="main_menu")
    builder.adjust(2, 2, 2, 1, 1)

    return builder.as_markup()


def times_menu(booking_date):
    builder = InlineKeyboardBuilder()

    for time_slot in TIME_SLOTS:
        if is_slot_available(booking_date, time_slot):
            builder.button(
                text=f"🕒 {time_slot}",
                callback_data=f"time:{time_slot}",
            )

    builder.button(text="⬅️ Выбрать другую дату", callback_data="back_to_dates")
    builder.button(text="🏠 Главное меню", callback_data="main_menu")
    builder.adjust(2, 2, 1, 1)

    return builder.as_markup()


def confirmation_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить запись",
                    callback_data="confirm_booking",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить запись",
                    callback_data="cancel_booking_flow",
                )
            ],
        ]
    )


def cancel_booking_menu(booking_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отменить запись",
                    callback_data=f"cancel_id:{booking_id}",
                )
            ]
        ]
    )




def is_slot_available(booking_date, booking_time):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id FROM bookings
            WHERE booking_date = ? AND booking_time = ?
            """,
            (booking_date, booking_time),
        ).fetchone()

    return row is None


def create_booking(
    client_id,
    client_name,
    service_name,
    price,
    booking_date,
    booking_time,
):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO bookings (
                client_id,
                client_name,
                service,
                price,
                booking_date,
                booking_time
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                client_name,
                service_name,
                price,
                booking_date,
                booking_time,
            ),
        )

        return cursor.lastrowid


def get_user_bookings(client_id):
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT * FROM bookings
            WHERE client_id = ?
            ORDER BY booking_date, booking_time
            """,
            (client_id,),
        ).fetchall()


def get_all_bookings():
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT * FROM bookings
            ORDER BY booking_date, booking_time
            """
        ).fetchall()


def get_booking_by_id(booking_id):
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM bookings WHERE id = ?",
            (booking_id,),
        ).fetchone()


def delete_booking(booking_id, client_id=None):
    with get_connection() as connection:
        if client_id is None:
            cursor = connection.execute(
                "DELETE FROM bookings WHERE id = ?",
                (booking_id,),
            )
        else:
            cursor = connection.execute(
                """
                DELETE FROM bookings
                WHERE id = ? AND client_id = ?
                """,
                (booking_id, client_id),
            )

        return cursor.rowcount > 0




@dp.message(CommandStart())
async def start_command(message: Message, state: FSMContext):
    await state.clear()

    welcome_text = (
        "Привет! 💈 Добро пожаловать в <b>BLACK LINE</b>!\n\n"
        "Твой стиль начинается здесь.\n"
        "Выбери услугу и удобное время, чтобы записаться "
        "к нашему барберу."
    )

    if BANNER_PATH.is_file():
        try:
            from aiogram.types import FSInputFile

            await message.answer_photo(
                photo=FSInputFile(BANNER_PATH),
                caption=welcome_text,
                reply_markup=main_menu(),
            )
            return
        except Exception as error:
            print(f"Не удалось отправить баннер: {error}")

    await message.answer(
        welcome_text,
        reply_markup=main_menu(),
    )




@dp.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()

    await callback.message.answer(
        "💈 <b>BLACK LINE</b>\n\nЧто ты хочешь сделать?",
        reply_markup=main_menu(),
    )




@dp.callback_query(F.data == "new_booking")
async def start_booking(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(BookingStates.choosing_service)
    await callback.answer()

    await callback.message.answer(
        "💈 <b>Выбери услугу:</b>",
        reply_markup=services_menu(),
    )


@dp.callback_query(
    BookingStates.choosing_service,
    F.data.startswith("service:"),
)
async def choose_service(callback: CallbackQuery, state: FSMContext):
    service_id = callback.data.split(":", 1)[1]

    if service_id not in SERVICES:
        await callback.answer("Неизвестная услуга.", show_alert=True)
        return

    service = SERVICES[service_id]

    await state.update_data(
        service_id=service_id,
        service_name=service["name"],
        price=service["price"],
    )
    await state.set_state(BookingStates.choosing_date)
    await callback.answer()

    await callback.message.answer(
        f"Выбрано: <b>{service['name']}</b>\n"
        f"Стоимость: <b>{service['price']} €</b>\n\n"
        "📅 Теперь выбери дату:",
        reply_markup=dates_menu(),
    )




@dp.callback_query(
    BookingStates.choosing_date,
    F.data.startswith("date:"),
)
async def choose_date(callback: CallbackQuery, state: FSMContext):
    booking_date = callback.data.split(":", 1)[1]

    try:
        selected_date = date.fromisoformat(booking_date)
    except ValueError:
        await callback.answer("Некорректная дата.", show_alert=True)
        return

    today = date.today()

    if selected_date < today or selected_date > today + timedelta(
        days=BOOKING_DAYS - 1
    ):
        await callback.answer(
            "Эта дата больше недоступна.",
            show_alert=True,
        )
        return

    await state.update_data(booking_date=booking_date)
    await state.set_state(BookingStates.choosing_time)
    await callback.answer()

    await callback.message.answer(
        f"📅 Выбрана дата: <b>{selected_date.strftime('%d.%m.%Y')}</b>\n\n"
        "🕒 Выбери свободное время:",
        reply_markup=times_menu(booking_date),
    )




@dp.callback_query(
    BookingStates.choosing_time,
    F.data.startswith("time:"),
)
async def choose_time(callback: CallbackQuery, state: FSMContext):
    booking_time = callback.data.split(":", 1)[1]
    data = await state.get_data()
    booking_date = data.get("booking_date")

    if booking_time not in TIME_SLOTS or not booking_date:
        await callback.answer(
            "Не удалось выбрать время. Начни запись заново.",
            show_alert=True,
        )
        return

    if not is_slot_available(booking_date, booking_time):
        await callback.answer(
            "Это время уже занято. Выбери другое.",
            show_alert=True,
        )
        await callback.message.answer(
            "🕒 Выбери другое свободное время:",
            reply_markup=times_menu(booking_date),
        )
        return

    await state.update_data(booking_time=booking_time)
    await state.set_state(BookingStates.entering_name)
    await callback.answer()

    await callback.message.answer(
        "✍️ Напиши своё имя, которое мы укажем в записи."
    )




@dp.message(BookingStates.entering_name)
async def enter_name(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправь имя текстом.")
        return

    client_name = message.text.strip()

    if len(client_name) < 2 or len(client_name) > 60:
        await message.answer(
            "Имя должно содержать от 2 до 60 символов. Попробуй ещё раз."
        )
        return

    await state.update_data(client_name=client_name)
    await state.set_state(BookingStates.confirming)

    data = await state.get_data()
    selected_date = date.fromisoformat(data["booking_date"])

    confirmation_text = (
        "📋 <b>Проверь свою запись:</b>\n\n"
        f"👤 Имя: {data['client_name']}\n"
        f"✂️ Услуга: {data['service_name']}\n"
        f"💶 Стоимость: {data['price']} €\n"
        f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
        f"🕒 Время: {data['booking_time']}\n\n"
        "Всё правильно?"
    )

    await message.answer(
        confirmation_text,
        reply_markup=confirmation_menu(),
    )




@dp.callback_query(
    BookingStates.confirming,
    F.data == "confirm_booking",
)
async def confirm_booking(callback: CallbackQuery, state: FSMContext):
    global bot

    data = await state.get_data()

    required_fields = (
        "client_name",
        "service_name",
        "price",
        "booking_date",
        "booking_time",
    )

    if not all(field in data for field in required_fields):
        await state.clear()
        await callback.answer(
            "Данные записи потеряны. Начни заново.",
            show_alert=True,
        )
        return

    if not is_slot_available(data["booking_date"], data["booking_time"]):
        await callback.answer(
            "Это время уже заняли. Выбери другое.",
            show_alert=True,
        )
        await state.set_state(BookingStates.choosing_time)
        await callback.message.answer(
            "Пожалуйста, выбери другое время:",
            reply_markup=times_menu(data["booking_date"]),
        )
        return

    try:
        booking_id = create_booking(
            client_id=callback.from_user.id,
            client_name=data["client_name"],
            service_name=data["service_name"],
            price=data["price"],
            booking_date=data["booking_date"],
            booking_time=data["booking_time"],
        )
    except sqlite3.IntegrityError:
        await callback.answer(
            "Это время уже занято. Выбери другое.",
            show_alert=True,
        )
        await state.set_state(BookingStates.choosing_time)
        await callback.message.answer(
            "🕒 Выбери другое свободное время:",
            reply_markup=times_menu(data["booking_date"]),
        )
        return

    selected_date = date.fromisoformat(data["booking_date"])

    await state.clear()
    await callback.answer("Запись подтверждена!")

    await callback.message.answer(
        "✅ <b>Ты успешно записан в BLACK LINE!</b>\n\n"
        f"Номер записи: <b>#{booking_id}</b>\n"
        f"👤 Имя: {data['client_name']}\n"
        f"✂️ Услуга: {data['service_name']}\n"
        f"💶 Стоимость: {data['price']} €\n"
        f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
        f"🕒 Время: {data['booking_time']}\n\n"
        "Ждём тебя! 💈",
        reply_markup=main_menu(),
    )

    admin_text = (
        "🔔 <b>Новая запись BLACK LINE!</b>\n\n"
        f"Номер: #{booking_id}\n"
        f"👤 Клиент: {data['client_name']}\n"
        f"🆔 Telegram ID: {callback.from_user.id}\n"
        f"✂️ Услуга: {data['service_name']}\n"
        f"💶 Стоимость: {data['price']} €\n"
        f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
        f"🕒 Время: {data['booking_time']}"
    )

    try:
        await bot.send_message(ADMIN_ID, admin_text)
    except Exception as error:
        print(f"Не удалось уведомить администратора: {error}")




@dp.callback_query(F.data == "cancel_booking_flow")
async def cancel_booking_flow(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()
    await callback.answer()

    await callback.message.answer(
        "Запись не создана. Ты можешь начать заново.",
        reply_markup=main_menu(),
    )


@dp.callback_query(F.data == "back_to_services")
async def back_to_services(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BookingStates.choosing_service)
    await callback.answer()

    await callback.message.answer(
        "Выбери услугу:",
        reply_markup=services_menu(),
    )


@dp.callback_query(F.data == "back_to_dates")
async def back_to_dates(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BookingStates.choosing_date)
    await callback.answer()

    await callback.message.answer(
        "📅 Выбери дату:",
        reply_markup=dates_menu(),
    )




@dp.callback_query(F.data == "my_bookings")
async def my_bookings(callback: CallbackQuery):
    await callback.answer()

    bookings = get_user_bookings(callback.from_user.id)

    if not bookings:
        await callback.message.answer(
            "📋 У тебя пока нет записей.",
            reply_markup=main_menu(),
        )
        return

    await callback.message.answer("📋 <b>Твои записи:</b>")

    for booking in bookings:
        selected_date = date.fromisoformat(booking["booking_date"])

        text = (
            f"Запись <b>#{booking['id']}</b>\n"
            f"👤 Имя: {booking['client_name']}\n"
            f"✂️ Услуга: {booking['service']}\n"
            f"💶 Стоимость: {booking['price']} €\n"
            f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
            f"🕒 Время: {booking['booking_time']}"
        )

        await callback.message.answer(
            text,
            reply_markup=cancel_booking_menu(booking["id"]),
        )

    await callback.message.answer(
        "Чтобы вернуться в меню, нажми кнопку ниже.",
        reply_markup=main_menu(),
    )




@dp.callback_query(F.data.startswith("cancel_id:"))
async def cancel_existing_booking(callback: CallbackQuery):
    global bot

    try:
        booking_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Некорректный номер записи.", show_alert=True)
        return

    booking = get_booking_by_id(booking_id)

    if booking is None or booking["client_id"] != callback.from_user.id:
        await callback.answer(
            "Запись не найдена или недоступна.",
            show_alert=True,
        )
        return

    was_deleted = delete_booking(
        booking_id,
        client_id=callback.from_user.id,
    )

    if not was_deleted:
        await callback.answer(
            "Не удалось отменить запись.",
            show_alert=True,
        )
        return

    await callback.answer("Запись отменена.")

    await callback.message.answer(
        f"❌ Запись #{booking_id} отменена.",
        reply_markup=main_menu(),
    )

    try:
        await bot.send_message(
            ADMIN_ID,
            f"❌ Клиент отменил запись #{booking_id}.\n"
            f"Клиент: {booking['client_name']}\n"
            f"Дата: {booking['booking_date']}\n"
            f"Время: {booking['booking_time']}",
        )
    except Exception as error:
        print(f"Не удалось уведомить администратора: {error}")




@dp.message(Command("bookings"))
async def admin_bookings(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У тебя нет доступа к этой команде.")
        return

    bookings = get_all_bookings()

    if not bookings:
        await message.answer("📋 Записей пока нет.")
        return

    await message.answer(
        f"📋 <b>Все записи BLACK LINE</b>\n"
        f"Всего: {len(bookings)}"
    )

    for booking in bookings:
        selected_date = date.fromisoformat(booking["booking_date"])

        text = (
            f"Запись <b>#{booking['id']}</b>\n"
            f"👤 Клиент: {booking['client_name']}\n"
            f"🆔 Telegram ID: {booking['client_id']}\n"
            f"✂️ Услуга: {booking['service']}\n"
            f"💶 Стоимость: {booking['price']} €\n"
            f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
            f"🕒 Время: {booking['booking_time']}"
        )

        await message.answer(text)




@dp.message(Command("stats"))
async def admin_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У тебя нет доступа к этой команде.")
        return

    bookings = get_all_bookings()
    total_bookings = len(bookings)
    total_revenue = sum(booking["price"] for booking in bookings)

    today_string = date.today().isoformat()

    today_bookings = [
        booking
        for booking in bookings
        if booking["booking_date"] == today_string
    ]

    await message.answer(
        "📊 <b>Статистика BLACK LINE</b>\n\n"
        f"📋 Всего записей: {total_bookings}\n"
        f"📅 Записей на сегодня: {len(today_bookings)}\n"
        f"💶 Сумма стоимости всех записей: {total_revenue} €"
    )




@dp.message(Command("admin"))
async def admin_help(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У тебя нет доступа к этой команде.")
        return

    await message.answer(
        "🛠 <b>Команды администратора</b>\n\n"
        "/bookings — посмотреть все записи\n"
        "/stats — статистика записей\n"
        "/admin — список команд"
    )




async def main():
    global bot

    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    print("BLACK LINE запускается...")
    print(f"База данных: {DB_PATH}")
    print(f"Баннер найден: {BANNER_PATH.is_file()}")

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        print("Бот запущен. Ожидание сообщений...")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
