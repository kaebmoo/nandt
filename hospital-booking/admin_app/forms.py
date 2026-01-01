"""
WTForms for Super Admin application
Forms for tenant management
"""

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Email, Length, Regexp, Optional

class HospitalForm(FlaskForm):
    """Form for creating/editing hospital (tenant)"""

    name = StringField(
        'ชื่อผู้ให้บริการ',
        validators=[
            DataRequired(message='กรุณากรอกชื่อผู้ให้บริการ'),
            Length(max=100, message='ชื่อผู้ให้บริการต้องไม่เกิน 100 ตัวอักษร')
        ],
        render_kw={"placeholder": "เช่น โรงพยาบาลหมอนนุ่ม"}
    )

    subdomain = StringField(
        'Subdomain',
        validators=[
            DataRequired(message='กรุณากรอก subdomain'),
            Length(max=50, message='subdomain ต้องไม่เกิน 50 ตัวอักษร'),
            Regexp(
                r'^[a-z0-9-]+$',
                message='subdomain ต้องเป็นตัวอักษรภาษาอังกฤษพิมพ์เล็ก ตัวเลข และ - เท่านั้น'
            )
        ],
        render_kw={
            "placeholder": "เช่น khunnoi",
            "pattern": "[a-z0-9-]+",
            "title": "ใช้ตัวอักษรภาษาอังกฤษพิมพ์เล็ก ตัวเลข และ - เท่านั้น"
        }
    )

    address = TextAreaField(
        'ที่อยู่',
        validators=[Optional()],
        render_kw={"placeholder": "ที่อยู่ผู้ให้บริการ", "rows": 3}
    )

    phone = StringField(
        'เบอร์โทรศัพท์',
        validators=[
            Optional(),
            Length(max=20, message='เบอร์โทรศัพท์ต้องไม่เกิน 20 ตัวอักษร')
        ],
        render_kw={"placeholder": "เช่น 02-123-4567"}
    )

    email = StringField(
        'อีเมล',
        validators=[
            Optional(),
            Email(message='รูปแบบอีเมลไม่ถูกต้อง'),
            Length(max=120, message='อีเมลต้องไม่เกิน 120 ตัวอักษร')
        ],
        render_kw={"placeholder": "email@example.com"}
    )

    description = TextAreaField(
        'รายละเอียด',
        validators=[Optional()],
        render_kw={"placeholder": "รายละเอียดเพิ่มเติมเกี่ยวกับผู้ให้บริการ", "rows": 4}
    )

    submit = SubmitField('บันทึก')
