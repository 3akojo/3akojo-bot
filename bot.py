import os, sqlite3, logging
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID','0') or 0)
PORT = int(os.environ.get('PORT','10000'))
PUBLIC_URL = os.environ.get('PUBLIC_URL','').rstrip('/')
DB_PATH = os.environ.get('DB_PATH','a3kojo.db')

# CJ Affiliate link
CJ_AFFILIATE_URL = os.environ.get('CJ_AFFILIATE_URL','').strip()

if not TOKEN:
    raise RuntimeError('BOT_TOKEN is missing')

if not PUBLIC_URL:
    # Render supplies RENDER_EXTERNAL_URL automatically; use it if present.
    PUBLIC_URL = os.environ.get('RENDER_EXTERNAL_URL','').rstrip('/')

app = Flask(__name__)


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    c = con.cursor()

    c.execute(
        'CREATE TABLE IF NOT EXISTS users '
        '(id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, '
        'balance REAL DEFAULT 0, referred_by INTEGER, referrals INTEGER DEFAULT 0)'
    )

    c.execute(
        'CREATE TABLE IF NOT EXISTS products '
        '(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price REAL, '
        'description TEXT, active INTEGER DEFAULT 1)'
    )

    c.execute(
        'CREATE TABLE IF NOT EXISTS orders '
        '(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, '
        'product_id INTEGER, status TEXT DEFAULT "pending", '
        'created_at TEXT DEFAULT CURRENT_TIMESTAMP)'
    )

    c.execute(
        'CREATE TABLE IF NOT EXISTS ads '
        '(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, '
        'text TEXT, active INTEGER DEFAULT 1)'
    )

    con.commit()
    con.close()


init_db()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user

    ref = None

    if context.args and context.args[0].startswith('ref_'):
        try:
            ref = int(context.args[0][4:])
        except:
            pass

    con = db()

    row = con.execute(
        'SELECT * FROM users WHERE id=?',
        (u.id,)
    ).fetchone()

    if not row:
        con.execute(
            'INSERT INTO users(id,username,first_name,referred_by) '
            'VALUES(?,?,?,?)',
            (
                u.id,
                u.username or '',
                u.first_name or '',
                ref if ref and ref != u.id else None
            )
        )

        if ref and ref != u.id and con.execute(
            'SELECT 1 FROM users WHERE id=?',
            (ref,)
        ).fetchone():

            con.execute(
                'UPDATE users SET referrals=referrals+1 WHERE id=?',
                (ref,)
            )

        con.commit()

    con.close()

    # Main menu
    kb = [
        [
            InlineKeyboardButton(
                '🛍️ المنتجات',
                callback_data='products'
            ),
            InlineKeyboardButton(
                '👥 الإحالات',
                callback_data='ref'
            )
        ],
        [
            InlineKeyboardButton(
                '💰 المحفظة',
                callback_data='wallet'
            ),
            InlineKeyboardButton(
                '📢 الإعلانات',
                callback_data='ads'
            )
        ],
        [
            InlineKeyboardButton(
                '📦 طلباتي',
                callback_data='orders'
            )
        ]
    ]

    # CJ Affiliate button
    if CJ_AFFILIATE_URL:
        kb.append([
            InlineKeyboardButton(
                '🛍️ عروض CJ',
                url=CJ_AFFILIATE_URL
            )
        ])

    await update.message.reply_text(
        '🔥 أهلاً بك في 3akojo\n\n'
        '🛍️ تسوق • عروض • إحالات • أرباح\n\n'
        'اختر من القائمة:',
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def myid(update, context):
    await update.message.reply_text(
        f'معرّف Telegram الخاص بك هو: {update.effective_user.id}'
    )


async def menu(update, context):
    await start(update, context)


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id

    if q.data == 'products':

        con = db()

        rows = con.execute(
            'SELECT * FROM products WHERE active=1 ORDER BY id DESC'
        ).fetchall()

        con.close()

        if not rows:
            return await q.edit_message_text(
                '🛍️ لا توجد منتجات مضافة حاليًا.\n\n'
                'سنضيف المنتجات من لوحة الإدارة.'
            )

        text = '🛍️ المنتجات المتاحة:\n\n'

        for r in rows:
            text += (
                f"#{r['id']} — {r['name']}\n"
                f"💵 {r['price']:.2f}\n"
                f"{r['description']}\n\n"
            )

        await q.edit_message_text(text)

    elif q.data == 'ref':

        link = (
            f'https://t.me/'
            f'{(await context.bot.get_me()).username}'
            f'?start=ref_{uid}'
        )

        con = db()

        r = con.execute(
            'SELECT referrals FROM users WHERE id=?',
            (uid,)
        ).fetchone()

        con.close()

        n = r['referrals'] if r else 0

        await q.edit_message_text(
            f'👥 الإحالات\n\n'
            f'عدد إحالاتك: {n}\n\n'
            f'🔗 رابطك:\n{link}\n\n'
            f'شارك الرابط مع الآخرين. '
            f'لا نعد بأرباح مضمونة؛ العمولات تعتمد على النظام والعروض الفعلية.'
        )

    elif q.data == 'wallet':

        con = db()

        r = con.execute(
            'SELECT balance FROM users WHERE id=?',
            (uid,)
        ).fetchone()

        con.close()

        bal = r['balance'] if r else 0

        await q.edit_message_text(
            f'💰 محفظتك\n\n'
            f'الرصيد الحالي: {bal:.2f}'
        )

    elif q.data == 'ads':

        con = db()

        rows = con.execute(
            'SELECT * FROM ads WHERE active=1 '
            'ORDER BY id DESC LIMIT 10'
        ).fetchall()

        con.close()

        if not rows:
            return await q.edit_message_text(
                '📢 لا توجد إعلانات حاليًا.'
            )

        await q.edit_message_text(
            '\n\n'.join(
                f"📢 {r['title']}\n{r['text']}"
                for r in rows
            )
        )

    elif q.data == 'orders':

        con = db()

        rows = con.execute(
            'SELECT o.id,p.name,o.status,o.created_at '
            'FROM orders o '
            'JOIN products p ON p.id=o.product_id '
            'WHERE o.user_id=? '
            'ORDER BY o.id DESC LIMIT 10',
            (uid,)
        ).fetchall()

        con.close()

        if not rows:
            return await q.edit_message_text(
                '📦 لا توجد طلبات حتى الآن.'
            )

        await q.edit_message_text(
            '\n'.join(
                f"#{r['id']} — {r['name']} — {r['status']}"
                for r in rows
            )
        )


async def admin(update, context):

    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text('غير مصرح.')

    await update.message.reply_text(
        '👑 لوحة الإدارة\n\n'
        '/addproduct الاسم|السعر|الوصف\n'
        '/addad العنوان|النص\n'
        '/credit user_id|amount\n'
        '/stats\n'
        '/orders\n'
        '/withdrawals'
    )


async def addproduct(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    raw = update.message.text.partition(' ')[2]

    parts = [
        x.strip()
        for x in raw.split('|', 2)
    ]

    if len(parts) != 3:
        return await update.message.reply_text(
            'الصيغة: /addproduct الاسم|السعر|الوصف'
        )

    try:
        price = float(parts[1])
    except:
        return await update.message.reply_text(
            'السعر يجب أن يكون رقمًا.'
        )

    con = db()

    con.execute(
        'INSERT INTO products(name,price,description) '
        'VALUES(?,?,?)',
        tuple(parts)
    )

    con.commit()
    con.close()

    await update.message.reply_text(
        '✅ تمت إضافة المنتج.'
    )


async def addad(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    parts = [
        x.strip()
        for x in update.message.text.partition(' ')[2].split('|', 1)
    ]

    if len(parts) != 2:
        return await update.message.reply_text(
            'الصيغة: /addad العنوان|النص'
        )

    con = db()

    con.execute(
        'INSERT INTO ads(title,text) VALUES(?,?)',
        parts
    )

    con.commit()
    con.close()

    await update.message.reply_text(
        '✅ تمت إضافة الإعلان.'
    )


async def credit(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    parts = [
        x.strip()
        for x in update.message.text.partition(' ')[2].split('|', 1)
    ]

    if len(parts) != 2:
        return await update.message.reply_text(
            'الصيغة: /credit user_id|amount'
        )

    try:
        uid = int(parts[0])
        amount = float(parts[1])
    except:
        return await update.message.reply_text(
            'بيانات غير صحيحة.'
        )

    con = db()

    con.execute(
        'UPDATE users SET balance=balance+? WHERE id=?',
        (amount, uid)
    )

    con.commit()
    con.close()

    await update.message.reply_text(
        '✅ تم تعديل الرصيد.'
    )


async def stats(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    con = db()

    a = con.execute(
        'SELECT COUNT(*) n FROM users'
    ).fetchone()['n']

    p = con.execute(
        'SELECT COUNT(*) n FROM products WHERE active=1'
    ).fetchone()['n']

    o = con.execute(
        'SELECT COUNT(*) n FROM orders'
    ).fetchone()['n']

    con.close()

    await update.message.reply_text(
        f'📊 المستخدمون: {a}\n'
        f'🛍️ المنتجات: {p}\n'
        f'📦 الطلبات: {o}'
    )


bot_app = Application.builder().token(TOKEN).build()

bot_app.add_handler(
    CommandHandler('start', start)
)

bot_app.add_handler(
    CommandHandler('myid', myid)
)

bot_app.add_handler(
    CommandHandler('menu', menu)
)

bot_app.add_handler(
    CommandHandler('admin', admin)
)

bot_app.add_handler(
    CommandHandler('addproduct', addproduct)
)

bot_app.add_handler(
    CommandHandler('addad', addad)
)

bot_app.add_handler(
    CommandHandler('credit', credit)
)

bot_app.add_handler(
    CommandHandler('stats', stats)
)

bot_app.add_handler(
    CallbackQueryHandler(buttons)
)


@app.get('/')
def health():
    return '3akojo bot is running', 200


@app.post('/telegram')
def telegram_webhook():

    update = Update.de_json(
        request.get_json(force=True),
        bot_app.bot
    )

    import asyncio

    asyncio.run(
        bot_app.process_update(update)
    )

    return 'ok', 200


async def setup():

    await bot_app.initialize()

    if PUBLIC_URL:
        await bot_app.bot.set_webhook(
            url=f'{PUBLIC_URL}/telegram'
        )

    await bot_app.start()


if __name__ == '__main__':

    import asyncio, threading

    asyncio.run(setup())

    app.run(
        host='0.0.0.0',
        port=PORT
    )
