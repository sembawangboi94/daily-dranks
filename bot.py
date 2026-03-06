import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from db import WaterDB

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CODE = os.getenv("ADMIN_CODE", "")
DB_PATH = os.getenv("DB_PATH", "water.db")
TZ = os.getenv("TZ", "Asia/Singapore")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")
if not ADMIN_CODE:
    raise RuntimeError("ADMIN_CODE is required")

db = WaterDB(DB_PATH)


def in_allowed_chat(chat_id: int) -> bool:
    allowed = db.get_allowed_chat_id()
    return allowed is not None and allowed == chat_id


def fmt_user_label(user) -> str:
    if user.username:
        return f"@{user.username}"
    return user.full_name or str(user.id)


def panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("+150", callback_data="add:150"),
                InlineKeyboardButton("+250", callback_data="add:250"),
                InlineKeyboardButton("+500", callback_data="add:500"),
            ],
            [InlineKeyboardButton("Custom amount", callback_data="custom")],
        ]
    )


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Open Panel", callback_data="open_panel")]]
    )


def render_today_summary(chat_id: int, user_id: int, tz_name: str) -> str:
    total = db.get_today_user_total(chat_id, user_id, tz_name)
    goal = db.get_user_goal(chat_id, user_id)
    timeline = db.get_today_timeline(chat_id, user_id, tz_name)
    tz = ZoneInfo(tz_name)

    lines = [f"Today total: {total} ml"]
    if goal:
        pct = min(100, int((total / goal) * 100)) if goal > 0 else 0
        lines.append(f"Goal: {goal} ml ({pct}%)")

    if timeline:
        lines.append("Timeline today:")
        for entry in timeline:
            t_local = datetime.fromisoformat(entry.created_at_utc).astimezone(tz)
            lines.append(f"- {t_local.strftime('%H:%M')} +{entry.amount_ml} ml")
    else:
        lines.append("No logs yet today.")

    series = db.get_daily_series(chat_id, user_id, tz_name, days=7)
    lines.append("\nLast 7 days:")
    for day, amount in series:
        bars = "█" * min(20, amount // 100)
        lines.append(f"{day}: {amount} ml {bars}")

    return "\n".join(lines)


async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.message:
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /setup <ADMIN_CODE>")
        return
    if context.args[0] != ADMIN_CODE:
        await update.message.reply_text("Invalid admin code.")
        return

    db.set_allowed_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        f"Setup complete for this chat ({update.effective_chat.id})."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.effective_user or not update.message:
        return

    chat_id = update.effective_chat.id
    if update.effective_chat.type != "private" and not in_allowed_chat(chat_id):
        return

    goal = db.get_user_goal(chat_id, update.effective_user.id)
    msg = [
        "Welcome to Daily Dranks 💧",
        "Use /w to open quick buttons or /w <ml> to log custom amount.",
        "Use /leaderboard to see group totals today, and /undo to remove your last entry.",
    ]
    if not goal:
        msg.append("You haven't set a daily goal yet. Set one with /goal <ml> (e.g., /goal 2000).")

    await update.message.reply_text("\n".join(msg), reply_markup=start_keyboard())


async def goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.effective_user or not update.message:
        return
    chat_id = update.effective_chat.id
    if not in_allowed_chat(chat_id):
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /goal <ml> (e.g. /goal 2000)")
        return
    amount = int(context.args[0])
    if amount < 200 or amount > 10000:
        await update.message.reply_text("Goal should be between 200 and 10000 ml.")
        return

    db.set_user_goal(chat_id, update.effective_user.id, amount)
    await update.message.reply_text(f"Daily goal set to {amount} ml.")


async def w(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.effective_user or not update.message:
        return
    chat_id = update.effective_chat.id
    if not in_allowed_chat(chat_id):
        return

    if len(context.args) == 0:
        await update.message.reply_text("Choose an amount:", reply_markup=panel_keyboard())
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /w <ml> or /w to open panel")
        return

    amount = int(context.args[0])
    await log_amount(update, amount)


async def log_amount(update: Update, amount: int):
    if not update.effective_chat or not update.effective_user:
        return
    if amount < 1 or amount > 5000:
        if update.message:
            await update.message.reply_text("Amount must be between 1 and 5000 ml.")
        elif update.callback_query:
            await update.callback_query.answer("Amount must be between 1 and 5000 ml.", show_alert=True)
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    now_utc = datetime.now(ZoneInfo("UTC")).isoformat()
    db.add_log(chat_id, user.id, fmt_user_label(user), amount, now_utc)

    summary = render_today_summary(chat_id, user.id, TZ)
    if update.message:
        await update.message.reply_text(f"Logged +{amount} ml.\n\n{summary}")
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text=f"Logged +{amount} ml.\n\n{summary}", reply_markup=panel_keyboard()
        )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not update.effective_chat:
        return
    if not in_allowed_chat(update.effective_chat.id):
        await query.answer("Chat not allowed.", show_alert=True)
        return

    await query.answer()

    if query.data == "open_panel":
        await query.edit_message_text("Choose an amount:", reply_markup=panel_keyboard())
        return

    if query.data == "custom":
        await query.edit_message_text("Use /w <ml> to log a custom amount (e.g. /w 320).")
        return

    if query.data and query.data.startswith("add:"):
        amount = int(query.data.split(":", 1)[1])
        await log_amount(update, amount)


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    if not in_allowed_chat(chat_id):
        return

    rows = db.get_today_group_leaderboard(chat_id, TZ, limit=20)
    if not rows:
        await update.message.reply_text("No logs in this group today yet.")
        return

    lines = ["Today's leaderboard 💧"]
    for idx, (_, label, total) in enumerate(rows, start=1):
        lines.append(f"{idx}. {label}: {total} ml")
    await update.message.reply_text("\n".join(lines))


async def undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.effective_user or not update.message:
        return
    chat_id = update.effective_chat.id
    if not in_allowed_chat(chat_id):
        return

    removed = db.undo_last(chat_id, update.effective_user.id)
    if removed is None:
        await update.message.reply_text("Nothing to undo.")
        return

    summary = render_today_summary(chat_id, update.effective_user.id, TZ)
    await update.message.reply_text(f"Removed last entry: {removed} ml.\n\n{summary}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("setup", setup))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("goal", goal))
    app.add_handler(CommandHandler("w", w))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("undo", undo))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
