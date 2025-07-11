# forms.py - เวอร์ชันปรับปรุง
from flask_wtf import FlaskForm
from wtforms import StringField, DateField, TimeField, TextAreaField, SelectField, BooleanField, IntegerField, HiddenField
from wtforms.validators import DataRequired, Optional, Length, ValidationError 
from wtforms.widgets import CheckboxInput, ListWidget
from wtforms.fields import SelectMultipleField
from datetime import datetime, timedelta


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
    
    who = StringField('เจ้าหน้าที่/ผู้ดูแล', validators=[
        Optional(),
        Length(max=100, message='ชื่อเจ้าหน้าที่ต้องไม่เกิน 100 ตัวอักษร')
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
    
    # **เพิ่ม validation methods ที่ขาดหายไป**
    
    def validate_start_date(self, field):
        """ตรวจสอบว่าวันที่เริ่มต้นไม่เป็นวันที่ในอดีต"""
        if field.data:
            today = datetime.now().date()
            if field.data < today:
                raise ValidationError('วันที่เริ่มต้นต้องเป็นวันนี้หรือวันในอนาคต')
    
    def validate_end_date(self, field):
        """ตรวจสอบว่าวันที่สิ้นสุดไม่เป็นวันก่อนวันที่เริ่มต้น"""
        if self.start_date.data and field.data:
            if field.data < self.start_date.data:
                raise ValidationError('วันที่สิ้นสุดต้องเป็นวันเดียวกันหรือหลังจากวันที่เริ่มต้น')
            
            # ตรวจสอบว่าไม่เกิน 1 ปี
            if (field.data - self.start_date.data).days > 365:
                raise ValidationError('ระยะเวลานัดหมายไม่ควรเกิน 1 ปี')
    
    def validate_end_time(self, field):
        """ตรวจสอบว่าเวลาสิ้นสุดถูกต้อง"""
        if self.start_date.data and self.end_date.data and self.start_time.data and field.data:
            # สร้าง datetime objects เพื่อเปรียบเทียบ
            start_datetime = datetime.combine(self.start_date.data, self.start_time.data)
            end_datetime = datetime.combine(self.end_date.data, field.data)
            
            # ตรวจสอบว่า end_datetime หลัง start_datetime
            if end_datetime <= start_datetime:
                raise ValidationError('เวลาสิ้นสุดต้องหลังจากเวลาเริ่มต้นอย่างน้อย 15 นาที')
            
            # ตรวจสอบว่าไม่เกิน 24 ชั่วโมง
            duration = end_datetime - start_datetime
            if duration.total_seconds() > (24 * 60 * 60):  # 24 ชั่วโมง
                raise ValidationError('ระยะเวลานัดหมายไม่ควรเกิน 24 ชั่วโมง')
            
            # ตรวจสอบว่าอย่างน้อย 15 นาที
            if duration.total_seconds() < (15 * 60):  # 15 นาที
                raise ValidationError('ระยะเวลานัดหมายต้องอย่างน้อย 15 นาที')
    
    def validate_weeks(self, field):
        """ตรวจสอบจำนวนสัปดาห์สำหรับ recurring appointments"""
        if self.is_recurring.data and field.data:
            if field.data < 1 or field.data > 52:
                raise ValidationError('จำนวนสัปดาห์ต้องอยู่ระหว่าง 1-52 สัปดาห์')
    
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
    
    # **เพิ่ม method สำหรับ auto-correct และ validation รวม**
    def get_validated_datetime_data(self):
        """
        ส่งคืนข้อมูล datetime ที่ validated และแก้ไขแล้ว
        ใช้สำหรับส่งข้อมูลไปยัง TeamUp API
        """
        if not all([self.start_date.data, self.start_time.data, self.end_date.data, self.end_time.data]):
            raise ValidationError('ข้อมูลวันที่และเวลาไม่ครบถ้วน')

        start_datetime = datetime.combine(self.start_date.data, self.start_time.data)
        end_datetime = datetime.combine(self.end_date.data, self.end_time.data)
        
        # **Auto-correct logic: ถ้า end_datetime <= start_datetime ให้แก้ไขอัตโนมัติ**
        if end_datetime <= start_datetime:
            # เพิ่ม 1 ชั่วโมงจาก start_datetime
            end_datetime = start_datetime + timedelta(hours=1)
            # อัปเดตค่าใน form fields
            self.end_date.data = end_datetime.date()
            self.end_time.data = end_datetime.time()
        
        return {
            'start_date': start_datetime.date().strftime('%Y-%m-%d'),
            'start_time': start_datetime.time().strftime('%H:%M'),
            'end_date': end_datetime.date().strftime('%Y-%m-%d'),
            'end_time': end_datetime.time().strftime('%H:%M'),
            'start_datetime': start_datetime,
            'end_datetime': end_datetime,
            'start_dt_iso': start_datetime.isoformat(),
            'end_dt_iso': end_datetime.isoformat()
        }
    
    def validate_appointment_logic(self):
        """
        ตรวจสอบ logic ทั้งหมดของ appointment
        เรียกใช้หลังจาก validate_on_submit() ผ่านแล้ว
        """
        errors = []
        
        # ตรวจสอบ recurring logic
        if self.is_recurring.data:
            is_valid, error_msg = self.validate_recurring_days()
            if not is_valid:
                errors.append(error_msg)
        
        # ตรวจสอบเวลาทำงาน (ไม่ควรเป็นเวลากลางคืน)
        if self.start_time.data and self.end_time.data:
            # ตัวอย่าง: เตือนถ้าเป็นเวลา 22:00-06:00
            if (self.start_time.data.hour >= 22 or self.start_time.data.hour < 6 or
                self.end_time.data.hour >= 22 or self.end_time.data.hour < 6):
                errors.append('คำเตือน: นัดหมายในช่วงเวลากลางคืน (22:00-06:00)')
        
        return len(errors) == 0, errors
    
    def to_dict(self):
        """แปลง form data เป็น dictionary สำหรับส่งไปยัง API"""
        try:
            datetime_data = self.get_validated_datetime_data()
            
            return {
                'title': self.title.data,
                'calendar_name': self.calendar_name.data,
                'start_date': datetime_data['start_date'],
                'start_time': datetime_data['start_time'],
                'end_date': datetime_data['end_date'],
                'end_time': datetime_data['end_time'],
                'start_dt': datetime_data['start_dt_iso'],
                'end_dt': datetime_data['end_dt_iso'],
                'location': self.location.data or '',
                'who': self.who.data or '',
                'description': self.description.data or '',
                'is_recurring': self.is_recurring.data,
                'weeks': self.weeks.data if self.is_recurring.data else None,
                'recurring_days': {
                    'mon': self.mon.data,
                    'tue': self.tue.data,
                    'wed': self.wed.data,
                    'thu': self.thu.data,
                    'fri': self.fri.data,
                    'sat': self.sat.data,
                    'sun': self.sun.data
                } if self.is_recurring.data else None,
                'form_token': self.form_token.data
            }
        except Exception as e:
            raise ValidationError(f'Error converting form data: {str(e)}')