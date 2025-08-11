# flask_app/app/forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, TimeField, DateField, HiddenField
from wtforms.validators import DataRequired, Length, Optional, ValidationError
from wtforms.fields import FieldList, FormField
from datetime import datetime, time

class TimeSlotForm(FlaskForm):
    """Form สำหรับ time slot แต่ละช่วง"""
    start_time = TimeField('เวลาเริ่มต้น', validators=[DataRequired()])
    end_time = TimeField('เวลาสิ้นสุด', validators=[DataRequired()])
    
    def validate_end_time(self, field):
        if self.start_time.data and field.data:
            if field.data <= self.start_time.data:
                raise ValidationError('เวลาสิ้นสุดต้องมากกว่าเวลาเริ่มต้น')

class DayScheduleForm(FlaskForm):
    """Form สำหรับตารางของแต่ละวัน"""
    enabled = BooleanField('เปิดทำการ')
    slots = FieldList(FormField(TimeSlotForm), min_entries=0, max_entries=10)

class AvailabilityTemplateForm(FlaskForm):
    """Form หลักสำหรับสร้าง/แก้ไข availability template"""
    id = HiddenField()
    name = StringField(
        'ชื่อเทมเพลต', 
        validators=[DataRequired(message='กรุณาใส่ชื่อเทมเพลต'), Length(1, 100)]
    )
    description = TextAreaField(
        'คำอธิบาย', 
        validators=[Optional(), Length(0, 500)]
    )
    timezone = SelectField(
        'เขตเวลา', 
        choices=[('Asia/Bangkok', 'Asia/Bangkok (GMT+7)')], 
        default='Asia/Bangkok'
    )
    
    # Schedule สำหรับแต่ละวัน
    sunday = FormField(DayScheduleForm, label='อาทิตย์')
    monday = FormField(DayScheduleForm, label='จันทร์')
    tuesday = FormField(DayScheduleForm, label='อังคาร')
    wednesday = FormField(DayScheduleForm, label='พุธ')
    thursday = FormField(DayScheduleForm, label='พฤหัสบดี')
    friday = FormField(DayScheduleForm, label='ศุกร์')
    saturday = FormField(DayScheduleForm, label='เสาร์')
    
    
    # def __init__(self, *args, **kwargs):
    #    super().__init__(*args, **kwargs)
    #    # เพิ่ม default time slot ถ้ายังไม่มี
    #    for day_field in [self.sunday, self.monday, self.tuesday, self.wednesday, 
    #                     self.thursday, self.friday, self.saturday]:
    #        if len(day_field.slots.entries) == 0:
    #            day_field.slots.append_entry()
    
    def validate(self, extra_validators=None):
        """Validate ทั้งฟอร์ม"""
        if not super().validate():
            return False
        
        # ตรวจสอบว่าต้องมีอย่างน้อย 1 วันที่เปิดทำการ
        has_enabled_day = False
        for day_field in [self.sunday, self.monday, self.tuesday, self.wednesday, 
                         self.thursday, self.friday, self.saturday]:
            if day_field.enabled.data:
                has_enabled_day = True
                # ตรวจสอบว่าวันที่เปิดต้องมี time slots
                valid_slots = [slot for slot in day_field.slots.entries 
                             if slot.start_time.data and slot.end_time.data]
                if not valid_slots:
                    day_field.enabled.errors.append(f'วันที่เปิดทำการต้องมีช่วงเวลาอย่างน้อย 1 ช่วง')
                    return False
        
        if not has_enabled_day:
            self.name.errors.append('ต้องเปิดทำการอย่างน้อย 1 วัน')
            return False
        
        return True
    
    def get_schedule_data(self):
        """แปลงข้อมูลจาก form เป็น format ที่ API ต้องการ"""
        schedule = {}
        days = [self.sunday, self.monday, self.tuesday, self.wednesday, 
                self.thursday, self.friday, self.saturday]
        
        for day_index, day_field in enumerate(days):
            if day_field.enabled.data:
                schedule[day_index] = []
                for slot in day_field.slots.entries:
                    if slot.start_time.data and slot.end_time.data:
                        schedule[day_index].append([
                            slot.start_time.data.strftime('%H:%M'),
                            slot.end_time.data.strftime('%H:%M')
                        ])
        
        return {
            'name': self.name.data,
            'description': self.description.data or '',
            'timezone': self.timezone.data,
            'schedule': schedule
        }

class DateOverrideForm(FlaskForm):
    """Form สำหรับสร้าง date override"""
    date = DateField(
        'วันที่', 
        validators=[DataRequired(message='กรุณาเลือกวันที่')],
        format='%Y-%m-%d'
    )
    override_type = SelectField(
        'ประเภท',
        choices=[('custom', 'เวลาพิเศษ'), ('unavailable', 'วันหยุด')],
        default='custom'
    )
    custom_start_time = TimeField('เวลาเริ่มต้น', validators=[Optional()])
    custom_end_time = TimeField('เวลาสิ้นสุด', validators=[Optional()])
    reason = StringField(
        'เหตุผล', 
        validators=[Optional(), Length(0, 255)]
    )
    scope = SelectField(
        'ขอบเขต',
        choices=[('global', 'ใช้กับทุกเทมเพลต'), ('template', 'เฉพาะเทมเพลตที่เลือก')],
        default='template'
    )
    template_id = HiddenField()
    
    def validate_date(self, field):
        """ตรวจสอบว่าวันที่ไม่ใช่อดีต"""
        if field.data and field.data < datetime.now().date():
            raise ValidationError('ไม่สามารถเพิ่มวันพิเศษในอดีตได้')
    
    def validate_custom_end_time(self, field):
        """ตรวจสอบเวลาสิ้นสุดเมื่อเป็นเวลาพิเศษ"""
        if self.override_type.data == 'custom':
            if not self.custom_start_time.data:
                raise ValidationError('กรุณาใส่เวลาเริ่มต้น')
            if not field.data:
                raise ValidationError('กรุณาใส่เวลาสิ้นสุด')
            if field.data <= self.custom_start_time.data:
                raise ValidationError('เวลาสิ้นสุดต้องมากกว่าเวลาเริ่มต้น')
    
    def get_api_data(self):
        """แปลงข้อมูลเป็น format ที่ API ต้องการ"""
        data = {
            'date': self.date.data.strftime('%Y-%m-%d'),
            'is_unavailable': self.override_type.data == 'unavailable',
            'reason': self.reason.data or ''
        }
        
        if self.override_type.data == 'custom':
            data['custom_start_time'] = self.custom_start_time.data.strftime('%H:%M')
            data['custom_end_time'] = self.custom_end_time.data.strftime('%H:%M')
        
        # Handle template scope
        if self.scope.data == 'template' and self.template_id.data:
            data['template_id'] = int(self.template_id.data)
            data['template_scope'] = 'template'
        else:
            data['template_scope'] = 'global'
        
        return data

class QuickSetupForm(FlaskForm):
    """Form สำหรับ quick setup เวลาทำการ"""
    preset = SelectField(
        'รูปแบบเวลาทำการ',
        choices=[
            ('weekday_8_16', 'จันทร์-ศุกร์ (08:00-16:00)'),
            ('weekday_8_17', 'จันทร์-ศุกร์ (08:00-17:00)'),
            ('weekday_9_17', 'จันทร์-ศุกร์ (09:00-17:00)'),
            ('weekday_8_12_13_17', 'จันทร์-ศุกร์ (08:00-12:00, 13:00-17:00)'),
            ('everyday_9_17', 'ทุกวัน (09:00-17:00)'),
            ('custom', 'กำหนดเอง')
        ],
        default='weekday_8_17'
    )
    
    def get_preset_schedule(self):
        """ส่งคืน schedule ตาม preset ที่เลือก"""
        presets = {
            'weekday_8_16': {
                'schedule': {1: [['08:00', '16:00']], 2: [['08:00', '16:00']], 
                           3: [['08:00', '16:00']], 4: [['08:00', '16:00']], 5: [['08:00', '16:00']]},
                'name': 'จันทร์-ศุกร์ (08:00-16:00)',
                'description': 'เวลาทำการปกติ'
            },
            'weekday_8_17': {
                'schedule': {1: [['08:00', '17:00']], 2: [['08:00', '17:00']], 
                           3: [['08:00', '17:00']], 4: [['08:00', '17:00']], 5: [['08:00', '17:00']]},
                'name': 'จันทร์-ศุกร์ (08:00-17:00)',
                'description': 'เวลาทำการปกติ'
            },
            'weekday_9_17': {
                'schedule': {1: [['09:00', '17:00']], 2: [['09:00', '17:00']], 
                           3: [['09:00', '17:00']], 4: [['09:00', '17:00']], 5: [['09:00', '17:00']]},
                'name': 'จันทร์-ศุกร์ (09:00-17:00)',
                'description': 'เวลาทำการปกติ'
            },
            'weekday_8_12_13_17': {
                'schedule': {1: [['08:00', '12:00'], ['13:00', '17:00']], 
                           2: [['08:00', '12:00'], ['13:00', '17:00']], 
                           3: [['08:00', '12:00'], ['13:00', '17:00']], 
                           4: [['08:00', '12:00'], ['13:00', '17:00']], 
                           5: [['08:00', '12:00'], ['13:00', '17:00']]},
                'name': 'จันทร์-ศุกร์ (08:00-12:00, 13:00-17:00)',
                'description': 'เวลาทำการแบบพักเที่ยง'
            },
            'everyday_9_17': {
                'schedule': {0: [['09:00', '17:00']], 1: [['09:00', '17:00']], 
                           2: [['09:00', '17:00']], 3: [['09:00', '17:00']], 
                           4: [['09:00', '17:00']], 5: [['09:00', '17:00']], 6: [['09:00', '17:00']]},
                'name': 'ทุกวัน (09:00-17:00)',
                'description': 'เปิดทำการทุกวัน'
            }
        }
        
        return presets.get(self.preset.data, {})

# Helper functions สำหรับ populate form data
def populate_availability_form_from_api_data(form, api_data):
    """ใส่ข้อมูลจาก API เข้าไปใน form"""
    if not api_data or 'availabilities' not in api_data:
        return
    
    availabilities = api_data['availabilities']
    if not availabilities:
        return
    
    # Group availabilities by day
    first_record = availabilities[0]
    form.name.data = first_record['name']
    form.description.data = first_record.get('description', '')
    form.timezone.data = first_record.get('timezone', 'Asia/Bangkok')
    
    # จัดกลุ่มตาม day_of_week
    schedule_by_day = {}
    for record in availabilities:
        day_num = record['day_of_week']
        if day_num not in schedule_by_day:
            schedule_by_day[day_num] = []
        schedule_by_day[day_num].append({
            'start': record['start_time'],
            'end': record['end_time']
        })
    
    # ใส่ข้อมูลใน form
    day_fields = [form.sunday, form.monday, form.tuesday, form.wednesday, 
                  form.thursday, form.friday, form.saturday]
    
    for day_index, day_field in enumerate(day_fields):
        if day_index in schedule_by_day:
            day_field.enabled.data = True
            # ล้าง slots เก่า
            day_field.slots.entries.clear()
            
            # เพิ่ม slots ใหม่
            for slot_data in schedule_by_day[day_index]:
                # สร้าง entry ใหม่แล้วค่อยใส่ข้อมูล
                day_field.slots.append_entry()
                new_slot = day_field.slots.entries[-1]  # entry ที่เพิ่งสร้าง
                
                try:
                    new_slot.start_time.data = datetime.strptime(slot_data['start'], '%H:%M').time()
                    new_slot.end_time.data = datetime.strptime(slot_data['end'], '%H:%M').time()
                except (ValueError, KeyError):
                    # ถ้า parse ไม่ได้ใช้ค่า default
                    new_slot.start_time.data = time(8, 30)
                    new_slot.end_time.data = time(16, 30)
        else:
            day_field.enabled.data = False
            day_field.slots.entries.clear()
            # เพิ่ม 1 empty slot สำหรับ UI
            day_field.slots.append_entry()

def create_default_template_form():
    """สร้าง form พร้อมข้อมูลเริ่มต้น"""
    form = AvailabilityTemplateForm()
    
    # ตั้งค่าเริ่มต้นสำหรับจันทร์-ศุกร์
    weekdays = [form.monday, form.tuesday, form.wednesday, form.thursday, form.friday]
    for day_field in weekdays:
        day_field.enabled.data = True
        if len(day_field.slots.entries) == 0:
            day_field.slots.append_entry()
        day_field.slots.entries[0].start_time.data = time(8, 30)
        day_field.slots.entries[0].end_time.data = time(16, 30)
    
    # ตั้งค่าเริ่มต้นให้ form
    form.name.data = 'จันทร์-ศุกร์ (08:30-16:30)'
    form.description.data = 'เวลาทำการปกติวันธรรมดา'
    
    return form