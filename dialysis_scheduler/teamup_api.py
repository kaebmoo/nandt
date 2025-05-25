# teamup_api.py
import requests
import json
import csv
from datetime import datetime, timedelta

class TeamupAPI:
    """
    คลาสสำหรับการเชื่อมต่อกับ TeamUp Calendar API
    """
    
    def __init__(self, api_key, calendar_id):
        """
        กำหนดค่าเริ่มต้นสำหรับการเชื่อมต่อ
        """
        self.api_key = api_key
        self.calendar_id = calendar_id
        self.base_url = f"https://api.teamup.com/{calendar_id}"
        print(f"Base URL: {self.base_url}")
        
        self.headers = {
            'Accept': "application/json",
            'Content-Type': "application/json",
            'Teamup-Token': api_key
        }
        print(f"Headers: {self.headers}")
        
        # แคชข้อมูลปฏิทินย่อย
        self.subcalendars = {}
    
    def check_access(self):
        """
        ตรวจสอบการเข้าถึง API โดยการเรียก configuration
        
        returns: (boolean, str) - สถานะการเชื่อมต่อและข้อความ
        """
        try:
            response = requests.get(
                f"{self.base_url}/configuration",  # เปลี่ยนจาก check-access
                headers=self.headers
            )
            
            if response.status_code == 200:
                return True, "เชื่อมต่อสำเร็จ"
            else:
                return False, f"สถานะ: {response.status_code}, ข้อความ: {response.text}"
                
        except Exception as e:
            return False, str(e)
    
    def get_subcalendars(self):
        """
        ดึงรายการปฏิทินย่อย
        
        returns: dict - ข้อมูลปฏิทินย่อย
        """
        try:
            response = requests.get(
                f"{self.base_url}/subcalendars",
                headers=self.headers
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # เก็บข้อมูลในแคช
                for subcal in data.get('subcalendars', []):
                    self.subcalendars[subcal['name']] = subcal['id']
                
                return data
            else:
                error_msg = f"ไม่สามารถดึงรายการปฏิทินย่อยได้: {response.text}"
                print(error_msg)
                return {'error': error_msg, 'subcalendars': []}
                
        except Exception as e:
            error_msg = f"เกิดข้อผิดพลาดในการดึงรายการปฏิทินย่อย: {e}"
            print(error_msg)
            return {'error': error_msg, 'subcalendars': []}
    
    def get_subcalendar_id(self, name):
        """
        รับ ID ของปฏิทินย่อยจากชื่อ ถ้าไม่มีจะสร้างใหม่
        
        params:
            name: str - ชื่อปฏิทินย่อย
            
        returns: int - ID ของปฏิทินย่อย
        """
        # ดึงข้อมูลปฏิทินย่อยก่อนหากยังไม่มีในแคช
        if not self.subcalendars:
            self.get_subcalendars()
        
        if name in self.subcalendars:
            return self.subcalendars[name]
        
        # ถ้าไม่มีปฏิทินย่อยดังกล่าว ให้สร้างใหม่
        try:
            new_subcal = {
                'name': name,
                'color': 5,  # เปลี่ยนจาก string เป็น integer
                'active': True,
                'overlap': True
            }
            
            response = requests.post(
                f"{self.base_url}/subcalendars",
                headers=self.headers,
                data=json.dumps(new_subcal)
            )
            
            if response.status_code == 201:
                data = response.json()
                subcal_id = data['subcalendar']['id']
                self.subcalendars[name] = subcal_id
                return subcal_id
            else:
                error_msg = f"ไม่สามารถสร้างปฏิทินย่อยได้: {response.text}"
                print(error_msg)
                return None
                
        except Exception as e:
            error_msg = f"เกิดข้อผิดพลาดในการสร้างปฏิทินย่อย: {e}"
            print(error_msg)
            return None
    
    def get_events(self, start_date=None, end_date=None, subcalendar_id=None):
        """
        ดึงรายการกิจกรรมในช่วงเวลาที่กำหนด
        
        params:
            start_date: datetime - วันที่เริ่มต้น
            end_date: datetime - วันที่สิ้นสุด
            subcalendar_id: int|list - ID ของปฏิทินย่อย (ถ้ามี)
            
        returns: dict - ข้อมูลกิจกรรม
        """
        if start_date is None:
            start_date = datetime.now()
        if end_date is None:
            end_date = datetime.now() + timedelta(days=7)
            
        params = {
            'startDate': start_date.strftime('%Y-%m-%d'),
            'endDate': end_date.strftime('%Y-%m-%d')
        }
        
        # แก้ไขการส่ง subcalendarId ให้เป็น array ตาม API requirement
        if subcalendar_id:
            print(f"กรองตาม subcalendar_id: {subcalendar_id}")
            if isinstance(subcalendar_id, list):
                # ถ้าเป็น list อยู่แล้วให้ใช้เลย
                for i, sid in enumerate(subcalendar_id):
                    params[f'subcalendarId[{i}]'] = str(sid)
            else:
                # ถ้าเป็นค่าเดียวให้แปลงเป็น array format
                params['subcalendarId[0]'] = str(subcalendar_id)
        
        print(f"Parameters ที่จะส่งไป: {params}")  # Debug
        
        response = requests.get(
            f"{self.base_url}/events",
            headers=self.headers,
            params=params
        )
        
        print(f"Response status: {response.status_code}")  # Debug
        print(f"Response URL: {response.url}")  # Debug
        
        if response.status_code == 200:
            data = response.json()
            
            # เพิ่มข้อมูลปฏิทินย่อยให้กับแต่ละ event
            if 'events' in data:
                for event in data['events']:
                    # เพิ่มชื่อปฏิทินย่อยให้กับ event
                    subcalendar_names = []
                    if 'subcalendar_ids' in event and event['subcalendar_ids']:
                        for sid in event['subcalendar_ids']:
                            # หาชื่อปฏิทินย่อยจาก ID
                            subcal_name = self.get_subcalendar_name_by_id(sid)
                            if subcal_name:
                                subcalendar_names.append(subcal_name)
                    
                    # เพิ่ม field ใหม่สำหรับแสดงชื่อปฏิทินย่อย
                    event['subcalendar_names'] = subcalendar_names
                    event['subcalendar_display'] = ', '.join(subcalendar_names) if subcalendar_names else 'ไม่ระบุ'
            
            return data
        else:
            error_msg = f"ไม่สามารถดึงรายการกิจกรรมได้: {response.text}"
            print(error_msg)
            return {"error": error_msg, "events": []}
        
    def get_subcalendar_name_by_id(self, subcalendar_id):
        """
        หาชื่อปฏิทินย่อยจาก ID
        
        params:
            subcalendar_id: int - ID ของปฏิทินย่อย
            
        returns: str - ชื่อปฏิทินย่อย หรือ None ถ้าไม่พบ
        """
        # ถ้ายังไม่มีข้อมูลปฏิทินย่อยในแคช ให้ดึงมาก่อน
        if not self.subcalendars:
            self.get_subcalendars()
        
        # หาชื่อจาก ID (reverse lookup)
        for name, sid in self.subcalendars.items():
            if sid == subcalendar_id:
                return name
        
        # ถ้าไม่พบในแคช ให้ลองดึงข้อมูลใหม่
        try:
            subcals_data = self.get_subcalendars()
            if 'subcalendars' in subcals_data:
                for subcal in subcals_data['subcalendars']:
                    if subcal['id'] == subcalendar_id:
                        return subcal['name']
        except Exception as e:
            print(f"Error getting subcalendar name: {e}")
        
        return None
    
    def create_appointment(self, patient_data):
        """สร้างนัดหมายเดี่ยว"""
        try:
            # หาชื่อปฏิทินย่อยจากชื่อ
            subcalendar_id = self.get_subcalendar_id_by_name(patient_data['calendar_name'])
            if not subcalendar_id:
                return False, f"ไม่พบปฏิทินย่อย: {patient_data['calendar_name']}"
            
            # แปลงวันที่และเวลาเป็น ISO string
            start_date = patient_data['start_date']  # YYYY-MM-DD
            start_time = patient_data['start_time']  # HH:MM
            end_date = patient_data['end_date']     # YYYY-MM-DD  
            end_time = patient_data['end_time']     # HH:MM
            
            # สร้าง datetime string ในรูปแบบ ISO
            start_datetime_str = f"{start_date}T{start_time}:00"
            end_datetime_str = f"{end_date}T{end_time}:00"
            
            # สร้างข้อมูลสำหรับส่งไป API
            event_data = {
                "title": patient_data['title'],
                "start_dt": start_datetime_str,  # ใช้ ISO string
                "end_dt": end_datetime_str,      # ใช้ ISO string
                "all_day": False,
                "subcalendar_ids": [subcalendar_id]
            }
            
            # เพิ่มข้อมูลเสริม (ถ้ามี)
            if patient_data.get('location'):
                event_data['location'] = patient_data['location']
            if patient_data.get('who'):
                event_data['who'] = patient_data['who']
            if patient_data.get('description'):
                event_data['notes'] = patient_data['description']
            
            # เพิ่มการตั้งค่าเริ่มต้น
            event_data.update({
                'signup_enabled': False,
                'comments_enabled': False,
                'attachments': []
            })
            
            print("ข้อมูลที่จะส่งไปยัง API:")
            print(f"URL: {self.base_url}/events")
            print(f"Headers: {self.headers}")
            print(json.dumps(event_data, indent=2, ensure_ascii=False))
            
            # ส่งคำขอไป API
            response = requests.post(
                f"{self.base_url}/events",
                headers=self.headers,
                json=event_data
            )
            
            print(f"สถานะการตอบกลับ: {response.status_code}")
            print(f"เนื้อหาการตอบกลับ: {response.text}")
            
            if response.status_code == 201:
                event_id = response.json().get('event', {}).get('id')
                return True, event_id
            else:
                error_data = response.json() if response.text else {'error': 'Unknown error'}
                if isinstance(error_data, dict) and 'error' in error_data:
                    error_msg = error_data['error'].get('message', response.text)
                else:
                    error_msg = response.text
                return False, f"การสร้างนัดหมายล้มเหลว: {error_msg}"
                
        except Exception as e:
            print(f"Exception in create_appointment: {e}")
            import traceback
            traceback.print_exc()
            return False, str(e)
    
    def create_recurring_appointment(self, patient_data, rrule):
        """
        สร้างนัดหมายแบบ recurring ตาม RFC 5545
        
        params:
            patient_data: dict - ข้อมูลผู้ป่วย
            rrule: str - RRULE string เช่น "FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=12"
                
        returns: (boolean, str) - สถานะการสร้างนัดหมายและข้อความหรือ ID
        """
        # ดึง ID ของปฏิทินย่อย
        subcalendar_id = self.get_subcalendar_id(patient_data['calendar_name'])
        
        if not subcalendar_id:
            return False, "ไม่สามารถดึงหรือสร้างปฏิทินย่อยได้"
        
        # แปลงรูปแบบวันที่และเวลา
        start_dt = self._format_datetime_to_timestamp(patient_data['start_date'], patient_data['start_time'])
        
        # คำนวณ end_dt สำหรับ recurring series
        # สำหรับ recurring events ต้องใช้ end date ของ series ไม่ใช่ของ event เดียว
        start_datetime = self._parse_datetime(patient_data['start_date'], patient_data['start_time'])
        end_datetime = self._parse_datetime(patient_data['end_date'], patient_data['end_time'])
        
        # คำนวณระยะเวลาของแต่ละ event
        duration_minutes = int((end_datetime - start_datetime).total_seconds() / 60)
        
        # สำหรับ recurring events ให้ end_dt เป็นวันสุดท้ายของ series
        # ตัวอย่าง: ถ้า COUNT=12 และ FREQ=WEEKLY ก็คือ 12 สัปดาห์
        series_end_date = start_datetime + timedelta(weeks=12)  # ปรับตามต้องการ
        end_dt = int(series_end_date.timestamp())
        
        # สร้างข้อมูลสำหรับการสร้างกิจกรรม recurring
        event_data = {
            'title': patient_data['title'],
            'start_dt': start_dt,
            'end_dt': end_dt,
            'all_day': False,
            'rrule': rrule,  # เพิ่ม RRULE
            'location': patient_data.get('location', ''),
            'who': patient_data.get('who', ''),
            'notes': patient_data.get('description', ''),
            'subcalendar_ids': [subcalendar_id],
            'signup_enabled': False,
            'comments_enabled': False,
            'attachments': []
        }
        
        print("ข้อมูลสำหรับ Recurring Event:")
        print(f"RRULE: {rrule}")
        print(f"Duration (minutes): {duration_minutes}")
        print(f"ข้อมูล: {json.dumps(event_data, indent=2, ensure_ascii=False)}")
        
        try:
            response = requests.post(
                f"{self.base_url}/events",
                headers=self.headers,
                data=json.dumps(event_data)
            )
            
            print(f"สถานะการตอบกลับ: {response.status_code}")
            print(f"เนื้อหาการตอบกลับ: {response.text}")
            
            if response.status_code == 201:
                data = response.json()
                return True, data['event']['id']
            else:
                return False, f"การสร้างนัดหมาย recurring ล้มเหลว: {response.text}"
                
        except Exception as e:
            return False, f"เกิดข้อผิดพลาด: {e}"
    
    def generate_rrule(self, frequency='WEEKLY', days=None, count=None, until=None):
        """
        สร้าง RRULE string สำหรับ recurring events
        
        params:
            frequency: str - DAILY, WEEKLY, MONTHLY, YEARLY
            days: list - วันในสัปดาห์ ['MO', 'WE', 'FR'] สำหรับ WEEKLY
            count: int - จำนวนครั้งที่ repeat
            until: datetime - วันที่สิ้นสุด
            
        returns: str - RRULE string
        """
        rrule_parts = [f"FREQ={frequency}"]
        
        if days and frequency == 'WEEKLY':
            rrule_parts.append(f"BYDAY={','.join(days)}")
        
        if count:
            rrule_parts.append(f"COUNT={count}")
        elif until:
            until_str = until.strftime('%Y%m%dT%H%M%SZ')
            rrule_parts.append(f"UNTIL={until_str}")
        
        return ';'.join(rrule_parts)
    
    def create_recurring_appointments_simple(self, patient_data, selected_days, weeks):
        """สร้างนัดหมายเกิดซ้ำแบบง่าย"""
        try:
            # หาชื่อปฏิทินย่อยจากชื่อ
            subcalendar_id = self.get_subcalendar_id_by_name(patient_data['calendar_name'])
            if not subcalendar_id:
                return False, f"ไม่พบปฏิทินย่อย: {patient_data['calendar_name']}"
            
            # สร้าง RRULE
            days_str = ','.join(selected_days)
            rrule = f"FREQ=WEEKLY;BYDAY={days_str};COUNT={weeks}"
            
            print(f"ข้อมูลสำหรับ Recurring Event:")
            print(f"RRULE: {rrule}")
            
            # แปลงวันที่และเวลาเป็น ISO string
            start_date = patient_data['start_date']  # YYYY-MM-DD
            start_time = patient_data['start_time']  # HH:MM
            end_date = patient_data['end_date']     # YYYY-MM-DD  
            end_time = patient_data['end_time']     # HH:MM
            
            # สร้าง datetime string ในรูปแบบ ISO
            start_datetime_str = f"{start_date}T{start_time}:00"
            end_datetime_str = f"{end_date}T{end_time}:00"
            
            print(f"Start datetime: {start_datetime_str}")
            print(f"End datetime: {end_datetime_str}")
            
            # สร้างข้อมูลสำหรับส่งไป API
            event_data = {
                "title": patient_data['title'],
                "start_dt": start_datetime_str,  # ใช้ ISO string
                "end_dt": end_datetime_str,      # ใช้ ISO string
                "all_day": False,
                "rrule": rrule,
                "subcalendar_ids": [subcalendar_id]
            }
            
            # เพิ่มข้อมูลเสริม (ถ้ามี)
            if patient_data.get('location'):
                event_data['location'] = patient_data['location']
            if patient_data.get('who'):
                event_data['who'] = patient_data['who']
            if patient_data.get('description'):
                event_data['notes'] = patient_data['description']
            
            # เพิ่มการตั้งค่าเริ่มต้น
            event_data.update({
                'signup_enabled': False,
                'comments_enabled': False,
                'attachments': []
            })
            
            print("ข้อมูลที่จะส่งไป API:")
            print(json.dumps(event_data, indent=2, ensure_ascii=False))
            
            # ส่งคำขอไป API
            response = requests.post(
                f"{self.base_url}/events",
                headers=self.headers,
                json=event_data
            )
            
            print(f"สถานะการตอบกลับ: {response.status_code}")
            print(f"เนื้อหาการตอบกลับ: {response.text}")
            
            if response.status_code == 201:
                event_id = response.json().get('event', {}).get('id')
                return True, event_id
            else:
                error_data = response.json() if response.text else {'error': 'Unknown error'}
                if isinstance(error_data, dict) and 'error' in error_data:
                    error_msg = error_data['error'].get('message', response.text)
                else:
                    error_msg = response.text
                return False, f"การสร้างนัดหมายล้มเหลว: {error_msg}"
                
        except Exception as e:
            print(f"Exception in create_recurring_appointments_simple: {e}")
            import traceback
            traceback.print_exc()
            return False, str(e)
        
    def get_subcalendar_id_by_name(self, calendar_name):
        """หา subcalendar ID จากชื่อ"""
        try:
            subcals = self.get_subcalendars()
            for subcal in subcals.get('subcalendars', []):
                if subcal['name'] == calendar_name:
                    return subcal['id']
            return None
        except Exception as e:
            print(f"Error getting subcalendar ID: {e}")
            return None
    def update_appointment_status(self, event_id, status, calendar_id=None):
        """
        อัปเดตสถานะของนัดหมายโดยการแก้ไขชื่อเรื่อง
        
        params:
            event_id: str - ID ของนัดหมาย
            status: str - สถานะใหม่ (มาตามนัด, ยกเลิก, ไม่มา)
            calendar_id: str - ID ของปฏิทิน (ไม่จำเป็น)
            
        returns: (boolean, str) - สถานะการอัปเดตและข้อความ
        """
        try:
            # ดึงข้อมูลนัดหมายปัจจุบันก่อน
            response = requests.get(
                f"{self.base_url}/events/{event_id}",
                headers=self.headers
            )
            
            if response.status_code != 200:
                return False, f"ไม่สามารถดึงข้อมูลนัดหมายได้: {response.text}"
            
            event_data = response.json()['event']
            current_title = event_data['title']
            
            # ล้างสถานะเก่าออกจากชื่อเรื่อง
            clean_title = current_title
            status_markers = ['(มาตามนัด)', '(ยกเลิก)', '(ไม่มา)']
            for marker in status_markers:
                clean_title = clean_title.replace(marker, '').strip()
            
            # เพิ่มสถานะใหม่
            new_title = f"{clean_title} ({status})"
            
            # สร้างข้อมูลสำหรับการอัปเดต - ต้องใส่ id แม้ว่า API doc จะบอกว่า readOnly
            update_data = {
                'id': event_data['id'],  # API ยังต้องการ id อยู่
                'title': new_title,
                'start_dt': event_data['start_dt'],
                'end_dt': event_data['end_dt'],
                'all_day': event_data.get('all_day', False),
                'signup_enabled': event_data.get('signup_enabled', False),
                'comments_enabled': event_data.get('comments_enabled', False),
                'attachments': event_data.get('attachments', [])
            }
            
            # เพิ่มข้อมูลอื่นๆ ที่อาจจำเป็น
            if 'subcalendar_ids' in event_data:
                update_data['subcalendar_ids'] = event_data['subcalendar_ids']
            if 'location' in event_data:
                update_data['location'] = event_data['location']
            if 'who' in event_data:
                update_data['who'] = event_data['who']
            if 'notes' in event_data:
                update_data['notes'] = event_data['notes']
            
            # ส่งคำขออัปเดต
            update_response = requests.put(
                f"{self.base_url}/events/{event_id}",
                headers=self.headers,
                json=update_data
            )
            
            print(f"อัปเดตสถานะ: {update_response.status_code}")
            print(f"ข้อมูลที่ส่ง: {update_data}")
            print(f"ผลลัพธ์: {update_response.text}")
            
            if update_response.status_code == 200:
                return True, f"อัปเดตสถานะเป็น '{status}' สำเร็จ"
            else:
                error_msg = update_response.text
                try:
                    error_data = update_response.json()
                    if 'error' in error_data:
                        error_msg = error_data['error'].get('message', error_msg)
                except:
                    pass
                return False, f"การอัปเดตสถานะล้มเหลว: {error_msg}"
                
        except Exception as e:
            print(f"Exception in update_appointment_status: {e}")
            import traceback
            traceback.print_exc()
            return False, str(e)
    
    def import_from_csv(self, file_path):
        """
        นำเข้าตารางนัดหมายฟอกไตจากไฟล์ CSV
        """
        results = {
            'success': 0,
            'failed': 0,
            'errors': []
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for i, row in enumerate(reader, 1):
                    try:
                        # ตรวจสอบข้อมูลที่จำเป็น
                        required_fields = ['Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 'Calendar Name']
                        for field in required_fields:
                            if field not in row or not row[field]:
                                raise ValueError(f"ไม่พบข้อมูลที่จำเป็น: {field}")
                        
                        # แปลงข้อมูลเป็นรูปแบบที่ฟังก์ชัน create_appointment ต้องการ
                        patient_data = {
                            'title': row['Subject'],
                            'start_date': row['Start Date'],
                            'start_time': row['Start Time'],
                            'end_date': row['End Date'],
                            'end_time': row['End Time'],
                            'location': row.get('Location', ''),
                            'who': row.get('Who', ''),
                            'description': row.get('Description', ''),
                            'calendar_name': row['Calendar Name']
                        }
                        
                        # สร้างนัดหมาย
                        success, result = self.create_appointment(patient_data)
                        
                        if success:
                            results['success'] += 1
                        else:
                            results['failed'] += 1
                            results['errors'].append({
                                'row': i,
                                'patient': patient_data['title'],
                                'error': result
                            })
                            
                    except Exception as e:
                        results['failed'] += 1
                        results['errors'].append({
                            'row': i,
                            'error': str(e)
                        })
                
            return results
                
        except Exception as e:
            results['errors'].append({
                'error': f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}"
            })
            return results
    
    def _format_datetime_to_timestamp(self, date_str, time_str):
        """
        แปลงรูปแบบวันที่และเวลาเป็น Unix timestamp
        
        params:
            date_str: str - วันที่ในรูปแบบ DD/MM/YYYY
            time_str: str - เวลาในรูปแบบ HH:MM
            
        returns: int - Unix timestamp
        """
        try:
            dt = self._parse_datetime(date_str, time_str)
            return int(dt.timestamp())
            
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการแปลงรูปแบบวันที่และเวลา: {e}")
            return None
    
    def _parse_datetime(self, date_str, time_str):
        """
        แปลงวันที่และเวลาเป็น datetime object
        """
        if '/' in date_str:
            day, month, year = date_str.split('/')
            date_formatted = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        else:
            date_formatted = date_str
        
        time_parts = time_str.split(':')
        hour = time_parts[0].zfill(2)
        minute = time_parts[1].zfill(2) if len(time_parts) > 1 else "00"
        
        datetime_str = f"{date_formatted} {hour}:{minute}:00"
        return datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
    
    def _format_datetime(self, date_str, time_str):
        """
        แปลงรูปแบบวันที่และเวลาให้ถูกต้องตาม API (deprecated - ใช้ timestamp แทน)
        """
        try:
            if '/' in date_str:
                day, month, year = date_str.split('/')
                date_formatted = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            else:
                date_formatted = date_str
            
            time_parts = time_str.split(':')
            hour = time_parts[0].zfill(2)
            minute = time_parts[1].zfill(2) if len(time_parts) > 1 else "00"
            
            datetime_str = f"{date_formatted}T{hour}:{minute}:00+07:00"
            print(f"แปลงวันที่จาก {date_str} {time_str} เป็น {datetime_str}")
            return datetime_str
            
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการแปลงรูปแบบวันที่และเวลา: {e}")
            return f"{date_str}T{time_str}:00+07:00"