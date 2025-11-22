"""
Main Telegram Bot Application
Hospital Booking Bot - Entry Point
"""
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Import config and services
from config import Config
from services.api_client import HospitalBookingAPI
from services.auth import UserAuth

# Import handlers
from handlers.start import get_start_handler
from handlers.booking import get_booking_handler
from handlers.search import register_search_handlers

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, Config.LOG_LEVEL)
)
logger = logging.getLogger(__name__)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /help command
    Show available commands
    """
    help_text = """
🏥 <b>คำสั่งที่ใช้งานได้:</b>

/start - เริ่มต้นใช้งาน / ลงทะเบียน
/book - จองนัดหมาย
/myappointments - ดูนัดหมายของฉัน
/help - แสดงคำสั่งทั้งหมด
/cancel - ยกเลิกการทำงานปัจจุบัน

<b>หรือใช้เมนูด้านล่าง:</b>
📅 จองนัด - จองนัดหมายใหม่
📋 นัดหมายของฉัน - ดูนัดหมายที่จองไว้
ℹ️ ช่วยเหลือ - ดูคำสั่งทั้งหมด

<i>หากมีปัญหาการใช้งาน กรุณาติดต่อเจ้าหน้าที่</i>
"""
    await update.message.reply_text(help_text, parse_mode='HTML')


async def help_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle help button from main menu"""
    await help_command(update, context)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle errors in the bot
    """
    logger.error(f"Exception while handling an update: {context.error}")

    # Notify user if possible
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "❌ เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง\n\n"
            "หากปัญหายังคงอยู่ กรุณาใช้คำสั่ง /start เพื่อเริ่มต้นใหม่"
        )


async def post_init(application: Application) -> None:
    """
    Initialize bot_data after application is created
    """
    # Initialize API client
    api = HospitalBookingAPI(
        base_url=Config.FASTAPI_BASE_URL,
        subdomain=Config.DEFAULT_SUBDOMAIN
    )

    # Initialize auth service
    auth = UserAuth(redis_url=Config.REDIS_URL)

    # Store in bot_data for access in handlers
    application.bot_data['api'] = api
    application.bot_data['auth'] = auth

    logger.info("Bot initialized successfully")
    logger.info(f"FastAPI: {Config.FASTAPI_BASE_URL}")
    logger.info(f"Subdomain: {Config.DEFAULT_SUBDOMAIN}")


async def post_shutdown(application: Application) -> None:
    """
    Cleanup when bot shuts down
    """
    # Close API client
    api: HospitalBookingAPI = application.bot_data.get('api')
    if api:
        await api.close()

    logger.info("Bot shut down successfully")


def main() -> None:
    """
    Start the bot
    """
    logger.info("Starting Hospital Booking Telegram Bot...")

    # Create application
    application = (
        Application.builder()
        .token(Config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Register handlers

    # 1. Start/Registration handler (ConversationHandler)
    application.add_handler(get_start_handler())

    # 2. Booking handler (ConversationHandler)
    application.add_handler(get_booking_handler())

    # 3. Search/Appointments handlers
    register_search_handlers(application)

    # 4. Help command
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.Regex("^ℹ️ ช่วยเหลือ$"), help_button))

    # 5. Error handler
    application.add_error_handler(error_handler)

    # Start the bot
    logger.info("Bot is running. Press Ctrl+C to stop.")

    # Run the bot with polling
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True  # Ignore pending updates on startup
    )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
