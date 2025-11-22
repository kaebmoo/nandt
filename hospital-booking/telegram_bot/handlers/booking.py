"""
Booking handler and conversation flow
Handles /book command and booking process
"""
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from services.auth import UserAuth
from services.api_client import HospitalBookingAPI, APIException
from utils.keyboards import (
    create_service_keyboard,
    create_date_keyboard,
    create_time_slots_keyboard,
    create_confirmation_keyboard
)
from utils.validators import format_date_display, format_time_display
from config import Config
import logging

logger = logging.getLogger(__name__)

# Conversation states
SELECTING_SERVICE, SELECTING_DATE, SELECTING_TIME, CONFIRMING = range(4)


async def book_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start booking process
    Check if user is registered, then show service selection
    """
    user = update.effective_user
    auth: UserAuth = context.bot_data['auth']

    # Check if user is registered
    if not auth.is_registered(user.id):
        await update.message.reply_text(
            "❌ คุณยังไม่ได้ลงทะเบียน\n\n"
            "กรุณาใช้คำสั่ง /start เพื่อลงทะเบียนก่อน"
        )
        return ConversationHandler.END

    # Get API client from bot_data
    api: HospitalBookingAPI = context.bot_data['api']

    try:
        # Fetch available services
        event_types = await api.get_active_event_types()

        if not event_types:
            await update.message.reply_text(
                "❌ ขณะนี้ยังไม่มีบริการให้จอง\n\n"
                "กรุณาลองใหม่ภายหลัง"
            )
            return ConversationHandler.END

        # Show service selection keyboard
        await update.message.reply_text(
            Config.Messages.BOOKING_SELECT_SERVICE,
            reply_markup=create_service_keyboard(event_types)
        )

        # Clear previous booking data
        context.user_data['booking'] = {}

        return SELECTING_SERVICE

    except APIException as e:
        logger.error(f"Failed to fetch event types: {e}")
        await update.message.reply_text(Config.Messages.ERROR_GENERIC)
        return ConversationHandler.END


async def service_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle service selection callback
    """
    query = update.callback_query
    await query.answer()

    # Handle cancel
    if query.data == "cancel":
        await query.edit_message_text(Config.Messages.CANCEL_OPERATION)
        context.user_data.clear()
        return ConversationHandler.END

    # Extract service ID from callback data (format: service_123)
    service_id = int(query.data.split('_')[1])

    # Store service ID
    context.user_data['booking']['service_id'] = service_id

    # Get service name for display
    api: HospitalBookingAPI = context.bot_data['api']
    try:
        event_type = await api.get_event_type(service_id)
        context.user_data['booking']['service_name'] = event_type['name']
        context.user_data['booking']['duration'] = event_type.get('duration_minutes', 30)
    except APIException:
        # Fallback if can't get details
        context.user_data['booking']['service_name'] = "Unknown Service"

    # Show date selection
    await query.edit_message_text(
        f"📋 บริการ: {context.user_data['booking']['service_name']}\n\n"
        + Config.Messages.BOOKING_SELECT_DATE,
        reply_markup=create_date_keyboard(days_ahead=7)
    )

    return SELECTING_DATE


async def date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle date selection callback
    """
    query = update.callback_query
    await query.answer()

    # Handle back to service selection
    if query.data == "back":
        api: HospitalBookingAPI = context.bot_data['api']
        try:
            event_types = await api.get_active_event_types()
            await query.edit_message_text(
                Config.Messages.BOOKING_SELECT_SERVICE,
                reply_markup=create_service_keyboard(event_types)
            )
            return SELECTING_SERVICE
        except APIException:
            await query.edit_message_text(Config.Messages.ERROR_GENERIC)
            return ConversationHandler.END

    # Handle cancel
    if query.data == "cancel":
        await query.edit_message_text(Config.Messages.CANCEL_OPERATION)
        context.user_data.clear()
        return ConversationHandler.END

    # Extract date from callback (format: date_2025-11-22)
    date_str = query.data.split('_', 1)[1]
    context.user_data['booking']['date'] = date_str

    # Fetch available time slots
    api: HospitalBookingAPI = context.bot_data['api']
    service_id = context.user_data['booking']['service_id']

    try:
        await query.edit_message_text("🔍 กำลังตรวจสอบเวลาว่าง...")

        time_slots = await api.get_availability(service_id, date_str)

        if not time_slots:
            await query.edit_message_text(
                f"❌ ไม่มีเวลาว่างในวันที่เลือก ({format_date_display(date_str)})\n\n"
                "กรุณาเลือกวันอื่น",
                reply_markup=create_date_keyboard()
            )
            return SELECTING_DATE

        # Show time slot selection
        await query.edit_message_text(
            f"📋 บริการ: {context.user_data['booking']['service_name']}\n"
            f"📅 วันที่: {format_date_display(date_str)}\n\n"
            + Config.Messages.BOOKING_SELECT_TIME,
            reply_markup=create_time_slots_keyboard(time_slots)
        )

        return SELECTING_TIME

    except APIException as e:
        logger.error(f"Failed to fetch availability: {e}")
        await query.edit_message_text(Config.Messages.ERROR_GENERIC)
        return ConversationHandler.END


async def time_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle time selection callback
    """
    query = update.callback_query
    await query.answer()

    # Handle back to date selection
    if query.data == "back_to_date":
        await query.edit_message_text(
            f"📋 บริการ: {context.user_data['booking']['service_name']}\n\n"
            + Config.Messages.BOOKING_SELECT_DATE,
            reply_markup=create_date_keyboard()
        )
        return SELECTING_DATE

    # Handle cancel
    if query.data == "cancel":
        await query.edit_message_text(Config.Messages.CANCEL_OPERATION)
        context.user_data.clear()
        return ConversationHandler.END

    # Handle no slots available
    if query.data == "no_slots":
        await query.answer("ไม่มีเวลาว่าง กรุณาเลือกวันอื่น")
        return SELECTING_TIME

    # Extract time and provider from callback (format: time_10:00_p123 or time_10:00)
    parts = query.data.split('_')
    time_str = parts[1]
    provider_id = None

    if len(parts) > 2 and parts[2].startswith('p'):
        provider_id = int(parts[2][1:])

    context.user_data['booking']['time'] = time_str
    context.user_data['booking']['provider_id'] = provider_id

    # Get user info for confirmation
    user = update.effective_user
    auth: UserAuth = context.bot_data['auth']
    user_data = auth.get_user(user.id)

    # Show confirmation
    booking = context.user_data['booking']
    confirmation_text = Config.Messages.BOOKING_CONFIRM.format(
        service=booking['service_name'],
        date=format_date_display(booking['date']),
        time=format_time_display(time_str),
        name=user_data['name'],
        phone=user_data['phone']
    )

    await query.edit_message_text(
        confirmation_text,
        reply_markup=create_confirmation_keyboard()
    )

    return CONFIRMING


async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle booking confirmation
    """
    query = update.callback_query
    await query.answer()

    # Handle cancellation
    if query.data == "confirm_no":
        await query.edit_message_text(Config.Messages.CANCEL_OPERATION)
        context.user_data.clear()
        return ConversationHandler.END

    # Handle confirmation
    if query.data == "confirm_yes":
        user = update.effective_user
        auth: UserAuth = context.bot_data['auth']
        api: HospitalBookingAPI = context.bot_data['api']

        user_data = auth.get_user(user.id)
        booking = context.user_data['booking']

        try:
            await query.edit_message_text("⏳ กำลังทำการจอง...")

            # Create booking via API
            result = await api.create_booking(
                event_type_id=booking['service_id'],
                date_str=booking['date'],
                time_str=booking['time'],
                guest_name=user_data['name'],
                guest_phone=user_data['phone'],
                provider_id=booking.get('provider_id')
            )

            if result.get('success'):
                # Success message
                success_text = Config.Messages.BOOKING_SUCCESS.format(
                    reference=result.get('booking_reference', 'N/A'),
                    service=result.get('event_type_name', booking['service_name']),
                    date=format_date_display(result.get('appointment_date', booking['date'])),
                    time=format_time_display(result.get('appointment_time', booking['time'])),
                    provider=result.get('provider_name', 'ไม่ระบุ'),
                    location=result.get('location', 'ไม่ระบุ')
                )

                await query.edit_message_text(success_text)

                logger.info(
                    f"Booking created: user={user.id}, "
                    f"reference={result.get('booking_reference')}"
                )

            else:
                await query.edit_message_text(
                    f"❌ ไม่สามารถจองได้\n\n"
                    f"เหตุผล: {result.get('message', 'Unknown error')}"
                )

        except APIException as e:
            logger.error(f"Booking failed: {e}")
            await query.edit_message_text(Config.Messages.ERROR_GENERIC)

        finally:
            context.user_data.clear()

        return ConversationHandler.END

    return CONFIRMING


async def cancel_booking_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle /cancel command during booking
    """
    await update.message.reply_text(Config.Messages.CANCEL_OPERATION)
    context.user_data.clear()
    return ConversationHandler.END


# Create the conversation handler
def get_booking_handler() -> ConversationHandler:
    """
    Create and return the booking conversation handler

    Returns:
        ConversationHandler for booking flow
    """
    return ConversationHandler(
        entry_points=[
            CommandHandler("book", book_start),
            MessageHandler(filters.Regex("^📅 จองนัด$"), book_start)
        ],
        states={
            SELECTING_SERVICE: [
                CallbackQueryHandler(service_selected)
            ],
            SELECTING_DATE: [
                CallbackQueryHandler(date_selected)
            ],
            SELECTING_TIME: [
                CallbackQueryHandler(time_selected)
            ],
            CONFIRMING: [
                CallbackQueryHandler(confirm_booking)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_booking_flow)
        ],
    )
