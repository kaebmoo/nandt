# forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, DateField, TimeField, TextAreaField, SelectField, BooleanField, IntegerField, HiddenField
from wtforms.validators import DataRequired, Optional, Length, ValidationError 
from wtforms.widgets import CheckboxInput, ListWidget
from wtforms.fields import SelectMultipleField


class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()

class AppointmentForm(FlaskForm):
    # Hidden field สำหรับป้องกันการส่งซ้ำ
    form_token = HiddenField()
    
    # ข้อมูลพื้นฐาน
    title = StringField('ชื่อผู้ป่วย', validators=[
        DataRequired(message='กรุณากรอกชื่อผู้ป่วย'),
        Length(min=2, max=200, message='ชื่อต้องมีความยาว 2-200 ตัวอักษร')
    ])
    
    calendar_name = SelectField('ปฏิทินย่อย', validators=[
        DataRequired(message='กรุณาเลือกปฏิทินย่อย')
    ])
    
    # วันที่และเวลา
    start_date = DateField('วันที่เริ่มต้น', validators=[
        DataRequired(message='กรุณาเลือกวันที่เริ่มต้น')
    ])
    
    start_time = TimeField('เวลาเริ่มต้น', validators=[
        DataRequired(message='กรุณาเลือกเวลาเริ่มต้น')
    ])
    
    end_date = DateField('วันที่สิ้นสุด', validators=[
        DataRequired(message='กรุณาเลือกวันที่สิ้นสุด')
    ])
    
    end_time = TimeField('เวลาสิ้นสุด', validators=[
        DataRequired(message='กรุณาเลือกเวลาสิ้นสุด')
    ])
    
    # ข้อมูลเสริม
    location = StringField('สถานที่', validators=[
        Optional(),
        Length(max=100, message='สถานที่ต้องไม่เกิน 100 ตัวอักษร')
    ])
    
    who = StringField('ผู้ดูแล', validators=[
        Optional(),
        Length(max=100, message='ชื่อผู้ดูแลต้องไม่เกิน 100 ตัวอักษร')
    ])
    
    description = TextAreaField('รายละเอียด', validators=[
        Optional(),
        Length(max=1000, message='รายละเอียดต้องไม่เกิน 1000 ตัวอักษร')
    ])
    
    # สำหรับ recurring appointments
    is_recurring = BooleanField('นัดหมายที่เกิดซ้ำ')
    
    # วันในสัปดาห์ (สำหรับ recurring)
    mon = BooleanField('จันทร์')
    tue = BooleanField('อังคาร')
    wed = BooleanField('พุธ')
    thu = BooleanField('พฤหัสบดี')
    fri = BooleanField('ศุกร์')
    sat = BooleanField('เสาร์')
    sun = BooleanField('อาทิตย์')
    
    weeks = IntegerField('จำนวนสัปดาห์', validators=[
        Optional()
    ], default=4)
    
    def validate_end_time(self, field):
        """ตรวจสอบว่าเวลาสิ้นสุดต้องมากกว่าเวลาเริ่มต้น"""
        if self.start_date.data and self.end_date.data and self.start_time.data and field.data:
            if self.start_date.data == self.end_date.data and field.data <= self.start_time.data:
                raise ValidationError('เวลาสิ้นสุดต้องมากกว่าเวลาเริ่มต้น')
    
    def validate_recurring_days(self):
        """ตรวจสอบว่าถ้าเป็น recurring ต้องเลือกวันในสัปดาห์"""
        if self.is_recurring.data:
            days = [self.mon.data, self.tue.data, self.wed.data, self.thu.data, 
                   self.fri.data, self.sat.data, self.sun.data]
            if not any(days):
                return False, 'กรุณาเลือกวันที่ต้องการให้เกิดซ้ำ'
            
            # ตรวจสอบว่าวันที่เลือกต้องตรงกับวันที่เริ่มต้น
            if self.start_date.data:
                start_weekday = self.start_date.data.weekday()  # 0=Monday, 6=Sunday
                day_mapping = [self.mon.data, self.tue.data, self.wed.data, self.thu.data, 
                              self.fri.data, self.sat.data, self.sun.data]
                
                if not day_mapping[start_weekday]:
                    weekday_names = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์']
                    return False, f'วันที่เริ่มต้นเป็นวัน{weekday_names[start_weekday]} กรุณาเลือกวัน{weekday_names[start_weekday]}ในการเกิดซ้ำด้วย'
        return True, None