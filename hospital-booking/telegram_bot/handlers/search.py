"""
Search and view appointments handler
Handles /myappointments command to view user's bookings
"""
from telegram import Update
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from services.auth import UserAuth
from services.api_client import HospitalBookingAPI, APIException
from utils.keyboards import (
    create_appointment_list_keyboard,
    create_appointment_actions_keyboard
)
from utils.validators import format_date_display, format_time_display
from config import Config
import logging

logger = logging.getLogger(__name__)


async def my_appointments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /myappointments command
    Show list of user's appointments
    """
    user = update.effective_user
    auth: UserAuth = context.bot_data['auth']
    api: HospitalBookingAPI = context.bot_data['api']

    # Check if user is registered
    if not auth.is_registered(user.id):
        await update.message.reply_text(
            "❌ คุณยังไม่ได้ลงทะเบียน\n\n"
            "กรุณาใช้คำสั่ง /start เพื่อลงทะเบียนก่อน"
        )
        return

    user_data = auth.get_user(user.id)
    phone = user_data.get('phone')

    if not phone:
        await update.message.reply_text(
            "❌ ไม่พบข้อมูลเบอร์โทรศัพท์\n\n"
            "กรุณาลงทะเบียนใหม่ด้วย /start"
        )
        return

    try:
        # Search appointments by phone
        appointments = await api.search_booking(phone=phone)

        if not appointments:
            await update.message.reply_text(Config.Messages.NO_APPOINTMENTS)
            return

        # Filter active appointments (not cancelled)
        active_appointments = [
            apt for apt in appointments
            if apt.get('status', '').lower() != 'cancelled'
        ]

        if not active_appointments:
            await update.message.reply_text(Config.Messages.NO_APPOINTMENTS)
            return

        # Show appointment list
        await update.message.reply_text(
            f"📋 นัดหมายของคุณ ({len(active_appointments)} รายการ):",
            reply_markup=create_appointment_list_keyboard(active_appointments)
        )

    except APIException as e:
        logger.error(f"Failed to fetch appointments: {e}")
        await update.message.reply_text(Config.Messages.ERROR_GENERIC)


async def appointment_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle appointment selection callback
    Show detailed appointment information
    """
    query = update.callback_query
    await query.answer()

    # Handle close
    if query.data == "close":
        await query.edit_message_text("ปิดแล้ว")
        return

    # Handle back to list
    if query.data == "back_to_list":
        user = update.effective_user
        auth: UserAuth = context.bot_data['auth']
        api: HospitalBookingAPI = context.bot_data['api']

        user_data = auth.get_user(user.id)
        phone = user_data.get('phone')

        try:
            appointments = await api.search_booking(phone=phone)
            active_appointments = [
                apt for apt in appointments
                if apt.get('status', '').lower() != 'cancelled'
            ]

            await query.edit_message_text(
                f"📋 นัดหมายของคุณ ({len(active_appointments)} รายการ):",
                reply_markup=create_appointment_list_keyboard(active_appointments)
            )
        except APIException:
            await query.edit_message_text(Config.Messages.ERROR_GENERIC)

        return

    # Extract booking reference from callback (format: apt_REF123)
    if query.data.startswith("apt_"):
        booking_reference = query.data.split('_', 1)[1]

        api: HospitalBookingAPI = context.bot_data['api']

        try:
            # Fetch appointment details
            appointment = await api.get_booking(booking_reference)

            # Format appointment details
            details_text = format_appointment_details(appointment)

            await query.edit_message_text(
                details_text,
                reply_markup=create_appointment_actions_keyboard(booking_reference),
                parse_mode='HTML'
            )

        except APIException as e:
            logger.error(f"Failed to fetch appointment details: {e}")
            await query.edit_message_text(Config.Messages.ERROR_GENERIC)

        return

    # Handle cancel appointment
    if query.data.startswith("cancel_"):
        booking_reference = query.data.split('_', 1)[1]

        # Ask for confirmation
        await query.edit_message_text(
            f"⚠️ ยืนยันการยกเลิกนัด?\n\n"
            f"รหัสการจอง: {booking_reference}\n\n"
            f"กดยืนยันเพื่อยกเลิกนัด",
            reply_markup={
                "inline_keyboard": [
                    [
                        {"text": "✅ ยืนยันยกเลิก", "callback_data": f"confirm_cancel_{booking_reference}"},
                        {"text": "❌ ไม่ยกเลิก", "callback_data": f"apt_{booking_reference}"}
                    ]
                ]
            }
        )

        return

    # Handle confirmed cancellation
    if query.data.startswith("confirm_cancel_"):
        booking_reference = query.data.split('_', 2)[2]

        api: HospitalBookingAPI = context.bot_data['api']

        try:
            await query.edit_message_text("⏳ กำลังยกเลิกนัด...")

            result = await api.cancel_booking(booking_reference)

            if result.get('success'):
                await query.edit_message_text(
                    f"✅ ยกเลิกนัดสำเร็จ\n\n"
                    f"รหัสการจอง: {booking_reference}\n\n"
                    f"หากต้องการจองใหม่ กรุณาใช้คำสั่ง /book"
                )

                logger.info(f"Appointment cancelled: {booking_reference}")

            else:
                await query.edit_message_text(
                    f"❌ ไม่สามารถยกเลิกนัดได้\n\n"
                    f"เหตุผล: {result.get('message', 'Unknown error')}"
                )

        except APIException as e:
            logger.error(f"Cancel failed: {e}")
            await query.edit_message_text(Config.Messages.ERROR_GENERIC)

        return

    # Handle reschedule (simplified - just message for MVP)
    if query.data.startswith("reschedule_"):
        booking_reference = query.data.split('_', 1)[1]

        await query.answer(
            "ฟีเจอร์การเลื่อนนัดกำลังอยู่ในระหว่างการพัฒนา\n"
            "กรุณายกเลิกนัดนี้และจองใหม่",
            show_alert=True
        )

        return


def format_appointment_details(appointment: dict) -> str:
    """
    Format appointment details for display

    Args:
        appointment: Appointment data from API

    Returns:
        Formatted HTML text
    """
    date = appointment.get('date', appointment.get('appointment_date', 'N/A'))
    time = appointment.get('time', appointment.get('appointment_time', 'N/A'))
    service = appointment.get('event_type_name', appointment.get('service_name', 'N/A'))
    provider = appointment.get('provider_name', 'ไม่ระบุ')
    location = appointment.get('location', 'ไม่ระบุ')
    status = appointment.get('status', 'confirmed')
    reference = appointment.get('booking_reference', appointment.get('reference', 'N/A'))
    notes = appointment.get('notes', '')

    # Format status
    status_emoji = {
        'confirmed': '✅',
        'pending': '⏳',
        'cancelled': '❌',
        'completed': '✔️'
    }
    status_display = f"{status_emoji.get(status, '📌')} {status.upper()}"

    text = f"""
<b>📋 รายละเอียดนัดหมาย</b>

🎫 รหัส: <code>{reference}</code>
{status_display}

📋 บริการ: {service}
📅 วันที่: {format_date_display(date)}
🕐 เวลา: {format_time_display(time)}
👨‍⚕️ แพทย์/พนักงาน: {provider}
📍 สถานที่: {location}
"""

    if notes:
        text += f"\n📝 หมายเหตุ: {notes}"

    return text.strip()


# Register handlers
def register_search_handlers(application) -> None:
    """
    Register all search/appointment handlers

    Args:
        application: Telegram Application instance
    """
    application.add_handler(CommandHandler("myappointments", my_appointments))
    application.add_handler(MessageHandler(filters.Regex("^📋 นัดหมายของฉัน$"), my_appointments))
    application.add_handler(CallbackQueryHandler(appointment_details))
