import os
import sqlite3
import logging
from urllib.parse import quote

from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0") or 0)
PORT = int(os.environ.get("PORT", "10000"))
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
DB_PATH = os.environ.get("DB_PATH", "a3kojo.db")

CJ_AFFILIATE_URL = os.environ.get("CJ_AFFILIATE_URL", "").strip()
GENIUS_WAVE_URL = os.environ.get("GENIUS_WAVE_URL", "").strip()

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

if not PUBLIC_URL:
    PUBLIC_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

app = Flask(__name__)


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    c = con.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance REAL DEFAULT 0,
            referred_by INTEGER,
            referrals INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price REAL,
            description TEXT,
            active INTEGER DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            text TEXT,
            active INTEGER DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS affiliate_clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            source TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.commit()
    con.close()


init_db()


def main_menu_keyboard(bot_username=None, user_id=None):
    keyboard = []

    if CJ_AFFILIATE_URL:
        keyboard.append([
            InlineKeyboardButton(
                "🛍️ عروض CJ | CJ Offers",
                callback_data="cj_offers"
            )
        ])

    if GENIUS_WAVE_URL:
        keyboard.append([
            InlineKeyboardButton(
                "🧠 Genius Wave",
                callback_data="genius_wave"
            )
        ])

    keyboard.extend([
        [
            InlineKeyboardButton("🛍️ المنتجات", callback_data="products"),
            InlineKeyboardButton("👥 الإحالات", callback_data="ref"),
        ],
        [
            InlineKeyboardButton("💰 المحفظة", callback_data="wallet"),
            InlineKeyboardButton("📢 الإعلانات", callback_data="ads"),
        ],
        [
            InlineKeyboardButton("📦 طلباتي", callback_data="orders"),
        ],
    ])

    if bot_username and user_id:
        referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

        share_text = (
            "🔥 اكتشف عروض ومنتجات عبر 3akojo\n"
            "🔥 Discover offers and products with 3akojo"
        )

        share_url = (
            "https://t.me/share/url?"
            f"url={quote(referral_link)}&"
            f"text={quote(share_text)}"
        )

        keyboard.append([
            InlineKeyboardButton(
                "📤 مشاركة رابط الإحالة",
                url=share_url
            )
        ])

    return InlineKeyboardMarkup(keyboard)


def back_button():
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                "🏠 القائمة الرئيسية | Main Menu",
                callback_data="menu"
            )
        ]]
    )


async def show_main_menu(message_or_query, context, user_id):
    bot_info = await context.bot.get_me()
    username = bot_info.username

    text = (
        "🔥 Welcome to 3akojo | أهلاً بك في 3akojo\n\n"

        "🛍️ Discover great deals & products\n"
        "🛍️ اكتشف أفضل العروض والمنتجات\n\n"

        "💰 Browse offers and find what you need\n"
        "💰 تصفح العروض واختر ما يناسبك\n\n"

        "👥 Invite friends and share your referral link\n"
        "👥 ادعُ أصدقاءك وشارك رابط الإحالة\n\n"

        "👇 اختر من القائمة للبدء:"
    )

    if hasattr(message_or_query, "edit_message_text"):
        await message_or_query.edit_message_text(
            text,
            reply_markup=main_menu_keyboard(username, user_id)
        )
    else:
        await message_or_query.reply_text(
            text,
            reply_markup=main_menu_keyboard(username, user_id)
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user

    ref = None

    if context.args and context.args[0].startswith("ref_"):
        try:
            ref = int(context.args[0][4:])
        except ValueError:
            ref = None

    con = db()

    row = con.execute(
        "SELECT * FROM users WHERE id=?",
        (u.id,)
    ).fetchone()

    if not row:
        valid_ref = None

        if ref and ref != u.id:
            exists = con.execute(
                "SELECT 1 FROM users WHERE id=?",
                (ref,)
            ).fetchone()

            if exists:
                valid_ref = ref

        con.execute(
            """
            INSERT INTO users
            (id, username, first_name, referred_by)
            VALUES (?, ?, ?, ?)
            """,
            (
                u.id,
                u.username or "",
                u.first_name or "",
                valid_ref
            ),
        )

        if valid_ref:
            con.execute(
                """
                UPDATE users
                SET referrals = referrals + 1
                WHERE id=?
                """,
                (valid_ref,)
            )

        con.commit()

    else:
        con.execute(
            """
            UPDATE users
            SET username=?, first_name=?
            WHERE id=?
            """,
            (
                u.username or "",
                u.first_name or "",
                u.id
            ),
        )

        con.commit()

    con.close()

    await show_main_menu(update.message, context, u.id)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(
        update.message,
        context,
        update.effective_user.id
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 Telegram ID:\n\n{update.effective_user.id}"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ 3akojo Help | المساعدة\n\n"

        "🛍️ عروض CJ — تصفح العروض والمنتجات.\n"
        "🧠 Genius Wave — مشاهدة عرض Genius Wave.\n"
        "👥 الإحالات — احصل على رابط الإحالة الخاص بك.\n"
        "💰 المحفظة — عرض الرصيد الموجود داخل البوت.\n"
        "📢 الإعلانات — مشاهدة الإعلانات المتاحة.\n"
        "📦 طلباتي — عرض الطلبات المسجلة داخل البوت.\n\n"

        "ℹ️ Affiliate Disclosure:\n"
        "3akojo may earn a commission from eligible purchases "
        "made through affiliate links.\n\n"

        "ℹ️ إفصاح الأفلييت:\n"
        "قد يحصل 3akojo على عمولة عند إتمام عمليات شراء مؤهلة "
        "عبر روابط التسويق بالعمولة."
    )

    await update.message.reply_text(
        text,
        reply_markup=back_button()
    )


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id

    # =========================
    # Main Menu
    # =========================
    if q.data == "menu":
        await show_main_menu(q, context, uid)
        return

    # =========================
    # CJ Offers
    # =========================
    if q.data == "cj_offers":

        if not CJ_AFFILIATE_URL:
            await q.edit_message_text(
                "⚠️ رابط CJ غير مضبوط حاليًا.",
                reply_markup=back_button()
            )
            return

        con = db()

        con.execute(
            """
            INSERT INTO affiliate_clicks
            (user_id, source)
            VALUES (?, ?)
            """,
            (uid, "cj_offers")
        )

        con.commit()
        con.close()

        text = (
            "🛍️ CJ Offers | عروض CJ\n\n"

            "🔥 Discover products and available offers.\n"
            "🔥 اكتشف المنتجات والعروض المتاحة.\n\n"

            "👇 اضغط على الزر لفتح عروض CJ:\n\n"

            "ℹ️ Affiliate Disclosure:\n"
            "3akojo may earn a commission from eligible purchases "
            "made through this affiliate link.\n\n"

            "ℹ️ إفصاح:\n"
            "قد يحصل 3akojo على عمولة عند إتمام عمليات شراء مؤهلة "
            "عبر رابط الأفلييت."
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔗 Open CJ Offers | فتح عروض CJ",
                    url=CJ_AFFILIATE_URL
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 القائمة الرئيسية | Main Menu",
                    callback_data="menu"
                )
            ]
        ])

        await q.edit_message_text(
            text,
            reply_markup=keyboard
        )

        return

    # =========================
    # Genius Wave
    # =========================
    if q.data == "genius_wave":

        if not GENIUS_WAVE_URL:
            await q.edit_message_text(
                "⚠️ رابط Genius Wave غير مضبوط حاليًا.",
                reply_markup=back_button()
            )
            return

        con = db()

        con.execute(
            """
            INSERT INTO affiliate_clicks
            (user_id, source)
            VALUES (?, ?)
            """,
            (uid, "genius_wave")
        )

        con.commit()
        con.close()

        text = (
            "🧠 Genius Wave\n\n"

            "🔥 Discover the Genius Wave offer.\n"
            "🔥 شاهد عرض Genius Wave.\n\n"

            "👇 اضغط على الزر لفتح العرض:\n\n"

            "ℹ️ Affiliate Disclosure:\n"
            "3akojo may earn a commission from eligible purchases "
            "made through this affiliate link.\n\n"

            "ℹ️ إفصاح:\n"
            "قد يحصل 3akojo على عمولة عند إتمام عمليات شراء مؤهلة "
            "عبر رابط الأفلييت."
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🧠 Open Genius Wave | فتح العرض",
                    url=GENIUS_WAVE_URL
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 القائمة الرئيسية | Main Menu",
                    callback_data="menu"
                )
            ]
        ])

        await q.edit_message_text(
            text,
            reply_markup=keyboard
        )

        return

    # =========================
    # Products
    # =========================
    if q.data == "products":

        con = db()

        rows = con.execute(
            """
            SELECT *
            FROM products
            WHERE active=1
            ORDER BY id DESC
            """
        ).fetchall()

        con.close()

        if not rows:
            await q.edit_message_text(
                "🛍️ لا توجد منتجات مضافة حاليًا.\n\n"
                "سنضيف المنتجات من لوحة الإدارة.",
                reply_markup=back_button()
            )
            return

        text = "🛍️ المنتجات المتاحة:\n\n"

        for r in rows:
            text += (
                f"#{r['id']} — {r['name']}\n"
                f"💵 {r['price']:.2f}\n"
                f"{r['description']}\n\n"
            )

        await q.edit_message_text(
            text,
            reply_markup=back_button()
        )

        return

    # =========================
    # Referrals
    # =========================
    if q.data == "ref":

        bot_info = await context.bot.get_me()

        link = (
            f"https://t.me/{bot_info.username}"
            f"?start=ref_{uid}"
        )

        con = db()

        r = con.execute(
            "SELECT referrals FROM users WHERE id=?",
            (uid,)
        ).fetchone()

        con.close()

        n = r["referrals"] if r else 0

        share_url = (
            "https://t.me/share/url?"
            f"url={quote(link)}&"
            f"text={quote('🔥 جرّب 3akojo واكتشف العروض والمنتجات')}"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📤 مشاركة الرابط",
                    url=share_url
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 القائمة الرئيسية | Main Menu",
                    callback_data="menu"
                )
            ]
        ])

        text = (
            "👥 الإحالات | Referrals\n\n"

            f"عدد إحالاتك: {n}\n\n"

            "🔗 رابط الإحالة الخاص بك:\n"
            f"{link}\n\n"

            "شارك الرابط مع الآخرين.\n"
            "Share your referral link with others.\n\n"

            "⚠️ لا توجد أرباح مضمونة؛ أي عمولات تعتمد "
            "على النظام والعروض الفعلية."
        )

        await q.edit_message_text(
            text,
            reply_markup=keyboard
        )

        return

    # =========================
    # Wallet
    # =========================
    if q.data == "wallet":

        con = db()

        r = con.execute(
            "SELECT balance FROM users WHERE id=?",
            (uid,)
        ).fetchone()

        con.close()

        bal = r["balance"] if r else 0

        text = (
            "💰 محفظتك | Your Wallet\n\n"

            f"الرصيد الحالي: {bal:.2f}\n\n"

            "ℹ️ هذا الرصيد هو الرصيد الداخلي في البوت.\n"

            "ℹ️ CJ affiliate commissions are tracked "
            "in your CJ account.\n"

            "ℹ️ Genius Wave affiliate commissions are tracked "
            "in your Digistore24 account."
        )

        await q.edit_message_text(
            text,
            reply_markup=back_button()
        )

        return

    # =========================
    # Ads
    # =========================
    if q.data == "ads":

        con = db()

        rows = con.execute(
            """
            SELECT *
            FROM ads
            WHERE active=1
            ORDER BY id DESC
            LIMIT 10
            """
        ).fetchall()

        con.close()

        if not rows:
            await q.edit_message_text(
                "📢 لا توجد إعلانات حاليًا.",
                reply_markup=back_button()
            )
            return

        text = "\n\n".join(
            f"📢 {r['title']}\n{r['text']}"
            for r in rows
        )

        await q.edit_message_text(
            text,
            reply_markup=back_button()
        )

        return

    # =========================
    # Orders
    # =========================
    if q.data == "orders":

        con = db()

        rows = con.execute(
            """
            SELECT
                o.id,
                p.name,
                o.status,
                o.created_at
            FROM orders o
            JOIN products p
                ON p.id=o.product_id
            WHERE o.user_id=?
            ORDER BY o.id DESC
            LIMIT 10
            """,
            (uid,)
        ).fetchall()

        con.close()

        if not rows:
            await q.edit_message_text(
                "📦 لا توجد طلبات حتى الآن.",
                reply_markup=back_button()
            )
            return

        text = "\n".join(
            f"#{r['id']} — {r['name']} — {r['status']}"
            for r in rows
        )

        await q.edit_message_text(
            text,
            reply_markup=back_button()
        )

        return


def is_admin(user_id):
    return user_id == ADMIN_ID


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح.")
        return

    await update.message.reply_text(
        "👑 لوحة الإدارة\n\n"

        "/addproduct الاسم|السعر|الوصف\n"
        "/addad العنوان|النص\n"
        "/credit user_id|amount\n"
        "/stats\n"
        "/clicks\n"
        "/orders\n"
        "/withdrawals"
    )


async def addproduct(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    raw = update.message.text.partition(" ")[2]

    parts = [
        x.strip()
        for x in raw.split("|", 2)
    ]

    if len(parts) != 3:
        await update.message.reply_text(
            "الصيغة:\n/addproduct الاسم|السعر|الوصف"
        )
        return

    try:
        price = float(parts[1])
    except ValueError:
        await update.message.reply_text(
            "السعر يجب أن يكون رقمًا."
        )
        return

    con = db()

    con.execute(
        """
        INSERT INTO products
        (name, price, description)
        VALUES (?, ?, ?)
        """,
        (
            parts[0],
            price,
            parts[2]
        )
    )

    con.commit()
    con.close()

    await update.message.reply_text(
        "✅ تمت إضافة المنتج."
    )


async def addad(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    raw = update.message.text.partition(" ")[2]

    parts = [
        x.strip()
        for x in raw.split("|", 1)
    ]

    if len(parts) != 2:
        await update.message.reply_text(
            "الصيغة:\n/addad العنوان|النص"
        )
        return

    con = db()

    con.execute(
        """
        INSERT INTO ads
        (title, text)
        VALUES (?, ?)
        """,
        (
            parts[0],
            parts[1]
        )
    )

    con.commit()
    con.close()

    await update.message.reply_text(
        "✅ تمت إضافة الإعلان."
    )


async def credit(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    raw = update.message.text.partition(" ")[2]

    parts = [
        x.strip()
        for x in raw.split("|", 1)
    ]

    if len(parts) != 2:
        await update.message.reply_text(
            "الصيغة:\n/credit user_id|amount"
        )
        return

    try:
        uid = int(parts[0])
        amount = float(parts[1])
    except ValueError:
        await update.message.reply_text(
            "بيانات غير صحيحة."
        )
        return

    con = db()

    result = con.execute(
        """
        UPDATE users
        SET balance=balance+?
        WHERE id=?
        """,
        (
            amount,
            uid
        )
    )

    con.commit()
    con.close()

    if result.rowcount == 0:
        await update.message.reply_text(
            "⚠️ المستخدم غير موجود."
        )
        return

    await update.message.reply_text(
        "✅ تم تعديل الرصيد."
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    con = db()

    users = con.execute(
        "SELECT COUNT(*) n FROM users"
    ).fetchone()["n"]

    products = con.execute(
        """
        SELECT COUNT(*) n
        FROM products
        WHERE active=1
        """
    ).fetchone()["n"]

    orders = con.execute(
        "SELECT COUNT(*) n FROM orders"
    ).fetchone()["n"]

    clicks = con.execute(
        """
        SELECT COUNT(*) n
        FROM affiliate_clicks
        """
    ).fetchone()["n"]

    unique_clickers = con.execute(
        """
        SELECT COUNT(DISTINCT user_id) n
        FROM affiliate_clicks
        """
    ).fetchone()["n"]

    cj_clicks = con.execute(
        """
        SELECT COUNT(*) n
        FROM affiliate_clicks
        WHERE source='cj_offers'
        """
    ).fetchone()["n"]

    genius_clicks = con.execute(
        """
        SELECT COUNT(*) n
        FROM affiliate_clicks
        WHERE source='genius_wave'
        """
    ).fetchone()["n"]

    con.close()

    await update.message.reply_text(
        "📊 إحصائيات 3akojo\n\n"

        f"👥 المستخدمون: {users}\n"
        f"🛍️ المنتجات: {products}\n"
        f"📦 الطلبات: {orders}\n\n"

        f"🔗 إجمالي ضغطات الأفلييت: {clicks}\n"
        f"👤 المستخدمون الفريدون: {unique_clickers}\n\n"

        f"🛍️ ضغطات CJ: {cj_clicks}\n"
        f"🧠 ضغطات Genius Wave: {genius_clicks}"
    )


async def clicks(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    con = db()

    total = con.execute(
        """
        SELECT COUNT(*) n
        FROM affiliate_clicks
        """
    ).fetchone()["n"]

    unique = con.execute(
        """
        SELECT COUNT(DISTINCT user_id) n
        FROM affiliate_clicks
        """
    ).fetchone()["n"]

    cj = con.execute(
        """
        SELECT COUNT(*) n
        FROM affiliate_clicks
        WHERE source='cj_offers'
        """
    ).fetchone()["n"]

    genius = con.execute(
        """
        SELECT COUNT(*) n
        FROM affiliate_clicks
        WHERE source='genius_wave'
        """
    ).fetchone()["n"]

    today = con.execute(
        """
        SELECT COUNT(*) n
        FROM affiliate_clicks
        WHERE date(created_at)=date('now')
        """
    ).fetchone()["n"]

    con.close()

    await update.message.reply_text(
        "🔗 Affiliate Clicks\n\n"

        f"📈 إجمالي الضغطات: {total}\n"
        f"👤 المستخدمون الفريدون: {unique}\n"
        f"📅 ضغطات اليوم: {today}\n\n"

        f"🛍️ CJ: {cj}\n"
        f"🧠 Genius Wave: {genius}\n\n"

        "ℹ️ هذه إحصائيات ضغطات البوت فقط.\n"
        "المبيعات والعمولات الفعلية تظهر في منصات الأفلييت."
    )


async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    con = db()

    rows = con.execute(
        """
        SELECT
            o.id,
            o.user_id,
            p.name,
            o.status,
            o.created_at
        FROM orders o
        JOIN products p
            ON p.id=o.product_id
        ORDER BY o.id DESC
        LIMIT 20
        """
    ).fetchall()

    con.close()

    if not rows:
        await update.message.reply_text(
            "📦 لا توجد طلبات."
        )
        return

    text = "📦 آخر الطلبات:\n\n"

    for r in rows:
        text += (
            f"#{r['id']} | "
            f"User: {r['user_id']} | "
            f"{r['name']} | "
            f"{r['status']}\n"
        )

    await update.message.reply_text(text)


async def withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text(
        "💸 نظام السحب غير مربوط تلقائيًا حاليًا.\n\n"

        "ℹ️ عمولات CJ الفعلية تتم إدارتها "
        "من حساب CJ Affiliate.\n\n"

        "ℹ️ عمولات Genius Wave الفعلية تتم إدارتها "
        "من حساب Digistore24."
    )


@app.get("/")
def health():
    return "3akojo bot is running", 200


@app.post("/telegram")
def telegram_webhook():

    update = Update.de_json(
        request.get_json(force=True),
        bot_app.bot
    )

    import asyncio

    asyncio.run(
        bot_app.process_update(update)
    )

    return "ok", 200


bot_app = Application.builder().token(TOKEN).build()

bot_app.add_handler(
    CommandHandler("start", start)
)

bot_app.add_handler(
    CommandHandler("myid", myid)
)

bot_app.add_handler(
    CommandHandler("menu", menu)
)

bot_app.add_handler(
    CommandHandler("help", help_command)
)

bot_app.add_handler(
    CommandHandler("admin", admin)
)

bot_app.add_handler(
    CommandHandler("addproduct", addproduct)
)

bot_app.add_handler(
    CommandHandler("addad", addad)
)

bot_app.add_handler(
    CommandHandler("credit", credit)
)

bot_app.add_handler(
    CommandHandler("stats", stats)
)

bot_app.add_handler(
    CommandHandler("clicks", clicks)
)

bot_app.add_handler(
    CommandHandler("orders", admin_orders)
)

bot_app.add_handler(
    CommandHandler("withdrawals", withdrawals)
)

bot_app.add_handler(
    CallbackQueryHandler(buttons)
)


async def setup():

    await bot_app.initialize()

    if PUBLIC_URL:
        await bot_app.bot.set_webhook(
            url=f"{PUBLIC_URL}/telegram"
        )

    await bot_app.start()


if __name__ == "__main__":

    import asyncio

    asyncio.run(setup())

    app.run(
        host="0.0.0.0",
        port=PORT
    )
