"""
Bot command handlers for the Illa Notifier Telegram bot.

Run alongside the scraping loop; handles direct user interactions.
"""
import asyncio
import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

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
        "Vigilo la cartelera y aviso en cuanto llega una película nueva. "
        "Así nunca te perderás un estreno.\n\n"
        "📢 *Canal* — @cartelera\\_illa recibe todas las novedades "
        "automáticamente en cuanto se detectan.\n\n"
        "🔔 *Notificaciones personalizadas* — con este bot puedes "
        "suscribirte solo a lo que te interesa: filtra por género "
        "\\(acción, comedia, drama…\\) o por idioma \\(VOSE, castellano, català…\\) "
        "y te aviso únicamente cuando llegue algo que encaje.\n\n"
        "¡Nos vemos en la butaca! 🍿"
    )

    start_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Configurar mis alertas", callback_data="open_alertas")],
    ])

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=start_keyboard)
    logger.info("Sent /start response to user %s (id=%s)", first_name, update.effective_user.id)


# ── Constantes para los filtros disponibles ──────────────────────────

FORMAT_OPTIONS: list[str] = ["VOSE", "CASTELLÀ", "CATALÀ"]
GENRE_OPTIONS: list[str] = ["Thriller", "Comedia", "Drama", "Terror", "Animació", "Aventura"]


def _build_alerts_keyboard(active_filters: set[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    """Build the inline keyboard for /alertas with format and genre toggles.

    Active filters are shown with a ✅ prefix.
    Header buttons act as 'select all' toggles and show ✅ when every option in
    their category is active.
    """
    filters = active_filters or set()

    def _btn(filter_type: str, label: str) -> InlineKeyboardButton:
        prefix = "✅ " if (filter_type, label) in filters else ""
        return InlineKeyboardButton(f"{prefix}{label}", callback_data=f"sub:{filter_type}:{label}")

    format_buttons = [_btn("format_type", v) for v in FORMAT_OPTIONS]
    genre_buttons = [_btn("genre", v) for v in GENRE_OPTIONS]

    all_formats_active = all(("format_type", v) in filters for v in FORMAT_OPTIONS)
    idioma_prefix = "✅ " if all_formats_active else ""

    all_genres_active = all(("genre", v) in filters for v in GENRE_OPTIONS)
    genre_prefix = "✅ " if all_genres_active else ""

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{idioma_prefix}💬 Idioma", callback_data="all:format_type")],
        format_buttons,
        [InlineKeyboardButton(f"{genre_prefix}🎭 Género", callback_data="all:genre")],
        genre_buttons[:3],
        genre_buttons[3:],
    ])


ALERTS_TEXT = (
    "🔔 *Mis alertas personalizadas*\n\n"
    "Selecciona lo que te interesa y te avisaré "
    "cuando llegue una película que encaje.\n\n"
    "_Toca un botón para activar/desactivar._"
)


async def alertas_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /alertas command: show subscription inline keyboard."""
    if update.message is None or update.effective_user is None:
        return

    active = db.get_user_filters(update.effective_user.id)
    keyboard = _build_alerts_keyboard(active)
    await update.message.reply_text(
        ALERTS_TEXT,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    logger.info("Sent /alertas keyboard to user id=%s", update.effective_user.id)


async def open_alertas_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the 'open_alertas' button from /start: replace the welcome message with the alerts keyboard."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await query.answer()

    active = db.get_user_filters(update.effective_user.id)
    keyboard = _build_alerts_keyboard(active)
    await query.edit_message_text(
        ALERTS_TEXT,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    logger.info("Opened alertas keyboard for user id=%s", update.effective_user.id)


async def subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle sub:* buttons: toggle the subscription filter and refresh the keyboard."""
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return

    # callback_data format: "sub:{filter_type}:{filter_value}"
    parts = query.data.split(":", 2)
    if len(parts) != 3:
        await query.answer("Error: formato de callback inválido")
        return

    _, filter_type, filter_value = parts
    telegram_id = update.effective_user.id

    now_active = db.toggle_filter(telegram_id, filter_type, filter_value)
    status = "activada" if now_active else "desactivada"
    await query.answer(f"{filter_value} {status}")

    # Re-render the keyboard with updated checks
    active = db.get_user_filters(telegram_id)
    keyboard = _build_alerts_keyboard(active)
    await query.edit_message_reply_markup(reply_markup=keyboard)
    logger.info(
        "User id=%s toggled %s:%s -> %s",
        telegram_id, filter_type, filter_value, status,
    )


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle header buttons that do nothing."""
    query = update.callback_query
    if query is not None:
        await query.answer()


async def toggle_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all:* buttons: select or deselect all values for a filter type."""
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return

    # callback_data format: "all:{filter_type}"
    _, filter_type = query.data.split(":", 1)
    telegram_id = update.effective_user.id

    # Determine which values belong to this filter type
    options_map: dict[str, list[str]] = {
        "format_type": FORMAT_OPTIONS,
        "genre": GENRE_OPTIONS,
    }
    values = options_map.get(filter_type, [])
    if not values:
        await query.answer("Error: tipo de filtro desconocido")
        return

    active = db.get_user_filters(telegram_id)
    all_active = all((filter_type, v) in active for v in values)

    if all_active:
        db.remove_all_filters(telegram_id, filter_type)
        await query.answer("Todos los idiomas desactivados")
    else:
        db.set_all_filters(telegram_id, filter_type, values)
        await query.answer("Todos los idiomas activados")

    active = db.get_user_filters(telegram_id)
    keyboard = _build_alerts_keyboard(active)
    await query.edit_message_reply_markup(reply_markup=keyboard)
    logger.info("User id=%s toggled all %s -> %s", telegram_id, filter_type, "off" if all_active else "on")


def build_application(config: BotConfig) -> Application:
    """Build and configure the Telegram Application with all registered handlers."""
    app = Application.builder().token(config.token).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("alertas", alertas_handler))
    app.add_handler(CallbackQueryHandler(open_alertas_callback, pattern="^open_alertas$"))
    app.add_handler(CallbackQueryHandler(toggle_all_callback, pattern=r"^all:"))
    app.add_handler(CallbackQueryHandler(subscription_callback, pattern=r"^sub:"))
    app.add_handler(CallbackQueryHandler(noop_callback, pattern="^noop$"))
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
