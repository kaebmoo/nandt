"""
Keyboard utilities for Telegram Bot
Provides inline keyboards and reply keyboards
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from typing import List, Dict, Any
from datetime import datetime, timedelta


def create_service_keyboard(event_types: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """
    Create inline keyboard for service selection

    Args:
        event_types: List of event types from API

    Returns:
        InlineKeyboardMarkup with service buttons
    """
    keyboard = []

    for event_type in event_types:
        button_text = f"📋 {event_type['name']}"
        callback_data = f"service_{event_type['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    # Add cancel button
    keyboard.append([InlineKeyboardButton("❌ ยกเลิก", callback_data="cancel")])

    return InlineKeyboardMarkup(keyboard)


def create_date_keyboard(days_ahead: int = 7) -> InlineKeyboardMarkup:
    """
    Create inline keyboard for date selection

    Args:
        days_ahead: Number of days to show (default 7)

    Returns:
        InlineKeyboardMarkup with date buttons
    """
    keyboard = []
    today = datetime.now().date()

    # Create buttons for next N days
    for i in range(days_ahead):
        date = today + timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")

        # Format display text
        if i == 0:
            display = f"📅 วันนี้ ({date.strftime('%d/%m')})"
        elif i == 1:
            display = f"📅 พรุ่งนี้ ({date.strftime('%d/%m')})"
        else:
            # Show Thai weekday names
            weekdays_th = ["จ", "อ", "พ", "พฤ", "ศ", "ส", "อา"]
            weekday = weekdays_th[date.weekday()]
            display = f"📅 {weekday} {date.strftime('%d/%m')}"

        callback_data = f"date_{date_str}"
        keyboard.append([InlineKeyboardButton(display, callback_data=callback_data)])

    # Add navigation buttons
    keyboard.append([
        InlineKeyboardButton("⬅️ ย้อนกลับ", callback_data="back"),
        InlineKeyboardButton("❌ ยกเลิก", callback_data="cancel")
    ])

    return InlineKeyboardMarkup(keyboard)


def create_time_slots_keyboard(time_slots: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """
    Create inline keyboard for time slot selection

    Args:
        time_slots: List of available time slots from API

    Returns:
        InlineKeyboardMarkup with time slot buttons
    """
    keyboard = []

    if not time_slots:
        # No available slots
        keyboard.append([InlineKeyboardButton("❌ ไม่มีเวลาว่าง", callback_data="no_slots")])
    else:
        # Group time slots in rows of 2
        row = []
        for i, slot in enumerate(time_slots):
            time_str = slot.get("time", slot.get("start_time", ""))
            provider_name = slot.get("provider_name", "")

            # Format button text
            if provider_name:
                button_text = f"🕐 {time_str}\n👨‍⚕️ {provider_name}"
            else:
                button_text = f"🕐 {time_str}"

            callback_data = f"time_{time_str}"
            if slot.get("provider_id"):
                callback_data += f"_p{slot['provider_id']}"

            row.append(InlineKeyboardButton(button_text, callback_data=callback_data))

            # Add row every 2 buttons or at the end
            if len(row) == 2 or i == len(time_slots) - 1:
                keyboard.append(row)
                row = []

    # Add navigation buttons
    keyboard.append([
        InlineKeyboardButton("⬅️ เลือกวันใหม่", callback_data="back_to_date"),
        InlineKeyboardButton("❌ ยกเลิก", callback_data="cancel")
    ])

    return InlineKeyboardMarkup(keyboard)


def create_confirmation_keyboard() -> InlineKeyboardMarkup:
    """
    Create confirmation keyboard (Yes/No)

    Returns:
        InlineKeyboardMarkup with Yes/No buttons
    """
    keyboard = [
        [
            InlineKeyboardButton("✅ ยืนยัน", callback_data="confirm_yes"),
            InlineKeyboardButton("❌ ยกเลิก", callback_data="confirm_no")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_appointment_list_keyboard(appointments: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """
    Create inline keyboard for appointment list

    Args:
        appointments: List of user appointments

    Returns:
        InlineKeyboardMarkup with appointment buttons
    """
    keyboard = []

    for apt in appointments:
        # Format appointment info
        date_str = apt.get("date", apt.get("appointment_date", ""))
        time_str = apt.get("time", apt.get("appointment_time", ""))
        service = apt.get("event_type_name", apt.get("service_name", "Unknown"))
        reference = apt.get("booking_reference", apt.get("reference", ""))

        button_text = f"📅 {date_str} {time_str} - {service}"
        callback_data = f"apt_{reference}"

        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    # Add close button
    keyboard.append([InlineKeyboardButton("❌ ปิด", callback_data="close")])

    return InlineKeyboardMarkup(keyboard)


def create_appointment_actions_keyboard(booking_reference: str) -> InlineKeyboardMarkup:
    """
    Create keyboard for appointment actions (Reschedule/Cancel)

    Args:
        booking_reference: Booking reference number

    Returns:
        InlineKeyboardMarkup with action buttons
    """
    keyboard = [
        [InlineKeyboardButton("🔄 เลื่อนนัด", callback_data=f"reschedule_{booking_reference}")],
        [InlineKeyboardButton("❌ ยกเลิกนัด", callback_data=f"cancel_{booking_reference}")],
        [InlineKeyboardButton("⬅️ ย้อนกลับ", callback_data="back_to_list")]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_phone_request_keyboard() -> ReplyKeyboardMarkup:
    """
    Create reply keyboard for phone number request

    Returns:
        ReplyKeyboardMarkup with phone sharing button
    """
    keyboard = [
        [KeyboardButton("📱 แชร์เบอร์โทร", request_contact=True)],
        [KeyboardButton("❌ ยกเลิก")]
    ]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)


def create_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Create main menu reply keyboard

    Returns:
        ReplyKeyboardMarkup with main menu options
    """
    keyboard = [
        [KeyboardButton("📅 จองนัด"), KeyboardButton("📋 นัดหมายของฉัน")],
        [KeyboardButton("ℹ️ ช่วยเหลือ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
