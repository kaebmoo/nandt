"""
Unit tests for input validators
Run with: pytest tests/test_validators.py -v
"""
import pytest
from utils.validators import (
    validate_phone,
    validate_email,
    validate_date,
    validate_time,
    validate_name,
    format_phone_display,
    format_date_display,
    format_time_display
)
from datetime import datetime


class TestPhoneValidation:
    """Test phone number validation"""

    def test_valid_thai_phone_10_digits(self):
        """Test valid 10-digit Thai phone"""
        is_valid, normalized = validate_phone("0812345678")
        assert is_valid is True
        assert normalized == "0812345678"

    def test_valid_phone_with_country_code_plus(self):
        """Test phone with +66 country code"""
        is_valid, normalized = validate_phone("+66812345678")
        assert is_valid is True
        assert normalized == "0812345678"

    def test_valid_phone_with_country_code_no_plus(self):
        """Test phone with 66 country code (no +)"""
        is_valid, normalized = validate_phone("66812345678")
        assert is_valid is True
        assert normalized == "0812345678"

    def test_phone_with_spaces(self):
        """Test phone with spaces"""
        is_valid, normalized = validate_phone("081 234 5678")
        assert is_valid is True
        assert normalized == "0812345678"

    def test_phone_with_dashes(self):
        """Test phone with dashes"""
        is_valid, normalized = validate_phone("081-234-5678")
        assert is_valid is True
        assert normalized == "0812345678"

    def test_invalid_phone_too_short(self):
        """Test invalid phone - too short"""
        is_valid, normalized = validate_phone("081234567")
        assert is_valid is False
        assert normalized is None

    def test_invalid_phone_too_long(self):
        """Test invalid phone - too long"""
        is_valid, normalized = validate_phone("08123456789")
        assert is_valid is False
        assert normalized is None

    def test_invalid_phone_wrong_format(self):
        """Test invalid phone - wrong format"""
        is_valid, normalized = validate_phone("1234567890")
        assert is_valid is False
        assert normalized is None


class TestEmailValidation:
    """Test email validation"""

    def test_valid_email(self):
        """Test valid email addresses"""
        assert validate_email("test@example.com") is True
        assert validate_email("user.name@domain.co.th") is True
        assert validate_email("user+tag@example.com") is True

    def test_invalid_email_no_at(self):
        """Test invalid email - no @ symbol"""
        assert validate_email("testexample.com") is False

    def test_invalid_email_no_domain(self):
        """Test invalid email - no domain"""
        assert validate_email("test@") is False

    def test_invalid_email_no_extension(self):
        """Test invalid email - no extension"""
        assert validate_email("test@example") is False


class TestDateValidation:
    """Test date validation"""

    def test_valid_future_date(self):
        """Test valid future date"""
        future_date = "2025-12-31"
        is_valid, date_obj = validate_date(future_date)
        assert is_valid is True
        assert date_obj is not None

    def test_invalid_date_format(self):
        """Test invalid date format"""
        is_valid, date_obj = validate_date("31/12/2025")
        assert is_valid is False
        assert date_obj is None

    def test_invalid_date_string(self):
        """Test invalid date string"""
        is_valid, date_obj = validate_date("not-a-date")
        assert is_valid is False
        assert date_obj is None


class TestTimeValidation:
    """Test time validation"""

    def test_valid_time(self):
        """Test valid time formats"""
        is_valid, normalized = validate_time("09:00")
        assert is_valid is True
        assert normalized == "09:00"

        is_valid, normalized = validate_time("14:30")
        assert is_valid is True
        assert normalized == "14:30"

    def test_invalid_time_format(self):
        """Test invalid time format"""
        is_valid, normalized = validate_time("9:00")  # Missing leading zero
        assert is_valid is False
        assert normalized is None

    def test_invalid_time_hour(self):
        """Test invalid time - hour out of range"""
        is_valid, normalized = validate_time("25:00")
        assert is_valid is False
        assert normalized is None


class TestNameValidation:
    """Test name validation"""

    def test_valid_thai_name(self):
        """Test valid Thai name"""
        is_valid, cleaned = validate_name("สมชาย ใจดี")
        assert is_valid is True
        assert cleaned == "สมชาย ใจดี"

    def test_valid_english_name(self):
        """Test valid English name"""
        is_valid, cleaned = validate_name("John Doe")
        assert is_valid is True
        assert cleaned == "John Doe"

    def test_valid_mixed_name(self):
        """Test valid mixed Thai-English name"""
        is_valid, cleaned = validate_name("สมชาย Smith")
        assert is_valid is True
        assert cleaned == "สมชาย Smith"

    def test_name_with_extra_spaces(self):
        """Test name with extra spaces"""
        is_valid, cleaned = validate_name("สมชาย   ใจดี")
        assert is_valid is True
        assert cleaned == "สมชาย ใจดี"

    def test_invalid_name_too_short(self):
        """Test invalid name - too short"""
        is_valid, cleaned = validate_name("A")
        assert is_valid is False
        assert cleaned is None

    def test_invalid_name_with_numbers(self):
        """Test invalid name - contains numbers"""
        is_valid, cleaned = validate_name("สมชาย123")
        assert is_valid is False
        assert cleaned is None


class TestFormatters:
    """Test display formatters"""

    def test_format_phone_display(self):
        """Test phone number formatting"""
        formatted = format_phone_display("0812345678")
        assert formatted == "081-234-5678"

    def test_format_date_display_thai(self):
        """Test date formatting in Thai"""
        formatted = format_date_display("2025-11-22", lang="th")
        assert "พฤศจิกายน" in formatted
        assert "2568" in formatted  # BE year

    def test_format_date_display_english(self):
        """Test date formatting in English"""
        formatted = format_date_display("2025-11-22", lang="en")
        assert "November" in formatted
        assert "2025" in formatted

    def test_format_time_display(self):
        """Test time formatting"""
        formatted = format_time_display("14:30")
        assert formatted == "14:30 น."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
