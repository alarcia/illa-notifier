"""
Bot command handlers for the Illa Notifier Telegram bot.

Run alongside the scraping loop; handles direct user interactions.
"""
import asyncio
import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from database import Database, TelegramUser

load_dotenv()

logger = logging.getLogger("illa_notifier.bot")
db = Database()


@dataclass(frozen=True)
class BotConfig:
    token: str

    @classmethod
    def from_env(cls) -> "BotConfig":
        token = os.environ.get("TELEGRAM_TOKEN", "")
        if not token:
            raise ValueError("TELEGRAM_TOKEN is required but not set")
        return cls(token=token)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command: register the user and send a personalised welcome message."""
    if update.effective_user is None or update.message is None:
        return

    tg_user = update.effective_user
    user = TelegramUser(
        telegram_id=tg_user.id,
        first_name=tg_user.first_name,
        username=tg_user.username,
    )
    db.upsert_user(user)
    logger.info("Upserted user id=%s (%s)", user.telegram_id, user.first_name)

    first_name = tg_user.first_name

    text = (
        f"👋 Hola, {first_name}!\n\n"
        "Soy el bot de 🎬 *Cinemes Illa Carlemany*.\n\n"
        "Me encargo de vigilar la cartelera y avisarte en cuanto llegue "
        "una película nueva al cine. Así nunca te perderás un estreno.\n\n"
        "📢 Las notificaciones automáticas se publican en el canal "
        "@cartelera\\_illa en cuanto se detecta una novedad.\n\n"
        "¡Nos vemos en la butaca! 🍿"
    )

    await update.message.reply_text(text, parse_mode="Markdown")
    logger.info("Sent /start response to user %s (id=%s)", first_name, update.effective_user.id)


def build_application(config: BotConfig) -> Application:
    """Build and configure the Telegram Application with all registered handlers."""
    app = Application.builder().token(config.token).build()
    app.add_handler(CommandHandler("start", start_handler))
    return app


async def _run_bot_async(app: Application) -> None:
    """Low-level async polling that avoids registering UNIX signal handlers.

    app.run_polling() calls loop.add_signal_handler() which only works in the
    main thread. Using the underlying primitives directly sidesteps that.
    """
    async with app:
        await app.updater.start_polling(drop_pending_updates=True)  # type: ignore[union-attr]
        await app.start()
        logger.info("Bot ready and polling for updates")
        # Block until the daemon thread is killed on main process exit.
        await asyncio.Event().wait()


def run_bot() -> None:
    """Entry point for the bot listener. Runs blocking polling in its own thread."""
    config = BotConfig.from_env()
    app = build_application(config)
    logger.info("Bot polling started")
    asyncio.run(_run_bot_async(app))
