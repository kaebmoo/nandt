"""
Input validation utilities
Validates user input for phone, email, dates, etc.
"""
import re
from datetime import datetime
from typing import Optional, Tuple


def validate_phone(phone: str) -> Tuple[bool, Optional[str]]:
    """
    Validate Thai phone number

    Args:
        phone: Phone number string

    Returns:
        Tuple of (is_valid, normalized_phone)
    """
    # Remove spaces, dashes, and parentheses
    cleaned = re.sub(r'[\s\-\(\)]', '', phone)

    # Thai phone patterns:
    # - 10 digits starting with 0
    # - With or without country code (+66 or 66)

    # Pattern 1: 0XXXXXXXXX (10 digits)
    if re.match(r'^0\d{9}$', cleaned):
        return True, cleaned

    # Pattern 2: +66XXXXXXXXX (country code + 9 digits)
    if re.match(r'^\+66\d{9}$', cleaned):
        # Convert to local format
        return True, '0' + cleaned[3:]

    # Pattern 3: 66XXXXXXXXX (country code + 9 digits, no +)
    if re.match(r'^66\d{9}$', cleaned):
        return True, '0' + cleaned[2:]

    return False, None


def validate_email(email: str) -> bool:
    """
    Validate email address

    Args:
        email: Email string

    Returns:
        True if valid
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_date(date_str: str) -> Tuple[bool, Optional[datetime]]:
    """
    Validate date string in YYYY-MM-DD format

    Args:
        date_str: Date string

    Returns:
        Tuple of (is_valid, datetime_object)
    """
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        # Check if date is not in the past
        if date_obj.date() < datetime.now().date():
            return False, None
        return True, date_obj
    except ValueError:
        return False, None


def validate_time(time_str: str) -> Tuple[bool, Optional[str]]:
    """
    Validate time string in HH:MM format

    Args:
        time_str: Time string

    Returns:
        Tuple of (is_valid, normalized_time)
    """
    try:
        time_obj = datetime.strptime(time_str, '%H:%M')
        return True, time_obj.strftime('%H:%M')
    except ValueError:
        return False, None


def validate_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate name input

    Args:
        name: Name string

    Returns:
        Tuple of (is_valid, cleaned_name)
    """
    # Remove extra whitespace
    cleaned = ' '.join(name.split())

    # Check minimum length
    if len(cleaned) < 2:
        return False, None

    # Check maximum length
    if len(cleaned) > 100:
        return False, None

    # Allow Thai, English, and spaces
    # Thai Unicode range: \u0E00-\u0E7F
    if not re.match(r'^[\u0E00-\u0E7Fa-zA-Z\s]+$', cleaned):
        return False, None

    return True, cleaned


def format_phone_display(phone: str) -> str:
    """
    Format phone number for display

    Args:
        phone: Phone number (0XXXXXXXXX format)

    Returns:
        Formatted phone (0XX-XXX-XXXX)
    """
    if len(phone) == 10 and phone.startswith('0'):
        return f"{phone[:3]}-{phone[3:6]}-{phone[6:]}"
    return phone


def format_date_display(date_str: str, lang: str = 'th') -> str:
    """
    Format date for display

    Args:
        date_str: Date in YYYY-MM-DD format
        lang: Language ('th' or 'en')

    Returns:
        Formatted date string
    """
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')

        if lang == 'th':
            # Thai Buddhist year
            year_be = date_obj.year + 543
            months_th = [
                "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน",
                "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม",
                "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
            ]
            month_th = months_th[date_obj.month - 1]
            return f"{date_obj.day} {month_th} {year_be}"
        else:
            return date_obj.strftime('%d %B %Y')

    except ValueError:
        return date_str


def format_time_display(time_str: str) -> str:
    """
    Format time for display

    Args:
        time_str: Time in HH:MM format

    Returns:
        Formatted time string (HH:MM น.)
    """
    try:
        time_obj = datetime.strptime(time_str, '%H:%M')
        return f"{time_obj.strftime('%H:%M')} น."
    except ValueError:
        return time_str
