import asyncio
import os
import sqlite3
import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, \
    InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest, TelegramConflictError
import random

# === КОНФИГУРАЦИЯ ===
BOT_TOKEN = "8128428418:AAESrE-3V_6O-_cuMMbclzH4nkxhZz6TDgE"
ADMIN_ID = 911793106
SUPPORT_LINK = "https://t.me/your_support_link"  # Замените на вашу ссылку
REVIEWS_LINK = "https://t.me/your_reviews_link"  # Замените на вашу ссылку
DB_NAME = "generic_store.db"

# --- Инициализация ---
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=storage)
ADMINS = set()


# === СОСТОЯНИЯ ===
class AddProduct(StatesGroup):
    category = State()
    brand_choice = State()
    brand_new = State()
    name = State()
    description = State()
    price = State()
    stock = State()
    photo = State()


class EditProduct(StatesGroup):
    product_id = State()
    field = State()
    new_value = State()


class EditStock(StatesGroup):
    product_id = State()
    waiting_for_stock = State()


class AddToCart(StatesGroup):
    product_id = State()
    quantity = State()


class ReserveFromCard(StatesGroup):
    product_id = State()
    quantity = State()
    date = State()


class AddPromotion(StatesGroup):
    title = State()
    content = State()
    photo = State()


class AddFAQ(StatesGroup):
    question = State()
    answer = State()


class AdminManagement(StatesGroup):
    add_admin_id = State()


# === БАЗА ДАННЫХ ===
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('PRAGMA foreign_keys = ON;')
    cur.execute('''
                CREATE TABLE IF NOT EXISTS products
                (
                    id
                    INTEGER
                    PRIMARY
                    KEY
                    AUTOINCREMENT,
                    category
                    TEXT
                    NOT
                    NULL,
                    brand
                    TEXT
                    NOT
                    NULL,
                    name
                    TEXT
                    NOT
                    NULL,
                    description
                    TEXT,
                    price
                    REAL
                    NOT
                    NULL,
                    stock
                    INTEGER
                    DEFAULT
                    0,
                    status
                    TEXT
                    DEFAULT
                    'in_stock',
                    photo
                    TEXT
                )
                ''')
    cur.execute('''
                CREATE TABLE IF NOT EXISTS cart
                (
                    user_id
                    INTEGER,
                    product_id
                    INTEGER,
                    quantity
                    INTEGER
                    DEFAULT
                    1,
                    PRIMARY
                    KEY
                (
                    user_id,
                    product_id
                ),
                    FOREIGN KEY
                (
                    product_id
                ) REFERENCES products
                (
                    id
                ) ON DELETE CASCADE
                    )
                ''')
    cur.execute('''
                CREATE TABLE IF NOT EXISTS users
                (
                    user_id
                    INTEGER
                    PRIMARY
                    KEY,
                    username
                    TEXT,
                    first_seen
                    DATETIME
                    DEFAULT
                    CURRENT_TIMESTAMP
                )
                ''')
    cur.execute('''
                CREATE TABLE IF NOT EXISTS reservations
                (
                    id
                    INTEGER
                    PRIMARY
                    KEY
                    AUTOINCREMENT,
                    user_id
                    INTEGER
                    NOT
                    NULL,
                    username
                    TEXT,
                    product_id
                    INTEGER
                    NOT
                    NULL,
                    product_name
                    TEXT
                    NOT
                    NULL,
                    quantity
                    INTEGER
                    NOT
                    NULL,
                    price
                    REAL
                    NOT
                    NULL,
                    reservation_code
                    INTEGER
                    NOT
                    NULL,
                    reservation_date
                    TEXT
                    NOT
                    NULL,
                    status
                    TEXT
                    DEFAULT
                    'active', -- active, completed, expired
                    completion_date
                    DATETIME
                )
                ''')
    cur.execute('''
                CREATE TABLE IF NOT EXISTS admins
                (
                    user_id
                    INTEGER
                    PRIMARY
                    KEY
                )
                ''')
    cur.execute('''
                CREATE TABLE IF NOT EXISTS promotions
                (
                    id
                    INTEGER
                    PRIMARY
                    KEY
                    AUTOINCREMENT,
                    title
                    TEXT
                    NOT
                    NULL,
                    content
                    TEXT,
                    photo
                    TEXT
                )
                ''')
    cur.execute('''
                CREATE TABLE IF NOT EXISTS faq
                (
                    id
                    INTEGER
                    PRIMARY
                    KEY
                    AUTOINCREMENT,
                    question
                    TEXT
                    NOT
                    NULL,
                    answer
                    TEXT
                    NOT
                    NULL
                )
                ''')
    cur.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (ADMIN_ID,))
    conn.commit()
    conn.close()


def get_db_connection():
    return sqlite3.connect(DB_NAME)


# --- Функции для админов ---
def load_admins():
    global ADMINS
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM admins")
        ADMINS = {row[0] for row in cur.fetchall()}


def add_admin_to_db(user_id):
    with get_db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    load_admins()


def remove_admin_from_db(user_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    load_admins()


# --- Функции для товаров ---
def get_products_by_category(category):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT brand FROM products WHERE category=? ORDER BY brand", (category,))
        return [b[0] for b in cur.fetchall()]


def get_products_by_brand(category, brand):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, price, stock, status, photo, description FROM products WHERE category=? AND brand=?",
            (category, brand))
        return cur.fetchall()


def get_product_by_id(product_id):
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM products WHERE id=?", (product_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def add_product(category, brand, name, description, price, stock, photo):
    with get_db_connection() as conn:
        status = 'in_stock' if stock > 0 else 'out_of_stock'
        conn.execute(
            "INSERT INTO products (category, brand, name, description, price, stock, status, photo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (category, brand, name, description, price, stock, status, photo))


def update_product(product_id, **kwargs):
    with get_db_connection() as conn:
        fields = ', '.join([f"{k}=?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [product_id]
        conn.execute(f"UPDATE products SET {fields} WHERE id=?", values)


def delete_product(product_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM products WHERE id=?", (product_id,))


# --- Функции для корзины ---
def add_to_cart(user_id, product_id, quantity):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT quantity FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id))
        result = cur.fetchone()
        if result:
            new_quantity = result[0] + quantity
            cur.execute("UPDATE cart SET quantity = ? WHERE user_id = ? AND product_id = ?",
                        (new_quantity, user_id, product_id))
        else:
            cur.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, ?)",
                        (user_id, product_id, quantity))


def get_cart(user_id):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('''SELECT p.id, p.name, p.price, c.quantity
                       FROM cart c
                                JOIN products p ON c.product_id = p.id
                       WHERE c.user_id = ?''', (user_id,))
        return cur.fetchall()


def remove_from_cart(user_id, product_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id))


def get_all_carts():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT u.user_id, u.username FROM cart c JOIN users u ON c.user_id = u.user_id")
        return cur.fetchall()


def clear_cart(user_id: int):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))


# --- Функции для бронирования ---
def add_reservation(user_id, username, code, date, item):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO reservations (user_id, username, reservation_code, reservation_date, product_id, product_name, quantity, price) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, username, code, date, item['pid'], item['name'], item['quantity'], item['price'])
        )


def get_user_reservation_dates(user_id):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT reservation_date FROM reservations WHERE user_id=? AND status='active' ORDER BY reservation_date DESC",
            (user_id,))
        return [row[0] for row in cur.fetchall()]


def get_user_reservations_by_date(user_id, date):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT reservation_code, product_name, quantity, price FROM reservations WHERE user_id=? AND reservation_date=? AND status='active'",
            (user_id, date))
        return cur.fetchall()


def get_all_reservations():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, reservation_code FROM reservations WHERE status = 'active' GROUP BY reservation_code ORDER BY id ASC")
        return cur.fetchall()


def get_reservation_details(res_id):
    with get_db_connection() as conn:
        cur = conn.cursor()
        # Ensure we get details for all items with the same reservation_code
        cur.execute("SELECT reservation_code FROM reservations WHERE id=?", (res_id,))
        res_code_row = cur.fetchone()
        if not res_code_row:
            return None, None
        res_code = res_code_row[0]

        cur.execute(
            "SELECT user_id, username, reservation_code, reservation_date FROM reservations WHERE reservation_code=? LIMIT 1",
            (res_code,))
        res_info = cur.fetchone()

        cur.execute("SELECT id, product_name, quantity, price FROM reservations WHERE reservation_code=?", (res_code,))
        items = cur.fetchall()

        return res_info, items


def complete_reservation(res_code):
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE reservations SET status='completed', completion_date=CURRENT_TIMESTAMP WHERE reservation_code=?",
            (res_code,))


# --- Функции для акций ---
def get_all_promotions():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, title FROM promotions")
        return cur.fetchall()


def get_promotion_by_id(promo_id):
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM promotions WHERE id=?", (promo_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def add_promotion(title, content, photo):
    with get_db_connection() as conn:
        conn.execute("INSERT INTO promotions (title, content, photo) VALUES (?, ?, ?)", (title, content, photo))


def delete_promotion(promo_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM promotions WHERE id=?", (promo_id,))


# --- Функции для FAQ ---
def get_all_faq():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, question FROM faq")
        return cur.fetchall()


def get_faq_by_id(faq_id):
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM faq WHERE id=?", (faq_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def add_faq(question, answer):
    with get_db_connection() as conn:
        conn.execute("INSERT INTO faq (question, answer) VALUES (?, ?)", (question, answer))


def delete_faq(faq_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM faq WHERE id=?", (faq_id,))


# --- Функции для статистики ---
def get_stats():
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Total users
        cur.execute("SELECT COUNT(user_id) FROM users")
        total_users = cur.fetchone()[0]

        # Revenue
        cur.execute("SELECT SUM(price * quantity) FROM reservations WHERE status='completed'")
        total_revenue = cur.fetchone()[0] or 0

        cur.execute(
            "SELECT SUM(price * quantity) FROM reservations WHERE status='completed' AND completion_date >= date('now', '-7 days')")
        revenue_7_days = cur.fetchone()[0] or 0

        cur.execute(
            "SELECT SUM(price * quantity) FROM reservations WHERE status='completed' AND completion_date >= date('now', '-30 days')")
        revenue_30_days = cur.fetchone()[0] or 0

        # Sales (completed reservations)
        cur.execute(
            "SELECT COUNT(DISTINCT reservation_code) FROM reservations WHERE status='completed' AND date(completion_date) = date('now')")
        sales_today = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT reservation_code) FROM reservations WHERE status='completed'")
        sales_total = cur.fetchone()[0]

        return {
            "total_users": total_users,
            "total_revenue": f"{total_revenue:.2f}",
            "revenue_7_days": f"{revenue_7_days:.2f}",
            "revenue_30_days": f"{revenue_30_days:.2f}",
            "sales_today": sales_today,
            "sales_total": sales_total,
        }


# === КЛАВИАТУРЫ ===
def main_menu(user_id):
    kb = [
        [InlineKeyboardButton(text="🛒 Ассортимент", callback_data="start_assort"),
         InlineKeyboardButton(text="📦 Корзина", callback_data="show_cart")],
        [InlineKeyboardButton(text="🔐 Мои брони", callback_data="user_reservations"),
         InlineKeyboardButton(text="🎁 Акции", callback_data="show_promos")],
        [InlineKeyboardButton(text="📝 Отзывы", url=REVIEWS_LINK),
         InlineKeyboardButton(text="📞 Поддержка", url=SUPPORT_LINK)],
        [InlineKeyboardButton(text="❓ Вопросы", callback_data="show_faq")],
    ]
    if user_id in ADMINS:
        kb.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔧 Управление ассортиментом", callback_data="admin_assort")],
        [InlineKeyboardButton(text="🎨 Управление акциями", callback_data="admin_promo")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👀 Посмотреть корзины", callback_data="admin_carts")],
        [InlineKeyboardButton(text="💬 Управление вопросами", callback_data="admin_faq")],
        [InlineKeyboardButton(text="👥 Управление администрацией", callback_data="admin_manage_admins")],
        [InlineKeyboardButton(text="🔐 Активные брони", callback_data="admin_reservations")],
        [InlineKeyboardButton(text="⬅️ Выйти", callback_data="main_menu")]
    ])


def admin_management_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить администратора", callback_data="admin_add_admin")],
        [InlineKeyboardButton(text="➖ Удалить администратора", callback_data="admin_remove_admin")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
    ])


def admin_assort_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin_add")],
        [InlineKeyboardButton(text="✏️ Изменить товар", callback_data="admin_edit")],
        [InlineKeyboardButton(text="🗑 Удалить товар", callback_data="admin_delete")],
        [InlineKeyboardButton(text="🔄 Изменить кол-во", callback_data="admin_status")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
    ])


def user_categories_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Категория 1", callback_data="user_cat_category1")],
        [InlineKeyboardButton(text="Категория 2", callback_data="user_cat_category2")],
        [InlineKeyboardButton(text="Категория 3", callback_data="user_cat_category3")],
        [InlineKeyboardButton(text="Категория 4 (с подкатегориями)", callback_data="user_cat_other")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]
    ])


def subcategories_kb(prefix, back_target):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подкатегория 1", callback_data=f"{prefix}_subcat_subcategory1")],
        [InlineKeyboardButton(text="Подкатегория 2", callback_data=f"{prefix}_subcat_subcategory2")],
        [InlineKeyboardButton(text="Подкатегория 3", callback_data=f"{prefix}_subcat_subcategory3")],
        [InlineKeyboardButton(text="Подкатегория 4", callback_data=f"{prefix}_subcat_subcategory4")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_target)]
    ])


def brands_kb(category, prefix, back_target):
    brands_list = get_products_by_category(category)
    if not brands_list:
        return None
    buttons = [[InlineKeyboardButton(text=brand, callback_data=f"{prefix}_brand_{category}_{brand}")] for brand in
               brands_list]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_target)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def product_list_kb(products, prefix, back_target):
    buttons = []
    for row in products:
        pid, name, price, stock, status, _, _ = row
        icon = "✅" if status == 'in_stock' and stock > 0 else "❌"
        text = f"{icon} {name} — {price}₽"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"{prefix}_prod_{pid}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_target)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cart_actions_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Забронировать всё", callback_data="reserve_all")],
        [InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu")]
    ])


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
async def safe_delete_message(message: types.Message):
    try:
        await message.delete()
    except (TelegramBadRequest, AttributeError):
        pass


async def send_or_edit(call: CallbackQuery, text: str, kb: InlineKeyboardMarkup, photo: str = None):
    try:
        if photo and os.path.exists(photo):
            media = InputMediaPhoto(media=FSInputFile(photo), caption=text)
            if call.message.photo:
                await call.message.edit_media(media=media, reply_markup=kb)
            else:
                await safe_delete_message(call.message)
                await call.message.answer_photo(photo=FSInputFile(photo), caption=text, reply_markup=kb)
        else:
            if call.message.photo:
                await safe_delete_message(call.message)
                await call.message.answer(text, reply_markup=kb)
            else:
                await call.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            await safe_delete_message(call.message)
            if photo and os.path.exists(photo):
                await call.message.answer_photo(photo=FSInputFile(photo), caption=text, reply_markup=kb)
            else:
                await call.message.answer(text, reply_markup=kb)
    except Exception:
        await safe_delete_message(call.message)
        if photo and os.path.exists(photo):
            await call.message.answer_photo(photo=FSInputFile(photo), caption=text, reply_markup=kb)
        else:
            await call.message.answer(text, reply_markup=kb)


# === ФОНОВЫЕ ЗАДАЧИ ===
async def cleanup_expired_reservations():
    while True:
        await asyncio.sleep(86400)  # Пауза на 24 часа

        today_iso = datetime.date.today().isoformat()

        with get_db_connection() as conn:
            cur = conn.cursor()
            # Находим просроченные брони
            cur.execute(
                "SELECT id, product_id, quantity FROM reservations WHERE status='active' AND reservation_date < ?",
                (today_iso,))
            expired_reservations = cur.fetchall()

            if not expired_reservations:
                continue

            for res_id, prod_id, qty in expired_reservations:
                # Возвращаем товар на склад
                prod = get_product_by_id(prod_id)
                if prod:
                    new_stock = prod['stock'] + qty
                    update_product(prod_id, stock=new_stock, status='in_stock')

            # Удаляем просроченные брони
            cur.execute("DELETE FROM reservations WHERE status='active' AND reservation_date < ?", (today_iso,))
            conn.commit()
            print(f"[{datetime.datetime.now()}] Cleaned up {len(expired_reservations)} expired reservations.")


# === ГЛАВНЫЕ ОБРАБОТЧИКИ ===
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    with get_db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
                     (message.from_user.id, message.from_user.username))
    await message.answer("Добро пожаловать в наш магазин!", reply_markup=main_menu(message.from_user.id))


@dp.message(Command("cancel"), StateFilter("*"))
async def cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=main_menu(message.from_user.id))


@dp.callback_query(F.data == "main_menu")
async def back_to_main_menu(call: CallbackQuery):
    await safe_delete_message(call.message)
    await call.message.answer("Главное меню:", reply_markup=main_menu(call.from_user.id))
    await call.answer()


# === ПОЛЬЗОВАТЕЛЬСКИЙ РАЗДЕЛ: АССОРТИМЕНТ ===
@dp.callback_query(F.data == "start_assort")
async def user_show_categories(call: CallbackQuery):
    await send_or_edit(call, "Выберите категорию:", user_categories_kb())
    await call.answer()


@dp.callback_query(F.data == "user_cat_other")
async def user_show_subcategories(call: CallbackQuery):
    await send_or_edit(call, "📦 Другие товары:", subcategories_kb("user", "start_assort"))
    await call.answer()


@dp.callback_query(F.data.startswith("user_cat_") | F.data.startswith("user_subcat_"))
async def user_select_brand(call: CallbackQuery):
    if call.data.startswith("user_cat_"):
        category = call.data.split("_")[2]
        back_target = "start_assort"
    else:  # user_subcat_
        category = call.data.split("_")[2]
        back_target = "user_cat_other"

    kb = brands_kb(category, "user", back_target)
    if not kb:
        await call.answer("В этой категории пока нет товаров.", show_alert=True)
        return
    await send_or_edit(call, "Выберите бренд:", kb)
    await call.answer()


@dp.callback_query(F.data.startswith("user_brand_"))
async def user_select_product(call: CallbackQuery):
    _, _, category, brand = call.data.split("_", 3)
    products = get_products_by_brand(category, brand)
    if not products:
        await call.answer("Товаров этого бренда нет.", show_alert=True)
        return

    back_target = f"user_cat_{category}"
    if category in ["subcategory1", "subcategory2", "subcategory3", "subcategory4"]:
        back_target = "user_cat_other"

    await send_or_edit(call, f"Товары бренда <b>{brand}</b>:", product_list_kb(products, "user", back_target))
    await call.answer()


@dp.callback_query(F.data.startswith("user_prod_"))
async def user_show_product_card(call: CallbackQuery):
    pid = int(call.data.split("_")[2])
    prod = get_product_by_id(pid)
    if not prod: return await call.answer("Товар не найден", show_alert=True)

    availability = f"🟢 В наличии: {prod['stock']} шт." if prod['status'] == 'in_stock' and prod[
        'stock'] > 0 else "🔴 Нет в наличии"
    text = (f"📦 <b>{prod['name']}</b>\n\n"
            f"{prod['description']}\n\n"
            f"💰 <b>Цена:</b> {prod['price']}₽\n"
            f"📊 <b>Наличие:</b> {availability}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Добавить в корзину", callback_data=f"addtocart_{pid}")],
        [InlineKeyboardButton(text="🔐 Забронировать", callback_data=f"reserve_card_{pid}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"user_brand_{prod['category']}_{prod['brand']}")]
    ])
    await send_or_edit(call, text, kb, prod.get('photo'))
    await call.answer()


# === ПОЛЬЗОВАТЕЛЬСКИЙ РАЗДЕЛ: КОРЗИНА ===
@dp.callback_query(F.data.startswith("addtocart_"))
async def add_to_cart_start(call: CallbackQuery, state: FSMContext):
    pid = int(call.data.split("_")[1])
    prod = get_product_by_id(pid)
    if not prod or prod['stock'] <= 0:
        await call.answer("Товара нет в наличии!", show_alert=True)
        return

    await state.set_state(AddToCart.quantity)
    await state.update_data(product_id=pid, stock=prod['stock'], name=prod['name'])

    text_to_send = f"Введите количество товара «{prod['name']}» для добавления в корзину (в наличии {prod['stock']} шт.)."
    if call.message.photo:
        await safe_delete_message(call.message)
        await call.message.answer(text_to_send)
    else:
        await call.message.edit_text(text_to_send)
    await call.answer()


@dp.message(AddToCart.quantity)
async def add_to_cart_finish(message: Message, state: FSMContext):
    try:
        quantity = int(message.text) if message.text and message.text.isdigit() else 1
        data = await state.get_data()
        if not (0 < quantity <= data['stock']):
            await message.answer(f"Некорректное количество. Введите число от 1 до {data['stock']}.")
            return
    except (ValueError, TypeError):
        await message.answer("Пожалуйста, введите число.")
        return

    pid = data['product_id']
    add_to_cart(message.from_user.id, pid, quantity)

    current_stock = data['stock']
    new_stock = current_stock - quantity
    new_status = 'in_stock' if new_stock > 0 else 'out_of_stock'
    update_product(pid, stock=new_stock, status=new_status)

    await state.clear()
    await message.answer(f"✅ Добавлено в корзину: {data['name']} ({quantity} шт.)")
    await message.answer("Главное меню:", reply_markup=main_menu(message.from_user.id))


@dp.callback_query(F.data == "show_cart")
async def show_cart(call: CallbackQuery):
    cart_items = get_cart(call.from_user.id)
    if not cart_items:
        return await send_or_edit(call, "🛒 Ваша корзина пуста.", InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]]))

    kb_buttons = []
    total_price = 0
    text = "🛒 <b>Ваша корзина:</b>\n\n"

    for pid, name, price, quantity in cart_items:
        item_total = price * quantity
        total_price += item_total
        text += f"• {name} ({quantity} шт.) - {price}₽/шт.\n"
        kb_buttons.append(
            [InlineKeyboardButton(text=f"👁️ {name}", callback_data=f"cart_prod_{pid}")])

    text += f"\n<b>Итого: {total_price}₽</b>"

    action_buttons = cart_actions_kb().inline_keyboard
    full_kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons + action_buttons)

    await send_or_edit(call, text, full_kb)
    await call.answer()


@dp.callback_query(F.data.startswith("cart_prod_"))
async def show_cart_product(call: CallbackQuery):
    pid = int(call.data.split("_")[2])
    prod = get_product_by_id(pid)
    if not prod: return await call.answer("Товар не найден", show_alert=True)

    availability = f"🟢 В наличии: {prod['stock']} шт." if prod['status'] == 'in_stock' and prod[
        'stock'] > 0 else "🔴 Нет в наличии"
    text = (f"📦 <b>{prod['name']}</b> (из корзины)\n\n"
            f"{prod['description']}\n\n"
            f"💰 <b>Цена:</b> {prod['price']}₽\n"
            f"📊 <b>Наличие:</b> {availability}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 Забронировать этот товар", callback_data=f"reserve_card_{pid}")],
        [InlineKeyboardButton(text="🗑 Удалить из корзины", callback_data=f"del_from_cart_{pid}")],
        [InlineKeyboardButton(text="⬅️ Назад в корзину", callback_data="show_cart")]
    ])
    await send_or_edit(call, text, kb, prod.get('photo'))
    await call.answer()


@dp.callback_query(F.data.startswith("del_from_cart_"))
async def remove_from_cart_handler(call: CallbackQuery):
    pid = int(call.data.split("_")[3])
    cart_items = get_cart(call.from_user.id)
    quantity_to_return = 0
    for item_pid, _, _, qty in cart_items:
        if item_pid == pid:
            quantity_to_return = qty
            break

    if quantity_to_return > 0:
        prod = get_product_by_id(pid)
        if prod:
            new_stock = prod['stock'] + quantity_to_return
            update_product(pid, stock=new_stock, status='in_stock')

    remove_from_cart(call.from_user.id, pid)
    await call.answer("Товар удален из корзины", show_alert=True)
    await show_cart(call)


@dp.callback_query(F.data == "clear_cart")
async def clear_cart_handler(call: CallbackQuery):
    cart_items = get_cart(call.from_user.id)
    for pid, _, _, qty in cart_items:
        prod = get_product_by_id(pid)
        if prod:
            new_stock = prod['stock'] + qty
            update_product(pid, stock=new_stock, status='in_stock')

    clear_cart(call.from_user.id)
    await call.answer("Корзина очищена!", show_alert=True)
    await show_cart(call)


@dp.callback_query(F.data == "reserve_all")
async def reserve_all_handler(call: CallbackQuery, state: FSMContext):
    cart_items = get_cart(call.from_user.id)
    if not cart_items:
        return await call.answer("Корзина пуста!", show_alert=True)

    # Проверка наличия всех товаров перед бронированием
    for pid, name, price, quantity in cart_items:
        prod = get_product_by_id(pid)
        if not prod or prod['stock'] < quantity:
            await call.answer(f"Недостаточно товара «{name}». В наличии: {prod.get('stock', 0)} шт.", show_alert=True)
            # Не очищаем корзину, даем пользователю исправить
            return

    await state.set_state(ReserveFromCard.date)
    await state.update_data(items_to_reserve=cart_items)

    today = datetime.date.today()
    date_buttons = []
    for i in range(7):
        date = today + datetime.timedelta(days=i)
        date_buttons.append(
            [InlineKeyboardButton(text=date.strftime("%d.%m.%Y"), callback_data=f"reserve_date_{date.isoformat()}")]
        )
    await send_or_edit(call, "Выберите дату получения для всех товаров в корзине:",
                       InlineKeyboardMarkup(inline_keyboard=date_buttons))


# === ПОЛЬЗОВАТЕЛЬСКИЙ РАЗДЕЛ: БРОНИРОВАНИЕ ===
@dp.callback_query(F.data.startswith("reserve_card_"))
async def reserve_from_card_start(call: CallbackQuery, state: FSMContext):
    pid = int(call.data.split("_")[2])
    prod = get_product_by_id(pid)
    if not prod or prod['stock'] <= 0:
        return await call.answer("Товара нет в наличии!", show_alert=True)

    await state.set_state(ReserveFromCard.quantity)
    await state.update_data(product_id=pid, stock=prod['stock'], name=prod['name'], price=prod['price'])

    text_to_send = f"<b>Бронирование: {prod['name']}</b>\n\nВведите желаемое количество (в наличии {prod['stock']} шт.)."
    if call.message.photo:
        await safe_delete_message(call.message)
        await call.message.answer(text_to_send)
    else:
        await call.message.edit_text(text_to_send)
    await call.answer()


@dp.message(ReserveFromCard.quantity)
async def reserve_from_card_quantity(message: Message, state: FSMContext):
    try:
        quantity = int(message.text) if message.text and message.text.isdigit() else 1
        data = await state.get_data()
        if not (0 < quantity <= data['stock']):
            await message.answer(f"Некорректное количество. Введите число от 1 до {data['stock']}.")
            return
    except (ValueError, TypeError):
        await message.answer("Пожалуйста, введите число.")
        return

    # Создаем список из одного товара для унификации
    item = get_product_by_id(data['product_id'])
    items_to_reserve = [(item['id'], item['name'], item['price'], quantity)]

    await state.update_data(items_to_reserve=items_to_reserve)
    await state.set_state(ReserveFromCard.date)

    today = datetime.date.today()
    date_buttons = []
    for i in range(7):
        date = today + datetime.timedelta(days=i)
        date_buttons.append(
            [InlineKeyboardButton(text=date.strftime("%d.%m.%Y"), callback_data=f"reserve_date_{date.isoformat()}")]
        )
    await message.answer("Выберите дату получения:", reply_markup=InlineKeyboardMarkup(inline_keyboard=date_buttons))


@dp.callback_query(F.data.startswith("reserve_date_"), ReserveFromCard.date)
async def reserve_from_card_date(call: CallbackQuery, state: FSMContext):
    date_str = call.data.split("_")[2]
    data = await state.get_data()
    items_to_reserve = data.get('items_to_reserve')

    if not items_to_reserve:
        await call.answer("Ошибка: не найдены товары для бронирования.", show_alert=True)
        await state.clear()
        return

    code = random.randint(10000, 99999)

    for pid, name, price, quantity in items_to_reserve:
        prod_data = get_product_by_id(pid)

        # Финальная проверка на случай, если кто-то купил товар пока пользователь выбирал дату
        if not prod_data or prod_data['stock'] < quantity:
            await call.message.edit_text(f"Упс! Пока вы выбирали, товар «{name}» закончился. Попробуйте снова.")
            await state.clear()
            return

        item_details = {'pid': pid, 'name': name, 'quantity': quantity, 'price': price}
        add_reservation(call.from_user.id, call.from_user.username, code, date_str, item_details)

        # Уменьшаем сток только после успешного добавления брони
        new_stock = prod_data['stock'] - quantity
        update_product(pid, stock=new_stock, status='in_stock' if new_stock > 0 else 'out_of_stock')

    # Очищаем корзину, если бронировали из нее
    if len(items_to_reserve) > 1 or call.message.text and "корзине" in call.message.text:
        clear_cart(call.from_user.id)

    await state.clear()

    sent_message = await call.message.edit_text(
        f"✅ Ваше бронирование принято.\nКод: <b>{code}</b>\n\n<i>Это сообщение удалится через 30 секунд.</i>")
    await call.message.answer("Посмотреть свои брони можно в разделе '🔐 Мои брони' в главном меню.",
                              reply_markup=main_menu(call.from_user.id))

    await asyncio.sleep(30)
    await safe_delete_message(sent_message)


@dp.callback_query(F.data == "user_reservations")
async def user_reservations_dates(call: CallbackQuery):
    dates = get_user_reservation_dates(call.from_user.id)
    if not dates:
        return await send_or_edit(call, "У вас нет активных бронирований.", InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]]))

    kb = [[InlineKeyboardButton(text=date, callback_data=f"show_res_date_{date}")] for date in dates]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")])
    await send_or_edit(call, "Выберите дату, чтобы посмотреть бронирования:", InlineKeyboardMarkup(inline_keyboard=kb))


@dp.callback_query(F.data.startswith("show_res_date_"))
async def user_show_reservation_by_date(call: CallbackQuery):
    date = call.data.split("_")[3]
    reservations = get_user_reservations_by_date(call.from_user.id, date)

    text = f"<b>Бронирования на {date}:</b>\n\n"

    grouped_res = {}
    for code, name, qty, price in reservations:
        if code not in grouped_res:
            grouped_res[code] = []
        grouped_res[code].append({'name': name, 'qty': qty, 'price': price})

    for code, items in grouped_res.items():
        text += f"--- Код брони: <code>{code}</code> ---\n"
        total_price = 0
        for item in items:
            item_total = item['price'] * item['qty']
            total_price += item_total
            text += f"• {item['name']} ({item['qty']} шт.) - {item['price']}₽/шт.\n"
        text += f"<i>Итого по брони: {total_price}₽</i>\n\n"

    await send_or_edit(call, text, InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад к датам", callback_data="user_reservations")]]))


# === ПОЛЬЗОВАТЕЛЬСКИЙ РАЗДЕЛ: АКЦИИ И FAQ ===
@dp.callback_query(F.data == "show_promos")
async def show_promos(call: CallbackQuery):
    promos = get_all_promotions()
    if not promos:
        return await call.answer("Актуальных акций нет.", show_alert=True)

    kb = [[InlineKeyboardButton(text=title, callback_data=f"promo_{pid}")] for pid, title in promos]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")])
    await send_or_edit(call, "🎁 Наши акции:", InlineKeyboardMarkup(inline_keyboard=kb))


@dp.callback_query(F.data.startswith("promo_"))
async def show_promo_detail(call: CallbackQuery):
    promo_id = int(call.data.split("_")[1])
    promo = get_promotion_by_id(promo_id)
    if not promo: return await call.answer("Акция не найдена.", show_alert=True)

    text = f"<b>{promo['title']}</b>\n\n{promo['content']}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ К акциям", callback_data="show_promos")]])
    await send_or_edit(call, text, kb, promo.get('photo'))


@dp.callback_query(F.data == "show_faq")
async def show_faq(call: CallbackQuery):
    faqs = get_all_faq()
    if not faqs:
        return await call.answer("Раздел вопросов и ответов пока пуст.", show_alert=True)

    kb = [[InlineKeyboardButton(text=q, callback_data=f"faq_{fid}")] for fid, q in faqs]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")])
    await send_or_edit(call, "❓ Часто задаваемые вопросы:", InlineKeyboardMarkup(inline_keyboard=kb))


@dp.callback_query(F.data.startswith("faq_"))
async def show_faq_answer(call: CallbackQuery):
    faq_id = int(call.data.split("_")[1])
    faq = get_faq_by_id(faq_id)
    if not faq: return await call.answer("Вопрос не найден.", show_alert=True)

    text = f"<b>❓ Вопрос:</b>\n<i>{faq['question']}</i>\n\n<b>💬 Ответ:</b>\n{faq['answer']}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ К вопросам", callback_data="show_faq")]])
    await send_or_edit(call, text, kb)


# === АДМИН-ПАНЕЛЬ ===
@dp.callback_query(F.data == "admin_panel")
async def admin_panel_cmd(call: CallbackQuery):
    if call.from_user.id not in ADMINS: return
    await send_or_edit(call, "👑 Админ-панель", admin_panel_kb())
    await call.answer()


@dp.callback_query(F.data == "admin_assort")
async def admin_assort_menu(call: CallbackQuery):
    if call.from_user.id not in ADMINS: return
    await send_or_edit(call, "🔧 Управление ассортиментом:", admin_assort_menu_kb())
    await call.answer()


# --- Админка: Добавление товара ---
@dp.callback_query(F.data == "admin_add")
async def admin_add_start(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = categories_kb("add", "admin_assort")
    await send_or_edit(call, "Выберите категорию для нового товара:", kb)
    await call.answer()


def categories_kb(prefix, back_target):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Категория 1", callback_data=f"{prefix}_cat_category1")],
        [InlineKeyboardButton(text="Категория 2", callback_data=f"{prefix}_cat_category2")],
        [InlineKeyboardButton(text="Категория 3", callback_data=f"{prefix}_cat_category3")],
        [InlineKeyboardButton(text="Категория 4 (с подкатегориями)", callback_data=f"{prefix}_cat_other")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_target)]
    ])


@dp.callback_query(F.data == "add_cat_other")
async def admin_add_select_subcategory(call: CallbackQuery):
    await send_or_edit(call, "Выберите подкатегорию:", subcategories_kb("add", "admin_add"))
    await call.answer()


@dp.callback_query(F.data.startswith("add_cat_") | F.data.startswith("add_subcat_"))
async def admin_add_set_category(call: CallbackQuery, state: FSMContext):
    if call.data == "add_cat_other": return

    if call.data.startswith("add_cat_"):
        category = call.data.split("_")[2]
        back_target = "admin_add"
    else:  # add_subcat_
        category = call.data.split("_")[2]
        back_target = "add_cat_other"

    await state.update_data(category=category)
    kb = brands_kb(category, "add", back_target)
    brand_buttons = []
    if kb:
        brand_buttons.extend(kb.inline_keyboard[:-1])
    brand_buttons.append([InlineKeyboardButton(text="🆕 Новый бренд", callback_data="add_brand_new")])
    brand_buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_target)])
    await send_or_edit(call, "Выберите бренд или добавьте новый:", InlineKeyboardMarkup(inline_keyboard=brand_buttons))
    await call.answer()


@dp.callback_query(F.data == "add_brand_new")
async def admin_add_new_brand_prompt(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddProduct.brand_new)
    await call.message.edit_text("Введите название нового бренда:")
    await call.answer()


@dp.callback_query(F.data.startswith("add_brand_"))
async def admin_add_existing_brand_selected(call: CallbackQuery, state: FSMContext):
    brand = call.data.split("_", 3)[3]
    await state.update_data(brand=brand)
    await state.set_state(AddProduct.name)
    await call.message.edit_text(f"Бренд: {brand}. Введите название товара:")
    await call.answer()


@dp.message(AddProduct.brand_new)
async def admin_add_new_brand_name(message: Message, state: FSMContext):
    await state.update_data(brand=message.text)
    await state.set_state(AddProduct.name)
    await message.answer("Введите название товара:")


@dp.message(AddProduct.name)
async def process_product_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddProduct.description)
    await message.answer("Введите описание товара:")


@dp.message(AddProduct.description)
async def process_product_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(AddProduct.price)
    await message.answer("Введите цену (число):")


@dp.message(AddProduct.price)
async def process_product_price(message: Message, state: FSMContext):
    try:
        await state.update_data(price=float(message.text.replace(',', '.')))
        await state.set_state(AddProduct.stock)
        await message.answer("Введите количество на складе (число):")
    except ValueError:
        await message.answer("Неверный формат. Введите число, например: 1500.50")


@dp.message(AddProduct.stock)
async def process_product_stock(message: Message, state: FSMContext):
    try:
        await state.update_data(stock=int(message.text))
        await state.set_state(AddProduct.photo)
        await message.answer("Отправьте фото товара или напишите 'пропустить'.")
    except ValueError:
        await message.answer("Неверный формат. Введите целое число, например: 10")


@dp.message(AddProduct.photo, F.photo)
async def process_product_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    file_info = await bot.get_file(file_id)
    file_path_tg = file_info.file_path
    local_file_path = f"photos/{file_id}.jpg"
    os.makedirs("photos", exist_ok=True)
    await bot.download_file(file_path_tg, local_file_path)
    await state.update_data(photo=local_file_path)
    await save_product_and_finish(message, state)


@dp.message(AddProduct.photo, F.text)
async def process_product_skip_photo(message: Message, state: FSMContext):
    if 'пропустить' in message.text.lower():
        await state.update_data(photo=None)
        await save_product_and_finish(message, state)
    else:
        await message.answer("Неверная команда. Отправьте фото или напишите 'пропустить'.")


async def save_product_and_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    add_product(data['category'], data['brand'], data['name'], data['description'], data['price'], data['stock'],
                data.get('photo'))
    await message.answer(f"✅ Товар «{data['name']}» успешно добавлен!")
    await state.clear()
    await message.answer("Вы в админ-панели:", reply_markup=admin_panel_kb())


# --- Админка: Редактирование товара ---
@dp.callback_query(F.data == "admin_edit")
async def admin_edit_start(call: CallbackQuery):
    kb = categories_kb("edit", "admin_assort")
    await send_or_edit(call, "Выберите категорию для редактирования:", kb)
    await call.answer()


@dp.callback_query(F.data.startswith("edit_cat_"))
async def admin_edit_brand(call: CallbackQuery):
    category = call.data.split("_")[2]
    kb = brands_kb(category, "edit", "admin_edit")
    if not kb: return await call.answer("Нет брендов.", show_alert=True)
    await send_or_edit(call, "Выберите бренд:", kb)
    await call.answer()


@dp.callback_query(F.data.startswith("edit_brand_"))
async def admin_edit_product(call: CallbackQuery):
    _, _, category, brand = call.data.split("_", 3)
    products = get_products_by_brand(category, brand)
    if not products: return await call.answer("Нет товаров.", show_alert=True)
    await send_or_edit(call, "Выберите товар для редактирования:",
                       product_list_kb(products, "edit", f"edit_cat_{category}"))
    await call.answer()


@dp.callback_query(F.data.startswith("edit_prod_"))
async def admin_edit_menu(call: CallbackQuery, state: FSMContext):
    pid = int(call.data.split("_")[2])
    prod = get_product_by_id(pid)
    if not prod: return await call.answer("Товар не найден", show_alert=True)
    await state.update_data(product_id=pid)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔤 Название", callback_data="edit_field_name")],
        [InlineKeyboardButton(text="📝 Описание", callback_data="edit_field_description")],
        [InlineKeyboardButton(text="💰 Цена", callback_data="edit_field_price")],
        [InlineKeyboardButton(text="🖼 Фото", callback_data="edit_field_photo")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"edit_brand_{prod['category']}_{prod['brand']}")]
    ])
    await send_or_edit(call, f"🔧 Редактирование: <b>{prod['name']}</b>", kb)
    await call.answer()


@dp.callback_query(F.data.startswith("edit_field_"))
async def edit_product_field_prompt(call: CallbackQuery, state: FSMContext):
    field = call.data.split("_")[2]
    await state.update_data(field=field)
    prompts = {
        "name": "Введите новое название:",
        "description": "Введите новое описание:",
        "price": "Введите новую цену:",
        "photo": "Отправьте новое фото или напишите 'пропустить' для удаления:"
    }
    await call.message.edit_text(prompts[field])
    await state.set_state(EditProduct.new_value)
    await call.answer()


@dp.message(EditProduct.new_value, F.text)
async def edit_product_save_text(message: Message, state: FSMContext):
    data = await state.get_data()
    pid, field = data['product_id'], data['field']
    value = message.text

    if field == 'price':
        try:
            value = float(value.replace(',', '.'))
        except ValueError:
            return await message.answer("Неверный формат, введите число.")

    if field == 'photo' and 'пропустить' in value.lower():
        value = None

    update_product(pid, **{field: value})
    await message.answer(f"✅ Поле «{field}» обновлено!")
    await state.clear()
    await message.answer("Вы в админ-панели:", reply_markup=admin_panel_kb())


@dp.message(EditProduct.new_value, F.photo)
async def edit_product_save_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    if data['field'] != 'photo': return

    pid = data['product_id']
    file_id = message.photo[-1].file_id
    file_info = await bot.get_file(file_id)
    file_path_tg = file_info.file_path
    local_file_path = f"photos/{file_id}.jpg"
    os.makedirs("photos", exist_ok=True)
    await bot.download_file(file_path_tg, local_file_path)

    update_product(pid, photo=local_file_path)
    await message.answer("✅ Фото обновлено!")
    await state.clear()
    await message.answer("Вы в админ-панели:", reply_markup=admin_panel_kb())


# --- Админка: Удаление товара ---
@dp.callback_query(F.data == "admin_delete")
async def admin_delete_start(call: CallbackQuery):
    kb = categories_kb("delete", "admin_assort")
    await send_or_edit(call, "Выберите категорию для удаления товара:", kb)
    await call.answer()


@dp.callback_query(F.data.startswith("delete_cat_"))
async def admin_delete_brand(call: CallbackQuery):
    category = call.data.split("_")[2]
    kb = brands_kb(category, "delete", "admin_delete")
    if not kb: return await call.answer("В этой категории нет брендов.", show_alert=True)
    await send_or_edit(call, "Выберите бренд:", kb)
    await call.answer()


@dp.callback_query(F.data.startswith("delete_brand_"))
async def admin_delete_product(call: CallbackQuery):
    _, _, category, brand = call.data.split("_", 3)
    products = get_products_by_brand(category, brand)
    if not products: return await call.answer("Нет товаров у этого бренда.", show_alert=True)
    await send_or_edit(call, "Выберите товар для удаления:",
                       product_list_kb(products, "delete", f"delete_cat_{category}"))
    await call.answer()


@dp.callback_query(F.data.startswith("delete_prod_"))
async def admin_delete_confirm(call: CallbackQuery):
    pid = int(call.data.split("_")[2])
    prod = get_product_by_id(pid)
    if not prod: return await call.answer("Товар не найден", show_alert=True)

    text = f"Вы подтверждаете удаление?\n\n<b>{prod['name']}</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить удаление", callback_data=f"delete_execute_{pid}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"delete_brand_{prod['category']}_{prod['brand']}")]
    ])
    await send_or_edit(call, text, kb)
    await call.answer()


@dp.callback_query(F.data.startswith("delete_execute_"))
async def admin_delete_execute(call: CallbackQuery):
    pid = int(call.data.split("_")[2])
    prod = get_product_by_id(pid)
    if not prod: return await call.answer("Товар уже удален.", show_alert=True)

    delete_product(pid)
    await call.answer(f"Товар «{prod['name']}» удален.", show_alert=True)
    await send_or_edit(call, "Вы возвращены в админ-панель.", admin_panel_kb())


# --- Админка: Изменение количества ---
@dp.callback_query(F.data == "admin_status")
async def admin_quantity_start(call: CallbackQuery):
    kb = categories_kb("quantity", "admin_assort")
    await send_or_edit(call, "Выберите категорию для изменения количества:", kb)
    await call.answer()


@dp.callback_query(F.data.startswith("quantity_cat_"))
async def admin_quantity_brand(call: CallbackQuery):
    category = call.data.split("_")[2]
    kb = brands_kb(category, "quantity", "admin_status")
    if not kb: return await call.answer("Нет брендов.", show_alert=True)
    await send_or_edit(call, "Выберите бренд:", kb)
    await call.answer()


@dp.callback_query(F.data.startswith("quantity_brand_"))
async def admin_quantity_product(call: CallbackQuery):
    _, _, category, brand = call.data.split("_", 3)
    products = get_products_by_brand(category, brand)
    if not products: return await call.answer("Нет товаров.", show_alert=True)
    await send_or_edit(call, "Выберите товар:", product_list_kb(products, "quantity", f"quantity_cat_{category}"))
    await call.answer()


@dp.callback_query(F.data.startswith("quantity_prod_"))
async def admin_quantity_prompt(call: CallbackQuery, state: FSMContext):
    pid = int(call.data.split("_")[2])
    prod = get_product_by_id(pid)
    if not prod: return

    await state.set_state(EditStock.waiting_for_stock)
    await state.update_data(product_id=pid)
    await call.message.edit_text(f"Введите новое количество для «{prod['name']}».\nТекущее: {prod['stock']} шт.")
    await call.answer()


@dp.message(EditStock.waiting_for_stock)
async def admin_quantity_save(message: Message, state: FSMContext):
    try:
        new_quantity = int(message.text)
        if new_quantity < 0: raise ValueError
    except ValueError:
        return await message.answer("Ошибка. Введите целое положительное число.")

    data = await state.get_data()
    pid = data['product_id']
    await state.clear()

    new_status = 'in_stock' if new_quantity > 0 else 'out_of_stock'
    update_product(pid, stock=new_quantity, status=new_status)

    await message.answer(f"✅ Количество товара успешно обновлено на {new_quantity} шт.")
    await message.answer("Вы в админ-панели:", reply_markup=admin_panel_kb())


# --- Админка: Редактирование акций ---
@dp.callback_query(F.data == "admin_promo")
async def admin_promo_menu(call: CallbackQuery):
    promos = get_all_promotions()
    kb = [[InlineKeyboardButton(text=f"❌ {title}", callback_data=f"del_promo_{pid}")] for pid, title in promos]
    kb.append([InlineKeyboardButton(text="➕ Добавить акцию", callback_data="add_promo")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")])
    await send_or_edit(call, "🎨 Управление акциями:", InlineKeyboardMarkup(inline_keyboard=kb))


@dp.callback_query(F.data == "add_promo")
async def add_promo_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddPromotion.title)
    await call.message.edit_text("Введите заголовок для новой акции:")
    await call.answer()


@dp.message(AddPromotion.title)
async def add_promo_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AddPromotion.content)
    await message.answer("Введите текст акции или напишите 'пропустить':")


@dp.message(AddPromotion.content)
async def add_promo_content(message: Message, state: FSMContext):
    if 'пропустить' in message.text.lower():
        await state.update_data(content="")
    else:
        await state.update_data(content=message.text)

    await state.set_state(AddPromotion.photo)
    await message.answer("Отправьте фото для акции или напишите 'пропустить':")


@dp.message(AddPromotion.photo, F.photo)
async def add_promo_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    file_info = await bot.get_file(file_id)
    file_path_tg = file_info.file_path
    local_file_path = f"photos/promo_{file_id}.jpg"
    os.makedirs("photos", exist_ok=True)
    await bot.download_file(file_path_tg, local_file_path)
    await state.update_data(photo=local_file_path)
    data = await state.get_data()
    add_promotion(data['title'], data['content'], data.get('photo'))
    await message.answer("✅ Акция добавлена!")
    await state.clear()
    await message.answer("Вы в админ-панели:", reply_markup=admin_panel_kb())


@dp.message(AddPromotion.photo, F.text)
async def add_promo_skip_photo(message: Message, state: FSMContext):
    if 'пропустить' in message.text.lower():
        await state.update_data(photo=None)
        data = await state.get_data()
        add_promotion(data['title'], data['content'], data.get('photo'))
        await message.answer("✅ Акция добавлена!")
        await state.clear()
        await message.answer("Вы в админ-панели:", reply_markup=admin_panel_kb())


@dp.callback_query(F.data.startswith("del_promo_"))
async def delete_promo_handler(call: CallbackQuery):
    promo_id = int(call.data.split("_")[2])
    delete_promotion(promo_id)
    await call.answer("Акция удалена.", show_alert=True)
    await admin_promo_menu(call)


# --- Админка: Редактирование FAQ ---
@dp.callback_query(F.data == "admin_faq")
async def admin_faq_menu(call: CallbackQuery):
    faqs = get_all_faq()
    kb = [[InlineKeyboardButton(text=f"❌ {q}", callback_data=f"del_faq_{fid}")] for fid, q in faqs]
    kb.append([InlineKeyboardButton(text="➕ Добавить вопрос", callback_data="add_faq")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")])
    await send_or_edit(call, "💬 Управление вопросами:", InlineKeyboardMarkup(inline_keyboard=kb))


@dp.callback_query(F.data == "add_faq")
async def add_faq_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddFAQ.question)
    await call.message.edit_text("Введите новый вопрос:")
    await call.answer()


@dp.message(AddFAQ.question)
async def add_faq_question(message: Message, state: FSMContext):
    await state.update_data(question=message.text)
    await state.set_state(AddFAQ.answer)
    await message.answer("Теперь введите ответ на этот вопрос:")


@dp.message(AddFAQ.answer)
async def add_faq_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    add_faq(data['question'], message.text)
    await message.answer("✅ Вопрос-ответ добавлен!")
    await state.clear()
    await message.answer("Вы в админ-панели:", reply_markup=admin_panel_kb())


@dp.callback_query(F.data.startswith("del_faq_"))
async def delete_faq_handler(call: CallbackQuery):
    faq_id = int(call.data.split("_")[2])
    delete_faq(faq_id)
    await call.answer("Вопрос удален.", show_alert=True)
    await admin_faq_menu(call)


# --- Админка: Статистика ---
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    stats = get_stats()
    text = (
        f"📊 <b>Статистика магазина</b> 📊\n\n"
        f"<b>Финансы:</b>\n"
        f"💰 Общий доход: <code>{stats['total_revenue']}₽</code>\n"
        f"📈 Доход за 7 дней: <code>{stats['revenue_7_days']}₽</code>\n"
        f"📅 Доход за 30 дней: <code>{stats['revenue_30_days']}₽</code>\n\n"
        f"<b>Активность:</b>\n"
        f"👥 Всего пользователей: <code>{stats['total_users']}</code>\n"
        f"🛍 Продаж сегодня: <code>{stats['sales_today']}</code>\n"
        f"🏆 Всего продаж: <code>{stats['sales_total']}</code>"
    )
    await send_or_edit(call, text, InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]]))


# --- Админка: Посмотреть корзины ---
@dp.callback_query(F.data == "admin_carts")
async def admin_carts_list(call: CallbackQuery):
    carts = get_all_carts()
    if not carts:
        return await send_or_edit(call, "Нет пользователей с товарами в корзине.", InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]]))

    kb = [[InlineKeyboardButton(text=f"@{username}" if username else f"ID: {uid}", callback_data=f"view_cart_{uid}")]
          for uid, username in carts]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")])
    await send_or_edit(call, "Выберите корзину для просмотра:", InlineKeyboardMarkup(inline_keyboard=kb))


@dp.callback_query(F.data.startswith("view_cart_"))
async def admin_view_cart(call: CallbackQuery):
    user_id = int(call.data.split("_")[2])
    cart_items = get_cart(user_id)

    with get_db_connection() as conn:
        user_info = conn.execute("SELECT username FROM users WHERE user_id=?", (user_id,)).fetchone()
    username = user_info[0] if user_info and user_info[0] else f"ID {user_id}"

    text = f"<b>🛒 Корзина пользователя</b>\nПользователь: @{username} (<code>{user_id}</code>)\n\n<b>Состав заказа:</b>\n"
    total_price = 0
    for pid, name, price, quantity in cart_items:
        total_price += price * quantity
        text += f"• {name} ({quantity} шт.) - {price}₽/шт.\n"

    text += f"\n<b>Общая сумма: {total_price}₽</b>"

    await send_or_edit(call, text, InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_carts")]]))


# --- Админка: Редактирование администрации ---
@dp.callback_query(F.data == "admin_manage_admins")
async def admin_manage_admins_menu(call: CallbackQuery):
    if call.from_user.id not in ADMINS: return
    await send_or_edit(call, "👥 Управление администраторами:", admin_management_kb())


@dp.callback_query(F.data == "admin_add_admin")
async def add_admin_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMINS: return
    await state.set_state(AdminManagement.add_admin_id)
    await call.message.edit_text("Введите ID пользователя для назначения администратором.\n\n"
                                 "<i>Чтобы узнать ID, пользователь может воспользоваться ботом @userinfobot</i>")
    await call.answer()


@dp.message(AdminManagement.add_admin_id)
async def add_admin_finish(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
        add_admin_to_db(user_id)
        await message.answer(f"✅ Пользователь с ID <code>{user_id}</code> успешно назначен администратором.")
        await state.clear()
        await message.answer("Вы в админ-панели:", reply_markup=admin_panel_kb())
    except ValueError:
        await message.answer("Неверный формат. Введите числовой ID.")


@dp.callback_query(F.data == "admin_remove_admin")
async def remove_admin_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMINS: return

    other_admins = [admin_id for admin_id in ADMINS if admin_id != call.from_user.id]
    if not other_admins:
        return await call.answer("Нет других администраторов для удаления.", show_alert=True)

    kb = [[InlineKeyboardButton(text=f"❌ Удалить {admin_id}", callback_data=f"remove_admin_{admin_id}")] for admin_id in
          other_admins]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_manage_admins")])

    await send_or_edit(call, "Выберите администратора для удаления:", InlineKeyboardMarkup(inline_keyboard=kb))


@dp.callback_query(F.data.startswith("remove_admin_"))
async def remove_admin_finish(call: CallbackQuery):
    admin_id_to_remove = int(call.data.split("_")[2])
    if admin_id_to_remove == ADMIN_ID:  # Защита от удаления главного админа
        return await call.answer("Нельзя удалить главного администратора.", show_alert=True)

    remove_admin_from_db(admin_id_to_remove)
    await call.answer(f"Администратор с ID {admin_id_to_remove} удален.", show_alert=True)
    await admin_manage_admins_menu(call)


# --- Админка: Забронированные товары ---
@dp.callback_query(F.data == "admin_reservations")
async def admin_reservations(call: CallbackQuery):
    reservations = get_all_reservations()
    if not reservations:
        return await send_or_edit(call, "Активных бронирований нет.", InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]]))

    kb = [[InlineKeyboardButton(text=f"Код: {code}", callback_data=f"res_{res_id}")] for res_id, code in reservations]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")])
    await send_or_edit(call, "Выберите бронирование для просмотра деталей:", InlineKeyboardMarkup(inline_keyboard=kb))


@dp.callback_query(F.data.startswith("res_"))
async def admin_show_reservation_details(call: CallbackQuery):
    res_id = int(call.data.split("_")[1])
    res_info, items = get_reservation_details(res_id)

    if not res_info:
        return await call.answer("Бронь не найдена.", show_alert=True)

    user_id, username, code, date = res_info
    text = f"<b>Бронь #{code}</b>\nПользователь: @{username} (<code>{user_id}</code>)\nДата получения: {date}\n\n<b>Состав заказа:</b>\n"
    total_price = 0
    for _, name, qty, price in items:
        text += f"• {name} ({qty} шт.) - {price}₽/шт.\n"
        total_price += qty * price

    text += f"\n<b>Общая сумма: {total_price}₽</b>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выполнено (завершить)", callback_data=f"complete_res_{code}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_reservations")]
    ])
    await send_or_edit(call, text, kb)


@dp.callback_query(F.data.startswith("complete_res_"))
async def admin_delete_reservation(call: CallbackQuery):
    res_code = int(call.data.split("_")[2])
    complete_reservation(res_code)
    await call.answer("Бронь отмечена как выполненная.", show_alert=True)
    await admin_reservations(call)


# === ЗАПУСК БОТА ===
async def main():
    print("Бот запускается...")
    load_admins()

    # Запускаем фоновую задачу по очистке старых броней
    asyncio.create_task(cleanup_expired_reservations())

    try:
        await dp.start_polling(bot)
    except TelegramConflictError:
        print("Бот уже запущен на другом сервере. Завершение работы.")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    init_db()
    asyncio.run(main())