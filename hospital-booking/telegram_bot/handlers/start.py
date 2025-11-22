"""
Start handler and user registration flow
Handles /start command and new user registration
"""
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters
)
from services.auth import UserAuth
from utils.keyboards import create_phone_request_keyboard, create_main_menu_keyboard
from utils.validators import validate_phone, validate_name
from config import Config
import logging

logger = logging.getLogger(__name__)

# Conversation states
REGISTRATION_NAME, REGISTRATION_PHONE = range(2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle /start command

    Checks if user is registered:
    - If yes: Show main menu
    - If no: Start registration flow
    """
    user = update.effective_user
    auth: UserAuth = context.bot_data['auth']

    # Check if user is already registered
    if auth.is_registered(user.id):
        user_data = auth.get_user(user.id)
        await update.message.reply_text(
            f"ยินดีต้อนรับกลับมา คุณ{user_data['name']}! 👋\n\n"
            "เลือกเมนูด้านล่างเพื่อใช้งาน:",
            reply_markup=create_main_menu_keyboard()
        )
        return ConversationHandler.END

    # New user - start registration
    await update.message.reply_text(
        Config.Messages.WELCOME,
        reply_markup=ReplyKeyboardRemove()
    )

    await update.message.reply_text(
        Config.Messages.REGISTRATION_START
    )

    return REGISTRATION_NAME


async def registration_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle user name input during registration
    """
    name = update.message.text.strip()

    # Validate name
    is_valid, cleaned_name = validate_name(name)

    if not is_valid:
        await update.message.reply_text(
            "❌ กรุณาระบุชื่อที่ถูกต้อง (ความยาว 2-100 ตัวอักษร)\n\n"
            "กรุณาพิมพ์ชื่อ-นามสกุลของคุณอีกครั้ง:"
        )
        return REGISTRATION_NAME

    # Store name in context
    context.user_data['registration_name'] = cleaned_name

    # Request phone number
    await update.message.reply_text(
        f"ขอบคุณครับ คุณ{cleaned_name}\n\n" + Config.Messages.REGISTRATION_PHONE,
        reply_markup=create_phone_request_keyboard()
    )

    return REGISTRATION_PHONE


async def registration_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle phone number input during registration

    Accepts both:
    1. Shared contact (from button)
    2. Text input
    """
    user = update.effective_user
    auth: UserAuth = context.bot_data['auth']

    phone = None

    # Check if user shared contact
    if update.message.contact:
        phone = update.message.contact.phone_number
    # Check if user typed phone number
    elif update.message.text and update.message.text != "❌ ยกเลิก":
        phone = update.message.text.strip()
    # Handle cancellation
    elif update.message.text == "❌ ยกเลิก":
        await update.message.reply_text(
            Config.Messages.CANCEL_OPERATION,
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # Validate phone
    if phone:
        is_valid, normalized_phone = validate_phone(phone)

        if not is_valid:
            await update.message.reply_text(
                "❌ กรุณาระบุเบอร์โทรศัพท์ที่ถูกต้อง\n\n"
                "รูปแบบ: 0812345678 หรือ +66812345678\n\n"
                "กรุณาลองใหม่อีกครั้ง:",
                reply_markup=create_phone_request_keyboard()
            )
            return REGISTRATION_PHONE

        # Register user
        name = context.user_data.get('registration_name')

        try:
            auth.register_user(
                telegram_id=user.id,
                name=name,
                phone=normalized_phone,
                username=user.username
            )

            logger.info(f"New user registered: {user.id} - {name} - {normalized_phone}")

            await update.message.reply_text(
                f"✅ ลงทะเบียนสำเร็จ!\n\n"
                f"👤 ชื่อ: {name}\n"
                f"📱 เบอร์โทร: {normalized_phone}\n\n"
                f"คุณสามารถเริ่มใช้งานระบบได้แล้ว",
                reply_markup=create_main_menu_keyboard()
            )

            # Clear registration data
            context.user_data.clear()

            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Registration error: {e}")
            await update.message.reply_text(
                Config.Messages.ERROR_GENERIC,
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END

    # If no phone received
    await update.message.reply_text(
        "❌ ไม่สามารถรับข้อมูลเบอร์โทรได้\n\nกรุณาลองใหม่อีกครั้ง:",
        reply_markup=create_phone_request_keyboard()
    )
    return REGISTRATION_PHONE


async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle /cancel command during registration
    """
    await update.message.reply_text(
        Config.Messages.CANCEL_OPERATION,
        reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END


# Create the conversation handler
def get_start_handler() -> ConversationHandler:
    """
    Create and return the start/registration conversation handler

    Returns:
        ConversationHandler for start command
    """
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REGISTRATION_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registration_name)
            ],
            REGISTRATION_PHONE: [
                MessageHandler(
                    (filters.TEXT | filters.CONTACT) & ~filters.COMMAND,
                    registration_phone
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_registration)
        ],
    )
